"""
verification/tests.py — Test suite checks

check_test_suite_passes() re-runs pytest itself and reads the real exit
code — it never trusts a tool's self-reported "passed": True.

check_test_files_unmodified() is the anti-cheat guarantee made concrete:
it hashes every file under tests/ and compares against a baseline taken
before the agent started. If the hash differs, the agent (or anything
else) touched a test file during the run — which is disallowed by the
contract, structurally enforced here, not just in the planner's prompt.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from tools.testing import run_tests as _run_tests_tool


def check_test_suite_exists(target_dir: Path) -> tuple[bool, str]:
    target_dir = Path(target_dir)
    test_files = list(target_dir.glob("tests/**/*.py")) + list(target_dir.glob("test_*.py"))
    test_files = [f for f in test_files if f.name != "__init__.py"]
    if test_files:
        return True, f"Found {len(test_files)} test file(s): {[str(f.relative_to(target_dir)) for f in test_files]}"
    return False, "No test files found under tests/ or test_*.py"


def check_test_suite_passes(target_dir: Path) -> tuple[bool, str]:
    result = _run_tests_tool(target_dir)
    if result["passed"]:
        return True, f"pytest exited 0.\n{result['stdout'][-500:]}"
    return False, f"pytest exited {result['exit_code']}.\nstderr: {result['stderr'][-500:]}\nstdout: {result['stdout'][-500:]}"


def hash_test_files(target_dir: Path) -> str:
    """Deterministic hash of every file under tests/, sorted by path so
    ordering never affects the hash. Used to detect any modification —
    including a partial one — to test files during an agent run.

    Deliberately excludes __pycache__, .pyc, and .pytest_cache — those are
    regenerated automatically every time pytest runs, so including them
    would make the hash change even when no real test file was touched,
    producing a false "tampering detected" result."""
    target_dir = Path(target_dir)
    tests_dir = target_dir / "tests"
    if not tests_dir.exists():
        return hashlib.sha256(b"NO_TESTS_DIR").hexdigest()

    hasher = hashlib.sha256()
    for path in sorted(tests_dir.rglob("*")):
        if not path.is_file():
            continue
        if "__pycache__" in path.parts or ".pytest_cache" in path.parts:
            continue
        if path.suffix == ".pyc":
            continue
        hasher.update(str(path.relative_to(target_dir)).encode("utf-8"))
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def check_test_files_unmodified(target_dir: Path, baseline_hash: str) -> tuple[bool, str]:
    current_hash = hash_test_files(target_dir)
    if current_hash == baseline_hash:
        return True, f"tests/ hash unchanged ({current_hash[:12]}...)"
    return False, (
        f"tests/ hash changed! baseline={baseline_hash[:12]}... "
        f"current={current_hash[:12]}... — a test file was modified, which is forbidden."
    )