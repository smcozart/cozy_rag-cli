"""Recency: metadata-driven staleness detection.

Recency is a metadata game: it only works if the index carries
`effective_date` and `superseded_by` per document — which is why the
methodology pushes domain semantics into the schema layer (Phase 1).

Scoring mirrors the canonical cozy_RAG scorer:
- base 1.0, minus 0.2 per superseded document in the retrieved set
- no dated documents retrieved -> 0.5 (neutral: cannot judge)
"""

from collections.abc import Sequence

from rag_method.contract import ScoredChunk

_PENALTY_PER_SUPERSEDED = 0.2


def recency(retrieved: Sequence[ScoredChunk]) -> float | None:
    if not retrieved:
        return None
    dated = [chunk for chunk in retrieved if chunk.metadata.get("effective_date")]
    if not dated:
        return 0.5
    superseded = sum(1 for chunk in retrieved if chunk.metadata.get("superseded_by"))
    return max(0.0, 1.0 - _PENALTY_PER_SUPERSEDED * superseded)
