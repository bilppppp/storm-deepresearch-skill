#!/usr/bin/env python3
"""Canonical hashing and atomic file operations for the governed harness."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Provides deterministic identity and promotion primitives for stage receipts."

MUTABLE_COMPONENTS = {"reports"}
IGNORED_PARTS = {".git", ".venv", "dist", "output", "tmp", "__pycache__"}
IGNORED_NAMES = {".DS_Store"}
CORE_FILES = {
    ".gitignore",
    "CHANGELOG.md",
    "LICENSE",
    "README.md",
    "SKILL.md",
    "manifest.json",
    "requirements-ci.txt",
    "requirements-dev.lock",
    "requirements.lock",
}


class HarnessIOError(ValueError):
    """Raised when an identity or atomic-I/O boundary cannot be established."""


def canonical_json_bytes(payload: object) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_sha256(payload: object) -> str:
    return sha256_bytes(canonical_json_bytes(payload))


def _atomic_write(path: Path, value: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as handle:
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: object) -> None:
    _atomic_write(path, canonical_json_bytes(payload))


def atomic_write_text(path: Path, value: str) -> None:
    _atomic_write(path, value.encode("utf-8"))


def atomic_promote(source: Path, destination: Path) -> None:
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    os.replace(source, destination)


def atomic_copy_file(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    os.close(file_descriptor)
    temporary = Path(temporary_name)
    try:
        shutil.copyfile(source, temporary)
        with temporary.open("rb") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _manifest_components(root: Path) -> set[str]:
    manifest_path = root / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessIOError(f"cannot load manifest.json: {exc}") from exc
    components = manifest.get("factory_components")
    if not isinstance(components, list) or not all(isinstance(item, str) for item in components):
        raise HarnessIOError("manifest factory_components must be a string array")
    result: set[str] = set()
    for component in components:
        path = Path(component)
        if path.is_absolute() or len(path.parts) != 1 or component in {"", ".", ".."}:
            raise HarnessIOError(f"invalid factory component: {component}")
        if component not in MUTABLE_COMPONENTS:
            result.add(component)
    return result


def governed_tree_manifest(root: Path) -> dict[str, str]:
    resolved_root = root.expanduser().resolve()
    if not resolved_root.is_dir():
        raise HarnessIOError(f"skill root does not exist: {resolved_root}")
    candidates: set[Path] = {
        resolved_root / name for name in CORE_FILES if (resolved_root / name).is_file()
    }
    for component in _manifest_components(resolved_root):
        component_path = resolved_root / component
        if component_path.is_symlink():
            raise HarnessIOError(f"governed component cannot be a symlink: {component}")
        if component_path.is_file():
            candidates.add(component_path)
        elif component_path.is_dir():
            for path in component_path.rglob("*"):
                relative = path.relative_to(resolved_root)
                if any(part in IGNORED_PARTS for part in relative.parts):
                    continue
                if path.name in IGNORED_NAMES:
                    continue
                if path.is_symlink():
                    raise HarnessIOError(f"governed path cannot be a symlink: {relative}")
                if path.is_file():
                    candidates.add(path)
    return {
        path.relative_to(resolved_root).as_posix(): sha256_file(path)
        for path in sorted(candidates, key=lambda item: item.relative_to(resolved_root).as_posix())
    }


def compute_skill_package_hash(root: Path) -> str:
    return canonical_json_sha256(governed_tree_manifest(root))


def load_canonical_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HarnessIOError(f"{path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise HarnessIOError(f"{path}: expected a JSON object")
    return payload
