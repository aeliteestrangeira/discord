$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$caPath = Join-Path $Root "instance\tls\local-ca.cer"
if (-not (Test-Path -LiteralPath $caPath -PathType Leaf)) {
    Write-Host "No local CA certificate file found; nothing to remove."
    exit 0
}
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($caPath)
$thumb = $cert.Thumbprint
$target = "Cert:\CurrentUser\Root\$thumb"
if (Test-Path $target) { Remove-Item -LiteralPath $target -Force }
Write-Host "Local HTTPS trust removed for the current Windows user."
