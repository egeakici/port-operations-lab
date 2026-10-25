param(
    [ValidateSet('Run','Status','Plan','Verify','Analyze','Finalize','Help')][string]$Action='Run',
    [ValidatePattern('^[0-9a-f]{64}$')][string]$AcceptScientificPacket,
    [string]$Owner=$env:USERNAME,
    [string]$Interpreter
)
$ErrorActionPreference='Stop'
$closureProject=Split-Path $PSScriptRoot -Parent
$closureRepo=Split-Path $closureProject -Parent
$closureCLI=Join-Path $closureProject 'step8\final_closure.py'

function Invoke-ClosurePython {
    param([string[]]$Arguments)
    & $script:closurePython -B $closureCLI @Arguments
    if ($LASTEXITCODE -ne 0) {
        if ($LASTEXITCODE -eq 3) {
            throw 'Safely incomplete: completed records preserved. Resume with the SAME command; no episode timeout or automatic background continuation.'
        }
        throw "Closure action failed (exit $LASTEXITCODE). Keep ALL results/logs. A genuine failure needs investigation and is never silently skipped."
    }
}

Push-Location -LiteralPath $closureRepo
try {
    $env:PYTHONUTF8='1'
    $env:PYTHONDONTWRITEBYTECODE='1'
    $closureCandidates=@()
    if ($Interpreter) { $closureCandidates+= $Interpreter }
    else {
        $closureCandidates+= (Join-Path $closureRepo '.venv\step7-cpu3132\Scripts\python.exe')
        $closureCandidates+= (Join-Path $closureRepo '.venv\Scripts\python.exe')
        $closureSystemPython=Get-Command python -ErrorAction SilentlyContinue
        if ($closureSystemPython) { $closureCandidates+= $closureSystemPython.Source }
    }
    $closurePython=$closureCandidates | Where-Object { Test-Path -LiteralPath $_ -PathType Leaf } | Select-Object -First 1
    if (!$closurePython) { throw 'Existing verified Python not found. Restore the Step7 CPU environment; this launcher never installs or retrains automatically.' }
    if ($Action -eq 'Help') { Invoke-ClosurePython -Arguments @('--help'); exit 0 }
    if ($Action -eq 'Run') {
        & $closurePython -c "from importlib.metadata import version; from importlib.util import find_spec; import sys; ok=all(find_spec(n) and version(n)==v for n,v in [('scipy','1.15.2'),('matplotlib','3.10.1')]); sys.exit(0 if ok else 1)"
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'Installing only pinned Step8 analysis extras under frozen simulation constraints...'
            & $closurePython -m pip install -c (Join-Path $closureProject 'configs\protocol\step7_cpu_constraints.txt') -r (Join-Path $closureProject 'step8\analysis_requirements.txt')
            if ($LASTEXITCODE -ne 0) { throw 'Analysis dependency setup failed before any scientific episode. Preserve output; no Step7/training executed.' }
        }
    }
    if ($Action -ne 'Run') {
        $closureArguments=@($Action.ToLowerInvariant())
        if ($Action -eq 'Verify') { $closureArguments+= '--canonical' }
        Invoke-ClosurePython -Arguments $closureArguments
    } else {
        Write-Host 'Project I closure: NEW13M diagnostics only; Step7 archive/PPO/policies preserved.'
        Write-Host 'One foreground CPU worker. Progress/heartbeat. Ctrl+C stops after the active episode.'
        if ($AcceptScientificPacket) {
            if (!$Owner.Trim()) { throw 'Explicit owner identity required for scientific acceptance.' }
            Invoke-ClosurePython -Arguments @('approve','--accept-packet',$AcceptScientificPacket,'--owner',$Owner,
                '--provenance','Owner explicitly executed Complete-ProjectIClosure.ps1 with -AcceptScientificPacket after reviewing the exact FC01-04 packet')
        }
        Invoke-ClosurePython -Arguments @('resume')
        Invoke-ClosurePython -Arguments @('verify','--canonical')
        Invoke-ClosurePython -Arguments @('finalize')
        Write-Host 'Final release produced. Read PROJECT_I_SCIENTIFIC_CLOSURE.md and its manifest; closure is asserted only by the machine gate.'
        Write-Host 'Return experiments\step8_final_closure plus updated docs\step8 and PROJECT_I_SCIENTIFIC_CLOSURE.md to the coding computer. Preserve the original Step7 bundle.'
    }
} finally { Pop-Location }
