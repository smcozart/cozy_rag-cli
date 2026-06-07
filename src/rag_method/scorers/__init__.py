"""Deterministic scorers. Cheap, reproducible, no LLM-judge required.

These follow the canonical pattern from cozy_RAG's four scorers: structural
(citation_accuracy, completeness), content (groundedness), metadata (recency).
Retrieval metrics (ndcg/recall/precision/mrr) score the retriever against qrels.

Custom domain scorers should follow the same shape:
    score(answer, retrieved, item) -> float | None
None means "not applicable for this item" and is excluded from aggregation.
"""

from rag_method.scorers.citation import citation_accuracy
from rag_method.scorers.completeness import completeness
from rag_method.scorers.groundedness import groundedness
from rag_method.scorers.recency import recency
from rag_method.scorers.retrieval import mrr, ndcg_at_k, precision_at_k, recall_at_k

__all__ = [
    "citation_accuracy",
    "completeness",
    "groundedness",
    "mrr",
    "ndcg_at_k",
    "precision_at_k",
    "recall_at_k",
    "recency",
]
