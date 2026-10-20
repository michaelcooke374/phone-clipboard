@echo off
rem ======================================================================
rem  Phone Clipboard: copy and paste between this computer and your iPhone.
rem  Double-click this file. The first time, it sets everything up (a minute
rem  or two; Windows asks for permission once). Then it opens the page with
rem  the code to scan with your iPhone.
rem  After that, Phone Clipboard starts by itself when you sign in to
rem  Windows, and you can open its page from the Start menu.
rem ======================================================================
setlocal
title Phone Clipboard
cd /d "%~dp0"
if /i "%~1"=="setup" goto :setup
if not exist "%~dp0data\setup-done.txt" goto :setup
call :find_python
if not defined PYW goto :setup
goto :run

:setup
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0app\windows-setup.ps1"
if errorlevel 1 goto :stopped
call :find_python
if not defined PYW goto :stopped

:run
rem pythonw runs Phone Clipboard without a window. If it's already running, this just opens its page.
start "" "%PYW%" "%~dp0app\phone_clipboard.py" --open
exit /b 0

:find_python
set "PYW="
for /d %%D in ("%~dp0.python\cpython-3.12*") do if exist "%%~fD\pythonw.exe" set "PYW=%%~fD\pythonw.exe"
exit /b 0

:stopped
echo.
echo   Phone Clipboard isn't ready yet. Fix the problem above, then double-click start.bat again.
echo.
pause
exit /b 1
