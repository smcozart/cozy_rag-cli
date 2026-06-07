"""Opaque backend: managed retrieval evaluated end-to-end only.

For Claude offerings where retrieval is partially or fully managed —
claude.ai Projects knowledge, Agent SDK with a built-in retrieval tool, an
MCP connector you don't control — per-stage retrieval scores are invisible.

The methodology's degradation rule applies: degrade the DIAGNOSIS layer,
never the MEASUREMENT layer. This adapter sets supports_retrieval=False, so
the runner skips retrieval metrics (ndcg/recall) but still scores everything
observable end-to-end: groundedness, citation accuracy, refusal correctness,
completeness. Every gate still applies.

The "config version" for an opaque backend is the hash of everything you DO
control: system prompt, tool definitions, model id, and a corpus snapshot id.
swap() repoints which config bundle your application loads — reversion still
works, it just happens at the application config layer instead of an index alias.

If you own the MCP retrieval server, don't use this — implement the full
contract there and keep stage diagnostics.
"""

import hashlib
import json
from collections.abc import Callable
from typing import Any

from rag_method.contract import Answer, ScoredChunk, UnsupportedOperationError

AnswerFn = Callable[[str], Answer]


class OpaqueBackend:
    supports_retrieval = False

    def __init__(self, answer_fn: AnswerFn, config: dict[str, Any]) -> None:
        """config: the controllable surface — system_prompt, tools, model, corpus_snapshot."""
        self._answer_fn = answer_fn
        self._configs: dict[str, dict[str, Any]] = {}
        self._serving = self._register(config)

    def _register(self, config: dict[str, Any]) -> str:
        canonical = json.dumps(config, sort_keys=True, default=str).encode("utf-8")
        version_id = hashlib.sha256(canonical).hexdigest()[:12]
        self._configs[version_id] = config
        return version_id

    def apply(self, spec: dict[str, Any], env: str) -> str:
        self._serving = self._register(spec)
        return self._serving

    def retrieve(self, query: str, k: int = 10) -> list[ScoredChunk]:
        raise UnsupportedOperationError(
            "opaque backend: retrieval is managed and not observable; evaluate end-to-end"
        )

    def version(self) -> str:
        return self._serving

    def swap(self, version_id: str) -> None:
        if version_id not in self._configs:
            raise UnsupportedOperationError(f"unknown config version: {version_id}")
        self._serving = version_id

    @property
    def serving_config(self) -> dict[str, Any]:
        return self._configs[self._serving]

    def answer(self, query: str) -> Answer:
        return self._answer_fn(query)

    def as_generator(self) -> Callable[[str, list[ScoredChunk]], Answer]:
        """Adapts this backend to the runner's Generate protocol (chunks ignored)."""

        def generate(query: str, chunks: list[ScoredChunk]) -> Answer:
            return self._answer_fn(query)

        return generate
