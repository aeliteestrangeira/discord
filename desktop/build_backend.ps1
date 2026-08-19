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

function Resolve-Source([string]$RelativePath) {
    $Resolved = [System.IO.Path]::GetFullPath((Join-Path $Root $RelativePath))
    if (-not (Test-Path -LiteralPath $Resolved)) {
        throw "Fonte de empacotamento ausente: $Resolved"
    }
    return $Resolved
}

function Data-Argument([string]$RelativePath, [string]$Destination) {
    $Source = Resolve-Source $RelativePath
    return ($Source + ";" + $Destination)
}

Push-Location $Root
try {
    $common = @(
        "--noconfirm", "--clean", "--onefile",
        "--distpath", $Out,
        "--workpath", $Work,
        "--specpath", $Spec
    )
    # PyInstaller resolves relative --add-data sources against --specpath.
    # Always pass absolute sources so moving the .spec file cannot rebase them.
    $dataArgs = @(
        "--add-data", (Data-Argument "assets" "assets"),
        "--add-data", (Data-Argument "priv\static" "priv\static"),
        "--add-data", (Data-Argument "priv\supabase" "priv\supabase"),
        "--add-data", (Data-Argument "lib\discord_app_web\templates" "lib\discord_app_web\templates"),
        "--add-data", (Data-Argument "config\.env.example" "config")
    )
    $AppEntry = Resolve-Source "app.py"
    & python -m PyInstaller @common @dataArgs --name discord-backend $AppEntry
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou para discord-backend." }

    $TlsEntry = Resolve-Source "priv\scripts\generate_local_tls.py"
    & python -m PyInstaller @common --name discord-tls $TlsEntry
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou para discord-tls." }

    foreach ($name in @("discord-backend.exe", "discord-tls.exe")) {
        $path = Join-Path $Out $name
        if (-not (Test-Path -LiteralPath $path -PathType Leaf)) { throw "Artefato ausente: $path" }
    }
    Write-Host "Backend executables ready in $Out"
} finally {
    Pop-Location
}
