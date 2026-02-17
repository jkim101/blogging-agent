"""Fact Checker agent.

Verifies factual accuracy of the Korean draft against source materials.
Runs only on Korean draft; results shared with English version.
Model: Claude Sonnet 4.5.
See 설계서 §3.3.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import FactCheckDiff, FactCheckResult
from prompts.fact_checker import SYSTEM_PROMPT, TOOLS

logger = logging.getLogger(__name__)


class FactCheckerAgent(BaseAgent):
    agent_name = "fact_checker"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Verify claims in draft_ko against sources."""
        draft_ko = state["draft_ko"]
        sources = state["sources"]
        previous_fact_check = state.get("fact_check")

        # Build source reference text
        source_refs = []
        for i, src in enumerate(sources, 1):
            source_refs.append(
                f"--- Source {i}: {src.title or src.origin} ---\n{src.content}"
            )

        user_message = (
            f"## Korean Draft to Verify\n\n{draft_ko}\n\n"
            f"## Source Materials\n\n" + "\n\n".join(source_refs)
        )

        message = self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tools=TOOLS,
            max_tokens=4096,
        )

        fact_check = self.parse_tool_response(message, FactCheckResult)

        result: dict[str, Any] = {
            "fact_check": fact_check,
            "current_step": "fact_checker",
        }

        # Build diff if this is a rewrite round
        if previous_fact_check:
            result["fact_check_diff"] = self._compute_diff(
                previous_fact_check, fact_check
            )

        return result

    @staticmethod
    def _compute_diff(
        previous: FactCheckResult, current: FactCheckResult
    ) -> FactCheckDiff:
        """Compare previous and current issues to track resolved/new/remaining."""
        prev_claims = {issue.claim for issue in previous.issues_found}
        curr_claims = {issue.claim for issue in current.issues_found}

        return FactCheckDiff(
            resolved=sorted(prev_claims - curr_claims),
            new=sorted(curr_claims - prev_claims),
            remaining=sorted(prev_claims & curr_claims),
        )
