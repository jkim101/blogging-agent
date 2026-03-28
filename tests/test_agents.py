"""Agent unit tests with mock LLM responses.

Tests each agent's run() method with mocked Claude API calls.
See 설계서 §13.2.
"""

from unittest.mock import patch

from core.state import (
    CriticFeedback,
    FactCheckResult,
    Outline,
    SEOMetadata,
    Verdict,
)
from tests.conftest import make_mock_message, make_text_block, make_tool_use_block


@patch("agents.base_agent.BaseAgent.call_llm")
def test_research_planner_produces_outline(mock_call, sample_source):
    """Research Planner should produce research_summary and outline."""
    from agents.research_planner import ResearchPlannerAgent

    mock_call.return_value = make_mock_message([
        make_text_block("Research analysis of AI agent patterns."),
        make_tool_use_block("create_outline", {
            "topic": "AI Agents",
            "angle": "Practical design patterns",
            "target_audience": "Engineers",
            "key_points": ["Separation of concerns"],
            "structure": [{"heading": "Intro", "key_points": ["Hook"]}],
            "estimated_word_count": 1500,
        }),
    ])

    agent = ResearchPlannerAgent()
    result = agent.run({"sources": [sample_source]})

    assert "outline" in result
    assert isinstance(result["outline"], Outline)
    assert result["outline"].topic == "AI Agents"
    assert "research_summary" in result
    assert len(result["research_summary"]) > 0


@patch("agents.base_agent.BaseAgent.call_llm")
def test_writer_produces_english_draft(mock_call, sample_state):
    """Writer should produce draft_en in Markdown."""
    from agents.writer import WriterAgent

    mock_call.return_value = make_mock_message([
        make_text_block("# AI Agent Design Patterns\n\nThis is the body."),
    ])

    agent = WriterAgent()
    result = agent.run(sample_state)

    assert "draft_en" in result
    assert "AI Agent" in result["draft_en"]
    assert result["rewrite_count"] == 0


@patch("agents.base_agent.BaseAgent.call_llm")
def test_writer_rewrite_increments_count(mock_call, sample_state, sample_critic_fail, sample_fact_check):
    """Writer rewrite should use rewrite prompt and increment count."""
    from agents.writer import WriterAgent

    sample_state["rewrite_count"] = 1
    sample_state["critic_feedback"] = sample_critic_fail
    sample_state["fact_check"] = sample_fact_check
    sample_state["draft_en"] = "Previous English draft"

    mock_call.return_value = make_mock_message([
        make_text_block("# Improved AI Agent Design Patterns\n\nImproved body."),
    ])

    agent = WriterAgent()
    result = agent.run(sample_state)

    assert result["rewrite_count"] == 2
    assert "draft_en" in result


@patch("agents.base_agent.BaseAgent.call_llm")
def test_fact_checker_produces_result(mock_call, sample_state):
    """Fact Checker should produce FactCheckResult."""
    from agents.fact_checker import FactCheckerAgent

    sample_state["draft_en"] = "AI agents are 100% accurate."

    mock_call.return_value = make_mock_message([
        make_tool_use_block("report_fact_check", {
            "claims_checked": 3,
            "issues_found": [{
                "claim": "100% 정확",
                "issue": "Overstated",
                "severity": "high",
                "suggestion": "Qualify claim",
            }],
            "overall_accuracy": 0.7,
            "suggestions": ["Add nuance"],
        }),
    ])

    agent = FactCheckerAgent()
    result = agent.run(sample_state)

    assert "fact_check" in result
    assert isinstance(result["fact_check"], FactCheckResult)
    assert result["fact_check"].claims_checked == 3
    assert len(result["fact_check"].issues_found) == 1


@patch("agents.base_agent.BaseAgent.call_llm")
def test_fact_checker_computes_diff(mock_call, sample_state, sample_fact_check_with_issues):
    """Fact Checker should compute diff on rewrite rounds."""
    from agents.fact_checker import FactCheckerAgent

    sample_state["draft_en"] = "Revised English draft"
    sample_state["fact_check"] = sample_fact_check_with_issues

    mock_call.return_value = make_mock_message([
        make_tool_use_block("report_fact_check", {
            "claims_checked": 3,
            "issues_found": [],
            "overall_accuracy": 0.95,
            "suggestions": [],
        }),
    ])

    agent = FactCheckerAgent()
    result = agent.run(sample_state)

    assert "fact_check_diff" in result
    assert "AI agents are 100% accurate" in result["fact_check_diff"].resolved


@patch("agents.base_agent.BaseAgent.call_llm")
def test_critic_pass_verdict(mock_call, sample_state, sample_fact_check):
    """Critic should PASS when score >= 7 and no high-severity issues."""
    from agents.critic import CriticAgent

    sample_state["draft_en"] = "A well-written English draft."
    sample_state["fact_check"] = sample_fact_check

    mock_call.return_value = make_mock_message([
        make_tool_use_block("submit_evaluation", {
            "verdict": "pass",
            "score": 8,
            "strengths": ["Clear", "Well-structured"],
            "weaknesses": ["Minor issues"],
            "specific_feedback": "Good work.",
            "rewrite_instructions": "",
        }),
    ])

    agent = CriticAgent()
    result = agent.run(sample_state)

    assert result["critic_feedback"].verdict == Verdict.PASS
    assert result["critic_feedback"].score == 8


@patch("agents.base_agent.BaseAgent.call_llm")
def test_critic_fail_verdict(mock_call, sample_state, sample_fact_check):
    """Critic should FAIL when score < 7."""
    from agents.critic import CriticAgent

    sample_state["draft_en"] = "A weak English draft."
    sample_state["fact_check"] = sample_fact_check

    mock_call.return_value = make_mock_message([
        make_tool_use_block("submit_evaluation", {
            "verdict": "fail",
            "score": 4,
            "strengths": ["Good topic"],
            "weaknesses": ["Shallow", "No examples"],
            "specific_feedback": "Needs work.",
            "rewrite_instructions": "Add depth and examples.",
        }),
    ])

    agent = CriticAgent()
    result = agent.run(sample_state)

    assert result["critic_feedback"].verdict == Verdict.FAIL
    assert result["critic_feedback"].score == 4


@patch("agents.base_agent.BaseAgent.call_llm")
def test_editor_edits_english_draft(mock_call, sample_state):
    """Editor should edit English draft."""
    from agents.editor import EditorAgent

    sample_state["draft_en"] = "English draft"

    mock_call.return_value = make_mock_message([make_text_block("Edited English draft")])

    agent = EditorAgent()
    result = agent.run(sample_state)

    assert "edited_draft_en" in result
    assert mock_call.call_count == 1


@patch("agents.base_agent.BaseAgent.call_llm")
def test_linkedin_produces_posts(mock_call, sample_state):
    """LinkedIn agent should produce KO and EN LinkedIn posts."""
    from agents.linkedin import LinkedInAgent

    sample_state["draft_en"] = "# AI Agents\n\nFull English post."

    mock_call.return_value = make_mock_message([
        make_tool_use_block("submit_linkedin_posts", {
            "en": "LinkedIn post about AI Agents. #AI #Agents",
        }),
    ])

    agent = LinkedInAgent()
    result = agent.run(sample_state)

    assert "linkedin_post_en" in result
    assert "#AI" in result["linkedin_post_en"]


@patch("agents.base_agent.BaseAgent.call_llm")
def test_seo_optimizer_produces_metadata(mock_call, sample_state):
    """SEO Optimizer should produce SEOMetadata and final posts."""
    from agents.seo_optimizer import SEOOptimizerAgent

    sample_state["edited_draft_en"] = "Edited English draft about AI agents."

    mock_call.return_value = make_mock_message([
        make_tool_use_block("submit_seo_metadata", {
            "optimized_title": "AI Agent Design Patterns",
            "meta_description": "A practical guide to AI agent design",
            "primary_keyword": "AI agents",
            "secondary_keywords": ["multi-agent", "design patterns"],
            "suggested_slug": "ai-agent-design-patterns",
        }),
        make_text_block("# AI Agent Design Patterns\n\nSEO optimized body."),
    ])

    agent = SEOOptimizerAgent()
    result = agent.run(sample_state)

    assert "seo_metadata_en" in result
    assert isinstance(result["seo_metadata_en"], SEOMetadata)
    assert result["seo_metadata_en"].optimized_title == "AI Agent Design Patterns"
    assert "final_post_en" in result
