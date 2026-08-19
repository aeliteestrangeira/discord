param(
    [int]$Port = 8000
)
$ErrorActionPreference = "Stop"

# Resolve the project root from this script's own location. This avoids the
# Windows cmd.exe trailing-backslash/quote ambiguity produced by %~dp0.
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$runtime = Join-Path $Root ".runtime"
$pidFile = Join-Path $runtime "flask.pid"
$markerFile = Join-Path $runtime "flask.marker"
$outLog = Join-Path $runtime "server.out.log"
$errLog = Join-Path $runtime "server.err.log"
$python = Join-Path $Root ".venv\Scripts\python.exe"
$app = Join-Path $Root "app.py"
$tlsCert = Join-Path $Root "instance\tls\server-cert.pem"
$tlsKey = Join-Path $Root "instance\tls\server-key.pem"

New-Item -ItemType Directory -Force -Path $runtime | Out-Null

function Get-ProjectProcess([int]$ProcessId, [string]$ExpectedMarker) {
    if ($ProcessId -le 0 -or [string]::IsNullOrWhiteSpace($ExpectedMarker)) {
        return $null
    }

    $proc = Get-CimInstance Win32_Process -Filter "ProcessId = $ProcessId" -ErrorAction SilentlyContinue
    if (-not $proc) {
        return $null
    }

    $exePath = [string]$proc.ExecutablePath
    $cmdLine = [string]$proc.CommandLine
    if ([string]::IsNullOrWhiteSpace($exePath) -or [string]::IsNullOrWhiteSpace($cmdLine)) {
        return $null
    }

    try {
        $exeFull = [System.IO.Path]::GetFullPath($exePath)
        $pythonFull = [System.IO.Path]::GetFullPath($python)
    } catch {
        return $null
    }

    $samePython = [string]::Equals($exeFull, $pythonFull, [System.StringComparison]::OrdinalIgnoreCase)
    $hasApp = $cmdLine.IndexOf($app, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    $hasMarker = $cmdLine.IndexOf($ExpectedMarker, [System.StringComparison]::Ordinal) -ge 0

    if ($samePython -and $hasApp -and $hasMarker) {
        return $proc
    }
    return $null
}

if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Ambiente virtual ausente. Execute INSTALL_DEPENDENCIES.bat primeiro."
}
if (-not (Test-Path -LiteralPath $app -PathType Leaf)) {
    throw "app.py não foi encontrado no diretório do projeto."
}

# Restart is fail-closed: a PID is terminated only when PID + executable +
# app.py path + per-launch marker all identify this exact project instance.
if ((Test-Path -LiteralPath $pidFile -PathType Leaf) -and (Test-Path -LiteralPath $markerFile -PathType Leaf)) {
    $oldPidText = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $oldMarker = (Get-Content -LiteralPath $markerFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    $oldPid = 0
    if ([int]::TryParse([string]$oldPidText, [ref]$oldPid)) {
        $oldProjectProc = Get-ProjectProcess -ProcessId $oldPid -ExpectedMarker ([string]$oldMarker)
        if ($oldProjectProc) {
            Write-Host "Encerrando servidor anterior deste projeto (PID $oldPid)..."
            Stop-Process -Id $oldPid -Force -ErrorAction Stop
            try { Wait-Process -Id $oldPid -Timeout 5 -ErrorAction SilentlyContinue } catch { }
        } elseif (Get-Process -Id $oldPid -ErrorAction SilentlyContinue) {
            throw "O PID registrado ($oldPid) pertence a um processo que não pôde ser validado como este projeto. Nenhum processo foi encerrado."
        }
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $markerFile -Force -ErrorAction SilentlyContinue
} elseif (Test-Path -LiteralPath $pidFile -PathType Leaf) {
    # Old/incomplete runtime state: do not trust a bare PID.
    $stalePid = (Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($stalePid -and (Get-Process -Id ([int]$stalePid) -ErrorAction SilentlyContinue)) {
        throw "Existe um PID antigo sem marcador de propriedade. Por segurança, ele não será encerrado automaticamente. Use o Gerenciador de Tarefas apenas se confirmar que é o servidor desta pasta, depois remova .runtime\\flask.pid."
    }
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
}

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    throw "A porta $Port já está ocupada pelo PID $($listener.OwningProcess). Por segurança, o script não encerra processos não validados como pertencentes a este projeto."
}

$marker = [guid]::NewGuid().ToString("N")
# Start-Process joins ArgumentList values into a command line. Quote only the
# filesystem argument because the project path may contain spaces.
$quotedApp = '"' + $app + '"'
$arguments = @(
    $quotedApp,
    "--bind", "127.0.0.1",
    "--port", "$Port",
    "--tls-cert", ('"' + $tlsCert + '"'),
    "--tls-key", ('"' + $tlsKey + '"'),
    "--instance-marker", $marker
)

$proc = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $Root -RedirectStandardOutput $outLog -RedirectStandardError $errLog -WindowStyle Minimized -PassThru
Set-Content -LiteralPath $pidFile -Value $proc.Id -Encoding ascii
Set-Content -LiteralPath $markerFile -Value $marker -Encoding ascii

Start-Sleep -Milliseconds 1000
if (-not (Get-Process -Id $proc.Id -ErrorAction SilentlyContinue)) {
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $markerFile -Force -ErrorAction SilentlyContinue
    Write-Host "O servidor encerrou durante a inicialização."
    if (Test-Path -LiteralPath $errLog) { Get-Content -LiteralPath $errLog -Tail 80 }
    exit 1
}

# Confirm that the process we just launched is the one we own.
if (-not (Get-ProjectProcess -ProcessId $proc.Id -ExpectedMarker $marker)) {
    Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $markerFile -Force -ErrorAction SilentlyContinue
    throw "O processo iniciado não pôde ser validado como pertencente a este projeto."
}

Write-Host "Servidor iniciado (PID $($proc.Id))."
$appHost = "discord"
Write-Host "Login unico: https://${appHost}:$Port/"
Write-Host "Controle protegido: https://${appHost}:$Port/admin"
Start-Process "https://${appHost}:$Port/"
