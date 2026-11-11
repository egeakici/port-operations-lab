<#
.SYNOPSIS
Resource-guarded foreground facade over the unchanged approved Project04.ps1.
.EXAMPLE
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 ValidateExecution
.EXAMPLE
.\04-rail-crane-scheduler\scripts\manual\Project04.ps1 Train -Seed 1103
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('Help','ValidateExecution','Status','ValidateEnvironment','ValidateProfile',
                 'PrepareGeneration','Generate','ResumeGeneration','VerifyGeneration',
                 'PrepareBaselines','Baselines','ResumeBaselines','PrepareTraining','Train',
                 'ResumeTraining','TrainingStatus','SelectModels','PrepareEvaluation','Evaluate',
                 'ResumeEvaluation','VerifyResults','GenerateReport')]
    [string]$Action = 'Help',
    [ValidateSet(1103,2207,3301,4409,5501)]
    [int]$Seed
)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$pythonPath = Join-Path $projectRoot '.venv-research/Scripts/python.exe'
$originalInterface = Join-Path $projectRoot 'scripts/Project04.ps1'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw "Missing isolated environment: $pythonPath" }
if ($Action -eq 'Help') {
    Write-Output 'ValidateExecution: read-only exact approval/source/config/environment and RAM/disk preflight.'
    Write-Output 'Every other action except Help repeats this preflight before calling the existing interface.'
    Write-Output 'One action per invocation; foreground only. Train/ResumeTraining require one explicit -Seed.'
    & $originalInterface Help
    exit $LASTEXITCODE
}
if (($Action -in @('Train','ResumeTraining')) -ne $PSBoundParameters.ContainsKey('Seed')) {
    throw 'Use one explicit approved -Seed only with Train or ResumeTraining.'
}
# Capture only short preflight JSON. Scientific stdout/stderr are never piped or
# redirected, so native tqdm remains attached to the interactive PowerShell host.
$preflightOutput = & $pythonPath -B (Join-Path $PSScriptRoot 'preflight.py')
if ($LASTEXITCODE -ne 0) {
    $preflightOutput | Write-Output
    exit $LASTEXITCODE
}
$preflight = ($preflightOutput -join "`n") | ConvertFrom-Json
if ($Action -eq 'ValidateExecution') { $preflightOutput | Write-Output; exit 0 }
[Console]::Error.WriteLine(('[Project04] approved CPU profile verified; free RAM {0:N2} GiB, disk {1:N2} GiB. Foreground action: {2}' -f
    ($preflight.available_ram_bytes / 1GB), ($preflight.free_disk_bytes / 1GB), $Action))
$forward = @{ Action = $Action }
if ($PSBoundParameters.ContainsKey('Seed')) { $forward['Seed'] = $Seed }
& $originalInterface @forward
exit $LASTEXITCODE
