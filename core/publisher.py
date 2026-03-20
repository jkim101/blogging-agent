"""Jekyll (GitHub Pages) publishing client.

Publishes blog posts to a Jekyll site by writing Markdown files with
frontmatter to the _posts/ directory. Supports two modes:
- Local: writes to local repo, commits and pushes via git CLI
- API: pushes files via GitHub Contents API (for containerized deployments)
See 설계서 §12.2 for publishing specification.
"""

from __future__ import annotations

import base64
import logging
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from config.settings import (
    GITHUB_PAGES_REPO,
    GITHUB_PAGES_URL,
    GITHUB_TOKEN,
    JEKYLL_REPO_PATH,
)

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """Raised when Jekyll publishing fails."""


class JekyllPublisher:
    """Publishes posts to a Jekyll GitHub Pages site."""

    def __init__(self, repo_path: str = "") -> None:
        self._repo_path = Path(repo_path or JEKYLL_REPO_PATH)
        self._use_api = bool(GITHUB_TOKEN) and not self._repo_path.exists()
        self._pending_files: list[dict[str, str]] = []

    def _build_post_content(
        self,
        title: str,
        body_markdown: str,
        tags: list[str] | None = None,
    ) -> str:
        """Build Jekyll post content with frontmatter."""
        now = datetime.now(ZoneInfo("US/Eastern"))
        datetime_str = now.strftime("%Y-%m-%d %H:%M:%S %z")

        tags = tags or []
        tag_lines = "\n".join(f"  - {tag}" for tag in tags)

        frontmatter = f"""---
title: "{title}"
date: {datetime_str}
categories:
  - blog
tags:
{tag_lines}
layout: single
author_profile: true
read_time: true
comments: false
share: false
related: true
---"""

        return frontmatter + "\n\n" + body_markdown

    def _build_filename(self, slug: str, language: str) -> str:
        now = datetime.now(ZoneInfo("US/Eastern"))
        date_str = now.strftime("%Y-%m-%d")
        return f"{date_str}-{slug}_{language}.md"

    def publish_post(
        self,
        title: str,
        body_markdown: str,
        slug: str,
        tags: list[str] | None = None,
        language: str = "ko",
    ) -> str:
        """Write a Jekyll post file and return the expected blog URL."""
        content = self._build_post_content(title, body_markdown, tags)
        filename = self._build_filename(slug, language)

        if self._use_api:
            self._pending_files.append({
                "path": f"_posts/{filename}",
                "content": content,
            })
            logger.info("Queued post for API publish: %s", filename)
        else:
            if not self._repo_path or not self._repo_path.exists():
                raise PublishError(
                    f"Jekyll repo path does not exist: {self._repo_path}"
                )
            posts_dir = self._repo_path / "_posts"
            posts_dir.mkdir(parents=True, exist_ok=True)
            filepath = posts_dir / filename
            filepath.write_text(content, encoding="utf-8")
            logger.info("Wrote Jekyll post: %s", filepath)

        url = f"{GITHUB_PAGES_URL}/blog/{slug}/"
        return url

    def commit_and_push(self, paths: list[Path], title: str) -> None:
        """Commit and push posts. Uses GitHub API or local git."""
        if self._use_api:
            self._commit_via_api(title)
        else:
            self._commit_via_git(paths, title)

    def _commit_via_api(self, message: str) -> None:
        """Push pending files via GitHub Contents API."""
        if not self._pending_files:
            logger.info("No pending files to publish via API")
            return

        headers = {
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        base_url = f"https://api.github.com/repos/{GITHUB_PAGES_REPO}/contents"

        with httpx.Client(timeout=30) as client:
            for file_info in self._pending_files:
                file_path = file_info["path"]
                content_b64 = base64.b64encode(
                    file_info["content"].encode("utf-8")
                ).decode("ascii")

                # Check if file already exists (to get sha for update)
                sha = None
                resp = client.get(
                    f"{base_url}/{file_path}",
                    headers=headers,
                )
                if resp.status_code == 200:
                    sha = resp.json().get("sha")

                payload: dict = {
                    "message": message,
                    "content": content_b64,
                }
                if sha:
                    payload["sha"] = sha

                resp = client.put(
                    f"{base_url}/{file_path}",
                    headers=headers,
                    json=payload,
                )

                if resp.status_code not in (200, 201):
                    raise PublishError(
                        f"GitHub API error for {file_path}: "
                        f"{resp.status_code} {resp.text}"
                    )
                logger.info("Published via API: %s", file_path)

        self._pending_files.clear()

    def _commit_via_git(self, paths: list[Path], title: str) -> None:
        """Commit and push via local git CLI."""
        repo = str(self._repo_path)

        try:
            for path in paths:
                subprocess.run(
                    ["git", "add", str(path)],
                    cwd=repo,
                    check=True,
                    capture_output=True,
                    text=True,
                )

            subprocess.run(
                ["git", "commit", "-m", title],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )

            subprocess.run(
                ["git", "push"],
                cwd=repo,
                check=True,
                capture_output=True,
                text=True,
            )

            logger.info("Committed and pushed %d file(s)", len(paths))
        except subprocess.CalledProcessError as e:
            raise PublishError(
                f"Git operation failed: {e.stderr or e.stdout}"
            ) from e
