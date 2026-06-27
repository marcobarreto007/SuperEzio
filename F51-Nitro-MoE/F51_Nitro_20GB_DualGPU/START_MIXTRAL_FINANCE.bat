@echo off
setlocal
cd /d "%~dp0"

title Mixtral 8x7B Instruct - Local Finance
echo ============================================
echo   Mixtral 8x7B Instruct Q4_K_M
echo   Local runtime: llama.cpp b3989
echo ============================================
echo.

set "BIN=%~dp0bin_mixtral_legacy\llama-server.exe"
set "MODEL=%~dp0models\Mixtral-8x7B-Instruct-v0.1-GGUF\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"

if not exist "%BIN%" (
  echo Missing Mixtral legacy runtime:
  echo   %BIN%
  pause
  exit /b 1
)

if not exist "%MODEL%" (
  echo Missing Mixtral GGUF:
  echo   %MODEL%
  pause
  exit /b 1
)

set "PATH=%~dp0bin_mixtral_legacy;%PATH%"
set F51_MOE_CACHE=0
set F51_MOE_CACHE_ENABLED=0
set F51_MOE_SCHED_SKIP=0

echo Starting server on http://127.0.0.1:8080 ...
echo.

"%BIN%" ^
  -m "%MODEL%" ^
  -ngl 18 ^
  -c 2048 -b 512 -ub 512 -t 8 ^
  --host 127.0.0.1 --port 8080

pause
