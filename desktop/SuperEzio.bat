@echo off
chcp 65001 >nul 2>nul
setlocal EnableDelayedExpansion

set "ROOT=C:\Users\marco\Desktop\SuperEzio"
if not exist "%ROOT%" goto root_error
cd /d "%ROOT%"
if errorlevel 1 goto root_error

REM Carrega variaveis do .env (dotenv)
if exist "%ROOT%\.env" (
    for /f "usebackq tokens=1* delims==" %%a in ("%ROOT%\.env") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            if not "%%b"=="" set "%%a=%%b"
        )
    )
)

set "PYTHON_EXE=%ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

set "PYTHONPATH=%ROOT%\src;%PYTHONPATH%"
set "SUPEREZIO_EDGE_AUTH=false"

REM Garante que o Coletor Profissional esta ativo
if not defined SUPEREZIO_PROFESSIONAL_COLLECTOR set "SUPEREZIO_PROFESSIONAL_COLLECTOR=true"

"%PYTHON_EXE%" --version >nul 2>nul
if errorlevel 1 goto python_error

curl --version >nul 2>nul
if errorlevel 1 goto curl_error

if not exist "%ROOT%\scripts\serve_ceo_llamacpp.ps1" goto ceo_script_error
if not exist "%ROOT%\src\agent_server\main.py" goto api_script_error

echo.
echo   SuperEzio v3.2.0 - Modo Local
echo   Python: %PYTHON_EXE%
echo   API: http://127.0.0.1:8002
echo   CEO: http://127.0.0.1:8082
echo   Modelo: Nemotron-Nano-12B (Phase 0 + Phase 1 QLoRA merged)
echo.

if /i "%SUPEREZIO_LAUNCHER_CHECK%"=="1" (
    echo   [OK] Launcher checks passed.
    exit /b 0
)

if not exist "%ROOT%\.f51\tmp\superezio-merged\model.safetensors" (
    echo   [AVISO] Modelo merged nao encontrado em .f51\tmp\superezio-merged\
    echo   [AVISO] Rode: python .f51\tmp\merge_adapters.py --adapter1 C:\Users\marco\Desktop\nemotron-adapter --adapter2 .f51\tmp\phase1-adapter --output .f51\tmp\superezio-merged
    echo   [AVISO] A API pode abrir, mas o CEO local nao vai carregar.
    echo.
)

curl -fsS http://127.0.0.1:8082/health >nul 2>nul
if errorlevel 1 (
    echo   [1/2] Iniciando CEO na porta 8082...
    start "SuperEzio CEO" /D "%ROOT%" cmd /k "powershell -ExecutionPolicy Bypass -File scripts\serve_ceo_llamacpp.ps1 -Port 8082"
) else (
    echo   [1/2] CEO ja esta respondendo na porta 8082.
)

echo   Aguardando CEO carregar modelo...
set /a CEO_ATTEMPTS=0

:wait_ceo
curl -fsS http://127.0.0.1:8082/health >nul 2>nul
if not errorlevel 1 goto ceo_ready
set /a CEO_ATTEMPTS+=1
if %CEO_ATTEMPTS% GEQ 50 goto ceo_timeout
ping 127.0.0.1 -n 4 >nul
goto wait_ceo

:ceo_ready
echo   CEO pronto em http://127.0.0.1:8082

curl -fsS http://127.0.0.1:8002/health >nul 2>nul
if errorlevel 1 (
    echo   [2/2] Iniciando API na porta 8002...
    start "SuperEzio API" /D "%ROOT%" cmd /k ""%PYTHON_EXE%" -m agent_server.main"
) else (
    echo   [2/2] API ja esta respondendo na porta 8002.
)

echo.
echo   Aguardando API...
set /a ATTEMPTS=0

:wait_api
curl -fsS http://127.0.0.1:8002/health >nul 2>nul
if not errorlevel 1 goto api_ready
set /a ATTEMPTS+=1
if %ATTEMPTS% GEQ 40 goto api_timeout
ping 127.0.0.1 -n 4 >nul
goto wait_api

:api_ready
echo   API pronta.
if /i "%SUPEREZIO_NO_BROWSER%"=="1" goto skip_browser
if /i "%SUPEREZIO_NO_BROWSER%"=="true" goto skip_browser
echo   Abrindo navegador...
start "" http://127.0.0.1:8002
goto done

:skip_browser
echo   Browser pulado por SUPEREZIO_NO_BROWSER=%SUPEREZIO_NO_BROWSER%.

:done
echo.
echo   SuperEzio rodando em modo local.
echo   API: http://127.0.0.1:8002
echo   CEO: http://127.0.0.1:8082
echo.
echo   Feche as janelas "SuperEzio CEO" e "SuperEzio API" para parar.
echo   Pressione qualquer tecla para fechar este launcher.
pause >nul
exit /b 0

:api_timeout
echo.
echo   [ERRO] A API nao respondeu em http://127.0.0.1:8002/health.
echo   Veja a janela "SuperEzio API" para o erro real.
pause
exit /b 1

:ceo_timeout
echo.
echo   [ERRO] O CEO nao respondeu em http://127.0.0.1:8082/health.
echo   Veja a janela "SuperEzio CEO" para o erro real.
echo   Comando manual: powershell -ExecutionPolicy Bypass -File scripts\serve_ceo_llamacpp.ps1 -Port 8082
pause
exit /b 1

:root_error
echo [ERRO] Nao consegui abrir %ROOT%.
pause
exit /b 1

:python_error
echo [ERRO] Python nao encontrado. Esperado: %PYTHON_EXE%
pause
exit /b 1

:curl_error
echo [ERRO] curl.exe nao encontrado no PATH.
pause
exit /b 1

:ceo_script_error
echo [ERRO] Script do CEO nao encontrado: %ROOT%\scripts\serve_ceo_llamacpp.ps1
pause
exit /b 1

:api_script_error
echo [ERRO] Script da API nao encontrado: %ROOT%\src\agent_server\main.py
pause
exit /b 1
