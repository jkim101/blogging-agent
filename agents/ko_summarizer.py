"""Korean Summarizer agent.

Produces a concise Korean digest from the finalized English blog post.
Not a full translation — a native Korean summary (~500 words).
Model: Claude Sonnet 4.5.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import BlogConfig
from prompts.ko_summarizer import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class KoSummarizerAgent(BaseAgent):
    agent_name = "ko_summarizer"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Summarize the English post into a Korean digest."""
        draft_en = state.get("edited_draft_en") or state.get("draft_en", "")
        config = state.get("blog_config") or BlogConfig()

        word_count = max(400, config.word_count // 3)

        system_prompt = SYSTEM_PROMPT.format(word_count=word_count)
        user_message = f"## English Blog Post\n\n{draft_en}"

        message = self.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=2000,
        )

        draft_ko = self.get_text_response(message)

        return {
            "draft_ko": draft_ko,
            "current_step": "ko_summarizer",
        }
