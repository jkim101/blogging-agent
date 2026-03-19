# Blogging Agent

Multi-agent pipeline that generates bilingual (Korean + English) blog posts from diverse sources.

## Architecture

```
Research Planner → [Outline Review] → Writer(KO) → Fact Checker → Critic ──→ Editor(KO) → SEO(KO)
                                                     ↑              ↓                        ↓
                                                     └── (fail) ← Writer(KO) (max 3)     Translator(→EN)
                                                                                              ↓
                                                                                    Editor(EN) → SEO(EN)
                                                                                              ↓
                                                                                [Publish Review] → Publish
```

7 specialized agents collaborate through a LangGraph pipeline with human-in-the-loop review at two checkpoints (outline approval and publish approval).

## Agents

| Agent | Model | Role |
|-------|-------|------|
| Research Planner | Claude Opus 4.6 | Analyze sources, generate outline |
| Writer | Claude Sonnet 4.5 | Write/rewrite Korean draft |
| Fact Checker | Claude Sonnet 4.5 | Verify claims against sources |
| Critic | Claude Opus 4.6 | Evaluate quality, pass/fail verdict |
| Translator | Claude Sonnet 4.5 | Korean → English conversion |
| Editor | Claude Sonnet 4.5 | Style polishing per style guide |
| SEO Optimizer | Claude Sonnet 4.5 | SEO metadata optimization |

## Tech Stack

- **LLM**: Claude API (Anthropic SDK) with tool_use + Pydantic parsing
- **Orchestration**: LangGraph (state management, conditional routing, HITL interrupts)
- **State Persistence**: LangGraph SqliteSaver
- **Web UI**: FastAPI + Jinja2 + HTMX
- **Parsers**: Trafilatura (URL), PyMuPDF (PDF), YouTube transcript
- **Build**: Hatchling
- **Deployment**: Docker + Railway

## Getting Started

### Install

```bash
pip install -e ".[dev]"
```

### Set environment variables

```bash
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY
```

### Run tests

```bash
pytest
```

### Start web dashboard

```bash
python main.py serve
```

### Run pipeline from CLI

```bash
# From URL
python main.py run https://example.com/article

# From PDF
python main.py run --pdf document.pdf

# From YouTube
python main.py run https://www.youtube.com/watch?v=VIDEO_ID

# Quick mode (skip config prompts, use defaults)
python main.py run --quick https://example.com/article
```

### Publish output to GitHub Pages

```bash
python main.py publish output/my-post-ko.md output/my-post-en.md
```

## Project Structure

```
config/          — Settings, style guide
prompts/         — Agent system prompts (separated from logic)
agents/          — Agent implementations (inherit BaseAgent)
parsers/         — Source content parsers (URL, PDF, YouTube)
core/            — Pipeline state, graph, runner
web/             — FastAPI app, templates, static
output/          — Generated blog posts (Markdown + YAML frontmatter)
data/            — SQLite checkpoint DB
tests/           — Unit tests
```

## Design Decisions

1. **Korean-first strategy**: Write KO draft → Fact Check/Critic → Translate to EN. Saves ~50% LLM cost.
2. **Fact Check before Critic**: Quality evaluation happens on verified content.
3. **HITL at 2 points**: Outline approval (prevent wasted work) + Publish approval (final gate).
4. **Critic rewrite loop**: Max 3 attempts. Round 3 is lenient on minor issues.
5. **Prompts separated from agents**: `prompts/` holds system prompts, `agents/` holds logic.
6. **Style preservation**: SEO Optimizer cannot rewrite body text.

## Deployment

### Railway

The project includes a `Dockerfile` and `railway.toml` for Railway deployment.

Required environment variables:

| Variable | Description |
|----------|-------------|
| `ANTHROPIC_API_KEY` | Claude API key |
| `DASHBOARD_PASSWORD` | Web dashboard login password |
| `SESSION_SECRET` | Session encryption key (random string) |

## License

Private
