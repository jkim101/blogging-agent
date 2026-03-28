"""LinkedIn Post agent.

Generates Korean and English LinkedIn posts from the finalized blog post.
Model: Claude Sonnet 4.5.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from prompts.linkedin import SYSTEM_PROMPT, TOOLS, LinkedInPosts

logger = logging.getLogger(__name__)


class LinkedInAgent(BaseAgent):
    agent_name = "linkedin"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Generate LinkedIn posts in Korean and English."""
        post_en = state.get("final_post_en") or state.get("edited_draft_en", "")
        seo_en = state.get("seo_metadata_en")
        outline = state.get("outline")

        title = seo_en.optimized_title if seo_en else (outline.topic if outline else "")
        angle = outline.angle if outline else ""
        keywords = []
        if seo_en:
            if seo_en.primary_keyword:
                keywords.append(seo_en.primary_keyword)
            keywords.extend(seo_en.secondary_keywords[:4])

        user_message = (
            f"## Blog Post Title\n{title}\n\n"
            f"## Angle\n{angle}\n\n"
            f"## Keywords\n{', '.join(keywords)}\n\n"
            f"## Full English Post\n\n{post_en}"
        )

        message = self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tools=TOOLS,
            max_tokens=1500,
        )

        posts = self.parse_tool_response(
            message, LinkedInPosts,
            _system_prompt=SYSTEM_PROMPT, _user_message=user_message, _tools=TOOLS,
        )

        return {
            "linkedin_post_ko": posts.ko,
            "linkedin_post_en": posts.en,
            "current_step": "linkedin",
        }
