"""
selfcheck.py — Run this from your project root to definitively confirm
every fix discussed in this conversation is actually active on disk.

Usage:
    python selfcheck.py

Prints a clear PASS/FAIL for each check. If anything shows FAIL, that
exact file needs to be re-saved from what was delivered in chat.
"""

import sys
from pathlib import Path

root = Path(__file__).parent
results = []


def check(label, filepath, must_contain, must_not_contain=None):
    path = root / filepath
    if not path.exists():
        results.append((False, f"{label}: FILE MISSING — {filepath}"))
        return
    content = path.read_text(encoding="utf-8", errors="replace")
    if must_contain not in content:
        results.append((False, f"{label}: MISSING expected content in {filepath}"))
        return
    if must_not_contain and must_not_contain in content:
        results.append((False, f"{label}: STALE content still present in {filepath}"))
        return
    results.append((True, f"{label}: OK ({filepath})"))


check("Windows python fallback chain", "tools/testing.py", "_find_working_python")
check("run_build registered in executor", "agent/executor.py", '"run_build": "run_build"')
check("run_build in planner's AVAILABLE_TOOLS", "agent/planner.py", '"run_build":')
check("checkpoint files excluded from list_files", "tools/repository.py", "EXCLUDED_DIRS")
check("recovery prompt includes tool list", "agent/recovery.py", "tool_list=")
check("planning prompt discourages shallow plans", "agent/prompts.py", "NOT acceptable")
check("JSON parser uses raw_decode (handles trailing junk)", "agent/planner.py", "raw_decode")
check("verifier never blindly trusts unknown checks", "verification/verifier.py", "Treating as unverified")
check("health-check URL injection in orchestrator", "agent/orchestrator.py", "last_deploy_url")
check("cloud checks marked non-required in contract", "contract.yaml", "required: false")
check("evidence summary respects required flag", "verification/evidence.py", "required_passed")
check("UI route exists", "app/api/ui.py", "CLOUD_CHECK_IDS")
check("UI wired into main app", "app/main.py", "ui_router")

print("=" * 70)
all_ok = True
for ok, msg in results:
    icon = "✅" if ok else "❌"
    print(f"{icon} {msg}")
    if not ok:
        all_ok = False
print("=" * 70)

if all_ok:
    print("\nALL FIXES CONFIRMED ACTIVE. If /run still misbehaves, it's a live")
    print("Gemini/environment issue, not a stale-file issue.")
else:
    print("\nSOME FILES ARE STALE — re-save the ones marked ❌ above from the")
    print("versions delivered in chat, then restart uvicorn.")
    sys.exit(1)