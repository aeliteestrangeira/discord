@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\ensure_local_hostname.ps1"
if errorlevel 1 (
  echo.
  echo Falha ao instalar o hostname local para hCaptcha.
  if exist ".runtime\hostname-setup.log" (
    echo.
    echo Diagnostico:
    powershell -NoProfile -Command "Get-Content -LiteralPath '.runtime\hostname-setup.log' -Tail 20"
  )
  pause
  exit /b 1
)
echo Hostname local pronto: https://discord/
pause
endlocal
