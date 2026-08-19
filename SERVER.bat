@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Ambiente Python ainda nao instalado.
  call INSTALL_DEPENDENCIES.bat || exit /b 1
)
".venv\Scripts\python.exe" -c "import flask, supabase, cryptography, psycopg" >nul 2>nul || call INSTALL_DEPENDENCIES.bat || exit /b 1

rem hCaptcha nao funciona em localhost/127.0.0.1. Garante um alias loopback
rem estavel antes de iniciar; a primeira execucao pode solicitar UAC.
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\ensure_local_hostname.ps1"
if errorlevel 1 (
  echo.
  echo Falha ao preparar o hostname local exigido pelo hCaptcha.
  if exist ".runtime\hostname-setup.log" powershell -NoProfile -Command "Get-Content -LiteralPath '.runtime\hostname-setup.log' -Tail 20"
  pause
  exit /b 1
)

rem Default deny: nao inicia o plano de controle se o armazenamento local
rem sensivel nao puder ser restringido ao usuario atual e LocalSystem.
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\harden_instance.ps1"
if errorlevel 1 (
  echo.
  echo Falha no hardening de instance. O servidor NAO foi iniciado.
  pause
  exit /b 1
)

rem WebAuthn/passkeys exigem contexto seguro. Prepara um certificado TLS local
rem e confia apenas na CA publica de desenvolvimento para o usuario Windows atual.
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\ensure_local_tls.ps1"
if errorlevel 1 (
  echo.
  echo Falha ao preparar HTTPS local exigido pelas chaves de acesso.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\restart_server.ps1" -Port 8000
if errorlevel 1 (
  echo.
  echo Falha ao iniciar/reiniciar. Consulte .runtime\server.err.log
  pause
  exit /b 1
)
endlocal
