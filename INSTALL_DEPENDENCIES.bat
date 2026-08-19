@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
  set "PY=py -3"
) else (
  set "PY=python"
)
if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  %PY% -m venv .venv || exit /b 1
)
echo Instalando dependencias...
".venv\Scripts\python.exe" -m pip --disable-pip-version-check install --upgrade pip || exit /b 1
if not exist "instance" mkdir "instance"
if exist "instance\requirements.resolved.txt" (
  echo Aplicando snapshot de dependencias preservado desta instalacao...
  ".venv\Scripts\python.exe" -m pip --disable-pip-version-check install --upgrade-strategy only-if-needed -r requirements.txt -c "instance\requirements.resolved.txt" || exit /b 1
) else (
  echo Primeira resolucao de dependencias desta instalacao...
  ".venv\Scripts\python.exe" -m pip --disable-pip-version-check install --upgrade-strategy only-if-needed -r requirements.txt || exit /b 1
)
".venv\Scripts\python.exe" -m pip check || exit /b 1
".venv\Scripts\python.exe" -m pip freeze --all > "instance\requirements.resolved.txt.tmp" || exit /b 1
move /Y "instance\requirements.resolved.txt.tmp" "instance\requirements.resolved.txt" >nul || exit /b 1
echo Dependencias instaladas e verificadas. Snapshot exato preservado em instance\requirements.resolved.txt.
endlocal
