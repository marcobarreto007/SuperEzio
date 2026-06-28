@echo off
echo Installing SuperEzio Watchdog Service...
echo.
powershell -ExecutionPolicy Bypass -Command "Start-Process powershell -ArgumentList '-ExecutionPolicy Bypass -File \"%~dp0install_watchdog.ps1\"' -Verb RunAs"
