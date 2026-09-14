#!/usr/bin/env python3
"""Print the version a tool is pinned to, from `mise.toml`.

One parser, so the shell scripts, the build and the maintenance sweep all read
the same file the same way. `mise.toml` is the manifest whether or not mise is
installed -- that is the point of routing everything through here rather than
through `mise` itself. A contributor with mise runs `mise install`; a
contributor without runs `mise install` and gets the same versions.

Usage:
    tools/pinned.py typst
    tools/pinned.py --all        # name<TAB>version, one per line
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

import tomllib

MANIFEST = Path(__file__).resolve().parent.parent / "mise.toml"


def pins() -> dict[str, str]:
    if not MANIFEST.is_file():
        sys.exit(f"missing manifest: {MANIFEST}")
    with MANIFEST.open("rb") as handle:
        return {k: str(v) for k, v in (tomllib.load(handle).get("tools") or {}).items()}


def main(argv: list[str]) -> int:
    found = pins()
    if argv[:1] == ["--all"]:
        for name, version in sorted(found.items()):
            print(f"{name}\t{version}")
        return 0
    if len(argv) != 1:
        sys.exit(__doc__)
    if argv[0] not in found:
        sys.exit(
            f"{argv[0]} is not pinned in {MANIFEST.name}; known: "
            + ", ".join(sorted(found))
        )
    print(found[argv[0]])
    return 0


class Pins(unittest.TestCase):
    """The manifest is the roster, whether or not mise is installed."""

    def test_the_tools_this_tree_pins(self) -> None:
        every = pins()
        self.assertIn("typst", every, "the build's own compiler")
        for tool, version in every.items():
            with self.subTest(tool=tool):
                self.assertTrue(version, f"{tool} is pinned to nothing")

    def test_a_version_is_a_version(self) -> None:
        # Not a range, not `latest`. The point of a pin is that two machines
        # install the same bytes.
        for tool, version in pins().items():
            with self.subTest(tool=tool):
                self.assertNotIn("latest", version)
                self.assertRegex(version, r"^[0-9]")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
