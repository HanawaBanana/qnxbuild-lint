"""Attribute tables for the QNX ``mkifs`` buildfile format.

Provenance: QNX SDP 8.0 documentation, ``mkifs`` reference, section
"Attribute list" (https://www.qnx.com/developers/docs/8.0/com.qnx.doc.neutrino.utilities/topic/m/mkifs.html).

Boolean attributes take a ``+`` or ``-`` prefix (``+autolink``, ``-bigendian``);
value attributes take ``=`` followed by a value (``uid=5``).  A ``?`` before an
attribute makes it conditional (``?+bigendian``).
"""

from __future__ import annotations

# Boolean attributes: written as +name / -name.
BOOLEAN_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "autolink",
        "big_pages",
        "bigendian",
        "dupignore",
        "followlink",
        "include",
        "keeplinked",
        "optional",
        "page_align",
        "raw",
        "script",
        # `compress` and `session` are used both standalone and inside
        # composite values such as [virtual=aarch64le,raw -compress] and on
        # script lines inside { } blocks (observed in qnx/bsp_raspberrypi-*).
        "compress",
        "session",
    }
)

# Value attributes: written as name=value.
VALUE_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "action",
        "autoso",
        "cd",
        "chain",
        "cksum",
        "dperms",
        "drop",
        "filter",
        "gid",
        "ifs_csa",
        "image",
        "keepsection",
        "linker",
        "module",
        "mount",
        "mtime",
        "pagesizes",
        "perms",
        "phys_align",
        "physical",
        "prefix",
        "ram",
        "search",
        "sha256",
        "sha512",
        "type",
        "uid",
        "virtual",
    }
)

# Values accepted by the ``type=`` attribute.  Docs (mkifs, "type= file_type"):
# "Allowable types are: link — a symbolic link, fifo — a named pipe,
# file — a regular, everyday file (the default), dir — a directory."
TYPE_VALUES: frozenset[str] = frozenset({"link", "fifo", "file", "dir"})

ALL_ATTRIBUTES: frozenset[str] = BOOLEAN_ATTRIBUTES | VALUE_ATTRIBUTES


def classify(name: str) -> str | None:
    """Return ``"boolean"``, ``"value"`` or ``None`` for an attribute token."""
    if name in BOOLEAN_ATTRIBUTES:
        return "boolean"
    if name in VALUE_ATTRIBUTES:
        return "value"
    return None
