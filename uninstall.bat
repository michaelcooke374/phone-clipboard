@echo off
rem ======================================================================
rem  Phone Clipboard: remove it from this computer.
rem  Stops it, and removes its firewall rule, its Start menu entry and its
rem  automatic start. Afterwards you can delete this folder.
rem ======================================================================
setlocal
title Remove Phone Clipboard
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\windows-setup.ps1" -Remove
echo.
pause
