import argparse
import contextlib
import fnmatch
import json
import logging
import os
import re
import subprocess
from datetime import datetime
from io import StringIO
from pathlib import Path

import pkg_resources
from anthropic import Anthropic, AnthropicBedrock
from diff_match_patch import diff_match_patch
from dotenv import load_dotenv

from .version_control import VersionControl

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


def parse_diff(diff_text):
    lines = diff_text.split("\n")
    diffs = []
    current_hunk = []
    for line in lines:
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


def apply_diff(file_path, diff_text):
    p = Path(file_path)

    # to handle the case where it's a diff for a new file
    if not p.exists():
        p.touch()

    with p.open("r") as f:
        text = f.read()

    hunk_diffs = parse_diff(diff_text)
    hunk_patches = [dmp.patch_make(hunk) for hunk in hunk_diffs]

    failed_hunks = []

    for i, patch in enumerate(hunk_patches, 1):
        text, applied_successfully = dmp.patch_apply(patch, text)

        if not all(applied_successfully):
            failed_hunks.append(i)

    if failed_hunks:
        failed_hunks = "\n".join(map(str, failed_hunks))
        return (
            f"Failed to apply hunk(s): {failed_hunks}. The file has not been modified."
        )

    with p.open("w") as f:
        f.write(text)

    return text


class ChatMode:
    def __init__(self, bedrock: bool, version_control: VersionControl):
        if bedrock:
            self.client = AnthropicBedrock()
            self.model = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        else:
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            self.client = Anthropic()
            self.model = "claude-3-5-sonnet-20240620"
        self.conversation_history = []
        self.version_control = version_control
        self.chat_dir = os.path.join(os.getcwd(), ".ctxl_chats")
        self.loaded_chat_path = None
        self.session_branch = None
        os.makedirs(self.chat_dir, exist_ok=True)

    def execute_with_versioning(
        self, command: str, user_initiated: bool = False, is_diff: bool = False
    ) -> tuple[bool, str]:
        if not user_initiated:
            user_confirmation = (
                input(f"Execute command: '{command}'? (y/n): ").strip().lower()
            )
            if user_confirmation not in ["y", "yes"]:
                return (
                    False,
                    """<result userskipped="true">\nUser skipped execution.\n</result>""",
                )
            target_pattern = r"<target>(.*?)</target>"
            content_pattern = r"<content>(.*?)</content>"
            purpose_pattern = r"<purpose>(.*?)</purpose>"

            target_match = re.search(target_pattern, command, re.DOTALL)
            target_path = target_match.group(1) if target_match else None

            # Find the content
            content_match = re.search(content_pattern, command, re.DOTALL)
            content = content_match.group(1).strip() if content_match else None

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

                # Create a new commit in the session branch
                commit_hash = self.version_control.create_new_version(
                    commit_message, branch=self.session_branch
                )

                output = f"""<result userskipped="false" returncode="{result.returncode}" commit_hash="{commit_hash}">\n{result.stdout}\n{result.stderr}\n</result>"""
            else:
                commit_message = (
                    purpose if purpose else f"Applied diff to {target_path}"
                )

                with capture_logs_and_output() as log_output:
                    result = apply_diff(target_path, content)

                commit_hash = self.version_control.create_new_version(
                    purpose, branch=self.session_branch
                )

                output = f"""<result userskipped="false" commit_hash="{commit_hash}">\n<logs>\n{log_output.getvalue()}\n</logs>\n<edited_file>\n{result}\n</edited_file></result>"""

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
                    max_tokens=4096,
                    stop_sequences=["<command>", "</command>", "<diff>", "</diff>"],
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
            "Entering interactive mode with Claude Sonnet. Type 'exit' to end the session or 'help' for available commands."
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
                elif user_input.lower() == "help":
                    print("Available commands:")
                    print("  exit: Exit interactive mode")
                    print("  help: Display this help message")
                    print("  !<bash_command>: Execute a bash command directly")
                    print(
                        "Any other input will be sent to Claude Sonnet for processing."
                    )
                    continue

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
        print(f"Chat saved to {filepath}")

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

    def start_session(self):
        self.session_branch = f"llm-session-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        self.version_control.create_branch(self.session_branch)
        print(f"Started new session: {self.session_branch}")


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
