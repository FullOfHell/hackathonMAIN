# Bootstrap the tools needed by the shared Git Bash setup.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Join-Path $PSScriptRoot '..')

function Install-Prerequisite($id) {
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw "Install $id manually or install Windows App Installer to enable winget, then rerun setup."
    }
    & winget.exe install --id $id --exact --source winget
    if ($LASTEXITCODE -ne 0) { throw "Installation of $id failed. Install it manually and rerun setup." }
    # Newly installed commands must be visible to Git Bash in this same session.
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
        [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
}

if (-not (Get-Command git.exe -ErrorAction SilentlyContinue)) { Install-Prerequisite 'Git.Git' }
$pythonReady = $false
foreach ($name in 'py.exe', 'python.exe') {
    $python = Get-Command $name -ErrorAction SilentlyContinue
    if ($python) {
        $versionArgs = @()
        if ($name -eq 'py.exe') { $versionArgs += '-3' }
        & $python.Source @versionArgs -c 'import sys; sys.exit(sys.version_info < (3, 10))'
        if ($LASTEXITCODE -eq 0) { $pythonReady = $true; break }
    }
}
if (-not $pythonReady) { Install-Prerequisite 'Python.Python.3.13' }
if (-not (Get-Command node.exe -ErrorAction SilentlyContinue) -or
    -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    Install-Prerequisite 'OpenJS.NodeJS.LTS'
}

$gitExec = git.exe --exec-path
$bash = Join-Path $gitExec '../../../bin/bash.exe'
if (-not (Test-Path -LiteralPath $bash)) { throw 'Git Bash is missing. Install Git for Windows and rerun setup.' }
& $bash scripts/setup.sh
exit $LASTEXITCODE
