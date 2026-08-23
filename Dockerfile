# ============================================
# ShipReady — Orchestrator Dockerfile
# Runs the FastAPI + ADK agent as a Cloud Run service
# ============================================

FROM python:3.12-slim

# Prevents .pyc files and forces stdout/stderr to be unbuffered
# (unbuffered output matters here so live agent logs stream to
# Cloud Run logs / your terminal in real time, not on exit)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps needed by GitPython (git binary) and cryptography/cffi builds
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first (separate layer = faster rebuilds when only code changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
# (.dockerignore already excludes .env, target-project state, docs, etc.)
COPY . .

# Cloud Run injects $PORT at runtime — default to 8080 for local testing
ENV PORT=8080
EXPOSE 8080

# Run as non-root for security
RUN useradd --create-home --uid 1000 shipready \
    && chown -R shipready:shipready /app
USER shipready

# Cloud Run sends SIGTERM on shutdown; uvicorn handles this gracefully by default.
# Using exec form (no shell) so uvicorn is PID 1 and receives signals directly.
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}