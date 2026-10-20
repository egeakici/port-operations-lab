param(
    [ValidateSet('Run','VerifyReturn','Status')][string]$Action = 'Run',
    [ValidatePattern('^[A-Za-z0-9_-]+$')][string]$RunName = 'campaign_v1',
    [string]$Python = 'python',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$step7Project = Split-Path $PSScriptRoot -Parent
$step7Repo = Split-Path $step7Project -Parent
$step7Bundle = Join-Path $step7Project ('experiments\step7_remote\' + $RunName)
$step7Interpreter = Join-Path $step7Repo '.venv\Scripts\python.exe'
Push-Location -LiteralPath $step7Repo
try {
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    if ($Action -eq 'Run') {
        if (!(Test-Path -LiteralPath $step7Interpreter)) {
            if (Test-Path -LiteralPath (Join-Path $step7Bundle 'session.json')) {
                throw 'Existing execution environment is missing. Restore its recorded dependencies before resuming.'
            }
            & $Python -m venv (Join-Path $step7Repo '.venv')
            if ($LASTEXITCODE) { throw 'Python 3.11+ virtual environment creation failed.' }
        }
        if (!$SkipInstall -and !(Test-Path -LiteralPath (Join-Path $step7Bundle 'session.json'))) {
            # Only before the first session. Never update dependencies under a scientific lock.
            & $step7Interpreter -m pip install -e './01-terminal-operations-core' -e './02-mini-port-simulation' -e './03-berth-allocation-lab[rl,dev,viz]' -e './integrated-terminal-pilot[dev]'
            if ($LASTEXITCODE) { throw 'Dependency installation failed. No campaign was started.' }
        }
    } elseif (!(Test-Path -LiteralPath $step7Interpreter)) {
        # Audit/status never installs Torch or starts a policy on the development computer.
        $step7Interpreter = $Python
    }
    $step7Mode = switch ($Action) { 'Run' {'--run'} 'VerifyReturn' {'--verify-return'} 'Status' {'--status'} }
    & $step7Interpreter (Join-Path $PSScriptRoot 'run_step7_remote.py') $step7Mode --bundle $step7Bundle
    $step7Exit = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $step7Exit
