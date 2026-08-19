param(
    [switch]$Elevated,
    [string]$LogPath = ""
)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$runtime = Join-Path $Root ".runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $runtime "hostname-setup.log"
}

$hostname = "discord"
# Constructed only for upgrade cleanup; the retired value is not an active project hostname.
$legacyHostname = "discord" + ".local" + ".test"
$hostsPath = Join-Path $env:SystemRoot "System32\drivers\etc\hosts"

function Write-SetupLog([string]$Message) {
    $line = "{0:u} {1}" -f (Get-Date), $Message
    try { Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8 -ErrorAction SilentlyContinue } catch { }
    Write-Host $Message
}

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-HostTokens([string]$Line) {
    $body = ($Line -split '#', 2)[0].Trim()
    if (-not $body) { return @() }
    return @($body -split '\s+' | Where-Object { $_ })
}

function Test-CanonicalMapping {
    if (-not (Test-Path -LiteralPath $hostsPath -PathType Leaf)) { return $false }
    $currentCount = 0
    $loopbackCount = 0
    $legacyCount = 0
    foreach ($line in [System.IO.File]::ReadAllLines($hostsPath)) {
        $tokens = @(Get-HostTokens $line)
        if ($tokens.Count -lt 2) { continue }
        $ip = $tokens[0]
        for ($i = 1; $i -lt $tokens.Count; $i++) {
            if ([string]::Equals($tokens[$i], $hostname, [System.StringComparison]::OrdinalIgnoreCase)) {
                $currentCount += 1
                if ($ip -eq "127.0.0.1") { $loopbackCount += 1 }
            }
            if ([string]::Equals($tokens[$i], $legacyHostname, [System.StringComparison]::OrdinalIgnoreCase)) {
                $legacyCount += 1
            }
        }
    }
    return ($currentCount -eq 1 -and $loopbackCount -eq 1 -and $legacyCount -eq 0)
}

function Update-HostsFile {
    if (-not (Test-Path -LiteralPath $hostsPath -PathType Leaf)) {
        throw "Arquivo hosts nao encontrado: $hostsPath"
    }

    $original = [System.IO.File]::ReadAllLines($hostsPath)
    $updated = New-Object System.Collections.Generic.List[string]

    foreach ($line in $original) {
        $comment = ""
        $commentIndex = $line.IndexOf('#')
        if ($commentIndex -ge 0) { $comment = $line.Substring($commentIndex).TrimEnd() }
        $tokens = @(Get-HostTokens $line)
        if ($tokens.Count -lt 2) {
            $updated.Add($line)
            continue
        }

        $ip = $tokens[0]
        $keptHosts = New-Object System.Collections.Generic.List[string]
        for ($i = 1; $i -lt $tokens.Count; $i++) {
            $candidate = $tokens[$i]
            $isCurrent = [string]::Equals($candidate, $hostname, [System.StringComparison]::OrdinalIgnoreCase)
            $isLegacy = [string]::Equals($candidate, $legacyHostname, [System.StringComparison]::OrdinalIgnoreCase)
            if (-not $isCurrent -and -not $isLegacy) { $keptHosts.Add($candidate) }
        }

        if ($keptHosts.Count -eq ($tokens.Count - 1)) {
            $updated.Add($line)
            continue
        }

        # Preserve unrelated aliases that happened to share the same hosts line.
        if ($keptHosts.Count -gt 0) {
            $rebuilt = $ip + "`t" + ($keptHosts -join "`t")
            if ($comment) { $rebuilt += "`t" + $comment }
            $updated.Add($rebuilt)
        }
    }

    $updated.Add("127.0.0.1`tdiscord`t# local application hostname")

    $file = Get-Item -LiteralPath $hostsPath -Force
    $wasReadOnly = [bool]($file.Attributes -band [System.IO.FileAttributes]::ReadOnly)
    try {
        if ($wasReadOnly) { $file.IsReadOnly = $false }
        [System.IO.File]::WriteAllLines($hostsPath, [string[]]$updated, [System.Text.Encoding]::ASCII)
    } finally {
        if ($wasReadOnly) {
            try { (Get-Item -LiteralPath $hostsPath -Force).IsReadOnly = $true } catch { }
        }
    }

    try { & ipconfig /flushdns | Out-Null } catch { }
    if (-not (Test-CanonicalMapping)) {
        throw "A gravacao terminou, mas a entrada 127.0.0.1 discord nao foi confirmada no arquivo hosts."
    }
}

try {
    if (Test-CanonicalMapping) {
        Write-SetupLog "Hostname local OK: discord -> 127.0.0.1"
        exit 0
    }

    if (-not (Test-IsAdministrator)) {
        if ($Elevated) { throw "Elevacao administrativa nao foi obtida." }
        Write-SetupLog "Configurando o hostname local unico: 127.0.0.1 discord"
        $argLine = '-NoProfile -ExecutionPolicy Bypass -File "' + $PSCommandPath + '" -Elevated -LogPath "' + $LogPath + '"'
        try {
            $proc = Start-Process -FilePath "powershell.exe" -Verb RunAs -ArgumentList $argLine -Wait -PassThru
        } catch {
            throw "Elevacao UAC cancelada ou indisponivel: $($_.Exception.Message)"
        }
        if ($null -eq $proc -or $proc.ExitCode -ne 0) {
            $code = if ($null -eq $proc) { -1 } else { $proc.ExitCode }
            throw "Processo elevado terminou com codigo $code. Consulte $LogPath"
        }
        if (-not (Test-CanonicalMapping)) {
            throw "O processo elevado terminou sem instalar 127.0.0.1 discord. Consulte $LogPath"
        }
        Write-SetupLog "Hostname local instalado: discord -> 127.0.0.1"
        exit 0
    }

    Write-SetupLog "Aplicando hostname local como administrador: 127.0.0.1 discord"
    Update-HostsFile
    Write-SetupLog "Hostname local instalado: discord -> 127.0.0.1"
    exit 0
} catch {
    Write-SetupLog ("ERRO: " + $_.Exception.Message)
    exit 1
}
