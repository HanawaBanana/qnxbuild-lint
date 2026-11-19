#!/usr/bin/env python3
"""Lint the downloaded BSP corpus and fail if it produces any diagnostic.

A vendor file that trips a rule is either a real bug in the vendor file or a
false positive in this linter; both must be explained before release, so the
check is strict.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qnxbuild_lint.buildfile import lint_source  # noqa: E402
from qnxbuild_lint.makefile import lint_tree  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / ".corpus"


def main() -> int:
    if not CORPUS.is_dir():
        print("corpus missing: run tools/fetch_corpus.py first", file=sys.stderr)
        return 2
    buildfiles = sorted(CORPUS.rglob("*.build"))
    makefiles = sum(1 for path in CORPUS.rglob("*") if path.is_file()) - len(buildfiles)
    diagnostics: list[str] = []
    for path in buildfiles:
        text = path.read_text(encoding="utf-8", errors="replace")
        for diagnostic in lint_source(text, str(path)).diagnostics:
            diagnostics.append(
                f"{path}:{diagnostic.line}:{diagnostic.col}: {diagnostic.severity} "
                f"[{diagnostic.rule}] {diagnostic.message}"
            )
    for diagnostic in lint_tree(str(CORPUS)):
        diagnostics.append(
            f"{diagnostic.line}:{diagnostic.col}: {diagnostic.severity} "
            f"[{diagnostic.rule}] {diagnostic.message}"
        )

    for line in diagnostics:
        print(line)
    print(f"{len(buildfiles)} buildfiles, {makefiles} other files, {len(diagnostics)} diagnostics")
    return 0 if not diagnostics else 1


if __name__ == "__main__":
    raise SystemExit(main())
