#!/usr/bin/env bash
# Scaffold a new RAG project from the methodology template.
# Usage: scripts/new-project.sh <target-dir> [project-name]
set -euo pipefail

TARGET="${1:?usage: new-project.sh <target-dir> [project-name]}"
NAME="${2:-$(basename "$TARGET")}"
KIT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -d "$TARGET" ] && [ -n "$(ls -A "$TARGET" 2>/dev/null)" ]; then
    echo "Target exists and is not empty: $TARGET" >&2
    exit 1
fi
mkdir -p "$TARGET"

cp -r "$KIT_ROOT/template/." "$TARGET/"
cp "$KIT_ROOT/METHODOLOGY.md" "$KIT_ROOT/CHECKLIST.md" "$TARGET/"

for file in DECISIONS.md EXPERIMENTS.md rag-spec.yaml; do
    sed -i.bak "s/<project>/$NAME/g" "$TARGET/$file" && rm -f "$TARGET/$file.bak"
done

mkdir -p "$TARGET/evals/runs" "$TARGET/data"
git -C "$TARGET" init >/dev/null

echo "Scaffolded '$NAME' at $TARGET"
echo "Next: Phase 0 — open DECISIONS.md and CHECKLIST.md. Harness: pip install rag-method (or uv add)."
