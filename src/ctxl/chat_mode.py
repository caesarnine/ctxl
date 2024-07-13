import os
import re
import subprocess
from typing import List, Tuple

import pkg_resources
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

system_prompt = (
    pkg_resources.resource_string("ctxl", "system_prompt.txt").decode("utf-8").strip()
)


class ChatMode:
    def __init__(self, xml_context: str):
        if not ANTHROPIC_API_KEY:
            raise ValueError("ANTHROPIC_API_KEY not found in environment variables")

        self.client = Anthropic(api_key=ANTHROPIC_API_KEY)
        self.xml_context = xml_context
        self.conversation_history = []

    def get_claude_response(self, user_input: str) -> str:
        self.conversation_history.append({"role": "user", "content": user_input})

        try:
            response = self.client.messages.create(
                system=system_prompt + f"<cwd>{os.getcwd()}</cwd>",
                model="claude-3-5-sonnet-20240620",
                messages=self.conversation_history,
                max_tokens=4096,
            )

            assistant_message = response.content[0].text
            self.conversation_history.append(
                {"role": "assistant", "content": assistant_message}
            )

            return assistant_message
        except Exception as e:
            return f"Error communicating with Claude API: {str(e)}"

    @staticmethod
    def extract_shell_commands(response: str) -> List[Tuple[str, str, str]]:
        pattern = r"<command(?: id=\"\d+\")?>(.*?)</command>"
        matches = re.findall(pattern, response, re.DOTALL)
        command_ids = re.findall(r'<command id="(\d+)">', response)
        return [
            (command_id, match.strip(), f"<command>\n{match}\n</command>")
            for command_id, match in zip(command_ids, matches)
        ]

    @staticmethod
    def execute_command(command_id, command: str) -> str:
        result = subprocess.run(
            command, shell=True, check=False, text=True, capture_output=True
        )
        return f"""<command_result commandid="{command_id}" returncode="{result.returncode}">\n{result.stdout}\n{result.stderr}\n</command_result>"""

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

                response = self.get_claude_response(user_input)
                print("Claude:", response)

                commands = self.extract_shell_commands(response)
                for command_id, command, block in commands:
                    print(f"\nDetected shell command:\n{block}")

                    confirm = (
                        input("Do you want to execute this command? (y/n): ")
                        .strip()
                        .lower()
                    )
                    if confirm == "y":
                        print("Executing command...")
                        output = self.execute_command(command_id, command)
                        print("Command output:")
                        print(output)
                        # Send the output back to Claude for context
                        response = self.get_claude_response(output)
                        print("Claude:", response)
                    else:
                        print("Command execution skipped.")
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
