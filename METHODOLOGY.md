# RAG System Development Methodology

**A vendor-agnostic process for building retrieval-augmented generation systems with measurable quality.**

> Synthesized 2026-06-07 from: Dave Ebbelaar's hybrid retrieval methodology (`.firecrawl/yt-rag-video.md`),
> the cozy_RAG research baseline (`.firecrawl/research/`, `.firecrawl/synthesis/`), and the implicit
> methodology encoded in cozy_RAG's own design (`DECISIONS.md`, `.planning/`, `.staging/scorers/`).
> Applies to any stack: Azure AI Search, LanceDB, Chroma, pgvector, Elasticsearch, or raw numpy on disk.

---

## How to Use This Document

This is a **process contract**, not a tutorial. It defines:

- **Seven phases** (0–6) in a fixed order, each with an explicit **exit gate**
- **The decision points** the architect must consciously resolve, and when
- **The "why"** behind every ordering constraint — so the architect understands the methodology rather than following it on faith

You do not advance to the next phase until the current phase's exit gate is met. The gates are
what produce consistency across projects and confidence in the result. The phases are
vendor-agnostic because they are defined by *decision points and validation criteria*, not tools.

---

## Part I — The Operating Principles

These eight principles are the load-bearing beliefs. Every phase, gate, and ordering rule below
derives from one or more of them. If you understand these, you can re-derive the methodology
from scratch — which is the test of whether you actually own it.

### P1. No tuning before measurement; no measurement without reproducibility

The single most common RAG failure pattern is "chuck everything into the vector database and
check off of vibes." Without ground truth (queries → known-relevant documents) you cannot tell
whether a change helped or hurt. And without reproducible configuration (schema-as-code, pinned
chunking/embedding settings), your eval baseline silently invalidates itself the moment anything
drifts. Ground truth and config reproducibility are *joint* prerequisites for iteration —
this is why they form Phase 1 together, before any pipeline tuning.

### P2. The corpus decides the architecture, not the other way around

There is no universally correct RAG stack. BM25-heavy corpora (codes, part numbers, legal
citations) reward sparse retrieval; paraphrase-heavy corpora reward dense. Hybrid + rerank is the
strongest *default*, but on some datasets dense-only with a larger candidate pool beats the full
hybrid. The methodology therefore mandates an **experimental harness**, not a fixed architecture:
build the components, then let measured scores on *your* corpus decide what stays.

### P3. Components in isolation, then composition

Every retrieval component has a known strength and a known failure mode (BM25 wins exact terms,
loses paraphrase; dense is the exact inverse). You can only reason about a composed pipeline if
you measured each component alone first. Practically: score BM25-only, dense-only, fused, and
fused+reranked as four separate eval runs. The deltas between them tell you what each stage earns
— and what you can remove.

### P4. Change one variable, measure the delta

A single scalar quality metric (NDCG@10 for retrieval; groundedness for generation), a fixed
eval sample (seeded, reproducible), one change at a time. Chunking strategy, embedding model,
fusion method, reranker, top-K — each is an experiment with a before/after score. This is the
difference between engineering and vibes.

### P5. Every known failure mode gets an adversarial test

RAG systems fail in *enumerable* ways (see Part IV: the 8-mode taxonomy). A system that passes a
golden Q&A set can still hallucinate on unanswerable questions, leak across tenants, or miss
evidence scattered across chunks. Hoping you handle a failure mode is not a strategy; shipping a
test for it is. The adversarial pack is MVP scope, never "v1.1."

### P6. Promotion is gated by measured quality, not opinion

Movement between environments (dev → staging → prod) is controlled by declarative eval gates
with per-metric severity: groundedness/refusal/leakage regressions **hard-block**; minor
recall/latency drift **warns**. Code review answers "is this code sound?" — it cannot answer
"does this retrieval setup actually work?" Only the eval harness can, so the harness owns the gate.

### P7. Observability is for root-cause debugging, not dashboards

When a gate fires, you must be able to answer *why* in minutes: replay the query, see the
subqueries issued, the chunks retrieved with per-stage scores, what entered the final context,
and what got cited. Logging retrieval decisions (not just outcomes) is what closes the loop:
eval regression → replay → classify failure mode → fix → re-run.

### P8. Bias toward simplicity; add infrastructure only when scale demands it

A 57k-document corpus is a 33 MB BM25 index and a 350 MB numpy file — both can live on disk,
load in memory, even sit in version control. Below roughly a million chunks you likely don't
need a vector database at all. Every piece of infrastructure you skip is drift you can't have
and operations you don't pay for. Adopt the database, the orchestration framework, and the
agentic layer only when a measured limitation forces you to.

---

## Part II — The Lifecycle at a Glance

```
Phase 0          Phase 1            Phase 2          Phase 3           Phase 4           Phase 5            Phase 6
FRAME       →    FOUNDATION    →    BASELINE    →    RETRIEVAL    →    GENERATION   →    AGENTIC      →    OPERATE
(decide)         (measure-ready)    (simplest        OPTIMIZATION      & SAFETY          ESCALATION        (promote,
                                     thing that      (tune against     (ground,          (only if          observe,
                                     works)          ground truth)     cite, refuse)     justified)        monitor)
```

| Phase | Exit gate (do not advance without) |
|---|---|
| **0 — Frame** | Decision record written; corpus explored hands-on; query patterns characterized; RAG confirmed as the right tool |
| **1 — Foundation** | Config expressed as versioned code; golden + adversarial + unanswerable eval sets exist and are versioned; metrics and gate thresholds declared |
| **2 — Baseline** | End-to-end pipeline runs; baseline scores recorded on the golden set |
| **3 — Retrieval** | Retrieval metric (e.g., NDCG@10 / recall@K) meets declared threshold; per-component contribution measured; winning configuration documented with evidence |
| **4 — Generation** | Groundedness / citation / refusal gates green; all 8 adversarial failure modes have a passing test |
| **5 — Agentic** | Explicit go/no-go decision recorded; if go: agentic evals (plan quality, source selection) green |
| **6 — Operate** | Promotion gates wired; rollback rehearsed; regression replay scheduled; drift alerts live |

Dependency logic (why this order is a correctness constraint, not a preference):

- You can't tune (3, 4) what you can't measure (1) on something that runs (2).
- You can't decide *whether* you need agentic complexity (5) until you've seen how far the
  simple pipeline gets (3, 4) — otherwise you're over-engineering on assumption.
- You can't gate promotion (6) without trustworthy evals (1) and debuggable failures (P7).

---

## Part III — The Phases

### Phase 0 — Frame the Problem

**Objective:** Make the architecture-shaping decisions consciously, with evidence, before any
pipeline code exists.

**Activities:**

1. **Confirm RAG is the right tool.** Decision tree:

   | Need | Right tool |
   |---|---|
   | Up-to-date facts, cited sources, data governance | RAG |
   | Domain *style/tone/format* | Fine-tune (small) or system prompt |
   | Fixed corpus ≤ ~200k tokens, latency-sensitive | Long-context + prompt caching |
   | Reasoning over millions of heterogeneous docs | RAG with agentic retrieval |

   Production systems often combine these (RAG for facts + prompt for guardrails + cache for
   always-loaded context). If RAG isn't needed, stop here — that's a success, not a failure.

2. **Explore the corpus by hand.** Open real documents. Trace 5–10 real (or realistic) queries
   to the documents that answer them. Note document structure (do tables matter? headings?
   conditional clauses?), size distribution, freshness dynamics (do documents supersede each
   other?), and vocabulary (exact identifiers vs natural language). *This direct contact is what
   makes every later decision — chunking above all — an informed one.* Do not delegate this step.

3. **Characterize the query population.** Simple lookups? Compound/multi-hop comparisons?
   Multi-turn conversational? Time-sensitive? This determines whether Phase 5 will ever be
   justified, and which adversarial modes matter most.

4. **Resolve the standing design-space decisions and write them down.** Each is a real tension —
   the methodology requires a *conscious* resolution per project, not a default absorbed silently:

   | # | Decision | Options & default posture |
   |---|---|---|
   | D1 | Vertical (one use case) vs horizontal (platform) | Start vertical; design seams for horizontal |
   | D2 | Backend strategy / lock-in tolerance | Primary backend first; pluggable adapter seam designed in; second backend proves the seam later |
   | D3 | Classic vs agentic vs adaptive retrieval | Classic until measured query complexity justifies more (revisited in Phase 5) |
   | D4 | Chunking strategy | Per-content-type profiles; decided empirically in Phase 2–3 |
   | D5 | Embedding model | Benchmark-driven (MTEB retrieval subset for your task + language), never vendor claims |
   | D6 | Eval framework | Portable open framework as primary (e.g., RAGAS); vendor evaluators as adapters; custom scorers for domain contracts |
   | D7 | Gate strictness | Per-metric: correctness metrics hard-block; performance metrics advise |
   | D8 | Tenancy model | Single-tenant default with `tenant_id` present everywhere in metadata (free upgrade path) |
   | D9 | Environment separation | Hybrid: shared dev/staging, dedicated prod (cost vs blast-radius balance) |
   | D10 | Promotion approval | dev→staging auto on green; staging→prod manual with audit report |

**Exit gate:** A written decision record (DECISIONS.md pattern) covering D1–D10 with rationale;
hands-on corpus notes; query-population characterization.

**Why this phase exists:** Requirement #1 of this methodology is that the architect understands
the solution. Decisions absorbed by default from a tutorial or a vendor SDK are decisions you
can't defend, revisit, or debug. Writing them down with rationale is what makes them yours —
and locking them prevents re-litigating them mid-build.

---

### Phase 1 — Foundation: Become Measure-Ready

**Objective:** Establish the two joint prerequisites for all iteration: reproducible
configuration and ground truth. *(Principle P1 — this entire phase is P1 made operational.)*

**Activities:**

1. **Configuration as code.** Every quality-affecting setting — chunking strategy and
   parameters, embedding model + dimensions, index schema, analyzer settings, retrieval
   parameters, scoring profiles — lives in versioned, declarative spec files. Environment
   binding (endpoints, credentials, service names) is separate per-env config.
   **Schema is code; deployment binds to environment.**
   - Lint the spec (catch dimension mismatches, missing flags, preview-feature misuse before deploy).
   - Pin the chunking config to the eval-dataset version — if chunking changes, the baseline is void
     and the full suite re-runs.
   - *Vendor illustrations:* Azure index/skillset/scoring-profile as REST resources in git;
     open-source equivalent is the same YAML applied to LanceDB/Chroma via adapter.

2. **Build the ground-truth structure: queries ↔ documents ↔ relationships.** The BEIR shape
   (corpus, queries, qrels) is the universal format. Your corpus exists; the rest you construct:

   - **Golden set** (50–200): realistic questions, each mapped to known-relevant document IDs,
     with reference answers. Hand-curate at least a seed.
   - **Synthetic expansion:** for each document, prompt a cheap LLM — *"You are a user with a
     question. The following document contains the answer. Generate one realistic question a
     user would ask in their own words. The question must be answerable by this document."* —
     then human-review. Synthetic-without-review drifts; human-only plateaus on coverage. Do both.
   - **Adversarial set:** one or more cases per failure mode in the 8-mode taxonomy (Part IV).
   - **Unanswerable set:** questions the corpus deliberately cannot answer. The correct behavior
     is refusal; this is the only way to measure absence-blindness.
   - **Regression set** (grows later): sampled, PII-scrubbed production queries replayed on a schedule.

   Keep datasets versioned in-repo (e.g., JSONL with `question`, `reference_answer`,
   `relevant_doc_ids`, `tags`, `must_refuse`, `tenant_id`).

3. **Declare metrics and thresholds now, before any scores exist** (so thresholds reflect
   requirements, not whatever the first build happened to achieve):

   - **Retrieval:** NDCG@10 (primary single scalar), recall@K, precision@K.
   - **Generation:** groundedness/faithfulness, citation accuracy, answer relevancy,
     completeness, recency (where freshness matters).
   - **Behavioral:** refusal accuracy on the unanswerable set; zero cross-tenant leakage.
   - Per metric: threshold + severity (`hard_block` | `advisory`) per decision D7.

   Custom scorers should be **deterministic or cheap** (string/fuzzy matching, regex,
   metadata checks — the four canonical cozy_RAG scorers are the model), reserving LLM-judge
   scoring for what genuinely needs it.

**Exit gate:** Spec files versioned and lintable; golden + adversarial + unanswerable sets exist
and are versioned; metric thresholds and severities declared in a gates file.

**Why before any pipeline:** Without a fixed dataset you cannot tell whether changes regress
quality. Without pinned config you cannot trust that yesterday's score and today's are comparable.
Teams that defer this "until the pipeline works" end up tuning by vibes — measured here means
measurable forever.

---

### Phase 2 — Baseline: The Simplest Pipeline That Works

**Objective:** An end-to-end pipeline with deliberately simple choices, fully scored — the
reference point all optimization is measured against.

**Activities:**

1. **Ingest & parse.** Handle the real formats (PDF, DOCX, HTML, tables). Parsing errors here
   poison everything downstream — spot-check parsed output against source documents.
2. **Chunk — first-class decision, default thoughtfully.** Hierarchy of strategies, in rising
   cost and quality:
   1. Token/char split (fast, lossy) — acceptable only as a speed baseline
   2. Sentence/paragraph boundaries
   3. **Document-layout-aware** (headings, tables, sections) — the production default for structured docs
   4. Semantic chunking (embedding-cluster boundaries)
   5. **Contextual chunking** (prepend a 50–100-token LLM-generated "how this chunk fits the
      document" summary before embedding) — Anthropic reports a 35% reduction in top-20
      retrieval failure rate from contextual embeddings alone, 49% combined with contextual
      BM25, and 67% with reranking added (Sep 2024)
   Rule of thumb: split anything over ~1,000 tokens; respect structural boundaries. If documents
   are already small and self-contained, chunking may be a no-op — that's a corpus property
   (P2), check it rather than assume it.
3. **Embed.** Model chosen via the MTEB retrieval leaderboard for your task class and language —
   never vendor claims. Note: the embedding model is the *most expensive choice to change later*
   (full corpus re-embed), so treat re-embedding as a planned, supported operation from day one
   rather than an emergency.
4. **Index & retrieve, minimally.** Dense-only or BM25-only — whichever Phase 0 suggested fits
   the corpus vocabulary — straight to generation. Per P8: files + in-memory before any database.
5. **Run the full eval suite. Record the baseline.** Fixed seed, fixed sample. This number is
   the denominator for every claim you'll ever make about improvement.

**Exit gate:** Pipeline runs end-to-end; baseline scores recorded for retrieval and generation
metrics on the golden set.

**Why a deliberately naive baseline:** Each later addition (hybrid, rerank, transforms) must
*earn its place* with a measured delta over this baseline (P3, P4). Without the naive number,
you cannot distinguish "the stack works" from "any of this was necessary."

---

### Phase 3 — Retrieval Optimization

**Objective:** Find the retrieval configuration that maximizes the retrieval metric on *your*
corpus, via controlled experiments.

**The candidate ladder** (each rung measured independently — the proven high-leverage order):

1. **Hybrid retrieval.** Sparse (BM25) + dense in parallel; fuse by **rank, not score**
   (Reciprocal Rank Fusion, k=60), because BM25 scores and cosine similarities are incomparable
   scales. Over-fetch candidates from each side (K≈50) before fusing. Hybrid almost always beats
   either alone — but verify on your data; it is not guaranteed (on FinanceQA, fused landed
   *between* its inputs until the reranker was added).
2. **Reranking.** Cross-encoder over the top 20–50 fused candidates, truncate to final top-N.
   Consistently the **largest measured gain per line of code** (FinanceQA: BM25 alone scored
   NDCG@10 of 28; the full hybrid + rerank stack reached 47, with the rerank step delivering
   the decisive jump over dense and fused retrieval alone). Cross-encoders see query and document *together*,
   which the bi-encoder embedding path structurally cannot.
3. **Chunking experiments.** Re-run the eval per chunking profile (layout-aware vs contextual vs
   baseline). Highest-leverage single parameter in the pipeline; most often left at default.
4. **Query-side transforms,** each as its own experiment: query rewrite, HyDE, multi-query
   expansion, decomposition (compound questions), step-back prompting. Measure each delta;
   discard what doesn't pay.
5. **Index/runtime tuning** where relevant: HNSW vs exhaustive KNN, quantization (4–32× memory
   for modest recall loss), dimension reduction.

**Diagnosis discipline:** capture per-stage scores (initial retrieval score vs post-rerank score)
on every result. "Found at L1 but demoted at L2" and "never retrieved at all" are different bugs
with different fixes — the score pair tells you which you have.

**Subtraction is an experiment too.** If hybrid+rerank ≈ dense+rerank on your corpus, drop BM25
and keep the simpler system (P2, P8). The full stack is a candidate, not a prescription.

**Output — quality/cost/latency profiles:** name the configurations you'll actually run
(`dev-fast`, `prod-quality`, `prod-budget`) with eval-validated trade-off curves, rather than a
single monolithic setting.

**Exit gate:** Declared retrieval threshold met (e.g., recall@10 ≥ 0.80 / NDCG@10 target);
per-component contribution table recorded; winning configuration + named profiles committed to
the spec with the evidence.

**Why retrieval before generation tuning:** Generation cannot cite what retrieval never surfaced.
Every downstream symptom (hallucination, missing citations, incomplete answers) is confounded
until retrieval quality is pinned. Fix the supply chain before judging the chef.

---

### Phase 4 — Generation & Safety

**Objective:** The answer layer makes only claims grounded in retrieved evidence, cites
verifiably, and refuses when it should.

**Activities:**

1. **Citation enforcement.** Mandatory citation format; post-generation validation that every
   citation resolves to an actually-retrieved chunk; uncited claims stripped. Citation is the
   *contract* between system and user — a perfect answer with unverifiable citations is useless.
2. **Refusal handling.** "If grounding is insufficient, say so" must beat fluent hallucination.
   Validate against the unanswerable set: silent answering from irrelevant context scores zero.
3. **Determinism where factuality matters.** Temperature 0 (or near) for factual responses.
4. **Context-window discipline.** Rerank + truncate to top 10–20 to mitigate lost-in-the-middle;
   prefer **just-in-time retrieval** for agent consumers (return chunk references + previews;
   agent fetches full text only for what it will actually use) over eagerly stuffing full chunks.
5. **Structural response contract** where the use case warrants it (summary / findings with
   citations / freshness note / limitations) — completeness scoring makes corner-cutting visible.
6. **Run the full adversarial pack** (Part IV). Every one of the 8 modes needs a passing test.
   Multi-tenant systems additionally run cross-tenant leakage probes: as tenant A, query for
   tenant B's content; assert zero leakage in retrieved chunks *and* final answer.

**Exit gate:** Groundedness, citation accuracy, and refusal accuracy at threshold; all 8
adversarial modes covered with passing tests; tenant isolation verified if applicable.

**Why after retrieval:** Groundedness scores are meaningless while retrieval is unstable — you
can't attribute a hallucination to the generator while the retriever might simply have failed to
supply the evidence.

---

### Phase 5 — Agentic Escalation (Conditional)

**Objective:** Decide — with evidence, not fashion — whether the system needs agentic retrieval,
and adopt the *minimum* agentic pattern that fixes the measured gap.

**Go/no-go criteria.** Escalate only if eval evidence from Phases 3–4 shows the simple pipeline
failing on: compound/multi-hop questions (scattered-evidence mode persisting despite hybrid +
rerank), genuinely heterogeneous sources requiring routing, or multi-turn context shaping
retrieval. If queries are simple and homogeneous: **stop here.** Classic RAG that measures well
beats agentic RAG that demos well.

**The escalation ladder** (adopt the lowest rung that fixes the measured failure):

1. **Router / adaptive** — classify query → route to strategy. Near-zero added latency. Start here.
2. **Query decomposition** — split compound questions into parallel sub-queries, retrieve per
   sub-query, synthesize. Fixes scattered-evidence.
3. **Corrective RAG** — lightweight retrieval-quality check between retrieve and generate;
   refine / fall back / combine on a 3-way verdict.
4. **Self-reflective gating** — model (or small judge LLM) decides *whether* to retrieve and
   judges sufficiency per claim.
5. **ReAct / retrieval-as-tool, multi-agent** — most flexible, hardest to evaluate; behavior is
   emergent. Requires the strongest observability before adoption.

Treat reasoning effort as a **per-route setting with a measured latency/quality curve**
(autocomplete: minimal; chat: low; analyst workloads: medium) — agentic is a spectrum, not a
binary. *(Vendor illustration: Azure's `retrievalReasoningEffort` knob; open-source equivalent
is which orchestration steps your harness runs.)*

**New eval obligations that come with going agentic:** plan quality (are sub-queries
well-formed? did decomposition cover all aspects?), source-selection accuracy, re-query rate,
and session-level multi-turn evals. The activity log (Phase 6) becomes mandatory, not optional.

**Exit gate:** Written go/no-go with the eval evidence; if go — chosen pattern justified against
the ladder, agentic-specific evals green, latency budget still met.

**Why a separate, late, conditional phase:** Agentic machinery adds latency, cost, and an
evaluation surface that's much harder to pin down. Buying that complexity *before* demonstrating
the simple pipeline's ceiling is the most common form of RAG over-engineering.

---

### Phase 6 — Operate: Promote, Observe, Monitor

**Objective:** The system improves safely in production, and quality regressions are caught by
machinery rather than by users.

**1. Eval-gated promotion.**

- Environments per D9 (hybrid separation typical). Same spec everywhere; only env binding differs.
- Promotion flow: run full eval suite against candidate config → hard-block gates must pass →
  dev→staging automatic on green; staging→prod requires human approval of a generated
  **promotion report** (eval summary vs baseline, gate results, config diff, rollback target) —
  the audit trail (D10).
- **Production approval is a guarantee, not a setting.** No automation path may promote to a
  production environment: auto-on-green configuration is ignored for protected envs, and the
  approval token is the specific candidate version hash from the reviewed report — approving
  "whatever is current" is structurally impossible, and a spec change after review voids the
  approval.
- **Atomic cutover via alias/pointer swap:** build the new index under a versioned name, validate,
  then atomically repoint the serving alias. Zero downtime regardless of reindex duration;
  rollback is the reverse swap, in seconds. Keep the previous index as the rollback target for a
  retention window. *(Azure aliases, Elasticsearch aliases, or a symlink/config pointer over
  LanceDB tables — same pattern everywhere.)*
- Known-expensive operations (corpus re-embed on model change) are pre-built workflows, not
  emergencies.

**2. Observability for root cause (P7).** Log per query: issued sub-queries, retrieved chunks
with per-stage scores, what entered final context, what got cited, latency and token spend,
config/eval-run version. Provide **replay** — reconstruct any failing query's full flow from the
log. Classify failures into the 8-mode taxonomy (heuristics first, LLM-assist for the remainder)
so fixes target modes, not anecdotes.

**3. Continuous quality.**

- **Nightly/scheduled regression replay** of the regression set; alert on deltas vs baseline.
- **Drift watch:** corpus freshness (hold out recently-added docs; assert they surface),
  query-population shift, eval-metric stability.
- Production metrics per route: groundedness, citation accuracy, refusal rate, p50/p95 latency,
  cost per query.
- **Feed production back into the eval sets:** sampled, scrubbed real queries become regression
  cases; novel failures become new adversarial cases. This is how the ground truth compounds
  instead of staling.

**Exit gate (steady state):** Promotion gates wired and exercised; one rollback rehearsed;
regression replay scheduled and alerting; failure-mode classification running.

**Why this is a phase and not an afterthought:** The eval harness from Phase 1 is the same
machinery that gates promotion and detects drift — operations is where the measurement
investment pays compound interest. A RAG system without this loop doesn't stay good; corpora
grow, queries shift, and quality decays silently.

---

## Part IV — The Failure-Mode Taxonomy (Adversarial Pack)

Eight enumerable ways RAG systems fail (extended from Faktion's enterprise RAG failure-mode
case studies — the count and several modes are this methodology's packaging, not Faktion's
own enumeration). Phase 1 builds at least one
adversarial test per mode; Phase 4 requires all to pass; Phase 6 classifies production failures
against them.

| # | Mode | What goes wrong | Detection test | Primary mitigation |
|---|---|---|---|---|
| 1 | **Scattered evidence** | Answer requires synthesizing ≥2 documents; single-shot retrieval misses one | Multi-doc questions answerable only by combining chunks | Query decomposition; multi-query; agentic escalation |
| 2 | **Context fragmentation** | Chunking severs dependent details ("if A then B" split across chunks) | Conditional clauses planted across chunk boundaries | Layout-aware or contextual chunking; overlap tuning |
| 3 | **Over-retrieval / noise** | Near-duplicates and irrelevant chunks dilute the context | Noise-sensitivity metric; rank position of known-good chunks | Reranker with threshold; dedupe by source |
| 4 | **Query ambiguity** | Unclear intent retrieves plausible-but-wrong content | Deliberately ambiguous queries; correct answer may be a clarifying refusal | Query rewrite / intent classification before retrieval |
| 5 | **Knowledge gaps (absence-blindness)** | System answers fluently from irrelevant context instead of refusing | Unanswerable set; assert refusal | Sufficiency check; refusal handler; groundedness gate |
| 6 | **Staleness** | Superseded or missing-recent documents win retrieval | Hold out recently added docs; assert they surface; superseded docs penalized | Freshness/recency scoring; metadata (`effective_date`, `superseded_by`); reindex monitoring |
| 7 | **Low traceability** | Claims without citations, or citations that don't resolve to retrieved sources | Citation-accuracy scorer (structural + referential) | Mandatory citation format; post-gen citation validation |
| 8 | **Latency vs depth** | Quality machinery (rerank, multi-hop, reasoning) blows the latency budget | p50/p95 per route against SLO | Named profiles; per-route reasoning effort; caching |

*Multi-tenant systems add mode 9: **tenant leakage** — adversarial cross-tenant probes, zero
tolerance, hard-block always.*

---

## Part V — Decision Record Template

Phase 0 produces this; later phases append. One file, versioned with the repo.

```markdown
# RAG Decision Record — <project>

## D0. Is RAG the right tool?            <evidence from the decision tree>
## D1. Vertical vs horizontal:           <choice + why>
## D2. Backend & lock-in posture:        <choice + why>
## D3. Classic vs agentic (initial):     <choice + why; revisit gate in Phase 5>
## D4. Chunking profile(s):              <decided empirically in Phase 2–3; record experiments>
## D5. Embedding model:                  <model, MTEB evidence, dimensions, re-embed plan>
## D6. Eval stack:                       <frameworks + custom scorers>
## D7. Gate severities:                  <hard-block list / advisory list + thresholds>
## D8. Tenancy:                          <model + isolation testing obligation>
## D9. Environments:                     <topology + why>
## D10. Promotion approvals:             <auto/manual boundaries + audit artifact>

## Experiment log (append-only)
| Date | Change | Metric before → after | Kept? |
|---|---|---|---|
```

---

## Part VI — Anti-Patterns This Methodology Exists to Prevent

1. **Vibes-driven development** — no ground truth, judging output by eyeball. *(Prevented by Phase 1.)*
2. **Tutorial-stack cargo-culting** — adopting hybrid+rerank+agentic wholesale without measuring
   what each piece earns on your corpus. *(Prevented by Phases 2–3: baseline + component deltas.)*
3. **Vector-database-first thinking** — infrastructure before evidence of need. *(P8.)*
4. **Golden-set-only confidence** — passing happy-path Q&A while failing every edge case.
   *(Prevented by the adversarial pack, Phase 4.)*
5. **Schema drift** — portal-clicked, env-divergent configs that silently invalidate baselines.
   *(Prevented by config-as-code + lint + pinning, Phase 1.)*
6. **Unattributable failures** — knowing a query failed but not why. *(Prevented by per-stage
   score capture + replay, Phases 3 & 6.)*
7. **Promotion by hope** — shipping config changes without gate runs or a rollback path.
   *(Prevented by Phase 6.)*
8. **Premature agency** — agentic orchestration as a starting point instead of a measured
   escalation. *(Prevented by Phase 5's go/no-go.)*
9. **Embedding-model lock-in by accident** — choosing a model casually, then discovering the
   re-embed cost. *(Prevented by D5 + planned re-embed workflow.)*
10. **Eval sets that stale** — ground truth never refreshed from production reality.
    *(Prevented by the Phase 6 feedback loop.)*

---

## Provenance

| Source | Contribution |
|---|---|
| Dave Ebbelaar, *Complete Guide to Hybrid Search in RAG* (transcript: `.firecrawl/yt-rag-video.md`) | Ground-truth-first discipline; component isolation; RRF; reranker leverage; NDCG-driven tuning; synthetic eval-set generation; simplicity bias |
| `.firecrawl/research/general-rag.md` | Pipeline stages; chunking hierarchy incl. contextual chunking; MTEB discipline; RAG-vs-fine-tune-vs-long-context tree; RAGAS metrics; four-dataset discipline |
| `.firecrawl/research/azure-ai-search.md` | Schema-is-code; alias-swap promotion; per-stage score capture; security trimming patterns (as general-principle illustrations) |
| `.firecrawl/research/agentic-rag.md` | Agentic escalation ladder; reasoning-effort spectrum; activity-log observability; agentic eval obligations |
| `.firecrawl/synthesis/` (tooling-design-space, OPEN-QUESTIONS, supplemental-findings) | 10 design-space decisions; 8-mode failure taxonomy; gate severity model; build-order dependencies |
| cozy_RAG planning artifacts (`DECISIONS.md`, `.planning/`, `.staging/scorers/`) | Foundation-before-eval-before-promotion ordering; four canonical scorer patterns; hybrid env separation; promotion report / audit trail |
