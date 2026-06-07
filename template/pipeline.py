"""Project pipeline binding — the ONE per-project file the rag-method CLI needs.

Everything else is declarative (rag-spec.yaml, gates.yaml, envs/, datasets).
This file binds the contract to your stack:

    build_backend(env) -> Backend     required
    generate(query, chunks) -> Answer optional — omit to evaluate retrieval only

Swap the body of build_backend when you change stacks; the process commands
(baseline / experiment / promote / rollback) stay identical.
"""

from pathlib import Path
from typing import Any

from rag_method.adapters import ReferenceBackend
from rag_method.contract import ScoredChunk  # noqa: F401  (used by generate signature)


def build_backend(env: dict[str, Any]):
    name = env.get("backend", "reference")
    if name == "reference":
        # Pure-Python local backend: serving pointer + immutable indexes on disk.
        return ReferenceBackend(Path("serving") / str(env["env"]))
    if name == "azure_search":
        # Bind via cozy_RAG (schema-as-code, aliases, activity logs) and wrap
        # its operations in the four-op contract. See adapters/azure_search.py
        # for the exact mapping.
        raise NotImplementedError("wire the Azure binding here (see cozy_RAG)")
    if name == "opaque":
        # Managed retrieval (Claude Projects / Agent SDK retrieval tool / MCP
        # connector you don't control): wrap your answer function.
        #   from rag_method.adapters import OpaqueBackend
        #   return OpaqueBackend(answer_fn=my_call, config={...env-controlled surface...})
        raise NotImplementedError("wire your managed answer function here")
    raise ValueError(f"unknown backend in env binding: {name}")


# def generate(query: str, chunks: list[ScoredChunk]) -> Answer:
#     """Your answer layer: call your LLM with the retrieved chunks, return an
#     Answer with citations (and refused=True when grounding is insufficient).
#     Omit this function entirely to run retrieval-only evals (Phases 2-3)."""
#     ...
