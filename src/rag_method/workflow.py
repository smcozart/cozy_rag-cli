"""The encoded process: baseline -> experiment -> promote/rollback.

This module is what makes the methodology programmatic. The loop's SEQUENCE
and BOOKKEEPING are owned by code; the human owns only the architect's
decisions (which variable to change, thresholds, prod approval).

Every project supplies exactly one binding file, pipeline.py:

    def build_backend(env: dict) -> Backend          # required
    def generate(query, chunks) -> Answer            # optional (skip = retrieval-only eval)

Everything else — spec, gates, env bindings, datasets — is declarative and
read from the standard artifacts. State (serving history, baseline pointer)
lives in evals/state.json; experiment rows are appended to EXPERIMENTS.md
automatically so the ledger cannot drift from what actually ran.
"""

import importlib.util
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

from rag_method.contract import Backend, Generate
from rag_method.diff import diff_runs
from rag_method.gates import evaluate_gates, load_gates
from rag_method.runner import run_eval, save_run


class WorkflowError(Exception):
    """Raised when the process cannot proceed (missing artifact, bad state)."""


@dataclass
class Project:
    root: Path
    env_name: str
    spec: dict[str, Any]
    gates: dict[str, Any]
    env: dict[str, Any]
    pipeline: ModuleType

    @property
    def datasets_dir(self) -> Path:
        return self.root / "evals" / "datasets"

    @property
    def runs_dir(self) -> Path:
        return self.root / "evals" / "runs"

    @property
    def state_path(self) -> Path:
        return self.root / "evals" / "state.json"

    @property
    def experiments_path(self) -> Path:
        return self.root / "EXPERIMENTS.md"


def load_project(root: str | Path, env_name: str = "dev") -> Project:
    root = Path(root).resolve()
    spec_path = root / "rag-spec.yaml"
    gates_path = root / "gates.yaml"
    env_path = root / "envs" / f"{env_name}.yaml"
    pipeline_path = root / "pipeline.py"
    for required in (spec_path, gates_path, env_path, pipeline_path):
        if not required.exists():
            raise WorkflowError(f"missing project artifact: {required}")

    module_name = f"_rag_pipeline_{abs(hash(str(root)))}"
    module_spec = importlib.util.spec_from_file_location(module_name, pipeline_path)
    if module_spec is None or module_spec.loader is None:
        raise WorkflowError(f"cannot import {pipeline_path}")
    pipeline = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(pipeline)
    if not hasattr(pipeline, "build_backend"):
        raise WorkflowError("pipeline.py must define build_backend(env) -> Backend")

    with spec_path.open(encoding="utf-8") as handle:
        spec = yaml.safe_load(handle) or {}
    with env_path.open(encoding="utf-8") as handle:
        env = yaml.safe_load(handle) or {}
    return Project(
        root=root,
        env_name=env_name,
        spec=spec,
        gates=load_gates(gates_path),
        env=env,
        pipeline=pipeline,
    )


def _backend(project: Project) -> Backend:
    backend: Backend = project.pipeline.build_backend(project.env)
    return backend


def _generate(project: Project) -> Generate | None:
    candidate = getattr(project.pipeline, "generate", None)
    return candidate


def _dataset_paths(project: Project) -> list[Path]:
    paths = sorted(
        path
        for path in project.datasets_dir.glob("*.jsonl")
        if not path.name.startswith(".")
    )
    if not paths:
        raise WorkflowError(f"no datasets in {project.datasets_dir}")
    return paths


def _load_state(project: Project) -> dict[str, Any]:
    if project.state_path.exists():
        loaded: dict[str, Any] = json.loads(project.state_path.read_text(encoding="utf-8"))
        return loaded
    return {}


def _save_state(project: Project, state: dict[str, Any]) -> None:
    project.state_path.parent.mkdir(parents=True, exist_ok=True)
    project.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _env_state(state: dict[str, Any], env_name: str) -> dict[str, Any]:
    return state.setdefault(env_name, {"history": [], "baseline_run": None})


def _load_run(project: Project, run_file: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(
        (project.root / run_file).read_text(encoding="utf-8")
    )
    return loaded


def _gate_metric_names(gates: dict[str, Any]) -> list[str]:
    names = list(gates.get("metrics") or {})
    for metric in gates.get("regression") or {}:
        if metric not in names:
            names.append(metric)
    return names


def _delta_summary(comparison: dict[str, Any], gates: dict[str, Any], limit: int = 4) -> str:
    parts: list[str] = []
    for metric in _gate_metric_names(gates)[:limit]:
        entry = comparison["aggregate"].get(metric)
        if not entry or entry["delta"] is None:
            continue
        sign = "+" if entry["delta"] >= 0 else ""
        parts.append(f"{metric} {entry['before']}->{entry['after']} ({sign}{entry['delta']})")
    return "; ".join(parts) if parts else "n/a"


def _append_experiment_row(project: Project, columns: list[str]) -> None:
    path = project.experiments_path
    if not path.exists():
        path.write_text(
            "# Experiment Log\n\n"
            "| Date | Change (one variable) | Versions (before -> after) "
            "| Metric deltas | Kept? | Why |\n|---|---|---|---|---|---|\n",
            encoding="utf-8",
        )
    cells = " | ".join(cell.replace("|", "/") for cell in columns)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"| {cells} |\n")


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def do_baseline(project: Project, k: int = 10) -> dict[str, Any]:
    """Phase 2 exit: apply the spec, run ALL datasets, record the denominator."""
    backend = _backend(project)
    version = backend.apply(project.spec, project.env_name)
    run = run_eval(_dataset_paths(project), backend, generate=_generate(project), k=k)
    run_path = save_run(run, project.runs_dir)

    state = _load_state(project)
    env_state = _env_state(state, project.env_name)
    if version not in env_state["history"]:
        env_state["history"].append(version)
    env_state["baseline_run"] = str(run_path.relative_to(project.root))
    _save_state(project, state)

    aggregate = run["aggregate"]
    metrics = "; ".join(
        f"{name}={aggregate[name]}" for name in _gate_metric_names(project.gates)
        if name in aggregate
    )
    _append_experiment_row(
        project,
        [_today(), "BASELINE", version, metrics or "n/a", "baseline", "Phase 2 denominator"],
    )
    return {"version": version, "run": run, "run_path": str(run_path)}


def do_experiment(project: Project, description: str, k: int = 10) -> dict[str, Any]:
    """The encoded A/B loop: apply -> run -> diff -> gates -> keep-or-revert -> log.

    Precondition: you edited ONE variable in rag-spec.yaml and can name it
    (the description). The function enforces everything else: the candidate is
    measured on the same datasets, compared against the recorded baseline,
    gated, kept or reverted, and the ledger row is written either way.
    """
    state = _load_state(project)
    env_state = _env_state(state, project.env_name)
    if not env_state["baseline_run"] or not env_state["history"]:
        raise WorkflowError("no baseline recorded — run `rag-method baseline` first")
    baseline_run = _load_run(project, env_state["baseline_run"])
    previous_version = env_state["history"][-1]

    backend = _backend(project)
    candidate_version = backend.apply(project.spec, project.env_name)
    no_change = candidate_version == previous_version

    run = run_eval(_dataset_paths(project), backend, generate=_generate(project), k=k)
    run_path = save_run(run, project.runs_dir)
    comparison = diff_runs(baseline_run, run)
    report = evaluate_gates(project.gates, run, baseline=baseline_run)

    if report["passed"]:
        verdict = "KEPT"
        if candidate_version not in env_state["history"]:
            env_state["history"].append(candidate_version)
        env_state["baseline_run"] = str(run_path.relative_to(project.root))
    else:
        verdict = "REVERTED"
        backend.swap(previous_version)
    _save_state(project, state)

    failures = "; ".join(
        f"{check['metric']} {check.get('actual')}<{check.get('threshold', check.get('max_drop'))}"
        for check in report["hard_block_failures"]
    )
    why = "gates green" if report["passed"] else f"hard block: {failures}"
    if no_change:
        why += " (WARNING: config hash unchanged — did you edit rag-spec.yaml?)"
    _append_experiment_row(
        project,
        [
            _today(),
            description,
            f"{previous_version} -> {candidate_version}",
            _delta_summary(comparison, project.gates),
            verdict,
            why,
        ],
    )
    return {
        "verdict": verdict,
        "previous_version": previous_version,
        "candidate_version": candidate_version,
        "report": report,
        "comparison": comparison,
        "run_path": str(run_path),
        "no_change": no_change,
    }


def do_rollback(project: Project) -> dict[str, Any]:
    """Repoint serving to the previous kept version. Seconds, reversible."""
    state = _load_state(project)
    env_state = _env_state(state, project.env_name)
    if len(env_state["history"]) < 2:
        raise WorkflowError("nothing to roll back to (need >=2 kept versions)")
    abandoned = env_state["history"].pop()
    target = env_state["history"][-1]
    _backend(project).swap(target)
    _save_state(project, state)
    _append_experiment_row(
        project,
        [_today(), "ROLLBACK", f"{abandoned} -> {target}", "n/a", "rolled back", "manual rollback"],
    )
    return {"from": abandoned, "to": target}


PROTECTED_ENV_NAMES = frozenset({"prod", "production", "prd", "live"})


def _human_approval_required(env_name: str, env_config: dict[str, Any]) -> tuple[bool, bool]:
    """Returns (requires_human_approval, auto_policy_overridden).

    Production is never promoted to by automation alone. Environments named
    like production — or marked `protected: true` — ALWAYS require explicit
    human approval; a `promotion.approval: auto_on_green` setting on such an
    environment is ignored (and surfaced in the report), not honored.
    Automation may build the candidate and run the gates; only a human ships.
    """
    is_protected = env_name.lower() in PROTECTED_ENV_NAMES or bool(env_config.get("protected"))
    auto = str(env_config.get("promotion", {}).get("approval", "manual")) == "auto_on_green"
    if is_protected:
        return True, auto
    return not auto, False


def do_promote(
    project: Project, to_env: str, approve: str | None = None, k: int = 10
) -> dict[str, Any]:
    """Eval-gated promotion. Human approval is bound to a SPECIFIC candidate.

    For environments requiring approval (all protected/production envs, plus
    any env with `promotion.approval: manual`), promotion is two-step:

      1. ``promote --to prod`` — builds the candidate (a new versioned
         index/resource; serving is untouched or reverted), runs the full
         suite, writes the promotion report, returns PENDING APPROVAL with
         the candidate version id.
      2. A human reviews ``evals/promotions/<...>.md``, then runs
         ``promote --to prod --approve <candidate_version>``.

    The approval token IS the candidate version hash: you can only approve
    the exact configuration you reviewed. If the spec changed since review,
    the hash changed, the approval is void, and a fresh report is produced.
    There is no flag that promotes "whatever is current" to production.

    A hard-block gate failure always blocks and reverts, approval or not.
    """
    target = load_project(project.root, to_env)
    requires_approval, policy_overridden = _human_approval_required(to_env, target.env)

    state = _load_state(project)
    target_state = _env_state(state, to_env)
    target_baseline = (
        _load_run(project, target_state["baseline_run"]) if target_state["baseline_run"] else None
    )
    previous_target_version = target_state["history"][-1] if target_state["history"] else None

    backend = _backend(target)
    candidate_version = backend.apply(project.spec, to_env)
    run = run_eval(_dataset_paths(project), backend, generate=_generate(target), k=k)
    run_path = save_run(run, project.runs_dir)
    report = evaluate_gates(project.gates, run, baseline=target_baseline)

    approval_satisfied = (not requires_approval) or (approve == candidate_version)
    approval_mismatch = (
        requires_approval and approve is not None and approve != candidate_version
    )
    promoted = report["passed"] and approval_satisfied

    if promoted:
        if candidate_version not in target_state["history"]:
            target_state["history"].append(candidate_version)
        target_state["baseline_run"] = str(run_path.relative_to(project.root))
    elif previous_target_version is not None:
        # Not shipping: serving goes back to the incumbent, candidate kept on
        # disk under its versioned name for review/approval.
        backend.swap(previous_target_version)
    _save_state(project, state)

    if promoted:
        status = "PROMOTED"
    elif not report["passed"]:
        status = "BLOCKED (gates)"
    else:
        status = "PENDING APPROVAL"
    next_step = (
        f"rag-method promote --to {to_env} --approve {candidate_version}"
        if status == "PENDING APPROVAL"
        else None
    )

    # A promotion is a decision, so it belongs in the EXPERIMENTS.md ledger
    # alongside baseline/experiment/rollback — not only in the promotions report
    # (which is a per-invocation artifact, not part of the durable decision log).
    # Two outcomes change or veto serving and are logged; PENDING APPROVAL is a
    # proposal with serving untouched (the report is its artifact), and a
    # wrong-token attempt is a refused attempt — neither is a decision.
    if status in ("PROMOTED", "BLOCKED (gates)"):
        aggregate = run["aggregate"]
        metric_summary = "; ".join(
            f"{name}={aggregate[name]}"
            for name in _gate_metric_names(project.gates)
            if name in aggregate
        )
        versions = f"{previous_target_version or 'none'} -> {candidate_version}"
        if status == "PROMOTED":
            why = f"approved {approve}" if requires_approval else "auto on green"
            verdict = "PROMOTED"
        else:
            failures = "; ".join(
                f"{check['metric']} {check.get('actual')}<"
                f"{check.get('threshold', check.get('max_drop'))}"
                for check in report["hard_block_failures"]
            )
            why = f"hard block: {failures}"
            verdict = "BLOCKED"
        _append_experiment_row(
            project,
            [_today(), f"PROMOTE -> {to_env}", versions,
             metric_summary or "n/a", verdict, why],
        )

    report_path = _write_promotion_report(
        project,
        to_env,
        run,
        report,
        previous_target_version,
        candidate_version,
        status=status,
        next_step=next_step,
        policy_overridden=policy_overridden,
    )
    return {
        "promoted": promoted,
        "status": status,
        "pending_approval": status == "PENDING APPROVAL",
        "approval_mismatch": approval_mismatch,
        "approval_policy_overridden": policy_overridden,
        "candidate_version": candidate_version,
        "rollback_target": previous_target_version,
        "report": report,
        "report_path": str(report_path),
        "run_path": str(run_path),
    }


def _write_promotion_report(
    project: Project,
    to_env: str,
    run: dict[str, Any],
    report: dict[str, Any],
    previous_version: str | None,
    candidate_version: str,
    status: str,
    next_step: str | None = None,
    policy_overridden: bool = False,
) -> Path:
    promotions_dir = project.root / "evals" / "promotions"
    promotions_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = promotions_dir / f"{stamp}-{project.env_name}-to-{to_env}.md"

    lines = [
        f"# Promotion Report: {project.env_name} -> {to_env}",
        "",
        f"- Result: {status}",
        f"- Candidate version: `{candidate_version}`",
        f"- Rollback target: `{previous_version or 'none (first deployment)'}`",
        f"- Run: `{run['run_id']}` on `{run['dataset']}` (k={run['k']})",
    ]
    if policy_overridden:
        lines.append(
            "- NOTE: `promotion.approval: auto_on_green` is IGNORED for protected "
            "environments — production promotion always requires a human."
        )
    lines += [
        "",
        "## Gate checks",
        "",
        "| Kind | Metric | Requirement | Actual | Severity | Passed |",
        "|---|---|---|---|---|---|",
    ]
    for check in report["checks"]:
        requirement = (
            f">= {check['threshold']}" if check["kind"] == "threshold"
            else f"drop <= {check['max_drop']} (baseline {check['baseline']})"
        )
        lines.append(
            f"| {check['kind']} | {check['metric']} | {requirement} | "
            f"{check['actual']} | {check['severity']} | {'yes' if check['passed'] else 'NO'} |"
        )
    lines += ["", "## Aggregate", ""]
    lines += [f"- {name}: {value}" for name, value in sorted(run["aggregate"].items())]
    if next_step:
        lines += [
            "",
            "## To approve",
            "",
            "Review the gate checks above, then run:",
            "",
            f"    {next_step}",
            "",
            f"The approval is bound to candidate `{candidate_version}` — if the spec "
            "changes, the hash changes and a fresh review is required.",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def do_status(project: Project) -> dict[str, Any]:
    """Where am I? Serving versions, baseline, dataset readiness, last experiments."""
    state = _load_state(project)
    placeholders = 0
    dataset_counts: dict[str, int] = {}
    for path in project.datasets_dir.glob("*.jsonl"):
        text = path.read_text(encoding="utf-8")
        dataset_counts[path.name] = sum(1 for line in text.splitlines() if line.strip())
        placeholders += text.count("REPLACE")
    recent: list[str] = []
    if project.experiments_path.exists():
        rows = [
            line for line in project.experiments_path.read_text(encoding="utf-8").splitlines()
            if line.startswith("| 2")
        ]
        recent = rows[-5:]
    return {
        "envs": state,
        "datasets": dataset_counts,
        "placeholder_count": placeholders,
        "recent_experiments": recent,
    }
