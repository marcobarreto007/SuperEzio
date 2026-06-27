@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File ".\profiles\Start-F51-20GB.ps1" -Profile aggressive6
pause
