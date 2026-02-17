"""FastAPI web application for the blogging agent dashboard.

Provides HITL review interface, pipeline management, and status monitoring.
Uses Jinja2 templates + HTMX for real-time updates.
See 설계서 §5 for HITL design, §10 for authentication.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, Form, Request, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from config.settings import DASHBOARD_PASSWORD, STYLE_GUIDE_PATH
from core.runner import PipelineRunner
from core.state import HumanDecision, PublishTarget, SourceContent
from parsers.url_parser import parse_url
from parsers.pdf_parser import parse_pdf
from parsers.youtube_parser import parse_youtube

logger = logging.getLogger(__name__)

app = FastAPI(title="Blogging Agent Dashboard")
app.add_middleware(SessionMiddleware, secret_key="blogging-agent-secret-key")

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
        except Exception:
            pass

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
):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    sources: list[SourceContent] = []

    # Parse URLs
    for url in urls:
        if url.strip():
            try:
                sources.append(parse_url(url.strip()))
            except Exception as e:
                logger.warning("Failed to parse URL %s: %s", url, e)

    # Parse YouTube URLs
    for yt_url in youtube_urls:
        if yt_url.strip():
            try:
                sources.append(parse_youtube(yt_url.strip()))
            except Exception as e:
                logger.warning("Failed to parse YouTube URL %s: %s", yt_url, e)

    # Parse PDFs
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for pdf_file in pdfs:
        if pdf_file.filename and pdf_file.size and pdf_file.size > 0:
            save_path = UPLOAD_DIR / pdf_file.filename
            with open(save_path, "wb") as f:
                shutil.copyfileobj(pdf_file.file, f)
            try:
                sources.append(parse_pdf(save_path))
            except Exception as e:
                logger.warning("Failed to parse PDF %s: %s", pdf_file.filename, e)

    if not sources:
        return templates.TemplateResponse(
            "new_pipeline.html",
            {"request": request, "error": "No valid sources provided."},
        )

    runner = get_runner()
    thread_id = runner.start(sources)

    # Track pipeline in session
    if "pipelines" not in request.session:
        request.session["pipelines"] = []
    request.session["pipelines"].append(thread_id)

    return RedirectResponse(f"/pipeline/{thread_id}", status_code=302)


@app.get("/pipeline/{thread_id}", response_class=HTMLResponse)
async def pipeline_detail(request: Request, thread_id: str):
    if not is_authenticated(request):
        return RedirectResponse("/login", status_code=302)

    runner = get_runner()
    status = runner.get_status(thread_id)
    state = runner.get_state(thread_id)

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
    runner.resume(thread_id, human_input)

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
    runner.resume(thread_id, human_input)

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
