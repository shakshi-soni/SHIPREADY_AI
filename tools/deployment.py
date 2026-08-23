"""
tools/deployment.py — Deployment tools

deploy_cloud_run() shells out to the real `gcloud` CLI. If gcloud isn't
installed, or the caller isn't authenticated, or the deploy fails for any
infrastructure reason, this returns a structured failure rather than
raising — that failure becomes a normal, diagnosable step in the recovery
loop instead of a special case the orchestrator has to know about.

check_health_endpoint() performs a real HTTP GET. It does not trust
Gemini's belief that a deployment succeeded — it asks the live URL.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None


def deploy_cloud_run(
    target_dir: Path,
    service_name: str = "shipready-target",
    project_id: str = "",
    region: str = "us-central1",
    timeout: int = 600,
) -> dict:
    target_dir = Path(target_dir)
    cmd = [
        "gcloud", "run", "deploy", service_name,
        "--source", str(target_dir),
        "--region", region,
        "--allow-unauthenticated",
        "--quiet",
    ]
    if project_id:
        cmd += ["--project", project_id]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return {
            "success": False,
            "stdout": "",
            "stderr": "gcloud CLI not found on this system.",
            "url": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "stdout": "",
            "stderr": f"gcloud run deploy timed out after {timeout}s",
            "url": None,
        }

    url = None
    for line in proc.stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("https://") and ".run.app" in stripped:
            url = stripped

    return {
        "success": proc.returncode == 0,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
        "url": url,
    }


def check_health_endpoint(url: str, timeout: int = 10) -> dict:
    if httpx is None:
        return {"reachable": False, "status_code": None, "error": "httpx not installed"}
    try:
        resp = httpx.get(f"{url.rstrip('/')}/health", timeout=timeout)
        return {
            "reachable": True,
            "status_code": resp.status_code,
            "body": resp.text[:500],
        }
    except Exception as e:  # noqa: BLE001 — any network failure is a valid "unhealthy" result, not a crash
        return {"reachable": False, "status_code": None, "error": str(e)}