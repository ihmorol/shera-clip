@echo off
rem Shera Clip one-command installer (double-click or run from a terminal).
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %*
pause
