"""The encoded process, end to end: baseline -> experiment (keep) ->
experiment (hard-block -> auto-revert) -> promote (manual approval) -> rollback.

This is the consistency claim under test: the same commands produce the same
sequence, bookkeeping, and reversion behavior every time.
"""

import json
from pathlib import Path

import pytest
import yaml

from rag_method.workflow import (
    WorkflowError,
    do_baseline,
    do_experiment,
    do_promote,
    do_rollback,
    do_status,
    load_project,
)

CORPUS = [
    {"id": "d1", "title": "Emergency Fund Guide",
     "text": "An emergency fund should be parked in a high-yield savings account "
             "or money market fund for liquidity and safety.",
     "metadata": {"effective_date": "2025-06-01"}},
    {"id": "d2", "title": "Business Expense Policy v2",
     "text": "Business expenses on a business trip include airfare, lodging, meals, "
             "and ground transportation.",
     "metadata": {"effective_date": "2026-02-01"}},
]

DATASET = [
    {"id": "q-1", "question": "Where should I park my emergency fund?",
     "reference_answer": "High-yield savings.", "relevant_doc_ids": ["d1"],
     "tags": ["topic:savings"], "must_refuse": False},
    {"id": "q-2", "question": "What counts as a business expense on a business trip?",
     "reference_answer": "Airfare, lodging, meals.", "relevant_doc_ids": ["d2"],
     "tags": ["topic:expenses"], "must_refuse": False},
]

PIPELINE = '''
from pathlib import Path
from rag_method.adapters import ReferenceBackend
from rag_method.contract import Answer, Citation

def build_backend(env):
    return ReferenceBackend(Path("serving") / str(env["env"]))

def generate(query, chunks):
    if not chunks:
        return Answer(text="I cannot answer that.", refused=True)
    top = chunks[0]
    return Answer(text="## Summary\\nAnswer.\\n## Findings\\n" + top.text,
                  citations=(Citation(title=top.title),))
'''


@pytest.fixture()
def project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)  # ReferenceBackend uses a relative serving/ dir
    (tmp_path / "data").mkdir()
    (tmp_path / "envs").mkdir()
    (tmp_path / "evals" / "datasets").mkdir(parents=True)

    (tmp_path / "data" / "corpus.jsonl").write_text(
        "\n".join(json.dumps(doc) for doc in CORPUS), encoding="utf-8")
    (tmp_path / "evals" / "datasets" / "golden.jsonl").write_text(
        "\n".join(json.dumps(item) for item in DATASET), encoding="utf-8")
    (tmp_path / "pipeline.py").write_text(PIPELINE, encoding="utf-8")

    spec = {"name": "wf-test", "corpus_path": "data/corpus.jsonl", "chunking": "layout"}
    (tmp_path / "rag-spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")
    gates = {
        "metrics": {
            "groundedness": {"threshold": 0.9, "severity": "hard_block"},
            "ndcg@10": {"threshold": 0.5, "severity": "advisory"},
        },
        "regression": {"groundedness": {"max_drop": 0.0, "severity": "hard_block"}},
    }
    (tmp_path / "gates.yaml").write_text(yaml.safe_dump(gates), encoding="utf-8")
    (tmp_path / "envs" / "dev.yaml").write_text(
        yaml.safe_dump({"env": "dev", "backend": "reference",
                        "promotion": {"approval": "auto_on_green"}}), encoding="utf-8")
    (tmp_path / "envs" / "prod.yaml").write_text(
        yaml.safe_dump({"env": "prod", "backend": "reference",
                        "promotion": {"approval": "manual"}}), encoding="utf-8")
    return tmp_path


def _set_spec(root: Path, **overrides: object) -> None:
    spec = yaml.safe_load((root / "rag-spec.yaml").read_text(encoding="utf-8"))
    spec.update(overrides)
    (root / "rag-spec.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")


def test_encoded_process(project_root: Path) -> None:
    project = load_project(project_root, "dev")

    # experiment before baseline is refused: the sequence is enforced
    with pytest.raises(WorkflowError, match="no baseline"):
        do_experiment(project, "premature")

    # Phase 2: baseline
    base = do_baseline(project)
    assert base["run"]["aggregate"]["groundedness"] == 1.0
    ledger = (project_root / "EXPERIMENTS.md").read_text(encoding="utf-8")
    assert "BASELINE" in ledger

    # Experiment 1: a passing change is KEPT and becomes the new comparison point
    _set_spec(project_root, chunking="contextual")
    project = load_project(project_root, "dev")
    result = do_experiment(project, "chunking: layout->contextual")
    assert result["verdict"] == "KEPT"
    assert result["candidate_version"] != result["previous_version"]
    kept_version = result["candidate_version"]

    # Experiment 2: make a hard-block gate unmeetable -> AUTO-REVERT to kept version
    gates = yaml.safe_load((project_root / "gates.yaml").read_text(encoding="utf-8"))
    gates["metrics"]["groundedness"]["threshold"] = 1.1  # impossible
    (project_root / "gates.yaml").write_text(yaml.safe_dump(gates), encoding="utf-8")
    _set_spec(project_root, chunking="token_split")
    project = load_project(project_root, "dev")
    result = do_experiment(project, "chunking: contextual->token_split")
    assert result["verdict"] == "REVERTED"
    backend = project.pipeline.build_backend(project.env)
    assert backend.version() == kept_version  # serving really went back

    # The ledger recorded BOTH outcomes — the log cannot drift from reality
    ledger = (project_root / "EXPERIMENTS.md").read_text(encoding="utf-8")
    assert "KEPT" in ledger and "REVERTED" in ledger

    # restore sane gates; promotion to prod is two-step: candidate -> human approval
    gates["metrics"]["groundedness"]["threshold"] = 0.9
    (project_root / "gates.yaml").write_text(yaml.safe_dump(gates), encoding="utf-8")
    _set_spec(project_root, chunking="contextual")
    project = load_project(project_root, "dev")

    pending = do_promote(project, "prod")
    assert pending["pending_approval"] and not pending["promoted"]
    candidate = pending["candidate_version"]
    pending_report = Path(pending["report_path"]).read_text(encoding="utf-8")
    assert "PENDING APPROVAL" in pending_report and candidate in pending_report

    # a wrong/stale token never ships
    mismatch = do_promote(project, "prod", approve="deadbeef0000")
    assert mismatch["approval_mismatch"] and not mismatch["promoted"]

    promotion = do_promote(project, "prod", approve=candidate)
    assert promotion["promoted"]
    assert Path(promotion["report_path"]).exists()
    report_text = Path(promotion["report_path"]).read_text(encoding="utf-8")
    assert "PROMOTED" in report_text and "Rollback target" in report_text

    # status reflects both envs
    status = do_status(project)
    assert "dev" in status["envs"] and "prod" in status["envs"]

    # rollback needs two kept versions in dev: keep one more, then roll back
    _set_spec(project_root, chunking="semantic")
    project = load_project(project_root, "dev")
    result = do_experiment(project, "chunking: contextual->semantic")
    assert result["verdict"] == "KEPT"
    rolled = do_rollback(project)
    assert rolled["to"] == kept_version
    backend = project.pipeline.build_backend(project.env)
    assert backend.version() == kept_version


def test_protected_env_ignores_auto_policy(project_root: Path) -> None:
    """A prod-named env with auto_on_green STILL requires human approval —
    the human-in-the-loop is a guarantee, not a setting."""
    (project_root / "envs" / "prod.yaml").write_text(
        yaml.safe_dump({"env": "prod", "backend": "reference",
                        "promotion": {"approval": "auto_on_green"}}), encoding="utf-8")
    project = load_project(project_root, "dev")
    do_baseline(project)

    result = do_promote(project, "prod")
    assert result["pending_approval"] and not result["promoted"]
    assert result["approval_policy_overridden"]

    approved = do_promote(project, "prod", approve=result["candidate_version"])
    assert approved["promoted"]
