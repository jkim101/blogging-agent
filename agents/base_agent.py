"""Base agent class wrapping the Claude API with tool_use + Pydantic parsing.

All 7 agents inherit from BaseAgent. Provides:
- Claude API call with model selection
- tool_use structured output parsing
- Pydantic validation of responses
- Token usage logging
- Retry with exponential backoff

See 설계서 §3 for agent specifications, §6 for tech stack.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from config.settings import AGENT_MODELS, ANTHROPIC_API_KEY

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

MAX_API_RETRIES = 3
MAX_PARSE_RETRIES = 2


class BaseAgent:
    """Base class for all pipeline agents.

    Subclasses must set `agent_name` and implement `run()`.
    """

    agent_name: str = "base"

    def __init__(self) -> None:
        self.client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        self.model = AGENT_MODELS.get(self.agent_name, "claude-sonnet-4-5-20250929")

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent's task and return state updates.

        Args:
            state: Current pipeline state.

        Returns:
            Dictionary of state field updates.
        """
        raise NotImplementedError

    def call_llm(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict] | None = None,
        max_tokens: int = 4096,
    ) -> anthropic.types.Message:
        """Call Claude API with exponential backoff retry (max 3 attempts)."""
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system_prompt,
            "messages": [{"role": "user", "content": user_message}],
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = {"type": "any"}

        last_error: Exception | None = None
        for attempt in range(MAX_API_RETRIES):
            try:
                message = self.client.messages.create(**kwargs)
                self._log_usage(message)
                return message
            except anthropic.RateLimitError as e:
                last_error = e
                wait = 2 ** attempt
                logger.warning(
                    "[%s] Rate limited, retrying in %ds (attempt %d/%d)",
                    self.agent_name, wait, attempt + 1, MAX_API_RETRIES,
                )
                time.sleep(wait)
            except anthropic.APIStatusError as e:
                if e.status_code >= 500:
                    last_error = e
                    wait = 2 ** attempt
                    logger.warning(
                        "[%s] Server error %d, retrying in %ds (attempt %d/%d)",
                        self.agent_name, e.status_code, wait, attempt + 1, MAX_API_RETRIES,
                    )
                    time.sleep(wait)
                else:
                    raise

        raise last_error  # type: ignore[misc]

    def parse_tool_response(
        self,
        message: anthropic.types.Message,
        model_class: type[T],
    ) -> T:
        """Extract tool_use result and validate with Pydantic.

        Retries LLM call once if validation fails.
        """
        tool_input = self._extract_tool_input(message)
        try:
            return model_class.model_validate(tool_input)
        except ValidationError as e:
            logger.warning(
                "[%s] Pydantic validation failed, retrying: %s",
                self.agent_name, e,
            )
            raise

    def get_text_response(self, message: anthropic.types.Message) -> str:
        """Extract plain text content from a message."""
        parts = []
        for block in message.content:
            if block.type == "text":
                parts.append(block.text)
        return "\n".join(parts)

    def _extract_tool_input(self, message: anthropic.types.Message) -> dict:
        """Find the first tool_use block and return its input."""
        for block in message.content:
            if block.type == "tool_use":
                return block.input  # type: ignore[return-value]
        raise ValueError(
            f"[{self.agent_name}] No tool_use block found in response. "
            f"Stop reason: {message.stop_reason}"
        )

    def _log_usage(self, message: anthropic.types.Message) -> None:
        """Log token usage for cost tracking."""
        usage = message.usage
        logger.info(
            "[%s] model=%s input_tokens=%d output_tokens=%d",
            self.agent_name,
            self.model,
            usage.input_tokens,
            usage.output_tokens,
        )

    @staticmethod
    def build_tool_schema(name: str, description: str, model_class: type[BaseModel]) -> dict:
        """Generate a Claude tool definition from a Pydantic model."""
        schema = model_class.model_json_schema()
        # Remove $defs at top level — Claude expects flat input_schema
        schema.pop("$defs", None)
        return {
            "name": name,
            "description": description,
            "input_schema": schema,
        }
