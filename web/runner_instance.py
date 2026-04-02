"""Singleton PipelineRunner shared across web modules."""

from __future__ import annotations

from core.runner import PipelineRunner

_runner: PipelineRunner | None = None


def get_runner() -> PipelineRunner:
    global _runner
    if _runner is None:
        _runner = PipelineRunner()
    return _runner
