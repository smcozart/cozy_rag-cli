# RAG Methodology — Working Checklist

One page for active use during a build. The reasoning lives in METHODOLOGY.md — if a step
feels arbitrary, go read its "why" there before skipping it.

## Phase 0 — Frame  ▢ gate: decision record complete
- [ ] D0: RAG confirmed as the right tool (vs fine-tune vs long-context)
- [ ] Corpus explored BY HAND (structure, freshness/supersession, vocabulary)
- [ ] 5–10 real queries traced to their answering documents manually
- [ ] Query population characterized (simple / compound / multi-turn / time-sensitive)
- [ ] D1–D10 resolved with rationale in DECISIONS.md

## Phase 1 — Foundation  ▢ gate: measure-ready
- [ ] rag-spec.yaml holds EVERY quality-affecting setting; envs/ holds only bindings
- [ ] Golden set seeded (50–200 target; synthetic-generate + human-review)
- [ ] Adversarial set: ≥1 case per failure mode (all 8; +tenant-leakage if multi-tenant)
- [ ] Unanswerable set exists (refusal is measurable)
- [ ] gates.yaml: thresholds + severities declared BEFORE first scores exist
- [ ] Chunking config pinned to dataset version

## Phase 2 — Baseline  ▢ gate: baseline recorded
- [ ] Parsing spot-checked against source documents
- [ ] `pipeline.py` binds your backend (and answer layer once you have one)
- [ ] Deliberately simple retrieval (one arm only); files/in-memory before databases
- [ ] `rag-method baseline` — runs everything, records the row automatically

## Phase 3 — Retrieval  ▢ gate: threshold met + deltas documented
- [ ] Hybrid (sparse + dense + RRF, k=60, over-fetch ~50/arm) — measured vs baseline
- [ ] Reranker over top 20–50 — measured (expect the biggest single gain)
- [ ] Chunking experiments (layout-aware vs contextual vs baseline) — measured
- [ ] Query transforms each measured independently; losers discarded
- [ ] Subtraction tested (does dropping an arm cost anything? if not, drop it)
- [ ] Per-stage scores captured (found-then-demoted vs never-found diagnosable)
- [ ] Named profiles committed (dev-fast / prod-quality / prod-budget) with curves
- [ ] Every change runs as `rag-method experiment "<one variable>"` — keep/revert and
      the EXPERIMENTS.md row happen automatically

## Phase 4 — Generation & Safety  ▢ gate: correctness gates green
- [ ] Citation enforcement on; citations resolve to actually-retrieved chunks
- [ ] Refusal handler beats fluent hallucination (unanswerable set passing)
- [ ] Temperature ≈ 0 for factual routes; rerank+truncate guards lost-in-the-middle
- [ ] All 8 adversarial modes passing; cross-tenant probes if multi-tenant (zero leakage)

## Phase 5 — Agentic (conditional)  ▢ gate: written go/no-go
- [ ] Go/no-go decided from PHASE 3–4 EVIDENCE, not fashion — no-go is a fine outcome
- [ ] If go: lowest escalation rung that fixes the measured gap (router → decomposition → corrective → reflective → ReAct)
- [ ] Agentic evals added (plan quality, source selection, re-query rate); latency budget held

## Phase 6 — Operate  ▢ gate: loop is live
- [ ] Promotion: `rag-method promote --to staging` (auto on green); `--to prod --approve`
      (manual + written report in evals/promotions/)
- [ ] Reversion REHEARSED once (`rag-method rollback`, then re-promote)
- [ ] Per-query logging: subqueries, chunks + stage scores, final context, citations, latency, cost, config version
- [ ] Scheduled regression replay + drift alerts
- [ ] Production queries feed back into regression set; novel failures become adversarial cases
