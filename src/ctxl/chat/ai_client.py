import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Iterator, List, Optional

from anthropic import Anthropic, AnthropicBedrock


class AIClient(ABC):
    @abstractmethod
    def send_message(
        self,
        system: str,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = [],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        pass

    @abstractmethod
    def stream_message(
        self,
        system: str,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Any]:
        pass


class AnthropicClient(AIClient):
    def __init__(self, api_key: str):
        self.client = Anthropic(api_key=api_key)
        self.logger = logging.getLogger(__name__)

    def send_message(
        self,
        system: str,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        try:
            response = self.client.messages.create(
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                stop_sequences=stop_sequences,
                tools=tools,
                extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            )
            return response
        except Exception as e:
            self.logger.error(f"Error in send_message: {str(e)}")
            raise

    def stream_message(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        model: str,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Any]:
        try:
            with self.client.messages.stream(
                system=system,
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                tools=tools,
                extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            ) as stream:
                for event in stream:
                    yield event
        except Exception as e:
            self.logger.error(f"Error in stream_message: {str(e)}")
            raise


class AnthropicBedrockClient(AIClient):
    def __init__(self):
        self.client = AnthropicBedrock()
        self.logger = logging.getLogger(__name__)

    def send_message(
        self,
        system: str,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: Optional[int] = None,
        stop_sequences: Optional[List[str]] = [],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Any:
        try:
            response = self.client.messages.create(
                model=model,
                system=system,
                messages=messages,
                max_tokens=max_tokens,
                stop_sequences=stop_sequences,
                tools=tools,
                extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            )
            return response
        except Exception as e:
            self.logger.error(f"Error in send_message: {str(e)}")
            raise

    def stream_message(
        self,
        system: str,
        messages: List[Dict[str, Any]],
        model: str,
        max_tokens: Optional[int] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Iterator[Any]:
        try:
            with self.client.messages.stream(
                system=system,
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                tools=tools,
                extra_headers={"anthropic-beta": "max-tokens-3-5-sonnet-2024-07-15"},
            ) as stream:
                for event in stream:
                    yield event
        except Exception as e:
            self.logger.error(f"Error in stream_message: {str(e)}")
            raise


def create_ai_client(bedrock: bool, api_key: Optional[str] = None) -> AIClient:
    try:
        if bedrock:
            return AnthropicBedrockClient()
        else:
            if not api_key:
                raise ValueError("ANTHROPIC_API_KEY not found in environment variables")
            return AnthropicClient(api_key)
    except Exception as e:
        logging.error(f"Error creating AI client: {str(e)}")
        raise
