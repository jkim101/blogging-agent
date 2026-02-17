"""Tests for Jekyll (GitHub Pages) publisher.

Tests JekyllPublisher with mocked filesystem and subprocess calls.
"""

from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from core.publisher import JekyllPublisher, PublishError


@pytest.fixture
def jekyll_repo(tmp_path):
    """Create a temporary Jekyll repo directory."""
    posts_dir = tmp_path / "_posts"
    posts_dir.mkdir()
    return tmp_path


@pytest.fixture
def publisher(jekyll_repo):
    return JekyllPublisher(repo_path=str(jekyll_repo))


def test_publish_post_creates_file(publisher, jekyll_repo):
    """publish_post should create a Markdown file in _posts/ with Jekyll frontmatter."""
    url = publisher.publish_post(
        title="Test Post Title",
        body_markdown="# Hello\n\nWorld",
        slug="test-post",
        tags=["python", "ai"],
        language="ko",
    )

    # Should return expected blog URL
    assert url == "https://jkim101.github.io/blog/test-post/"

    # File should exist in _posts/
    posts = list((jekyll_repo / "_posts").glob("*-test-post_ko.md"))
    assert len(posts) == 1

    content = posts[0].read_text()
    assert 'title: "Test Post Title"' in content
    assert "layout: single" in content
    assert "author_profile: true" in content
    assert "read_time: true" in content
    assert "  - python" in content
    assert "  - ai" in content
    assert "categories:" in content
    assert "  - blog" in content
    assert "# Hello" in content
    assert "World" in content


def test_publish_post_english(publisher, jekyll_repo):
    """publish_post should use language suffix in filename."""
    publisher.publish_post(
        title="English Post",
        body_markdown="Content",
        slug="eng-post",
        language="en",
    )

    posts = list((jekyll_repo / "_posts").glob("*-eng-post_en.md"))
    assert len(posts) == 1


def test_publish_post_no_tags(publisher, jekyll_repo):
    """publish_post should handle empty tags."""
    publisher.publish_post(
        title="No Tags",
        body_markdown="Content",
        slug="no-tags",
    )

    posts = list((jekyll_repo / "_posts").glob("*-no-tags_ko.md"))
    assert len(posts) == 1
    content = posts[0].read_text()
    assert "tags:" in content


def test_missing_repo_path_raises_error(tmp_path):
    """Publishing to a non-existent repo should raise PublishError."""
    pub = JekyllPublisher(repo_path=str(tmp_path / "nonexistent"))
    with pytest.raises(PublishError, match="does not exist"):
        pub.publish_post(title="Test", body_markdown="Content", slug="test")


def test_commit_and_push_calls_git(publisher, jekyll_repo):
    """commit_and_push should call git add, commit, and push."""
    test_file = jekyll_repo / "_posts" / "2026-02-14-test_ko.md"
    test_file.write_text("content")

    with patch("core.publisher.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        publisher.commit_and_push(
            paths=[test_file],
            title="Add post: Test",
        )

    assert mock_run.call_count == 3
    # Verify git add, commit, push sequence
    calls = mock_run.call_args_list
    assert calls[0].args[0][0:2] == ["git", "add"]
    assert calls[1].args[0][0:2] == ["git", "commit"]
    assert calls[2].args[0][0:2] == ["git", "push"]


def test_commit_and_push_git_error(publisher, jekyll_repo):
    """Git failure should raise PublishError."""
    import subprocess

    with patch("core.publisher.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(
            1, "git", stderr="error: failed to push"
        )
        with pytest.raises(PublishError, match="Git operation failed"):
            publisher.commit_and_push(
                paths=[jekyll_repo / "_posts" / "test.md"],
                title="Test",
            )
