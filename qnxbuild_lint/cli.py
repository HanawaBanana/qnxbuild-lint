"""Command line interface for qnxbuild-lint."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__
from .buildfile import Diagnostic, lint_source
from .makefile import lint_tree

RULES: dict[str, str] = {
    "ATTR_KIND": "boolean and value attributes were written in the wrong form (+x vs x=y)",
    "ATTR_UNKNOWN": "attribute name is not in the mkifs attribute list",
    "ATTR_EMPTY_VALUE": "value attribute given an empty value",
    "ATTR_BAD_TYPE": "type= value is not one of link/fifo/file/dir",
    "ATTR_BARE": "attribute token has neither a +/- prefix nor =value",
    "ATTR_CONFLICT": "contradicting attributes in one group, e.g. [+raw -raw]",
    "ATTR_DUPLICATE": "the same attribute appears twice in one group",
    "ATTR_NOT_LEADING": "attribute group does not start the line",
    "ATTR_SPLIT_GROUPS": "two attribute groups on one line; mkifs accepts only one",
    "LINK_NEEDS_TARGET": "[type=link] needs a name=target file specification",
    "FILE_DUPLICATE_TARGET": "two entries write the same path; mkifs silently keeps the last",
    "MAKE_MISSING_INCLUDE": "included makefile does not exist (and is not -include)",
    "MAKE_MISSING_VARIANT_DIR": "LIST= variable names a directory that does not exist",
    "MAKE_CYCLE": "include/recursion cycle would make the build loop",
    "MAKE_SPACE_RECIPE": "recipe line indented with spaces; make aborts 'missing separator'",
    "MAKE_DUP_RECIPE": "target defined with more than one recipe",
    "MAKE_ORPHAN_RECIPE": "recipe line with no preceding rule",
    "MAKE_UNREADABLE": "makefile could not be read",
}


def _collect(paths: list[str]) -> list[tuple[str, Diagnostic]]:
    results: list[tuple[str, Diagnostic]] = []
    for entry in paths:
        if os.path.isdir(entry):
            for path, diagnostic in _lint_dir(entry):
                results.append((path, diagnostic))
        elif os.path.isfile(entry):
            text = open(entry, encoding="utf-8", errors="replace").read()
            for diagnostic in lint_source(text, entry).diagnostics:
                results.append((entry, diagnostic))
        else:
            results.append(
                (
                    entry,
                    Diagnostic("IO_MISSING", "error", 0, 0, f"no such file or directory: {entry}"),
                )
            )
    return results


def _lint_dir(root: str) -> list[tuple[str, Diagnostic]]:
    out: list[tuple[str, Diagnostic]] = []
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in sorted(filenames):
            if not name.endswith(".build"):
                continue
            path = os.path.join(dirpath, name)
            text = open(path, encoding="utf-8", errors="replace").read()
            for diagnostic in lint_source(text, path).diagnostics:
                out.append((path, diagnostic))
    for diagnostic in lint_tree(root):
        out.append((diagnostic.message.split(":")[0] if ":" in diagnostic.message else root, diagnostic))
    return out


def _render_text(results: list[tuple[str, Diagnostic]]) -> str:
    lines = []
    for path, diagnostic in sorted(results, key=lambda item: (item[0], item[1].line, item[1].col)):
        lines.append(
            f"{path}:{diagnostic.line}:{diagnostic.col}: {diagnostic.severity} "
            f"[{diagnostic.rule}] {diagnostic.message}"
        )
    return "\n".join(lines)


def _render_json(results: list[tuple[str, Diagnostic]]) -> str:
    payload = {
        "version": __version__,
        "diagnostics": [
            {"file": path, **diagnostic.as_dict()} for path, diagnostic in results
        ],
        "summary": {
            "errors": sum(1 for _, d in results if d.severity == "error"),
            "warnings": sum(1 for _, d in results if d.severity == "warning"),
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


def _render_sarif(results: list[tuple[str, Diagnostic]]) -> str:
    sarif = {
        "version": "2.1.0",
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "qnxbuild-lint",
                        "version": __version__,
                        "rules": [
                            {"id": rule, "shortDescription": {"text": text}}
                            for rule, text in sorted(RULES.items())
                        ],
                    }
                },
                "results": [
                    {
                        "ruleId": diagnostic.rule,
                        "level": "error" if diagnostic.severity == "error" else "warning",
                        "message": {"text": diagnostic.message},
                        "locations": [
                            {
                                "physicalLocation": {
                                    "artifactLocation": {"uri": path},
                                    "region": {
                                        "startLine": max(diagnostic.line, 1),
                                        "startColumn": max(diagnostic.col, 1),
                                    },
                                }
                            }
                        ],
                    }
                    for path, diagnostic in results
                ],
            }
        ],
    }
    return json.dumps(sarif, ensure_ascii=False, indent=2)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="qnxbuild-lint",
        description="Lint QNX mkifs buildfiles and recursive Makefiles before `mkifs` fails.",
    )
    parser.add_argument("--version", action="version", version=f"qnxbuild-lint {__version__}")
    parser.add_argument("--explain", metavar="RULE", help="print what a rule means")
    sub = parser.add_subparsers(dest="command")
    lint = sub.add_parser("lint", help="lint files or directories")
    lint.add_argument("paths", nargs="+")
    lint.add_argument("--format", choices=("text", "json", "sarif"), default="text")
    lint.add_argument("--max-warnings", type=int, default=-1)
    args = parser.parse_args(argv)

    if args.explain:
        if args.explain not in RULES:
            print(f"unknown rule: {args.explain}", file=sys.stderr)
            return 2
        print(f"{args.explain}: {RULES[args.explain]}")
        return 0

    if args.command != "lint":
        parser.print_help()
        return 2

    results = _collect(args.paths)
    if args.format == "json":
        print(_render_json(results))
    elif args.format == "sarif":
        print(_render_sarif(results))
    else:
        text = _render_text(results)
        if text:
            print(text)

    errors = sum(1 for _, d in results if d.severity == "error")
    warnings = sum(1 for _, d in results if d.severity == "warning")
    if args.format == "text":
        print(f"{errors} error(s), {warnings} warning(s)", file=sys.stderr)
    if errors:
        return 1
    if args.max_warnings >= 0 and warnings > args.max_warnings:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
