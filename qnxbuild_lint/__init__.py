"""qnxbuild-lint: static checks for QNX ``mkifs`` buildfiles and recursive Makefiles."""

from __future__ import annotations

try:  # installed distribution metadata is authoritative
    from importlib.metadata import version as _dist_version

    __version__ = _dist_version("qnxbuild-lint")
except Exception:  # source checkout without an install
    __version__ = "0.2.1"

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
