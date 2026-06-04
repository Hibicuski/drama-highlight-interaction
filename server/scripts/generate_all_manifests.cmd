@echo off
setlocal
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0generate_all_manifests.ps1" %*
exit /b %errorlevel%
