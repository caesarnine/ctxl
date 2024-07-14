import os
import subprocess

import pkg_resources
from anthropic import Anthropic, AnthropicBedrock
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

system_prompt = (
    pkg_resources.resource_string("ctxl", "system_prompt.txt").decode("utf-8").strip()
)

environment_info = subprocess.run(
    "cat /etc/os-release", shell=True, check=True, text=True, capture_output=True
)

shell_info = subprocess.run(
    "echo $SHELL", shell=True, check=True, text=True, capture_output=True
)

cwd = os.getcwd()

system_prompt = (
    "<environment_info>\n"
    + environment_info.stdout.strip()
    + f"\nSHELL={shell_info.stdout.strip()}\nCWD={cwd}\n</environment_info>"
    + "\n"
    + system_prompt
)


class ChatMode:
    def __init__(self, xml_context: str, bedrock: bool):

        if bedrock:
            self.client = AnthropicBedrock()
            self.model = "anthropic.claude-3-5-sonnet-20240620-v1:0"
        else:
            if not ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            self.client = Anthropic()
            self.model = "claude-3-5-sonnet-20240620"
        self.xml_context = xml_context
        self.conversation_history = []

    def get_user_confirmation(self, command: str) -> bool:
        while True:
            user_input = (
                input(f"\nAllow execution of command: '{command}'? (y/n): ")
                .lower()
                .strip()
            )
            if user_input in ["y", "yes"]:
                return True
            elif user_input in ["n", "no"]:
                return False
            else:
                print("Invalid input. Please enter 'y' for yes or 'n' for no.")

    def get_claude_response(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})

        try:
            current_response = ""
            current_command = ""

            while True:
                with self.client.messages.stream(
                    system=system_prompt,
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
                    return current_response + assistant_message
                elif stop_reason == "stop_sequence":
                    if stop_sequence == "<command>":
                        current_command = ""
                        current_response += assistant_message + "<command>"
                        print("<command>", end="", flush=True)
                    elif stop_sequence == "</command>":
                        current_command = assistant_message
                        print("</command>", flush=True)

                        user_allowed, result = self.execute_command(current_command)
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
                            return current_response
                        else:
                            print(result)

        except Exception as e:
            error_message = f"Error communicating with Claude API: {str(e)}"
            print(error_message)
            return error_message

    @staticmethod
    def execute_command(command: str) -> tuple[bool, str]:
        user_confirmation = (
            input(f"Execute command: '{command}'? (y/n): ").strip().lower()
        )
        if user_confirmation not in ["y", "yes"]:
            return (
                False,
                """<command_result userskipped="true">\nUser skipped execution.\n</command_result>""",
            )

        result = subprocess.run(
            command, shell=True, check=False, text=True, capture_output=True
        )
        return (
            True,
            f"""<command_result userskipped="false" returncode="{result.returncode}">\n{result.stdout}\n{result.stderr}\n</command_result>""",
        )

    def start(self):
        print(
            "Entering interactive mode with Claude Sonnet. Type 'exit' to end the session or 'help' for available commands."
        )

        # Send an initial message to Claude to analyze the project
        initial_response = self.get_claude_response(self.xml_context)
        print("Claude:", initial_response)

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


def start_chat_mode(xml_context: str):
    chat = ChatMode(xml_context)
    chat.start()


if __name__ == "__main__":
    # This block is mainly for testing purposes
    # In normal operation, chat mode would be started from ctxl.py
    sample_xml = """
    <root>
        <project_context>
            <file path="example.py">
                <content>
                    print("Hello, World!")
                </content>
            </file>
        </project_context>
        <task>Analyze this simple project</task>
    </root>
    """
    start_chat_mode(sample_xml)
