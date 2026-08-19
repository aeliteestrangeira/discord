@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\stop_server.ps1"
if errorlevel 1 (
  echo.
  echo Falha segura: nenhum processo nao validado foi encerrado.
  pause
  exit /b 1
)
endlocal
