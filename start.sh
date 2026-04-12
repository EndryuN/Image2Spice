#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Starting image2spice..."
echo

# ── Dependency checks ─────────────────────────────────────────────────
echo "Checking dependencies..."

# Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[ERROR] Python is not installed."
    echo "        Install it with your package manager:"
    echo "          macOS:        brew install python"
    echo "          Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "          Fedora:       sudo dnf install python3 python3-pip"
    echo "          Arch:         sudo pacman -S python python-pip"
    exit 1
fi
PYTHON_CMD=$(command -v python3 || command -v python)
PYVER=$($PYTHON_CMD --version 2>&1)
echo "  [OK] $PYVER"

# Node.js
if ! command -v node &>/dev/null; then
    echo "[ERROR] Node.js is not installed."
    echo "        Install it with your package manager:"
    echo "          macOS:        brew install node"
    echo "          Ubuntu/Debian: curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash - && sudo apt install -y nodejs"
    echo "          Fedora:       sudo dnf install nodejs"
    echo "          Arch:         sudo pacman -S nodejs npm"
    exit 1
fi
echo "  [OK] Node.js $(node --version)"

# Backend dependencies
if ! $PYTHON_CMD -c "import fastapi, httpx, uvicorn" &>/dev/null; then
    echo "[!] Backend Python packages not installed. Installing now..."
    cd "$SCRIPT_DIR/backend"
    $PYTHON_CMD -m pip install -r requirements.txt
    echo "  [OK] Backend dependencies installed"
else
    echo "  [OK] Backend dependencies"
fi

# Frontend dependencies
if [ ! -d "$SCRIPT_DIR/frontend/node_modules" ]; then
    echo "[!] Frontend packages not installed. Running npm install..."
    cd "$SCRIPT_DIR/frontend"
    npm install
    echo "  [OK] Frontend dependencies installed"
else
    echo "  [OK] Frontend dependencies"
fi

echo

# Check if Ollama is running (optional — OpenRouter can be used instead)
if ! curl -s --max-time 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
    echo "[*] Ollama is not running. You can use OpenRouter / OpenAI / Claude instead."
    echo "    To use local models, start Ollama first: ollama serve"
    echo
fi

# ── Kill any existing processes on ports 8000 and 5173 ────────────────
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
echo "image2spice is running!"
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

# Wait specifically on the backend. If backend dies (Ctrl+C OR /api/shutdown
# triggered SIGTERM from inside the process), tear down the frontend too.
wait $BACKEND_PID 2>/dev/null || true
echo
echo "Backend stopped — shutting down frontend..."
kill $FRONTEND_PID 2>/dev/null || true
wait $FRONTEND_PID 2>/dev/null || true
echo "Stopped."
exit 0
