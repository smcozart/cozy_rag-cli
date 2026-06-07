"""rag-method: stack-agnostic harness for the RAG Development Methodology.

Consistency across backends comes from three things:
- the artifact set (DECISIONS.md, rag-spec.yaml, evals/, gates.yaml, EXPERIMENTS.md)
- the backend contract (apply / retrieve / version / swap)
- the loop (eval run -> diff -> gates -> keep-or-revert)

This package implements the contract types and the loop. Backends bind via adapters.
"""

from rag_method.contract import Answer, Backend, Citation, Generate, ScoredChunk
from rag_method.diff import diff_runs
from rag_method.gates import evaluate_gates, load_gates
from rag_method.runner import run_eval, save_run

__all__ = [
    "Answer",
    "Backend",
    "Citation",
    "Generate",
    "ScoredChunk",
    "diff_runs",
    "evaluate_gates",
    "load_gates",
    "run_eval",
    "save_run",
]
