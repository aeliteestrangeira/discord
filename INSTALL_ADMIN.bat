@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  call INSTALL_DEPENDENCIES.bat || exit /b 1
)
".venv\Scripts\python.exe" -c "import flask, supabase, cryptography, psycopg" >nul 2>nul || call INSTALL_DEPENDENCIES.bat || exit /b 1
".venv\Scripts\python.exe" "priv\scripts\install_admin.py" || exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "priv\scripts\harden_instance.ps1"
if errorlevel 1 (
  echo.
  echo Administrador criado, mas houve falha ao executar o hardening do diretorio instance.
  pause
  exit /b 1
)
echo.
echo Administrador pronto. Use SERVER.bat para iniciar/reiniciar o servidor.
pause
endlocal
