# RAG Decision Record — <project>

> Phase 0 artifact. Resolve every decision below WITH RATIONALE before pipeline code.
> Once resolved, decisions are locked — re-litigating requires an explicit entry in the
> experiment log with new evidence. See METHODOLOGY.md Part III, Phase 0.

## D0. Is RAG the right tool?

<!-- Evidence from the decision tree: up-to-date cited facts -> RAG; style/tone -> fine-tune
     or prompt; fixed corpus <=200k tokens -> long-context + caching. If not RAG, stop. -->

## D1. Vertical vs horizontal

<!-- One use case, or a platform? Default: start vertical, design seams. -->

## D2. Backend strategy & lock-in posture

<!-- Primary backend + adapter seam. If any layer is managed/opaque (e.g. Claude Projects
     retrieval), record the degradation: end-to-end eval only, no stage diagnostics. -->

## D3. Classic vs agentic (initial posture)

<!-- Default: classic until measured query complexity justifies escalation (Phase 5 gate). -->

## D4. Chunking profile(s)

<!-- Decided EMPIRICALLY in Phases 2-3. Record the candidate profiles here now;
     record the winning experiment in the log below. -->

## D5. Embedding model

<!-- Model + dimensions + MTEB evidence (task class, language). Record the re-embed plan:
     changing this later means re-embedding the corpus — a workflow, not an emergency. -->

## D6. Eval stack

<!-- Frameworks + custom scorers. Custom scorers: deterministic and cheap by default. -->

## D7. Gate severities

<!-- Which metrics hard-block, which advise, and the thresholds. Mirror in gates.yaml. -->

## D8. Tenancy

<!-- Default: single-tenant with tenant_id present in all metadata (free upgrade path).
     If multi-tenant: cross-tenant leakage tests are non-negotiable hard blocks. -->

## D9. Environments

<!-- Topology (e.g. shared dev/staging, dedicated prod) + why. -->

## D10. Promotion approvals

<!-- Default: dev->staging auto on green gates; staging->prod manual with promotion report. -->

---

## Corpus exploration notes (Phase 0, do by hand — do not delegate)

<!-- Document structure, size distribution, freshness dynamics (supersession?), vocabulary
     (exact identifiers vs natural language). Trace 5-10 real queries to their answering docs. -->

## Query population characterization

<!-- Simple lookups? Compound/multi-hop? Multi-turn? Time-sensitive? This decides which
     adversarial modes matter most and whether Phase 5 will ever be justified. -->
