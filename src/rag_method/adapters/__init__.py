"""Backend adapters. Each binds the four-operation contract to a stack.

- reference:     pure-Python keyword retriever over local files. Zero credentials,
                 fully working. Demonstrates immutable versions + pointer-swap
                 reversion, and doubles as the "custom code" example.
- azure_search:  binding map for Azure AI Search. Stub — use cozy_RAG for the
                 full implementation (schema-as-code, aliases, eval gates).
- claude_opaque: wraps a managed/agentic answer function (Claude Projects,
                 Agent SDK + retrieval tool, MCP connector) as an end-to-end-only
                 backend, per the methodology's degradation rule.
"""

from rag_method.adapters.claude_opaque import OpaqueBackend
from rag_method.adapters.reference import ReferenceBackend

__all__ = ["OpaqueBackend", "ReferenceBackend"]
