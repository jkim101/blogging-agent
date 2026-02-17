Run the blogging agent pipeline.

1. Ask for source URLs, PDF paths, or RSS feed URLs
2. Parse sources using parsers/ modules
3. Execute the LangGraph pipeline via `python main.py run <sources>`
4. Monitor progress and handle HITL checkpoints

If the web dashboard is preferred, start with `python main.py serve` instead.
