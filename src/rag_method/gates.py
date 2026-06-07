"""Declarative eval gates: promotion is gated by measured quality, not opinion.

gates.yaml format:

    metrics:
      groundedness:        {threshold: 0.95, severity: hard_block}
      citation_accuracy:   {threshold: 0.90, severity: hard_block}
      "ndcg@10":           {threshold: 0.50, severity: advisory}
    regression:
      "ndcg@10":           {max_drop: 0.02, severity: hard_block}
      completeness:        {max_drop: 0.05, severity: advisory}

Threshold gates check the candidate run's aggregate. Regression gates compare
against a baseline run (the currently-promoted config's last run). Severity:
`hard_block` failures veto promotion; `advisory` failures warn and pass.
"""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml


def load_gates(path: str | Path) -> dict[str, Any]:
    with Path(path).open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    return loaded


def evaluate_gates(
    gates: Mapping[str, Any],
    run: Mapping[str, Any],
    baseline: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Returns a gate report: {passed, hard_block_failures, advisories, checks}."""
    aggregate: Mapping[str, float] = run["aggregate"]
    baseline_aggregate: Mapping[str, float] = baseline["aggregate"] if baseline else {}
    checks: list[dict[str, Any]] = []

    for metric, rule in (gates.get("metrics") or {}).items():
        threshold = float(rule["threshold"])
        severity = rule.get("severity", "advisory")
        actual = aggregate.get(metric)
        passed = actual is not None and actual >= threshold
        checks.append(
            {
                "kind": "threshold",
                "metric": metric,
                "threshold": threshold,
                "actual": actual,
                "severity": severity,
                "passed": passed,
            }
        )

    for metric, rule in (gates.get("regression") or {}).items():
        if baseline is None:
            continue
        max_drop = float(rule["max_drop"])
        severity = rule.get("severity", "advisory")
        before = baseline_aggregate.get(metric)
        after = aggregate.get(metric)
        if before is None or after is None:
            passed = False
            drop = None
        else:
            drop = round(before - after, 4)
            passed = drop <= max_drop
        checks.append(
            {
                "kind": "regression",
                "metric": metric,
                "max_drop": max_drop,
                "baseline": before,
                "actual": after,
                "drop": drop,
                "severity": severity,
                "passed": passed,
            }
        )

    hard_block_failures = [
        check for check in checks if not check["passed"] and check["severity"] == "hard_block"
    ]
    advisories = [
        check for check in checks if not check["passed"] and check["severity"] == "advisory"
    ]
    return {
        "passed": not hard_block_failures,
        "hard_block_failures": hard_block_failures,
        "advisories": advisories,
        "checks": checks,
        "config_version": run.get("config_version"),
        "baseline_version": baseline.get("config_version") if baseline else None,
    }
