"""Parser and validator for QNX recursive Makefiles."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

from .buildfile import Diagnostic

INCLUDE_RE = re.compile(r"^(-)?(include|sinclude)\s+(.+)$")
# SDP-provided includes are written as $(MKFILES_ROOT)/qmacros.mk and only
# resolve inside a QNX make environment, so they cannot be checked here.
VAR_REF_RE = re.compile(r"\$[({]")
DEFINE_RE = re.compile(r"^define\b")
ENDEF_RE = re.compile(r"^endef\b")
CONDITIONAL_RE = re.compile(r"^(ifeq|ifneq|ifdef|ifndef|else|endif)\b")
# QNX recursion is driven by recurse.mk plus a LIST=<variable> declaration,
# e.g. "LIST=CPU" recurses into the directories named by $(CPU).
LIST_RE = re.compile(r"^LIST\s*[:+]?=\s*(.+)$")
RULE_RE = re.compile(r"^([^\s:#=][^:#=]*?)\s*:(?!=)\s*(.*)$")
VAR_ASSIGN_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.]*)\s*[:+?]?=\s*(.*)$")


@dataclass
class Makefile:
    path: str
    includes: list[tuple[str, int, bool]] = field(default_factory=list)  # (target, line, optional)
    variants: list[tuple[str, int]] = field(default_factory=list)  # (dir, line)
    uses_recurse: bool = False
    variables: dict[str, str] = field(default_factory=dict)
    rule_lines: dict[str, list[int]] = field(default_factory=dict)
    recipes: dict[str, list[tuple[int, str]]] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]


def parse(path: str, text: str) -> Makefile:
    mk = Makefile(path=path)
    current_target: str | None = None
    conditional_lines: list[int] = []
    in_define = False
    continued = False
    for index, raw in enumerate(text.splitlines(), start=1):
        stripped_raw = raw.strip()
        if continued:
            # Part of a backslash-continued logical line (variable or rule).
            continued = stripped_raw.endswith("\\")
            continue
        if in_define:
            if ENDEF_RE.match(stripped_raw):
                in_define = False
            continue
        if DEFINE_RE.match(stripped_raw):
            in_define = True
            current_target = None
            continue
        if CONDITIONAL_RE.match(stripped_raw):
            conditional_lines.append(index)
            continue
        if not raw.strip():
            continue
        if raw.startswith("\t"):
            if current_target is None:
                mk.diagnostics.append(
                    Diagnostic(
                        "MAKE_ORPHAN_RECIPE",
                        "error",
                        index,
                        1,
                        f"{path}: recipe line has no preceding rule",
                    )
                )
                continue
            mk.recipes.setdefault(current_target, []).append((index, raw[1:].strip()))
            continue

        stripped = raw.strip()
        if stripped.startswith("#"):
            continue
        if raw[:1] in " \t":
            if VAR_ASSIGN_RE.match(stripped):
                # GNU make accepts an indented variable assignment.
                continue
            # A space-indented command line makes make abort with
            # "missing separator" — a real build breaker, not a style issue.
            mk.diagnostics.append(
                Diagnostic(
                    "MAKE_SPACE_RECIPE",
                    "error",
                    index,
                    1,
                    "recipe line must start with a TAB; spaces make `make` abort with 'missing separator'",
                )
            )
            current_target = None
            continue

        current_target = None
        list_decl = LIST_RE.match(stripped)
        if list_decl:
            for var_name in list_decl.group(1).split():
                mk.variants.append((var_name, index))
            continue

        inc = INCLUDE_RE.match(stripped)
        if inc:
            target = inc.group(3).strip()
            optional = bool(inc.group(1)) or inc.group(2) == "sinclude"
            if VAR_REF_RE.search(target):
                # Variable include: only resolvable inside a QNX make run.
                continue
            mk.includes.append((target, index, optional))
            if target == "recurse.mk":
                mk.uses_recurse = True
            continue

        assign = VAR_ASSIGN_RE.match(stripped)
        if assign:
            mk.variables[assign.group(1)] = assign.group(2).strip()
            continued = stripped.endswith("\\")
            continue

        rule = RULE_RE.match(stripped)
        if rule:
            targets = [t.strip() for t in rule.group(1).split() if t.strip()]
            if not targets:
                continue
            current_target = targets[0]
            for target_name in targets:
                mk.rule_lines.setdefault(target_name, []).append(index)
            continued = stripped.endswith("\\")
            continue


    for target_name, lines in mk.rule_lines.items():
        if len(lines) < 2:
            continue
        if any(lines[0] < line < lines[-1] for line in conditional_lines):
            # Same target in separate conditional branches is legitimate.
            continue
        mk.diagnostics.append(
            Diagnostic(
                "MAKE_DUP_RECIPE",
                "warning",
                lines[-1],
                1,
                f"target '{target_name}' is defined {len(lines)} times; "
                "make keeps the last recipe and warns 'overriding recipe'",
            )
        )
    # Every diagnostic produced here belongs to the file being parsed; the CLI
    # reports it verbatim instead of parsing a path out of the message text.
    for diagnostic in mk.diagnostics:
        diagnostic.path = path
    return mk


def _resolve(base: str, name: str) -> str:
    return os.path.normpath(os.path.join(os.path.dirname(base), name))


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as handle:
        return handle.read()


def lint_tree(root: str) -> list[Diagnostic]:
    """Lint every Makefile under ``root`` and check the include/recursion graph."""
    diagnostics: list[Diagnostic] = []
    parsed: dict[str, Makefile] = {}

    def load(path: str) -> None:
        if path in parsed:
            return
        try:
            parsed[path] = parse(path, _read(path))
        except OSError as exc:
            diagnostics.append(
                Diagnostic("MAKE_UNREADABLE", "error", 1, 1, f"{path}: {exc}", path=path)
            )
            return

    for dirpath, _dirnames, filenames in os.walk(root):
        for name in ("Makefile", "GNUmakefile", "makefile"):
            if name in filenames:
                load(os.path.join(dirpath, name))

    # Follow includes to a fixpoint before analysing the graph.
    queue = list(parsed)
    while queue:
        path = queue.pop()
        for target, _line, optional in parsed[path].includes:
            resolved = _resolve(path, target)
            if os.path.exists(resolved) and resolved not in parsed:
                load(resolved)
                if resolved in parsed:
                    queue.append(resolved)

    graph: dict[str, set[str]] = {}
    for path in parsed:
        mk = parsed[path]
        diagnostics.extend(mk.diagnostics)
        edges = graph.setdefault(path, set())
        for target, line, optional in mk.includes:
            resolved = _resolve(path, target)
            if not os.path.exists(resolved) and os.sep not in target:
                # Bare names such as `recurse.mk` come from the SDP include
                # path ($QNX_TARGET/usr/include/mk) at build time, so a
                # missing copy next to the makefile is not an error.
                continue
            if not os.path.exists(resolved):
                if not optional:
                    diagnostics.append(
                        Diagnostic(
                            "MAKE_MISSING_INCLUDE",
                            "error",
                            line,
                            1,
                            f"{path}: included file '{target}' does not exist",
                            path=path,
                        )
                    )
                continue
            edges.add(resolved)
        for var_name, line in mk.variants:
            # recurse.mk walks the directories named by the LIST variable, e.g.
            # LIST=CPU with CPU=aarch64 aarch64le recurses into both.
            values = mk.variables.get(var_name, "").split()
            if not values:
                continue  # set by qconfig.mk / the SDP environment
            for value in values:
                resolved = _resolve(path, value)
                if not os.path.isdir(resolved):
                    diagnostics.append(
                        Diagnostic(
                            "MAKE_MISSING_VARIANT_DIR",
                            "error",
                            line,
                            1,
                            f"{path}: LIST={var_name} names '{value}' but no such directory exists",
                            path=path,
                        )
                    )
                    continue
                edges.add(resolved)

    diagnostics.extend(_find_cycles(graph))
    return diagnostics


def _find_cycles(graph: dict[str, set[str]]) -> list[Diagnostic]:
    """Report each include/recursion cycle once, anchored at its smallest path."""
    colour: dict[str, int] = {}
    stack: list[str] = []
    reported: set[frozenset[str]] = set()
    found: list[Diagnostic] = []

    def visit(node: str) -> None:
        colour[node] = 1
        stack.append(node)
        for neighbour in sorted(graph.get(node, ())):
            state = colour.get(neighbour, 0)
            if state == 1:
                cycle = stack[stack.index(neighbour):] + [neighbour]
                key = frozenset(cycle)
                if key not in reported:
                    reported.add(key)
                    found.append(
                        Diagnostic(
                            "MAKE_CYCLE",
                            "error",
                            1,
                            1,
                            "include/recursion cycle: " + " -> ".join(cycle),
                            path=cycle[0],
                        )
                    )
            elif state == 0 and neighbour in graph:
                visit(neighbour)
        stack.pop()
        colour[node] = 2

    for node in sorted(graph):
        if colour.get(node, 0) == 0:
            visit(node)
    return found
