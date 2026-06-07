"""The backend contract: the seam that makes the methodology portable.

Every backend (Azure AI Search, LanceDB, pgvector, a Claude/MCP retrieval tool,
or plain files) is wrapped to expose four operations:

    apply(spec, env)   -> deploy configuration reproducibly, return immutable version id
    retrieve(query, k) -> scored chunks, with per-stage scores where the backend exposes them
    version()          -> the config/index version currently serving
    swap(version_id)   -> atomically repoint serving to a version (this IS reversion)

Degradation rule: when a backend is partially opaque (managed retrieval where
per-stage scores are invisible), set `supports_retrieval = False` and evaluate
end-to-end only. You lose stage diagnostics; you never lose the gates.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class ScoredChunk:
    chunk_id: str
    text: str
    score: float
    stage_scores: dict[str, float] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def doc_id(self) -> str:
        return self.metadata.get("doc_id", self.chunk_id)

    @property
    def title(self) -> str:
        return self.metadata.get("title", "")


@dataclass(frozen=True)
class Citation:
    title: str
    section: str = ""
    page: str = ""


@dataclass(frozen=True)
class Answer:
    text: str
    citations: tuple[Citation, ...] = ()
    refused: bool = False


@runtime_checkable
class Backend(Protocol):
    supports_retrieval: bool

    def apply(self, spec: dict[str, object], env: str) -> str: ...

    def retrieve(self, query: str, k: int = 10) -> list[ScoredChunk]: ...

    def version(self) -> str: ...

    def swap(self, version_id: str) -> None: ...


class Generate(Protocol):
    """The answer layer. Receives the query and retrieved chunks, returns an Answer.

    For opaque backends (supports_retrieval=False), chunks will be an empty
    sequence and the generator owns retrieval internally.
    """

    def __call__(self, query: str, chunks: Sequence[ScoredChunk]) -> Answer: ...


class BackendError(Exception):
    """Raised by adapters for contract-level failures."""


class UnsupportedOperationError(BackendError):
    """Raised when an opaque backend cannot honor a contract operation."""
