@echo off
echo ========================================
echo   SuperEzio — Startup Completo
echo ========================================
echo.

echo [1/2] Iniciando CEO (Qwen3-Next-80B)...
start "SuperEzio CEO" powershell -ExecutionPolicy Bypass -File scripts\serve_agent_llamacpp.ps1 -Port 8082

echo Aguardando CEO carregar o modelo...
:wait_ceo
timeout /t 5 /nobreak >/dev/null
curl -s http://127.0.0.1:8082/health 2>/dev/null | find "ok" >/dev/null
if errorlevel 1 goto wait_ceo
echo CEO ONLINE!

echo.
echo [2/2] Iniciando API (agent_server)...
start "SuperEzio API" cmd /c "C:\Progra~1\Python312\python -m uvicorn agent_server.main:app --host 127.0.0.1 --port 8002"

echo Aguardando API...
:wait_api
timeout /t 3 /nobreak >/dev/null
curl -s http://127.0.0.1:8002/health 2>/dev/null | find "ok" >/dev/null
if errorlevel 1 goto wait_api
echo API ONLINE!

echo.
echo ========================================
echo   Sistema ONLINE!
echo   Cockpit: http://127.0.0.1:8002
echo ========================================
pause
