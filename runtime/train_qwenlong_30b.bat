@echo off
set HF_HUB_ENABLE_HF_TRANSFER=1
cd /d "C:\Users\marco\Desktop\SuperEzio Financeiro"

REM Extract HF token from .env
for /f "tokens=2 delims==" %%a in ('findstr "HUGGINGFACE_API_KEY" "C:\Users\marco\Desktop\SuperEzio Financeiro\.env"') do set HF_TOKEN=%%a

echo === F51 Nitro LoRA Training - Bob Core local ===
echo Started: %date% %time%
echo Log: runtime\logs\train_bob_core.log

"C:\Users\marco\Desktop\SuperEzio Financeiro\.venv\Scripts\python.exe" "C:\Users\marco\Desktop\SuperEzio Financeiro\scripts\train_bob_core_f51.py" > "C:\Users\marco\Desktop\SuperEzio Financeiro\runtime\logs\train_bob_core.log" 2>&1

echo === DONE ===
echo Finished: %date% %time%
