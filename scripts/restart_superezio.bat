@echo off
setlocal enabledelayedexpansion
title Reiniciar SuperEzio

cd /d "%~dp0.."

echo ========================================================
echo        SUPEREZIO -- REINICIAR SERVIDORES (:8002)
echo ========================================================
echo.

set "HEALTH_URL=http://127.0.0.1:8002/health"
set "UI_URL=http://127.0.0.1:8002"
set "VENV_PY=%~dp0..\.venv\Scripts\python.exe"
set "PYTHON_EXE="

rem 1. Matar servidores anteriores na porta 8002
echo [1/3] Parando servidores existentes do SuperEzio...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$c = Get-NetTCPConnection -LocalPort 8002 -State Listen -ErrorAction SilentlyContinue; if ($c) { Write-Host '  Encerrando processo PID' $c.OwningProcess 'na porta 8002...'; Stop-Process -Id $c.OwningProcess -Force -ErrorAction SilentlyContinue }; try { $procs = Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -match 'agent_server\.main' }; foreach ($p in $procs) { Write-Host '  Encerrando processo residual PID' $p.ProcessId '...'; Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } } catch {}"

rem Aguardar liberacao da porta
ping -n 3 127.0.0.1 >nul

rem 2. Localizar Python
echo.
echo [2/3] Localizando Python e iniciando nova instancia...
if exist "%VENV_PY%" (
    set "PYTHON_EXE=%VENV_PY%"
) else (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        set "PYTHON_EXE=%%i"
        goto :have_py
    )
)

:have_py
if not defined PYTHON_EXE (
    echo [ERRO] Python nao encontrado no sistema!
    pause
    exit /b 1
)

echo   Python: %PYTHON_EXE%

if defined PYTHONPATH (
    set "PYTHONPATH=src;%PYTHONPATH%"
) else (
    set "PYTHONPATH=src"
)

if not exist "runtime\logs" mkdir "runtime\logs"

rem Iniciar processo desanexado com start /min
start "SuperEzio Server (:8002)" /min "%PYTHON_EXE%" -m agent_server.main

rem 3. Aguardar prontidao via /health
echo.
echo [3/3] Aguardando prontidao do servidor (:8002/health)...
set "ONLINE=0"
for /l %%i in (1,1,30) do (
    ping -n 2 127.0.0.1 >nul
    curl.exe -fsS --max-time 1 %HEALTH_URL% >nul 2>&1
    if !errorlevel! equ 0 (
        set "ONLINE=1"
        goto :server_ready
    )
    echo   Aguardando inicializacao... (%%i/30s)
)

:server_ready
if "%ONLINE%"=="1" (
    echo.
    echo ========================================================
    echo   SUPEREZIO REINICIADO COM SUCESSO!
    echo   URL: %UI_URL%
    echo ========================================================
    echo.
    start "" "%UI_URL%"
    echo Navegador aberto. Esta janela sera fechada em 3 segundos.
    ping -n 4 127.0.0.1 >nul
    exit /b 0
) else (
    echo.
    echo [AVISO] O servidor foi disparado mas nao respondeu no /health em 30s.
    echo Verifique os logs em runtime\logs\
    pause
    exit /b 1
)
