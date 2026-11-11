<#
.SYNOPSIS
Foreground Project 04 research commands in the isolated pinned environment.
.EXAMPLE
.\04-rail-crane-scheduler\scripts\Project04.ps1 Status
.EXAMPLE
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 1103
#>
[CmdletBinding()]
param(
    [Parameter(Position=0)]
    [ValidateSet('Help','Status','ValidateEnvironment','ValidateProfile','PrepareGeneration','Generate','ResumeGeneration','VerifyGeneration',
                 'PrepareBaselines','Baselines','ResumeBaselines','PrepareTraining','Train','ResumeTraining','TrainingStatus',
                 'SelectModels','PrepareEvaluation','Evaluate','ResumeEvaluation','VerifyResults','GenerateReport','RecordApproval')]
    [string]$Action = 'Help',
    [int]$Seed,
    [string]$Profile,
    [string]$WorkDirectory,
    [string]$Approval,
    [string]$ApprovalText,
    [string]$OwnerEvidence
)
$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv-research/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "Project 04 isolated environment missing: $pythonPath. See docs/research_readiness/ENVIRONMENT_SETUP.md."
}
$arguments = @('-B', '-m', 'rail_crane_scheduler.campaign_cli', $Action)
if ($Action -eq 'Help') { $arguments = @('-B', '-m', 'rail_crane_scheduler.campaign_cli', '--help') }
if ($PSBoundParameters.ContainsKey('Seed')) { $arguments += @('--seed', [string]$Seed) }
if ($Profile) { $arguments += @('--profile', [System.IO.Path]::GetFullPath($Profile)) }
if ($WorkDirectory) { $arguments += @('--workdir', [System.IO.Path]::GetFullPath($WorkDirectory)) }
if ($Approval) { $arguments += @('--approval', [System.IO.Path]::GetFullPath($Approval)) }
if ($ApprovalText) { $arguments += @('--approval-text', $ApprovalText) }
if ($OwnerEvidence) { $arguments += @('--owner-evidence', $OwnerEvidence) }
# stderr is intentionally left attached for real tqdm; stdout stays valid JSON.
# No activation, external environment, background process or silent fallback.
& $pythonPath @arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
