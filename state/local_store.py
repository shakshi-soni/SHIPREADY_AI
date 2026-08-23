"""
state/local_store.py — Local JSON state

Per the locked architecture: no Firestore for MVP. This is a simple
key-value store backed by a single JSON file, used for agent run state
(current plan, step index, run status) — separate from evidence.json,
which is an append-only log, not mutable state.

Writes are atomic: content is written to a temp file in the same
directory, then renamed over the real file. os.rename is atomic on both
POSIX and Windows for same-directory renames, so a crash mid-write can
never leave a half-written, corrupted state file — you either get the
old version or the new one, never a broken one in between.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


class LocalStore:
    def __init__(self, path: str | Path = "state/agent_state.json"):
        self.path = Path(path)

    def load(self) -> dict:
        if not self.path.exists():
            return {}
        try:
            with open(self.path) as f:
                return json.load(f)
        except json.JSONDecodeError:
            # A corrupted/empty state file shouldn't crash the agent —
            # treat it as empty state rather than raising.
            return {}

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

        fd, tmp_path = tempfile.mkstemp(
            dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp_path, self.path)  # atomic on POSIX and Windows
        except Exception:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise

    def get(self, key: str, default: Any = None) -> Any:
        return self.load().get(key, default)

    def set(self, key: str, value: Any) -> None:
        data = self.load()
        data[key] = value
        self.save(data)

    def update(self, **kwargs: Any) -> None:
        data = self.load()
        data.update(kwargs)
        self.save(data)

    def clear(self) -> None:
        self.save({})