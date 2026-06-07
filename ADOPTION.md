# ADOPTION.md — Retrofitting the Methodology onto Pre-Existing RAG Systems

METHODOLOGY.md describes the greenfield path. Most real systems aren't greenfield.
This guide covers the brownfield path: an existing RAG system gets **wrapped, measured,
and then improved under gates** — never rebuilt. The phases stay the same; their
direction reverses. Instead of designing forward, you document backward until the
incumbent system is simply *config version #1* in the experiment history.

---

## The Retrofit Sequence

### 1. Phase 0 becomes archaeology, not framing

Fill `DECISIONS.md` D0–D10 **retroactively** — document the decisions the system already
embodies: which chunking, which embedding model, which backend, what tenancy model.

- **Every blank you cannot fill is a decision that was made by default** — which is the
  methodology's definition of a tuning candidate. The retroactive decision record IS your
  experiment backlog, pre-prioritized.
- The hands-on corpus exploration still happens, and is usually *more* revealing on
  brownfield: most teams running an existing RAG have never manually traced ten real
  queries to the documents that should answer them.

### 2. `rag-spec.yaml` is extracted, not authored

Pull every quality-affecting setting out of the live system into the spec. The spec
starts **descriptive** (what *is*) before it becomes prescriptive (what *should be*).

Expect this step to surface its own finding: dev and prod configs have drifted, and
nobody knew. That discovery alone routinely pays for the retrofit.

### 3. `pipeline.py` wraps the existing system — via the adoption ladder

The four-op contract does not demand full automation on day one. Climb:

| Rung | What's wired | What you get |
|---|---|---|
| **L0** | `version()` = hash of the extracted spec | Version *identity* — runs become attributable |
| **L1** | `retrieve()` calls the existing search endpoint; scores mapped into `ScoredChunk` | **The full eval loop works.** Baseline, experiments, diffs, gates — config changes still applied by hand |
| **L2** | `apply()` actually deploys config (always to a NEW versioned index/resource) | Experiments become one command end-to-end |
| **L3** | `swap()` wired (alias / pointer / config bundle) | Built-in reversion and gated promotion |

**Measurement value arrives at L1, which is cheap** — typically a day, since it calls an
endpoint you already have. If a layer is managed/opaque (vendor retrieval you can't see
into), apply the degradation rule via `OpaqueBackend`: end-to-end metrics only, every
gate still applies.

### 4. Baseline the incumbent — the single highest-value move

`rag-method baseline` against the wrapped system gives it the first ground-truth
measurement it has ever had. Brownfield has a genuine *advantage* here: **production
query logs exist.** Build eval datasets from:

- **Real user queries** (sampled, PII-scrubbed) → golden + regression sets. Labeling
  the qrels (`relevant_doc_ids`) is the real human work — synthetic generation can
  propose candidate documents, but a human confirms each one.
- **Synthetic generation** over the existing corpus to fill coverage gaps.
- **The complaint history** → adversarial set. Failures users actually reported are a
  pre-built adversarial pack; map each to its mode in the 8-mode taxonomy.

### 5. Gates ratchet from reality, not aspiration

Do **not** set `groundedness: 0.95` on a system that measures 0.61 — every experiment
will revert forever and the team abandons the tooling. Instead:

- **Initial hard-blocks = "never get worse than today"**: regression gates against the
  measured baseline (`max_drop: 0.00`).
- Threshold gates start at or just above the baseline, then **ratchet upward as
  experiments win**. After each kept experiment, consider raising the floor to the new
  level.
- Record destination thresholds in `DECISIONS.md` D7; `gates.yaml` tracks the current
  rung of the ratchet.

### 6. From here, the loop is identical to greenfield

Edit one variable → `rag-method experiment` → keep-or-revert → ledger row. The safety
property that makes experimenting on a production system sane:

> **`apply()` always builds a NEW index/resource under a versioned name — it never
> mutates the live one.** The incumbent keeps serving untouched while challengers are
> measured against it. Promotion is the pointer swap; reversion is the reverse swap.

---

## Greenfield vs. Brownfield — what changes

| | Greenfield | Brownfield |
|---|---|---|
| Phase 0 | Frame decisions forward | Excavate decisions backward; blanks = experiment backlog |
| Spec | Authored | Extracted (drift discovery is a free finding) |
| Phase 2 baseline | Simplest pipeline you build | The incumbent, as-is |
| Eval data | Synthetic-first | **Production-logs-first (advantage)** |
| Gates | From requirements | Ratchet from measured reality |
| `apply()` | Full from day one | Adoption ladder L0→L3 |

---

## Worked Binding: Azure AI Search (config lives in JSON files)

Azure AI Search configuration is REST-resource JSON: index definition, skillset,
indexer, scoring profiles, semantic configuration, aliases. Two sound patterns for
fitting that into the kit — pick by where your team already keeps truth:

### Pattern A — spec renders the JSON (greenfield / cozy_RAG style)

`rag-spec.yaml` is the single source; `apply()` renders the Azure JSON payloads from it
and PUTs them. Best when starting clean — one file to edit, the linter can enforce
cross-resource rules (vector dimensions match the embedding model, scoring-profile
fields are filterable, etc.). This is the cozy_RAG schema-as-code design.

### Pattern B — the JSON files ARE the spec (brownfield default)

If the team already maintains `index.json` / `skillset.json` in the repo (or you just
exported them from the live service), don't force a translation layer. Reference them:

```yaml
# rag-spec.yaml
azure:
  index_definition: search/index.json        # the Azure REST payloads, verbatim
  skillset: search/skillset.json
  indexer: search/indexer.json
  api_version: "2025-11-01-preview"

retrieval:                                    # query-time knobs NOT stored in Azure JSON
  mode: hybrid
  candidates_per_arm: 50
  semantic_config: default
  rerank: {enabled: true, final_top: 10}
```

**The version hash must cover the referenced file contents, not just the YAML.**
`apply()` canonicalizes spec + every referenced JSON file and hashes the lot (the
reference adapter does exactly this with spec + corpus bytes). An edit to `index.json`
alone produces a new config version — which is what makes `experiment` correctly detect
"you changed something" vs. "config hash unchanged."

### The contract ops in Azure terms

| Op | Azure mechanics |
|---|---|
| `apply(spec, env)` | Compute version hash → if new, PUT index as **`{base}-{hash}`** (a NEW index, never the serving one), PUT skillset, run the indexer to populate it. Return the hash. The serving alias is untouched. |
| `retrieve(query, k)` | POST `/indexes/{target}/docs/search` with hybrid config. Map `@search.score` → `stage_scores["l1"]`, `@search.rerankerScore` → `stage_scores["l2"]`. |
| `version()` | GET the alias → which versioned index it points at. |
| `swap(version_id)` | PUT the alias to `{base}-{version_id}`. Atomic, zero-downtime; the previous index is the rollback target (keep per retention policy, e.g. 48h). |

### Three Azure-specific realities to plan for

1. **Candidate evaluation must target the candidate index by name, not the alias.**
   During an experiment, the alias still serves the incumbent. `retrieve()` should hit
   the index `apply()` just built (`{base}-{hash}`), so the eval measures the challenger
   while production traffic is untouched. Only `swap()` moves the alias.

2. **Reindex time makes `experiment` asynchronous in practice.** Building and populating
   a candidate index takes minutes-to-hours depending on corpus size and skillset cost.
   Batch index-level experiments deliberately (chunking, analyzers, vector dims);
   query-time experiments (k, hybrid weights, semantic config selection, reranker
   settings) need **no reindex** — same index, new query parameters, near-instant. The
   version hash distinguishes the two automatically because query-time knobs live in
   the YAML layer.

3. **Portal drift detection comes free.** Since `apply()` knows the canonical JSON, a
   `GET` of the live index definition diffed against the repo's JSON catches anyone who
   "just clicked something" in the Azure portal. Run the diff at the start of `baseline`
   and `experiment`; a mismatch means your version identity is lying — stop and
   reconcile before measuring. (In-place-updatable changes like adding a field can PATCH
   the live index; anything touching vector dimensions, analyzers, or field deletion
   requires the rebuild-and-swap path. When in doubt, rebuild — versioned indexes make
   rebuild the safe default.)

The full-featured Azure implementation of all of the above (linting, migration diffs,
activity-log replay) is the **cozy_RAG** project; this kit's `AzureSearchBackend` stub
documents the mapping and delegates there.

---

## Honest caveats

- If retrieval logic is buried inside application code rather than behind an endpoint,
  extracting a callable `retrieve()` may need a small refactor first — the most common
  L1 blocker.
- Chunking/embedding experiments on brownfield carry reindex cost; batch them.
- Labeling qrels from production logs is real human work (hours, not minutes). It is
  also the single best investment in the whole retrofit.

## Fleet note (multiple existing systems)

Each system gets the five artifacts and its own `pipeline.py`. Because run records share
one format, you gain something greenfield can't offer: **cross-system comparison** —
system A's groundedness vs. system B's, under identical metric definitions, from one
`evals/runs/` convention.
