"""Output file saving — Markdown + YAML frontmatter.

Saves final blog posts to the output/ directory.
File naming: {slug}_{language}.md
See 설계서 §12 for output format specification.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from typing import Any

from config.settings import OUTPUT_DIR

logger = logging.getLogger(__name__)


def save_posts(
    state: dict[str, Any],
    pipeline_id: str = "",
    blog_urls: dict[str, str] | None = None,
) -> list[Path]:
    """Save final posts as Markdown files with YAML frontmatter.

    Args:
        state: Pipeline state dict.
        pipeline_id: Optional pipeline ID for frontmatter.
        blog_urls: Optional dict mapping language code to blog URL.

    Returns list of saved file paths.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    blog_urls = blog_urls or {}

    # Save Korean post
    if state.get("final_post_ko") or state.get("edited_draft_ko"):
        path = _save_single(
            state=state,
            language="ko",
            body=state.get("final_post_ko") or state.get("edited_draft_ko", ""),
            seo=state.get("seo_metadata_ko"),
            pipeline_id=pipeline_id,
            blog_url=blog_urls.get("ko", ""),
        )
        saved.append(path)

    # Save English post
    if state.get("final_post_en") or state.get("edited_draft_en"):
        path = _save_single(
            state=state,
            language="en",
            body=state.get("final_post_en") or state.get("edited_draft_en", ""),
            seo=state.get("seo_metadata_en"),
            pipeline_id=pipeline_id,
            blog_url=blog_urls.get("en", ""),
        )
        saved.append(path)

    return saved


def _save_single(
    state: dict[str, Any],
    language: str,
    body: str,
    seo: Any | None,
    pipeline_id: str,
    blog_url: str = "",
) -> Path:
    """Save a single language version with YAML frontmatter."""
    # Determine slug
    slug = "untitled"
    if seo and seo.suggested_slug:
        slug = seo.suggested_slug
    elif state.get("outline"):
        slug = _slugify(state["outline"].topic)

    filename = f"{slug}_{language}.md"
    path = OUTPUT_DIR / filename

    # Build frontmatter
    frontmatter_fields: list[str] = []
    _add(frontmatter_fields, "title", seo.optimized_title if seo else (state.get("outline").topic if state.get("outline") else ""))
    _add(frontmatter_fields, "date", date.today().isoformat())
    _add(frontmatter_fields, "language", language)

    if seo:
        _add(frontmatter_fields, "meta_description", seo.meta_description)
        _add(frontmatter_fields, "primary_keyword", seo.primary_keyword)
        if seo.secondary_keywords:
            keywords = ", ".join(f'"{kw}"' for kw in seo.secondary_keywords)
            frontmatter_fields.append(f"secondary_keywords: [{keywords}]")
        _add(frontmatter_fields, "slug", seo.suggested_slug)

    if state.get("critic_feedback"):
        _add(frontmatter_fields, "critic_score", state["critic_feedback"].score)
    _add(frontmatter_fields, "rewrite_count", state.get("rewrite_count", 0))
    if state.get("fact_check"):
        _add(frontmatter_fields, "fact_check_accuracy", state["fact_check"].overall_accuracy)
    if blog_url:
        _add(frontmatter_fields, "blog_url", blog_url)
    if pipeline_id:
        _add(frontmatter_fields, "pipeline_id", pipeline_id)

    frontmatter = "---\n" + "\n".join(frontmatter_fields) + "\n---\n\n"
    content = frontmatter + body

    path.write_text(content, encoding="utf-8")
    logger.info("Saved %s post: %s", language.upper(), path)

    return path


def _add(fields: list[str], key: str, value: Any) -> None:
    """Add a key-value pair to frontmatter fields."""
    if isinstance(value, str):
        # Quote strings that contain special YAML characters
        if any(c in value for c in ':"{}[]#&*!|>\'%@'):
            fields.append(f'{key}: "{value}"')
        else:
            fields.append(f"{key}: {value}")
    else:
        fields.append(f"{key}: {value}")


def _slugify(text: str) -> str:
    """Convert text to a URL-friendly slug."""
    import re
    slug = text.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")[:60]
