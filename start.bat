@echo off
echo Starting image2asc...
echo.

:: Check if Ollama is running
curl -s http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [!] Ollama is not running. Please start Ollama first.
    pause
    exit /b 1
)

:: Kill any existing processes on ports 8000 and 5173
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    echo Killing existing process on port 8000 (PID %%a)
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo Killing existing process on port 5173 (PID %%a)
    taskkill /PID %%a /F >nul 2>&1
)

:: Start backend
echo Starting backend on port 8000...
start "image2asc-backend" cmd /c "cd /d %~dp0backend && python -m uvicorn main:app --port 8000"

:: Wait for backend to be ready
timeout /t 3 /nobreak >nul

:: Start frontend
echo Starting frontend on port 5173...
start "image2asc-frontend" cmd /c "cd /d %~dp0frontend && npm run dev"

:: Wait and open browser
timeout /t 3 /nobreak >nul
echo.
echo image2asc is running!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo.
echo Opening browser...
start http://localhost:5173
echo.
echo Close this window to keep servers running, or press any key to stop them.
pause >nul

:: Cleanup
taskkill /FI "WINDOWTITLE eq image2asc-backend" /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq image2asc-frontend" /F >nul 2>&1
