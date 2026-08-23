"""
tools/checkpoint.py — Git-based checkpoint & rollback

Implements the "safe workspace" rule from the locked architecture:
  checkpoint -> agent modifies source -> verify -> PASS keep / FAIL rollback

Uses a SEPARATE git directory (.shipready-checkpoint/), not a normal
in-place `.git` folder. This matters: target-project/ lives inside
ShipReady's own repository, and a literal `.git` folder there would make
the outer repo treat it as an embedded submodule (Git detects this by
folder name, not by .gitignore rules — .gitignore cannot suppress it).
Using `git --git-dir=<checkpoint-dir> --work-tree=<target_dir>` gives the
same real commit/reset/clean guarantees without ever creating a `.git`
folder inside target_dir, so the outer repo sees plain files, nothing
embedded.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

CHECKPOINT_DIR_NAME = ".shipready-checkpoint"


class CheckpointError(Exception):
    pass


def _run_git(target_dir: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    git_dir = target_dir / CHECKPOINT_DIR_NAME
    result = subprocess.run(
        ["git", f"--git-dir={git_dir}", f"--work-tree={target_dir}", *args],
        cwd=target_dir,
        capture_output=True,
        text=True,
    )
    if check and result.returncode != 0:
        raise CheckpointError(
            f"git {' '.join(args)} failed (exit {result.returncode}): {result.stderr.strip()}"
        )
    return result


class Checkpoint:
    def __init__(self, target_dir: str | Path):
        self.target_dir = Path(target_dir).resolve()
        if not self.target_dir.exists():
            raise CheckpointError(f"Target directory does not exist: {self.target_dir}")

    def ensure_repo(self) -> None:
        """Initializes the checkpoint's git-dir if one doesn't already
        exist. Safe to call repeatedly — no-ops if already set up.

        Gracefully degrades if the `git` binary isn't available at all
        (e.g. some serverless environments like Vercel don't ship one) —
        raises CheckpointError rather than crashing with a raw
        FileNotFoundError, so callers can catch it and skip rollback
        protection instead of failing the whole run."""
        git_dir = self.target_dir / CHECKPOINT_DIR_NAME
        if git_dir.exists():
            return

        git_dir.mkdir(parents=True, exist_ok=True)
        try:
            subprocess.run(
                ["git", f"--git-dir={git_dir}", "init", "-q"],
                cwd=self.target_dir, capture_output=True, text=True, check=True,
            )
        except FileNotFoundError:
            raise CheckpointError(
                "The `git` binary is not available in this environment. "
                "Checkpoint/rollback protection is disabled for this run."
            )
        _run_git(self.target_dir, ["config", "user.email", "shipready@local"])
        _run_git(self.target_dir, ["config", "user.name", "ShipReady Checkpoint"])
        # The checkpoint dir must never track itself
        _run_git(self.target_dir, ["add", "-A", "--", ".", f":!{CHECKPOINT_DIR_NAME}"])
        _run_git(self.target_dir, ["commit", "--allow-empty", "-q", "-m", "shipready: initial baseline"])

    def create_checkpoint(self, label: str = "pre-run") -> str:
        """Commits the current state and returns the commit SHA to roll
        back to. --allow-empty guarantees a fresh, addressable checkpoint
        every call even if nothing changed since the last one."""
        self.ensure_repo()
        _run_git(self.target_dir, ["add", "-A", "--", ".", f":!{CHECKPOINT_DIR_NAME}"])
        _run_git(self.target_dir, ["commit", "--allow-empty", "-q", "-m", f"shipready checkpoint: {label}"])
        result = _run_git(self.target_dir, ["rev-parse", "HEAD"])
        return result.stdout.strip()

    def rollback(self, checkpoint_sha: str) -> None:
        """Hard-resets back to checkpoint_sha and removes any untracked
        files the agent created — the working directory ends up
        byte-for-byte identical to the checkpoint."""
        _run_git(self.target_dir, ["reset", "--hard", checkpoint_sha])
        _run_git(self.target_dir, ["clean", "-fd", "-q", "--exclude", CHECKPOINT_DIR_NAME])

    def commit_changes(self, message: str = "shipready: verified changes") -> str:
        """Commits the current state as a permanent, kept change (called
        when a run ends in status='ready'). Returns the new commit SHA."""
        _run_git(self.target_dir, ["add", "-A", "--", ".", f":!{CHECKPOINT_DIR_NAME}"])
        _run_git(self.target_dir, ["commit", "--allow-empty", "-q", "-m", message])
        result = _run_git(self.target_dir, ["rev-parse", "HEAD"])
        return result.stdout.strip()

    def current_sha(self) -> str:
        self.ensure_repo()
        result = _run_git(self.target_dir, ["rev-parse", "HEAD"])
        return result.stdout.strip()