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
    $backendCommon = @(
        "--noconfirm", "--clean", "--onedir",
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
    & python -m PyInstaller @backendCommon @dataArgs --name discord-backend $AppEntry
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou para discord-backend." }

    # The long-running backend is intentionally onedir. PyInstaller onefile uses
    # a parent bootloader plus an application child; terminating only the parent
    # can leave the actual server alive on Windows. The short-lived TLS helper
    # remains onefile because it exits before Electron proceeds.
    $tlsCommon = @(
        "--noconfirm", "--clean", "--onefile",
        "--distpath", $Out,
        "--workpath", $Work,
        "--specpath", $Spec
    )
    $TlsEntry = Resolve-Source "priv\scripts\generate_local_tls.py"
    & python -m PyInstaller @tlsCommon --name discord-tls $TlsEntry
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou para discord-tls." }

    $BackendExe = Join-Path $Out "discord-backend\discord-backend.exe"
    $TlsExe = Join-Path $Out "discord-tls.exe"
    if (-not (Test-Path -LiteralPath $BackendExe -PathType Leaf)) { throw "Artefato ausente: $BackendExe" }
    if (-not (Test-Path -LiteralPath $TlsExe -PathType Leaf)) { throw "Artefato ausente: $TlsExe" }
    Write-Host "Backend onedir and TLS helper ready in $Out"
} finally {
    Pop-Location
}
