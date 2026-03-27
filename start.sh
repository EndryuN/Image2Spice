#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting image2asc..."
echo

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[!] Ollama is not running. Please start Ollama first."
    exit 1
fi

# Kill any existing processes on ports 8000 and 5173
lsof -ti:8000 2>/dev/null | xargs -r kill -9 2>/dev/null || true
lsof -ti:5173 2>/dev/null | xargs -r kill -9 2>/dev/null || true

cleanup() {
    echo
    echo "Shutting down..."
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start backend
echo "Starting backend on port 8000..."
cd "$SCRIPT_DIR/backend"
python -m uvicorn main:app --port 8000 &
BACKEND_PID=$!

sleep 2

# Start frontend
echo "Starting frontend on port 5173..."
cd "$SCRIPT_DIR/frontend"
npm run dev &
FRONTEND_PID=$!

sleep 2

echo
echo "image2asc is running!"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost:5173"
echo
echo "Press Ctrl+C to stop."

# Open browser
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:5173
elif command -v open &>/dev/null; then
    open http://localhost:5173
fi

wait
