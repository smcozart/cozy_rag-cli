"""The eval runner: one dataset + one backend (+ optional generator) -> one run record.

A run is the unit of comparison in the methodology. Runs are keyed by the
backend's immutable config version, so "config A vs config B" is always
"run on version A vs run on version B" — which is what makes A/B testing
and reversion mechanical.

Dataset format (JSONL, one item per line):
    {"id": "q-001", "question": "...", "reference_answer": "...",
     "relevant_doc_ids": ["d1", "d2"], "tags": ["mode:scattered-evidence"],
     "must_refuse": false}
"""

import json
import statistics
import time
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rag_method.contract import Backend, Generate, ScoredChunk
from rag_method.scorers import (
    citation_accuracy,
    completeness,
    groundedness,
    mrr,
    ndcg_at_k,
    precision_at_k,
    recall_at_k,
    recency,
)


def _load_dataset(path: Path) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _score_item(
    item: Mapping[str, Any],
    backend: Backend,
    generate: Generate | None,
    k: int,
) -> dict[str, Any]:
    question: str = item["question"]
    relevant: list[str] = item.get("relevant_doc_ids", [])
    must_refuse: bool = item.get("must_refuse", False)

    retrieved: list[ScoredChunk] = []
    metrics: dict[str, float | None] = {}
    started = time.perf_counter()

    if backend.supports_retrieval:
        retrieved = backend.retrieve(question, k=k)
        retrieved_ids = [chunk.doc_id for chunk in retrieved]
        metrics[f"ndcg@{k}"] = ndcg_at_k(retrieved_ids, relevant, k)
        metrics[f"recall@{k}"] = recall_at_k(retrieved_ids, relevant, k)
        metrics[f"precision@{k}"] = precision_at_k(retrieved_ids, relevant, k)
        metrics["mrr"] = mrr(retrieved_ids, relevant)

    if generate is not None:
        answer = generate(question, retrieved)
        metrics["completeness"] = completeness(answer)
        metrics["refusal_correct"] = 1.0 if answer.refused == must_refuse else 0.0
        if backend.supports_retrieval:
            # These compare the answer against the retrieval set; for opaque
            # backends that set is invisible, so per the degradation rule the
            # metrics are absent (diagnosis degraded), not zero.
            metrics["groundedness"] = groundedness(answer, retrieved, must_refuse)
            metrics["citation_accuracy"] = citation_accuracy(answer, retrieved)
            metrics["recency"] = recency(retrieved)

    return {
        "id": item.get("id", question[:40]),
        "tags": item.get("tags", []),
        "must_refuse": must_refuse,
        "retrieved_doc_ids": [chunk.doc_id for chunk in retrieved],
        "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        "metrics": metrics,
    }


def _aggregate(per_question: Iterable[Mapping[str, Any]]) -> dict[str, float]:
    buckets: dict[str, list[float]] = {}
    for record in per_question:
        for name, value in record["metrics"].items():
            if value is not None:
                buckets.setdefault(name, []).append(value)
    return {name: round(statistics.mean(values), 4) for name, values in buckets.items()}


def _aggregate_by_tag(per_question: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    tags = {tag for record in per_question for tag in record["tags"]}
    return {
        tag: _aggregate([r for r in per_question if tag in r["tags"]])
        for tag in sorted(tags)
    }


def run_eval(
    dataset_path: str | Path | Sequence[str | Path],
    backend: Backend,
    generate: Generate | None = None,
    k: int = 10,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Run one or more datasets against a backend. Returns the run record.

    The record is self-describing: it pins the config version, dataset(s), and
    k, so any two runs are comparable (or visibly not comparable). Passing all
    datasets (golden + adversarial + unanswerable) in one call produces one
    gateable run; tags keep the per-set breakdowns.
    """
    if isinstance(dataset_path, (str, Path)):
        paths = [Path(dataset_path)]
    else:
        paths = [Path(p) for p in dataset_path]
    items = [item for path in paths for item in _load_dataset(path)]
    per_question = [_score_item(item, backend, generate, k) for item in items]
    config_version = backend.version()
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    # Latency is observability for the latency-vs-depth failure mode; it stays
    # out of `metrics` because gate semantics are higher-is-better.
    latencies = sorted(record["latency_ms"] for record in per_question)
    latency_summary = {
        "mean_ms": round(statistics.mean(latencies), 1) if latencies else None,
        "p95_ms": latencies[max(0, int(0.95 * (len(latencies) - 1)))] if latencies else None,
    }
    return {
        "run_id": run_id or f"{config_version}-{timestamp}",
        "config_version": config_version,
        "dataset": "+".join(path.name for path in paths),
        "k": k,
        "timestamp": timestamp,
        "question_count": len(items),
        "latency": latency_summary,
        "aggregate": _aggregate(per_question),
        "by_tag": _aggregate_by_tag(per_question),
        "per_question": per_question,
    }


def save_run(run: Mapping[str, Any], runs_dir: str | Path) -> Path:
    directory = Path(runs_dir)
    directory.mkdir(parents=True, exist_ok=True)
    safe_id = str(run["run_id"]).replace(":", "-").replace("+", "")
    out_path = directory / f"{safe_id}.json"
    out_path.write_text(json.dumps(run, indent=2), encoding="utf-8")
    return out_path
