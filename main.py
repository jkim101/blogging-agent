"""CLI entry point for the blogging agent pipeline.

Usage:
    python main.py serve                                        # Start web dashboard
    python main.py run <url> [url2] ...                         # Run pipeline with URLs
    python main.py run --pdf <file.pdf>                         # Run pipeline with a PDF
    python main.py run https://www.youtube.com/watch?v=VIDEO_ID # Run with YouTube video
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


def run_pipeline(args: list[str]) -> None:
    """Parse sources from CLI args and run the pipeline interactively."""
    from core.runner import PipelineRunner
    from core.state import HumanDecision, SourceContent
    from parsers.url_parser import parse_url
    from parsers.pdf_parser import parse_pdf
    from parsers.youtube_parser import is_youtube_url, parse_youtube

    sources: list[SourceContent] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--pdf":
            i += 1
            if i >= len(args):
                print("Error: --pdf requires a file path")
                sys.exit(1)
            path = Path(args[i])
            print(f"Parsing PDF: {path}")
            sources.append(parse_pdf(path))
        elif is_youtube_url(arg):
            print(f"Parsing YouTube: {arg}")
            sources.append(parse_youtube(arg))
        else:
            print(f"Parsing URL: {arg}")
            sources.append(parse_url(arg))
        i += 1

    if not sources:
        print("Error: no valid sources provided")
        sys.exit(1)

    print(f"\nParsed {len(sources)} source(s). Starting pipeline...\n")

    runner = PipelineRunner()
    thread_id = runner.start(sources)

    # Interactive HITL loop
    while True:
        status = runner.get_status(thread_id)

        if not status["is_interrupted"]:
            print("\nPipeline completed!")
            state = runner.get_state(thread_id)
            _print_results(state)
            break

        state = runner.get_state(thread_id)

        if status["next_node"] == "outline_review":
            human_input = _review_outline(state)
        elif status["next_node"] == "publish_review":
            human_input = _review_publish(state)
        else:
            print(f"Unexpected interrupt at: {status['next_node']}")
            break

        if human_input.get("outline_decision") == HumanDecision.REJECT or \
           human_input.get("publish_decision") == HumanDecision.REJECT:
            print("\nPipeline rejected. Exiting.")
            runner.resume(thread_id, human_input)
            break

        print("\nResuming pipeline...\n")
        runner.resume(thread_id, human_input)


def _review_outline(state: dict) -> dict:
    """Interactive outline review in terminal."""
    from core.state import HumanDecision

    outline = state["outline"]
    print("=" * 60)
    print("OUTLINE REVIEW")
    print("=" * 60)
    print(f"Topic: {outline.topic}")
    print(f"Angle: {outline.angle}")
    print(f"Target Audience: {outline.target_audience}")
    print(f"Estimated Words: {outline.estimated_word_count}")
    print()
    print("Key Points:")
    for kp in outline.key_points:
        print(f"  - {kp}")
    print()
    print("Structure:")
    for section in outline.structure:
        print(f"  ## {section.heading}")
        for kp in section.key_points:
            print(f"     - {kp}")
    print()

    while True:
        choice = input("[A]pprove / [E]dit (with notes) / [R]eject? ").strip().lower()
        if choice in ("a", "approve"):
            return {"outline_decision": HumanDecision.APPROVE, "outline_human_notes": ""}
        elif choice in ("e", "edit"):
            notes = input("Notes for the Writer: ").strip()
            return {"outline_decision": HumanDecision.EDIT, "outline_human_notes": notes}
        elif choice in ("r", "reject"):
            return {"outline_decision": HumanDecision.REJECT, "outline_human_notes": ""}
        print("Invalid choice. Enter A, E, or R.")


def _review_publish(state: dict) -> dict:
    """Interactive publish review in terminal."""
    from core.state import HumanDecision, PublishTarget

    print("=" * 60)
    print("PUBLISH REVIEW")
    print("=" * 60)

    if state.get("critic_feedback"):
        fb = state["critic_feedback"]
        print(f"Critic Score: {fb.score}/10 ({fb.verdict.value.upper()})")
    if state.get("fact_check"):
        fc = state["fact_check"]
        print(f"Fact Check: {fc.claims_checked} claims, accuracy {fc.overall_accuracy:.0%}")
    print(f"Rewrites: {state.get('rewrite_count', 0)}")
    print()

    # Show Korean preview
    ko = state.get("final_post_ko") or state.get("edited_draft_ko") or ""
    if ko:
        print("--- Korean Post (first 500 chars) ---")
        print(ko[:500])
        print("...\n" if len(ko) > 500 else "\n")

    # Show English preview
    en = state.get("final_post_en") or state.get("edited_draft_en") or ""
    if en:
        print("--- English Post (first 500 chars) ---")
        print(en[:500])
        print("...\n" if len(en) > 500 else "\n")

    while True:
        choice = input("[P]ublish / [R]eject? ").strip().lower()
        if choice in ("p", "publish"):
            # Ask about GitHub Pages publishing for each language
            publish_targets = []
            if ko:
                ko_choice = input("Publish Korean to GitHub Pages? [Y/n] ").strip().lower()
                publish_targets.append(
                    PublishTarget(language="ko", platform="github_pages", publish=ko_choice != "n")
                )
            if en:
                en_choice = input("Publish English to GitHub Pages? [Y/n] ").strip().lower()
                publish_targets.append(
                    PublishTarget(language="en", platform="github_pages", publish=en_choice != "n")
                )
            return {
                "publish_decision": HumanDecision.APPROVE,
                "publish_targets": publish_targets,
            }
        elif choice in ("r", "reject"):
            return {"publish_decision": HumanDecision.REJECT}
        print("Invalid choice. Enter P or R.")


def _print_results(state: dict) -> None:
    """Print final results summary and save output files."""
    from core.output import save_posts

    saved = save_posts(state)
    if saved:
        print("\nSaved files:")
        for path in saved:
            print(f"  {path}")

    if state.get("seo_metadata_ko"):
        seo = state["seo_metadata_ko"]
        print(f"\nTitle (KO): {seo.optimized_title}")
        print(f"Slug: {seo.suggested_slug}")
    if state.get("seo_metadata_en"):
        seo = state["seo_metadata_en"]
        print(f"Title (EN): {seo.optimized_title}")
    if state.get("final_post_ko"):
        print(f"Korean post: {len(state['final_post_ko'])} chars")
    if state.get("final_post_en"):
        print(f"English post: {len(state['final_post_en'])} chars")


def main() -> None:
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python main.py serve                                        # Start web dashboard")
        print("  python main.py run <url> [url2] ...                         # Run pipeline with URLs")
        print("  python main.py run --pdf <file.pdf>                         # Run pipeline with PDF")
        print("  python main.py run https://www.youtube.com/watch?v=VIDEO_ID # YouTube video")
        sys.exit(1)

    command = sys.argv[1]

    if command == "serve":
        import uvicorn
        uvicorn.run("web.app:app", host="0.0.0.0", port=8000, reload=True)
    elif command == "run":
        if len(sys.argv) < 3:
            print("Error: provide at least one source (URL or --pdf <path>)")
            sys.exit(1)
        run_pipeline(sys.argv[2:])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
