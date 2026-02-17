"""YouTube transcript parser using youtube-transcript-api.

Extracts video transcripts for use as blog source content.
Supports youtube.com and youtu.be URL formats.
"""

from __future__ import annotations

import logging
import re

from youtube_transcript_api import YouTubeTranscriptApi

from core.state import SourceContent, SourceType

logger = logging.getLogger(__name__)

_YOUTUBE_PATTERNS = [
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/watch\?.*v=([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?youtu\.be/([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:https?://)?(?:www\.)?youtube\.com/embed/([a-zA-Z0-9_-]{11})"),
]


def _extract_video_id(url: str) -> str:
    """Extract video ID from a YouTube URL.

    Raises ValueError if the URL is not a valid YouTube URL.
    """
    for pattern in _YOUTUBE_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract video ID from URL: {url}")


def is_youtube_url(url: str) -> bool:
    """Check if a URL is a YouTube video URL."""
    return any(pattern.search(url) for pattern in _YOUTUBE_PATTERNS)


def parse_youtube(url: str) -> SourceContent:
    """Fetch and parse transcript from a YouTube video URL.

    Tries Korean transcript first, then English, then any available language.
    Raises ValueError if no transcript is available.
    """
    video_id = _extract_video_id(url)

    try:
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
    except Exception as e:
        raise ValueError(f"Failed to fetch transcripts for video {video_id}: {e}")

    # Try preferred languages in order
    transcript = None
    for lang in ["ko", "en"]:
        try:
            transcript = transcript_list.find_transcript([lang])
            break
        except Exception:
            continue

    # Fall back to any available transcript
    if transcript is None:
        try:
            transcript = next(iter(transcript_list))
        except StopIteration:
            raise ValueError(f"No transcripts available for video {video_id}")

    entries = transcript.fetch()
    text = " ".join(entry["text"] for entry in entries)

    if not text.strip():
        raise ValueError(f"Empty transcript for video {video_id}")

    return SourceContent(
        source_type=SourceType.YOUTUBE,
        origin=url,
        title=f"YouTube: {video_id}",
        content=text,
        metadata={
            "video_id": video_id,
            "language": transcript.language_code,
        },
    )
