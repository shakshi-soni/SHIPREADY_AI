"""
app/api/routes.py — ShipReady API routes

Endpoints:
  GET  /health           Cloud Run liveness check for THIS service
                          (not to be confused with the target project's
                          own /health endpoint, which is a different thing
                          entirely — that one lives in target-project/app.py
                          and gets checked by verification/deployment.py).
  POST /run               Triggers a full inspect -> plan -> execute ->
                           verify -> recover cycle against the target project.
  GET  /status            Last known run state (from LocalStore).
  GET  /evidence           Full evidence-backed readiness report.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
def health():
    """Liveness check for the ShipReady service itself (Cloud Run uses
    this to confirm the container is up) — separate from the target
    project's own /health endpoint that ShipReady inspects and fixes."""
    return {"status": "healthy", "service": "shipready-orchestrator"}


@router.post("/run")
def run(request: Request, approve_deploy: bool = False):
    """Runs one full ShipReady cycle: scans the target project for real,
    builds a plan for any gaps, executes it, and independently verifies
    every claim. Returns the full run report, generated entirely from
    recorded evidence — never from LLM narration.

    approve_deploy: risky operations (currently: deploy_cloud_run) are
    blocked by default (see agent/policy.py). Pass ?approve_deploy=true
    to explicitly approve them for this run. This is a deliberate,
    per-request opt-in — there is no way to make deployment silent."""
    orchestrator = request.app.state.orchestrator
    verifier = request.app.state.verifier
    store = request.app.state.store

    # Wire the per-request approval choice into this run only — the
    # orchestrator's default stays deny_all for every other caller.
    from agent.policy import allow_all, deny_all
    orchestrator.approval_fn = allow_all if approve_deploy else deny_all

    store.update(status="running", started_at=datetime.now(timezone.utc).isoformat())

    try:
        scan_result = verifier.full_scan()
        report = orchestrator.run(scan_result)
    except Exception as e:
        # Safety net: even though Orchestrator.run() already catches planning
        # failures internally, this guards against anything unexpected
        # (e.g. a bug in a future change) so /run always returns clean JSON,
        # never a raw 500 traceback.
        store.update(status="error", error=str(e), finished_at=datetime.now(timezone.utc).isoformat())
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": str(e)},
        )

    store.update(
        status=report.status,
        finished_at=datetime.now(timezone.utc).isoformat(),
        total_steps_executed=report.total_steps_executed,
        elapsed_seconds=report.elapsed_seconds,
    )

    planner = request.app.state.planner
    evidence_log = request.app.state.evidence_log
    # full_scan() (above) already recorded every one of the 10 contract
    # checks to the evidence log, real evidence attached — this makes that
    # visible in the /run response itself, not just via a separate /evidence
    # call. Without this, an "already_ready" result (nothing to fix) came
    # back with an empty evidence list even though every check was, in
    # fact, genuinely verified moments earlier.
    readiness = evidence_log.summary(planner.all_checks())

    return {
        "status": report.status,
        "gaps_found": [asdict(g) for g in report.gaps_found],
        "total_steps_executed": report.total_steps_executed,
        "elapsed_seconds": report.elapsed_seconds,
        "abort_reason": report.abort_reason,
        "readiness": readiness,
        "evidence": [
            {
                "step": asdict(e.step),
                "result": asdict(e.result),
                "verified": e.verified,
                "attempts_used": e.attempts_used,
                "diagnosis_log": e.diagnosis_log,
            }
            for e in report.evidence
        ],
    }


@router.get("/status")
def status(request: Request):
    """Returns the last known run state without triggering a new run —
    useful for a UI polling progress, or checking state after a crash."""
    store = request.app.state.store
    return store.load()


@router.get("/evidence")
def evidence(request: Request):
    """Returns the full contract-compliance report built from recorded
    evidence: X/Y verified, with the real evidence string behind each
    check — not an LLM's summary of what it thinks it did."""
    planner = request.app.state.planner
    evidence_log = request.app.state.evidence_log
    return evidence_log.summary(planner.all_checks())