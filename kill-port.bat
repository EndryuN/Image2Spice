@echo off
set PORT=%1
if "%PORT%"=="" set PORT=8000

for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%PORT% " ^| findstr "LISTENING"') do (
    echo Killing PID %%a on port %PORT%
    taskkill /PID %%a /F
)
