#!/usr/bin/env sh
# Type-check the example code the book quotes with `#snippet`.
#
# The point of keeping listings in `code/` instead of inside the prose is that
# a compiler can read them. A listing that no longer compiles should fail the
# build, not mislead a reader.
#
# Add a branch here for each language the book quotes.
set -eu

root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$root"
status=0
checked=0

# --- Rust ------------------------------------------------------------------ #
# Checked as standalone library crates: no Cargo project to maintain, and
# `--emit=metadata` type-checks without producing artifacts.
rust_files=$(find code -name '*.rs' -type f 2>/dev/null | sort)
if [ -n "$rust_files" ]; then
  if command -v rustc > /dev/null 2>&1; then
    output=$(mktemp -d)
    trap 'rm -rf "$output"' EXIT
    for file in $rust_files; do
      echo "rustc $file"
      rustc --edition 2021 --crate-type lib --emit=metadata \
        --out-dir "$output" "$file" || status=1
      checked=$((checked + 1))
    done
  else
    echo "skipping $(echo "$rust_files" | wc -l | tr -d ' ') Rust file(s): rustc not installed" >&2
  fi
fi

if [ "$checked" -eq 0 ]; then
  echo "no example code to check"
else
  echo "checked $checked example file(s)"
fi
exit "$status"
