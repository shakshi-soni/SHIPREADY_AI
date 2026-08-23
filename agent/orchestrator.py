"""
agent/orchestrator.py — ShipReady Orchestrator

Runs the full loop:
  INSPECT (caller-provided scan) -> ANALYZE gaps -> PLAN -> EXECUTE
  -> VERIFY (injected, deterministic) -> FAIL? -> RECOVER (max N) -> EVIDENCE

The orchestrator never decides success itself — verify_fn is injected from
outside (it will be backed by verification/ once that module exists) so
this class stays testable and the "verifier decides, not the LLM" rule is
structurally enforced rather than just documented.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from agent.executor import Executor, ExecutionResult
from agent.planner import Gap, PlanStep, Planner, PlannerError
from agent.policy import ApprovalFn, deny_all, is_risky
from agent.recovery import RecoveryError, RecoveryManager
from tools.checkpoint import Checkpoint, CheckpointError


class OrchestratorError(Exception):
    pass


class BudgetExceeded(OrchestratorError):
    """Raised when a hard guardrail (steps, time, deploy attempts) is hit."""


@dataclass
class StepEvidence:
    step: PlanStep
    result: ExecutionResult
    verified: bool
    attempts_used: int = 0
    diagnosis_log: list[str] = field(default_factory=list)


@dataclass
class RunReport:
    status: str  # "ready" | "not_ready" | "already_ready" | "aborted"
    gaps_found: list[Gap]
    evidence: list[StepEvidence]
    total_steps_executed: int
    elapsed_seconds: float
    abort_reason: Optional[str] = None


# VerifyFn signature: (step, ExecutionResult) -> bool
VerifyFn = Callable[[PlanStep, ExecutionResult], bool]


class Orchestrator:
    def __init__(
        self,
        contract_path: str | Path,
        target_dir: str | Path,
        generate_fn: Callable[[str, str], str],
        verify_fn: VerifyFn,
        max_agent_steps: int = 30,
        max_repair_attempts: int = 3,
        max_deploy_attempts: int = 2,
        max_execution_time_seconds: int = 600,
        approval_fn: ApprovalFn = deny_all,
    ):
        self.planner = Planner(contract_path=contract_path, generate_fn=generate_fn)
        self.executor = Executor(target_dir=target_dir)
        self.recovery = RecoveryManager(
            generate_fn=generate_fn,
            max_attempts=max_repair_attempts,
            valid_check_ids={c["id"] for c in self.planner.all_checks()},
        )
        self.verify_fn = verify_fn
        self.checkpoint = Checkpoint(target_dir=target_dir)
        self.approval_fn = approval_fn

        self.max_agent_steps = max_agent_steps
        self.max_repair_attempts = max_repair_attempts
        self.max_deploy_attempts = max_deploy_attempts
        self.max_execution_time_seconds = max_execution_time_seconds

    def run(self, scan_result: dict) -> RunReport:
        start = time.monotonic()

        def _elapsed() -> float:
            return time.monotonic() - start

        def _check_budgets(steps_executed: int):
            if steps_executed > self.max_agent_steps:
                raise BudgetExceeded(
                    f"Exceeded max_agent_steps={self.max_agent_steps}"
                )
            if _elapsed() > self.max_execution_time_seconds:
                raise BudgetExceeded(
                    f"Exceeded max_execution_time_seconds={self.max_execution_time_seconds}"
                )

        # 1. ANALYZE — deterministic, no LLM
        gaps = self.planner.analyze_gaps(scan_result)
        if not gaps:
            return RunReport(
                status="already_ready",
                gaps_found=[],
                evidence=[],
                total_steps_executed=0,
                elapsed_seconds=_elapsed(),
            )

        # CHECKPOINT — capture the current (broken) state before any
        # modification happens. If this run doesn't end fully "ready",
        # every change gets rolled back to exactly this point.
        # Degrades gracefully (no rollback protection, not a hard failure)
        # in environments without a `git` binary, e.g. some serverless hosts.
        checkpoint_sha = None
        checkpoint_available = True
        try:
            checkpoint_sha = self.checkpoint.create_checkpoint(label="before-run")
        except CheckpointError as e:
            checkpoint_available = False

        # 2. PLAN — LLM-assisted, deterministically validated
        try:
            plan = self.planner.build_plan(gaps)
        except PlannerError as e:
            return RunReport(
                status="aborted",
                gaps_found=gaps,
                evidence=[],
                total_steps_executed=0,
                elapsed_seconds=_elapsed(),
                abort_reason=f"Planning failed: {e}",
            )
        except Exception as e:
            # Catches anything from the Gemini call itself — missing API
            # key, network failure, rate limit, auth error. These are
            # expected real-world failure modes at an external API
            # boundary, not programming bugs, so they end the run cleanly
            # with a reported reason instead of propagating as a crash.
            return RunReport(
                status="aborted",
                gaps_found=gaps,
                evidence=[],
                total_steps_executed=0,
                elapsed_seconds=_elapsed(),
                abort_reason=f"Planning failed (Gemini call error): {e}",
            )

        if not plan:
            # Real gaps exist (we wouldn't be here otherwise — see the
            # early return above for the genuinely-nothing-to-do case),
            # but Gemini returned an empty plan anyway. Silently treating
            # this as success would trigger a real bug: all(x for x in [])
            # is True in Python, so an empty evidence list would otherwise
            # be misread as "everything passed." Report it honestly instead.
            return RunReport(
                status="aborted",
                gaps_found=gaps,
                evidence=[],
                total_steps_executed=0,
                elapsed_seconds=_elapsed(),
                abort_reason=(
                    f"Gemini returned an empty plan despite {len(gaps)} real gap(s) "
                    f"needing action: {[g.check_id for g in gaps]}. Nothing was executed."
                ),
            )

        evidence: list[StepEvidence] = []
        steps_executed = 0
        deploy_attempts = 0
        last_deploy_url = None

        # 3. EXECUTE -> VERIFY -> RECOVER, per step
        for step in plan:
            try:
                _check_budgets(steps_executed)
            except BudgetExceeded as e:
                # Budget hit mid-run — real modifications may already exist
                # on disk, so roll back to the pre-run checkpoint rather
                # than leaving a half-modified target project behind.
                try:
                    if checkpoint_available:
                        self.checkpoint.rollback(checkpoint_sha)
                except CheckpointError:
                    pass  # best-effort — the abort_reason below is the priority
                return RunReport(
                    status="aborted",
                    gaps_found=gaps,
                    evidence=evidence,
                    total_steps_executed=steps_executed,
                    elapsed_seconds=_elapsed(),
                    abort_reason=str(e),
                )

            if step.tool == "deploy_cloud_run":
                deploy_attempts += 1
                if deploy_attempts > self.max_deploy_attempts:
                    evidence.append(
                        StepEvidence(
                            step=step,
                            result=ExecutionResult(
                                step_id=step.step_id, tool=step.tool, success=False,
                                raw_output="", error="max_deploy_attempts exceeded",
                            ),
                            verified=False,
                            diagnosis_log=["Skipped: deploy attempt budget exhausted."],
                        )
                    )
                    continue

            # POLICY GATE — risky steps must be explicitly approved before
            # they ever reach the executor. A denied step is recorded as
            # unverified evidence, not silently skipped and not silently run.
            if is_risky(step) and not self.approval_fn(step):
                evidence.append(
                    StepEvidence(
                        step=step,
                        result=ExecutionResult(
                            step_id=step.step_id, tool=step.tool, success=False,
                            raw_output="", error="Blocked: risky operation not approved",
                        ),
                        verified=False,
                        diagnosis_log=[
                            f"Step {step.step_id} ({step.tool}) requires approval and was not approved."
                        ],
                    )
                )
                continue

            # HEALTH-CHECK URL INJECTION — Gemini cannot know the real
            # deployment URL at plan time (it doesn't exist until AFTER a
            # successful deploy). Never trust whatever Gemini put in
            # check_health_endpoint's args; always use the URL from this
            # run's own most recent successful deployment, or skip the
            # step entirely if there isn't one.
            if step.tool == "check_health_endpoint":
                if last_deploy_url:
                    step.args["url"] = last_deploy_url
                else:
                    evidence.append(
                        StepEvidence(
                            step=step,
                            result=ExecutionResult(
                                step_id=step.step_id, tool=step.tool, success=False,
                                raw_output="", error="No successful deployment in this run to check",
                            ),
                            verified=False,
                            diagnosis_log=[
                                "Skipped: no deployment URL available yet — deployment either "
                                "hasn't run, was blocked, or failed."
                            ],
                        )
                    )
                    continue

            result = self.executor.execute_step(step)
            steps_executed += 1
            verified = self.verify_fn(step, result)

            # Track a successful deployment's URL for any later health-check step.
            if step.tool == "deploy_cloud_run" and result.success:
                try:
                    import ast
                    parsed = ast.literal_eval(result.raw_output)
                    if isinstance(parsed, dict) and parsed.get("url"):
                        last_deploy_url = parsed["url"]
                except (ValueError, SyntaxError):
                    pass
            diagnosis_log: list[str] = []
            attempts_used = 0

            # 4. RECOVER, bounded by max_repair_attempts
            if not verified:
                current_step, current_result = step, result
                for attempt in range(1, self.max_repair_attempts + 1):
                    try:
                        _check_budgets(steps_executed)
                    except BudgetExceeded:
                        break

                    try:
                        diagnosis = self.recovery.diagnose_and_patch(
                            current_step, current_result.raw_output or (current_result.error or ""), attempt
                        )
                    except RecoveryError as e:
                        diagnosis_log.append(f"Recovery attempt {attempt} failed to produce a fix: {e}")
                        break

                    diagnosis_log.append(diagnosis.diagnosis)
                    attempts_used = attempt

                    if diagnosis.corrective_step is None:
                        diagnosis_log.append("No safe corrective step proposed. Stopping recovery.")
                        break

                    current_result = self.executor.execute_step(diagnosis.corrective_step)
                    steps_executed += 1
                    verified = self.verify_fn(diagnosis.corrective_step, current_result)
                    current_step = diagnosis.corrective_step

                    if verified:
                        break

                result = current_result
                step = current_step  # log the step that actually produced this result —
                # a corrective step from recovery, if one ran — so "step" and "result"
                # in the output always describe the same real action, not the
                # original plan alongside a different attempt's outcome.

            evidence.append(
                StepEvidence(
                    step=step,
                    result=result,
                    verified=verified,
                    attempts_used=attempts_used,
                    diagnosis_log=diagnosis_log,
                )
            )

        overall_ready = all(e.verified for e in evidence)

        # ROLLBACK or COMMIT based on outcome — this is what makes the
        # "safe workspace" guarantee real: a run that doesn't end fully
        # verified leaves the target project exactly as it found it.
        try:
            if overall_ready and checkpoint_available:
                self.checkpoint.commit_changes(message="shipready: all checks verified")
            elif checkpoint_available:
                self.checkpoint.rollback(checkpoint_sha)
        except CheckpointError as e:
            # Checkpoint failure at this stage doesn't invalidate the
            # evidence already collected — report it, don't hide it.
            return RunReport(
                status="aborted",
                gaps_found=gaps,
                evidence=evidence,
                total_steps_executed=steps_executed,
                elapsed_seconds=_elapsed(),
                abort_reason=f"Run finished but checkpoint commit/rollback failed: {e}",
            )

        return RunReport(
            status="ready" if overall_ready else "not_ready",
            gaps_found=gaps,
            evidence=evidence,
            total_steps_executed=steps_executed,
            elapsed_seconds=_elapsed(),
        )