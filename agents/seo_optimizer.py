"""SEO Optimizer agent.

Optimizes title, meta description, headings, and keyword density.
Must NOT rewrite body text — only metadata and heading adjustments.
Runs separately for Korean and English.
Model: Claude Sonnet 4.5.
See 설계서 §3.7.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import BlogConfig, SEOMetadata
from prompts.seo_optimizer import SYSTEM_PROMPT, TOOLS

logger = logging.getLogger(__name__)


class SEOOptimizerAgent(BaseAgent):
    agent_name = "seo_optimizer"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Optimize SEO metadata and produce final posts."""
        outline = state["outline"]
        config = state.get("blog_config") or BlogConfig()
        results: dict[str, Any] = {"current_step": "seo_optimizer"}

        # Optimize Korean
        edited_ko = state.get("edited_draft_ko", "")
        if edited_ko:
            seo_ko, final_ko = self._optimize(edited_ko, outline, config, language="ko")
            results["seo_metadata_ko"] = seo_ko
            results["final_post_ko"] = final_ko

        # Optimize English
        edited_en = state.get("edited_draft_en", "")
        if edited_en:
            seo_en, final_en = self._optimize(edited_en, outline, config, language="en")
            results["seo_metadata_en"] = seo_en
            results["final_post_en"] = final_en

        return results

    def _optimize(
        self, draft: str, outline, config: BlogConfig, language: str
    ) -> tuple[SEOMetadata, str]:
        """Run SEO optimization for a single language version."""
        config_section = config.format_as_prompt_section()
        if config.primary_keyword:
            config_section += f"\n- Preferred primary keyword: {config.primary_keyword}"
        if config.categories:
            config_section += f"\n- Suggested categories: {', '.join(config.categories)}"

        system_prompt = SYSTEM_PROMPT.format(language=language, config_section=config_section)
        user_message = (
            f"## Blog Post ({language.upper()})\n\n{draft}\n\n"
            f"## Topic Info\n\nTopic: {outline.topic}\n"
            f"Angle: {outline.angle}\n"
            f"Target Audience: {outline.target_audience}"
        )

        message = self.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=TOOLS,
            max_tokens=1500,
        )

        seo_metadata = self.parse_tool_response(
            message, SEOMetadata,
            _system_prompt=system_prompt, _user_message=user_message, _tools=TOOLS,
        )

        # Get the final post text (output after tool_use)
        final_post = self.get_text_response(message)
        if not final_post:
            final_post = draft

        return seo_metadata, final_post
