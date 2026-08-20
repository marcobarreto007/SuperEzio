@echo off
setlocal
rem Legacy compatibility shim. setup_superezio.bat is the only bootstrap authority.
call "%~dp0setup_superezio.bat" run %*
exit /b %errorlevel%
