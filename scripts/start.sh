#!/usr/bin/env bash
# scripts/start.sh
# Usage: ./scripts/start.sh [--reload]
set -euo pipefail

PORT=${TESTFLOW_PORT:-8000}
RELOAD_FLAG=""
[[ "${1:-}" == "--reload" ]] && RELOAD_FLAG="--reload"

echo "TestFlow - Starting tool server..."

# Check if already running
if curl -sf "http://localhost:$PORT/health" | grep -q '"ok"' 2>/dev/null; then
    echo "Tool server already running at http://localhost:$PORT"
    exit 0
fi

# Start in background
poetry run uvicorn tool_server:app --host localhost --port "$PORT" $RELOAD_FLAG &
TOOL_PID=$!
sleep 3

# Health check
if curl -sf "http://localhost:$PORT/health" | grep -q '"ok"'; then
    echo "Tool server healthy at http://localhost:$PORT (PID $TOOL_PID)"
else
    echo "ERROR: Tool server did not start. Check output above."
    exit 1
fi

echo ""
echo "Ready. Open OpenClaw in this directory and start writing articles."
echo "Tip: 'poetry run task test' to run tests, 'poetry run task lint' to lint."
