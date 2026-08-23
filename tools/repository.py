"""
tools/repository.py — Repository tools

Deterministic file operations against a target project directory.

Two independent safety guarantees live here, not just in the planner:
  1. Any write targeting a path under tests/ is refused.
  2. Any path that would resolve outside target_dir is refused
     (blocks '../../etc/passwd'-style escapes from a bad plan).

These checks exist at the tool layer on purpose — the planner already
rejects unsafe plans before they're built, but a tool that can be tricked
by a malformed path is a second point of failure. Enforcing it twice is
cheap insurance.
"""

from __future__ import annotations

import re
from pathlib import Path


class ToolError(Exception):
    """Raised when a tool call is invalid or refused (e.g. writing to tests/,
    a path-escape attempt, or a missing target)."""


_DEF_PATTERN = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(", re.MULTILINE)


def _defined_function_names(source: str) -> set[str]:
    return set(_DEF_PATTERN.findall(source))


def is_test_path(path: str) -> bool:
    normalized = path.replace("\\", "/").lstrip("./")
    return normalized.startswith("tests/") or normalized == "tests"


def resolve_target_path(target_dir: Path, relative_path: str) -> Path:
    """Resolves relative_path inside target_dir and refuses any escape."""
    target_dir = Path(target_dir).resolve()
    candidate = (target_dir / relative_path).resolve()
    if target_dir not in candidate.parents and candidate != target_dir:
        raise ToolError(f"Path escapes target directory: {relative_path!r}")
    return candidate


def read_file(target_dir: Path, path: str) -> str:
    full_path = resolve_target_path(target_dir, path)
    if not full_path.exists():
        raise ToolError(f"File not found: {path}")
    return full_path.read_text(encoding="utf-8", errors="replace")


def write_file(target_dir: Path, path: str, content: str) -> dict:
    if is_test_path(path):
        raise ToolError(
            f"Refused: write_file cannot target a test path ({path!r}). "
            "Test files are read-only by design."
        )
    full_path = resolve_target_path(target_dir, path)
    existed_before = full_path.exists()
    before = full_path.read_text(encoding="utf-8") if existed_before else ""

    # DETERMINISTIC guard against destructive overwrites — a real, tested
    # failure mode where an LLM "fixes" one bug by replacing the whole file
    # with a minimal version, silently deleting unrelated working functions
    # (observed in real runs: a /health fix wiped out the entire tasks
    # feature, breaking every other test). Prompt instructions alone
    # weren't reliable enough to prevent this consistently, so it's
    # enforced here instead, at the tool layer, where it can't be skipped.
    if existed_before and path.endswith(".py") and before.strip():
        old_functions = _defined_function_names(before)
        new_functions = _defined_function_names(content)
        missing = old_functions - new_functions
        if missing:
            raise ToolError(
                f"Refused: this write would delete existing function(s) "
                f"{sorted(missing)} that are defined in the current {path}. "
                f"If you're fixing a specific bug, modify only what's "
                f"necessary and keep all other functions intact — read the "
                f"current file content first if you haven't already."
            )

    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_text(content, encoding="utf-8")
    return {
        "path": path,
        "bytes_written": len(content.encode("utf-8")),
        "was_new_file": not existed_before,
        "changed": before != content,
    }


def list_files(target_dir: Path, pattern: str = "**/*") -> list[str]:
    """Lists real project files, excluding ShipReady's own internal
    tracking directories (.shipready-checkpoint git internals, .git,
    __pycache__, .pytest_cache). Without this exclusion, Gemini's view
    of "the project" gets flooded with dozens of git object files that
    aren't part of the actual codebase — confusing its planning."""
    target_dir = Path(target_dir).resolve()
    EXCLUDED_DIRS = {".shipready-checkpoint", ".git", "__pycache__", ".pytest_cache"}
    return sorted(
        str(p.relative_to(target_dir))
        for p in target_dir.glob(pattern)
        if p.is_file() and not any(part in EXCLUDED_DIRS for part in p.parts)
    )