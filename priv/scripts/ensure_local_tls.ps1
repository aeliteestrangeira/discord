$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$python = Join-Path $Root ".venv\Scripts\python.exe"
$generator = Join-Path $PSScriptRoot "generate_local_tls.py"
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) { throw "Python virtual environment not found." }
& $python $generator | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Failed to generate local TLS material." }
$caPath = Join-Path $Root "instance\tls\local-ca.cer"
if (-not (Test-Path -LiteralPath $caPath -PathType Leaf)) { throw "Local CA certificate was not generated." }
$cert = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($caPath)
$thumb = $cert.Thumbprint
$existing = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
if (-not $existing) {
    Import-Certificate -FilePath $caPath -CertStoreLocation "Cert:\CurrentUser\Root" | Out-Null
}
$check = Get-ChildItem Cert:\CurrentUser\Root | Where-Object { $_.Thumbprint -eq $thumb } | Select-Object -First 1
if (-not $check) { throw "Local TLS trust could not be installed for the current Windows user." }
Write-Host "HTTPS local trust ready for the current Windows user."
