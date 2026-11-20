"""Unit tests for the mkifs buildfile checker."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qnxbuild_lint.buildfile import lint_source  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]


def rules(text: str) -> list[str]:
    return [d.rule for d in lint_source(text).diagnostics]


class ValidBuildfileTests(unittest.TestCase):
    def test_clean_buildfile_has_no_diagnostics(self) -> None:
        text = (
            "[image=0=IFS:/ifs] rpi5.ifs\n"
            "[search=../install/aarch64le/usr/lib]\n"
            "[uid=0 gid=0 perms=0644 type=link] bin/sh=usr/bin/sh\n"
            "[+raw] usr/bin/toy\n"
            "[?+bigendian] ./startup-bcm2712\n"
            "# trailing comment\n"
        )
        self.assertEqual([d.as_dict() for d in lint_source(text).diagnostics], [])

    def test_entries_keep_attributes_and_spec(self) -> None:
        parsed = lint_source("[uid=0 gid=0] bin/sh\nbin/ls\n")
        self.assertEqual(parsed.entries[0].attributes, ["uid=0", "gid=0"])
        self.assertEqual(parsed.entries[0].spec, "bin/sh")
        self.assertEqual(parsed.entries[1].spec, "bin/ls")
        self.assertEqual(parsed.entries[1].attributes, [])


class AttributeRuleTests(unittest.TestCase):
    def test_boolean_attribute_written_as_value(self) -> None:
        self.assertIn("ATTR_KIND", rules("[raw=1] foo\n"))

    def test_value_attribute_written_as_boolean(self) -> None:
        self.assertIn("ATTR_KIND", rules("[+uid] foo\n"))

    def test_unknown_attribute(self) -> None:
        self.assertIn("ATTR_UNKNOWN", rules("[uidx=0] foo\n"))

    def test_empty_value(self) -> None:
        self.assertIn("ATTR_EMPTY_VALUE", rules("[uid=] foo\n"))

    def test_bad_type_value(self) -> None:
        self.assertIn("ATTR_BAD_TYPE", rules("[type=hardlink] foo\n"))

    def test_bare_token(self) -> None:
        self.assertIn("ATTR_BARE", rules("[uid] foo\n"))

    def test_conflicting_signs(self) -> None:
        self.assertIn("ATTR_CONFLICT", rules("[+raw -raw] foo\n"))

    def test_duplicate_same_token_is_warning(self) -> None:
        diagnostics = lint_source("[uid=0 uid=0] foo\n").diagnostics
        self.assertEqual([(d.rule, d.severity) for d in diagnostics], [("ATTR_DUPLICATE", "warning")])

    def test_split_groups_are_rejected(self) -> None:
        # QNX docs: "[uid=5] [gid=5] filename" is the incorrect way.
        self.assertIn("ATTR_SPLIT_GROUPS", rules("[uid=5] [gid=5] foo\n"))

    def test_group_must_lead_the_line(self) -> None:
        self.assertIn("ATTR_NOT_LEADING", rules("foo [uid=0]\n"))

    def test_link_attribute_needs_target(self) -> None:
        self.assertIn("LINK_NEEDS_TARGET", rules("[type=link] bin/sh\n"))
        self.assertNotIn("LINK_NEEDS_TARGET", rules("[type=link] bin/sh=usr/bin/sh\n"))


class DuplicateTargetTests(unittest.TestCase):
    def test_same_image_path_twice_is_a_warning(self) -> None:
        diagnostics = lint_source("[uid=0] bin/tool\n[uid=1000] bin/tool\n").diagnostics
        self.assertEqual([(d.rule, d.severity) for d in diagnostics], [("FILE_DUPLICATE_TARGET", "warning")])
        self.assertIn("line 1", diagnostics[0].message)

    def test_link_target_counts_as_the_same_path(self) -> None:
        text = "bin/tool\n[type=link] bin/tool=usr/bin/tool\n"
        self.assertIn("FILE_DUPLICATE_TARGET", [d.rule for d in lint_source(text).diagnostics])


class InlineBlockTests(unittest.TestCase):
    def test_hash_inside_inline_file_is_content(self) -> None:
        text = (
            "[+script] startup-script = {\n"
            "# this is shell content, not a buildfile comment\n"
            "}\n"
            "[bogus=1] usr/bin/toy\n"
        )
        rules_found = [d.rule for d in lint_source(text).diagnostics]
        self.assertIn("ATTR_UNKNOWN", rules_found)

    def test_escaped_brace_does_not_close_the_block(self) -> None:
        text = (
            "[perms=0644] /etc/x = {\n"
            "echo \\}\n"
            "}\n"
            "[bogus=1] usr/bin/toy\n"
        )
        self.assertIn("ATTR_UNKNOWN", [d.rule for d in lint_source(text).diagnostics])

    def test_unclosed_block_does_not_hide_later_lines_for_ever(self) -> None:
        text = "[+script] s = {\n}\n[uid=0] usr/bin/a\n"
        self.assertEqual([d.rule for d in lint_source(text).diagnostics], [])


class AttributeEdgeCaseTests(unittest.TestCase):
    def test_bare_type_token_does_not_raise(self) -> None:
        self.assertIn("ATTR_BARE", [d.rule for d in lint_source("[type] x\n").diagnostics])

    def test_type_with_plus_prefix_does_not_raise(self) -> None:
        self.assertIn("ATTR_KIND", [d.rule for d in lint_source("[+type] x\n").diagnostics])

    def test_sticky_type_link_line_is_allowed(self) -> None:
        # Attributes on a line by themselves apply to all following files.
        text = "[type=link]\nbin/sh=usr/bin/sh\n"
        self.assertEqual([d.rule for d in lint_source(text).diagnostics], [])


class RobustnessTests(unittest.TestCase):
    def test_does_not_raise_on_garbage(self) -> None:
        for blob in ("[[[\n", "[uid=\n", "\x00\x01binary\n", "[] \n", "[+script\n"):
            lint_source(blob)

    def test_line_numbers_point_at_the_offending_line(self) -> None:
        diagnostics = lint_source("ok\n\n[bad=1] x\n").diagnostics
        self.assertEqual(diagnostics[0].line, 3)


if __name__ == "__main__":
    unittest.main()


class SectionHeaderTests(unittest.TestCase):
    def test_unknown_section_header_is_named(self):
        """`[block]` is not an mkifs attribute; name the problem, not "needs =value"."""
        bf = lint_source("[block]\nformat=ifs\n")
        found = [d.rule for d in bf.diagnostics]
        self.assertEqual(found.count("SECTION_UNKNOWN"), 1)
        self.assertNotIn("ATTR_BARE", found)
        self.assertEqual(bf.diagnostics[0].line, 1)

    def test_documented_value_attribute_without_value_stays_bare(self):
        """`image` is a documented value attribute (`image=[start][-end]...`),
        so `[image]` on its own is a missing value, not an unknown section."""
        self.assertEqual(rules("[image]\n"), ["ATTR_BARE"])

    def test_real_world_fragment_parses_clean(self):
        """Shape of a third-party CTI fragment (Apache-2.0): include block,
        [type=link] with an absolute target, `file` block with source_path."""
        text = (
            "include {\n"
            "    glaned\n"
            "    sensors.d\n"
            "}\n"
            "\n"
            "[type=link] /usr/bin/glaned = /bin/glaned\n"
            "\n"
            "file /etc/sensors.d {\n"
            "    source_path = sensors.d\n"
            "}\n"
        )
        self.assertEqual(rules(text), [])

    def test_global_boolean_attribute_alone_is_not_a_section(self):
        self.assertEqual(rules("[+raw]\nmy_app\n"), [])
