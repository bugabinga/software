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
import tomllib
from pathlib import Path

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
        sys.exit(f"{argv[0]} is not pinned in {MANIFEST.name}; known: "
                 + ", ".join(sorted(found)))
    print(found[argv[0]])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
