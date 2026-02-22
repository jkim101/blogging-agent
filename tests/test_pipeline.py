"""Pipeline logic tests.

Tests state transitions, conditional routing, and HITL checkpoints.
See 설계서 §13.2.
"""

from core.state import CriticFeedback, HumanDecision, Verdict
from core.graph import (
    route_after_critic,
    route_after_outline_review,
    route_after_publish_review,
)
from langgraph.graph import END


def test_critic_pass_routes_to_translator(sample_state, sample_critic_pass):
    """Critic PASS verdict should route to Translator."""
    sample_state["critic_feedback"] = sample_critic_pass
    sample_state["rewrite_count"] = 1

    result = route_after_critic(sample_state)
    assert result == "translator"


def test_critic_fail_routes_to_writer(sample_state, sample_critic_fail):
    """Critic FAIL verdict should route back to Writer for rewrite."""
    sample_state["critic_feedback"] = sample_critic_fail
    sample_state["rewrite_count"] = 1

    result = route_after_critic(sample_state)
    assert result == "writer"


def test_max_rewrite_forces_pass(sample_state, sample_critic_fail):
    """After MAX_REWRITE_ATTEMPTS, pipeline should proceed even on FAIL."""
    sample_state["critic_feedback"] = sample_critic_fail
    sample_state["rewrite_count"] = 3  # MAX_REWRITE_ATTEMPTS default

    result = route_after_critic(sample_state)
    assert result == "translator"


def test_outline_approve_routes_to_writer(sample_state):
    """Outline approve should route to writer."""
    sample_state["outline_decision"] = HumanDecision.APPROVE

    result = route_after_outline_review(sample_state)
    assert result == "writer"


def test_outline_edit_routes_to_writer(sample_state):
    """Outline edit (approve with notes) should route to writer."""
    sample_state["outline_decision"] = HumanDecision.EDIT

    result = route_after_outline_review(sample_state)
    assert result == "writer"


def test_outline_reject_routes_to_end(sample_state):
    """Outline reject should end the pipeline."""
    sample_state["outline_decision"] = HumanDecision.REJECT

    result = route_after_outline_review(sample_state)
    assert result == END


def test_publish_approve_routes_to_publish(sample_state):
    """Publish approve should route to publish node."""
    sample_state["publish_decision"] = HumanDecision.APPROVE

    result = route_after_publish_review(sample_state)
    assert result == "publish"


def test_publish_reject_routes_to_end(sample_state):
    """Publish reject should end the pipeline."""
    sample_state["publish_decision"] = HumanDecision.REJECT

    result = route_after_publish_review(sample_state)
    assert result == END


def test_save_posts_creates_files(tmp_path, sample_state, sample_critic_pass, sample_fact_check):
    """save_posts should create Markdown files with YAML frontmatter."""
    from unittest.mock import patch
    from core.output import save_posts
    from core.state import SEOMetadata

    sample_state["critic_feedback"] = sample_critic_pass
    sample_state["fact_check"] = sample_fact_check
    sample_state["final_post_ko"] = "# 한글 포스트\n\n본문입니다."
    sample_state["final_post_en"] = "# English Post\n\nBody text."
    sample_state["seo_metadata_ko"] = SEOMetadata(
        optimized_title="AI 에이전트 설계",
        meta_description="설계 가이드",
        primary_keyword="AI 에이전트",
        secondary_keywords=["설계"],
        suggested_slug="ai-agent-design",
    )
    sample_state["seo_metadata_en"] = SEOMetadata(
        optimized_title="AI Agent Design",
        meta_description="Design guide",
        primary_keyword="AI agents",
        secondary_keywords=["design"],
        suggested_slug="ai-agent-design",
    )

    with patch("core.output.OUTPUT_DIR", tmp_path):
        saved = save_posts(sample_state, pipeline_id="test123")

    assert len(saved) == 2
    assert (tmp_path / "ai-agent-design_ko.md").exists()
    assert (tmp_path / "ai-agent-design_en.md").exists()

    ko_content = (tmp_path / "ai-agent-design_ko.md").read_text()
    assert ko_content.startswith("---\n")
    assert "language: ko" in ko_content
    assert "critic_score: 8" in ko_content
    assert "pipeline_id: test123" in ko_content
    assert "# 한글 포스트" in ko_content



def test_publish_node_without_targets(tmp_path, sample_state, sample_critic_pass, sample_fact_check):
    """publish_node without targets should just save local files."""
    from unittest.mock import patch
    from core.graph import publish_node
    from core.state import SEOMetadata

    sample_state["critic_feedback"] = sample_critic_pass
    sample_state["fact_check"] = sample_fact_check
    sample_state["final_post_ko"] = "# 한글 포스트"
    sample_state["seo_metadata_ko"] = SEOMetadata(
        optimized_title="Test", suggested_slug="test-post",
    )

    with patch("core.output.OUTPUT_DIR", tmp_path):
        result = publish_node(sample_state)

    assert result["current_step"] == "publish"
    assert "blog_url_ko" not in result
    assert (tmp_path / "test-post_ko.md").exists()


def test_graph_compiles():
    """Graph should compile without errors."""
    from core.graph import build_graph
    graph = build_graph()
    nodes = list(graph.get_graph().nodes.keys())

    assert "research_planner" in nodes
    assert "writer" in nodes
    assert "fact_checker" in nodes
    assert "critic" in nodes
    assert "translator" in nodes
    assert "editor" in nodes
    assert "seo_optimizer" in nodes
    assert "outline_review" in nodes
    assert "publish_review" in nodes
    assert "publish" in nodes
