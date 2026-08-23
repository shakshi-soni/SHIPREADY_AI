"""
agent/policy.py — Approval gates for risky operations

Per the locked architecture: deployment, destructive file operations, and
credential/secret operations must not execute silently. This module is
the enforcement point — the Orchestrator checks every step against
RISKY_TOOLS before executing it, and only proceeds if an approval_fn
says yes.

Default behavior is DENY, not allow — a risky step with no approval_fn
configured, or one that returns False, is blocked and recorded as
evidence, never silently skipped or silently run.
"""

from __future__ import annotations

from typing import Callable

from agent.planner import PlanStep

# Tools that require explicit approval before execution. Currently this is
# just deploy_cloud_run (the only real "action with consequences" tool
# ShipReady has) — but the set is here, not hardcoded inline, so adding a
# delete_file or credential-touching tool later means updating one line,
# not hunting through the orchestrator.
RISKY_TOOLS: set[str] = {
    "deploy_cloud_run",
}

# ApprovalFn signature: (step) -> bool. True = approved, False = blocked.
ApprovalFn = Callable[[PlanStep], bool]


def deny_all(step: PlanStep) -> bool:
    """Safe default: every risky step is blocked unless the caller
    explicitly wires up a real approval mechanism (CLI prompt, API
    confirmation endpoint, config flag, etc.)."""
    return False


def allow_all(step: PlanStep) -> bool:
    """Explicit opt-in for automated/CI contexts where a human has
    already pre-approved risky operations for this run (e.g. a config
    flag set before a scheduled deploy). Never the default — must be
    passed in deliberately."""
    return True


def is_risky(step: PlanStep) -> bool:
    return step.tool in RISKY_TOOLS


class PolicyBlocked(Exception):
    """Raised (or recorded, depending on caller) when a risky step is
    denied approval."""

    def __init__(self, step: PlanStep):
        self.step = step
        super().__init__(
            f"Step {step.step_id} ({step.tool}) is a risky operation and was not approved."
        )