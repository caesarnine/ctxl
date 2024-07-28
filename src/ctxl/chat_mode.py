import argparse
import fnmatch
import json
import os
import subprocess
from collections import defaultdict
from datetime import datetime

import pkg_resources
from anthropic import Anthropic, AnthropicBedrock
from dotenv import load_dotenv

from .version_control import VersionControl

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")


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

    def format_diff(
        self, diff: str, max_lines: int = 50, context_lines: int = 3
    ) -> str:

        # ANSI color codes
        RED = "\033[91m"
        GREEN = "\033[92m"
        YELLOW = "\033[93m"
        RESET = "\033[0m"

        lines = diff.split("\n")
        formatted_lines = []
        file_changes = defaultdict(lambda: {"added": 0, "removed": 0})
        current_file = None
        changes_count = 0

        for line in lines:
            if line.startswith("diff --git"):
                current_file = line.split()[-1].lstrip("b/")
                formatted_lines.append(f"\n{YELLOW}{line}{RESET}")
            elif line.startswith("+++") or line.startswith("---"):
                formatted_lines.append(f"{YELLOW}{line}{RESET}")
            elif line.startswith("+"):
                file_changes[current_file]["added"] += 1
                changes_count += 1
                formatted_lines.append(f"{GREEN}{line}{RESET}")
            elif line.startswith("-"):
                file_changes[current_file]["removed"] += 1
                changes_count += 1
                formatted_lines.append(f"{RED}{line}{RESET}")
            elif line.startswith("@@"):
                formatted_lines.append(f"{YELLOW}{line}{RESET}")
            else:
                formatted_lines.append(line)

        # Summarize changes
        summary = [f"{YELLOW}Changes summary:{RESET}"]
        for file, changes in file_changes.items():
            summary.append(f"  {file}: +{changes['added']} -{changes['removed']}")
        summary.append(f"Total: {changes_count} lines changed")

        # Limit output for large diffs
        if len(formatted_lines) > max_lines:
            context_start = max(0, (max_lines - context_lines) // 2)
            context_end = max(
                0, len(formatted_lines) - (max_lines - context_lines) // 2
            )
            formatted_lines = (
                formatted_lines[:context_start]
                + [
                    f"{YELLOW}... ({len(formatted_lines) - max_lines} lines skipped) ...{RESET}"
                ]
                + formatted_lines[context_end:]
            )

        return "\n".join(summary + ["\n"] + formatted_lines)

    def execute_command_with_versioning(self, command: str) -> tuple[bool, str]:
        user_confirmation = (
            input(f"Execute command: '{command}'? (y/n): ").strip().lower()
        )
        if user_confirmation not in ["y", "yes"]:
            return (
                False,
                """<command_result userskipped="true">\nUser skipped execution.\n</command_result>""",
            )

        result = subprocess.run(
            command,
            shell=True,
            check=False,
            text=True,
            capture_output=True,
            executable="/bin/bash",
        )

        # Create a new commit in the session branch
        commit_hash = self.version_control.create_new_version(
            f"Executed command: {command}", branch=self.session_branch
        )

        output = f"""<command_result userskipped="false" returncode="{result.returncode}" commit_hash="{commit_hash}">\n{result.stdout}\n{result.stderr}\n</command_result>"""

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
                    stop_sequences=["<command>", "</command>"],
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

                        user_allowed, result = self.execute_command_with_versioning(
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

        while True:
            try:
                user_input = input("User: ").strip()

                if user_input.lower() == "exit":
                    print("Exiting interactive mode. Goodbye!")
                    break
                elif user_input.lower() == "help":
                    print("Available commands:")
                    print("  exit: Exit interactive mode")
                    print("  help: Display this help message")
                    print(
                        "Any other input will be sent to Claude Sonnet for processing."
                    )
                    continue

                self.get_claude_response(user_input)
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
