param(
    [Parameter(Mandatory = $true)][string]$DataRoot,
    [Parameter(Mandatory = $true)][string]$CaPath
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = [System.IO.Path]::GetFullPath($DataRoot)
$instance = Join-Path $root "instance"
$config = Join-Path $root "config"
$runtime = Join-Path $root "runtime"
$icacls = Join-Path $env:SystemRoot "System32\icacls.exe"
if (-not (Test-Path -LiteralPath $icacls -PathType Leaf)) { throw "icacls.exe do Windows nao encontrado: $icacls" }
foreach ($dir in @($root, $instance, $config, $runtime)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.User) { throw "SID do usuario atual indisponivel." }
$userSid = $identity.User.Value
$systemSid = "S-1-5-18"

& $icacls $root /grant:r "*${userSid}:(OI)(CI)F" "*${systemSid}:(OI)(CI)F" /inheritance:r /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Falha ao proteger o diretorio persistente do desktop." }
$children = @(Get-ChildItem -LiteralPath $root -Force -ErrorAction Stop)
foreach ($child in $children) {
    & $icacls $child.FullName /reset /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao propagar ACL para $($child.FullName)." }
}

$privateEnv = Join-Path $config "SUPABASE_PRIVILEGED.env"
if (Test-Path -LiteralPath $privateEnv -PathType Leaf) {
    & $icacls $privateEnv /grant:r "*${userSid}:F" "*${systemSid}:F" /inheritance:r /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao proteger o bootstrap privado persistente." }
}

if (-not (Test-Path -LiteralPath $CaPath -PathType Leaf)) { throw "CA local nao encontrada: $CaPath" }
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CaPath)
$thumb = $cert.Thumbprint
$existing = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
if (-not $existing) {
    Import-Certificate -FilePath $CaPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
}
$check = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
if (-not $check) { throw "A CA local nao foi instalada no armazenamento CurrentUser Root." }
Write-Host "Desktop data ACL and local TLS trust ready."
