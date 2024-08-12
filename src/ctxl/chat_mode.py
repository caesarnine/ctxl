import argparse
import contextlib
import fnmatch
import json
import logging
import os
import re
import subprocess
from datetime import datetime  # Ensure this import remains
from difflib import unified_diff
from io import StringIO
from pathlib import Path

import pkg_resources
from anthropic import Anthropic, AnthropicBedrock
from diff_match_patch import diff_match_patch
from dotenv import load_dotenv

from .version_control import VersionControl

# Add logging configuration
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)


dmp = diff_match_patch()
dmp.Match_Distance = 1000000

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


@contextlib.contextmanager
def capture_logs_and_output():
    log_output = StringIO()
    handler = logging.StreamHandler(log_output)
    logger = logging.getLogger()
    logger.addHandler(handler)

    # Store the original level to restore it later
    original_level = logger.level
    logger.setLevel(logging.INFO)

    try:
        yield log_output
    finally:
        logger.removeHandler(handler)
        # Restore the original logging level
        logger.setLevel(original_level)


def load_gitignore(path):
    gitignore = set()
    gitignore_path = os.path.join(path, ".gitignore")
    if os.path.exists(gitignore_path):
        with open(gitignore_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    gitignore.add(line)
    return gitignore


def should_ignore(path, name, gitignore, ignore_dotfiles):
    if ignore_dotfiles and name.startswith("."):
        return True
    if gitignore:
        for pattern in gitignore:
            if fnmatch.fnmatch(name, pattern) or fnmatch.fnmatch(
                os.path.join(path, name), pattern
            ):
                return True
    return False


def generate_tree(startpath, max_depth=3, ignore_dotfiles=True, use_gitignore=True):
    gitignore = load_gitignore(startpath) if use_gitignore else set()
    tree = []
    for root, dirs, files in os.walk(startpath):
        level = root.replace(startpath, "").count(os.sep)
        if level > max_depth:
            continue
        indent = "│   " * (level)
        tree.append(f"{indent}├── {os.path.basename(root)}/")
        subindent = "│   " * (level + 1)

        dirs[:] = [
            d for d in dirs if not should_ignore(root, d, gitignore, ignore_dotfiles)
        ]
        files = [
            f for f in files if not should_ignore(root, f, gitignore, ignore_dotfiles)
        ]

        for f in files:
            tree.append(f"{subindent}├── {f}")
    return "\n".join(tree)


cwd = os.getcwd()

system_prompt = (
    pkg_resources.resource_string("ctxl", "system_prompt.txt").decode("utf-8").strip()
)

environment_info = subprocess.run(
    "cat /etc/os-release", shell=True, check=True, text=True, capture_output=True
)

shell_info = subprocess.run(
    "echo /bin/bash", shell=True, check=True, text=True, capture_output=True
)


def generate_system_prompt():
    directory_tree = generate_tree(".", ignore_dotfiles=True, use_gitignore=True)

    contextualized_system_prompt = f"""<environment_info>
    {environment_info.stdout.strip()}
    SHELL={shell_info.stdout.strip()}
    CWD={cwd}
    </environment_info>

    <cwd_tree>
    {directory_tree}
    </cwd_tree>

    {system_prompt}"""

    return contextualized_system_prompt


def lint_and_format_code(path=".") -> str:
    command = f"ruff check --fix {path} && ruff format {path}"
    result = subprocess.run(
        command, shell=True, check=False, text=True, capture_output=True
    )
    return f"<lint_result>\n{result.stdout}\n{result.stderr}\n</lint_result>"


def parse_diff(diff_text):
    lines = diff_text.split("\n")
    diffs = []
    current_hunk = []
    for line in lines:
        # ignore the file headers
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            if current_hunk:
                diffs.append(current_hunk)
            current_hunk = []
        if line.startswith(" "):
            current_hunk.append((0, line[1:] + "\n"))
        elif line.startswith("+"):
            current_hunk.append((1, line[1:] + "\n"))
        elif line.startswith("-"):
            current_hunk.append((-1, line[1:] + "\n"))

    if current_hunk:
        dmp.diff_cleanupSemanticLossless(current_hunk)
        dmp.diff_cleanupMerge(current_hunk)
        dmp.diff_cleanupEfficiency(current_hunk)
        diffs.append(current_hunk)

    return diffs


def save_snapshot(
    file_path: Path,
    original_content: str,
    applied_diff: str,
    updated_content: str,
    unified_diff: str,
    lint_output: str,
):
    ctxl_dir = Path.cwd() / ".ctxl"
    ctxl_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().isoformat(timespec="seconds").replace(":", "-")
    snapshot_file = ctxl_dir / f"snapshot_{timestamp}.json"

    snapshot_data = {
        "file_path": str(file_path),
        "original_content": original_content,
        "applied_diff": applied_diff,
        "updated_content": updated_content,
        "post_diff": unified_diff,
        "lint_output": lint_output,
        "timestamp": timestamp,
    }

    with snapshot_file.open("w") as f:
        json.dump(snapshot_data, f, indent=2)


def apply_diff(file_path: Path, diff_text: str) -> str:
    file_path = Path(file_path)  # Ensure file_path is a Path object

    # to handle the case where it's a diff for a new file
    if not file_path.exists():
        file_path.touch()

    with file_path.open("r") as f:
        original_content = f.read()

    # Generate unified diff
    hunk_diffs = parse_diff(diff_text)
    hunk_patches = [dmp.patch_make(hunk) for hunk in hunk_diffs]

    failed_hunks = []
    text = original_content

    for i, patch in enumerate(hunk_patches, 1):
        text, applied_successfully = dmp.patch_apply(patch, text)

        if not all(applied_successfully):
            failed_hunks.append(str(i))

    if failed_hunks:
        failed_hunks_str = ", ".join(failed_hunks)
        return f"Failed to apply hunk(s): {failed_hunks_str}. The file has not been modified."

    with file_path.open("w") as f:
        f.write(text)

    lint_output = lint_and_format_code()

    with file_path.open("r") as f:
        updated_content = f.read()

    # Generate unified diff
    unified_diff_lines = list(
        unified_diff(
            original_content.splitlines(keepends=True),
            updated_content.splitlines(keepends=True),
            fromfile=str(file_path),
            tofile=str(file_path),
            lineterm="",
        )
    )
    unified_diff_text = "".join(unified_diff_lines)

    with file_path.open("w") as f:
        f.write(text)

    # Save snapshot after applying the diff
    save_snapshot(
        file_path,
        original_content,
        diff_text,
        updated_content,
        unified_diff_text,
        lint_output,
    )
    return updated_content


class ChatMode:
    def __init__(self, bedrock: bool, version_control: VersionControl) -> None:
        if bedrock:
            self.client = AnthropicBedrock()
            self.model = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        else:
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            self.client = Anthropic()
            self.model: str = "claude-3-5-sonnet-20240620"
        self.conversation_history: list[dict[str, str]] = []
        self.version_control = version_control
        self.chat_dir: str = os.path.join(os.getcwd(), ".ctxl_chats")
        self.loaded_chat_path: str | None = None
        os.makedirs(self.chat_dir, exist_ok=True)

    def list_chats(self):
        chat_files = sorted(os.listdir(self.chat_dir), reverse=True)
        if not chat_files:
            print("No saved chats found.")
        else:
            print("Available chats:")
            for i, chat in enumerate(chat_files, 1):
                print(f"{i}. {chat}")

    def switch_chat(self, chat_number):
        chat_files = sorted(os.listdir(self.chat_dir), reverse=True)
        if 1 <= chat_number <= len(chat_files):
            selected_chat = chat_files[chat_number - 1]
            filepath = os.path.join(self.chat_dir, selected_chat)
            with open(filepath, "r") as f:
                self.conversation_history = json.load(f)
            self.loaded_chat_path = filepath
            print(f"Switched to chat: {selected_chat}")
        else:
            print("Invalid chat number. Use 'list' to see available chats.")

    def clear_history(self):
        self.conversation_history = []
        print("Conversation history cleared.")

    def execute_with_versioning(
        self, command: str, user_initiated: bool = False, is_diff: bool = False
    ) -> tuple[bool, str]:
        if not user_initiated:
            user_confirmation = (
                input(f"Execute command: '{command}'? (y/n): ").strip().lower()
            )
            if user_confirmation.strip() not in ["y", "yes", ""]:
                return (
                    False,
                    """<result userskipped="true">\nUser skipped execution.\n</result>""",
                )
        target_pattern = r"<target>(.*)</target>"
        content_pattern = r"<content>(.*)</content>"
        purpose_pattern = r"<purpose>(.*)</purpose>"

        target_match = re.search(target_pattern, command, re.DOTALL)
        target_path = target_match.group(1) if target_match else None

        # Find the content
        content_match = re.search(content_pattern, command, re.DOTALL)
        content = content_match.group(1).strip() if content_match else None

        if user_initiated:
            content = command.removeprefix("!").strip()

        # Find the purpose
        purpose_match = re.search(purpose_pattern, command, re.DOTALL)
        purpose = purpose_match.group(1).strip() if purpose_match else None

        if not is_diff:
            result = subprocess.run(
                content,
                shell=True,
                check=False,
                text=True,
                capture_output=True,
                executable="/bin/bash",
            )

            commit_message = purpose if purpose else f"Executed command: {command}"

            commit_hash = self.version_control.create_new_version(commit_message)

            lint_result = lint_and_format_code()

            output = f"""<result userskipped="false" returncode="{result.returncode}" commit_hash="{commit_hash}">\n{result.stdout}\n{result.stderr}\n{lint_result}</result>"""
        else:
            commit_message = purpose if purpose else f"Applied diff to {target_path}"

            result = apply_diff(target_path, content)

            commit_hash = self.version_control.create_new_version(
                purpose,
            )

            lint_result = lint_and_format_code()

            output = f"""<result userskipped="false" commit_hash="{commit_hash}"><updated_file>\n{result}\n</updated_file>\n{lint_result}\n</result>"""

        return (True, output)

    def get_claude_response(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})
        contextualized_system_prompt = generate_system_prompt()

        try:
            current_response = ""
            current_command = ""

            while True:
                with self.client.messages.stream(
                    system=contextualized_system_prompt,
                    model=self.model,
                    messages=self.conversation_history
                    + [{"role": "assistant", "content": current_response}],
                    max_tokens=8192,
                    stop_sequences=["<command>", "</command>", "<diff>", "</diff>"],
                    extra_headers={
                        "anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"
                    },
                ) as stream:
                    assistant_message = ""
                    for event in stream:
                        if event.type == "content_block_delta":
                            if event.delta.type == "text_delta":
                                print(event.delta.text, end="", flush=True)
                                assistant_message += event.delta.text
                        elif event.type == "message_delta":
                            if event.delta.stop_reason:
                                stop_reason = event.delta.stop_reason
                            if event.delta.stop_sequence:
                                stop_sequence = event.delta.stop_sequence

                if stop_reason == "end_turn":
                    self.conversation_history.append(
                        {
                            "role": "assistant",
                            "content": current_response + assistant_message,
                        }
                    )
                    self.save_chat()
                    return current_response + assistant_message
                elif stop_reason == "stop_sequence":
                    if stop_sequence == "<command>":
                        current_command = ""
                        current_response += assistant_message + "<command>"
                        print("<command>", end="", flush=True)
                    elif stop_sequence == "</command>":
                        current_command = assistant_message
                        print("</command>", flush=True)

                        user_allowed, result = self.execute_with_versioning(
                            current_command
                        )
                        print(result, end="", flush=True)
                        current_response += assistant_message + "</command>\n" + result

                        if not user_allowed:
                            print(
                                "Command skipped by user. Continuing conversation...",
                                flush=True,
                            )
                            self.conversation_history.append(
                                {
                                    "role": "assistant",
                                    "content": current_response,
                                }
                            )
                            self.save_chat()
                            return current_response

                    elif stop_sequence == "<diff>":
                        current_diff = ""
                        current_response += assistant_message + "<diff>"
                        print("<diff>", end="", flush=True)
                    elif stop_sequence == "</diff>":
                        current_diff = assistant_message
                        print("</diff>", flush=True)
                        current_diff = "<diff>\n" + current_diff + "</diff>\n"

                        user_allowed, result = self.execute_with_versioning(
                            current_diff, is_diff=True
                        )
                        print(result, end="", flush=True)
                        current_response += assistant_message + "</diff>\n" + result

                        if not user_allowed:
                            print(
                                "Diff not applied by user. Continuing conversation...",
                                flush=True,
                            )
                            self.conversation_history.append(
                                {
                                    "role": "assistant",
                                    "content": current_response,
                                }
                            )
                            self.save_chat()
                            return current_response

        except Exception as e:
            error_message = f"Error communicating with Claude API: {str(e)}"
            print(error_message)
            return error_message

    def start(self):
        print(
            "Entering interactive mode with Claude Sonnet. Type 'exit' to end the session or '/help' for available commands."
        )

        resume_chat = (
            input("Would you like to resume the previous chat? (y/n): ").lower().strip()
        )
        if resume_chat in ["y", "yes"]:
            if not self.load_latest_chat():
                print("Starting a new chat.")
        else:
            print("Starting a new chat.")

        full_user_input = ""
        while True:
            try:
                print("\n")
                user_input = input("User: ").strip()
                full_user_input += user_input + "\n"

                if user_input.startswith("!"):
                    command = user_input[1:].strip()
                    _, result = self.execute_with_versioning(
                        command, user_initiated=True
                    )
                    full_user_input += f"<command>{command}</command>\n{result}\n"
                    print(result)
                    continue

                if user_input.lower() == "exit":
                    print("Exiting interactive mode. Goodbye!")
                    break
                elif user_input.lower() == "/help":
                    print("Available commands:")
                    print("  exit: Exit interactive mode")
                    print("  /help: Display this help message")
                    print("  /list: List available saved chats")
                    print("  /switch <number>: Switch to a specific chat")
                    print("  /clear: Clear current conversation history")
                    print("  !<bash_command>: Execute a bash command directly")
                    print(
                        "Any other input will be sent to Claude Sonnet for processing."
                    )
                    continue
                elif user_input.lower() == "/list":
                    self.list_chats()
                    continue
                elif user_input.lower().startswith("/switch "):
                    chat_number = int(user_input.split()[1])
                    self.switch_chat(chat_number)
                    continue
                elif user_input.lower() == "/clear":
                    self.clear_history()
                    continue

                print("Contextual: ", end="")
                self.get_claude_response(full_user_input)
                full_user_input = ""
                # We don't need to print the response here as it's already printed in get_claude_response
            except KeyboardInterrupt:
                print("\nKeyboard interrupt detected. Exiting interactive mode.")
                break
            except Exception as e:
                print(f"An error occurred: {str(e)}")

    def save_chat(self):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"chat_{timestamp}.json"
        filepath = (
            os.path.join(self.chat_dir, filename)
            if not self.loaded_chat_path
            else self.loaded_chat_path
        )
        with open(filepath, "w") as f:
            json.dump(self.conversation_history, f)

    def load_latest_chat(self):
        chat_files = sorted(os.listdir(self.chat_dir), reverse=True)
        if not chat_files:
            print("No previous chats found.")
            return False
        latest_chat = chat_files[0]
        filepath = os.path.join(self.chat_dir, latest_chat)
        self.loaded_chat_path = filepath
        with open(filepath, "r") as f:
            self.conversation_history = json.load(f)
        print(f"Loaded chat from {filepath}")
        return True


def main():
    parser = argparse.ArgumentParser(description="Chat Mode CLI")
    parser.add_argument(
        "--bedrock",
        action="store_true",
        help="Use AnthropicBedrock instead of Anthropic",
    )
    parser.add_argument(
        "--show-dotfiles",
        action="store_true",
        help="Show dotfiles in the directory tree",
    )
    parser.add_argument(
        "--ignore-gitignore",
        action="store_true",
        help="Ignore .gitignore when generating the directory tree",
    )
    args = parser.parse_args()

    version_control = (
        VersionControl()
    )  # You might need to adjust this based on how VersionControl is initialized
    chat = ChatMode(bedrock=args.bedrock, version_control=version_control)
    chat.start()


if __name__ == "__main__":
    main()
