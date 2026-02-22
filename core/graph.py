"""LangGraph pipeline definition with HITL interrupts and SqliteSaver.

Defines the full pipeline graph:
  Research Planner → [HITL] → Writer(KO) → Fact Checker → Critic
    ↕ (rewrite loop)
  → Translator → Editor(KO+EN) → SEO Optimizer(KO+EN) → [HITL] → Publish

See 설계서 §2 for pipeline architecture, §5 for HITL design.
"""

from __future__ import annotations

import logging
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.critic import CriticAgent
from agents.editor import EditorAgent
from agents.fact_checker import FactCheckerAgent
from agents.research_planner import ResearchPlannerAgent
from agents.seo_optimizer import SEOOptimizerAgent
from agents.translator import TranslatorAgent
from agents.writer import WriterAgent
from config.settings import MAX_REWRITE_ATTEMPTS, SQLITE_DB_PATH
from core.state import BlogConfig, HumanDecision, PipelineState, Verdict

logger = logging.getLogger(__name__)

# Instantiate agents
_research_planner = ResearchPlannerAgent()
_writer = WriterAgent()
_fact_checker = FactCheckerAgent()
_critic = CriticAgent()
_translator = TranslatorAgent()
_editor = EditorAgent()
_seo_optimizer = SEOOptimizerAgent()


# --- Node functions ---

def research_planner_node(state: PipelineState) -> dict:
    logger.info("Running: research_planner")
    return _research_planner.run(state)


def outline_review_node(state: PipelineState) -> dict:
    """HITL checkpoint #1: Outline review.

    This node is a pass-through — the actual pause happens via
    interrupt_before. When resumed, the state will already contain
    outline_decision and outline_human_notes from the web UI.
    """
    decision = state.get("outline_decision")
    if decision == HumanDecision.REJECT:
        logger.info("Outline rejected by human")
    else:
        logger.info("Outline approved (decision=%s)", decision)
    return {}


def writer_node(state: PipelineState) -> dict:
    logger.info("Running: writer (rewrite_count=%d)", state.get("rewrite_count", 0))
    return _writer.run(state)


def fact_checker_node(state: PipelineState) -> dict:
    logger.info("Running: fact_checker")
    return _fact_checker.run(state)


def critic_node(state: PipelineState) -> dict:
    logger.info("Running: critic")
    return _critic.run(state)


def translator_node(state: PipelineState) -> dict:
    logger.info("Running: translator")
    return _translator.run(state)


def editor_node(state: PipelineState) -> dict:
    logger.info("Running: editor")
    return _editor.run(state)


def seo_optimizer_node(state: PipelineState) -> dict:
    logger.info("Running: seo_optimizer")
    return _seo_optimizer.run(state)


def publish_review_node(state: PipelineState) -> dict:
    """HITL checkpoint #2: Publish review.

    Pass-through node. Paused via interrupt_before.
    """
    decision = state.get("publish_decision")
    logger.info("Publish review (decision=%s)", decision)
    return {}


def publish_node(state: PipelineState) -> dict:
    """Publish to GitHub Pages (if requested) and save final posts to output directory."""
    from core.output import save_posts
    from core.publisher import JekyllPublisher, PublishError

    result: dict = {"current_step": "publish"}
    blog_urls: dict[str, str] = {}

    # Publish to GitHub Pages if targets are set
    targets = state.get("publish_targets", [])
    jekyll_targets = [t for t in targets if t.publish and t.platform == "github_pages"]

    if jekyll_targets:
        try:
            publisher = JekyllPublisher()
            for target in jekyll_targets:
                lang = target.language
                seo = state.get(f"seo_metadata_{lang}")
                body = state.get(f"final_post_{lang}") or state.get(f"edited_draft_{lang}", "")
                if not body:
                    continue

                title = seo.optimized_title if seo else ""
                slug = seo.suggested_slug if seo else "untitled"
                tags = []
                if seo:
                    if seo.primary_keyword:
                        tags.append(seo.primary_keyword)
                    tags.extend(seo.secondary_keywords)

                url = publisher.publish_post(
                    title=title, body_markdown=body, slug=slug,
                    tags=tags, language=lang,
                )
                blog_urls[lang] = url
                result[f"blog_url_{lang}"] = url
                logger.info("Published %s to GitHub Pages: %s", lang.upper(), url)

            # Commit and push once after all posts are written
            if blog_urls:
                commit_title = title or "New blog post"
                posts_dir = publisher._repo_path / "_posts"
                publisher.commit_and_push(paths=[posts_dir], title=f"Add post: {commit_title}")
        except PublishError as e:
            logger.error("Jekyll publish failed: %s", e)

    # Always save local files
    logger.info("Saving final posts")
    saved = save_posts(state, blog_urls=blog_urls)
    for path in saved:
        logger.info("Saved: %s", path)

    return result


# --- Routing functions ---

def route_after_outline_review(state: PipelineState) -> str:
    """Route after HITL #1: approve → writer, reject → end."""
    decision = state.get("outline_decision", HumanDecision.APPROVE)
    if decision == HumanDecision.REJECT:
        return END
    return "writer"


def route_after_critic(state: PipelineState) -> str:
    """Route after Critic: pass → translator, fail → writer (up to max)."""
    feedback = state.get("critic_feedback")
    rewrite_count = state.get("rewrite_count", 0)

    if feedback and feedback.verdict == Verdict.FAIL:
        if rewrite_count < MAX_REWRITE_ATTEMPTS:
            logger.info("Critic FAIL → rewrite (attempt %d/%d)", rewrite_count + 1, MAX_REWRITE_ATTEMPTS)
            return "writer"
        else:
            logger.info("Max rewrites reached (%d), forcing pass", MAX_REWRITE_ATTEMPTS)

    config = state.get("blog_config") or BlogConfig()
    if config.output_language == "ko-only":
        logger.info("output_language=ko-only → skipping translator")
        return "editor"

    return "translator"


def route_after_publish_review(state: PipelineState) -> str:
    """Route after HITL #2: publish → publish, reject → end."""
    decision = state.get("publish_decision", HumanDecision.APPROVE)
    if decision == HumanDecision.REJECT:
        return END
    return "publish"


# --- Graph builder ---

def build_graph() -> SqliteSaver:
    """Build and return the compiled LangGraph StateGraph with checkpointer."""
    graph = StateGraph(PipelineState)

    # Add nodes
    graph.add_node("research_planner", research_planner_node)
    graph.add_node("outline_review", outline_review_node)
    graph.add_node("writer", writer_node)
    graph.add_node("fact_checker", fact_checker_node)
    graph.add_node("critic", critic_node)
    graph.add_node("translator", translator_node)
    graph.add_node("editor", editor_node)
    graph.add_node("seo_optimizer", seo_optimizer_node)
    graph.add_node("publish_review", publish_review_node)
    graph.add_node("publish", publish_node)

    # Linear edges
    graph.add_edge(START, "research_planner")
    graph.add_edge("research_planner", "outline_review")
    graph.add_edge("writer", "fact_checker")
    graph.add_edge("fact_checker", "critic")
    graph.add_edge("translator", "editor")
    graph.add_edge("editor", "seo_optimizer")
    graph.add_edge("seo_optimizer", "publish_review")
    graph.add_edge("publish", END)

    # Conditional edges
    graph.add_conditional_edges("outline_review", route_after_outline_review)
    graph.add_conditional_edges("critic", route_after_critic)
    graph.add_conditional_edges("publish_review", route_after_publish_review)

    # Set up checkpointer
    db_path = Path(SQLITE_DB_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    import sqlite3
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    checkpointer = SqliteSaver(conn)

    # Compile with HITL interrupts
    compiled = graph.compile(
        checkpointer=checkpointer,
        interrupt_before=["outline_review", "publish_review"],
    )

    return compiled
