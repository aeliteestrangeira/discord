@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call INSTALL_DEPENDENCIES.bat || exit /b 1
)
".venv\Scripts\python.exe" -c "import psycopg, supabase, cryptography, dotenv" >nul 2>nul || call INSTALL_DEPENDENCIES.bat || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\harden_instance.ps1"
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" "priv\scripts\initialize_database.py"
set RC=%ERRORLEVEL%
if not "%RC%"=="0" (
  echo.
  echo Falha ao inicializar/verificar o banco. Nenhum segredo foi exibido.
  pause
  exit /b %RC%
)
echo.
echo Banco inicializado/verificado.
pause
endlocal
