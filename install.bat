@echo off
rem Shera Clip one-command installer (double-click or run from a terminal).
set "EXTRA="
if /i "%~1"=="--add-path" set "EXTRA=-AddPath"
if /i "%~1"=="-AddPath" set "EXTRA=-AddPath"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1" %EXTRA%
pause
