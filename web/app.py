"""FastAPI web application — AI Writing Hub.

Provides:
  - Blog Generator (full LangGraph pipeline with HITL)
  - Quick Summary (single-shot summarizer)
  - LinkedIn Article (single-shot long-form article writer)
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config.settings import DASHBOARD_PASSWORD, STYLE_GUIDE_PATH
from web.runner_instance import get_runner
from web.api_v1 import router as api_v1_router
from core.state import BlogConfig, HumanDecision, PublishTarget, SourceContent, ToolConfig
from parsers.url_parser import parse_url
from parsers.pdf_parser import parse_pdf
from parsers.youtube_parser import parse_youtube

# Simple in-memory job store for non-pipeline tools
_jobs: dict[str, dict] = {}


def _run_job(job_id: str, fn, *args):
    _jobs[job_id] = {"status": "running", "result": None, "error": None}
    def _worker():
        try:
            result = fn(*args)
            _jobs[job_id].update({"status": "completed", "result": result})
        except Exception as exc:
            logger.error("Job %s failed: %s", job_id, exc)
            _jobs[job_id].update({"status": "error", "error": str(exc)})
    threading.Thread(target=_worker, daemon=True).start()

logger = logging.getLogger(__name__)

app = FastAPI(title="Blogging Agent Dashboard")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "blogging-agent-secret-key"))
app.include_router(api_v1_router)

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


# --- Auth helpers ---

def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("home.html", {"request": request})


@app.get("/blog", response_class=HTMLResponse)
async def blog_home(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return RedirectResponse("/dashboard", status_code=302)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login(request: Request, password: str = Form(...)):
    if password == DASHBOARD_PASSWORD:
        request.session["authenticated"] = True
        return RedirectResponse("/dashboard", status_code=302)
    return templates.TemplateResponse(
        "login.html", {"request": request, "error": "Invalid password"}
    )


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    # Get all pipeline thread_ids from session
    pipelines = []
    for thread_id in request.session.get("pipelines", []):
        try:
            status = runner.get_status(thread_id)
            pipelines.append(status)
        except Exception as e:
            logger.error("Failed to load pipeline %s: %s", thread_id, e)
            # Show errored pipelines so they can be deleted
            pipelines.append({
                "thread_id": thread_id,
                "current_step": "error",
                "is_interrupted": False,
                "rewrite_count": 0,
                "critic_score": None,
                "has_final_ko": False,
                "has_final_en": False,
            })

    return templates.TemplateResponse(
        "dashboard.html", {"request": request, "pipelines": pipelines}
    )


@app.get("/new", response_class=HTMLResponse)
async def new_pipeline_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("new_pipeline.html", {"request": request})


@app.post("/pipeline/start")
async def start_pipeline(
    request: Request,
    urls: list[str] = Form(default=[]),
    youtube_urls: list[str] = Form(default=[]),
    pdfs: list[UploadFile] = File(default=[]),
    word_count: int = Form(default=1500),
    tone: str = Form(default="professional"),
    writing_style: str = Form(default="analysis"),
    target_audience: str = Form(default=""),
    primary_keyword: str = Form(default=""),
    categories: str = Form(default=""),
    include_code_examples: str = Form(default=""),
    include_tldr: str = Form(default=""),
    custom_instructions: str = Form(default=""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    sources: list[SourceContent] = []

    # Parse URLs
    for url in urls:
        if url.strip():
            try:
                sources.append(await asyncio.to_thread(parse_url, url.strip()))
            except Exception as e:
                logger.warning("Failed to parse URL %s: %s", url, e)

    # Parse YouTube URLs
    for yt_url in youtube_urls:
        if yt_url.strip():
            try:
                sources.append(await asyncio.to_thread(parse_youtube, yt_url.strip()))
            except Exception as e:
                logger.warning("Failed to parse YouTube URL %s: %s", yt_url, e)

    # Parse PDFs
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_file in pdfs:
        if pdf_file.filename and pdf_file.size and pdf_file.size > 0:
            save_path = UPLOAD_DIR / Path(pdf_file.filename).name
            with open(save_path, "wb") as f:
                shutil.copyfileobj(pdf_file.file, f)
            try:
                sources.append(await asyncio.to_thread(parse_pdf, save_path))
            except Exception as e:
                logger.warning("Failed to parse PDF %s: %s", pdf_file.filename, e)

    if not sources:
        return templates.TemplateResponse(
            "new_pipeline.html",
            {"request": request, "error": "No valid sources provided."},
        )

    blog_config = BlogConfig(
        word_count=word_count,
        tone=tone,
        writing_style=writing_style,
        target_audience=target_audience.strip(),
        primary_keyword=primary_keyword.strip(),
        categories=[c.strip() for c in categories.split(",") if c.strip()],
        include_code_examples=bool(include_code_examples),
        include_tldr=bool(include_tldr),
        custom_instructions=custom_instructions.strip(),
    )

    runner = get_runner()
    thread_id = await asyncio.to_thread(runner.start, sources, blog_config=blog_config)

    # Track pipeline in session (must reassign to trigger SessionMiddleware save)
    pipelines = list(request.session.get("pipelines", []))
    pipelines.append(thread_id)
    request.session["pipelines"] = pipelines

    return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)


@app.post("/pipeline/{thread_id}/retry")
async def retry_pipeline(request: Request, thread_id: str):
    """Retry a stuck pipeline from its last checkpoint."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    status = runner.get_status(thread_id)
    if not status.get("is_stuck"):
        logger.warning("retry skipped for %s: pipeline is not stuck (next=%s)", thread_id, status.get("next_node"))
        return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)

    try:
        await asyncio.to_thread(runner.retry, thread_id)
    except Exception as e:
        logger.error("Retry failed for pipeline %s: %s", thread_id, e)

    return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)


@app.post("/pipeline/{thread_id}/delete")
async def delete_pipeline(request: Request, thread_id: str):
    """Remove a pipeline from the dashboard session."""
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    pipelines = request.session.get("pipelines", [])
    if thread_id in pipelines:
        pipelines.remove(thread_id)
        request.session["pipelines"] = pipelines

    return RedirectResponse("/dashboard", status_code=302)


@app.get("/pipeline/{thread_id}", response_class=HTMLResponse)
async def pipeline_detail(request: Request, thread_id: str):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    try:
        status = runner.get_status(thread_id)
        state = runner.get_state(thread_id)
    except Exception as e:
        logger.error("Failed to load pipeline %s: %s", thread_id, e)
        return templates.TemplateResponse(
            "pipeline_status.html",
            {
                "request": request,
                "pipeline_id": thread_id,
                "status": {"current_step": "error", "is_interrupted": False, "rewrite_count": 0,
                           "critic_score": None, "has_final_ko": False, "has_final_en": False},
                "state": {},
                "error": f"Failed to load pipeline: {e}",
            },
        )

    # Route to appropriate view based on pipeline state
    if status["is_interrupted"]:
        if status["next_node"] == "outline_review":
            return templates.TemplateResponse(
                "review_outline.html",
                {
                    "request": request,
                    "pipeline_id": thread_id,
                    "outline": state.get("outline"),
                    "research_summary": state.get("research_summary", ""),
                },
            )
        elif status["next_node"] == "publish_review":
            return templates.TemplateResponse(
                "review_publish.html",
                {
                    "request": request,
                    "pipeline_id": thread_id,
                    "state": state,
                },
            )

    # Running or completed — show status
    return templates.TemplateResponse(
        "pipeline_status.html",
        {"request": request, "pipeline_id": thread_id, "status": status, "state": state},
    )


@app.post("/pipeline/{thread_id}/outline-decision")
async def outline_decision(
    request: Request,
    thread_id: str,
    decision: str = Form(...),
    notes: str = Form(default=""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    status = runner.get_status(thread_id)
    if status.get("next_node") != "outline_review":
        logger.warning("outline-decision skipped for %s: not at outline_review (next=%s)", thread_id, status.get("next_node"))
        return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)

    human_input = {
        "outline_decision": HumanDecision(decision),
        "outline_human_notes": notes,
    }
    await asyncio.to_thread(runner.resume, thread_id, human_input)

    return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)


@app.post("/pipeline/{thread_id}/publish-decision")
async def publish_decision(
    request: Request,
    thread_id: str,
    decision: str = Form(...),
    publish_en: str = Form(default=""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    status = runner.get_status(thread_id)
    if status.get("next_node") != "publish_review":
        logger.warning("publish-decision skipped for %s: not at publish_review (next=%s)", thread_id, status.get("next_node"))
        return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)

    publish_targets = [
        PublishTarget(language="en", platform="github_pages", publish=bool(publish_en)),
    ]
    human_input = {
        "publish_decision": HumanDecision(decision),
        "publish_targets": publish_targets,
    }
    await asyncio.to_thread(runner.resume, thread_id, human_input)

    return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)


# --- API endpoint for HTMX polling ---

@app.get("/api/pipeline/{thread_id}/status", response_class=HTMLResponse)
async def pipeline_status_fragment(request: Request, thread_id: str):
    """Return status HTML fragment for HTMX polling."""
    runner = get_runner()
    status = runner.get_status(thread_id)

    # If interrupted, redirect the client to the full page
    if status["is_interrupted"]:
        return HTMLResponse(
            content=f'<div hx-redirect="/pipeline/{thread_id}"></div>'
        )

    return templates.TemplateResponse(
        "fragments/status_bar.html",
        {"request": request, "status": status},
    )


@app.get("/style-guide", response_class=HTMLResponse)
async def style_guide(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    content = STYLE_GUIDE_PATH.read_text()
    return templates.TemplateResponse(
        "style_guide.html",
        {"request": request, "style_guide_content": content},
    )


# ---------------------------------------------------------------------------
# Shared helpers for simple tools
# ---------------------------------------------------------------------------

async def _parse_sources(
    urls: list[str],
    youtube_urls: list[str],
    pdfs: list[UploadFile],
) -> list[SourceContent]:
    sources: list[SourceContent] = []
    for url in urls:
        if url.strip():
            try:
                sources.append(await asyncio.to_thread(parse_url, url.strip()))
            except Exception as exc:
                logger.warning("Failed to parse URL %s: %s", url, exc)
    for yt_url in youtube_urls:
        if yt_url.strip():
            try:
                sources.append(await asyncio.to_thread(parse_youtube, yt_url.strip()))
            except Exception as exc:
                logger.warning("Failed to parse YouTube %s: %s", yt_url, exc)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_file in pdfs:
        if pdf_file.filename and pdf_file.size and pdf_file.size > 0:
            save_path = UPLOAD_DIR / Path(pdf_file.filename).name
            with open(save_path, "wb") as f:
                shutil.copyfileobj(pdf_file.file, f)
            try:
                sources.append(await asyncio.to_thread(parse_pdf, save_path))
            except Exception as exc:
                logger.warning("Failed to parse PDF %s: %s", pdf_file.filename, exc)
    return sources


# ---------------------------------------------------------------------------
# Summary tool
# ---------------------------------------------------------------------------

@app.get("/summary", response_class=HTMLResponse)
async def summary_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("summary_new.html", {"request": request})


@app.post("/summary/run")
async def summary_run(
    request: Request,
    urls: list[str] = Form(default=[]),
    youtube_urls: list[str] = Form(default=[]),
    pdfs: list[UploadFile] = File(default=[]),
    word_count: int = Form(default=400),
    tone: str = Form(default="professional"),
    target_audience: str = Form(default=""),
    include_tldr: str = Form(default=""),
    custom_instructions: str = Form(default=""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    sources = await _parse_sources(urls, youtube_urls, pdfs)
    if not sources:
        return templates.TemplateResponse(
            "summary_new.html",
            {"request": request, "error": "No valid sources provided."},
        )

    config = ToolConfig(
        word_count=word_count,
        tone=tone,
        target_audience=target_audience.strip(),
        include_tldr=bool(include_tldr),
        custom_instructions=custom_instructions.strip(),
    )

    from agents.summarizer import SummarizerAgent
    agent = SummarizerAgent()
    job_id = str(uuid.uuid4())[:8]
    _run_job(job_id, agent.run, sources, config)

    return RedirectResponse(f"/summary/{job_id}", status_code=302)


@app.get("/summary/{job_id}", response_class=HTMLResponse)
async def summary_result(request: Request, job_id: str):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    job = _jobs.get(job_id, {"status": "error", "error": "Job not found."})
    result_text = job.get("result", {}).get("summary", "") if job.get("result") else ""
    return templates.TemplateResponse("tool_result.html", {
        "request": request,
        "job_id": job_id,
        "tool": "summary",
        "tool_label": "Quick Summary",
        "back_url": "/summary",
        "status": job["status"],
        "result": result_text,
        "error": job.get("error"),
    })


# ---------------------------------------------------------------------------
# LinkedIn Article tool
# ---------------------------------------------------------------------------

@app.get("/linkedin-article", response_class=HTMLResponse)
async def linkedin_article_page(request: Request):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)
    return templates.TemplateResponse("linkedin_article_new.html", {"request": request})


@app.post("/linkedin-article/run")
async def linkedin_article_run(
    request: Request,
    urls: list[str] = Form(default=[]),
    youtube_urls: list[str] = Form(default=[]),
    pdfs: list[UploadFile] = File(default=[]),
    word_count: int = Form(default=800),
    tone: str = Form(default="professional"),
    target_audience: str = Form(default=""),
    include_tldr: str = Form(default=""),
    custom_instructions: str = Form(default=""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    sources = await _parse_sources(urls, youtube_urls, pdfs)
    if not sources:
        return templates.TemplateResponse(
            "linkedin_article_new.html",
            {"request": request, "error": "No valid sources provided."},
        )

    config = ToolConfig(
        word_count=word_count,
        tone=tone,
        target_audience=target_audience.strip(),
        include_tldr=bool(include_tldr),
        custom_instructions=custom_instructions.strip(),
    )

    from agents.linkedin_article import LinkedInArticleAgent
    agent = LinkedInArticleAgent()
    job_id = str(uuid.uuid4())[:8]
    _run_job(job_id, agent.run, sources, config)

    return RedirectResponse(f"/linkedin-article/{job_id}", status_code=302)


@app.get("/linkedin-article/{job_id}", response_class=HTMLResponse)
async def linkedin_article_result(request: Request, job_id: str):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    job = _jobs.get(job_id, {"status": "error", "error": "Job not found."})
    result_text = job.get("result", {}).get("article", "") if job.get("result") else ""
    return templates.TemplateResponse("tool_result.html", {
        "request": request,
        "job_id": job_id,
        "tool": "linkedin-article",
        "tool_label": "LinkedIn Article",
        "back_url": "/linkedin-article",
        "status": job["status"],
        "result": result_text,
        "error": job.get("error"),
    })


# ---------------------------------------------------------------------------
# Generic job polling endpoint (HTMX)
# ---------------------------------------------------------------------------

@app.get("/api/job/{job_id}/poll", response_class=HTMLResponse)
async def job_poll(request: Request, job_id: str, tool: str = ""):
    if not is_authenticated(request):
        return HTMLResponse("")

    job = _jobs.get(job_id, {"status": "error", "error": "Job not found."})
    tool_label = {"summary": "Quick Summary", "linkedin-article": "LinkedIn Article"}.get(tool, tool)
    back_url = f"/{tool}" if tool else "/"

    result_key = "summary" if tool == "summary" else "article"
    result_text = job.get("result", {}).get(result_key, "") if job.get("result") else ""

    return templates.TemplateResponse("fragments/job_poll.html", {
        "request": request,
        "job_id": job_id,
        "tool": tool,
        "tool_label": tool_label,
        "back_url": back_url,
        "status": job["status"],
        "result": result_text,
        "error": job.get("error"),
    })
