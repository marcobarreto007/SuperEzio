@echo off
title SuperEzio Launcher
chcp 65001 > NUL

:: ===========================================================================
:: SuperEzio Launcher — Fallback quando SuperEzio.exe nao funciona
:: ===========================================================================
:: Verifica Python, instala dependencias, inicia servidor e abre browser.
:: ===========================================================================

setlocal enabledelayedexpansion

echo.
echo  ========================================
echo    SuperEzio — Launch Pad
echo  ========================================
echo.

:: ── 1. Check Python ──
where python >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python nao encontrado no PATH.
    echo        Instale Python 3.11+ em https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

python -c "import sys; exit(0 if sys.version_info >= (3,11) else 1)"
if %ERRORLEVEL% NEQ 0 (
    echo [ERRO] Python 3.11+ necessario. Versao atual:
    python --version
    pause
    exit /b 1
)

echo [OK] Python encontrado:
python --version
echo.

:: ── 2. Check / install project ──
python -c "import fastapi" 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [INFO] Dependencias nao encontradas. Instalando...
    echo.
    pip install -e .
    if !ERRORLEVEL! NEQ 0 (
        echo [ERRO] Falha ao instalar dependencias.
        pause
        exit /b 1
    )
    echo [OK] Dependencias instaladas.
) else (
    echo [OK] Dependencias ja instaladas.
)
echo.

:: ── 3. Ensure playwright browsers (se playwright instalado) ──
python -c "import playwright" 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [INFO] Playwright detectado. Verificando browsers...
    python -m playwright install chromium 2>nul
)
echo.

:: ── 4. Start server ──
echo [INFO] Iniciando SuperEzio em http://127.0.0.1:8002 ...
echo [INFO] Pressione CTRL+C para parar o servidor.
echo.

:: Open browser after a short delay
start /B "" cmd /c "timeout /t 5 /nobreak >nul && start http://127.0.0.1:8002"

python -m agent_server.main

echo.
echo [INFO] Servidor encerrado.
pause
