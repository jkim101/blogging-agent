"""Shared test fixtures for the blogging agent test suite."""

import pytest
from unittest.mock import MagicMock

import anthropic

from core.state import (
    CriticFeedback,
    FactCheckIssue,
    FactCheckResult,
    Outline,
    OutlineSection,
    PipelineState,
    Severity,
    SourceContent,
    SourceType,
    Verdict,
)


@pytest.fixture
def sample_source() -> SourceContent:
    return SourceContent(
        source_type=SourceType.URL,
        origin="https://example.com/article",
        title="Sample Article",
        content="This is sample article content for testing. AI agents use multi-step pipelines.",
    )


@pytest.fixture
def sample_outline() -> Outline:
    return Outline(
        topic="AI Agent Design Patterns",
        angle="Practical lessons from building multi-agent systems",
        target_audience="Software engineers interested in AI",
        key_points=["Agent separation", "State management", "Human oversight"],
        structure=[
            OutlineSection(heading="Introduction", key_points=["Hook", "Thesis"]),
            OutlineSection(heading="Core Patterns", key_points=["Pattern 1", "Pattern 2"]),
            OutlineSection(heading="Conclusion", key_points=["Summary", "Call to action"]),
        ],
        estimated_word_count=2000,
    )


@pytest.fixture
def sample_fact_check() -> FactCheckResult:
    return FactCheckResult(
        claims_checked=5,
        issues_found=[],
        overall_accuracy=0.95,
        suggestions=["Consider adding source citations"],
    )


@pytest.fixture
def sample_fact_check_with_issues() -> FactCheckResult:
    return FactCheckResult(
        claims_checked=5,
        issues_found=[
            FactCheckIssue(
                claim="AI agents are 100% accurate",
                issue="Overstated accuracy claim",
                severity=Severity.HIGH,
                suggestion="Qualify the accuracy claim",
            ),
        ],
        overall_accuracy=0.7,
        suggestions=[],
    )


@pytest.fixture
def sample_critic_pass() -> CriticFeedback:
    return CriticFeedback(
        verdict=Verdict.PASS,
        score=8,
        strengths=["Clear structure", "Good examples"],
        weaknesses=["Minor transition issues"],
        specific_feedback="Well written overall.",
        rewrite_instructions="",
    )


@pytest.fixture
def sample_critic_fail() -> CriticFeedback:
    return CriticFeedback(
        verdict=Verdict.FAIL,
        score=5,
        strengths=["Good topic choice"],
        weaknesses=["Shallow analysis", "Missing examples"],
        specific_feedback="Needs significant improvement.",
        rewrite_instructions="Add concrete examples and deepen the analysis.",
    )


@pytest.fixture
def sample_state(sample_source, sample_outline) -> dict:
    return {
        "sources": [sample_source],
        "outline": sample_outline,
        "research_summary": "AI agents use multi-step pipelines for complex tasks.",
        "rewrite_count": 0,
        "current_step": "writer",
    }


def make_mock_message(content_blocks: list, usage=None) -> MagicMock:
    """Create a mock anthropic.types.Message."""
    msg = MagicMock(spec=anthropic.types.Message)
    msg.content = content_blocks
    msg.stop_reason = "end_turn"
    if usage is None:
        usage = MagicMock()
        usage.input_tokens = 100
        usage.output_tokens = 200
    msg.usage = usage
    return msg


def make_text_block(text: str) -> MagicMock:
    """Create a mock TextBlock."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    return block


def make_tool_use_block(name: str, input_data: dict) -> MagicMock:
    """Create a mock ToolUseBlock."""
    block = MagicMock()
    block.type = "tool_use"
    block.name = name
    block.input = input_data
    return block
