"""PDF content parser using PyMuPDF.

Extracts text content from PDF files.
See 설계서 §6 (PyMuPDF).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pymupdf

from core.state import SourceContent, SourceType

logger = logging.getLogger(__name__)


def parse_pdf(file_path: str | Path) -> SourceContent:
    """Extract text content from a PDF file.

    Concatenates text from all pages. Raises FileNotFoundError or ValueError on failure.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF not found: {path}")

    with pymupdf.open(str(path)) as doc:
        pages = [page.get_text().strip() for page in doc if page.get_text().strip()]

    if not pages:
        raise ValueError(f"No text content extracted from PDF: {path}")

    content = "\n\n".join(pages)

    return SourceContent(
        source_type=SourceType.PDF,
        origin=str(path),
        title=path.stem,
        content=content,
        metadata={"page_count": len(pages)},
    )
