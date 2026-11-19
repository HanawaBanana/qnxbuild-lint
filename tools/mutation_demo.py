#!/usr/bin/env python3
"""Mutation demo: inject the classic QNX build breaks into a real BSP buildfile
and show that qnxbuild-lint catches every one of them.

Usage:
    python3 tools/mutation_demo.py .corpus/qnx__bsp_raspberrypi-bcm2712-rpi5/images/rpi5.build
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qnxbuild_lint.buildfile import lint_source  # noqa: E402

# (name, line to insert or replace, expected rule)
MUTATIONS: list[tuple[str, str, str]] = [
    ("boolean attribute written as a value", "[raw=1] usr/bin/toy", "ATTR_KIND"),
    ("value attribute written as a flag", "[+uid] usr/bin/toy", "ATTR_KIND"),
    ("two attribute groups on one line", "[uid=0] [gid=0] usr/bin/toy", "ATTR_SPLIT_GROUPS"),
    ("undocumented attribute name", "[uid=0 gidz=0] usr/bin/toy", "ATTR_UNKNOWN"),
    ("type= value outside link/fifo/file/dir", "[type=hardlink] usr/bin/toy", "ATTR_BAD_TYPE"),
    ("symlink without a target", "[type=link] usr/bin/toy", "LINK_NEEDS_TARGET"),
    ("same image path written twice", "[uid=0] usr/bin/toy\n[uid=1000] usr/bin/toy", "FILE_DUPLICATE_TARGET"),
]


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    base = Path(argv[1]).read_text(encoding="utf-8", errors="replace")
    print(f"base file: {argv[1]}")
    print(f"baseline diagnostics: {len(lint_source(base).diagnostics)}")

    failures = 0
    for name, snippet, expected in MUTATIONS:
        mutated = base + "\n" + snippet + "\n"
        found = {d.rule for d in lint_source(mutated).diagnostics} - {d.rule for d in lint_source(base).diagnostics}
        ok = expected in found
        failures += 0 if ok else 1
        print(f"{'caught ' if ok else 'MISSED '} {expected:22s} {name}")
    print(f"\n{len(MUTATIONS) - failures}/{len(MUTATIONS)} mutations caught")
    return 0 if failures == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
