import json
import logging
import os
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)


class ChatSession:
    def __init__(self, chat_dir: Optional[str] = None):
        self.conversation_history: List[Dict[str, str]] = []
        self.system_prompt: str = ""
        self.chat_dir: str = chat_dir or os.path.join(os.getcwd(), ".ctxl_chats")
        self.loaded_chat_path: Optional[str] = None
        self._initialize_chat_directory()
        self._load_system_prompt()

    def _initialize_chat_directory(self) -> None:
        """Initialize the chat directory."""
        try:
            os.makedirs(self.chat_dir, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create chat directory: {e}")
            raise

    def add_message(self, role: str, content: str) -> None:
        """Add a message to the conversation history."""
        self.conversation_history.append({"role": role, "content": content})

    def get_messages(self) -> List[Dict[str, str]]:
        """Get all messages in the conversation history."""
        return self.conversation_history

    def clear_messages(self) -> None:
        """Clear all messages from the conversation history."""
        self.conversation_history = []
        logger.info("Conversation history cleared.")

    def get_system_prompt(self) -> str:
        """Get the current system prompt."""
        return self.system_prompt

    def _load_system_prompt(self) -> None:
        """Load the system prompt from a file."""
        try:
            with open("system_prompt.txt", "r") as f:
                self.system_prompt = f.read().strip()
            logger.info("System prompt loaded successfully.")
        except FileNotFoundError:
            logger.warning("System prompt file not found. Using default prompt.")
            self.system_prompt = "You are a helpful AI assistant."

    def save_chat(self) -> None:
        """Save the current chat session."""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"chat_{timestamp}.json"
            filepath = (
                os.path.join(self.chat_dir, filename)
                if not self.loaded_chat_path
                else self.loaded_chat_path
            )
            self.loaded_chat_path = filepath
            with open(filepath, "w") as f:
                json.dump(
                    {
                        "system_prompt": self.system_prompt,
                        "history": self.conversation_history,
                    },
                    f,
                )
            logger.info(f"Chat saved to {filepath}")
        except IOError as e:
            logger.error(f"Failed to save chat: {e}")
            raise

    def load_latest_chat(self) -> bool:
        """Load the most recent chat session."""
        chat_files = self._get_sorted_chat_files()
        if not chat_files:
            logger.info("No previous chats found.")
            return False

        return self._load_chat(chat_files[0])

    def _load_chat(self, chat_file: str) -> bool:
        """Load a specific chat file."""
        filepath = os.path.join(self.chat_dir, chat_file)
        self.loaded_chat_path = filepath
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            self.system_prompt = data.get("system_prompt", self.system_prompt)
            self.conversation_history = data.get("history", [])
            logger.info(f"Loaded chat from {filepath}")
            return True
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to load chat from {filepath}: {e}")
            return False

    def list_chats(self) -> None:
        """List all available chat sessions."""
        chat_files = self._get_sorted_chat_files()
        if not chat_files:
            logger.info("No saved chats found.")
        else:
            logger.info("Available chats:")
            for i, chat in enumerate(chat_files, 1):
                logger.info(f"{i}. {chat}")

    def switch_chat(self, chat_number: int) -> bool:
        """Switch to a specific chat session."""
        chat_files = self._get_sorted_chat_files()
        if 1 <= chat_number <= len(chat_files):
            return self._load_chat(chat_files[chat_number - 1])
        else:
            logger.warning("Invalid chat number. Use 'list' to see available chats.")
            return False

    def _get_sorted_chat_files(self) -> List[str]:
        """Get a sorted list of chat files."""
        try:
            return sorted(os.listdir(self.chat_dir), reverse=True)
        except OSError as e:
            logger.error(f"Failed to list chat directory: {e}")
            return []

    def get_chat_summary(self) -> str:
        """Get a summary of the current chat session."""
        return f"""<chat_summary>
        Messages: {len(self.conversation_history)}
        System Prompt: {self.system_prompt[:50]}...
        Loaded Chat: {self.loaded_chat_path or "None"}
        </chat_summary>"""
