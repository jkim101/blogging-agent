"""System prompts for the Critic agent.

See 설계서 §3.4 for agent specification.
"""

from agents.base_agent import BaseAgent
from core.state import CriticFeedback

SYSTEM_PROMPT = """\
You are a Critic for a blogging pipeline. Your role is to:

1. Evaluate the Korean draft on logic, structure, depth, and clarity
2. Consider the fact-check results in your evaluation
3. Score the draft from 1-10
4. Issue a verdict using these exact criteria:
   - PASS: score >= 7 AND zero high-severity fact issues
   - FAIL: score < 7 OR one or more high-severity fact issues

Provide specific, actionable feedback including:
- Strengths to preserve
- Weaknesses to address
- Concrete rewrite instructions if FAIL

Current rewrite round: {rewrite_count}/3

Use the `submit_evaluation` tool to return your structured evaluation.
"""

SYSTEM_PROMPT_LENIENT = """\

IMPORTANT: This is the final rewrite attempt (round 3/3). Be lenient on minor issues.
Only FAIL if score < 5 OR the post structure is unintelligible OR there are high-severity fact errors.
"""

TOOLS = [
    BaseAgent.build_tool_schema(
        name="submit_evaluation",
        description=(
            "Submit critic evaluation. Include: verdict (pass/fail), "
            "score (1-10), strengths list, weaknesses list, "
            "specific_feedback, and rewrite_instructions (if fail)."
        ),
        model_class=CriticFeedback,
    ),
]
