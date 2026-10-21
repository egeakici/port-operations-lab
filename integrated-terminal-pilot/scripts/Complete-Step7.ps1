param(
    [ValidateSet('Run','Status','VerifyReturn','Diagnose')][string]$Action = 'Run',
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = 'step7_cpu3132_v1'
)
$ErrorActionPreference = 'Stop'
$step7Project = Split-Path $PSScriptRoot -Parent
$step7Repo = Split-Path $step7Project -Parent
$step7Bundle = Join-Path $step7Project ('experiments\step7_remote\' + $RunName)
$step7EnvSpec = Join-Path $step7Project 'configs\protocol\step7_cpu_environment_v1.json'
$step7Constraints = Join-Path $step7Project 'configs\protocol\step7_cpu_constraints.txt'
$step7Bootstrap = Join-Path $step7Repo '.venv\step7-bootstrap'
$step7BootstrapSpec = Join-Path $step7Project 'configs\protocol\step7_python_bootstrap_v1.json'
$step7Environment = Join-Path $step7Repo '.venv\step7-cpu3132'
$step7Python = Join-Path $step7Environment 'Scripts\python.exe'
$step7Ready = Join-Path $step7Environment 'step7_environment_ready.json'
$step7Transcript = $false
$step7Exit = 2

function Invoke-Step7Native {
    param([scriptblock]$Command)
    & $Command
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE). Original logs are preserved." }
}

Push-Location -LiteralPath $step7Repo
try {
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    if ($Action -eq 'Diagnose') {
        $step7DiagnosticPython = Join-Path $step7Repo '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $step7Python) { $step7DiagnosticPython = $step7Python }
        elseif (!(Test-Path -LiteralPath $step7DiagnosticPython)) { $step7DiagnosticPython = (Get-Command python -ErrorAction Stop).Source }
        Invoke-Step7Native { & $step7DiagnosticPython (Join-Path $PSScriptRoot 'run_step7_remote.py') --diagnose --bundle $step7Bundle }
        $step7Exit = 0
    } elseif ($Action -ne 'Run' -or (Test-Path -LiteralPath (Join-Path $step7Bundle 'transfer_manifest.json'))) {
        # Audit/status are read-only with respect to the execution environment.
        $step7AuditAction = $Action
        if ($Action -eq 'Run') { $step7AuditAction = 'VerifyReturn' }
        $step7AuditPython = Join-Path $step7Repo '.venv\Scripts\python.exe'
        if (Test-Path -LiteralPath $step7Python) { $step7AuditPython = $step7Python }
        elseif (!(Test-Path -LiteralPath $step7AuditPython)) { $step7AuditPython = (Get-Command python -ErrorAction Stop).Source }
        & (Join-Path $PSScriptRoot 'Start-Step7Remote.ps1') -Action $step7AuditAction -RunName $RunName -Interpreter $step7AuditPython -SkipInstall
        $step7Exit = $LASTEXITCODE
    } else {
        $step7Tracked = & git status --porcelain --untracked-files=no
        if ($LASTEXITCODE) { throw 'Cannot inspect Git source state.' }
        $step7Untracked = & git ls-files --others --exclude-standard integrated-terminal-pilot
        if ($LASTEXITCODE -or $step7Tracked -or $step7Untracked) { throw 'Commit/push/pull the reviewed implementation first. Dirty source is not executable.' }
        if (Test-Path -LiteralPath (Join-Path $step7Bundle 'pipeline\FAILED.json')) {
            throw 'A genuine failure is preserved in this bundle. Use -Action Diagnose; no automatic retry or deletion.'
        }
        New-Item -ItemType Directory -Path (Join-Path $step7Bundle 'bootstrap') -Force | Out-Null
        $step7TranscriptPath = Join-Path $step7Bundle ('bootstrap\setup_' + [guid]::NewGuid().ToString('N') + '.log')
        Start-Transcript -LiteralPath $step7TranscriptPath | Out-Null
        $step7Transcript = $true
        $step7SpecHash = (Get-FileHash -LiteralPath $step7EnvSpec -Algorithm SHA256).Hash.ToLowerInvariant()
        $step7ConstraintsHash = (Get-FileHash -LiteralPath $step7Constraints -Algorithm SHA256).Hash.ToLowerInvariant()
        if (!(Test-Path -LiteralPath $step7Ready)) {
            if (Test-Path -LiteralPath (Join-Path $step7Bundle 'session.json')) {
                throw 'Recorded execution environment is missing. Restore it; do not reinstall under an existing scientific session.'
            }
            # The Windows installer can complete in maintenance mode without honoring
            # a new TargetDir. Use PSF's standalone build-system package instead.
            # Its exact version/archive hash are pinned; no registry or PATH edits.
            . (Join-Path $PSScriptRoot 'Step7PythonBootstrap.ps1')
            $step7RuntimePython = Get-Step7ReferencePython -BootstrapDirectory $step7Bootstrap `
                -SpecificationPath $step7BootstrapSpec -EvidenceDirectory (Join-Path $step7Bundle 'bootstrap')
            if (!(Test-Path -LiteralPath $step7Python)) {
                Write-Host 'Creating the separate Step 7 Python environment...'
                Invoke-Step7Native { & $step7RuntimePython -m venv $step7Environment }
            }
            Invoke-Step7Native { & $step7Python -c "import sys; assert sys.version_info[:3] == (3,13,2), sys.version" }
            Write-Host 'Installing pinned CPU dependencies; experiments begin only after setup and prerequisite checks...'
            Invoke-Step7Native { & $step7Python -m pip install -c $step7Constraints 'torch==2.6.0' --index-url https://download.pytorch.org/whl/cpu }
            Invoke-Step7Native { & $step7Python -m pip install -c $step7Constraints -e './01-terminal-operations-core' -e './02-mini-port-simulation' -e './03-berth-allocation-lab[rl,dev,viz]' -e './integrated-terminal-pilot[dev]' }
            Invoke-Step7Native { & $step7Python -c "from integrated_terminal_pilot.benchmark.step7_environment import verify; print(verify())" }
            $step7ReadyPartial = $step7Ready + '.' + [guid]::NewGuid().ToString('N') + '.partial'
            @{environment_spec_sha256=$step7SpecHash; constraints_sha256=$step7ConstraintsHash} |
                ConvertTo-Json | Set-Content -LiteralPath $step7ReadyPartial -Encoding UTF8
            [IO.File]::Move($step7ReadyPartial, $step7Ready)
        } else {
            $step7Recorded = Get-Content -LiteralPath $step7Ready -Raw | ConvertFrom-Json
            if ($step7Recorded.environment_spec_sha256 -ne $step7SpecHash -or $step7Recorded.constraints_sha256 -ne $step7ConstraintsHash) {
                throw 'Environment specification changed. Preserve the old environment/session; do not update silently.'
            }
            Invoke-Step7Native { & $step7Python -c "from integrated_terminal_pilot.benchmark.step7_environment import verify; print(verify())" }
        }
        $step7RetainedReady = Join-Path $step7Bundle 'bootstrap\environment_ready.json'
        if (Test-Path -LiteralPath $step7RetainedReady) {
            if ((Get-FileHash -LiteralPath $step7Ready).Hash -ne (Get-FileHash -LiteralPath $step7RetainedReady).Hash) {
                throw 'Retained environment receipt differs; never overwrite execution evidence.'
            }
        } else { Copy-Item -LiteralPath $step7Ready -Destination $step7RetainedReady }
        Write-Host "Step 7 result folder: $step7Bundle"
        # Keep setup transcript outside the subsequent immutable scientific export.
        Stop-Transcript | Out-Null
        $step7Transcript = $false
        & (Join-Path $PSScriptRoot 'Start-Step7Remote.ps1') -RunName $RunName -Interpreter $step7Python -SkipInstall
        $step7Exit = $LASTEXITCODE
    }
} catch {
    Write-Host ('BLOCKED_PRESERVED: ' + $_.Exception.Message) -ForegroundColor Red
    if ($step7Transcript) {
        $step7SetupFailure = Join-Path $step7Bundle ('bootstrap\failure_' + [guid]::NewGuid().ToString('N') + '.json')
        @{
            phase='bootstrap'; exception=$_.Exception.ToString(); position=$_.InvocationInfo.PositionMessage
            stack=$_.ScriptStackTrace; transcript=$step7TranscriptPath
        } | ConvertTo-Json | Set-Content -LiteralPath $step7SetupFailure -Encoding UTF8
        Write-Host "Setup error details: $step7SetupFailure"
    }
    Write-Host "Keep this folder and its logs: $step7Bundle"
    $step7Exit = 2
} finally {
    if ($step7Transcript) { Stop-Transcript | Out-Null }
    Pop-Location
}
exit $step7Exit
