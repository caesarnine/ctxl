import json
import logging
import os
import subprocess
from typing import Any, Dict, Generator, List

import pkg_resources
from dotenv import load_dotenv

from ..utils.file_utils import generate_tree
from ..version_control import VersionControl
from .ai_client import AIClient, create_ai_client
from .executor import CommandExecutor, lint_and_format_code

logger = logging.getLogger(__name__)

# Logging configuration
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("anthropic").setLevel(logging.WARNING)
logging.getLogger("ctxl.chat.session").setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Configuration Management
class Config:
    def __init__(self):
        load_dotenv()
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.cwd = os.getcwd()
        self.environment_info = self._get_environment_info()
        self.shell_info = self._get_shell_info()
        self.system_prompt = self._load_system_prompt()

    def _get_environment_info(self):
        return subprocess.run(
            "cat /etc/os-release",
            shell=True,
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def _get_shell_info(self):
        return subprocess.run(
            "echo /bin/bash", shell=True, check=True, text=True, capture_output=True
        ).stdout.strip()

    def _load_system_prompt(self):
        return (
            pkg_resources.resource_string("ctxl", "system_prompt.txt")
            .decode("utf-8")
            .strip()
        )


tool_schemas = [
    {
        "name": "execute_command",
        "description": "Execute a shell command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to execute",
                },
                "purpose": {
                    "type": "string",
                    "description": "The purpose of the command",
                },
            },
            "required": ["command", "purpose"],
        },
    },
    {
        "name": "apply_diff",
        "description": "Apply a diff to the codebase",
        "input_schema": {
            "type": "object",
            "properties": {
                "diff": {
                    "type": "string",
                    "description": "The diff to apply to the codebase",
                },
                "purpose": {
                    "type": "string",
                    "description": "The purpose of the diff application",
                },
                "target_path": {
                    "type": "string",
                    "description": "The target path for the file.",
                },
            },
            "required": ["diff", "target_path", "purpose"],
        },
    },
]


class State:
    def __init__(
        self,
        name: str,
        on: Dict[str, str] = None,
        entry: List[str] = None,
        exit: List[str] = None,
    ):
        self.name = name
        self.on = on or {}
        self.entry = entry or []
        self.exit = exit or []


class StateMachine:
    def __init__(self, states: Dict[str, State], initial: str):
        self.states = states
        self.current_state = initial
        self.context = {}

    def transition(self, event: str) -> None:
        current_state = self.states[self.current_state]
        if event in current_state.on:
            next_state = current_state.on[event]
            for action in current_state.exit:
                getattr(self, action)()
            self.current_state = next_state
            for action in self.states[next_state].entry:
                getattr(self, action)()

    def send(self, event: str) -> None:
        self.transition(event)


class ChatMode:
    def __init__(
        self, config: Config, bedrock: bool, version_control: VersionControl
    ) -> None:
        self.config = config
        self.client: AIClient = create_ai_client(bedrock, config.anthropic_api_key)
        self.model: str = (
            "claude-3-5-sonnet-20240620"
            if not bedrock
            else "anthropic.claude-3-5-sonnet-20240620-v1:0"
        )
        self.messages: List[Dict[str, Any]] = []
        self.command_executor = CommandExecutor(version_control, lint_and_format_code)

    def _process_stream(self, stream: Generator[Any, None, None]) -> str:
        for event in stream:
            self._process_event(event)
        return self.assistant_message

    def _process_event(self, event: Any) -> None:
        if event.type == "content_block_start":
            if event.content_block.type == "text":
                self.send("START_TEXT")
            elif event.content_block.type == "tool_use":
                self.current_tool_use = event.content_block
                self.current_json_buffer = ""
                self.send("START_TOOL")
        elif event.type == "content_block_delta":
            if event.delta.type == "text_delta":
                self.send("TEXT_DELTA")
                self._accumulate_text(event.delta.text)
            elif event.delta.type == "input_json_delta":
                self.send("JSON_DELTA")
                self.current_json_buffer += event.delta.partial_json
        elif event.type == "content_block_stop":
            self.send("FINISH_BLOCK")
        elif event.type == "message_delta" and event.delta.stop_reason == "end_turn":
            self.send("END_TURN")
            self._finalize_message()
        elif event.type == "message_delta" and event.delta.stop_reason == "tool_use":
            self.send("FINISH_TOOL")

    def reset_state(self) -> None:
        self.assistant_message = ""
        self.current_tool_use = None
        self.current_json_buffer = ""

    def _accumulate_text(self, text: str) -> None:
        print(text, end="", flush=True)
        self.assistant_message += text

    def parse_tool_input(self) -> None:
        try:
            self.current_tool_use.input = json.loads(self.current_json_buffer)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse complete JSON: {self.current_json_buffer}")
            self.current_tool_use.input = {}

    def execute_tool(self) -> None:
        tool_result = self._execute_tool(self.current_tool_use)
        print(f"\nTool '{self.current_tool_use.name}' result: {tool_result}")
        self._append_tool_messages(tool_result)

    def _append_tool_messages(self, tool_result: str) -> None:
        self.messages.append(
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": self.assistant_message},
                    self.current_tool_use.to_dict(),
                ],
            }
        )
        self.messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": self.current_tool_use.id,
                        "content": tool_result,
                    }
                ],
            }
        )

    def reset_for_new_response(self) -> None:
        self.assistant_message = ""
        self.get_claude_response("")

    def _finalize_message(self) -> None:
        self.messages.append({"role": "assistant", "content": self.assistant_message})

    def execute_command(self, command: str, purpose: str) -> str:
        try:
            result = self.command_executor.execute_with_versioning(
                text=command, purpose=purpose
            )
            return result
        except Exception as e:
            return f"Error executing command: {str(e)}"

    def apply_diff(self, diff: str, target_path: str, purpose: str) -> str:
        try:
            result = self.command_executor.execute_with_versioning(
                text=diff, purpose=purpose, target_path=target_path, is_diff=True
            )
            return result
        except Exception as e:
            return f"Error applying diff: {str(e)}"

    def get_claude_response(self, user_input: str) -> str:
        if user_input:
            self.messages.append({"role": "user", "content": user_input})

        contextualized_system_prompt = self.generate_system_prompt()
        try:
            stream = self.client.stream_message(
                model=self.model,
                system=contextualized_system_prompt,
                max_tokens=8192,
                messages=self.messages,
                tools=tool_schemas,
            )

            return self._process_stream(stream)
        except Exception as e:
            raise Exception(f"Error communicating with Claude API: {str(e)}")

    def _process_stream(self, stream):
        try:
            return self._run_state_machine(stream)
        except Exception as e:
            logger.error(f"Error processing stream: {str(e)}", exc_info=True)
            raise Exception(f"Error processing Claude API response: {str(e)}")

    def _run_state_machine(self, stream):
        assistant_message = ""
        current_tool_use = None
        current_json_buffer = ""

        def idle_state():
            nonlocal assistant_message, current_tool_use, current_json_buffer
            while True:
                event = yield
                logger.debug(f"Idle state received event: {event}")
                if event.type == "content_block_start":
                    if event.content_block.type == "text":
                        yield "processing_text"
                    elif event.content_block.type == "tool_use":
                        current_tool_use = event.content_block
                        current_json_buffer = ""
                        logger.debug(f"Tool use started: {current_tool_use}")
                        yield "accumulating_json"
                elif (
                    event.type == "message_delta"
                    and event.delta.stop_reason == "end_turn"
                ):
                    self.messages.append(
                        {"role": "assistant", "content": assistant_message}
                    )
                    return assistant_message

        def processing_text_state():
            nonlocal assistant_message
            while True:
                event = yield
                logger.debug(f"Processing text state received event: {event}")
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    print(event.delta.text, end="", flush=True)
                    assistant_message += event.delta.text
                elif event.type == "content_block_stop":
                    yield "idle"

        def accumulating_json_state():
            nonlocal current_json_buffer
            while True:
                event = yield
                logger.debug(f"Accumulating JSON state received event: {event}")
                if (
                    event.type == "content_block_delta"
                    and event.delta.type == "input_json_delta"
                ):
                    current_json_buffer += event.delta.partial_json
                    logger.debug(f"Accumulated JSON: {current_json_buffer}")
                elif event.type == "content_block_stop":
                    try:
                        current_tool_use.input = json.loads(current_json_buffer)
                        logger.debug(f"Parsed tool input: {current_tool_use.input}")
                    except json.JSONDecodeError:
                        logger.error(
                            f"Failed to parse complete JSON: {current_json_buffer}"
                        )
                        current_tool_use.input = {}
                    yield "executing_tool"

        def executing_tool_state():
            nonlocal assistant_message, current_tool_use
            while True:
                event = yield
                logger.debug(f"Executing tool state received event: {event}")
                if (
                    event.type == "message_delta"
                    and event.delta.stop_reason == "tool_use"
                ):
                    logger.debug(f"Executing tool: {current_tool_use}")
                    tool_result = self._execute_tool(current_tool_use)
                    logger.debug(f"Tool result: {tool_result}")
                    print(f"\nTool '{current_tool_use.name}' result: {tool_result}")

                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": [
                                {"type": "text", "text": assistant_message},
                                current_tool_use.to_dict(),
                            ],
                        }
                    )

                    self.messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "tool_result",
                                    "tool_use_id": current_tool_use.id,
                                    "content": tool_result,
                                }
                            ],
                        }
                    )

                    assistant_message = ""  # Reset for potential new response
                    return self.get_claude_response("")

        states = {
            "idle": idle_state(),
            "processing_text": processing_text_state(),
            "accumulating_json": accumulating_json_state(),
            "executing_tool": executing_tool_state(),
        }

        current_state = "idle"
        states[current_state].send(None)  # Prime the initial state

        for event in stream:
            logger.debug(f"Current state: {current_state}, Received event: {event}")
            try:
                next_state = states[current_state].send(event)
                if next_state:
                    logger.debug(f"Transitioning from {current_state} to {next_state}")
                    current_state = next_state
                    states[current_state].send(None)  # Prime the next state
            except StopIteration as e:
                # If a state returns, it's the final result
                return e.value

    def _execute_tool(self, tool_use):
        tool_name = tool_use.name
        tool_input = tool_use.input

        if tool_name == "execute_command":
            return self.execute_command(
                command=tool_input["command"], purpose=tool_input["purpose"]
            )
        elif tool_name == "apply_diff":
            return self.apply_diff(
                tool_input["diff"], tool_input["target_path"], tool_input["purpose"]
            )
        else:
            return f"Unknown tool: {tool_name}"

    def generate_system_prompt(self):
        directory_tree = generate_tree(".", ignore_dotfiles=True, use_gitignore=True)
        tools_description = self._generate_tools_description()

        return f"""<environment_info>
        {self.config.environment_info}
        SHELL={self.config.shell_info}
        CWD={self.config.cwd}
        </environment_info>

        <cwd_tree>
        {directory_tree}
        </cwd_tree>

        <available_tools>
        {tools_description}
        </available_tools>

        {self.config.system_prompt}"""

    def start(self):
        print(
            "Entering interactive mode with Claude Sonnet. Type 'exit' to end the session."
        )

        while True:
            try:
                user_input = input("\nUser: ").strip()

                if user_input.lower() == "exit":
                    print("Exiting interactive mode. Goodbye!")
                    break

                print("Contextual: ", end="")
                self.get_claude_response(user_input)
            except KeyboardInterrupt:
                print("\nKeyboard interrupt detected. Exiting interactive mode.")
                break
            except Exception as e:
                print(f"An error occurred: {str(e)}")

    def _generate_tools_description(self):
        return "\n".join(
            [
                f"- {tool['name']}: {tool['description']}\n  Input: {json.dumps(tool['input_schema'], indent=2)}"
                for tool in tool_schemas
            ]
        )
