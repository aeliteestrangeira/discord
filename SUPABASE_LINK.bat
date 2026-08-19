@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
where supabase >nul 2>nul
if %errorlevel%==0 (
  set "SB=supabase"
) else (
  where npx >nul 2>nul || (
    echo Supabase CLI e npx nao foram encontrados.
    echo Instale a CLI e execute novamente.
    exit /b 1
  )
  set "SB=npx supabase"
)
%SB% login || exit /b 1
pushd "priv"
if not exist "supabase\config.toml" %SB% init || (popd & exit /b 1)
%SB% link --project-ref kwekrdluscriubyfolri
set RC=%ERRORLEVEL%
popd
if not "%RC%"=="0" exit /b %RC%
echo Projeto vinculado pela CLI.
endlocal
