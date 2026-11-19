"""Unit tests for the recursive Makefile checker."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qnxbuild_lint.makefile import lint_tree, parse  # noqa: E402


def write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class ParseTests(unittest.TestCase):
    def test_list_variable_drives_recursion(self) -> None:
        mk = parse(
            "/x/Makefile",
            "LIST=CPU VARIANT\n"
            "CPU=aarch64 aarch64le\n"
            "include recurse.mk\n",
        )
        self.assertTrue(mk.uses_recurse)
        self.assertEqual([name for name, _ in mk.variants], ["CPU", "VARIANT"])
        self.assertEqual(mk.variables["CPU"], "aarch64 aarch64le")
        self.assertEqual([i for i, _, _ in mk.includes], ["recurse.mk"])

    def test_space_indented_recipe_is_an_error(self) -> None:
        mk = parse("/x/Makefile", "all:\n    cc -o x x.c\n")
        self.assertEqual([d.rule for d in mk.diagnostics], ["MAKE_SPACE_RECIPE"])

    def test_duplicate_recipe_warns(self) -> None:
        mk = parse("/x/Makefile", "all:\n\tcc a.c\nall:\n\tcc b.c\n")
        self.assertEqual([d.severity for d in mk.diagnostics], ["warning"])


class TreeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def rules(self) -> list[str]:
        return [d.rule for d in lint_tree(str(self.root))]

    def test_clean_tree_is_silent(self) -> None:
        write(self.root, "Makefile", "all:\n\t@echo built\n")
        write(self.root, "recurse.mk", "%:\n\t@true\n")
        write(
            self.root,
            "src/Makefile",
            "include ../recurse.mk\nall:\n\tcc -c x.c\n",
        )
        self.assertEqual(self.rules(), [])

    def test_missing_include_with_path_is_reported(self) -> None:
        write(self.root, "Makefile", "include sub/nothere.mk\nall:\n\t@true\n")
        self.assertEqual(self.rules(), ["MAKE_MISSING_INCLUDE"])

    def test_bare_include_comes_from_the_sdp_include_path(self) -> None:
        # `include recurse.mk` resolves through $QNX_TARGET/usr/include/mk at
        # build time, so a missing local copy is not an error.
        write(self.root, "Makefile", "[recursive]\ninclude recurse.mk\nsrc\n")
        (self.root / "src").mkdir()
        write(self.root, "src/Makefile", "all:\n\t@true\n")
        self.assertEqual(self.rules(), [])

    def test_optional_include_is_not_reported(self) -> None:
        write(self.root, "Makefile", "-include sub/nothere.mk\nall:\n\t@true\n")
        self.assertEqual(self.rules(), [])

    def test_missing_variant_directory(self) -> None:
        write(self.root, "Makefile", "LIST=CPU\nCPU=aarch64\ninclude recurse.mk\n")
        self.assertEqual(self.rules(), ["MAKE_MISSING_VARIANT_DIR"])

    def test_variant_directory_present_is_silent(self) -> None:
        write(self.root, "Makefile", "LIST=CPU\nCPU=aarch64\ninclude recurse.mk\n")
        (self.root / "aarch64").mkdir()
        write(self.root, "aarch64/Makefile", "all:\n\t@true\n")
        self.assertEqual(self.rules(), [])

    def test_variant_set_by_environment_is_skipped(self) -> None:
        write(self.root, "Makefile", "LIST=CPU\ninclude recurse.mk\n")
        self.assertEqual(self.rules(), [])

    def test_cycle_is_reported_once(self) -> None:
        write(self.root, "Makefile", "include sub/a.mk\nall:\n\t@true\n")
        write(self.root, "sub/a.mk", "include b.mk\n")
        write(self.root, "sub/b.mk", "include a.mk\n")
        self.assertEqual(self.rules(), ["MAKE_CYCLE"])

    def test_recursive_subdir_with_makefile_is_followed(self) -> None:
        write(self.root, "Makefile", "[recursive]\nsrc\n")
        write(self.root, "src/Makefile", "all:\n    echo broken\n")
        self.assertIn("MAKE_SPACE_RECIPE", self.rules())


if __name__ == "__main__":
    unittest.main()
