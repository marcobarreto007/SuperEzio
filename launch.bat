@echo off
setlocal enabledelayedexpansion
title SuperEzio - Quantitative AI Copilot

cd /d "%~dp0"

echo ========================================================
echo        SUPEREZIO -- QUANTITATIVE AI COPILOT
echo ========================================================
echo.

set "HEALTH_URL=http://127.0.0.1:8002/health"
set "UI_URL=http://127.0.0.1:8002"

rem 1. Check if SuperEzio is already running on port 8002
curl.exe -fsS --max-time 2 %HEALTH_URL% >nul 2>&1
if %errorlevel% equ 0 (
    echo [OK] SuperEzio API server ja esta ativo na porta 8002.
    goto :open_ui
)

echo [1/2] Iniciando servidor SuperEzio (:8002)...

rem 2. Locate Python executable
set "PY_CMD=python"
if exist ".venv\Scripts\python.exe" (
    set "PY_CMD=.venv\Scripts\python.exe"
)

rem Ensure PYTHONPATH includes src
if defined PYTHONPATH (
    set "PYTHONPATH=src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=src"
)

rem Create logs dir if not exists
if not exist "runtime\logs" mkdir "runtime\logs"

rem Start server in minimized window
start "SuperEzio Server" /min %PY_CMD% -m agent_server.main

echo [2/2] Aguardando prontidao do servidor...
for /l %%i in (1,1,30) do (
    ping -n 2 127.0.0.1 >nul
    curl.exe -fsS --max-time 1 %HEALTH_URL% >nul 2>&1
    if !errorlevel! equ 0 (
        echo [OK] Servidor online e saudavel!
        goto :open_ui
    )
    <nul set /p=.
)

echo.
echo [AVISO] O servidor esta demorando para responder.
echo Tentando abrir a interface mesmo assim...

:open_ui
echo.
echo [>>] Abrindo interface no navegador...
start "" "%UI_URL%"

echo.
echo ========================================================
echo   SuperEzio OPERACIONAL
echo   UI: %UI_URL%
echo ========================================================
echo.
ping -n 3 127.0.0.1 >nul
exit /b 0
