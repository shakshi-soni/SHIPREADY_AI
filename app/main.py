"""
app/main.py — ShipReady's Cloud Run entrypoint.

Wires together:
  - a real Gemini-backed generate_fn (via google-genai) for Planner/Recovery
  - Verifier (deterministic — decides ready/not-ready, not Gemini)
  - Orchestrator (runs the full inspect -> plan -> execute -> verify -> recover loop)
  - LocalStore (JSON state, so /status reflects the last run without re-running it)
  - FastAPI app, serving the routes defined in app/api/routes.py

This file intentionally contains almost no logic of its own — it's wiring,
not behavior. All real behavior lives in agent/, tools/, verification/,
which are independently tested.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from google import genai
from google.genai import types

from agent.executor import Executor
from agent.orchestrator import Orchestrator
from agent.planner import Planner
from state.local_store import LocalStore
from verification.evidence import EvidenceLog
from verification.verifier import Verifier

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
TARGET_PROJECT_DIR = os.environ.get("TARGET_PROJECT_DIR", "./target-project")
CONTRACT_PATH = os.environ.get("CONTRACT_PATH", "./contract.yaml")
STATE_DIR = os.environ.get("SHIPREADY_STATE_DIR", "state")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

MAX_AGENT_STEPS = int(os.environ.get("MAX_AGENT_STEPS", "30"))
MAX_REPAIR_ATTEMPTS = int(os.environ.get("MAX_REPAIR_ATTEMPTS", "3"))
MAX_DEPLOY_ATTEMPTS = int(os.environ.get("MAX_DEPLOY_ATTEMPTS", "2"))
MAX_EXECUTION_TIME_SECONDS = int(os.environ.get("MAX_EXECUTION_TIME_SECONDS", "600"))


def make_gemini_generate_fn():
    """Returns a (system_prompt, user_prompt) -> str callable backed by a
    real Gemini API call. Kept as a factory (not called at import time) so
    the app can still start — and /health can still respond — even if
    GEMINI_API_KEY is missing; the failure surfaces per-request instead of
    crashing the whole service on boot."""
    client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None

    def generate_fn(system_prompt: str, user_prompt: str) -> str:
        if client is None:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Configure it in your environment "
                "before triggering a run (see .env.example)."
            )
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=user_prompt,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
                temperature=0.2,
                # A full multi-step plan (README content + architecture doc
                # + a source patch + deploy/health steps) is a genuinely
                # long JSON response. Without an explicit generous limit,
                # the response can get cut off mid-generation, producing
                # truncated JSON that can never parse successfully no
                # matter how the parser is relaxed — this was the actual
                # root cause of repeated "Expecting ',' delimiter" errors
                # right near the end of long responses.
                max_output_tokens=8192,
            ),
        )
        # Detect truncation DEFINITIVELY via the API's own finish_reason,
        # rather than guessing from a JSON parse error after the fact.
        if response.candidates and response.candidates[0].finish_reason == "MAX_TOKENS":
            raise RuntimeError(
                "Gemini's response was cut off because it hit the max_output_tokens "
                "limit before finishing. The plan was too long to complete — this is "
                "not a JSON formatting bug. Consider raising max_output_tokens further "
                "or asking for more concise generated content."
            )
        return response.text

    return generate_fn


# ---------- Module-level singletons, built once at startup ----------

generate_fn = make_gemini_generate_fn()
evidence_log = EvidenceLog(path=f"{STATE_DIR}/evidence.json")
verifier = Verifier(target_dir=TARGET_PROJECT_DIR, evidence_log=evidence_log)
planner = Planner(contract_path=CONTRACT_PATH, generate_fn=generate_fn)
store = LocalStore(path=f"{STATE_DIR}/agent_state.json")

orchestrator = Orchestrator(
    contract_path=CONTRACT_PATH,
    target_dir=TARGET_PROJECT_DIR,
    generate_fn=generate_fn,
    verify_fn=verifier.verify_step,
    max_agent_steps=MAX_AGENT_STEPS,
    max_repair_attempts=MAX_REPAIR_ATTEMPTS,
    max_deploy_attempts=MAX_DEPLOY_ATTEMPTS,
    max_execution_time_seconds=MAX_EXECUTION_TIME_SECONDS,
)

app = FastAPI(title="ShipReady", version="0.1.0")

# Routes are registered in app/api/routes.py, which imports the singletons
# above via app.state so they're constructed exactly once per process,
# not once per request.
app.state.orchestrator = orchestrator
app.state.verifier = verifier
app.state.planner = planner
app.state.store = store
app.state.evidence_log = evidence_log

from app.api.routes import router  # noqa: E402  (import after app.state is populated)
from app.api.ui import ui_router  # noqa: E402

app.include_router(router)
app.include_router(ui_router)