@echo off
setlocal
cd /d "%~dp0"

title Mixtral 8x7B Instruct - Local 16GB
echo ============================================
echo   Mixtral 8x7B Instruct Q4_K_M - Local
echo   RTX 5060 Ti 16GB ^| legacy llama.cpp b3989
echo ============================================
echo.

set "ROOT=%~dp0F51_Nitro_20GB_DualGPU"
set "BIN=%ROOT%\bin_mixtral_legacy\llama-server.exe"
set "MODEL=%ROOT%\models\Mixtral-8x7B-Instruct-v0.1-GGUF\mixtral-8x7b-instruct-v0.1.Q4_K_M.gguf"

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

set "PATH=%ROOT%\bin_mixtral_legacy;%PATH%"

rem The current F51 runtime cannot load this older GGUF because it expects *_exps tensors.
rem The legacy b3989 runtime is used only for Mixtral compatibility.
set F51_MOE_CACHE=0
set F51_MOE_CACHE_ENABLED=0
set F51_MOE_SCHED_SKIP=0

echo Starting server on http://127.0.0.1:8080 ...
echo Model: %MODEL%
echo Runtime: %BIN%
echo.

"%BIN%" ^
  -m "%MODEL%" ^
  -ngl 18 ^
  -c 2048 -b 512 -ub 512 -t 8 ^
  --host 127.0.0.1 --port 8080

pause
