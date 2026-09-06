@echo off
title SuperEzio Bootstrap
setlocal enabledelayedexpansion
cd /d "%~dp0"

set ERR_COUNT=0
set STEP=0

:: === SuperEzio Bootstrap v4.0.0 (Windows) ===
:: Idempotente: pode rodar varias vezes sem quebrar.

if /i "%1"=="run" goto :step_run
if /i "%1"=="--help" goto :usage

call :header
call :step_python
if %ERR_COUNT% NEQ 0 goto :summary
call :step_venv
if %ERR_COUNT% NEQ 0 goto :summary
call :step_install_deps
if %ERR_COUNT% NEQ 0 goto :summary
call :step_playwright
call :step_env_file
call :step_jwt_secret
call :step_seed_admin
goto :summary

:header
cls
echo.
echo  ====== SuperEzio Bootstrap v4.0.0 ======
echo  Windows ONE-CLICK Setup
echo.
goto :eof

:step_num
set /a STEP+=1
echo [!STEP!] %~1
goto :eof

:step_python
call :step_num "Verificando Python 3.11+..."
python --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python nao encontrado.
    echo Instale de https://www.python.org/downloads/
    set /a ERR_COUNT+=1
    goto :eof
)
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PY_VER=%%v
echo [OK] Python: !PY_VER!
for /f "tokens=1,2 delims=." %%a in ("!PY_VER!") do (
    set PY_MAJOR=%%a
    set PY_MINOR=%%b
)
if !PY_MAJOR! LSS 3 (
    echo [FAIL] Python 3.11+ necessario
    set /a ERR_COUNT+=1
    goto :eof
)
if !PY_MAJOR! EQU 3 if !PY_MINOR! LSS 11 (
    echo [FAIL] Python 3.11+ necessario
    set /a ERR_COUNT+=1
    goto :eof
)
echo [OK] Requisito atendido.
goto :eof

:step_venv
call :step_num "Verificando virtual environment..."
if exist ".venv\Scripts\python.exe" (
    echo [OK] .venv ja existe.
    goto :eof
)
echo [INFO] Criando .venv...
python -m venv .venv
if errorlevel 1 (
    echo [FAIL] Erro ao criar .venv
    set /a ERR_COUNT+=1
    goto :eof
)
echo [OK] .venv criado.
goto :eof

:activate_venv
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat" >nul 2>&1
)
goto :eof

:step_install_deps
call :step_num "Instalando dependencias fixadas..."
call :activate_venv
if not exist "requirements-lock.txt" (
    echo [FAIL] requirements-lock.txt nao encontrado.
    set /a ERR_COUNT+=1
    goto :eof
)
".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
if errorlevel 1 (
    echo [FAIL] Erro ao instalar requirements-lock.txt.
    set /a ERR_COUNT+=1
    goto :eof
)
".venv\Scripts\python.exe" -m pip install --no-deps --no-build-isolation -e .
if errorlevel 1 (
    echo [FAIL] Erro ao instalar o pacote SuperEzio.
    set /a ERR_COUNT+=1
    goto :eof
)
echo [OK] Dependencias instaladas.
goto :eof

:step_playwright
call :step_num "Instalando navegador Chromium do Playwright..."
".venv\Scripts\python.exe" -m playwright install chromium
if errorlevel 1 (
    echo [FAIL] Erro ao instalar Chromium para o browser smoke.
    set /a ERR_COUNT+=1
    goto :eof
)
echo [OK] Chromium do Playwright instalado.
goto :eof

:step_env_file
call :step_num "Verificando .env.local..."
if exist ".env.local" (
    echo [OK] .env.local ja existe.
    goto :eof
)
if exist ".env.example" (
    echo [INFO] Copiando .env.example para .env.local...
    copy ".env.example" ".env.local" >nul
    echo [OK] .env.local criado de .env.example.
    echo [INFO] Edite .env.local com suas API keys.
) else (
    echo [SKIP] .env.example nao encontrado - pulando.
)
goto :eof

:step_jwt_secret
call :step_num "Verificando SUPEREZIO_JWT_SECRET..."
if exist ".env.local" (
    findstr /B "SUPEREZIO_JWT_SECRET=" ".env.local" >nul 2>&1
    if not errorlevel 1 goto :jwt_ok
)
echo [INFO] Gerando JWT_SECRET aleatorio...
for /f "delims=" %%s in ('".venv\Scripts\python.exe" -c "import secrets; print(secrets.token_urlsafe(48))"') do set JWT_GEN=%%s
if "!JWT_GEN!"=="" (
    echo [FAIL] Erro ao gerar JWT_SECRET
    set /a ERR_COUNT+=1
    goto :eof
)
echo SUPEREZIO_JWT_SECRET=!JWT_GEN! >> ".env.local"
echo [OK] JWT_SECRET gerado e salvo em .env.local.
goto :eof
:jwt_ok
echo [OK] SUPEREZIO_JWT_SECRET ja configurado.
goto :eof

:step_seed_admin
call :step_num "Verificando admin seed..."
if not exist "scripts\seed_admin.py" (
    echo [SKIP] seed_admin.py nao encontrado.
    goto :eof
)
call :activate_venv
if not defined SUPEREZIO_ADMIN_PASSWORD (
    echo [FAIL] SUPEREZIO_ADMIN_PASSWORD nao definido.
    echo [INFO] Defina uma senha unica nesta sessao antes de rodar o bootstrap:
    echo        set SUPEREZIO_ADMIN_PASSWORD=uma-senha-forte-e-unica
    set /a ERR_COUNT+=1
    goto :eof
)
".venv\Scripts\python.exe" scripts/seed_admin.py --username admin --email admin@superezio.com
if errorlevel 1 (
    echo [FAIL] Falha ao verificar admin.
    set /a ERR_COUNT+=1
) else (
    echo [OK] Admin seed criado: admin.
)
goto :eof

:step_run
call :header
echo.
echo  [INFO] Iniciando API :8002 com modelos externos pelo launcher oficial.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
if errorlevel 1 exit /b %errorlevel%
goto :eof

:usage
call :header
echo.
echo  Comandos:
echo    setup_superezio.bat        bootstrap completo
echo    setup_superezio.bat run    inicia servidor
echo    setup_superezio.bat --help esta mensagem
echo.
pause
goto :eof

:summary
echo.
if !ERR_COUNT! EQU 0 (
    echo [OK] Bootstrap concluido com sucesso!
    echo.
    echo Para iniciar o servidor:
    echo   setup_superezio.bat run
    echo.
    echo Ou manualmente:
    echo   powershell -NoProfile -ExecutionPolicy Bypass -File start.ps1
    echo.
    echo Abra: http://127.0.0.1:8002
) else (
    echo [FAIL] !ERR_COUNT! erro(s) encontrado(s).
    echo Corrija e rode novamente.
)
echo.
pause
exit /b !ERR_COUNT!
