@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  py -3 priv\scripts\preflight.py
) else (
  python priv\scripts\preflight.py
)
if errorlevel 1 pause
endlocal
