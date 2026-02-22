"""Parser unit tests.

Tests URL, PDF, and YouTube parsing functionality.
"""

import pytest
from unittest.mock import MagicMock, patch

from core.state import SourceType


@patch("parsers.url_parser.trafilatura")
def test_url_parser_returns_source_content(mock_traf):
    """URL parser should return SourceContent with extracted text."""
    from parsers.url_parser import parse_url

    mock_traf.fetch_url.return_value = "<html>content</html>"
    mock_traf.extract.return_value = (
        '{"title": "Test Article", "author": "Author", "date": "2026-01-01",'
        ' "text": "Extracted article text about AI agents."}'
    )

    result = parse_url("https://example.com/article")

    assert result.source_type == SourceType.URL
    assert result.origin == "https://example.com/article"
    assert result.title == "Test Article"
    assert "AI agents" in result.content
    assert result.metadata.get("author") == "Author"


@patch("parsers.url_parser.trafilatura")
def test_url_parser_handles_fetch_failure(mock_traf):
    """URL parser should raise ValueError on fetch failure."""
    from parsers.url_parser import parse_url
    import pytest

    mock_traf.fetch_url.return_value = None

    with pytest.raises(ValueError, match="Failed to fetch"):
        parse_url("https://example.com/bad-url")


@patch("parsers.url_parser.trafilatura")
def test_url_parser_handles_extract_failure(mock_traf):
    """URL parser should raise ValueError when extraction fails."""
    from parsers.url_parser import parse_url
    import pytest

    mock_traf.fetch_url.return_value = "<html>content</html>"
    mock_traf.extract.return_value = None

    with pytest.raises(ValueError, match="Failed to extract"):
        parse_url("https://example.com/empty")


@patch("parsers.pdf_parser.pymupdf")
def test_pdf_parser_returns_source_content(mock_pymupdf, tmp_path):
    """PDF parser should return SourceContent with extracted text."""
    from parsers.pdf_parser import parse_pdf

    # Create a dummy PDF file
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 dummy")

    # Mock pymupdf
    mock_page = MagicMock()
    mock_page.get_text.return_value = "Page 1 content about AI."

    mock_doc = MagicMock()
    mock_doc.__iter__ = lambda self: iter([mock_page])
    mock_doc.__enter__ = lambda self: mock_doc
    mock_doc.__exit__ = MagicMock(return_value=False)
    mock_pymupdf.open.return_value = mock_doc

    result = parse_pdf(pdf_path)

    assert result.source_type == SourceType.PDF
    assert "AI" in result.content
    assert result.metadata["page_count"] == 1


def test_pdf_parser_handles_missing_file():
    """PDF parser should raise FileNotFoundError for missing files."""
    from parsers.pdf_parser import parse_pdf

    with pytest.raises(FileNotFoundError):
        parse_pdf("/nonexistent/file.pdf")


# --- YouTube parser tests ---

@patch("parsers.youtube_parser.YouTubeTranscriptApi")
def test_youtube_parser_returns_source_content(mock_api_cls):
    """YouTube parser should return SourceContent with transcript text."""
    from parsers.youtube_parser import parse_youtube

    mock_snippet_1 = MagicMock()
    mock_snippet_1.text = "안녕하세요."
    mock_snippet_2 = MagicMock()
    mock_snippet_2.text = "오늘은 AI에 대해 이야기합니다."

    mock_fetched = MagicMock()
    mock_fetched.snippets = [mock_snippet_1, mock_snippet_2]

    mock_transcript = MagicMock()
    mock_transcript.language_code = "ko"
    mock_transcript.fetch.return_value = mock_fetched

    mock_transcript_list = MagicMock()
    mock_transcript_list.find_transcript.return_value = mock_transcript

    mock_api = MagicMock()
    mock_api.list.return_value = mock_transcript_list
    mock_api_cls.return_value = mock_api

    result = parse_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    assert result.source_type == SourceType.YOUTUBE
    assert result.origin == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert "AI" in result.content
    assert result.metadata["video_id"] == "dQw4w9WgXcQ"
    assert result.metadata["language"] == "ko"


def test_youtube_parser_rejects_non_youtube_url():
    """YouTube parser should raise ValueError for non-YouTube URLs."""
    from parsers.youtube_parser import parse_youtube

    with pytest.raises(ValueError, match="Could not extract video ID"):
        parse_youtube("https://example.com/article")


@patch("parsers.youtube_parser.YouTubeTranscriptApi")
def test_youtube_parser_handles_no_transcripts(mock_api_cls):
    """YouTube parser should raise ValueError when no transcripts available."""
    from parsers.youtube_parser import parse_youtube

    mock_api = MagicMock()
    mock_api.list.side_effect = Exception("Subtitles are disabled")
    mock_api_cls.return_value = mock_api

    with pytest.raises(ValueError, match="Failed to fetch transcripts"):
        parse_youtube("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
