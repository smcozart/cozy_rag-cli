"""End-to-end smoke test: the whole loop on the reference backend.

Proves: apply -> immutable version, retrieve -> scored chunks, eval run ->
metrics, gates -> verdict, diff -> A/B comparison, swap -> reversion.
"""

import json
from collections.abc import Sequence
from pathlib import Path

import pytest

from rag_method import diff_runs, evaluate_gates, run_eval, save_run
from rag_method.adapters import OpaqueBackend, ReferenceBackend
from rag_method.contract import Answer, Citation, ScoredChunk

CORPUS = [
    {
        "id": "d1",
        "title": "Emergency Fund Guide",
        "text": "An emergency fund should be parked in a high-yield savings account "
        "or money market fund for liquidity and safety.",
        "metadata": {"effective_date": "2025-06-01"},
    },
    {
        "id": "d2",
        "title": "Business Expense Policy",
        "text": "A business expense on a business trip includes airfare, lodging, "
        "and meals required for the trip.",
        "metadata": {"effective_date": "2024-01-15", "superseded_by": "d3"},
    },
    {
        "id": "d3",
        "title": "Business Expense Policy v2",
        "text": "Updated policy: business expenses on a business trip include airfare, "
        "lodging, meals, and ground transportation.",
        "metadata": {"effective_date": "2026-02-01"},
    },
]

DATASET = [
    {
        "id": "q-1",
        "question": "Where should I park my emergency fund?",
        "reference_answer": "High-yield savings or money market.",
        "relevant_doc_ids": ["d1"],
        "tags": ["topic:savings"],
        "must_refuse": False,
    },
    {
        "id": "q-2",
        "question": "What counts as a business expense on a business trip?",
        "reference_answer": "Airfare, lodging, meals, ground transportation.",
        "relevant_doc_ids": ["d3"],
        "tags": ["topic:expenses"],
        "must_refuse": False,
    },
    {
        "id": "q-3",
        "question": "What is the corporate dress code in Antarctica offices?",
        "reference_answer": "The system must refuse.",
        "relevant_doc_ids": [],
        "tags": ["behavior:refusal"],
        "must_refuse": True,
    },
]


@pytest.fixture()
def project(tmp_path: Path) -> dict[str, Path]:
    corpus_path = tmp_path / "corpus.jsonl"
    corpus_path.write_text(
        "\n".join(json.dumps(doc) for doc in CORPUS), encoding="utf-8"
    )
    dataset_path = tmp_path / "golden.jsonl"
    dataset_path.write_text(
        "\n".join(json.dumps(item) for item in DATASET), encoding="utf-8"
    )
    return {"root": tmp_path, "corpus": corpus_path, "dataset": dataset_path}


def naive_generate(query: str, chunks: Sequence[ScoredChunk]) -> Answer:
    """Toy answer layer: cite the top chunk, refuse when nothing retrieved."""
    if not chunks:
        return Answer(text="I can't answer that from the knowledge base.", refused=True)
    top = chunks[0]
    text = (
        "## Summary\n"
        f"Based on {top.title}.\n\n"
        "## Findings\n"
        f"{top.text}\n\n"
        "## Document Currency\n"
        f"Effective {top.metadata.get('effective_date', 'unknown')} (2026 review).\n\n"
        "## Limitations\nAnswered from the top retrieved document only."
    )
    return Answer(text=text, citations=(Citation(title=top.title),))


def test_full_loop(project: dict[str, Path]) -> None:
    backend = ReferenceBackend(project["root"] / "serving")
    spec_a = {"corpus_path": str(project["corpus"]), "name": "smoke", "variant": "A"}
    version_a = backend.apply(spec_a, env="dev")
    assert backend.version() == version_a

    chunks = backend.retrieve("emergency fund", k=5)
    assert chunks and chunks[0].doc_id == "d1"

    run_a = run_eval(project["dataset"], backend, generate=naive_generate, k=5)
    aggregate = run_a["aggregate"]
    assert aggregate["ndcg@5"] > 0.5
    assert aggregate["recall@5"] > 0.5
    assert aggregate["refusal_correct"] == 1.0
    assert aggregate["groundedness"] == 1.0
    assert aggregate["citation_accuracy"] == 1.0
    assert "topic:savings" in run_a["by_tag"]

    out_path = save_run(run_a, project["root"] / "runs")
    assert out_path.exists()

    gates = {
        "metrics": {
            "groundedness": {"threshold": 0.95, "severity": "hard_block"},
            "ndcg@5": {"threshold": 0.99, "severity": "advisory"},
        },
        "regression": {"groundedness": {"max_drop": 0.0, "severity": "hard_block"}},
    }
    report = evaluate_gates(gates, run_a, baseline=run_a)
    assert report["passed"]

    # A/B: config B (one variable changed) -> new immutable version
    spec_b = {**spec_a, "variant": "B"}
    version_b = backend.apply(spec_b, env="dev")
    assert version_b != version_a
    run_b = run_eval(project["dataset"], backend, generate=naive_generate, k=5)
    comparison = diff_runs(run_a, run_b)
    assert comparison["comparable"]
    assert comparison["before_version"] == version_a

    # Built-in reversion: swap back to A in one call
    backend.swap(version_a)
    assert backend.version() == version_a
    assert set(backend.list_versions()) == {version_a, version_b}


def test_opaque_backend_degrades_diagnosis_not_measurement(project: dict[str, Path]) -> None:
    def managed_answer(query: str) -> Answer:
        if "Antarctica" in query:
            return Answer(text="I can't answer that.", refused=True)
        return Answer(
            text="## Summary\nManaged answer.\n## Findings\nDetails here.",
            citations=(Citation(title="Emergency Fund Guide"),),
        )

    backend = OpaqueBackend(managed_answer, config={"model": "claude", "prompt": "v1"})
    run = run_eval(project["dataset"], backend, generate=backend.as_generator(), k=5)

    # Measurement layer intact: refusal behavior is still scored...
    assert run["aggregate"]["refusal_correct"] == 1.0
    # ...diagnosis layer degraded: retrieval-relative metrics are absent
    # (not zero) because the managed retrieval set is invisible.
    assert "ndcg@5" not in run["aggregate"]
    assert "groundedness" not in run["aggregate"]
    assert "citation_accuracy" not in run["aggregate"]

    # Reversion at the config layer still works.
    version_1 = backend.version()
    version_2 = backend.apply({"model": "claude", "prompt": "v2"}, env="dev")
    assert version_2 != version_1
    backend.swap(version_1)
    assert backend.version() == version_1
