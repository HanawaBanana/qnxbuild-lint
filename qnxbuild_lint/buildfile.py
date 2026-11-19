"""Parser and validator for QNX ``mkifs`` buildfiles (``*.build``)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .attributes import TYPE_VALUES, classify

BANNER = "# qnxbuild-lint:"


@dataclass
class Diagnostic:
    rule: str
    severity: str  # "error" | "warning"
    line: int
    col: int
    message: str

    def as_dict(self) -> dict:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "line": self.line,
            "column": self.col,
            "message": self.message,
        }


@dataclass
class Entry:
    """One buildfile entry: a (possibly empty) attribute group plus a file spec."""

    line: int
    attributes: list[str] = field(default_factory=list)
    spec: str = ""
    bracketed: bool = False


@dataclass
class Buildfile:
    path: str
    entries: list[Entry]
    diagnostics: list[Diagnostic]

    @property
    def errors(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "error"]

    @property
    def warnings(self) -> list[Diagnostic]:
        return [d for d in self.diagnostics if d.severity == "warning"]


_ATTR_GROUP = re.compile(r"\[([^\]]*)\]")
_VAR_REF = re.compile(r"\$\{[^}]*\}")


def _strip_comment(line: str) -> str:
    """Remove a trailing ``#`` comment, honouring quoted strings."""
    out = []
    quote = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            out.append(ch)
            continue
        if ch == "#":
            break
        out.append(ch)
    return "".join(out)


def _brace_delta(text: str) -> int:
    """Net `{` minus `}` on a line.

    ``${VAR}`` references and escaped braces (``\{``/``\}``) do not count —
    mkifs requires ``}`` inside an inline file to be escaped with a backslash.
    """
    cleaned = _VAR_REF.sub("", text)
    cleaned = cleaned.replace("\\{", "").replace("\\}", "")
    return cleaned.count("{") - cleaned.count("}")


def parse_attributes(
    group: str, line_no: int, col: int, diagnostics: list[Diagnostic]
) -> list[str]:
    """Split one ``[...]`` attribute group into tokens and validate each token."""
    tokens = group.split()
    seen: dict[str, str] = {}  # bare name -> rendered token
    for token in tokens:
        if not token:
            continue
        conditional = token.startswith("?")
        body = token[1:] if conditional else token
        if body[:1] in "+-":
            name, value = body[1:], None
            kind = classify(name)
            if kind == "value":
                diagnostics.append(
                    Diagnostic(
                        "ATTR_KIND",
                        "error",
                        line_no,
                        col,
                        f"'{name}' is a value attribute; write '{name}=...', not '{token}'",
                    )
                )
            elif kind is None:
                diagnostics.append(
                    Diagnostic(
                        "ATTR_UNKNOWN",
                        "error",
                        line_no,
                        col,
                        f"unknown attribute '{name}'",
                    )
                )
        elif "=" in body:
            name, _, value = body.partition("=")
            kind = classify(name)
            if kind == "boolean":
                diagnostics.append(
                    Diagnostic(
                        "ATTR_KIND",
                        "error",
                        line_no,
                        col,
                        f"'{name}' is a boolean attribute; write '+{name}' or '-{name}', not '{token}'",
                    )
                )
            elif kind is None:
                diagnostics.append(
                    Diagnostic(
                        "ATTR_UNKNOWN",
                        "error",
                        line_no,
                        col,
                        f"unknown attribute '{name}'",
                    )
                )
            elif not value:
                diagnostics.append(
                    Diagnostic(
                        "ATTR_EMPTY_VALUE",
                        "error",
                        line_no,
                        col,
                        f"attribute '{name}' has an empty value",
                    )
                )
            elif name == "type" and value not in TYPE_VALUES:
                diagnostics.append(
                    Diagnostic(
                        "ATTR_BAD_TYPE",
                        "error",
                        line_no,
                        col,
                        f"type='{value}' is not one of {sorted(TYPE_VALUES)}",
                    )
                )
        else:
            diagnostics.append(
                Diagnostic(
                    "ATTR_BARE",
                    "error",
                    line_no,
                    col,
                    f"attribute '{token}' needs a '+'/'-' prefix or '=' and a value",
                )
            )
            continue

        bare = body.lstrip("+-").split("=", 1)[0]
        previous = seen.get(bare)
        if previous is not None and previous != token:
            diagnostics.append(
                Diagnostic(
                    "ATTR_CONFLICT",
                    "error",
                    line_no,
                    col,
                    f"'{token}' contradicts '{previous}' in the same attribute group",
                )
            )
        elif previous is not None:
            diagnostics.append(
                Diagnostic(
                    "ATTR_DUPLICATE",
                    "warning",
                    line_no,
                    col,
                    f"attribute '{bare}' is repeated in the same group",
                )
            )
        seen[bare] = token
    return tokens


def lint_source(text: str, path: str = "<string>") -> Buildfile:
    """Parse and lint buildfile text.  Never raises on malformed input."""
    entries: list[Entry] = []
    diagnostics: list[Diagnostic] = []
    depth = 0  # inside a `name = { ... }` script or file-content block
    for index, raw in enumerate(text.splitlines(), start=1):
        if depth > 0:
            # Inside an inline file `#` is ordinary content (mkifs docs:
            # "mkifs doesn't interpret a pound sign (#) in an inline file as
            # the beginning of a comment").
            depth = max(0, depth + _brace_delta(raw))
            continue
        stripped = _strip_comment(raw).strip()
        if not stripped:
            continue
        groups = list(_ATTR_GROUP.finditer(stripped))
        rest = stripped
        tokens: list[str] = []
        if groups:
            if groups[0].start() != 0:
                diagnostics.append(
                    Diagnostic(
                        "ATTR_NOT_LEADING",
                        "error",
                        index,
                        1,
                        "attribute group must start the line",
                    )
                )
            if len(groups) > 1:
                diagnostics.append(
                    Diagnostic(
                        "ATTR_SPLIT_GROUPS",
                        "error",
                        index,
                        groups[1].start() + 1,
                        "combine all attributes into one pair of brackets: '[a] [b]' is invalid",
                    )
                )
            for group in groups:
                tokens.extend(
                    parse_attributes(
                        group.group(1), index, group.start() + 2, diagnostics
                    )
                )
            rest = _ATTR_GROUP.sub("", stripped).strip()

        entry = Entry(line=index, attributes=tokens, spec=rest, bracketed=bool(groups))
        entries.append(entry)
        _check_entry(entry, path, diagnostics)
        depth = max(0, depth + _brace_delta(stripped))

    _check_duplicate_targets(entries, diagnostics)
    return Buildfile(path=path, entries=entries, diagnostics=diagnostics)


def _target_path(entry: Entry) -> str | None:
    """Return the in-image path an entry writes, or None for script lines."""
    if not entry.spec:
        return None
    spec = entry.spec.strip()
    if spec.startswith("{"):
        return None
    target = spec.split("=", 1)[0].strip() if "=" in spec else spec
    if not target or target.endswith("=") or " " in target:
        return None
    return target.lstrip("./") or "/"


def _check_duplicate_targets(entries: list[Entry], diagnostics: list[Diagnostic]) -> None:
    """mkifs keeps the LAST entry for a target path; earlier ones vanish silently."""
    seen: dict[str, int] = {}
    for entry in entries:
        target = _target_path(entry)
        if target is None:
            continue
        if target in seen:
            diagnostics.append(
                Diagnostic(
                    "FILE_DUPLICATE_TARGET",
                    "warning",
                    entry.line,
                    1,
                    f"target '{target}' was already written at line {seen[target]}; "
                    "mkifs keeps the last entry and drops the earlier one",
                )
            )
        else:
            seen[target] = entry.line


def _check_entry(entry: Entry, path: str, diagnostics: list[Diagnostic]) -> None:
    names = {t.lstrip("?+-").split("=", 1)[0] for t in entry.attributes}
    type_values = [
        token.split("=", 1)[1]
        for token in entry.attributes
        if token.lstrip("?").startswith("type=")
    ]
    if "type" in names:
        # A bare `[type=link]` line applies to all following files (mkifs
        # documented "sticky" attribute form), so only a line that names its
        # own file specification can be wrong here.
        if entry.spec and "=" not in entry.spec and type_values and type_values[0] == "link":
            diagnostics.append(
                Diagnostic(
                    "LINK_NEEDS_TARGET",
                    "error",
                    entry.line,
                    1,
                    "[type=link] needs a 'name=target' file specification",
                )
            )
