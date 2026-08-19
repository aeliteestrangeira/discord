@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\remove_local_tls_trust.ps1"
if errorlevel 1 (
  echo Failed to remove local TLS trust.
  pause
  exit /b 1
)
echo Local TLS trust removed.
pause
endlocal
