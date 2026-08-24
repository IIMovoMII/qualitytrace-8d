@echo off
setlocal
set ROOT=%~dp0
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%ROOT%run_project.ps1" %*
exit /b %ERRORLEVEL%
