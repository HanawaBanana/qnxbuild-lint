"""End-to-end tests for the qnxbuild-lint CLI."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "qnxbuild_lint.cli", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=120,
    )


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_clean_file_exits_zero(self) -> None:
        good = self.root / "clean.build"
        good.write_text("[uid=0] bin/sh\n", encoding="utf-8")
        result = run("lint", str(good))
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_broken_file_exits_one_and_names_the_line(self) -> None:
        bad = self.root / "bad.build"
        bad.write_text("ok\n[bogus=1] bin/x\n", encoding="utf-8")
        result = run("lint", str(bad))
        self.assertEqual(result.returncode, 1)
        self.assertIn(":2:", result.stdout)
        self.assertIn("ATTR_UNKNOWN", result.stdout)

    def test_json_output_is_machine_readable(self) -> None:
        bad = self.root / "bad.build"
        bad.write_text("[uid] x\n", encoding="utf-8")
        result = run("lint", str(bad), "--format", "json")
        payload = json.loads(result.stdout)
        self.assertEqual(payload["summary"]["errors"], 1)
        self.assertEqual(payload["diagnostics"][0]["rule"], "ATTR_BARE")
        self.assertEqual(payload["diagnostics"][0]["file"], str(bad))

    def test_sarif_output_names_the_rule(self) -> None:
        bad = self.root / "bad.build"
        bad.write_text("[type=weird] x\n", encoding="utf-8")
        result = run("lint", str(bad), "--format", "sarif")
        sarif = json.loads(result.stdout)
        rule_ids = {r["ruleId"] for r in sarif["runs"][0]["results"]}
        self.assertEqual(rule_ids, {"ATTR_BAD_TYPE"})

    def test_directory_walk_finds_buildfiles_and_makefiles(self) -> None:
        (self.root / "images").mkdir()
        (self.root / "images" / "board.build").write_text("[uid=] a\n", encoding="utf-8")
        (self.root / "Makefile").write_text("LIST=CPU\nCPU=aarch64\ninclude recurse.mk\n", encoding="utf-8")
        result = run("lint", str(self.root), "--format", "json")
        payload = json.loads(result.stdout)
        rules = {d["rule"] for d in payload["diagnostics"]}
        self.assertEqual(rules, {"ATTR_EMPTY_VALUE", "MAKE_MISSING_VARIANT_DIR"})

    def test_max_warnings_promotes_warnings_to_failure(self) -> None:
        warn = self.root / "warn.build"
        warn.write_text("[uid=0 uid=0] x\n", encoding="utf-8")
        self.assertEqual(run("lint", str(warn)).returncode, 0)
        self.assertEqual(run("lint", str(warn), "--max-warnings", "0").returncode, 1)

    def test_explain_prints_rule_text(self) -> None:
        result = run("--explain", "MAKE_SPACE_RECIPE")
        self.assertEqual(result.returncode, 0)
        self.assertIn("missing separator", result.stdout)

    def test_missing_path_is_reported_not_crashed(self) -> None:
        result = run("lint", str(self.root / "nope.build"))
        self.assertEqual(result.returncode, 1)
        self.assertIn("IO_MISSING", result.stdout)


if __name__ == "__main__":
    unittest.main()
