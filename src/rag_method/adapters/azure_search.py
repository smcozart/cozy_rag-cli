"""Azure AI Search adapter: contract binding map.

This is intentionally a stub. The full-featured Azure binding — schema-as-code
with linting, alias-based promotion, eval-gated promote/rollback, activity-log
replay — is the cozy_RAG project (D:/dev/cozy_RAG). Use it rather than
reimplementing here.

Contract -> Azure mapping (what an implementation does):

  apply(spec, env)   Render spec to index + skillset + scoring-profile JSON,
                     PUT via the Search REST API against the env's service.
                     Version id = content hash of the rendered resources;
                     create index under a versioned name `<base>-<hash>`.
  retrieve(query,k)  POST /indexes/<alias>/docs/search with hybrid config.
                     Map per-stage scores: @search.score -> stage_scores["l1"],
                     @search.rerankerScore -> stage_scores["l2"].
  version()          Resolve the serving alias -> versioned index name.
  swap(version_id)   PUT the alias to point at `<base>-<version_id>` (atomic,
                     zero-downtime; the previous index is the rollback target).
"""

from typing import Any

from rag_method.contract import ScoredChunk, UnsupportedOperationError


class AzureSearchBackend:
    supports_retrieval = True

    def __init__(self, endpoint: str, index_base_name: str) -> None:
        self.endpoint = endpoint
        self.index_base_name = index_base_name

    def apply(self, spec: dict[str, Any], env: str) -> str:
        raise UnsupportedOperationError(
            "AzureSearchBackend is a binding map, not an implementation. "
            "Use cozy_RAG (`cozy_rag apply --env <env>`) for the full Azure binding."
        )

    def retrieve(self, query: str, k: int = 10) -> list[ScoredChunk]:
        raise UnsupportedOperationError("see class docstring — use cozy_RAG")

    def version(self) -> str:
        raise UnsupportedOperationError("see class docstring — use cozy_RAG")

    def swap(self, version_id: str) -> None:
        raise UnsupportedOperationError("see class docstring — use cozy_RAG")
