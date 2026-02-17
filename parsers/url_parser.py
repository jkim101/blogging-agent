"""URL content parser using Trafilatura.

Extracts clean text content from web URLs with noise removal.
See 설계서 §6 (Trafilatura).
"""

from __future__ import annotations

import json
import logging

import trafilatura

from core.state import SourceContent, SourceType

logger = logging.getLogger(__name__)


def parse_url(url: str) -> SourceContent:
    """Fetch and parse web content from a URL.

    Uses trafilatura for main-content extraction with noise removal.
    Raises ValueError if fetching or extraction fails.
    """
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        raise ValueError(f"Failed to fetch URL: {url}")

    text = trafilatura.extract(
        downloaded,
        include_comments=False,
        include_tables=True,
        favor_recall=True,
    )
    if not text:
        raise ValueError(f"Failed to extract content from URL: {url}")

    # Extract metadata via JSON output
    meta_json = trafilatura.extract(
        downloaded,
        output_format="json",
        include_comments=False,
    )

    meta_dict: dict = {}
    title = ""
    if meta_json:
        try:
            parsed = json.loads(meta_json)
            title = parsed.get("title", "")
            meta_dict = {
                k: v for k, v in parsed.items()
                if k in ("author", "date", "sitename", "categories", "tags")
                and v
            }
        except json.JSONDecodeError:
            logger.warning("Failed to parse metadata JSON for URL: %s", url)

    return SourceContent(
        source_type=SourceType.URL,
        origin=url,
        title=title,
        content=text,
        metadata=meta_dict,
    )
