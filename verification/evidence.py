"""
verification/evidence.py — Evidence Log

Every recorded entry comes from an actual check result (a real file read,
a real pytest run, a real HTTP call) — never from LLM narration. The
summary() report is built entirely from this recorded evidence, which is
what makes ShipReady's final "X/Y verified" claim inspectable rather than
just asserted.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class EvidenceEntry:
    check_id: str
    passed: bool
    evidence: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    git_sha: str = ""
    deployment_revision: str = ""


class EvidenceLog:
    def __init__(self, path: str | Path = "state/evidence.json"):
        self.path = Path(path)
        self.entries: list[EvidenceEntry] = []

    def record(
        self,
        check_id: str,
        passed: bool,
        evidence: str,
        git_sha: str = "",
        deployment_revision: str = "",
    ) -> EvidenceEntry:
        entry = EvidenceEntry(
            check_id=check_id,
            passed=passed,
            evidence=evidence,
            git_sha=git_sha,
            deployment_revision=deployment_revision,
        )
        self.entries.append(entry)
        return entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.path, "w") as f:
            json.dump([asdict(e) for e in self.entries], f, indent=2)

    def load(self) -> None:
        if not self.path.exists():
            self.entries = []
            return
        with open(self.path) as f:
            raw = json.load(f)
        self.entries = [EvidenceEntry(**item) for item in raw]

    def summary(self, contract_checks: list[dict]) -> dict:
        """Builds the final readiness report from recorded evidence only.
        contract_checks: the flattened list from Planner.all_checks().

        Overall READY/NOT READY is determined by REQUIRED checks only —
        a check marked required: false (e.g. cloud_run_deployed in the
        current Gemini-only operating mode) is still shown honestly in
        the checklist, but doesn't block an overall ready result."""
        latest_by_check: dict[str, EvidenceEntry] = {}
        for entry in self.entries:
            latest_by_check[entry.check_id] = entry  # last recorded wins

        rows = []
        passed_count = 0
        required_total = 0
        required_passed = 0
        for check in contract_checks:
            check_id = check["id"]
            required = check.get("required", True)
            entry = latest_by_check.get(check_id)
            passed = entry.passed if entry else False
            if passed:
                passed_count += 1
            if required:
                required_total += 1
                if passed:
                    required_passed += 1
            rows.append(
                {
                    "check_id": check_id,
                    "description": check["description"],
                    "required": required,
                    "passed": passed,
                    "evidence": entry.evidence if entry else "No evidence recorded — check never ran",
                    "timestamp": entry.timestamp if entry else None,
                }
            )

        total = len(contract_checks)
        return {
            "status": "READY" if required_passed == required_total else "NOT READY",
            "verified": f"{passed_count}/{total}",
            "required_verified": f"{required_passed}/{required_total}",
            "checks": rows,
        }