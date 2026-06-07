"""Citation accuracy: structural + referential validity.

Citation is the contract between system and user. A citation must be
well-formed (non-empty title) AND resolve to a document that was actually
retrieved (fuzzy title match). A perfect answer with unverifiable citations
scores zero on this axis.
"""

from collections.abc import Sequence
from difflib import SequenceMatcher

from rag_method.contract import Answer, ScoredChunk

_MATCH_THRESHOLD = 0.8


def _title_matches(citation_title: str, retrieved_titles: Sequence[str]) -> bool:
    needle = citation_title.lower().strip()
    for title in retrieved_titles:
        candidate = title.lower().strip()
        if not candidate:
            continue
        if needle in candidate or candidate in needle:
            return True
        if SequenceMatcher(None, needle, candidate).ratio() >= _MATCH_THRESHOLD:
            return True
    return False


def citation_accuracy(answer: Answer, retrieved: Sequence[ScoredChunk]) -> float | None:
    if answer.refused:
        return None
    if not answer.citations:
        return 0.0
    retrieved_titles = [chunk.title for chunk in retrieved]
    valid = sum(
        1
        for citation in answer.citations
        if citation.title.strip() and _title_matches(citation.title, retrieved_titles)
    )
    return valid / len(answer.citations)
