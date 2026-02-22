"""Critic agent.

Evaluates Korean draft quality on logic, structure, and depth.
Issues pass/fail verdict. On fail, triggers Writer rewrite loop.
Model: Claude Opus 4.6 (strict, consistent quality evaluation).
See 설계서 §3.4.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import CriticFeedback
from prompts.critic import SYSTEM_PROMPT, SYSTEM_PROMPT_LENIENT, TOOLS

logger = logging.getLogger(__name__)


class CriticAgent(BaseAgent):
    agent_name = "critic"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Evaluate draft_ko and return CriticFeedback with verdict."""
        draft_ko = state["draft_ko"]
        outline = state["outline"]
        fact_check = state["fact_check"]
        rewrite_count = state.get("rewrite_count", 0)
        fact_check_diff = state.get("fact_check_diff")

        # Build system prompt with rewrite context
        system_prompt = SYSTEM_PROMPT.format(rewrite_count=rewrite_count)
        if rewrite_count >= 3:
            system_prompt += SYSTEM_PROMPT_LENIENT

        # Build user message
        fact_summary = (
            f"Claims checked: {fact_check.claims_checked}\n"
            f"Overall accuracy: {fact_check.overall_accuracy}\n"
            f"Issues ({len(fact_check.issues_found)}):\n"
        )
        for issue in fact_check.issues_found:
            fact_summary += (
                f"  [{issue.severity.value}] {issue.claim}: {issue.issue}\n"
            )

        user_message = (
            f"## Korean Draft\n\n{draft_ko}\n\n"
            f"## Outline\n\nTopic: {outline.topic}\nAngle: {outline.angle}\n\n"
            f"## Fact Check Results\n\n{fact_summary}"
        )

        if fact_check_diff:
            user_message += (
                f"\n## Fact Check Diff (vs previous round)\n"
                f"Resolved: {', '.join(fact_check_diff.resolved) or 'none'}\n"
                f"New: {', '.join(fact_check_diff.new) or 'none'}\n"
                f"Remaining: {', '.join(fact_check_diff.remaining) or 'none'}\n"
            )

        message = self.call_llm(
            system_prompt=system_prompt,
            user_message=user_message,
            tools=TOOLS,
            max_tokens=4096,
        )

        feedback = self.parse_tool_response(
            message, CriticFeedback,
            _system_prompt=system_prompt, _user_message=user_message, _tools=TOOLS,
        )

        return {
            "critic_feedback": feedback,
            "current_step": "critic",
        }
