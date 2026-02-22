"""FastAPI web application for the blogging agent dashboard.

Provides HITL review interface, pipeline management, and status monitoring.
Uses Jinja2 templates + HTMX for real-time updates.
See 설계서 §5 for HITL design, §10 for authentication.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config.settings import DASHBOARD_PASSWORD, STYLE_GUIDE_PATH
from core.runner import PipelineRunner
from core.state import BlogConfig, HumanDecision, PublishTarget, SourceContent
from parsers.url_parser import parse_url
from parsers.pdf_parser import parse_pdf
from parsers.youtube_parser import parse_youtube

logger = logging.getLogger(__name__)

app = FastAPI(title="Blogging Agent Dashboard")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "blogging-agent-secret-key"))

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"
UPLOAD_DIR = Path(__file__).parent.parent / "data" / "uploads"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Singleton runner
_runner: PipelineRunner | None = None


def get_runner() -> PipelineRunner:
    global _runner
    if _runner is None:
        _runner = PipelineRunner()
    return _runner


# --- Auth helpers ---

def is_authenticated(request: Request) -> bool:
    return request.session.get("authenticated", False)


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
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
    output_language: str = Form(default="both"),
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
        output_language=output_language,
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
    publish_ko: str = Form(default=""),
    publish_en: str = Form(default=""),
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    publish_targets = [
        PublishTarget(language="ko", platform="github_pages", publish=bool(publish_ko)),
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
