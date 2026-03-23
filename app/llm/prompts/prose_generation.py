"""GraphIQ — Prose Generation Prompt.

Grounding rules ensure the LLM describes only what the data shows.
"""
from __future__ import annotations

_PROSE_SYSTEM = """\
You present O2C (Order-to-Cash) data findings in clear, concise business language.
You are given the user's original question and the query results summary.

RULES:
- Only describe what the data shows. Do NOT speculate or infer beyond the data.
- If the result set is empty, say "No matching records found" and suggest possible reasons.
- Cite specific numbers, dates, and document IDs from the data.
- Keep the response under 200 words unless the data requires more detail.
- For flow traces, describe the chain step by step with key values at each node.
- If results were truncated, mention: "Showing first N results."
- Never say "It seems like..." or "Based on my analysis..." — assert what the data shows.
- Professional and analytical tone. No filler phrases.
"""


def build_prose_prompt(question: str, prose_context: str) -> str:
    """Build the prose generation prompt.

    Args:
        question: Original user question.
        prose_context: Compact summary from the handler's shape_result().

    Returns:
        Full prompt string for prose generation.
    """
    return (
        _PROSE_SYSTEM
        + f"\n\nUser question: {question}\n\n"
        + f"Query results:\n{prose_context}\n\n"
        + "Write a concise, professional answer describing what the data shows:"
    )
