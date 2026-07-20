@echo off
title SuperEzio Bootstrap
setlocal enabledelayedexpansion

set ERR_COUNT=0
set STEP=0
set PASS=[OK]
set FAIL=[FAIL]
set SKIP=[SKIP]
set INFO=[INFO]

if /i "%1"=="run" goto :step_run
if /i "%1"=="--help" goto :usage

call :header
call :step_python
if %ERR_COUNT% NEQ 0 goto :summary
call :step_venv
call :step_install_deps
call :step_playwright
call :step_env_file
call :step_jwt_secret
call :step_seed_admin
goto :summary

:header
cls
echo.
echo  === SuperEzio Bootstrap v4.0.0 ===
echo  Windows ONE-CLICK Setup
echo.
goto :eof

:step_num
set /a STEP+=1
echo [%STEP%] %~1
goto :eof

:step_python
call :step_num Verificando Python 3.11+...
python --version >nul 2>&1
if errorlevel 1 (
    echo %FAIL% Python nao encontrado. Instale de https://www.python.org/downloads/
    set /a ERR_COUNT+=1
    goto :eof
)
for /f "tokens=2" %%v in ('python --version 2^^^>^&1') do set PY_VER=%%v
echo %PASS% Python: %PY_VER%
for /f "tokens=1,2 delims=." %%a in ("%PY_VER%") do set PY_MAJOR=%%a^&set PY_MINOR=%%b
if %PY_MAJOR% LSS 3 (
    echo %FAIL% Python 3.11+ necessario
    set /a ERR_COUNT+=1
    goto :eof
)
if %PY_MAJOR% EQU 3 if %PY_MINOR% LSS 11 (
    echo %FAIL% Python 3.11+ necessario
    set /a ERR_COUNT+=1
)
echo %PASS% Requisito atendido.
goto :eof

:step_venv
call :step_num Verificando virtual environment...
if exist ".venv\Scripts\python.exe" (
    echo %PASS% .venv ja existe.
    goto :eof
)
echo %INFO% Criando .venv...
python -m venv .venv
if errorlevel 1 (
    echo %FAIL% Erro ao criar .venv
    set /a ERR_COUNT+=1
    goto :eof
)
echo %PASS% .venv criado.
goto :eof

:activate_venv
if exist ".venv\Scriptsctivate.bat" call ".venv\Scriptsctivate.bat" >nul 2>&1
goto :eof

:step_install_deps
call :step_num Instalando dependencias...
call :activate_venv
python -m pip install -e . 2>&1 | findstr /V "already satisfied" | findstr /V "^$"
if errorlevel 1 (
    echo %FAIL% Erro na instalacao.
    set /a ERR_COUNT+=1
    goto :eof
)
echo %PASS% Dependencias instaladas.
goto :eof

:step_playwright
call :step_num Instalando Playwright Chromium...
python -m playwright install chromium 2>&1
echo %PASS% Playwright Chromium instalado.
goto :eof

:step_env_file
call :step_num Verificando .env.local...
if exist ".env.local" (
    echo %PASS% .env.local ja existe.
    goto :eof
)
if exist ".env.example" (
    echo %INFO% Copiando .env.example para .env.local...
    copy ".env.example" ".env.local" >nul
    echo %PASS% .env.local criado.
) else (
    echo %SKIP% .env.example nao encontrado.
)
goto :eof

:step_jwt_secret
call :step_num Verificando JWT_SECRET...
if exist ".env.local" (
    findstr /B "SUPEREZIO_JWT_SECRET=" ".env.local" >nul 2>&1
    if not errorlevel 1 echo %PASS% JWT_SECRET ja configurado.^&goto :eof
)
echo %INFO% Gerando JWT_SECRET...
cd /d "%~dp0"
for /f "delims=" %%s in ('python -c "import secrets; print(secrets.token_urlsafe(48))"') do set JWT_GEN=%%s
if "%JWT_GEN%"=="" (
    echo %FAIL% Erro ao gerar JWT_SECRET
    set /a ERR_COUNT+=1
    goto :eof
)
echo SUPEREZIO_JWT_SECRET=%JWT_GEN% >> .env.local
echo %PASS% JWT_SECRET gerado.
goto :eof

:step_seed_admin
call :step_num Verificando admin seed...
if not exist "scripts\seed_admin.py" (
    echo %SKIP% seed_admin.py nao encontrado.
    goto :eof
)
call :activate_venv
if not defined SUPEREZIO_ADMIN_PASSWORD set SUPEREZIO_ADMIN_PASSWORD=SuperEzioAdmin2024!
python scripts/seed_admin.py --username admin --email admin@superezio.com --password %SUPEREZIO_ADMIN_PASSWORD% 2>&1
echo %PASS% Admin seed verificado.
goto :eof

:step_run
call :header
call :activate_venv
if %ERR_COUNT% GTR 0 (
    echo %FAIL% Corrija os erros antes de iniciar.
    pause
    exit /b 1
)
echo.
echo Servidor: http://127.0.0.1:8002
echo Ctrl+C para parar.
echo.
start "" /b cmd /c "timeout /t 3 /nobreak ^>nul ^& start http://127.0.0.1:8002"
python -m agent_server.main
pause
goto :eof

:usage
call :header
echo Comandos:
echo   setup_superezio.bat        bootstrap completo
echo   setup_superezio.bat run    inicia servidor
echo   setup_superezio.bat --help esta mensagem
echo.
pause
goto :eof

:summary
echo.
if %ERR_COUNT% EQU 0 (
    echo %PASS% Bootstrap concluido!
    echo Para iniciar: setup_superezio.bat run
    echo Abra: http://127.0.0.1:8002
) else (
    echo %FAIL% %ERR_COUNT% erro(s). Corrija e rode novamente.
)
echo.
pause
