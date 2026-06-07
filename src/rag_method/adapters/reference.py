"""Reference backend: pure-Python keyword retrieval over local files.

Exists for three reasons:
1. The kit must run end-to-end with zero credentials so the loop can be
   learned and tested before any vendor is involved.
2. It demonstrates the reversion architecture concretely: every apply()
   writes an immutable index under indexes/<version>/, and serving.txt is
   the pointer that swap() repoints. Rollback = repoint. Same pattern as
   Azure aliases or an Elasticsearch alias — just visible on disk.
3. Per methodology principle P8: below ~1M chunks, files + memory are often
   all you need. This adapter IS that claim, runnable.

Retrieval is TF-IDF-style keyword overlap (a simplified BM25). It is a real,
scoreable retriever — good enough to baseline against and to exercise every
scorer — not a production retriever.

Corpus format (JSONL): {"id": "...", "title": "...", "text": "...",
                        "metadata": {"effective_date": "...", "superseded_by": "..."}}
"""

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from rag_method.contract import BackendError, ScoredChunk

_TOKEN = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    "a an and are as at be but by for from has have i if in into is it its of on or that the "
    "their there these they this to was we what when where which who will with you your".split()
)


def _tokenize(text: str) -> list[str]:
    return [tok for tok in _TOKEN.findall(text.lower()) if tok not in _STOPWORDS]


class ReferenceBackend:
    supports_retrieval = True

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)
        self.indexes_dir = self.root / "indexes"
        self.pointer = self.root / "serving.txt"

    def apply(self, spec: dict[str, Any], env: str) -> str:
        corpus_section = spec.get("corpus")
        raw_path = (
            corpus_section.get("corpus_path")
            if isinstance(corpus_section, dict)
            else spec.get("corpus_path")
        )
        if not raw_path:
            raise BackendError("spec needs corpus_path (top-level or under `corpus:`)")
        corpus_path = Path(str(raw_path))
        if not corpus_path.exists():
            raise BackendError(f"corpus not found: {corpus_path}")
        corpus_bytes = corpus_path.read_bytes()
        spec_canonical = json.dumps(spec, sort_keys=True).encode("utf-8")
        version_id = hashlib.sha256(spec_canonical + corpus_bytes).hexdigest()[:12]

        index_dir = self.indexes_dir / version_id
        if not index_dir.exists():
            index_dir.mkdir(parents=True)
            docs = [
                json.loads(line)
                for line in corpus_bytes.decode("utf-8").splitlines()
                if line.strip()
            ]
            (index_dir / "docs.json").write_text(
                json.dumps(docs, ensure_ascii=False), encoding="utf-8"
            )
            (index_dir / "meta.json").write_text(
                json.dumps({"env": env, "spec": spec}, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        self.swap(version_id)
        return version_id

    def version(self) -> str:
        if not self.pointer.exists():
            raise BackendError("no version serving; run apply() first")
        return self.pointer.read_text(encoding="utf-8").strip()

    def swap(self, version_id: str) -> None:
        if not (self.indexes_dir / version_id).exists():
            raise BackendError(f"unknown version: {version_id}")
        self.pointer.write_text(version_id, encoding="utf-8")

    def list_versions(self) -> list[str]:
        if not self.indexes_dir.exists():
            return []
        return sorted(path.name for path in self.indexes_dir.iterdir() if path.is_dir())

    def retrieve(self, query: str, k: int = 10) -> list[ScoredChunk]:
        docs = self._serving_docs()
        n_docs = len(docs)
        doc_tokens = [_tokenize(doc.get("text", "")) for doc in docs]
        doc_freq: Counter[str] = Counter()
        for tokens in doc_tokens:
            doc_freq.update(set(tokens))

        query_tokens = _tokenize(query)
        scored: list[tuple[float, int]] = []
        for index, tokens in enumerate(doc_tokens):
            counts = Counter(tokens)
            score = sum(
                counts[tok] * math.log(1 + n_docs / doc_freq[tok])
                for tok in query_tokens
                if tok in counts
            )
            if score > 0:
                scored.append((score, index))
        scored.sort(key=lambda pair: -pair[0])

        results: list[ScoredChunk] = []
        for score, index in scored[:k]:
            doc = docs[index]
            metadata = {str(key): str(value) for key, value in (doc.get("metadata") or {}).items()}
            metadata.setdefault("doc_id", str(doc["id"]))
            metadata.setdefault("title", str(doc.get("title", "")))
            results.append(
                ScoredChunk(
                    chunk_id=str(doc["id"]),
                    text=str(doc.get("text", "")),
                    score=round(score, 4),
                    stage_scores={"l1_keyword": round(score, 4)},
                    metadata=metadata,
                )
            )
        return results

    def _serving_docs(self) -> list[dict[str, Any]]:
        index_dir = self.indexes_dir / self.version()
        docs_path = index_dir / "docs.json"
        loaded: list[dict[str, Any]] = json.loads(docs_path.read_text(encoding="utf-8"))
        return loaded
