"""Research Planner agent.

Analyzes source content, extracts key insights, and generates a blog outline.
Model: Claude Opus 4.6 (complex reasoning + multi-source analysis).
See 설계서 §3.1.
"""

from __future__ import annotations

import logging
from typing import Any

from agents.base_agent import BaseAgent
from core.state import Outline
from prompts.research_planner import SYSTEM_PROMPT, TOOLS

logger = logging.getLogger(__name__)


class ResearchPlannerAgent(BaseAgent):
    agent_name = "research_planner"

    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Analyze sources and produce research_summary + outline."""
        sources = state["sources"]

        # Build user message with all source content
        source_texts = []
        for i, src in enumerate(sources, 1):
            source_texts.append(
                f"--- Source {i}: {src.title or src.origin} ---\n"
                f"Type: {src.source_type.value}\n"
                f"Origin: {src.origin}\n\n"
                f"{src.content}"
            )
        user_message = "\n\n".join(source_texts)

        message = self.call_llm(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tools=TOOLS,
            max_tokens=4096,
        )

        outline = self.parse_tool_response(message, Outline)

        # Extract research summary from text blocks (LLM may include analysis before tool call)
        research_summary = self.get_text_response(message)
        if not research_summary:
            research_summary = f"Research analysis for: {outline.topic}"

        return {
            "research_summary": research_summary,
            "outline": outline,
            "current_step": "research_planner",
        }
