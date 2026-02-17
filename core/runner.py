"""Pipeline execution manager.

Handles pipeline lifecycle: start, resume from checkpoint, error recovery.
See 설계서 §9 for error handling, §5.3 for checkpoint mechanism.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from core.graph import build_graph
from core.state import HumanDecision, PipelineState, SourceContent

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Manages pipeline execution with error handling and checkpointing."""

    def __init__(self) -> None:
        self.graph = build_graph()

    def start(self, sources: list[SourceContent]) -> str:
        """Start a new pipeline run.

        Returns:
            Pipeline run ID (thread_id).
        """
        thread_id = uuid.uuid4().hex[:12]
        config = {"configurable": {"thread_id": thread_id}}

        initial_state: dict[str, Any] = {
            "sources": sources,
            "rewrite_count": 0,
            "current_step": "started",
        }

        logger.info("Starting pipeline run: %s", thread_id)

        # Run until first HITL interrupt (outline_review)
        for event in self.graph.stream(initial_state, config=config):
            self._log_event(event)

        return thread_id

    def resume(self, thread_id: str, human_input: dict[str, Any]) -> None:
        """Resume a paused pipeline with human input.

        Args:
            thread_id: Pipeline run ID.
            human_input: Decision and notes from HITL checkpoint.
                e.g. {"outline_decision": "approve", "outline_human_notes": "..."}
                or   {"publish_decision": "approve", "publish_targets": [...]}
        """
        config = {"configurable": {"thread_id": thread_id}}

        # Inject human input into the state
        self.graph.update_state(config, human_input)

        logger.info("Resuming pipeline %s with input: %s", thread_id, list(human_input.keys()))

        # Continue execution until next interrupt or completion
        for event in self.graph.stream(None, config=config):
            self._log_event(event)

    def get_status(self, thread_id: str) -> dict[str, Any]:
        """Get current pipeline status.

        Returns:
            Dict with current_step, is_interrupted, and state snapshot.
        """
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = self.graph.get_state(config)

        state = snapshot.values
        next_nodes = snapshot.next

        return {
            "thread_id": thread_id,
            "current_step": state.get("current_step", "unknown"),
            "is_interrupted": len(next_nodes) > 0,
            "next_node": next_nodes[0] if next_nodes else None,
            "rewrite_count": state.get("rewrite_count", 0),
            "has_outline": state.get("outline") is not None,
            "has_draft_ko": bool(state.get("draft_ko")),
            "has_draft_en": bool(state.get("draft_en")),
            "has_final_ko": bool(state.get("final_post_ko")),
            "has_final_en": bool(state.get("final_post_en")),
            "critic_score": (
                state["critic_feedback"].score
                if state.get("critic_feedback")
                else None
            ),
        }

    def get_state(self, thread_id: str) -> PipelineState:
        """Get the full pipeline state for a given run."""
        config = {"configurable": {"thread_id": thread_id}}
        snapshot = self.graph.get_state(config)
        return snapshot.values

    @staticmethod
    def _log_event(event: dict) -> None:
        """Log graph stream events."""
        for node_name, output in event.items():
            step = output.get("current_step", node_name) if isinstance(output, dict) else node_name
            logger.info("Completed node: %s", step)
