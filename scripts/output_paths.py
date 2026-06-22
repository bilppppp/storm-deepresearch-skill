#!/usr/bin/env python3
"""Resolve research output paths without escaping approved boundaries."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_INTERFACE = "internal-module"
SCRIPT_INTERFACE_REASON = "Shared output boundary checks imported by package CLIs."


class OutputPathError(ValueError):
    """Raised when a requested output path violates the package boundary."""


def _absolute(path: Path, base: Path) -> Path:
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else base / expanded


def _require_descendant(path: Path, root: Path, message: str) -> None:
    if path == root or not path.is_relative_to(root):
        raise OutputPathError(message)


def slugify_topic(topic: str) -> str:
    slug = re.sub(r"[^\w]+", "-", topic.casefold(), flags=re.UNICODE).strip("-_")
    return (slug[:64].rstrip("-_") or "research")


def select_new_output_dir(
    topic: str,
    *,
    workspace: Path | None = None,
    output_root: Path | None = None,
    output: Path | str | None = None,
    now: datetime | None = None,
) -> Path:
    """Choose a new run directory and enforce containment after symlink resolution."""
    workspace_path = (workspace or Path.cwd()).expanduser().resolve()
    if not workspace_path.is_dir():
        raise OutputPathError(f"workspace directory does not exist: {workspace_path}")
    if output_root is None:
        root = (workspace_path / "output" / "storm-deepresearch").resolve(strict=False)
        _require_descendant(
            root,
            workspace_path,
            "default output root escapes the workspace after symlink resolution",
        )
    else:
        root = _absolute(Path(output_root), workspace_path).resolve(strict=False)
    if root in {Path("/"), Path.home().resolve(), workspace_path}:
        raise OutputPathError("output root is too broad; choose a dedicated child directory")

    if output is None:
        timestamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
        candidate = root / f"{slugify_topic(topic)}-{timestamp}"
    else:
        requested = Path(output).expanduser()
        candidate = requested if requested.is_absolute() else root / requested
    resolved = candidate.resolve(strict=False)
    _require_descendant(
        resolved,
        root,
        "output path is outside the approved output root after symlink resolution",
    )
    return resolved


def resolve_package_dir(package_dir: Path, *, must_exist: bool = True) -> Path:
    resolved = package_dir.expanduser().resolve(strict=False)
    if must_exist and not resolved.is_dir():
        raise OutputPathError(f"research package directory does not exist: {resolved}")
    return resolved


def package_child(package_dir: Path, relative: str | Path) -> Path:
    """Resolve a fixed package child and reject traversal or symlink escape."""
    root = resolve_package_dir(package_dir)
    relative_path = Path(relative)
    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise OutputPathError("package child must be a relative path without parent traversal")
    child = (root / relative_path).resolve(strict=False)
    if child == root or not child.is_relative_to(root):
        raise OutputPathError("resolved output path escapes the research package")
    return child
