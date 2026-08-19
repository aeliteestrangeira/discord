@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

echo Iniciando o mesmo site no aplicativo Electron...

where node >nul 2>nul
if errorlevel 1 (
  echo.
  echo Node.js nao foi encontrado.
  echo Instale Node.js LTS e execute este arquivo novamente.
  pause
  exit /b 1
)

where npm >nul 2>nul
if errorlevel 1 (
  echo.
  echo npm nao foi encontrado no PATH.
  pause
  exit /b 1
)

if not exist "node_modules\electron\dist\electron.exe" (
  echo.
  echo Primeira execucao: instalando Electron 43.2.0...
  call npm install --no-audit --no-fund
  if errorlevel 1 (
    echo.
    echo Falha ao instalar as dependencias desktop.
    pause
    exit /b 1
  )
)

echo.
echo Abrindo aplicativo desktop...
call npm run desktop:start
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo O aplicativo desktop encerrou com codigo %RC%.
  if exist ".runtime\desktop.log" (
    echo.
    echo Ultimas mensagens:
    powershell -NoProfile -Command "Get-Content -LiteralPath '.runtime\desktop.log' -Tail 30"
  )
  pause
)
exit /b %RC%
