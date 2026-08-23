# ShipReady — Architecture

**One-line spec:** A Gemini-powered agent (via the Google GenAI SDK) that inspects an incomplete Python project, plans corrective actions, executes them through deterministic tools, verifies each claim independently, and produces an evidence-backed submission-readiness report.

**Core principle (keep this above your desk):**
> The LLM reasons. Tools act. Verifiers prove.

---

## 1. Layered Architecture

```
                              USER
                               │
                               ▼
                        ┌─────────────┐
                        │     UI      │   (simple status feed, not a dashboard)
                        └──────┬──────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │   CLOUD RUN SERVICE    │  ← Google Cloud requirement #1
                   │  (FastAPI orchestrator)│    (this IS your deployed app)
                   └───────────┬────────────┘
                               │
                               ▼
                   ┌───────────────────────┐
                   │    ORCHESTRATOR         │
                   │   (Orchestrator loop)  │
                   └───────────┬────────────┘
                               │
                 ┌─────────────┼──────────────┐
                 ▼             ▼              ▼
           ┌──────────┐  ┌───────────┐  ┌─────────────┐
           │  GEMINI  │  │  PLANNER  │  │ LOCAL STATE │
           │ (reason) │  │           │  │   (JSON)    │
           └────┬─────┘  └─────┬─────┘  └─────────────┘
                │              │
                └──────┬───────┘
                       ▼
               ┌───────────────┐
               │  TOOL ROUTER  │   ← LLM picks tool, tool does deterministic work
               └───────┬───────┘
                       │
        ┌──────────────┼───────────────┬────────────────┐
        ▼              ▼               ▼                ▼
   ┌─────────┐   ┌───────────┐   ┌───────────┐   ┌─────────────┐
   │  REPO   │   │   TEST    │   │  DEPLOY   │   │   DOC/ARCH  │
   │  TOOLS  │   │  TOOLS    │   │  TOOLS    │   │  GENERATOR  │
   └────┬────┘   └─────┬─────┘   └─────┬─────┘   └──────┬──────┘
        │              │               │                │
        └──────────────┴───────┬───────┴────────────────┘
                                ▼
                       ┌─────────────────┐
                       │    VERIFIER     │  ← deterministic only, no LLM trust
                       │ (proves claims) │
                       └────────┬────────┘
                                ▼
                       ┌─────────────────┐
                       │  EVIDENCE LOG   │  ← timestamped, re-runnable checks
                       └────────┬────────┘
                                ▼
                       SUBMISSION-READY REPORT
```

**Target repo lives OUTSIDE the live agent** — the agent never edits its own running code. It operates on a sandboxed target project (a copy, or a separate repo) via a temp branch.

```
AGENT (live, on Cloud Run)  ──inspects/modifies──▶  TARGET PROJECT (sandbox/branch)
                                                            │
                                                     tests → verify → evidence
```

---

## 2. Component Responsibilities

| Component | Job | Trust level |
|---|---|---|
| Gemini | Interpret repo, find gaps, plan actions, diagnose failures, propose fixes | Probabilistic — never trusted alone |
| Orchestrator | Runs the loop: inspect → plan → act → observe → verify → replan. Uses the Google GenAI SDK to call Gemini. | Deterministic control flow |
| Tool Router | Maps LLM's chosen action to an actual function call | Deterministic |
| Repo Tools | `list_files`, `read_file`, `write_file` (source only) | Deterministic, source-only write access |
| Test Tools | `run_tests` (read-only on test files) | Deterministic |
| Deploy Tools | `deploy_cloud_run`, `check_endpoint` | Deterministic |
| Verifier | Independently checks every claim (file exists, test exit code, HTTP 200, etc.) | **Ground truth — final authority** |
| Evidence Log | Records every action + result + timestamp + git SHA + deployment revision (where applicable) | Immutable record, not LLM-generated |

**Hard rule: test files are read-only to the agent.** Only source files (`app.py` etc.) are writable. This structurally prevents the classic LLM cheat of loosening an assertion to fake a pass.

---

## 3. Folder Structure

```
shipready/
├── app/
│   ├── main.py                 # FastAPI entrypoint (Cloud Run service)
│   └── api/
│       └── routes.py
├── agent/
│   ├── orchestrator.py         # agent loop (Google GenAI SDK)
│   ├── planner.py              # turns gaps into an action plan
│   ├── executor.py             # calls tools per plan step
│   ├── recovery.py             # diagnose → patch → retry (max 3)
│   └── prompts.py
├── tools/
│   ├── repository.py           # read/write source, read-only tests
│   ├── testing.py               # run_tests, run_build
│   ├── deployment.py            # gcloud run deploy, check_endpoint
│   └── docgen.py                 # README + architecture generation
├── verification/
│   ├── requirements.py          # checklist-based checks
│   ├── tests.py                 # parses pytest exit code + output
│   ├── deployment.py            # HTTP health check
│   └── evidence.py               # writes evidence log entries
├── state/
│   └── local_store.py            # JSON state (swap for Firestore later, not now)
├── target-project/               # the deliberately-broken demo repo
│   ├── app.py
│   ├── tests/test_app.py
│   ├── README.md                 # intentionally incomplete
│   └── requirements.txt
├── Dockerfile
├── requirements.txt
├── README.md
└── .env.example
```

---

## 4. The Loop (what actually runs)

```
1. INSPECT     → repo tools scan target-project
2. ANALYZE     → Gemini compares actual state vs. readiness checklist
3. PLAN        → Gemini outputs ordered action list
4. EXECUTE     → tool router calls one deterministic tool per step
5. OBSERVE     → raw tool output captured (not summarized by LLM)
6. VERIFY      → verifier independently re-checks the claim
7. FAIL?
     ├─ YES → recovery.py: diagnose → patch source (not tests) → retry (max 3) → back to 4
     └─ NO  → next step
8. ALL STEPS DONE → final full verification pass
9. EVIDENCE REPORT generated FROM verifier output, not from LLM narration
```

Hard limits enforced from day one: `MAX_AGENT_STEPS`, `MAX_REPAIR_ATTEMPTS = 3`, `MAX_DEPLOY_ATTEMPTS = 2`, `MAX_EXECUTION_TIME`.

---

## 5. Build Phases (gated — don't skip ahead)

| Phase | Adds | Cloud Run? | Ship-safe on its own? |
|---|---|---|---|
| **v0.1** | Inspect → gap analysis → doc generation → file-existence verifier → evidence report | Orchestrator only | ✅ yes |
| **v0.2** | pytest execution + diagnosis + patch + retry loop | Orchestrator only | ✅ yes |
| **v0.3** | Target deployment to Cloud Run + HTTP health check | Orchestrator + target both on Cloud Run | ✅ yes — this phase satisfies the Cloud requirement fully |
| Stretch | Approval gating UI, richer docgen, polish | — | optional |

**Freeze point:** once v0.3 works end-to-end and reliably, stop adding scope. Polish the demo instead.

---

## 6. Non-negotiable engineering rules

1. **Gemini never certifies its own success** — the verifier decides.
2. **The agent never touches its own live code** — only the sandboxed target.
3. **No infinite autonomy** — steps, retries, time, and deploy attempts are all capped.
4. **Test files are read-only** — prevents fake fixes.
5. **Evidence is generated from real tool output**, never from LLM summary text.