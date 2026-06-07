"""Run diffing: the offline A/B comparison.

Compares two run records (config A vs config B on the SAME dataset) and
surfaces aggregate deltas, per-tag deltas, and per-question regressions —
the evidence that goes into EXPERIMENTS.md before a keep-or-kill decision.
"""

from collections.abc import Mapping
from typing import Any


def _delta_map(
    before: Mapping[str, float], after: Mapping[str, float]
) -> dict[str, dict[str, float | None]]:
    metrics = sorted(set(before) | set(after))
    out: dict[str, dict[str, float | None]] = {}
    for metric in metrics:
        b, a = before.get(metric), after.get(metric)
        out[metric] = {
            "before": b,
            "after": a,
            "delta": round(a - b, 4) if a is not None and b is not None else None,
        }
    return out


def diff_runs(
    run_a: Mapping[str, Any], run_b: Mapping[str, Any], regression_threshold: float = 0.0
) -> dict[str, Any]:
    """Diff run_a (before/baseline) against run_b (after/candidate)."""
    comparable = run_a.get("dataset") == run_b.get("dataset") and run_a.get("k") == run_b.get("k")

    by_question_a = {record["id"]: record["metrics"] for record in run_a["per_question"]}
    regressions: list[dict[str, Any]] = []
    for record in run_b["per_question"]:
        before_metrics = by_question_a.get(record["id"])
        if before_metrics is None:
            continue
        for metric, after_value in record["metrics"].items():
            before_value = before_metrics.get(metric)
            if before_value is None or after_value is None:
                continue
            drop = before_value - after_value
            if drop > regression_threshold:
                regressions.append(
                    {
                        "id": record["id"],
                        "metric": metric,
                        "before": before_value,
                        "after": after_value,
                        "drop": round(drop, 4),
                        "tags": record.get("tags", []),
                    }
                )

    tags = sorted(set(run_a.get("by_tag", {})) | set(run_b.get("by_tag", {})))
    by_tag = {
        tag: _delta_map(
            run_a.get("by_tag", {}).get(tag, {}),
            run_b.get("by_tag", {}).get(tag, {}),
        )
        for tag in tags
    }

    return {
        "comparable": comparable,
        "before_version": run_a.get("config_version"),
        "after_version": run_b.get("config_version"),
        "aggregate": _delta_map(run_a["aggregate"], run_b["aggregate"]),
        "by_tag": by_tag,
        "question_regressions": sorted(regressions, key=lambda r: -r["drop"]),
    }
