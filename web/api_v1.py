"""JSON REST API v1 for programmatic access.

Provides API-key-authenticated endpoints for personal-intelligence integration.
All existing HTML/session-based routes are unchanged.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Header
from pydantic import BaseModel, Field

from config.settings import BLOGGING_AGENT_API_KEY
from core.state import BlogConfig, HumanDecision, PublishTarget, SourceContent, SourceType
from web.runner_instance import get_runner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["v1"])


# --- Auth ---

def verify_api_key(x_api_key: Annotated[str, Header()]) -> None:
    if not BLOGGING_AGENT_API_KEY:
        raise HTTPException(status_code=500, detail="BLOGGING_AGENT_API_KEY not configured on server")
    if x_api_key != BLOGGING_AGENT_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


AuthDep = Annotated[None, Depends(verify_api_key)]


# --- Request / Response schemas ---

class SourceInput(BaseModel):
    source_type: SourceType
    origin: str = Field(description="Original URL, file path, or identifier")
    title: str = ""
    content: str = Field(default="", description="Pre-parsed text content (required for source_type=text)")
    metadata: dict = Field(default_factory=dict)


class BlogConfigInput(BaseModel):
    word_count: int = 1500
    tone: str = "professional"
    writing_style: str = "analysis"
    target_audience: str = ""
    primary_keyword: str = ""
    categories: list[str] = Field(default_factory=list)
    include_code_examples: bool = False
    include_tldr: bool = False
    custom_instructions: str = ""


class StartPipelineRequest(BaseModel):
    sources: list[SourceInput]
    blog_config: BlogConfigInput = Field(default_factory=BlogConfigInput)


class StartPipelineResponse(BaseModel):
    thread_id: str
    status: str = "started"


class PipelineStatusResponse(BaseModel):
    thread_id: str
    current_step: str
    is_interrupted: bool
    is_stuck: bool
    next_node: str | None
    rewrite_count: int
    has_outline: bool
    has_draft_en: bool
    has_final_en: bool
    critic_score: int | None
    outline: dict | None = None
    research_summary: str | None = None


class OutlineDecisionRequest(BaseModel):
    decision: str = Field(description="approve | edit | reject")
    notes: str = ""


class PublishDecisionRequest(BaseModel):
    decision: str = Field(description="approve | reject")
    publish_en: bool = True


class PipelineResultResponse(BaseModel):
    thread_id: str
    final_post_en: str
    linkedin_post_en: str
    seo_metadata_en: dict | None
    critic_score: int | None
    blog_url_en: str


# --- Endpoints ---

@router.post("/pipeline/start", response_model=StartPipelineResponse, status_code=201)
async def start_pipeline(body: StartPipelineRequest, _: AuthDep) -> Any:
    """Start a new blog generation pipeline from pre-parsed content or URLs."""
    sources = [
        SourceContent(
            source_type=s.source_type,
            origin=s.origin,
            title=s.title,
            content=s.content,
            metadata=s.metadata,
        )
        for s in body.sources
    ]

    if not sources:
        raise HTTPException(status_code=400, detail="At least one source is required")

    blog_config = BlogConfig(
        word_count=body.blog_config.word_count,
        tone=body.blog_config.tone,
        writing_style=body.blog_config.writing_style,
        target_audience=body.blog_config.target_audience,
        primary_keyword=body.blog_config.primary_keyword,
        categories=body.blog_config.categories,
        include_code_examples=body.blog_config.include_code_examples,
        include_tldr=body.blog_config.include_tldr,
        custom_instructions=body.blog_config.custom_instructions,
    )

    runner = get_runner()
    thread_id = await asyncio.to_thread(runner.start, sources, blog_config)
    logger.info("Pipeline started via API v1: %s", thread_id)

    return StartPipelineResponse(thread_id=thread_id, status="started")


@router.get("/pipeline/{thread_id}/status", response_model=PipelineStatusResponse)
async def get_pipeline_status(thread_id: str, _: AuthDep) -> Any:
    """Get current pipeline status."""
    runner = get_runner()
    try:
        status = runner.get_status(thread_id)
        state = runner.get_state(thread_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {e}")

    outline_data = None
    if state.get("outline"):
        outline = state["outline"]
        outline_data = {
            "topic": outline.topic,
            "angle": outline.angle,
            "target_audience": outline.target_audience,
            "key_points": outline.key_points,
            "structure": [
                {"heading": s.heading, "key_points": s.key_points}
                for s in outline.structure
            ],
            "estimated_word_count": outline.estimated_word_count,
        }

    return PipelineStatusResponse(
        thread_id=thread_id,
        current_step=status["current_step"],
        is_interrupted=status["is_interrupted"],
        is_stuck=status["is_stuck"],
        next_node=status["next_node"],
        rewrite_count=status["rewrite_count"],
        has_outline=status["has_outline"],
        has_draft_en=status["has_draft_en"],
        has_final_en=status["has_final_en"],
        critic_score=status["critic_score"],
        outline=outline_data,
        research_summary=state.get("research_summary") or None,
    )


@router.post("/pipeline/{thread_id}/outline-decision")
async def submit_outline_decision(
    thread_id: str, body: OutlineDecisionRequest, _: AuthDep
) -> Any:
    """Submit approve/edit/reject for the outline HITL checkpoint."""
    if body.decision not in ("approve", "edit", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve, edit, or reject")

    runner = get_runner()
    try:
        status = runner.get_status(thread_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {e}")

    if status.get("next_node") != "outline_review":
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline is not waiting for outline review (next_node={status.get('next_node')})",
        )

    human_input = {
        "outline_decision": HumanDecision(body.decision),
        "outline_human_notes": body.notes,
    }
    await asyncio.to_thread(runner.resume, thread_id, human_input)
    logger.info("Outline decision submitted for pipeline %s: %s", thread_id, body.decision)

    return {"thread_id": thread_id, "resumed": True}


@router.post("/pipeline/{thread_id}/publish-decision")
async def submit_publish_decision(
    thread_id: str, body: PublishDecisionRequest, _: AuthDep
) -> Any:
    """Submit approve/reject for the publish HITL checkpoint."""
    if body.decision not in ("approve", "reject"):
        raise HTTPException(status_code=400, detail="decision must be approve or reject")

    runner = get_runner()
    try:
        status = runner.get_status(thread_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {e}")

    if status.get("next_node") != "publish_review":
        raise HTTPException(
            status_code=409,
            detail=f"Pipeline is not waiting for publish review (next_node={status.get('next_node')})",
        )

    publish_targets = [
        PublishTarget(language="en", platform="github_pages", publish=body.publish_en),
    ]
    human_input = {
        "publish_decision": HumanDecision(body.decision),
        "publish_targets": publish_targets,
    }
    await asyncio.to_thread(runner.resume, thread_id, human_input)
    logger.info("Publish decision submitted for pipeline %s: %s", thread_id, body.decision)

    return {"thread_id": thread_id, "resumed": True}


@router.get("/pipeline/{thread_id}/result", response_model=PipelineResultResponse)
async def get_pipeline_result(thread_id: str, _: AuthDep) -> Any:
    """Get final output after pipeline completion."""
    runner = get_runner()
    try:
        state = runner.get_state(thread_id)
        status = runner.get_status(thread_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Pipeline not found: {e}")

    if not status["has_final_en"]:
        raise HTTPException(status_code=409, detail="Pipeline has not completed yet")

    seo = state.get("seo_metadata_en")
    seo_data = None
    if seo:
        seo_data = {
            "optimized_title": seo.optimized_title,
            "meta_description": seo.meta_description,
            "primary_keyword": seo.primary_keyword,
            "secondary_keywords": seo.secondary_keywords,
            "suggested_slug": seo.suggested_slug,
        }

    return PipelineResultResponse(
        thread_id=thread_id,
        final_post_en=state.get("final_post_en", ""),
        linkedin_post_en=state.get("linkedin_post_en", ""),
        seo_metadata_en=seo_data,
        critic_score=status["critic_score"],
        blog_url_en=state.get("blog_url_en", ""),
    )
