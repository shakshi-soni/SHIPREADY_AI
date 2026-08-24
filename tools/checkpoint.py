"""
tools/checkpoint.py — Git-based checkpoint & rollback

Implements the safe-workspace rule:

checkpoint -> agent modifies source -> verify -> PASS keep / FAIL rollback

On environments without Git, such as some serverless runtimes,
checkpoint protection gracefully disables itself instead of crashing
the request.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


CHECKPOINT_DIR_NAME = ".shipready-checkpoint"


class CheckpointError(Exception):
    pass


def _run_git(
    target_dir: Path,
    args: list[str],
    check: bool = True,
) -> subprocess.CompletedProcess:

    git_dir = target_dir / CHECKPOINT_DIR_NAME

    try:
        result = subprocess.run(
            [
                "git",
                f"--git-dir={git_dir}",
                f"--work-tree={target_dir}",
                *args,
            ],
            cwd=target_dir,
            capture_output=True,
            text=True,
        )

    except FileNotFoundError as e:
        raise CheckpointError(
            "The `git` binary is not available in this environment. "
            "Checkpoint/rollback protection is disabled for this run."
        ) from e

    if check and result.returncode != 0:
        raise CheckpointError(
            f"git {' '.join(args)} failed "
            f"(exit {result.returncode}): "
            f"{result.stderr.strip()}"
        )

    return result


class Checkpoint:

    def __init__(self, target_dir: str | Path):
        self.target_dir = Path(target_dir).resolve()

        if not self.target_dir.exists():
            raise CheckpointError(
                f"Target directory does not exist: "
                f"{self.target_dir}"
            )

    def ensure_repo(self) -> None:

        git_dir = self.target_dir / CHECKPOINT_DIR_NAME

        # An existing directory does NOT necessarily mean it is
        # a valid Git repository. This is especially important on
        # Vercel where target-project may have been copied from the
        # deployment bundle.
        if git_dir.exists():

            try:
                _run_git(
                    self.target_dir,
                    ["rev-parse", "--git-dir"],
                )
                return

            except CheckpointError:
                shutil.rmtree(
                    git_dir,
                    ignore_errors=True,
                )

        git_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        try:
            subprocess.run(
                [
                    "git",
                    f"--git-dir={git_dir}",
                    "init",
                    "-q",
                ],
                cwd=self.target_dir,
                capture_output=True,
                text=True,
                check=True,
            )

        except FileNotFoundError as e:
            shutil.rmtree(
                git_dir,
                ignore_errors=True,
            )

            raise CheckpointError(
                "The `git` binary is not available in this "
                "environment. Checkpoint/rollback protection "
                "is disabled for this run."
            ) from e

        except subprocess.CalledProcessError as e:
            shutil.rmtree(
                git_dir,
                ignore_errors=True,
            )

            raise CheckpointError(
                f"git init failed "
                f"(exit {e.returncode}): "
                f"{(e.stderr or '').strip()}"
            ) from e

        _run_git(
            self.target_dir,
            [
                "config",
                "user.email",
                "shipready@local",
            ],
        )

        _run_git(
            self.target_dir,
            [
                "config",
                "user.name",
                "ShipReady Checkpoint",
            ],
        )

        _run_git(
            self.target_dir,
            [
                "add",
                "-A",
                "--",
                ".",
                f":!{CHECKPOINT_DIR_NAME}",
            ],
        )

        _run_git(
            self.target_dir,
            [
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                "shipready: initial baseline",
            ],
        )

    def create_checkpoint(
        self,
        label: str = "pre-run",
    ) -> str:

        self.ensure_repo()

        _run_git(
            self.target_dir,
            [
                "add",
                "-A",
                "--",
                ".",
                f":!{CHECKPOINT_DIR_NAME}",
            ],
        )

        _run_git(
            self.target_dir,
            [
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                f"shipready checkpoint: {label}",
            ],
        )

        result = _run_git(
            self.target_dir,
            ["rev-parse", "HEAD"],
        )

        return result.stdout.strip()

    def rollback(
        self,
        checkpoint_sha: str,
    ) -> None:

        _run_git(
            self.target_dir,
            [
                "reset",
                "--hard",
                checkpoint_sha,
            ],
        )

        _run_git(
            self.target_dir,
            [
                "clean",
                "-fd",
                "-q",
                "--exclude",
                CHECKPOINT_DIR_NAME,
            ],
        )

    def commit_changes(
        self,
        message: str = "shipready: verified changes",
    ) -> str:

        _run_git(
            self.target_dir,
            [
                "add",
                "-A",
                "--",
                ".",
                f":!{CHECKPOINT_DIR_NAME}",
            ],
        )

        _run_git(
            self.target_dir,
            [
                "commit",
                "--allow-empty",
                "-q",
                "-m",
                message,
            ],
        )

        result = _run_git(
            self.target_dir,
            ["rev-parse", "HEAD"],
        )

        return result.stdout.strip()

    def current_sha(self) -> str:

        self.ensure_repo()

        result = _run_git(
            self.target_dir,
            ["rev-parse", "HEAD"],
        )

        return result.stdout.strip()