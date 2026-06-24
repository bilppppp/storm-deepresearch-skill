#!/usr/bin/env python3
"""Redact machine-local roots from text files inside a release ZIP."""
from __future__ import annotations

import argparse
import json
import os
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


def safe_member(name: str) -> bool:
    path = PurePosixPath(name)
    return not path.is_absolute() and ".." not in path.parts


def replacements(redact_roots: list[Path]) -> list[tuple[bytes, bytes]]:
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    roots_and_markers: list[tuple[Path, str]] = []
    home = Path.home().absolute()
    for path in redact_roots:
        expanded = path.expanduser().absolute()
        roots_and_markers.extend([(expanded, "$SKILL_ROOT"), (expanded.resolve(), "$SKILL_ROOT")])
        for root in (expanded, expanded.resolve()):
            try:
                relative = root.relative_to(home)
            except ValueError:
                continue
            roots_and_markers.append((Path("$HOME") / relative, "$SKILL_ROOT"))
    roots_and_markers.extend([(home, "$HOME"), (home.resolve(), "$HOME")])
    for root, marker in roots_and_markers:
        value = str(root)
        if value not in seen:
            pairs.append((value, marker))
            seen.add(value)
    pairs.sort(key=lambda item: len(item[0]), reverse=True)
    return [(source.encode("utf-8"), marker.encode("utf-8")) for source, marker in pairs]


def sanitize_archive(archive: Path, redact_roots: list[Path]) -> dict[str, object]:
    archive = archive.expanduser().resolve()
    if not archive.is_file():
        raise FileNotFoundError(f"Archive does not exist: {archive}")

    pairs = replacements(redact_roots)
    changed_entries: list[str] = []
    entry_count = 0
    temp_path: Path | None = None
    try:
        with zipfile.ZipFile(archive, "r") as source:
            infos = source.infolist()
            names = [info.filename for info in infos]
            if len(names) != len(set(names)):
                raise ValueError("Archive contains duplicate member names")
            unsafe = [name for name in names if not safe_member(name)]
            if unsafe:
                raise ValueError(f"Archive contains unsafe member: {unsafe[0]}")

            fd, raw_temp = tempfile.mkstemp(prefix=f".{archive.name}.", suffix=".tmp", dir=archive.parent)
            os.close(fd)
            temp_path = Path(raw_temp)
            with zipfile.ZipFile(temp_path, "w") as target:
                for info in infos:
                    data = source.read(info.filename)
                    original = data
                    try:
                        data.decode("utf-8")
                    except UnicodeDecodeError:
                        pass
                    else:
                        for needle, marker in pairs:
                            data = data.replace(needle, marker)
                    if data != original:
                        changed_entries.append(info.filename)
                    target.writestr(info, data)
                    entry_count += 1

        with zipfile.ZipFile(temp_path, "r") as check:
            for info in check.infolist():
                data = check.read(info.filename)
                try:
                    data.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                for needle, _ in pairs:
                    if needle in data:
                        raise ValueError(f"Local path remains in archive member: {info.filename}")

        temp_path.replace(archive)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)

    return {
        "ok": True,
        "archive": str(archive),
        "entry_count": entry_count,
        "changed_entry_count": len(changed_entries),
        "changed_entries": changed_entries,
        "markers": [marker.decode("utf-8") for _, marker in pairs],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument(
        "--redact-root",
        action="append",
        type=Path,
        required=True,
        help="Machine-local root to replace with $SKILL_ROOT; may be repeated.",
    )
    args = parser.parse_args()
    try:
        report = sanitize_archive(args.archive, args.redact_root)
    except (FileNotFoundError, ValueError, zipfile.BadZipFile) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
