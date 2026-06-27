@echo off
setlocal

set "WT=C:\Users\marco\Desktop\F51-Nitro-MoE\build_worktrees\llama_clean_20260531_220628"
set "BUILD=%WT%\build-f51-swa"

if exist "%BUILD%" rmdir /s /q "%BUILD%"

set "PATH=C:\Program Files (x86)\Microsoft Visual Studio\Installer;%PATH%"
call "C:\Program Files\Microsoft Visual Studio\18\Professional\Common7\Tools\VsDevCmd.bat" -arch=x64 -host_arch=x64
if errorlevel 1 exit /b 1

set "CUDA_PATH=C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA\v12.8"
set "PATH=%CUDA_PATH%\bin;%PATH%"

where cl
where nvcc

cmake -S "%WT%" -B "%BUILD%" -G Ninja -DCMAKE_BUILD_TYPE=Release -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=120 -DCMAKE_CUDA_FLAGS=--allow-unsupported-compiler
if errorlevel 1 exit /b 1

cmake --build "%BUILD%" --target llama-server -j 10
exit /b %ERRORLEVEL%
