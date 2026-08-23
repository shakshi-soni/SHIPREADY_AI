"""
agent/planner.py — ShipReady Planner

Responsibilities:
  1. Load the readiness contract (contract.yaml).
  2. Deterministically compare a repository scan result against the
     contract to find gaps (no LLM needed for this part — it's just a
     dict comparison, so it's fast, free, and can't hallucinate).
  3. Ask Gemini to turn those gaps into an ordered, tool-based plan.
  4. Parse and validate Gemini's response into PlanStep objects.

Design note: the Gemini call is injected as `generate_fn` rather than
hardcoded to the google-genai client. This keeps Planner testable without
a live API key, and the same class works in production by passing a real
Gemini-backed function at construction time.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import yaml

from agent.prompts import GAP_ANALYSIS_PROMPT, PLANNING_PROMPT, SYSTEM_ROLE


class PlannerError(Exception):
    """Raised when the planner cannot produce a valid plan."""


@dataclass
class Gap:
    check_id: str
    description: str
    evidence: str = ""


@dataclass
class PlanStep:
    step_id: int
    action: str
    tool: str
    args: dict = field(default_factory=dict)
    check_id: str = ""
    rationale: str = ""

    def __post_init__(self):
        if not isinstance(self.step_id, int) or self.step_id < 1:
            raise PlannerError(f"Invalid step_id: {self.step_id!r}")
        if not self.tool:
            raise PlannerError(f"Step {self.step_id} is missing a tool")


# Tools ShipReady's executor exposes. The planner may only choose from
# this list — anything else is rejected during validation, not silently
# passed through.
AVAILABLE_TOOLS = {
    "read_file": "Read a file from the target project (read-only).",
    "write_file": "Write/overwrite a source file. Refuses any path under tests/.",
    "list_files": "List files in the target project.",
    "run_tests": "Run pytest against the target project (read-only on test files).",
    "run_build": "Compile all .py source files to catch syntax errors before testing/deploying.",
    "generate_readme": "Generate/update README.md from the actual repo contents.",
    "generate_architecture_doc": "Generate an architecture description from the codebase.",
    "deploy_cloud_run": "Deploy the target project to Google Cloud Run.",
    "check_health_endpoint": "HTTP GET the deployed /health endpoint.",
}


def _strip_code_fences(text: str) -> str:
    """Gemini sometimes wraps JSON in ```json ... ``` even when told not to.
    Strip that defensively rather than trusting the prompt alone."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


class Planner:
    def __init__(
        self,
        contract_path: str | Path = "contract.yaml",
        generate_fn: Optional[Callable[[str, str], str]] = None,
    ):
        """
        generate_fn: callable(system_prompt: str, user_prompt: str) -> raw text response.
        If None, build_plan() will raise rather than silently doing nothing —
        callers must explicitly wire up a Gemini client (or a test double).
        """
        self.contract_path = Path(contract_path)
        self.contract = self._load_contract()
        self.generate_fn = generate_fn

    # ---------- Contract loading ----------

    def _load_contract(self) -> dict:
        if not self.contract_path.exists():
            raise PlannerError(f"Contract file not found: {self.contract_path}")
        with open(self.contract_path) as f:
            data = yaml.safe_load(f)
        if not data or "checks" not in data:
            raise PlannerError("contract.yaml is missing a top-level 'checks' section")
        return data

    def all_checks(self) -> list[dict]:
        """Flatten contract.yaml's grouped checks into a single list."""
        flat = []
        for group in self.contract["checks"].values():
            for check in group:
                flat.append(check)
        return flat

    # ---------- Deterministic gap analysis (no LLM) ----------

    def analyze_gaps(self, scan_result: dict) -> list[Gap]:
        """
        scan_result: dict mapping check_id -> bool (True = satisfied).
        Any required check missing from scan_result, or present but False,
        is treated as a gap. This step is pure Python — no model call,
        so it can't hallucinate a false pass or a false gap.
        """
        gaps = []
        for check in self.all_checks():
            check_id = check["id"]
            required = check.get("required", True)
            satisfied = scan_result.get(check_id, False)
            if required and not satisfied:
                gaps.append(
                    Gap(
                        check_id=check_id,
                        description=check["description"],
                        evidence=scan_result.get(f"{check_id}_evidence", "not found"),
                    )
                )
        return gaps

    # ---------- LLM-assisted planning ----------

    def build_plan(self, gaps: list[Gap]) -> list[PlanStep]:
        if not gaps:
            return []
        if self.generate_fn is None:
            raise PlannerError(
                "No generate_fn configured — Planner needs a Gemini-backed "
                "callable to turn gaps into a plan."
            )

        tool_list = "\n".join(f"- {name}: {desc}" for name, desc in AVAILABLE_TOOLS.items())
        gaps_json = json.dumps([g.__dict__ for g in gaps], indent=2)
        user_prompt = PLANNING_PROMPT.format(tool_list=tool_list, gaps=gaps_json)

        raw = self.generate_fn(SYSTEM_ROLE, user_prompt)
        return self._parse_plan_response(raw)

    def _parse_plan_response(self, raw_text: str) -> list[PlanStep]:
        cleaned = _strip_code_fences(raw_text)
        try:
            # Use raw_decode via a JSONDecoder instead of json.loads() directly.
            # json.loads() requires the ENTIRE string to be exactly one JSON
            # value with nothing after it — but Gemini sometimes appends
            # trailing content after a complete, valid JSON value (a stray
            # repeated brace, an extra newline plus junk). raw_decode() parses
            # the first complete JSON value and simply ignores whatever comes
            # after it, which is exactly the right behavior here: the plan
            # itself is real and complete, trailing noise shouldn't sink it.
            decoder = json.JSONDecoder(strict=False)
            data, _ = decoder.raw_decode(cleaned)
        except json.JSONDecodeError as e:
            # Show context AROUND the actual failure position, not just the
            # first 500 chars — for long responses the real problem is
            # often well past that point and invisible in a truncated dump.
            context_start = max(0, e.pos - 200)
            context_end = min(len(cleaned), e.pos + 200)
            raise PlannerError(
                f"Gemini did not return valid JSON: {e}\n"
                f"Context around the error (position {e.pos}):\n"
                f"...{cleaned[context_start:context_end]}..."
            )

        if not isinstance(data, list):
            raise PlannerError(f"Expected a JSON array of steps, got: {type(data)}")

        steps = []
        for i, item in enumerate(data, start=1):
            if not isinstance(item, dict):
                raise PlannerError(f"Plan item {i} is not a JSON object: {item!r}")

            tool = item.get("tool")
            if tool not in AVAILABLE_TOOLS:
                raise PlannerError(
                    f"Plan step {i} references unknown tool {tool!r}. "
                    f"Allowed: {sorted(AVAILABLE_TOOLS)}"
                )

            check_id = str(item.get("check_id", ""))
            valid_check_ids = {c["id"] for c in self.all_checks()}
            if check_id not in valid_check_ids:
                raise PlannerError(
                    f"Plan step {i} references check_id {check_id!r}, which is not "
                    f"one of the real checks in the contract. Rejecting — a step "
                    f"targeting a check that doesn't exist can never be verified, "
                    f"and would waste real work chasing a phantom goal. "
                    f"Valid check_ids: {sorted(valid_check_ids)}"
                )

            args = item.get("args", {})
            target_path = str(args.get("path", "")) if isinstance(args, dict) else ""
            if "tests/" in target_path or target_path.startswith("tests"):
                raise PlannerError(
                    f"Plan step {i} targets a test file ({target_path!r}), "
                    "which is forbidden — rejecting entire plan."
                )

            try:
                step = PlanStep(
                    step_id=int(item.get("step_id", i)),
                    action=str(item.get("action", "")),
                    tool=tool,
                    args=args if isinstance(args, dict) else {},
                    check_id=str(item.get("check_id", "")),
                    rationale=str(item.get("rationale", "")),
                )
            except (TypeError, ValueError) as e:
                raise PlannerError(f"Plan step {i} has invalid fields: {e}")

            steps.append(step)

        steps.sort(key=lambda s: s.step_id)
        return steps