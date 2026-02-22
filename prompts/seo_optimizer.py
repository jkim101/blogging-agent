"""System prompts for the SEO Optimizer agent.

See 설계서 §3.7 for agent specification.
"""

from agents.base_agent import BaseAgent
from core.state import SEOMetadata

SYSTEM_PROMPT = """\
You are an SEO Optimizer for a blogging pipeline. Your role is to:

1. Generate an optimized title (max 60 chars)
2. Write a meta description (max 160 chars)
3. Identify primary and secondary keywords
4. Suggest a URL slug
5. Optimize heading structure for SEO

IMPORTANT: Do NOT rewrite body text. Only optimize metadata and headings.
Preserve the Editor's established style.

Language: {language}

Use the `submit_seo_metadata` tool to return your structured SEO metadata.
Then output the final post with optimized headings as plain text.
{config_section}"""

TOOLS = [
    BaseAgent.build_tool_schema(
        name="submit_seo_metadata",
        description=(
            "Submit SEO metadata. Include: optimized_title, "
            "meta_description, primary_keyword, secondary_keywords list, "
            "and suggested_slug."
        ),
        model_class=SEOMetadata,
    ),
]
