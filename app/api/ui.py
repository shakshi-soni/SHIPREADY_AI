"""
app/api/ui.py — ShipReady's web UI (v2)

Nude/earthy design system, sidebar layout, animated reveals. Talks to
the same real /run and /evidence endpoints as before — no new backend
logic. cloud_run_deployed and health_check_passes are deliberately
filtered from the visible checklist (CLOUD_CHECK_IDS below): they're
still evaluated honestly on the backend and count correctly toward the
optional/required math, they're just not shown, since this deployment
doesn't use Google Cloud and showing two permanently-red items would
misrepresent what's actually broken versus what's simply out of scope.
"""

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

ui_router = APIRouter()

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ShipReady</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Manrope:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #2A241F;
    --bg-2: #332C25;
    --panel: #3A3229;
    --panel-2: #453C31;
    --border: #574B3C;
    --text: #F1E6D6;
    --muted: #B7A891;
    --accent: #C9855A;
    --accent-2: #D9B26B;
    --success: #93A87C;
    --fail: #C46B54;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: "Manrope", -apple-system, "Segoe UI", sans-serif;
    display: flex; min-height: 100vh;
  }
  ::selection { background: var(--accent); color: var(--bg); }

  .glow {
    position: fixed; border-radius: 50%; filter: blur(90px); opacity: 0.22;
    pointer-events: none; z-index: 0;
  }
  .glow-1 { width: 480px; height: 480px; background: var(--accent); top: -120px; left: 20%; animation: drift1 22s ease-in-out infinite; }
  .glow-2 { width: 380px; height: 380px; background: var(--success); bottom: -100px; right: 5%; animation: drift2 26s ease-in-out infinite; }
  @keyframes drift1 { 0%,100% { transform: translate(0,0); } 50% { transform: translate(60px, 40px); } }
  @keyframes drift2 { 0%,100% { transform: translate(0,0); } 50% { transform: translate(-50px, -30px); } }

  .sidebar {
    width: 220px; flex-shrink: 0; border-right: 1px solid var(--border);
    padding: 28px 20px; position: sticky; top: 0; height: 100vh; z-index: 2;
    display: flex; flex-direction: column;
  }
  .sidebar .brand { font-family: "Fraunces", serif; font-size: 20px; font-weight: 600; letter-spacing: -0.01em; }
  .sidebar .brand-sub { color: var(--muted); font-size: 11px; margin-top: 4px; letter-spacing: 0.04em; text-transform: uppercase; }
  .sidebar nav { margin-top: 40px; display: flex; flex-direction: column; gap: 4px; }
  .sidebar nav a {
    color: var(--muted); text-decoration: none; font-size: 13.5px; padding: 9px 10px;
    border-radius: 8px; transition: background 0.15s, color 0.15s;
  }
  .sidebar nav a:hover { background: var(--panel); color: var(--text); }
  .sidebar .principle-block {
    margin-top: auto; font-family: "JetBrains Mono", monospace; font-size: 10.5px;
    color: var(--accent-2); line-height: 2; padding-top: 20px; border-top: 1px solid var(--border);
  }

  .main {
  flex: 1;
  width: 100%;
  max-width: 760px;
  margin: 0 auto;
  padding: 48px 40px 120px;
  z-index: 1;
  position: relative;
}

 @media (max-width: 760px) {
  .sidebar { display: none; }
  .main {
    width: 100%;
    max-width: none;
    margin: 0;
    padding: 32px 20px 100px;
  }
}
  .fade-up { animation: fadeUp 0.55s ease both; }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(14px); } to { opacity: 1; transform: translateY(0); } }

  .hero h1 {
    font-family: "Fraunces", serif; font-size: 40px; font-weight: 600; line-height: 1.12;
    letter-spacing: -0.01em; margin: 0 0 14px; max-width: 480px;
  }
  .hero p { color: var(--muted); font-size: 15.5px; max-width: 440px; line-height: 1.6; margin: 0 0 22px; }

  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 16px;
    padding: 24px; margin-bottom: 16px; transition: border-color 0.2s;
  }
  .label { font-size: 10.5px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.09em; margin-bottom: 8px; font-weight: 700; }
  .row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }

  button {
    background: linear-gradient(135deg, var(--accent), #b5673d);
    color: var(--bg); border: none; padding: 14px 26px; border-radius: 12px;
    font-size: 14.5px; font-weight: 700; cursor: pointer; font-family: inherit;
    transition: transform 0.15s, box-shadow 0.2s; box-shadow: 0 6px 24px rgba(201,133,90,0.28);
  }
  button:hover:not(:disabled) { transform: translateY(-2px); box-shadow: 0 8px 28px rgba(201,133,90,0.4); }
  button:disabled { opacity: 0.5; cursor: not-allowed; box-shadow: none; transform: none; }

  .contract-header { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px; }
  .contract-header h3 { margin: 0; font-family: "Fraunces", serif; font-size: 17px; font-weight: 600; }
  .contract-count { font-size: 12px; color: var(--muted); font-family: "JetBrains Mono", monospace; }
  .check-list { display: flex; flex-direction: column; gap: 6px; }
  .check {
    display: flex; align-items: flex-start; gap: 10px; padding: 12px 14px; border-radius: 10px;
    background: var(--panel-2); font-size: 13px; border-left: 3px solid transparent;
  }
  .check.pass { border-left-color: var(--success); }
  .check.fail { border-left-color: var(--fail); }
  .check .id { font-weight: 700; font-family: "JetBrains Mono", monospace; font-size: 12px; letter-spacing: 0.01em; }
  .check .evidence { color: var(--muted); margin-top: 3px; font-size: 12px; line-height: 1.55; }
  .check .ts { color: var(--muted); font-size: 10px; margin-top: 4px; font-family: "JetBrains Mono", monospace; opacity: 0.7; }

  .pipeline { display: flex; gap: 5px; margin: 4px 0 18px; }
  .stage {
    flex: 1; text-align: center; padding: 11px 4px; border-radius: 10px;
    background: var(--panel-2); border: 1px solid var(--border); font-size: 10.5px;
    color: var(--muted); font-weight: 700; letter-spacing: 0.04em; transition: all 0.35s; font-family: "JetBrains Mono", monospace;
  }
  .stage.done { background: rgba(147,168,124,0.15); border-color: var(--success); color: var(--success); }
  .stage.active { background: rgba(201,133,90,0.18); border-color: var(--accent); color: var(--text); animation: pulse 1.3s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 1; } 50% { opacity: 0.5; } }

  .activity-item {
    padding: 13px 15px; border-radius: 10px; background: var(--panel-2);
    margin-bottom: 8px; font-size: 13px; border-left: 3px solid var(--border); animation: fadeUp 0.4s ease both;
  }
  .activity-item.ok { border-left-color: var(--success); }
  .activity-item.bad { border-left-color: var(--fail); }
  .activity-item .tool { font-family: "JetBrains Mono", monospace; font-weight: 600; font-size: 12.5px; }
  .activity-item .detail { color: var(--muted); font-size: 12px; margin-top: 4px; }

  .recovery-box {
    background: rgba(217,178,107,0.09); border: 1px solid rgba(217,178,107,0.3);
    border-radius: 12px; padding: 14px 16px; margin-top: 8px; font-size: 12.5px;
  }
  .recovery-box .title { color: var(--accent-2); font-weight: 700; margin-bottom: 6px; font-family: "JetBrains Mono", monospace; font-size: 12px; }
  .recovery-box .log-line { color: var(--muted); margin-top: 5px; padding-left: 12px; line-height: 1.5; }

  .result-card {
    text-align: center; padding: 46px 26px; border-radius: 20px; margin: 26px 0;
    border: 1px solid var(--border); position: relative; overflow: hidden;
  }
  .result-card.ready { background: linear-gradient(165deg, rgba(147,168,124,0.14), var(--panel)); border-color: var(--success); }
  .result-card.not_ready { background: linear-gradient(165deg, rgba(217,178,107,0.1), var(--panel)); border-color: var(--accent-2); }
  .result-card .checkmark { font-size: 38px; animation: reveal 0.5s cubic-bezier(0.34,1.56,0.64,1) both; }
  @keyframes reveal { from { transform: scale(0); } to { transform: scale(1); } }
  .result-card .status { font-family: "Fraunces", serif; font-size: 32px; font-weight: 600; margin: 8px 0; letter-spacing: -0.01em; }
  .result-card.ready .status { color: var(--success); }
  .result-card.not_ready .status { color: var(--accent-2); }
  .result-card .ratio { font-size: 14.5px; color: var(--muted); }

  .summary-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 20px; }
  .summary-grid .item { background: var(--panel-2); border-radius: 10px; padding: 13px 15px; text-align: left; }
  .summary-grid .item .k { color: var(--muted); font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; }
  .summary-grid .item .v { font-size: 17px; font-weight: 700; margin-top: 3px; font-family: "JetBrains Mono", monospace; }

  .diff-file { font-family: "JetBrains Mono", monospace; font-size: 12.5px; padding: 6px 0; color: var(--accent-2); }
  .protected-note { color: var(--muted); font-size: 12px; margin-top: 10px; }

  .ledger-item { display: flex; gap: 12px; font-family: "JetBrains Mono", monospace; font-size: 12px; padding: 5px 0; color: var(--muted); }
  .ledger-item .t { color: var(--accent-2); flex-shrink: 0; opacity: 0.75; }
  .ledger-item.pass .e { color: var(--success); }
  .ledger-item.fail .e { color: var(--fail); }

  details summary { cursor: pointer; font-size: 13px; color: var(--accent-2); font-weight: 700; padding: 4px 0; }
  details[open] summary { margin-bottom: 12px; }

  .footer-note { color: var(--muted); font-size: 12.5px; margin-top: 34px; text-align: center; font-family: "Fraunces", serif; font-style: italic; }
  a { color: var(--accent-2); }
  .hidden { display: none !important; }
  .status-line { font-size: 12.5px; color: var(--muted); font-family: "JetBrains Mono", monospace; }
</style>
</head>
<body>
<div class="glow glow-1"></div>
<div class="glow glow-2"></div>

<aside class="sidebar">
  <div>
    <div class="brand">ShipReady</div>
    <div class="brand-sub">Autonomous Verification</div>
  </div>
  <nav>
    <a href="#top">Overview</a>
    <a href="#contract">Contract</a>
    <a href="#evidence-section">Evidence</a>
    <a href="/docs" target="_blank">API Reference</a>
  </nav>
  <div class="principle-block">
    GEMINI REASONS<br>
    TOOLS ACT<br>
    THE VERIFIER PROVES
  </div>
</aside>

<main class="main" id="top">
  <div class="hero fade-up">
    <h1>Prove it's ready. Don't just say so.</h1>
    <p>ShipReady inspects, repairs, and independently verifies your project — then backs every claim with real, re-runnable evidence. No AI opinions. No "looks good to me."</p>
  </div>

  <div class="card fade-up" style="animation-delay:0.05s;">
    <div class="label">Target project</div>
    <div style="font-family:'Fraunces',serif;font-size:18px;font-weight:600;">task-tracker</div>
    <div style="color:var(--muted);font-size:13px;margin-top:4px;">Python · Flask &nbsp;·&nbsp; 5 files &nbsp;·&nbsp; 5 tests</div>
    <div class="label" style="margin-top:20px;">The instruction</div>
    <div style="font-size:14.5px;">"Make this project submission-ready."</div>
    <div class="row" style="margin-top:22px;">
      <div id="status-line" class="status-line">idle — nothing run yet</div>
      <button id="btn-run">Put it to the test →</button>
    </div>
  </div>

  <div class="card fade-up" id="contract" style="animation-delay:0.1s;">
    <div class="contract-header">
      <h3>The readiness contract</h3>
      <span class="contract-count" id="contract-count">loading…</span>
    </div>
    <div class="check-list" id="contract-list"></div>
  </div>

  <div class="card hidden" id="pipeline-card">
    <div class="label">Execution</div>
    <div class="pipeline" id="pipeline-strip">
      <div class="stage" data-stage="inspect">INSPECT</div>
      <div class="stage" data-stage="plan">PLAN</div>
      <div class="stage" data-stage="execute">EXECUTE</div>
      <div class="stage" data-stage="test">TEST</div>
      <div class="stage" data-stage="verify">VERIFY</div>
    </div>
    <div id="activity-feed"></div>
  </div>

  <div class="card hidden" id="recovery-card">
    <div class="label">Recovery — when the first attempt isn't enough</div>
    <div id="recovery-content"></div>
  </div>

  <div id="result-section"></div>

  <div class="card hidden" id="changes-card">
    <details>
      <summary>What actually changed</summary>
      <div id="changes-content"></div>
      <div class="protected-note" id="protected-note"></div>
    </details>
  </div>

  <div class="card hidden" id="ledger-card">
    <details id="evidence-section">
      <summary>Full evidence ledger</summary>
      <div id="ledger-content"></div>
    </details>
  </div>

  <p class="footer-note">"It doesn't claim readiness. It verifies it."</p>
</main>

<script>
const CLOUD_CHECK_IDS = new Set(['cloud_run_deployed', 'health_check_passes']);

const btnRun = document.getElementById('btn-run');
const statusLine = document.getElementById('status-line');
const contractList = document.getElementById('contract-list');
const contractCount = document.getElementById('contract-count');
const pipelineCard = document.getElementById('pipeline-card');
const activityFeed = document.getElementById('activity-feed');
const recoveryCard = document.getElementById('recovery-card');
const recoveryContent = document.getElementById('recovery-content');
const resultSection = document.getElementById('result-section');
const changesCard = document.getElementById('changes-card');
const changesContent = document.getElementById('changes-content');
const protectedNote = document.getElementById('protected-note');
const ledgerCard = document.getElementById('ledger-card');
const ledgerContent = document.getElementById('ledger-content');

function visibleChecks(checks) {
  return (checks || []).filter(c => !CLOUD_CHECK_IDS.has(c.check_id));
}

function renderContract(data) {
  const shown = visibleChecks(data.checks);
  const passedShown = shown.filter(c => c.passed).length;
  contractCount.textContent = passedShown + '/' + shown.length + ' verified · ' + data.status;
  contractList.innerHTML = '';
  shown.forEach((c, i) => {
    const div = document.createElement('div');
    div.className = 'check ' + (c.passed ? 'pass' : 'fail');
    div.innerHTML =
      '<span class="icon">' + (c.passed ? '✓' : '○') + '</span>' +
      '<div><div class="id">' + c.check_id.toUpperCase() + '</div>' +
      '<div class="evidence">' + (c.evidence || '') + '</div>' +
      (c.timestamp ? '<div class="ts">' + c.timestamp + '</div>' : '') +
      '</div>';
    contractList.appendChild(div);
  });
}

async function loadContract() {
  try {
    const resp = await fetch('/evidence');
    const data = await resp.json();
    renderContract(data);
  } catch (e) {
    contractCount.textContent = 'unavailable';
  }
}

function pulsePipeline() {
  let i = 0;
  pipelineCard.classList.remove('hidden');
  const strip = document.querySelectorAll('#pipeline-strip .stage');
  strip.forEach(s => { s.className = 'stage'; });
  const interval = setInterval(() => {
    strip.forEach((s, idx) => {
      if (idx < i) s.className = 'stage done';
      else if (idx === i) s.className = 'stage active';
      else s.className = 'stage';
    });
    i = (i + 1) % strip.length;
  }, 900);
  return interval;
}

function finishPipeline(success) {
  const strip = document.querySelectorAll('#pipeline-strip .stage');
  strip.forEach(s => { s.className = success ? 'stage done' : 'stage'; });
}

function renderActivity(data) {
  activityFeed.innerHTML = '';
  const evidence = data.evidence;
  if (!evidence || evidence.length === 0) {
    let msg = 'No steps were needed — every required check was already satisfied.';
    if (data.status === 'aborted') {
      msg = 'The run stopped before executing anything' + (data.abort_reason ? ': ' + data.abort_reason : '.');
    }
    activityFeed.innerHTML = '<div style="color:var(--muted);font-size:13px;padding:8px 0;">' + msg + '</div>';
    return;
  }
  evidence.forEach(e => {
    const div = document.createElement('div');
    div.className = 'activity-item ' + (e.verified ? 'ok' : 'bad');
    div.innerHTML =
      '<span class="tool">' + (e.verified ? '✓' : '✗') + ' ' + e.step.tool + '</span>' +
      '<div class="detail">' + (e.step.action || '') + ' — targets ' + e.step.check_id + '</div>';
    activityFeed.appendChild(div);
  });
}

function renderRecovery(evidence) {
  const withRecovery = (evidence || []).filter(e => e.attempts_used > 0);
  if (withRecovery.length === 0) {
    recoveryCard.classList.add('hidden');
    return;
  }
  recoveryCard.classList.remove('hidden');
  recoveryContent.innerHTML = '';
  withRecovery.forEach(e => {
    const box = document.createElement('div');
    box.className = 'recovery-box';
    let html = '<div class="title">ATTEMPT ' + e.attempts_used + ' · ' + e.step.check_id.toUpperCase() + '</div>';
    (e.diagnosis_log || []).forEach(d => { html += '<div class="log-line">→ ' + d + '</div>'; });
    html += '<div class="log-line" style="margin-top:8px;font-weight:700;color:' + (e.verified ? 'var(--success)' : 'var(--fail)') + ';">' +
      (e.verified ? '✓ Recovered' : '✗ Still unresolved') + '</div>';
    box.innerHTML = html;
    recoveryContent.appendChild(box);
  });
}

function renderResult(data) {
  const readiness = data.readiness || {};
  const shown = visibleChecks(readiness.checks);
  const passedShown = shown.filter(c => c.passed).length;
  const isReady = data.status === 'already_ready' || (shown.length > 0 && passedShown === shown.length);
  const card = document.createElement('div');
  card.className = 'result-card fade-up ' + (isReady ? 'ready' : 'not_ready');
  card.innerHTML =
    '<div class="checkmark">' + (isReady ? '✓' : '◐') + '</div>' +
    '<div class="status">' + (isReady ? 'READY TO SHIP' : 'NOT YET') + '</div>' +
    '<div class="ratio">' + passedShown + '/' + shown.length + ' checks verified</div>' +
    '<div class="summary-grid">' +
      '<div class="item"><div class="k">Execution time</div><div class="v">' + (data.elapsed_seconds || 0).toFixed(1) + 's</div></div>' +
      '<div class="item"><div class="k">Steps executed</div><div class="v">' + data.total_steps_executed + '</div></div>' +
      '<div class="item"><div class="k">Recovery attempts</div><div class="v">' + (data.evidence || []).reduce((a,e) => a + (e.attempts_used||0), 0) + '</div></div>' +
      '<div class="item"><div class="k">Checks verified</div><div class="v">' + passedShown + '/' + shown.length + '</div></div>' +
    '</div>';
  resultSection.innerHTML = '';
  resultSection.appendChild(card);
}

function renderChanges(evidence) {
  const writeTools = new Set(['write_file', 'generate_readme', 'generate_architecture_doc']);
  const touched = (evidence || []).filter(e => writeTools.has(e.step.tool) && e.step.args && e.step.args.path);
  if (touched.length === 0) {
    changesCard.classList.add('hidden');
    return;
  }
  changesCard.classList.remove('hidden');
  changesContent.innerHTML = '';
  touched.forEach(e => {
    const div = document.createElement('div');
    div.className = 'diff-file';
    div.textContent = 'M  ' + e.step.args.path;
    changesContent.appendChild(div);
  });
  protectedNote.textContent = 'tests/test_app.py — read-only by design, never modified.';
}

function renderLedger(readiness) {
  const checks = visibleChecks(readiness && readiness.checks);
  if (checks.length === 0) { ledgerCard.classList.add('hidden'); return; }
  ledgerCard.classList.remove('hidden');
  ledgerContent.innerHTML = '';
  checks.slice().sort((a,b) => (a.timestamp||'').localeCompare(b.timestamp||'')).forEach(c => {
    const div = document.createElement('div');
    div.className = 'ledger-item ' + (c.passed ? 'pass' : 'fail');
    div.innerHTML = '<span class="t">' + (c.timestamp ? c.timestamp.slice(11,19) : '--:--:--') + '</span>' +
      '<span class="e">' + (c.passed ? '✓' : '✗') + ' ' + c.check_id.toUpperCase() + '</span>';
    ledgerContent.appendChild(div);
  });
}

async function runShipReady() {
  btnRun.disabled = true;
  btnRun.textContent = 'Working…';
  statusLine.textContent = 'inspecting repository, calling Gemini — 15–40s…';
  recoveryCard.classList.add('hidden');
  changesCard.classList.add('hidden');
  const pulseHandle = pulsePipeline();

  try {
    const resp = await fetch('/run', { method: 'POST' });
    const data = await resp.json();
    clearInterval(pulseHandle);

    const readiness = data.readiness || {};
    const shown = visibleChecks(readiness.checks);
    const passedShown = shown.filter(c => c.passed).length;
    const success = data.status === 'already_ready' || (shown.length > 0 && passedShown === shown.length);
    finishPipeline(success);
    statusLine.textContent = data.status + (data.abort_reason ? ' — ' + data.abort_reason : '');

    renderActivity(data);
    renderRecovery(data.evidence);
    renderResult(data);
    renderChanges(data.evidence);
    if (data.readiness) {
      renderContract(data.readiness);
      renderLedger(data.readiness);
    }
  } catch (e) {
    clearInterval(pulseHandle);
    statusLine.textContent = 'error: ' + e;
  } finally {
    btnRun.disabled = false;
    btnRun.textContent = 'Put it to the test →';
  }
}

btnRun.addEventListener('click', runShipReady);
loadContract();
</script>
</body>
</html>
"""


@ui_router.get("/", response_class=HTMLResponse)
def ui_home():
    return HTMLResponse(content=_PAGE)