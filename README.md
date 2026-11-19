# qnxbuild-lint

![ci](https://github.com/HanawaBanana/qnxbuild-lint/actions/workflows/ci.yml/badge.svg)

Catch QNX build breaks **before** `mkifs` / `mk` do — from a Linux or macOS host, with no QNX SDP installed.

QNX image builds fail late and quietly: `mkifs` aborts on a malformed buildfile, and the message points at a line whose real cause is an attribute written in the wrong form (`[raw=1]` instead of `[+raw]`) or two attribute groups split across one line. Recursive BSP builds fail the same way when an `include` target moved or a `[recursive]` subdirectory was renamed. `qnxbuild-lint` checks both formats statically and exits non-zero in CI.

```console
$ qnxbuild-lint lint images/
images/rpi5.build:14:1: error [ATTR_SPLIT_GROUPS] combine all attributes into one pair of brackets: '[a] [b]' is invalid
images/rpi5.build:22:1: error [ATTR_KIND] 'uid' is a value attribute; write 'uid=...', not '+uid'
2 error(s), 0 warning(s)
```

## What it checks

Buildfiles (`*.build`, QNX SDP 8.0 `mkifs` attribute list):

| Rule | Meaning |
| --- | --- |
| `ATTR_KIND` | boolean attribute written as `name=value`, or value attribute written as `+name` |
| `ATTR_UNKNOWN` | attribute is not in the documented `mkifs` attribute list |
| `ATTR_EMPTY_VALUE` | `uid=` with no value |
| `ATTR_BAD_TYPE` | `type=` value is not `link`, `fifo`, `file` or `dir` |
| `ATTR_BARE` | token has neither a `+`/`-` prefix nor `=value` |
| `ATTR_CONFLICT` | one group holds contradicting settings, e.g. `[+raw -raw]` |
| `ATTR_DUPLICATE` | same attribute twice in one group (warning) |
| `ATTR_NOT_LEADING` | attribute group does not start the line |
| `ATTR_SPLIT_GROUPS` | `[uid=5] [gid=5] file` — documented as the incorrect way |
| `LINK_NEEDS_TARGET` | `[type=link]` without a `name=target` specification |
| `FILE_DUPLICATE_TARGET` | two entries write the same image path; `mkifs` keeps the last one (warning) |

Recursive Makefiles:

| Rule | Meaning |
| --- | --- |
| `MAKE_MISSING_INCLUDE` | explicitly pathed `include` target does not exist (bare names such as `recurse.mk` resolve through the SDP include path and are skipped) |
| `MAKE_MISSING_VARIANT_DIR` | `LIST=CPU` names a directory that does not exist |
| `MAKE_CYCLE` | include/recursion cycle that would loop forever |
| `MAKE_SPACE_RECIPE` | recipe line indented with spaces; `make` aborts with `missing separator` |
| `MAKE_DUP_RECIPE` | target has more than one recipe; `make` keeps the last and warns (warning) |
| `MAKE_ORPHAN_RECIPE` | recipe line with no preceding rule |

Every rule maps to a documented or observable `mkifs`/`make` behaviour — nothing here is style.

## Install and run

```console
$ pipx install qnxbuild-lint    # or: pip install qnxbuild-lint
$ qnxbuild-lint lint images/ src/ --format sarif > qnxbuild.sarif
$ qnxbuild-lint --explain MAKE_SPACE_RECIPE
```

Exit codes: `0` clean, `1` errors found (or warnings above `--max-warnings`), `2` usage error.
Output formats: `text`, `json`, `sarif` (for GitHub code scanning).

From a checkout, without installing:

```console
$ python3 -m qnxbuild_lint.cli lint images/ --format json
```

## How it is validated

* Unit tests cover every rule, malformed input (`[[[`, binary noise, unterminated groups) and the exit-code contract.
* Real-world corpus: **957 files** from `qnx/bsp_raspberrypi-bcm2712-rpi5` and `qnx/bsp_raspberrypi-bcm2711-rpi4` (2 buildfiles, 955 Makefiles, headers and sources) are linted by `tools/check_corpus.py`, which currently reports **0 diagnostics**. A linter that cries wolf on vendor files is worse than no linter — every false positive found this way was fixed rather than suppressed (inline `{ }` blocks, `define … endef` bodies, backslash continuations, `[virtual=aarch64le,raw -compress]` composite values, SDP-provided bare includes, `type=dir`, `LIST=`-driven recursion). Corpus files are downloaded at check time and never vendored, so the BSP licence does not spread here.
* Mutation demo: `tools/mutation_demo.py` takes a real vendor buildfile, appends each historical defect class and asserts the linter catches it — 7/7 caught on `images/rpi5.build`, whose baseline is 0 diagnostics.

```console
$ python3 tools/fetch_corpus.py          # downloads the corpus into .corpus/
$ python3 tools/check_corpus.py          # asserts zero diagnostics on it
$ python3 tools/mutation_demo.py .corpus/qnx__bsp_raspberrypi-bcm2712-rpi5/images/rpi5.build
```

## Limitations (stated, not hidden)

* Validates **syntax and references**, not semantics: it cannot know whether a `search=` path exists on your host, or whether a binary name resolves.
* The attribute list is pinned to QNX SDP 8.0 `mkifs`; add new attributes in `qnxbuild_lint/attributes.py` when a release adds them.
* Makefile support targets the QNX recursion model (`LIST=<variable>`, `recurse.mk`, plain `include`), not arbitrary GNU make dialects. Variant variables supplied by `qconfig.mk` or the SDP environment are skipped because their values are not in the tree.

## Licence

MIT — see `LICENSE`.
