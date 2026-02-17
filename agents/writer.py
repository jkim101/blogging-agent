"""Writer agent.

Generates Korean blog post draft from approved outline.
Handles rewrites incorporating Critic feedback and Fact Check issues.
Model: Claude Sonnet 4.5.
See 설계서 §3.2.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from prompts.writer import REWRITE_PROMPT, SYSTEM_PROMPT

logger = logging.getLogger(__name__)


class WriterAgent(BaseAgent):
    agent_name = "writer"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Write or rewrite Korean draft based on outline and feedback."""
        outline = state["outline"]
        research_summary = state.get("research_summary", "")
        rewrite_count = state.get("rewrite_count", 0)
        critic_feedback = state.get("critic_feedback")
        fact_check = state.get("fact_check")
        human_notes = state.get("outline_human_notes", "")

        if rewrite_count > 0 and critic_feedback:
            # Rewrite mode
            system_prompt = REWRITE_PROMPT.format(
                weaknesses="\n".join(critic_feedback.weaknesses),
                rewrite_instructions=critic_feedback.rewrite_instructions,
                fact_issues="\n".join(
                    f"[{issue.severity.value}] {issue.claim}: {issue.issue}"
                    for issue in (fact_check.issues_found if fact_check else [])
                ),
                strengths="\n".join(critic_feedback.strengths),
            )
            user_message = (
                f"## Previous Draft\n\n{state['draft_ko']}\n\n"
                f"## Outline\n\n{self._format_outline(outline)}"
            )
        else:
            # Initial write
            system_prompt = SYSTEM_PROMPT
            user_message = (
                f"## Research Summary\n\n{research_summary}\n\n"
                f"## Outline\n\n{self._format_outline(outline)}"
            )
            if human_notes:
                user_message += f"\n\n## Human Notes\n\n{human_notes}"

        message = self.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=8192,
        )

        draft_ko = self.get_text_response(message)

        return {
            "draft_ko": draft_ko,
            "rewrite_count": rewrite_count + 1 if rewrite_count > 0 else 0,
            "current_step": "writer",
        }

    @staticmethod
    def _format_outline(outline) -> str:
        """Format Outline object as readable text for the prompt."""
        lines = [
            f"Topic: {outline.topic}",
            f"Angle: {outline.angle}",
            f"Target Audience: {outline.target_audience}",
            f"Estimated Word Count: {outline.estimated_word_count}",
            "",
            "Key Points:",
        ]
        for point in outline.key_points:
            lines.append(f"- {point}")
        lines.append("")
        lines.append("Structure:")
        for section in outline.structure:
            lines.append(f"\n## {section.heading}")
            for kp in section.key_points:
                lines.append(f"  - {kp}")
        return "\n".join(lines)
