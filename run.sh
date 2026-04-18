#!/usr/bin/env bash
set -e

VENV=".venv"
PYTHON="$VENV/bin/python"
PIP="$VENV/bin/pip"
STREAMLIT="$VENV/bin/streamlit"

echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Spec Sandbox — Setup & Launch"
echo "══════════════════════════════════════════════════════════"
echo ""

# ── 1. Create venv if needed ──────────────────────────────────
if [ ! -f "$PYTHON" ]; then
  echo "→ Creating virtual environment..."
  python3 -m venv "$VENV"
fi

# ── 2. Install dependencies ───────────────────────────────────
echo "→ Installing dependencies..."
"$PIP" install -e ".[dev]" -q
"$PIP" install streamlit pandas -q

# ── 3. Run demo pipeline to populate DB ───────────────────────
if [ ! -f "spec_sandbox.db" ]; then
  echo ""
  echo "→ No database found. Running demo pipeline (mock LLM, ~5s)..."
  echo ""
  "$PYTHON" demo.py
else
  echo "→ Database already exists (spec_sandbox.db). Skipping demo run."
  echo "  Delete spec_sandbox.db and re-run to start fresh."
fi

# ── 4. Launch Streamlit ───────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════"
echo "  Launching Streamlit at http://localhost:8501"
echo "  Press Ctrl+C to stop."
echo "══════════════════════════════════════════════════════════"
echo ""

"$STREAMLIT" run app.py --server.headless false --browser.gatherUsageStats false
