@echo off
echo RETIRED: no scheduled task may own the SuperEzio lifecycle.
echo.
echo Lifecycle oficial: start.ps1 / stop.ps1 na raiz do projeto.
echo Watchdog do CEO (:8080): scripts\watchdog_ceo.ps1 (relanca o llama-server
echo se cair; log em runtime\logs\watchdog_ceo.log).
exit /b 2
