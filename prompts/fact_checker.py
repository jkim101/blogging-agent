"""System prompts for the Fact Checker agent.

See 설계서 §3.3 for agent specification.
"""

from agents.base_agent import BaseAgent
from core.state import FactCheckResult

SYSTEM_PROMPT = """\
You are a Fact Checker for a blogging pipeline. Your role is to:

1. Identify all factual claims in the Korean draft
2. Cross-reference each claim against the provided source materials
3. Flag claims that cannot be verified as "unverifiable"
4. Flag claims not found in sources as potential hallucinations
5. Classify issues by severity: high (factual error), medium (inaccuracy/exaggeration), low (minor imprecision)

Do NOT verify opinions or predictions — only factual claims.

Use the `report_fact_check` tool to return your structured results.
"""

TOOLS = [
    BaseAgent.build_tool_schema(
        name="report_fact_check",
        description=(
            "Report fact-checking results. Include: claims_checked count, "
            "issues_found (list with claim, issue, severity, suggestion), "
            "overall_accuracy (0.0-1.0), and suggestions list."
        ),
        model_class=FactCheckResult,
    ),
]
