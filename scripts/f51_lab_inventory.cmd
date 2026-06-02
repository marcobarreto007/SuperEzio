@echo off
setlocal EnableExtensions
mkdir C:\F51_LAB 2>nul

set OUT=C:\F51_LAB\inventory.txt

echo === CPU ===> "%OUT%"
wmic cpu get name,numberofcores,numberoflogicalprocessors >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === RAM (chips) ===>> "%OUT%"
wmic memorychip get capacity,speed,manufacturer >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === OS RAM ===>> "%OUT%"
powershell -NoProfile -Command "$o=Get-CimInstance Win32_OperatingSystem; 'TotalGB=' + [math]::Round($o.TotalVisibleMemorySize/1MB,2); 'FreeGB=' + [math]::Round($o.FreePhysicalMemory/1MB,2)" >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === GPU ===>> "%OUT%"
nvidia-smi >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === PYTHON (PATH) ===>> "%OUT%"
python --version >> "%OUT%" 2>&1
where python >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === PYTHON (SuperEzio venv) ===>> "%OUT%"
set VENV=%~dp0..\.venv\Scripts\python.exe
if exist "%VENV%" (
  "%VENV%" --version >> "%OUT%" 2>&1
  "%VENV%" -c "import torch; print('torch', torch.__version__); print('cuda', torch.cuda.is_available()); print('devices', torch.cuda.device_count()); [print(i, torch.cuda.get_device_name(i), round(torch.cuda.get_device_properties(i).total_memory/1024**3,2), 'GB') for i in range(torch.cuda.device_count())]" >> "%OUT%" 2>&1
) else (
  echo venv not found: %VENV%>> "%OUT%"
)

echo.>> "%OUT%"
echo === CUDA PATH ===>> "%OUT%"
where nvcc >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === llama-server ===>> "%OUT%"
if exist "%~dp0..\llama.cpp\bin\llama-server.exe" (
  echo FOUND: %~dp0..\llama.cpp\bin\llama-server.exe>> "%OUT%"
  "%~dp0..\llama.cpp\bin\llama-server.exe" --version >> "%OUT%" 2>&1
) else (
  echo llama-server.exe NOT FOUND under llama.cpp\bin>> "%OUT%"
)

echo.>> "%OUT%"
echo === CEO GGUF ===>> "%OUT%"
if exist "%~dp0..\models\superezio-ceo-intent-merged.Q4_K_M.gguf" (
  dir "%~dp0..\models\superezio-ceo-intent-merged.Q4_K_M.gguf" >> "%OUT%"
) else (
  echo GGUF not found>> "%OUT%"
)

echo.>> "%OUT%"
echo === DISK C: ===>> "%OUT%"
wmic logicaldisk where "DeviceID='C:'" get Size,FreeSpace >> "%OUT%" 2>&1

echo.
echo Inventory written to %OUT%
notepad "%OUT%"
