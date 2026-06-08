# rag-method

**RAG development as an enforced process, not a vibe.** A stack-agnostic methodology kit +
CLI for building retrieval-augmented generation systems with measurable quality: scaffolded
decision records, versioned eval datasets, declarative gates, one-command A/B experiments,
and built-in reversion — identical across Azure AI Search, open-source/custom pipelines, and
managed offerings like Claude retrieval.

```
rag-method baseline      ->  apply spec, run all eval datasets, record the denominator
rag-method experiment    ->  apply -> run -> diff -> gates -> KEPT or auto-REVERTED -> ledger row
rag-method promote       ->  eval-gated, report-backed promotion between environments
rag-method rollback      ->  repoint serving to the previous kept version, in seconds
```

## Why

Most RAG development is "chuck everything into a vector database and check off of vibes."
Without ground truth you can't tell whether a change helped; without pinned config your
baseline silently invalidates itself; without an enforced sequence every project does it
differently. This kit encodes the alternative:

- **No tuning before measurement; no measurement without reproducibility.** Ground-truth
  eval sets and config-as-code are scaffolded before any pipeline tuning.
- **Change one variable, measure the delta.** `experiment` is the only way changes land,
  and it writes the ledger row whether the change is kept or reverted — the log cannot
  drift from reality.
- **Promotion is gated by measured quality, not opinion.** Hard-block gates veto and
  auto-revert; advisory gates warn.
- **Production ALWAYS has a human in the loop — as a guarantee, not a setting.** Envs
  named `prod`/`production`/`prd`/`live` (or marked `protected: true`) ignore
  `auto_on_green`. Approval is bound to the specific candidate version hash from the
  reviewed promotion report — if the spec changed since review, the hash changed and the
  approval is void. There is no flag that ships "whatever is current" to production.
- **Reversion is an architectural property, not a feature.** Configs are immutable
  content-hashed versions; serving is a pointer; rollback is one swap.

The machine owns *sequence and bookkeeping*. The architect owns *decisions* — which
variable to change, where the thresholds sit, whether prod ships.

The full process contract lives in [METHODOLOGY.md](METHODOLOGY.md): 8 operating
principles, 7 gated phases (Frame → Foundation → Baseline → Retrieval → Generation →
Agentic → Operate), an 8-mode failure taxonomy, and the anti-patterns each phase exists to
prevent. [CHECKLIST.md](CHECKLIST.md) is the one-page version for active use.
Retrofitting an **existing** RAG system instead of starting fresh? Start with
[ADOPTION.md](ADOPTION.md) — the phases run in reverse (document backward, wrap, baseline
the incumbent, ratchet gates) via an L0→L3 adoption ladder.

## Status — honest scope (v0.1)

| Layer | State |
|---|---|
| Process engine (CLI, workflow, runner, gates, diff, state, auto-ledger) | **Working, tested** (pytest + live exercise, Windows & Linux CI) |
| Deterministic scorers (ndcg/recall/precision/mrr, citation accuracy, groundedness, completeness, recency) | **Working, tested** |
| Reference backend (pure-Python keyword retrieval, immutable versions + pointer-swap) | **Working, tested** — zero credentials needed |
| Opaque backend (managed/Claude retrieval, end-to-end-only eval per the degradation rule) | **Working, tested** with a stubbed answer fn; not yet exercised against a live LLM |
| Azure AI Search adapter | **Binding map only** — documents the exact contract→Azure mapping; full implementation is the cozy_RAG project |
| LLM-judge scorers (RAGAS-style faithfulness etc.) | Not included yet — deterministic scorers only, by design first |

Translation: the *process* is real and runnable today end-to-end against the reference
backend. Binding it to your production stack means implementing the four-operation
contract for that stack (see below) — that's the per-project work the kit deliberately
isolates into one file.

## Quickstart

```bash
git clone https://github.com/smcozart/cozy_rag-cli && cd cozy_rag-cli
uv run --extra dev pytest tests/ -q        # prove the loop works on your machine

# scaffold a new on-method project
scripts/new-project.sh ~/dev/my-rag my-rag         # or scripts\new-project.ps1 on Windows
cd ~/dev/my-rag && uv init --bare && uv add <path-or-git-ref-to-rag-method>
```

Then work the phases:

1. **Phase 0 — Frame.** Fill `DECISIONS.md` (D0–D10) and explore your corpus *by hand*.
   No pipeline code yet. This is the methodology's load-bearing discipline.
2. **Phase 1 — Foundation.** Put your corpus reference and every quality-affecting setting
   in `rag-spec.yaml`. Replace the placeholders in `evals/datasets/` (golden + 8-mode
   adversarial + unanswerable). Set `gates.yaml` thresholds from requirements.
3. **Phase 2 — Baseline.**

   ```bash
   rag-method status          # warns about remaining placeholders
   rag-method baseline        # version a3f81c2e9b04 — all metrics recorded
   ```

4. **Phases 3–4 — Optimize.** Edit ONE variable in `rag-spec.yaml`, then:

   ```bash
   rag-method experiment "chunking: layout->contextual"
   # KEPT: a3f81c2e9b04 -> f7a16d1b235f          (or REVERTED: serving swapped back)
   #   [PASS] ndcg@10 (threshold: >= 0.5, actual 0.61)
   #   ndcg@10: 0.54 -> 0.61 (+0.07)
   #   worst per-question regressions: ...
   # EXPERIMENTS.md row appended
   ```

   Enable the Phase 4 gate block in `gates.yaml` once `pipeline.py` has a `generate()`.
5. **Phase 6 — Operate.**

   ```bash
   rag-method promote --to staging              # auto on green
   rag-method promote --to prod                 # builds + validates candidate; PENDING APPROVAL + report
   rag-method promote --to prod --approve <id>  # human ships THAT reviewed candidate, and only that one
   rag-method rollback                          # seconds, reversible
   ```

## The backend contract

Every stack binds to four operations — this is the seam that makes the process portable:

```python
apply(spec, env)   -> str    # deploy config reproducibly; return immutable version id
retrieve(query, k) -> list[ScoredChunk]   # with per-stage scores where observable
version()          -> str    # what's serving right now
swap(version_id)   -> None   # atomically repoint serving (this IS reversion)
```

| Contract op | Azure AI Search | Custom code (LanceDB/pgvector/files) | Claude offerings (Projects / Agent SDK / MCP) |
|---|---|---|---|
| `apply` | Index/skillset PUT from spec; versioned index name | Builder writes versioned table/dir | Hash of prompt + tools + model + corpus snapshot |
| `retrieve` | Hybrid query; `@search.score`→l1, `rerankerScore`→l2 | Your pipeline, full stage visibility | Your MCP server (full contract) **or** opaque |
| `version` | Alias target | Pointer file | Serving config hash |
| `swap` | Alias swap (atomic) | Repoint pointer file | Repoint config bundle |

**Degradation rule** for managed/opaque retrieval: degrade the *diagnosis* layer, never the
*measurement* layer. Retrieval-relative metrics go absent (not zero); end-to-end gates
(refusal correctness, completeness, latency) still apply. Record the trade in
`DECISIONS.md` D2.

Each project supplies exactly one binding file, `pipeline.py`:

```python
def build_backend(env: dict) -> Backend: ...          # required
def generate(query, chunks) -> Answer: ...            # optional; omit for retrieval-only evals
```

Swap stacks by changing that file. The commands — and therefore the process — stay identical.

## How performance is tracked

- **Run records** (`evals/runs/*.json`) — machine layer. Every eval pins config version,
  dataset, k; carries aggregate metrics, per-tag breakdowns (incl. per-failure-mode),
  per-question scores, and latency (mean/p95). Files in git = replayable history.
- **`EXPERIMENTS.md`** — human layer. Append-only ledger of decisions, written by the tool.
- **`gates.yaml`** — policy layer. Thresholds + severities + regression rules, versioned,
  so "what does it take to ship" is never tribal knowledge.

## Repo layout

```
METHODOLOGY.md            the process contract (read this first)
ADOPTION.md               brownfield retrofit guide (existing systems, L0-L3 ladder, Azure JSON)
CHECKLIST.md              one-page working checklist
src/rag_method/
  cli.py  workflow.py     the encoded process (commands, sequence, state, ledger)
  contract.py             the four-op backend protocol + Answer/Citation types
  runner.py gates.py diff.py
  scorers/                deterministic scorers
  adapters/               reference (working) / azure_search (map) / claude_opaque (working)
template/                 scaffolded into every new project (artifacts, datasets, pipeline.py)
scripts/new-project.*     scaffolder (PowerShell + bash)
tests/                    smoke + full workflow (baseline→keep→auto-revert→promote→rollback)
```

## Roadmap

- `rag-method sweep` — run a list of spec variants, emit the comparison table (Phase 3's
  candidate ladder as one invocation)
- Worked example with a live LLM `generate()` (Claude) and a dense/hybrid custom backend
- LLM-judge scorer seam (RAGAS adapter) alongside the deterministic set
- Azure binding via [cozy_RAG](https://github.com/smcozart) as it matures
- Online A/B helpers (traffic split by version id, per-version production metrics)

## Provenance

Synthesized from Dave Ebbelaar's hybrid-retrieval methodology (BM25 + dense + RRF +
rerank, NDCG-driven), the BEIR ground-truth pattern, Anthropic's contextual-retrieval
findings (Sep 2024), an 8-mode failure taxonomy extended from Faktion's enterprise RAG
failure-mode case studies, and the schema-as-code / eval-gated promotion design of the
cozy_RAG project. Full source map in METHODOLOGY.md (Provenance).

## License

MIT — see [LICENSE](LICENSE).
