"""
api/index.py — Vercel entrypoint for ShipReady.

Vercel's serverless functions have a READ-ONLY filesystem except /tmp.
ShipReady needs to write to target-project/, so on cold start this copies
the shipped (read-only) target-project into a writable /tmp location and
points the orchestrator there instead.

Known real limitations of this deployment target — not hidden, listed
plainly:
  - /tmp is ephemeral. It may or may not persist between requests to the
    same function instance, and will NOT persist across cold starts.
    Each fresh instance starts from the original, unmodified target-project.
  - Execution time limits apply. A run that needs multiple Gemini calls
    (planning + recovery attempts) can be slow; if it exceeds Vercel's
    function timeout, the request will be cut off mid-run. This has not
    been tested against Vercel's actual current limits from this
    environment — verify directly after deploying.
  - `git` may or may not be present in Vercel's Python runtime. Checkpoint/
    rollback degrades gracefully if it's missing (see tools/checkpoint.py)
    — the agent still works, just without rollback protection.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

# Redirect target_dir to a writable /tmp location before app.main is imported,
# since app.main builds its singletons (Verifier, Orchestrator, etc.) at
# import time using TARGET_PROJECT_DIR from the environment.
_SOURCE_TARGET = Path(__file__).parent.parent / "target-project"
_WRITABLE_TARGET = Path("/tmp/target-project")

if not _WRITABLE_TARGET.exists():
    shutil.copytree(_SOURCE_TARGET, _WRITABLE_TARGET)

os.environ["TARGET_PROJECT_DIR"] = str(_WRITABLE_TARGET)
os.environ["CONTRACT_PATH"] = str(Path(__file__).parent.parent / "contract.yaml")
# Local JSON state also needs a writable location on Vercel. Assign this
# unconditionally so a dashboard environment variable cannot redirect state
# back into Vercel's read-only /var/task filesystem.
os.environ["SHIPREADY_STATE_DIR"] = "/tmp/state"
Path("/tmp/state").mkdir(parents=True, exist_ok=True)

from app.main import app  # noqa: E402  (must import after env vars are set)

# Vercel's Python runtime looks for an ASGI-compatible `app` object.