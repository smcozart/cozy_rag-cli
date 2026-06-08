"""rag-method CLI: the process as commands.

    rag-method status                          where am I, what's unmet
    rag-method baseline   [--env dev]          Phase 2: record the denominator
    rag-method experiment "<one change>"       the A/B loop, keep-or-revert, auto-logged
    rag-method promote    --to staging|prod    eval-gated promotion + report
    rag-method rollback   [--env dev]          repoint serving to previous version

Run from the project root (where rag-spec.yaml lives).
"""

import argparse
import sys
from pathlib import Path

from rag_method.workflow import (
    WorkflowError,
    do_baseline,
    do_experiment,
    do_promote,
    do_rollback,
    do_status,
    load_project,
)


def _print_gate_report(report: dict) -> None:
    for check in report["checks"]:
        marker = "PASS" if check["passed"] else ("BLOCK" if check["severity"] == "hard_block" else "warn")
        if check["kind"] == "threshold":
            detail = f">= {check['threshold']}, actual {check['actual']}"
        else:
            detail = f"drop <= {check['max_drop']}, baseline {check['baseline']}, actual {check['actual']}"
        print(f"  [{marker}] {check['metric']} ({check['kind']}: {detail})")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag-method", description=__doc__)
    parser.add_argument("--root", default=".", help="project root (default: cwd)")
    parser.add_argument("--env", default="dev", help="environment binding (default: dev)")
    parser.add_argument("-k", type=int, default=10, help="retrieval depth for eval (default: 10)")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="serving versions, baseline, dataset readiness")
    sub.add_parser("baseline", help="apply spec, run all datasets, record baseline")
    exp = sub.add_parser("experiment", help="A/B one spec change against the baseline")
    exp.add_argument("description", help="the ONE variable you changed, e.g. 'chunking: layout->contextual'")
    promote = sub.add_parser("promote", help="eval-gated promotion to another env")
    promote.add_argument("--to", required=True, help="target env, e.g. staging or prod")
    promote.add_argument(
        "--approve",
        metavar="VERSION",
        default=None,
        help="explicit human approval, bound to the candidate version id from the "
        "promotion report (production envs ALWAYS require this; never automated)",
    )
    sub.add_parser("rollback", help="repoint serving to the previous kept version")

    args = parser.parse_args(argv)
    try:
        project = load_project(Path(args.root), args.env)
        if args.command == "status":
            status = do_status(project)
            print(f"project: {project.root.name}   env: {project.env_name}")
            for env_name, env_state in status["envs"].items():
                history = env_state.get("history", [])
                serving = history[-1] if history else "(nothing applied)"
                print(f"  {env_name}: serving {serving}  ({len(history)} kept versions)  "
                      f"baseline run: {env_state.get('baseline_run') or 'none'}")
            print(f"datasets: {status['datasets']}")
            if status["placeholder_count"]:
                print(f"  WARNING: {status['placeholder_count']} REPLACE placeholders remain — "
                      "Phase 1 gate is not met")
            if status["recent_experiments"]:
                print("recent experiments:")
                for row in status["recent_experiments"]:
                    print(f"  {row}")
        elif args.command == "baseline":
            result = do_baseline(project, k=args.k)
            print(f"baseline recorded: version {result['version']}")
            for name, value in sorted(result["run"]["aggregate"].items()):
                print(f"  {name}: {value}")
            print(f"run: {result['run_path']}")
        elif args.command == "experiment":
            result = do_experiment(project, args.description, k=args.k)
            print(f"{result['verdict']}: {result['previous_version']} -> {result['candidate_version']}")
            if result["no_change"]:
                print("  WARNING: config hash unchanged — did you edit rag-spec.yaml?")
            _print_gate_report(result["report"])
            for metric, entry in result["comparison"]["aggregate"].items():
                if entry["delta"] is not None:
                    print(f"  {metric}: {entry['before']} -> {entry['after']} ({entry['delta']:+})")
            regressions = result["comparison"]["question_regressions"][:5]
            if regressions:
                print("  worst per-question regressions:")
                for regression in regressions:
                    print(f"    {regression['id']} {regression['metric']} "
                          f"{regression['before']} -> {regression['after']}")
            print("EXPERIMENTS.md row appended")
        elif args.command == "promote":
            result = do_promote(project, args.to, approve=args.approve, k=args.k)
            print(f"{result['status']}: candidate {result['candidate_version']} -> {args.to} "
                  f"(rollback target: {result['rollback_target']})")
            if result["approval_policy_overridden"]:
                print("  note: auto_on_green is IGNORED for protected environments — "
                      "production promotion always requires a human")
            if result["approval_mismatch"]:
                print("  approval did not match the candidate — the spec changed since "
                      "review; re-review the new report before approving")
            _print_gate_report(result["report"])
            if result["pending_approval"]:
                print("  candidate built and validated; serving unchanged. Review the "
                      "report, then approve THAT candidate:")
                print(f"    rag-method promote --to {args.to} "
                      f"--approve {result['candidate_version']}")
            print(f"report: {result['report_path']}")
        elif args.command == "rollback":
            result = do_rollback(project)
            print(f"rolled back: {result['from']} -> {result['to']}")
    except WorkflowError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
