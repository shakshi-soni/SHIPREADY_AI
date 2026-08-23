"""
verification/verifier.py — Top-level Verifier

Two jobs:
  1. full_scan() — runs every contract check against the real target_dir
     and returns a scan_result dict (check_id -> bool), the exact shape
     Planner.analyze_gaps() expects. This is how ShipReady "inspects
     reality" without ever asking an LLM what's true.
  2. verify_step() — the VerifyFn the Orchestrator calls after each
     execution. It does NOT trust ExecutionResult.success (which only
     means "the tool call didn't crash") — it re-runs the specific
     deterministic check tied to that step's check_id.

The test-file baseline hash is captured once, at Verifier construction —
before the agent has had any chance to touch anything — so the integrity
check has something honest to compare against.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Optional

from agent.planner import PlanStep
from agent.executor import ExecutionResult
from verification import deployment as dep_checks
from verification import requirements as req_checks
from verification import tests as test_checks
from verification.evidence import EvidenceLog


def _try_parse_dict(raw_output: str) -> Optional[dict]:
    """ExecutionResult.raw_output is str(some_dict) — safely parse it back
    with ast.literal_eval (never eval) so we can inspect the tool's actual
    returned data, not just whether the call raised."""
    try:
        parsed = ast.literal_eval(raw_output)
        return parsed if isinstance(parsed, dict) else None
    except (ValueError, SyntaxError):
        return None


class Verifier:
    def __init__(self, target_dir: str | Path, evidence_log: Optional[EvidenceLog] = None):
        self.target_dir = Path(target_dir)
        self.evidence = evidence_log or EvidenceLog()
        # Baseline captured NOW, before any agent action — this is the
        # honest "before" state the integrity check compares against.
        self._test_baseline_hash = test_checks.hash_test_files(self.target_dir)
        self._last_deploy_result: Optional[dict] = None
        self._last_deploy_url: Optional[str] = None

    # ---------- Full contract scan (used for gap analysis input) ----------

    def full_scan(self) -> dict:
        scan_result: dict = {}

        checks: list[tuple[str, tuple[bool, str]]] = [
            ("readme_exists", req_checks.check_readme_exists(self.target_dir)),
            ("readme_min_sections", req_checks.check_readme_min_sections(self.target_dir)),
            ("architecture_doc_exists", req_checks.check_architecture_doc_exists(self.target_dir)),
            ("source_files_present", req_checks.check_source_files_present(self.target_dir)),
            ("test_suite_exists", test_checks.check_test_suite_exists(self.target_dir)),
            ("test_suite_passes", test_checks.check_test_suite_passes(self.target_dir)),
            (
                "test_files_unmodified",
                test_checks.check_test_files_unmodified(self.target_dir, self._test_baseline_hash),
            ),
            ("dockerfile_exists", dep_checks.check_dockerfile_exists(self.target_dir)),
            ("cloud_run_deployed", dep_checks.check_cloud_run_deployed(self._last_deploy_result)),
            ("health_check_passes", dep_checks.check_health_check_passes(self._last_deploy_url)),
        ]

        for check_id, (passed, evidence) in checks:
            scan_result[check_id] = passed
            scan_result[f"{check_id}_evidence"] = evidence
            self.evidence.record(check_id, passed, evidence)

        return scan_result

    # ---------- Per-step verification (the Orchestrator's VerifyFn) ----------

    def verify_step(self, step: PlanStep, result: ExecutionResult) -> bool:
        """Called by the Orchestrator after every execution. Re-checks
        reality for that step's check_id rather than trusting result.success."""
        if not result.success:
            self.evidence.record(step.check_id or step.tool, False, result.error or "Tool call failed")
            return False

        # Track deployment results for later checks (deploy + health are related)
        if step.tool == "deploy_cloud_run":
            parsed = _try_parse_dict(result.raw_output)
            self._last_deploy_result = parsed
            self._last_deploy_url = parsed.get("url") if parsed else None
            passed, evidence = dep_checks.check_cloud_run_deployed(self._last_deploy_result)
            self.evidence.record("cloud_run_deployed", passed, evidence)
            return passed

        if step.tool == "check_health_endpoint":
            passed, evidence = dep_checks.check_health_check_passes(self._last_deploy_url)
            self.evidence.record("health_check_passes", passed, evidence)
            return passed

        # Dispatch to the deterministic check matching this step's declared check_id
        check_id = step.check_id
        dispatch = {
            "readme_exists": lambda: req_checks.check_readme_exists(self.target_dir),
            "readme_min_sections": lambda: req_checks.check_readme_min_sections(self.target_dir),
            "architecture_doc_exists": lambda: req_checks.check_architecture_doc_exists(self.target_dir),
            "source_files_present": lambda: req_checks.check_source_files_present(self.target_dir),
            "test_suite_exists": lambda: test_checks.check_test_suite_exists(self.target_dir),
            "test_suite_passes": lambda: test_checks.check_test_suite_passes(self.target_dir),
            "test_files_unmodified": lambda: test_checks.check_test_files_unmodified(
                self.target_dir, self._test_baseline_hash
            ),
            "dockerfile_exists": lambda: dep_checks.check_dockerfile_exists(self.target_dir),
        }

        check_fn = dispatch.get(check_id)
        if check_fn is None:
            # Unknown/unmatched check_id — this must NEVER be treated as
            # success. Blindly trusting an unrecognized check_id (e.g. from
            # a recovery step that drifted off-target, like proposing
            # list_files instead of an actual fix) is exactly the kind of
            # silent false-pass this whole verifier exists to prevent.
            self.evidence.record(
                check_id or step.tool,
                False,
                f"No dedicated verifier for check_id={check_id!r} — cannot confirm "
                f"this step actually satisfied a real contract check. Treating as unverified.",
            )
            return False

        passed, evidence = check_fn()
        self.evidence.record(check_id, passed, evidence)
        return passed