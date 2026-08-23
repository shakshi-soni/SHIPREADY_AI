"""
tools/docgen.py — Documentation generation tools

These are thin, deterministic wrappers over repository.write_file().
Gemini composes the actual README/architecture content (that's reasoning
work, done in the planner/agent layer) — these functions just perform the
real, verifiable act of writing it to disk. Keeping content-generation and
file-writing separate means the Verifier can always re-read the file from
disk and check it for real, rather than trusting that "generation" happened.
"""

from __future__ import annotations

from pathlib import Path

from tools.repository import write_file


def generate_readme(target_dir: Path, content: str) -> dict:
    return write_file(target_dir, "README.md", content)


def generate_architecture_doc(target_dir: Path, content: str) -> dict:
    return write_file(target_dir, "ARCHITECTURE.md", content)