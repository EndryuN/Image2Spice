@echo off
setlocal
echo Starting image2spice...
echo.

:: Check if Ollama is running (optional — OpenRouter/OpenAI/Claude can be used instead)
curl.exe -s --max-time 3 http://localhost:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo [*] Ollama is not running. You can use OpenRouter / OpenAI / Claude instead.
    echo     To use local models, start Ollama first: ollama serve
    echo.
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

:: Start backend in background (same console — logs interleave)
echo Starting backend on port 8000...
pushd "%~dp0backend"
start /b "" cmd /c "python -m uvicorn main:app --port 8000"
popd

:: Wait for backend to come up
timeout /t 3 /nobreak >nul

:: Start frontend in background (same console — logs interleave)
echo Starting frontend on port 5173...
pushd "%~dp0frontend"
start /b "" cmd /c "npm run dev"
popd

:: Wait for frontend
timeout /t 3 /nobreak >nul

echo.
echo image2spice is running!
echo   Backend:  http://localhost:8000
echo   Frontend: http://localhost:5173
echo.
echo Click "Exit" in the app or press Ctrl+C here to stop both servers.
echo.

:: Open browser
start "" http://localhost:5173

:: Watcher loop — poll the backend port. When it stops listening,
:: tear down the frontend and exit.
:waitloop
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul
if errorlevel 1 goto cleanup
timeout /t 2 /nobreak >nul
goto waitloop

:cleanup
echo.
echo Backend stopped — shutting down frontend...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
:: Defense: also kill anything still on 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    taskkill /PID %%a /F >nul 2>&1
)
echo Stopped.
endlocal
exit /b 0
