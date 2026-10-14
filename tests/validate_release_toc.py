"""Reject outdated or incomplete release metadata before tagging or publishing."""
from pathlib import Path
import re
import sys


def validate(toc_path: Path, required_interface: str, project_id: str) -> None:
    text = toc_path.read_text(encoding="utf-8-sig")
    fields = {}
    for line in text.splitlines():
        match = re.fullmatch(r"##\s*([^:]+):\s*(.*)", line)
        if match:
            fields[match[1].strip()] = match[2].strip()
    interfaces = {value.strip() for value in fields.get("Interface", "").split(",")}
    if required_interface not in interfaces:
        raise SystemExit(f"{toc_path}: Interface must include {required_interface}")
    if not fields.get("Version") or "@" in fields["Version"]:
        raise SystemExit(f"{toc_path}: a literal addon Version is required")
    if fields.get("X-Curse-Project-ID") != project_id:
        raise SystemExit(f"{toc_path}: incorrect CurseForge project ID")
    for line in text.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            target = toc_path.parent / line.replace("\\", "/")
            if not target.is_file():
                raise SystemExit(f"{toc_path}: missing referenced file {line}")
    print(f"{toc_path}: Interface {required_interface}, Version {fields['Version']}, project {project_id}: OK")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit("usage: validate_release_toc.py <addon.toc> <interface> <curse-project-id>")
    validate(Path(sys.argv[1]), sys.argv[2], sys.argv[3])
