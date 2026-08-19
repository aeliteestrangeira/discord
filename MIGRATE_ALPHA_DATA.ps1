Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($env:LOCALAPPDATA)) {
    throw "LOCALAPPDATA nao esta definido."
}

$SourceRoot = [System.IO.Path]::GetFullPath($PSScriptRoot)
$TargetRoot = Join-Path $env:LOCALAPPDATA "AEliteEstrangeira\DiscordDesktop"
$SourceInstance = Join-Path $SourceRoot "instance"
$SourcePrivate = Join-Path $SourceRoot "config\SUPABASE_PRIVILEGED.env"
$TargetInstance = Join-Path $TargetRoot "instance"
$TargetConfig = Join-Path $TargetRoot "config"
$TargetRuntime = Join-Path $TargetRoot "runtime"
$TargetPrivate = Join-Path $TargetConfig "SUPABASE_PRIVILEGED.env"

foreach ($dir in @($TargetRoot, $TargetInstance, $TargetConfig, $TargetRuntime)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

$targetState = @(Get-ChildItem -LiteralPath $TargetInstance -Force -ErrorAction SilentlyContinue)
if ((Test-Path -LiteralPath $SourceInstance -PathType Container) -and $targetState.Count -eq 0) {
    & robocopy.exe $SourceInstance $TargetInstance /E /COPY:DAT /DCOPY:DAT /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "Falha ao copiar instance (robocopy=$LASTEXITCODE)." }
} elseif ($targetState.Count -gt 0) {
    Write-Host "O destino ja contem estado em instance; ele nao foi sobrescrito."
}

if (Test-Path -LiteralPath $SourcePrivate -PathType Leaf) {
    if (-not (Test-Path -LiteralPath $TargetPrivate -PathType Leaf)) {
        Copy-Item -LiteralPath $SourcePrivate -Destination $TargetPrivate -ErrorAction Stop
        Write-Host "Bootstrap privado copiado para o armazenamento persistente."
    } else {
        Write-Host "Bootstrap privado persistente ja existe; ele nao foi sobrescrito."
    }
} else {
    Write-Host "Nenhum config\SUPABASE_PRIVILEGED.env foi encontrado na Alpha atual."
}

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.User) { throw "SID do usuario atual indisponivel." }
$userSid = $identity.User.Value
$systemSid = "S-1-5-18"

& icacls $TargetRoot /grant:r "*${userSid}:(OI)(CI)F" "*${systemSid}:(OI)(CI)F" /inheritance:r /Q | Out-Null
if ($LASTEXITCODE -ne 0) { throw "Falha ao proteger o diretorio persistente." }

$children = @(Get-ChildItem -LiteralPath $TargetRoot -Force -ErrorAction Stop)
foreach ($child in $children) {
    & icacls $child.FullName /reset /T /C /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao propagar ACL para $($child.FullName)." }
}

if (Test-Path -LiteralPath $TargetPrivate -PathType Leaf) {
    & icacls $TargetPrivate /grant:r "*${userSid}:F" "*${systemSid}:F" /inheritance:r /Q | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Falha ao proteger o bootstrap privado persistente." }
}

Write-Host ""
Write-Host "SUCESSO: dados persistentes preparados em:" -ForegroundColor Green
Write-Host $TargetRoot
Write-Host "Nenhum arquivo da Alpha de origem foi removido."
