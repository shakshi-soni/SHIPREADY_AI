"""
verification/deployment.py — Deployment checks

check_cloud_run_deployed() and check_health_check_passes() never trust
Gemini's belief that "deployment succeeded" — they check the actual
result dict returned by tools/deployment.py (a real gcloud subprocess
result) and, for health, make a fresh live HTTP request. If deployment
infrastructure genuinely isn't available (no gcloud CLI, no network),
these correctly report False rather than faking a pass.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from tools.deployment import check_health_endpoint as _check_health_tool


def check_dockerfile_exists(target_dir: Path) -> tuple[bool, str]:
    dockerfile = Path(target_dir) / "Dockerfile"
    if dockerfile.exists() and dockerfile.stat().st_size > 0:
        return True, "Dockerfile present"
    return False, "Dockerfile missing or empty"


def check_cloud_run_deployed(deploy_result: Optional[dict]) -> tuple[bool, str]:
    """deploy_result is the dict returned by tools.deployment.deploy_cloud_run().
    Passing None means no deploy attempt has been recorded yet."""
    if deploy_result is None:
        return False, "No deployment attempt has been recorded yet"
    if deploy_result.get("success") and deploy_result.get("url"):
        return True, f"Deployed successfully: {deploy_result['url']}"
    return False, f"Deployment did not succeed: {deploy_result.get('stderr', 'unknown error')[:300]}"


def check_health_check_passes(url: Optional[str]) -> tuple[bool, str]:
    if not url:
        return False, "No deployment URL available to check"
    result = _check_health_tool(url)
    if result.get("reachable") and result.get("status_code") == 200:
        return True, f"GET {url}/health -> 200. Body: {result.get('body', '')[:200]}"
    if not result.get("reachable"):
        return False, f"Health endpoint unreachable: {result.get('error', 'unknown error')}"
    return False, f"Health endpoint returned status {result.get('status_code')}, expected 200"