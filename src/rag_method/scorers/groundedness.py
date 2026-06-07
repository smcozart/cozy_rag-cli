"""Groundedness: are claims supported by what was ACTUALLY retrieved?

Stricter than generic faithfulness: this pins responsibility to the retrieval
set, not to "supported in principle." Refusal behavior is scored here too:
- refused when the item demands refusal      -> 1.0 (correct refusal)
- refused when the corpus could answer        -> 0.0 (over-refusal)
- answered when the item demands refusal      -> 0.0 (absence-blindness)
- answered with no citations                  -> 0.0 (silent hallucination)
- otherwise: fraction of citations resolving to retrieved documents
"""

from collections.abc import Sequence

from rag_method.contract import Answer, ScoredChunk
from rag_method.scorers.citation import _title_matches


def groundedness(
    answer: Answer, retrieved: Sequence[ScoredChunk], must_refuse: bool
) -> float:
    if answer.refused:
        return 1.0 if must_refuse else 0.0
    if must_refuse:
        return 0.0
    if not answer.citations:
        return 0.0
    retrieved_titles = [chunk.title for chunk in retrieved]
    grounded = sum(
        1 for citation in answer.citations if _title_matches(citation.title, retrieved_titles)
    )
    return grounded / len(answer.citations)
