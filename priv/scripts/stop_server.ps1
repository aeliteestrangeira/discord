$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$runtime = Join-Path $Root ".runtime"
$pidFile = Join-Path $runtime "flask.pid"
$markerFile = Join-Path $runtime "flask.marker"
$python = Join-Path $Root ".venv\Scripts\python.exe"
$app = Join-Path $Root "app.py"

if (-not (Test-Path -LiteralPath $pidFile -PathType Leaf)) {
    Write-Host "Nenhum PID registrado."
    exit 0
}
if (-not (Test-Path -LiteralPath $markerFile -PathType Leaf)) {
    throw "PID encontrado sem marcador de propriedade. Nenhum processo foi encerrado."
}

$pidText = (Get-Content -LiteralPath $pidFile -ErrorAction Stop | Select-Object -First 1)
$marker = (Get-Content -LiteralPath $markerFile -ErrorAction Stop | Select-Object -First 1)
$processId = 0
if (-not [int]::TryParse([string]$pidText, [ref]$processId)) {
    throw "PID registrado inválido. Nenhum processo foi encerrado."
}

$proc = Get-CimInstance Win32_Process -Filter "ProcessId = $processId" -ErrorAction SilentlyContinue
if (-not $proc) {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $markerFile -Force -ErrorAction SilentlyContinue
    Write-Host "O processo já estava encerrado; estado de runtime limpo."
    exit 0
}

$exePath = [string]$proc.ExecutablePath
$cmdLine = [string]$proc.CommandLine
if ([string]::IsNullOrWhiteSpace($exePath) -or [string]::IsNullOrWhiteSpace($cmdLine)) {
    throw "Não foi possível validar a propriedade do processo. Nenhum processo foi encerrado."
}

$exeFull = [System.IO.Path]::GetFullPath($exePath)
$pythonFull = [System.IO.Path]::GetFullPath($python)
$samePython = [string]::Equals($exeFull, $pythonFull, [System.StringComparison]::OrdinalIgnoreCase)
$hasApp = $cmdLine.IndexOf($app, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
$hasMarker = $cmdLine.IndexOf([string]$marker, [System.StringComparison]::Ordinal) -ge 0

if (-not ($samePython -and $hasApp -and $hasMarker)) {
    throw "O PID registrado não foi validado como este projeto. Nenhum processo foi encerrado."
}

Stop-Process -Id $processId -Force -ErrorAction Stop
try { Wait-Process -Id $processId -Timeout 5 -ErrorAction SilentlyContinue } catch { }
Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $markerFile -Force -ErrorAction SilentlyContinue
Write-Host "Servidor deste projeto encerrado."
