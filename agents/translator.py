"""Translator agent.

Converts the finalized Korean draft into a natural English blog post.
Not a literal translation — adapts for English-speaking audience.
Model: Claude Sonnet 4.5.
See 설계서 §3.5.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from prompts.translator import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class TranslatorAgent(BaseAgent):
    agent_name = "translator"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Convert draft_ko to draft_en."""
        draft_ko = state["draft_ko"]

        message = self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=f"## Korean Blog Post\n\n{draft_ko}",
            max_tokens=4000,
        )

        draft_en = self.get_text_response(message)

        return {
            "draft_en": draft_en,
            "current_step": "translator",
        }
