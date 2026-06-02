@echo off
setlocal EnableExtensions
mkdir C:\F51_LAB 2>nul
set OUT=C:\F51_LAB\storage_cold_layer.txt

echo === F51 STORAGE / COLD LAYER SCAN ===> "%OUT%"
echo Data: %date% %time%>> "%OUT%"
echo.>> "%OUT%"

echo === PHYSICAL DISKS ===>> "%OUT%"
powershell -NoProfile -Command "Get-PhysicalDisk | Select-Object FriendlyName, MediaType, BusType, @{N='Size_GB';E={[math]::Round($_.Size/1GB,2)}}, HealthStatus | Format-Table -AutoSize" >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === VOLUMES ===>> "%OUT%"
powershell -NoProfile -Command "Get-Volume | Where-Object DriveLetter | Select-Object DriveLetter, FileSystem, @{N='Size_GB';E={[math]::Round($_.Size/1GB,2)}}, @{N='Free_GB';E={[math]::Round($_.SizeRemaining/1GB,2)}} | Format-Table -AutoSize" >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === PAGEFILE (RAM fria no SSD) ===>> "%OUT%"
wmic pagefile get Name,AllocatedBaseSize,CurrentUsage >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === LARGE FILES SuperEzio Financeiro ===>> "%OUT%"
cd /d "%~dp0.."
for %%F in (
  "models\superezio-ceo-intent-merged.Q4_K_M.gguf"
  "models\qwen36-35b-f51.Q4_K_M.gguf"
  "models\Qwen3.6-27B-Q4_K_M.gguf"
) do (
  if exist "%%~F" (
    echo FOUND %%~F>> "%OUT%"
    dir "%%~F" >> "%OUT%"
  ) else (
    echo MISSING %%~F>> "%OUT%"
  )
)

echo.>> "%OUT%"
echo === FOLDER SIZES (GB) ===>> "%OUT%"
powershell -NoProfile -Command ^
  "$root='%~dp0..';" ^
  "@('models','.f51\tmp','data\fraud_datasets','llama.cpp','.venv','runtime\logs','.f51\cache') | ForEach-Object {" ^
  "  $p=Join-Path $root $_; if(Test-Path $p){ $s=(Get-ChildItem $p -Recurse -File -EA SilentlyContinue | Measure-Object Length -Sum).Sum; [PSCustomObject]@{Path=$_; GB=[math]::Round($s/1GB,2)} }" ^
  "} | Format-Table -AutoSize" >> "%OUT%" 2>&1

echo.>> "%OUT%"
echo === LLAMA CACHE FLAGS (referencia) ===>> "%OUT%"
echo prompt cache: serve_ceo usa cache RAM ate 8192 MiB (ver log Teste1)>> "%OUT%"
echo --mlock no CEO: prende pesos na RAM (quente, anti-frio)>> "%OUT%"
echo --cache-ram 0: desliga prompt cache>> "%OUT%"
echo mmap: GGUF lido do SSD sob demanda (padrao)>> "%OUT%"

echo.
echo Gravado: %OUT%
notepad "%OUT%"
