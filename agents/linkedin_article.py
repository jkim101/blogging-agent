"""LinkedIn Article agent.

Generates a long-form LinkedIn article from source content.
Single LLM call — no pipeline needed.
Model: Claude Sonnet 4.5.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import ToolConfig
from prompts.linkedin_article import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class LinkedInArticleAgent(BaseAgent):
    agent_name = "linkedin_article"

    def run(self, sources: list[Any], config: ToolConfig) -> dict[str, str]:
        """Write a LinkedIn article from the provided sources."""
        combined = "\n\n---\n\n".join(
            f"**Source:** {s.title or s.origin}\n\n{s.content[:4000]}"
            for s in sources
        )
        config_section = config.format_as_prompt_section()
        system_prompt = SYSTEM_PROMPT.format(config_section=config_section)
        user_message = f"Write a LinkedIn article based on the following sources:\n\n{combined}"

        message = self.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=2500,
        )
        article = self.get_text_response(message)
        title = sources[0].title if sources else "LinkedIn Article"
        return {"article": article, "title": title}
