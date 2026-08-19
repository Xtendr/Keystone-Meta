#!/usr/bin/env python3
"""Install or restore the local-only synthetic visual fixture.

This tool never makes network calls and never reads credentials.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "KeystoneMetaData.lua"
FIXTURE = ROOT / "tests" / "fixtures" / "synthetic" / "visual_snapshot.lua"
BACKUP_DIR = ROOT / ".visual_fixture_backup"
BACKUP = BACKUP_DIR / "KeystoneMetaData.lua"
LOCK = BACKUP_DIR / "ACTIVE"


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def enable() -> int:
    if LOCK.exists() or BACKUP.exists():
        print(
            "Refusing nested enable: a visual-fixture backup already exists.\n"
            "Restore first: python tools/use_visual_fixture.py --restore",
            file=sys.stderr,
        )
        return 2
    if not TARGET.exists():
        print(f"missing {TARGET}", file=sys.stderr)
        return 1
    if not FIXTURE.exists():
        print(f"missing {FIXTURE}", file=sys.stderr)
        return 1
    fixture = FIXTURE.read_text(encoding="utf-8")
    if "isSynthetic = true" not in fixture:
        print("fixture is missing isSynthetic = true", file=sys.stderr)
        return 1
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    _atomic_write(BACKUP, TARGET.read_text(encoding="utf-8"))
    _atomic_write(LOCK, "SYNTHETIC VISUAL FIXTURE ACTIVE\n")
    _atomic_write(TARGET, fixture)
    print("SYNTHETIC VISUAL FIXTURE ACTIVE")
    print(f"Installed {FIXTURE.name} over KeystoneMetaData.lua")
    print("Restore with: python tools/use_visual_fixture.py --restore")
    return 0


def restore() -> int:
    if not BACKUP.exists():
        print("No visual-fixture backup to restore.", file=sys.stderr)
        return 1
    _atomic_write(TARGET, BACKUP.read_text(encoding="utf-8"))
    if LOCK.exists():
        LOCK.unlink()
    BACKUP.unlink()
    try:
        BACKUP_DIR.rmdir()
    except OSError:
        pass
    print("Restored previous KeystoneMetaData.lua")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Install or restore the synthetic visual fixture")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--enable", action="store_true", help="Back up live data and install the synthetic fixture")
    group.add_argument("--restore", action="store_true", help="Restore the exact previous data file")
    args = parser.parse_args(argv)
    if args.enable:
        return enable()
    return restore()


if __name__ == "__main__":
    raise SystemExit(main())
