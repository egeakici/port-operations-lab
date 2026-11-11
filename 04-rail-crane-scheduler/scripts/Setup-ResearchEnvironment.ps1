<# .SYNOPSIS
Reproduce the verified Windows AMD64 CPython 3.13.2 environment, without legacy changes.
#>
[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv-research/Scripts/python.exe'
if (Test-Path -LiteralPath $pythonPath) {
    & $pythonPath -B -m rail_crane_scheduler.campaign_cli ValidateEnvironment
    if ($LASTEXITCODE -ne 0) { throw 'Existing isolated environment differs; preserve it and review before changing packages.' }
    return
}
$version = & py -3.13 -c 'import platform; print(platform.python_version())'
if ($LASTEXITCODE -ne 0 -or $version -ne '3.13.2') { throw 'Exact CPython 3.13.2 is required by this environment lock.' }
& py -3.13 -m venv (Join-Path $projectRoot '.venv-research')
if ($LASTEXITCODE -ne 0) { throw 'venv setup failed; retained for inspection.' }
& $pythonPath -m pip install --require-hashes --only-binary=:all: --cache-dir (Join-Path $projectRoot 'experiments/pip-cache') -r (Join-Path $projectRoot 'configs/research/requirements-research.lock')
if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed; no experiment launched.' }
& $pythonPath -m pip install --no-deps --no-build-isolation -e $projectRoot
if ($LASTEXITCODE -ne 0) { throw 'Editable Project 04 packaging failed.' }
& $pythonPath -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency compatibility check failed.' }
& $pythonPath -B -m rail_crane_scheduler.campaign_cli ValidateEnvironment
if ($LASTEXITCODE -ne 0) { throw 'Installed environment does not match the approved identity.' }
