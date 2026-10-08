"""Optionally archive the exact frozen evidence and final release; never delete originals."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from berth_allocation_lab.benchmark.inputs import sha256_file
from berth_allocation_lab.results.release import DEFAULT_RELEASE_ID, DEFAULT_ROOT, verify_release


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    release = root / DEFAULT_ROOT / DEFAULT_RELEASE_ID
    verify_release(release)
    inventory = json.loads((release / "provenance/backup_manifest.json").read_text(encoding="utf-8"))
    members: dict[str, Path] = {}
    for entry in inventory["entries"]:
        relative = entry["path"]
        source = (root / relative).resolve()
        if not source.is_relative_to(root):
            raise SystemExit(f"Backup path escapes project: {relative}")
        if source.is_file():
            if sha256_file(source) != entry["sha256"]:
                raise SystemExit(f"Backup source changed: {relative}")
            members[relative] = source
        elif source == release.resolve():
            manifest = json.loads((release / "manifest.json").read_text(encoding="utf-8"))
            for file_relative, digest in manifest["release_file_sha256"].items():
                file = release / file_relative
                if sha256_file(file) != digest:
                    raise SystemExit(f"Release file changed: {file}")
                members[file.relative_to(root).as_posix()] = file
            members[(release / "manifest.json").relative_to(root).as_posix()] = release / "manifest.json"
        else:
            raise SystemExit(f"Backup source missing: {relative}")
    output = args.output.resolve()
    if output.is_relative_to(root):
        raise SystemExit("Place the backup outside the Project 03 directory.")
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("xb") as stream, ZipFile(stream, "w", compression=ZIP_DEFLATED) as archive:
        for relative, source in sorted(members.items()):
            archive.write(source, arcname=relative)
    print(f"Created {output} with {len(members)} files; originals unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
