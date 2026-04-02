"""Summarizer agent.

Takes parsed source content and produces a structured summary.
Single LLM call — no pipeline needed.
Model: Claude Sonnet 4.5.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import ToolConfig
from prompts.summarizer import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class SummarizerAgent(BaseAgent):
    agent_name = "summarizer"

    def run(self, sources: list[Any], config: ToolConfig) -> dict[str, str]:
        """Summarize the provided sources and return the summary text."""
        combined = "\n\n---\n\n".join(
            f"**Source:** {s.title or s.origin}\n\n{s.content[:4000]}"
            for s in sources
        )
        config_section = config.format_as_prompt_section()
        system_prompt = SYSTEM_PROMPT.format(config_section=config_section)
        user_message = f"Please summarize the following sources:\n\n{combined}"

        message = self.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=2000,
        )
        summary = self.get_text_response(message)
        title = sources[0].title if sources else "Summary"
        return {"summary": summary, "title": title}
