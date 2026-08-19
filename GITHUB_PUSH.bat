@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo Repository: https://github.com/aeliteestrangeira/discord

where git >nul 2>nul
if errorlevel 1 (
  echo Git nao encontrado. Instale Git for Windows e tente novamente.
  pause
  exit /b 1
)

if not exist ".git\" (
  echo.
  echo Esta pasta nao e um clone Git e nao possui .git.
  echo Para publicar um pacote ZIP, use PUBLISH_TO_GITHUB.bat do pacote Publisher.
  echo Nao execute git push diretamente a partir de um ZIP extraido.
  pause
  exit /b 2
)

git remote set-url origin https://github.com/aeliteestrangeira/discord.git >nul 2>nul
if errorlevel 1 (
  echo Falha ao configurar origin.
  pause
  exit /b 1
)

git branch -M main

echo.
echo Sincronizando referencia remota...
git fetch origin main
if errorlevel 1 goto :fail

echo.
echo Enviando branch main...
git push -u origin main
if errorlevel 1 goto :fail

echo.
echo Projeto enviado com sucesso.
pause
exit /b 0

:fail
echo.
echo Falha na operacao Git. Nenhum force push foi executado.
pause
exit /b 1
