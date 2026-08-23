"""
agent/recovery.py — ShipReady Recovery Manager

When a step's verification fails, this module asks Gemini to diagnose the
raw failure output and propose exactly one corrective step. It reuses the
same JSON-parsing discipline as the planner: structured output only, tool
names validated against the real tool list, and any attempt to target a
tests/ path is rejected before it ever reaches the executor.

Hard limit: MAX_REPAIR_ATTEMPTS caps how many times this loop can run for
a single failing step. There is no path to infinite retries.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Optional

from agent.planner import AVAILABLE_TOOLS, PlanStep, PlannerError, _strip_code_fences
from agent.prompts import DIAGNOSIS_PROMPT, SYSTEM_ROLE


class RecoveryError(Exception):
    """Raised when a corrective step cannot be safely produced."""


@dataclass
class DiagnosisResult:
    diagnosis: str
    corrective_step: Optional[PlanStep]


class RecoveryManager:
    def __init__(
        self,
        generate_fn: Callable[[str, str], str],
        max_attempts: int = 3,
        valid_check_ids: Optional[set[str]] = None,
    ):
        self.generate_fn = generate_fn
        self.max_attempts = max_attempts
        # When provided, a corrective step whose check_id isn't a real
        # contract check is rejected outright — this is a real, observed
        # failure mode: recovery inventing check_ids like
        # "project_files_listed" that can never be verified, burning
        # repair attempts (and real API quota) chasing a phantom goal
        # instead of the actual failing check.
        self.valid_check_ids = valid_check_ids

    def diagnose_and_patch(
        self,
        failed_step: PlanStep,
        raw_output: str,
        attempt_number: int,
    ) -> DiagnosisResult:
        if attempt_number > self.max_attempts:
            raise RecoveryError(
                f"Attempt {attempt_number} exceeds max_attempts={self.max_attempts}. "
                "Stopping to avoid an unbounded retry loop."
            )

        user_prompt = DIAGNOSIS_PROMPT.format(
            tool_list="\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_TOOLS.items()),
            failed_step=json.dumps(failed_step.__dict__, indent=2),
            raw_output=raw_output[:2000],  # cap prompt size on huge tracebacks
            attempt_number=attempt_number,
            max_attempts=self.max_attempts,
        )
        raw = self.generate_fn(SYSTEM_ROLE, user_prompt)
        return self._parse_diagnosis_response(raw)

    def _parse_diagnosis_response(self, raw_text: str) -> DiagnosisResult:
        cleaned = _strip_code_fences(raw_text)
        try:
            decoder = json.JSONDecoder(strict=False)
            data, _ = decoder.raw_decode(cleaned)
        except json.JSONDecodeError as e:
            context_start = max(0, e.pos - 200)
            context_end = min(len(cleaned), e.pos + 200)
            raise RecoveryError(
                f"Gemini did not return valid JSON: {e}\n"
                f"Context around the error (position {e.pos}):\n"
                f"...{cleaned[context_start:context_end]}..."
            )

        if not isinstance(data, dict) or "diagnosis" not in data:
            raise RecoveryError(f"Diagnosis response missing required fields: {data!r}")

        diagnosis = str(data["diagnosis"])
        corrective_raw = data.get("corrective_step")

        if corrective_raw is None:
            return DiagnosisResult(diagnosis=diagnosis, corrective_step=None)

        if not isinstance(corrective_raw, dict):
            raise RecoveryError(f"corrective_step must be an object or null, got: {corrective_raw!r}")

        tool = corrective_raw.get("tool")
        if tool not in AVAILABLE_TOOLS:
            raise RecoveryError(f"Corrective step uses unknown tool {tool!r}")

        check_id = str(corrective_raw.get("check_id", ""))
        if self.valid_check_ids is not None and check_id not in self.valid_check_ids:
            raise RecoveryError(
                f"Corrective step targets check_id {check_id!r}, which is not a "
                f"real contract check — refusing to chase a phantom goal. "
                f"Valid check_ids: {sorted(self.valid_check_ids)}"
            )

        args = corrective_raw.get("args", {})
        target_path = str(args.get("path", "")) if isinstance(args, dict) else ""
        if "tests/" in target_path or target_path.startswith("tests"):
            raise RecoveryError(
                f"Corrective step targets a test file ({target_path!r}) — refusing. "
                "A patch may never touch tests/, even during recovery."
            )

        try:
            corrective_step = PlanStep(
                step_id=int(corrective_raw.get("step_id", 1)),
                action=str(corrective_raw.get("action", "")),
                tool=tool,
                args=args if isinstance(args, dict) else {},
                check_id=str(corrective_raw.get("check_id", "")),
                rationale=str(corrective_raw.get("rationale", "")),
            )
        except (TypeError, ValueError, PlannerError) as e:
            raise RecoveryError(f"Corrective step has invalid fields: {e}")

        return DiagnosisResult(diagnosis=diagnosis, corrective_step=corrective_step)