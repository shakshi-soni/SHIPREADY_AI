# ShipReady

**It doesn't claim readiness. It verifies it.**

An autonomous agent that inspects an incomplete software project, repairs what's missing, and independently verifies the result against a written contract — producing an evidence-backed readiness report instead of an AI's opinion.

Built for the **Taskmaster** track of the **All Things Agentic Hackathon**.

---

## ⚡ See it in 30 seconds

```
Incomplete project
      ↓
  ShipReady
      ↓
Inspect → Plan → Repair → Test → Deploy → Verify
      ↓
  10 / 10 checks verified
      ↓
  READY TO SHIP
```

▶ *Demo video: coming soon*

---

## 🚀 The problem

A project can look finished while secretly having missing docs, broken tests, no deployment, and no evidence that any of it actually works. "Done" is usually a claim.

Modern AI coding tools can generate software faster than ever — the bottleneck is increasingly *knowing whether what got generated is actually complete, reproducible, and deployable.* ShipReady targets that verification gap specifically, not code generation itself.

## The solution

Give ShipReady an incomplete project and one instruction: *"make this submission-ready."* It inspects the real repository, plans corrective actions with Gemini, executes them through deterministic tools, and independently re-checks every result before calling anything done.

**Reference demo:** `target-project/` is a deliberately incomplete Flask app shipped alongside ShipReady, used to demonstrate the full inspect → repair → verify loop end to end.

## Why this isn't just another coding agent

| | Typical coding agent | ShipReady |
|---|---|---|
| Output | Writes code, reports completion | Executes a full workflow, then independently verifies it |
| Testing | May suggest tests | Actually runs tests, reads the real exit code |
| Success claim | AI reports success | A separate Verifier decides — never the LLM |
| Audit trail | Limited | Every check recorded as evidence |
| Autonomy | Open-ended | Bounded: step, retry, time, and deploy limits |

---

## What's actually autonomous

| Decided by Gemini | Executed by deterministic tools | Decided by the Verifier |
|---|---|---|
| Which gaps matter, what order to fix them | File reads/writes, running pytest, building Docker, deploying, HTTP health checks | Whether each check actually passes |
| Diagnosing a test failure | — | Final ready / not-ready status |
| Proposing a corrective patch | — | — |

**The core principle: Gemini proposes. Deterministic tools execute. The Verifier decides.**

That's it — that single rule, applied consistently, is what the rest of this document demonstrates rather than restates.

## How it works

```
GOAL ("make this project submission-ready")
  ↓
INSPECT     — Verifier reads the real filesystem, runs pytest, checks for a Dockerfile
  ↓
ANALYZE     — gaps computed against contract.yaml (plain dict comparison, no LLM)
  ↓
PLAN        — Gemini proposes an ordered set of tool calls to close the gaps
  ↓
CHECKPOINT  — a real git commit is taken before anything is touched
  ↓
EXECUTE     — a deterministic tool performs the real action
  ↓
VERIFY      — the Verifier independently re-checks the result
  ↓
FAIL? → RECOVER  — Gemini diagnoses the raw failure, proposes one patch, retries (max 3)
  ↓
COMMIT or ROLLBACK  — fully verified → commit the changes. Not fully verified → git reset back to the checkpoint
  ↓
EVIDENCE    — every check's real result recorded with a timestamp
  ↓
READINESS REPORT — built from the evidence log
```

## 🧠 Architecture

```
                              USER
                               │
                               ▼
                        FastAPI (Cloud Run)
                               │
                               ▼
                          ORCHESTRATOR
                               │
                 ┌─────────────┼──────────────┐
                 ▼             ▼              ▼
             GEMINI        PLANNER      LOCAL STATE
          (Google GenAI                    (JSON)
              SDK)
                 │             │
                 └──────┬──────┘
                        ▼
                  TOOL ROUTER
                        │
        ┌───────────────┼────────────────┬─────────────────┐
        ▼               ▼                ▼                 ▼
   REPOSITORY        TESTING        DEPLOYMENT          DOCGEN
     TOOLS             TOOLS           TOOLS             TOOLS
        │               │                │                 │
        └───────────────┴───────┬────────┴─────────────────┘
                                 ▼
                         TARGET SANDBOX
                    (target-project/, isolated from
                     ShipReady's own code, protected
                       by a git checkpoint)
                                 │
                                 ▼
                            VERIFIER
                                 │
                                 ▼
                          EVIDENCE LOG
                                 │
                                 ▼
                       READINESS REPORT
```

## 🛡️ Engineering principles

1. **The agent and the target are isolated.** ShipReady never modifies its own running code — only the sandboxed `target-project/`.
2. **Tests are protected.** `tests/` is read-only, enforced at two independent layers (planner rejects the plan; executor refuses the write even if a plan slipped through). A SHA-256 hash of `tests/`, captured before the run, catches any modification — including partial ones.
3. **Autonomy is bounded.** `MAX_AGENT_STEPS`, `MAX_REPAIR_ATTEMPTS`, `MAX_DEPLOY_ATTEMPTS`, `MAX_EXECUTION_TIME_SECONDS`.
4. **Risky operations require approval.** `deploy_cloud_run` is blocked by default; a run must explicitly opt in to allow it.
5. **A run that isn't fully verified leaves no trace.** Real git checkpoint before modification; rollback on anything short of fully verified.

## Trust model

| Component | Role | Trust |
|---|---|---|
| Gemini | Reasoning, planning, diagnosis | Probabilistic |
| Orchestrator | Control flow | Deterministic |
| Tools | Execution | Deterministic |
| Target project | The thing being repaired | Untrusted |
| Verifier | Validation | Final authority for the defined readiness contract |

---

## ✅ The readiness contract

`contract.yaml` defines what "ready" means as data, not opinion — all **10 checks**:

```
READINESS CONTRACT
──────────────────────────────────
01  README exists
02  README has real Setup / Usage / Architecture sections (not just headings)
03  Architecture doc exists (standalone or a substantive README section)
04  Source entrypoint present
05  Test suite exists
06  Test suite passes (real pytest exit code)
07  Test files unmodified since the run started (SHA-256 hash check)
08  Dockerfile exists
09  Deployed to Cloud Run
10  GET /health → 200, status: healthy
```

## Verification engine

Every check re-reads reality — file contents, a real pytest run, a real HTTP request:

- **Documentation** — sections must exist *and* contain real content; a deterministic detector rejects `TODO`, `coming soon`, and headings with near-empty content underneath
- **Tests** — pytest is re-run, the exit code is read directly, not asked about
- **Test integrity** — a hash of `tests/` is compared before/after the run
- **Deployment / health** — the real result dict from `gcloud run deploy`, and a real `GET /health` request against the live URL

## 📊 Evidence log

Every check produces a recorded entry — `check_id`, `passed`, the real evidence string, a timestamp, and where applicable a git SHA and deployment revision. The final report is generated from these entries, not from Gemini's account of what happened.

**A real captured run** (local test, mocked Gemini plan, everything else — the file write, the re-verification — genuinely executed):

```json
{
  "status": "ready",
  "total_steps_executed": 1,
  "elapsed_seconds": 0.0876,
  "evidence": [
    {
      "step": {"tool": "write_file", "check_id": "test_suite_passes"},
      "verified": true
    }
  ]
}
```

*This confirms the loop itself works end to end. It does not include a live Gemini API call or a live Cloud Run deployment — both are built and unit-tested against real subprocess/HTTP behavior, but not yet exercised against live Google services. See [Current test coverage](#-current-test-coverage) below for the honest breakdown.*

## Failure recovery

```
STEP FAILS
    ↓
Verifier records the real failure evidence
    ↓
Gemini diagnoses the raw output, proposes one corrective step
    ↓
Corrective step validated — must not target tests/, must use a real tool
    ↓
Executed, re-verified
    ↓
PASS → continue          FAIL → retry (max 3 attempts total)
    ↓
Still failing → recorded as NOT READY, not hidden, not retried forever
```

## Security & safety

- Sandbox isolation, test-file protection (two layers + hash), path-escape protection on every write
- Execution limits: step count, repair attempts, deploy attempts, wall-clock time
- Approval gate on deployment (default: denied)
- Real git checkpoint/rollback — verified with real file corruption and real restoration in testing
- No secrets in generated content; `.env` is git-ignored

---

## 🛠️ Tech stack

| Layer | Technology |
|---|---|
| Reasoning | Gemini, via the **Google GenAI SDK** |
| Orchestration | Custom Python agent loop |
| API | FastAPI + Uvicorn |
| Infrastructure | Google Cloud Run |
| Verification | pytest, httpx, hashlib |
| Rollback | Git (subprocess) |
| State | Local JSON |
| Config | YAML + `.env` |

## Project structure

```
shipready/
├── agent/            # orchestrator, planner, executor, recovery, policy, prompts
├── app/               # FastAPI entrypoint + API routes
│   └── api/
├── tools/              # repository, testing, deployment, docgen, checkpoint
├── verification/        # independent verifiers + evidence log
├── state/                 # local JSON state store
├── target-project/         # reference project ShipReady repairs (demo fixture)
│   └── tests/               # read-only to the agent
├── contract.yaml             # the readiness contract
├── Dockerfile
├── requirements.txt
└── README.md
```

## Installation

```bash
git clone <repository-url>
cd shipready

python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # Mac/Linux

pip install -r requirements.txt
pip install -r target-project/requirements.txt
```

## Configuration

```bash
cp .env.example .env
```

```
GEMINI_API_KEY=your_key_here      # https://aistudio.google.com/apikey
GCP_PROJECT_ID=your_gcp_project   # only needed for the deploy step
```

`.env` is git-ignored — never commit it.

## Running locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
```

Open `http://localhost:8080/docs`, or:

```bash
curl http://localhost:8080/health
curl -X POST http://localhost:8080/run
curl http://localhost:8080/evidence
```

## Cloud Run deployment

```bash
gcloud auth login
gcloud config set project YOUR_PROJECT_ID
gcloud services enable run.googleapis.com cloudbuild.googleapis.com

gcloud run deploy shipready-orchestrator \
  --source . \
  --region us-central1 \
  --allow-unauthenticated
```

## Reproducibility

- Python 3.12, dependencies pinned in `requirements.txt`
- Env vars: `GEMINI_API_KEY`, `GCP_PROJECT_ID`
- `target-project/` ships with one deliberate bug (`/health` returns `"error"` not `"healthy"`) so a real repair is always demonstrable
- Test command: `pytest -v` inside `target-project/`

## 🧪 Current test coverage

`target-project/`'s own suite, run against its current incomplete state:

```
tests/test_app.py::test_health_returns_healthy       FAILED  (the deliberate bug)
tests/test_app.py::test_get_tasks_starts_empty        PASSED
tests/test_app.py::test_add_task_success                PASSED
tests/test_app.py::test_add_task_missing_title_returns_400  PASSED
tests/test_app.py::test_added_task_appears_in_list       PASSED

1 failed, 4 passed
```

ShipReady's own modules are covered by an independent suite exercising tool routing, verifier independence from tool self-reports, sandbox path-escape protection, test-file write protection, tamper-hash detection, real git checkpoint/rollback, approval-gate default-deny behavior, and placeholder-content rejection — all against real files and real subprocess calls, run twice each to confirm determinism.

**Honestly not yet tested:** a live Gemini API call, and a live `gcloud run deploy` + health check. Both are built and exercise real, correct code paths against mocked or missing external services (graceful failure confirmed); neither has been exercised against the real Google services yet.

## Limitations

**In scope:** Python projects, pytest-based testing, Google Cloud Run, a fixed 10-check contract.

**Out of scope:** other languages/build systems, other cloud providers, unbounded execution, fully automatic deployment without approval.

## Resource & cost controls

| Limit | Purpose |
|---|---|
| `MAX_AGENT_STEPS` | Caps total plan steps per run |
| `MAX_REPAIR_ATTEMPTS = 3` | Caps recovery retries per failing step |
| `MAX_DEPLOY_ATTEMPTS = 2` | Caps expensive redeploys |
| `MAX_EXECUTION_TIME_SECONDS` | Wall-clock cap per run |

## Hackathon alignment

Gemini (via the Google GenAI SDK) drives the reasoning; Google Cloud Run is the deployment target the agent both runs on and deploys to; the full inspect → plan → execute → verify → recover loop is a real multi-step autonomous workflow, not a chat wrapper, fitting the Taskmaster track's request for a complete workflow over a conversational interface.

## Why we built it

Software projects rarely fail because nobody wrote code. They fail because "finished" was never objectively defined or verified. ShipReady was built around a simple idea: completion should be something a system can prove, not something an AI can claim.

## License

MIT