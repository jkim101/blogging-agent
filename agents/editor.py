"""Editor agent.

Polishes tone, format, and style per style_guide.yaml.
Runs separately for Korean and English drafts.
Model: Claude Sonnet 4.5.
See 설계서 §3.6.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from config.settings import STYLE_GUIDE_PATH
from core.state import BlogConfig
from prompts.editor import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class EditorAgent(BaseAgent):
    agent_name = "editor"

    def __init__(self) -> None:
        super().__init__()
        with open(STYLE_GUIDE_PATH) as f:
            self._style_guide_raw = f.read()

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Edit both Korean and English drafts for style consistency."""
        system_prompt = SYSTEM_PROMPT.format(style_guide=self._style_guide_raw)
        config = state.get("blog_config") or BlogConfig()

        results: dict[str, Any] = {"current_step": "editor"}

        # Edit Korean draft (skip for en-only)
        draft_ko = state.get("draft_ko", "")
        if draft_ko and config.output_language != "en-only":
            msg_ko = self.call_llm(
                system_prompt=system_prompt,
                user_message=f"## Draft to Edit (Korean)\n\n{draft_ko}",
                max_tokens=4000,
            )
            results["edited_draft_ko"] = self.get_text_response(msg_ko)

        # Edit English draft
        draft_en = state.get("draft_en", "")
        if draft_en:
            msg_en = self.call_llm(
                system_prompt=system_prompt,
                user_message=f"## Draft to Edit (English)\n\n{draft_en}",
                max_tokens=4000,
            )
            results["edited_draft_en"] = self.get_text_response(msg_en)

        return results
