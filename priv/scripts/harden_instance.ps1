$ErrorActionPreference = "Stop"

# Resolve project root from this script. Do not accept a path from cmd.exe.
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\.."))
$instance = Join-Path $Root "instance"
New-Item -ItemType Directory -Force -Path $instance | Out-Null

$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $identity.User) {
    throw "Nao foi possivel determinar o SID do usuario atual."
}
$userSid = $identity.User.Value
$systemSid = "S-1-5-18"

function Invoke-IcaclsChecked {
    param(
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$FailureMessage
    )

    & icacls @Arguments | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (icacls=$LASTEXITCODE)."
    }
}

# IMPORTANT:
# Apply (OI)(CI) only to the directory ACE. Those inheritance flags are directory
# inheritance metadata. The previous implementation recursively wrote that same
# ACE to files, which could leave existing key files without an effective access
# grant. This sequence hardens only the parent, then resets descendants so they
# inherit the parent's effective ACL.
Invoke-IcaclsChecked -Arguments @(
    $instance,
    "/grant:r",
    "*${userSid}:(OI)(CI)F",
    "*${systemSid}:(OI)(CI)F",
    "/Q"
) -FailureMessage "Falha ao conceder acesso ao diretorio instance"

# Remove inherited ACEs from the instance directory itself. The explicit ACEs
# above remain and are the only ACL source propagated to descendants.
Invoke-IcaclsChecked -Arguments @(
    $instance,
    "/inheritance:r",
    "/Q"
) -FailureMessage "Falha ao remover heranca do diretorio instance"

# Repair/harden every existing child independently. /reset replaces each child's
# ACL with its default inherited ACL. This is intentional: it repairs files that
# may have been made unreadable by v3.1 while preserving default-deny at parent.
$children = @(Get-ChildItem -LiteralPath $instance -Force -ErrorAction Stop)
foreach ($child in $children) {
    Invoke-IcaclsChecked -Arguments @(
        $child.FullName,
        "/reset",
        "/T",
        "/C",
        "/Q"
    ) -FailureMessage "Falha ao reparar ACL de $($child.FullName)"
}

# Fail closed if the account running Flask still cannot read the key material.
foreach ($name in @("master.key", "csrf.key", "audit.key")) {
    $path = Join-Path $instance $name
    if (Test-Path -LiteralPath $path) {
        try {
            $stream = [System.IO.File]::Open(
                $path,
                [System.IO.FileMode]::Open,
                [System.IO.FileAccess]::Read,
                [System.IO.FileShare]::ReadWrite
            )
            $stream.Dispose()
        }
        catch {
            throw "ACL aplicada, mas o usuario atual nao consegue ler $name : $($_.Exception.Message)"
        }
    }
}

# The bootstrap credentials intentionally remain in the package for update
# convenience. Restrict their local ACL to the current Windows identity and
# LocalSystem before the application starts. This does not protect a copied ZIP;
# it limits exposure on the installed filesystem.
foreach ($secretName in @("config\SUPABASE_PRIVILEGED.env", ".env")) {
    $secretPath = Join-Path $Root $secretName
    if (-not (Test-Path -LiteralPath $secretPath -PathType Leaf)) { continue }
    Invoke-IcaclsChecked -Arguments @(
        $secretPath,
        "/grant:r",
        "*${userSid}:F",
        "*${systemSid}:F",
        "/inheritance:r",
        "/Q"
    ) -FailureMessage "Falha ao proteger $secretName"
}

# Verify that the Flask process will also be able to create/write runtime state.
$probe = Join-Path $instance (".acl-probe-" + [Guid]::NewGuid().ToString("N") + ".tmp")
try {
    [System.IO.File]::WriteAllText($probe, "acl-ok", [System.Text.Encoding]::ASCII)
    Remove-Item -LiteralPath $probe -Force
}
catch {
    throw "ACL aplicada, mas o usuario atual nao consegue gravar em instance: $($_.Exception.Message)"
}

Write-Host "ACL validada para instance e bootstrap privado: usuario atual e LocalSystem com acesso; demais acessos negados por padrao."
