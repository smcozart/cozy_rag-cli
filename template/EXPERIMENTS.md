# Experiment Log — <project>

> Append-only ledger of decisions, written by the tool. One row per decision —
> a baseline, an experiment (one variable changed, measured on the same
> versioned dataset + k; "Kept?" is the keep-or-kill call), a promotion, or a
> rollback. Config versions come from `backend.apply()`; run records live in
> `evals/runs/`. The tool appends rows below; don't hand-edit existing ones.

| Date | Change (one variable) | Versions (before -> after) | Metric deltas | Kept? | Why |
|---|---|---|---|---|---|
