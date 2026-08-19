Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Out = Join-Path $Root "build\backend"
$Work = Join-Path $Root "build\pyinstaller-work"
$Spec = Join-Path $Root "build\pyinstaller-spec"
Remove-Item -LiteralPath $Out -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $Spec -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $Out, $Work, $Spec | Out-Null

Push-Location $Root
try {
    $common = @(
        "--noconfirm", "--clean", "--onefile",
        "--distpath", $Out,
        "--workpath", $Work,
        "--specpath", $Spec
    )
    $dataArgs = @(
        "--add-data", "assets;assets",
        "--add-data", "priv\static;priv\static",
        "--add-data", "priv\supabase;priv\supabase",
        "--add-data", "lib\discord_app_web\templates;lib\discord_app_web\templates",
        "--add-data", "config\.env.example;config"
    )
    & python -m PyInstaller @common @dataArgs --name discord-backend app.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou para discord-backend." }

    & python -m PyInstaller @common --name discord-tls priv\scripts\generate_local_tls.py
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou para discord-tls." }

    foreach ($name in @("discord-backend.exe", "discord-tls.exe")) {
        $path = Join-Path $Out $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Artefato ausente: $path" }
    }
    Write-Host "Backend executables ready in $Out"
} finally {
    Pop-Location
}
