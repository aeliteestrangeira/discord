@echo off
setlocal
cd /d "%~dp0"

echo Repository: https://github.com/aeliteestrangeira/discord

git --version >nul 2>&1
if errorlevel 1 (
  echo Git nao encontrado. Instale Git for Windows e execute novamente.
  pause
  exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
  git remote add origin https://github.com/aeliteestrangeira/discord.git
) else (
  git remote set-url origin https://github.com/aeliteestrangeira/discord.git
)

git branch -M main

echo.
echo Enviando branch main...
git push -u origin main
if errorlevel 1 (
  echo.
  echo Falha no push. Se solicitado, autentique sua conta GitHub no navegador/Git Credential Manager e tente novamente.
  pause
  exit /b 1
)

echo.
echo Projeto enviado com sucesso.
pause
