"""
tools/testing.py — Test & build tools

run_tests() shells out to the real pytest binary against the target
project — it never asks Gemini whether tests passed, it reads the actual
exit code.

run_build() is a lightweight syntax/import sanity check (py_compile),
scoped to Python projects.

The subprocess environment preserves the current Python import paths.
This is important on serverless environments such as Vercel, where
sys.executable can point to the runtime interpreter while dependencies
are installed in the function's vendored environment.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_working_python() -> list[str]:
    """Return candidate Python command prefixes in priority order."""
    candidates: list[list[str]] = []

    if sys.executable:
        candidates.append([sys.executable])

    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found and [found] not in candidates:
            candidates.append([found])

    py_launcher = shutil.which("py")
    if py_launcher:
        candidate = [py_launcher, "-3"]
        if candidate not in candidates:
            candidates.append(candidate)

    return candidates


def _subprocess_env() -> dict[str, str]:
    """
    Preserve the current process's Python import paths for child Python
    processes.

    On Vercel, the function runtime can use /var/lang/bin/python while
    installed packages are available through the function's Python
    environment. Without PYTHONPATH, `python -m pytest` can report
    `No module named pytest` even though pytest is installed.
    """
    env = os.environ.copy()

    existing = env.get("PYTHONPATH", "")
    current_paths = [path for path in sys.path if path]

    merged: list[str] = []

    for path in current_paths:
        if path not in merged:
            merged.append(path)

    if existing:
        for path in existing.split(os.pathsep):
            if path and path not in merged:
                merged.append(path)

    if merged:
        env["PYTHONPATH"] = os.pathsep.join(merged)

    return env


def run_tests(target_dir: Path, timeout: int = 120) -> dict:
    target_dir = Path(target_dir)
    candidates = _find_working_python()
    attempts_log = []
    env = _subprocess_env()

    for base_cmd in candidates:
        try:
            proc = subprocess.run(
                [
                    *base_cmd,
                    "-m",
                    "pytest",
                    "-v",
                    "--tb=short",
                ],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

        except FileNotFoundError as e:
            attempts_log.append(
                f"{base_cmd}: not found ({e})"
            )
            continue

        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1,
                "stdout": "",
                "passed": False,
                "stderr": (
                    f"pytest timed out after {timeout}s"
                ),
            }

        # Windows App Execution Alias failure.
        if (
            proc.returncode == 9009
            and "Microsoft Store" in proc.stderr
        ):
            attempts_log.append(
                f"{base_cmd}: Windows App Execution Alias "
                f"redirect (exit 9009)"
            )
            continue

        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "passed": proc.returncode == 0,
        }

    return {
        "exit_code": -1,
        "stdout": "",
        "stderr": (
            "TEST_ENVIRONMENT_UNAVAILABLE: no working Python "
            "interpreter found. "
            f"Tried: {attempts_log}. "
            "This cannot be fixed by patching source code — "
            "it requires fixing the Python environment."
        ),
        "passed": False,
    }


def run_build(target_dir: Path, timeout: int = 60) -> dict:
    """
    Compile every Python source file under target_dir to catch
    syntax errors.
    """
    target_dir = Path(target_dir)

    py_files = [
        str(path)
        for path in target_dir.rglob("*.py")
        if "tests" not in path.parts
    ]

    if not py_files:
        return {
            "passed": True,
            "stdout": "No .py files found to compile.",
            "stderr": "",
            "exit_code": 0,
        }

    candidates = _find_working_python()
    attempts_log = []
    env = _subprocess_env()

    for base_cmd in candidates:
        try:
            proc = subprocess.run(
                [
                    *base_cmd,
                    "-m",
                    "py_compile",
                    *py_files,
                ],
                cwd=target_dir,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=env,
            )

        except FileNotFoundError as e:
            attempts_log.append(
                f"{base_cmd}: not found ({e})"
            )
            continue

        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "stdout": "",
                "exit_code": -1,
                "stderr": (
                    f"Build check timed out after {timeout}s"
                ),
            }

        if (
            proc.returncode == 9009
            and "Microsoft Store" in proc.stderr
        ):
            attempts_log.append(
                f"{base_cmd}: Windows App Execution Alias "
                f"redirect (exit 9009)"
            )
            continue

        return {
            "passed": proc.returncode == 0,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "exit_code": proc.returncode,
        }

    return {
        "passed": False,
        "stdout": "",
        "stderr": (
            "TEST_ENVIRONMENT_UNAVAILABLE: no working Python "
            "interpreter found. "
            f"Tried: {attempts_log}."
        ),
        "exit_code": -1,
    }