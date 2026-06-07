"""Retrieval metrics against ground-truth qrels (binary relevance).

These answer: did the retriever surface the documents known to answer the query?
NDCG@k is the recommended single scalar for the experiment log; the others
support diagnosis.
"""

import math
from collections.abc import Sequence


def ndcg_at_k(retrieved_doc_ids: Sequence[str], relevant_doc_ids: Sequence[str], k: int) -> float | None:
    relevant = set(relevant_doc_ids)
    if not relevant:
        return None
    dcg = sum(
        1.0 / math.log2(rank + 2)
        for rank, doc_id in enumerate(retrieved_doc_ids[:k])
        if doc_id in relevant
    )
    ideal_hits = min(len(relevant), k)
    idcg = sum(1.0 / math.log2(rank + 2) for rank in range(ideal_hits))
    return dcg / idcg if idcg > 0 else None


def recall_at_k(retrieved_doc_ids: Sequence[str], relevant_doc_ids: Sequence[str], k: int) -> float | None:
    relevant = set(relevant_doc_ids)
    if not relevant:
        return None
    hits = relevant.intersection(retrieved_doc_ids[:k])
    return len(hits) / len(relevant)


def precision_at_k(retrieved_doc_ids: Sequence[str], relevant_doc_ids: Sequence[str], k: int) -> float | None:
    relevant = set(relevant_doc_ids)
    if not relevant:
        return None
    top = list(retrieved_doc_ids[:k])
    if not top:
        return 0.0
    hits = sum(1 for doc_id in top if doc_id in relevant)
    return hits / len(top)


def mrr(retrieved_doc_ids: Sequence[str], relevant_doc_ids: Sequence[str]) -> float | None:
    relevant = set(relevant_doc_ids)
    if not relevant:
        return None
    for rank, doc_id in enumerate(retrieved_doc_ids, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0
