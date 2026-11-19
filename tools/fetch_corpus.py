#!/usr/bin/env python3
"""Download real QNX BSP buildfiles and Makefiles into ``.corpus/``.

The files are fetched at check time instead of being vendored: the BSPs carry
their own licence and this project only needs them as a false-positive oracle.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPOS = (
    "qnx/bsp_raspberrypi-bcm2712-rpi5",
    "qnx/bsp_raspberrypi-bcm2711-rpi4",
)
KEEP_NAMES = {"Makefile", "recurse.mk", "common.mk"}
DEST = Path(__file__).resolve().parents[1] / ".corpus"
UA = {"User-Agent": "qnxbuild-lint-corpus"}


def fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main() -> int:
    total = 0
    for repo in REPOS:
        tree_url = f"https://api.github.com/repos/{repo}/git/trees/main?recursive=1"
        try:
            tree = json.loads(fetch(tree_url))
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"skip {repo}: {exc}", file=sys.stderr)
            continue
        wanted = [item["path"] for item in tree.get("tree", []) if item["type"] == "blob"]
        def download(path: str) -> bool:
            target = DEST / repo.replace("/", "__") / path
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                target.write_bytes(fetch(f"https://raw.githubusercontent.com/{repo}/main/{path}"))
                return True
            except Exception as exc:  # noqa: BLE001
                print(f"skip {repo}/{path}: {exc}", file=sys.stderr)
                return False

        with ThreadPoolExecutor(max_workers=16) as pool:
            total += sum(1 for ok in pool.map(download, wanted) if ok)
        print(f"{repo}: {len(wanted)} candidate files")
    print(f"corpus written to {DEST}: {total} files")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
