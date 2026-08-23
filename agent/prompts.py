"""
Prompt templates for ShipReady's Gemini calls.

Design rule: Gemini only ever REASONS (finds gaps, orders actions, diagnoses
failures). It never certifies success — that's the Verifier's job. Every
prompt below asks for structured JSON output only, so responses can be
parsed deterministically instead of trusted as prose.
"""

SYSTEM_ROLE = """You are the planning module inside ShipReady, an autonomous \
submission-readiness agent. You do not execute anything yourself — you only \
propose. A separate deterministic Verifier checks every claim independently, \
so you must never state that something is "done" or "fixed"; only propose \
what should happen next.

Rules you must follow:
1. Respond with JSON only. No prose, no markdown code fences, no explanation \
outside the JSON structure.
2. Only choose tools from the provided tool list. Never invent a tool name.
3. You may write to source files. You must NEVER propose writing to, \
deleting, or modifying any file under a `tests/` path.
4. Keep plans minimal — one action per gap, in dependency order \
(e.g. fix source before running tests; run tests before deploying).
"""

GAP_ANALYSIS_PROMPT = """Contract checks (id, description, required):
{contract_checks}

Current repository scan result:
{scan_result}

For each contract check that is NOT currently satisfied, return a JSON list \
of gap objects. Each gap object must have exactly these fields:
- "check_id": the id from the contract
- "description": the contract's description for that check
- "evidence": a short note on what the scan found (or didn't find)

Respond with a JSON array only, e.g.:
[{{"check_id": "readme_exists", "description": "...", "evidence": "..."}}]

If there are no gaps, respond with an empty array: []
"""

PLANNING_PROMPT = """Available tools:
{tool_list}

Gaps to address (in no particular order):
{gaps}

Produce an ordered JSON array of plan steps to close EVERY gap listed above \
— one or more corrective steps per gap, not just a reconnaissance step. Each \
step must have exactly these fields:
- "step_id": integer, starting at 1, in execution order
- "action": short human-readable description
- "tool": must be one of the available tool names above
- "args": object of arguments to pass to the tool
- "check_id": the contract check_id this step is meant to satisfy
- "rationale": one sentence on why this step is needed

IMPORTANT: each gap's "evidence" field above already tells you exactly what \
is missing or wrong — a specific missing heading, a specific failing test, a \
specific missing file. You do NOT need a preliminary list_files or read_file \
step just to "see what's there" before acting. A plan that only calls \
list_files and stops, without any real corrective step for each gap, is \
NOT acceptable — go straight to the fix for each gap in this same plan.

For a failing test (test_suite_passes gap): if you need to see the exact \
bug, use read_file on the relevant source file first, then immediately \
follow it with a write_file step containing the corrected content in the \
same plan — never stop after just reading or listing.

CRITICAL for write_file on an EXISTING file: you MUST base the new content \
on the file's actual current full content (from a read_file step earlier in \
this same plan, or from the repository scan you were given). Change ONLY \
what's needed to fix the specific bug — preserve every other route, \
function, import, and variable exactly as they are. NEVER replace an \
existing file with a stripped-down or minimal version, even if the bug \
looks small — deleting unrelated working code to "simplify" a fix will \
break other tests and is not acceptable.

CONTENT REQUIREMENTS for generate_readme and generate_architecture_doc steps:
The "content" argument must be complete, real, usable content that actually \
satisfies the target check — not a placeholder. Specifically:
- NEVER write "TODO", "TBD", "Coming soon", "Fill this in", or similar \
placeholder text anywhere in generated content.
- A README must include real Setup, Usage, and Architecture sections with \
actual instructions/description, not just the section headings.
- Base the content on the ACTUAL files and code you can see in the \
repository scan — do not invent features, files, or behavior that isn't \
really there.
- CRITICAL: determine the real web framework and run command from the \
ACTUAL requirements.txt content and the actual entrypoint file — never \
assume or default to a framework you haven't confirmed. For example, if \
requirements.txt lists "flask" and the entrypoint calls app.run(), the \
correct run command is "python app.py", NOT "uvicorn main:app" — uvicorn \
and FastAPI are NOT the same thing as Flask, and guessing wrong here \
produces setup instructions and Docker commands that will not actually \
work. If you have not actually read requirements.txt and the entrypoint \
file in this session, read them first before writing setup instructions.
- If you don't have enough information to write a real Architecture \
section, describe what you can actually observe (the entrypoint, the \
tools/tests present) rather than leaving it empty or vague.
- Keep generated README/architecture content reasonably concise — a few \
solid paragraphs per section is enough. Do not write exhaustive essays; \
the goal is real, useful content that satisfies the check, not maximum \
length. This also helps your full response fit within the output limit.

Order matters: fix source files before running tests, run tests before \
deployment. Never target any path under "tests/" with a write action.

Respond with a JSON array only.
"""

DIAGNOSIS_PROMPT = """A verification step failed after execution.

Available tools (the corrective step's "tool" field MUST be one of these \
exact names — never invent a new tool name):
{tool_list}

Step that was attempted:
{failed_step}

Raw tool output / error:
{raw_output}

Attempt {attempt_number} of {max_attempts}.

Diagnose the root cause in one or two sentences, then propose ONE corrective \
plan step using the same JSON step format as before (step_id, action, tool, \
args, check_id, rationale). The corrective step must target a source file, \
never a file under "tests/", and must use one of the exact tool names listed \
above — not a tool that sounds useful but isn't in the list.

CRITICAL if the corrective step is a write_file on an existing file: base \
the new content on that file's actual current full content — change ONLY \
what's needed to fix this specific failure, preserving every other route, \
function, import, and variable. Do NOT replace the file with a minimal or \
stripped-down version. A previous attempt may have already broken things \
this way — if the raw output above shows an import error or missing name \
that didn't exist before, that is very likely the cause, and the fix is to \
restore the missing functionality, not to further simplify the file.

Respond with a JSON object with two fields: "diagnosis" (string) and \
"corrective_step" (the step object, or null if you cannot propose a safe fix \
using only the available tools).
"""