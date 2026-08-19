#!/usr/bin/env python3
"""Validate that a packaged ZIP contains exactly one top-level KeystoneMeta directory."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def top_level_entries(names: list[str]) -> set[str]:
    tops: set[str] = set()
    for name in names:
        normalized = name.replace("\\", "/").lstrip("/")
        if not normalized or normalized.endswith("/"):
            first = normalized.split("/", 1)[0]
            if first:
                tops.add(first)
            continue
        first = normalized.split("/", 1)[0]
        if first:
            tops.add(first)
    return tops


SYNTHETIC_MARKERS = ("isSynthetic = true", "isSynthetic=true")


def contains_synthetic_marker(text: str) -> bool:
    return any(marker in text for marker in SYNTHETIC_MARKERS)


def assert_not_synthetic(text: str, source: str) -> None:
    if contains_synthetic_marker(text):
        raise SystemExit(f"{source}: synthetic visual fixture must not be packaged or released")


def validate_release_data(path: Path) -> None:
    assert_not_synthetic(path.read_text(encoding="utf-8"), str(path))


def validate_zip(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        tops = top_level_entries(archive.namelist())
        if tops != {"KeystoneMeta"}:
            raise SystemExit(f"{path}: expected exactly one top-level KeystoneMeta directory, found {sorted(tops)}")
        for name in archive.namelist():
            normalized = name.replace("\\", "/")
            if normalized.endswith("KeystoneMetaData.lua"):
                assert_not_synthetic(archive.read(name).decode("utf-8"), f"{path}:{normalized}")
    print(f"{path}: OK (top-level KeystoneMeta/)")


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: validate_zip.py <package.zip> [...]", file=sys.stderr)
        return 2
    for raw in argv[1:]:
        for path in Path().glob(raw) if any(ch in raw for ch in "*?[]") else [Path(raw)]:
            if not path.exists():
                print(f"missing {path}", file=sys.stderr)
                return 1
            validate_zip(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
