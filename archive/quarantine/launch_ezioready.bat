@echo off
setlocal
cd /d "%~dp0"

if exist "%~dp0desktop\SuperEzio.bat" (
	call "%~dp0desktop\SuperEzio.bat"
	exit /b %errorlevel%
)

echo [ERRO] Launcher principal nao encontrado: %~dp0desktop\SuperEzio.bat
pause
exit /b 1
