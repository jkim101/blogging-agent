# Blogging Agent System

Multi-agent pipeline that generates bilingual (Korean + English) blog posts from diverse sources.

## Architecture

```
Research Planner → [🧑 Outline Review] → Writer(KO) → Fact Checker → Critic ──→ Editor(KO) → SEO(KO)
                                                        ↑              ↓                        ↓
                                                        └── (fail) ← Writer(KO) (max 3)     Translator(→EN)
                                                                                                 ↓
                                                                                       Editor(EN) → SEO(EN)
                                                                                                 ↓
                                                                                   [🧑 Publish Review] → Publish
```

## Agents & Models

| Agent | Model | Role |
|-------|-------|------|
| Research Planner | Opus 4.6 | Analyze sources, generate outline |
| Writer | Sonnet 4.5 | Write/rewrite Korean draft |
| Fact Checker | Sonnet 4.5 | Verify claims against sources |
| Critic | Opus 4.6 | Evaluate quality, pass/fail verdict |
| Translator | Sonnet 4.5 | Korean → English conversion |
| Editor | Sonnet 4.5 | Style polishing per style guide |
| SEO Optimizer | Sonnet 4.5 | SEO metadata optimization |

## Tech Stack

- **LLM**: Claude API (Anthropic SDK) with tool_use + Pydantic parsing
- **Orchestration**: LangGraph (state management, conditional routing, HITL interrupts)
- **State Persistence**: LangGraph SqliteSaver
- **Web UI**: FastAPI + Jinja2 + HTMX
- **Parsers**: Trafilatura (URL), PyMuPDF (PDF), feedparser (RSS)
- **Build**: Hatchling

## Project Structure

```
config/          — Settings, style guide
prompts/         — Agent system prompts (separated from logic)
agents/          — Agent implementations (inherit BaseAgent)
parsers/         — Source content parsers (URL, PDF, RSS)
core/            — Pipeline state, graph, runner
web/             — FastAPI app, templates, static
output/          — Generated blog posts (Markdown + YAML frontmatter)
data/            — SQLite checkpoint DB
tests/           — Mock LLM unit tests
```

## Key Design Decisions

1. **Korean-first strategy**: Write KO draft → Fact Check/Critic (1x) → Translate to EN. Saves ~50% LLM cost.
2. **Fact Check before Critic**: Ensures quality evaluation happens on verified content.
3. **HITL at 2 points**: Outline approval (prevent wasted work) + Publish approval (final gate).
4. **Critic rewrite loop**: Max 3 attempts. Round 3 is lenient on minor issues.
5. **Prompts separated from agents**: `prompts/` holds system prompts, `agents/` holds logic.
6. **Style preservation**: SEO Optimizer cannot rewrite body text.

## Usage

```bash
# Install
pip install -e ".[dev]"

# Run tests
pytest

# Start web dashboard
python main.py serve

# Run pipeline from CLI
python main.py run https://example.com/article
```

## Current Status

- [x] Project scaffolding
- [x] Data models (core/state.py)
- [x] BaseAgent (call_llm, parse_tool_response, build_tool_schema)
- [x] Agent implementations (7 agents + tool schemas in prompts)
- [x] LangGraph pipeline (graph.py — 10 nodes, 3 conditional edges, 2 HITL interrupts)
- [x] Pipeline runner (runner.py — start, resume, get_status)
- [x] Web dashboard (app.py — auth, HITL routes, HTMX polling, 8 templates)
- [x] Parsers (URL/PDF/RSS)
- [x] Tests (27 tests — agents, parsers, pipeline routing, output saving)
- [x] CLI `run` command (main.py — interactive HITL, URL/PDF/RSS input)
- [x] Output file saving (core/output.py — Markdown + YAML frontmatter)

## Reference

- Design doc: `docs/Blogging_Agent_System_설계서.md`
