"""Application settings loaded from environment variables."""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
STYLE_GUIDE_PATH = PROJECT_ROOT / "config" / "style_guide.yaml"
OUTPUT_DIR = PROJECT_ROOT / "output"

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
JEKYLL_REPO_PATH = os.getenv("JEKYLL_REPO_PATH", str(Path.home() / "antigravity" / "jkim101.github.io"))
GITHUB_PAGES_URL = "https://jkim101.github.io"

# Dashboard
DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "change-me")

# Pipeline
MAX_REWRITE_ATTEMPTS = int(os.getenv("MAX_REWRITE_ATTEMPTS", "3"))

# Database
SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "data/pipeline.db")

# Model Configuration
OPUS_MODEL = "claude-opus-4-6"
SONNET_MODEL = "claude-sonnet-4-5-20250929"

# Agent → Model mapping
AGENT_MODELS = {
    "research_planner": OPUS_MODEL,
    "writer": SONNET_MODEL,
    "fact_checker": SONNET_MODEL,
    "critic": OPUS_MODEL,
    "translator": SONNET_MODEL,
    "editor": SONNET_MODEL,
    "seo_optimizer": SONNET_MODEL,
}
