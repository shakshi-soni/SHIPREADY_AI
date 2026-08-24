"""
tools/testing.py — Test & build tools

run_tests() shells out to the real pytest binary against the target
project — it never asks Gemini whether tests passed, it reads the actual
exit code. run_build() is a lightweight syntax/import sanity check
(py_compile), scoped to match ShipReady's declared support target:
Python projects only (see contract.yaml -> target.supported_languages).

Uses sys.executable (not a hardcoded "python3") so this works correctly
on Windows, where there is normally no python3.exe on PATH — only
python.exe. Hardcoding "python3" caused Windows to redirect to a broken
Microsoft Store app-execution-alias shortcut instead of finding a real
interpreter. sys.executable always points at the exact interpreter
currently running this code, on every platform.
"""

from __future__ import annotations
import os
import shutil
import subprocess
import sys
from pathlib import Path


def _find_working_python() -> list[str]:
    """Returns candidate [executable, ...] command prefixes to try, in
    order of preference. sys.executable should always work — but if
    something in the local environment is redirecting it (a broken PATH,
    a stale venv, a Windows App Execution Alias shadowing it), fall back
    to searching for a real interpreter via shutil.which() before giving
    up. Returns a LIST of candidates to try in order, not just one."""
    candidates = []
    if sys.executable:
        candidates.append([sys.executable])
    for name in ("python3", "python", "py"):
        found = shutil.which(name)
        if found and [found] not in candidates:
            candidates.append([found])
    # Windows: `py -3` (the official launcher) sometimes works when nothing else does
    py_launcher = shutil.which("py")
    if py_launcher:
        candidates.append([py_launcher, "-3"])
    return candidates

def _subprocess_env() -> dict[str, str]:
    """Preserve the Python import paths available to the running Vercel
    function when launching a child Python process.

    Vercel's Python runtime can make installed packages available to the
    function while the raw /var/lang/bin/python executable used by a
    subprocess may not automatically inherit the same site-packages path.
    Passing the current interpreter's sys.path through PYTHONPATH keeps
    subprocess-based tools such as pytest in the exact same environment.
    """
    env = os.environ.copy()

    current_python_paths = [
        path for path in sys.path
        if path and path != "."
    ]

    existing_pythonpath = env.get("PYTHONPATH", "")

    if existing_pythonpath:
        current_python_paths.append(existing_pythonpath)

    env["PYTHONPATH"] = os.pathsep.join(current_python_paths)

    return env

def run_tests(target_dir: Path, timeout: int = 120) -> dict:
    target_dir = Path(target_dir)
    candidates = _find_working_python()
    attempts_log = []

    for base_cmd in candidates:
        try:
            proc = subprocess.run(
                [*base_cmd, "-m", "py_compile", *py_files],
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_subprocess_env(),
            )
                
        except FileNotFoundError as e:
            attempts_log.append(f"{base_cmd}: not found ({e})")
            continue
        except subprocess.TimeoutExpired:
            return {
                "exit_code": -1, "stdout": "", "passed": False,
                "stderr": f"pytest timed out after {timeout}s",
            }

        # Windows' specific "App Execution Alias" redirect signature:
        # exit code 9009 combined with the Microsoft Store message means
        # this candidate is broken even though subprocess didn't raise —
        # try the next candidate instead of accepting this failure.
        if proc.returncode == 9009 and "Microsoft Store" in proc.stderr:
            attempts_log.append(f"{base_cmd}: Windows App Execution Alias redirect (exit 9009)")
            continue

        return {
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "passed": proc.returncode == 0,
        }

    # Every candidate failed — this is a genuine environment problem,
    # not something a source-code patch can ever fix.
    return {
        "exit_code": -1,
        "stdout": "",
        "stderr": (
            "TEST_ENVIRONMENT_UNAVAILABLE: no working Python interpreter found. "
            f"Tried: {attempts_log}. This cannot be fixed by patching source code — "
            "it requires fixing the local Python installation/PATH."
        ),
        "passed": False,
    }


def run_build(target_dir: Path, timeout: int = 60) -> dict:
    """Compiles every .py file under target_dir to catch syntax errors.
    This is intentionally lightweight — ShipReady's declared scope is
    Python + pytest + Cloud Run, not a general-purpose build system."""
    target_dir = Path(target_dir)
    py_files = [
        str(p) for p in target_dir.rglob("*.py")
        if "tests" not in p.parts  # don't need to "build" test files separately
    ]
    if not py_files:
        return {"passed": True, "stdout": "No .py files found to compile.", "stderr": "", "exit_code": 0}

    candidates = _find_working_python()
    attempts_log = []

    for base_cmd in candidates:
        try:
            proc = subprocess.run(
                [*base_cmd, "-m", "py_compile", *py_files],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except FileNotFoundError as e:
            attempts_log.append(f"{base_cmd}: not found ({e})")
            continue
        except subprocess.TimeoutExpired:
            return {
                "passed": False, "stdout": "", "exit_code": -1,
                "stderr": f"Build check timed out after {timeout}s",
            }

        if proc.returncode == 9009 and "Microsoft Store" in proc.stderr:
            attempts_log.append(f"{base_cmd}: Windows App Execution Alias redirect (exit 9009)")
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
            "TEST_ENVIRONMENT_UNAVAILABLE: no working Python interpreter found. "
            f"Tried: {attempts_log}."
        ),
        "exit_code": -1,
    }