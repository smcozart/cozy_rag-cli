"""Completeness: structural response-format validation.

Completeness is a proxy for effort — a system that cuts corners skips
sections. The weighted checklist mirrors the canonical cozy_RAG scorer:
summary (0.20), findings with >=1 citation (0.40), document-currency note
with a date (0.20), limitations (0.10), minimum length (0.10).

Tune the section patterns to your own response contract; the shape
(deterministic weighted checklist) is the part to keep.
"""

import re

from rag_method.contract import Answer

_MIN_LENGTH_CHARS = 200

_SUMMARY = re.compile(r"(?im)^(#+\s*summary|\*\*summary)")
_FINDINGS = re.compile(r"(?im)^(#+\s*(findings|answer|details)|\*\*(findings|answer|details))")
_CURRENCY = re.compile(r"(?im)^(#+\s*(document\s+currency|currency|freshness)|\*\*(document\s+currency|currency|freshness))")
_LIMITATIONS = re.compile(r"(?im)^(#+\s*limitations|\*\*limitations)")
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b(19|20)\d{2}\b")


def completeness(answer: Answer) -> float | None:
    if answer.refused:
        return None
    text = answer.text
    score = 0.0
    if _SUMMARY.search(text):
        score += 0.20
    if _FINDINGS.search(text) and answer.citations:
        score += 0.40
    if _CURRENCY.search(text) and _DATE.search(text):
        score += 0.20
    if _LIMITATIONS.search(text):
        score += 0.10
    if len(text) >= _MIN_LENGTH_CHARS:
        score += 0.10
    return score
