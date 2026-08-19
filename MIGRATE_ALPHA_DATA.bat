@echo off
setlocal EnableExtensions
cd /d "%~dp0"

echo Migrando dados persistentes da Desktop Alpha...
where powershell.exe >nul 2>nul
if errorlevel 1 (
  echo ERRO: Windows PowerShell nao encontrado.
  pause
  exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0MIGRATE_ALPHA_DATA.ps1"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" echo ERRO: migracao nao concluida. Codigo %RC%.
if "%RC%"=="0" echo MIGRACAO CONCLUIDA.
pause
exit /b %RC%
