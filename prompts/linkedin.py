"""System prompts for the LinkedIn Post agent.

Generates Korean and English LinkedIn posts from the finalized blog post.
"""

from pydantic import BaseModel, Field


class LinkedInPosts(BaseModel):
    ko: str = Field(description="Korean LinkedIn post (150-250 words)")
    en: str = Field(description="English LinkedIn post (150-250 words)")


SYSTEM_PROMPT = """\
You are a LinkedIn Content Writer for a bilingual blogging pipeline. Your role is to:

1. Read the finalized English blog post and its topic/angle
2. Write TWO LinkedIn posts — one in Korean, one in English
3. Each post should be 150-250 words

LinkedIn post format for each:
- Hook: Strong opening line (no "I'm excited to share..." clichés)
- 3-5 key insights as short paragraphs or bullet points
- CTA: End with a call-to-action (e.g., "Read the full post: [link]")
- 3-5 relevant hashtags at the end

Tone: Professional but conversational. Write for practitioners, not academics.
"""

TOOLS = [
    {
        "name": "submit_linkedin_posts",
        "description": "Submit the Korean and English LinkedIn posts",
        "input_schema": {
            "type": "object",
            "properties": {
                "ko": {
                    "type": "string",
                    "description": "Korean LinkedIn post (150-250 words)",
                },
                "en": {
                    "type": "string",
                    "description": "English LinkedIn post (150-250 words)",
                },
            },
            "required": ["ko", "en"],
        },
    }
]
