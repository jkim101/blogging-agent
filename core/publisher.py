"""Jekyll (GitHub Pages) publishing client.

Publishes blog posts to a Jekyll site by writing Markdown files with
frontmatter to the _posts/ directory, then committing and pushing to GitHub.
See 설계서 §12.2 for publishing specification.
"""

from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config.settings import GITHUB_PAGES_URL, JEKYLL_REPO_PATH

logger = logging.getLogger(__name__)


class PublishError(Exception):
    """Raised when Jekyll publishing fails."""


class JekyllPublisher:
    """Publishes posts to a Jekyll GitHub Pages site."""

    def __init__(self, repo_path: str = "") -> None:
        self._repo_path = Path(repo_path or JEKYLL_REPO_PATH)

    def publish_post(
        self,
        title: str,
        body_markdown: str,
        slug: str,
        tags: list[str] | None = None,
        language: str = "ko",
    ) -> str:
        """Write a Jekyll post file and return the expected blog URL.

        Args:
            title: Post title.
            body_markdown: Post body in Markdown format.
            slug: URL-friendly slug for the post.
            tags: Tags for the post (from SEO keywords).
            language: Language code ("ko" or "en").

        Returns:
            The expected GitHub Pages URL for the post.
        """
        if not self._repo_path or not self._repo_path.exists():
            raise PublishError(
                f"Jekyll repo path does not exist: {self._repo_path}"
            )

        posts_dir = self._repo_path / "_posts"
        posts_dir.mkdir(parents=True, exist_ok=True)

        now = datetime.now(ZoneInfo("US/Eastern"))
        date_str = now.strftime("%Y-%m-%d")
        datetime_str = now.strftime("%Y-%m-%d %H:%M:%S %z")

        filename = f"{date_str}-{slug}_{language}.md"
        filepath = posts_dir / filename

        # Build Jekyll frontmatter
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

        content = frontmatter + "\n\n" + body_markdown
        filepath.write_text(content, encoding="utf-8")
        logger.info("Wrote Jekyll post: %s", filepath)

        url = f"{GITHUB_PAGES_URL}/blog/{slug}/"
        return url

    def commit_and_push(self, paths: list[Path], title: str) -> None:
        """Git add, commit, and push the given files.

        Args:
            paths: File paths to stage.
            title: Commit message.
        """
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
