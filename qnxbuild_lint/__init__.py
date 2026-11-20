"""qnxbuild-lint: static checks for QNX ``mkifs`` buildfiles and recursive Makefiles."""

from __future__ import annotations

__version__ = "0.2.0"

from .buildfile import Diagnostic, Entry, Buildfile, lint_source  # noqa: E402,F401
from .makefile import Makefile, lint_tree, parse  # noqa: E402,F401

__all__ = [
    "__version__",
    "Buildfile",
    "Diagnostic",
    "Entry",
    "Makefile",
    "lint_source",
    "lint_tree",
    "parse",
]
