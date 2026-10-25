# Project I scientific closure

**PROVISIONAL — SYNTHETIC / UNCALIBRATED. Project I is NOT finally closed.**

Official full canonical return verification is VERIFIED_FULL_CANONICAL. Primary Holm interval construction and the required diagnostic campaign remain blocked. The numerical calculations below are conditional previews, not final public inferential claims.

Analysis `ac9db68020c4079d293a202eb52a0fb9f2d995e1de79d5eecc070ddfe7dbdedf`; code `406e7907d29720db08b9e1b56093dbc71e78c38230a051c05bf9b8beca75f8e3`. Step7 manifest `d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`. Frozen scientific revision `8cc697f26575ca18ed98a164390a5a40e137b343`; analysis HEAD `2a05112bd5576b31dc7db36618ea3dfc287f07bb`.

```json
{
  "STEP7_CAMPAIGN_EXECUTION": "COMPLETED_1960_OF_1960",
  "STEP7_TRANSFER_METADATA_AUDIT": "VERIFIED",
  "STEP7_OFFICIAL_RETURN_GATE": "VERIFIED_FULL_CANONICAL",
  "STEP8_PRIMARY_ANALYSIS": "BLOCKED",
  "STEP8_S1_INFERENCE": "COMPLETE",
  "STEP8_S2_INFERENCE": "BLOCKED",
  "STEP8_CARGO_NONINFERIORITY": "COMPUTED",
  "STEP8_DIAGNOSTIC_ABLATIONS": "BLOCKED",
  "diagnostic_capability_status": "BLOCKED_SOURCE_CONTRACT_NOT_EXECUTABLE",
  "primary_inference_blocker": "HOLM_CI_CONSTRUCTION_UNSPECIFIED_IN_FROZEN_SOURCE",
  "STEP8_ANALYSIS_TESTS": "PASS",
  "STEP8_FINAL_REPORT": "PROVISIONAL",
  "PROJECT_I_FINAL_CLOSED": "NO",
  "reasons": [
    "Frozen primary Holm CI construction unspecified; raw95% intervals cannot replace adjusted primary gate",
    "Frozen SharedRolloutEvaluator/runner exposes no model-only crane/transport/yard coupling switches; changing execution physics is not a valid substitute.",
    "Frozen runner rejects B2 outside PRIMARY_RESEARCH_PROFILE; QC4/QC6 cannot be passed through that API as-is.",
    "Nominal 0.5min/move crane-off service is not achieved merely by transport/yard-off with shared cranes; realistic transshipment availability differs from A2 nominal semantics.",
    "Protocol11 universal none==A2 text is only supported by the approved scoped closure equivalence gate; no amended mapping to a realistic 13M coupling campaign is specified.",
    "Heavy occupancy0.3 explicitly unsupported in locked analysis note. Retain these cells, do not regenerate cargo or silently drop them.",
    "Coupling counts derive from protocol6.5/11 and the objective stays AM07; the operational mapping of model-only crane-off state and scoped none/A2 gate must be specified before new diagnostic results."
  ],
  "STEP7_OUTER_RERUNS": 0,
  "PPO_RETRAINING": "NONE",
  "CHECKPOINTS_AND_PHYSICS": "UNCHANGED",
  "new_diagnostic_episodes": 0
}
```

- [x] Existing Step7 campaign completed1960/1960; no rerun.
- [x] Source413paths, authentic checkpoints, approvals, parameters and seven restored references preserved.
- [x] Read-only scenario pairing, D24/cargo summaries and review reconciliation computed.
- [x] Prespecified10k time bootstrap and cargo upper-bound tests calculated provisionally; all checkpoints reported.
- [x] Existing matched B2/B2-T objective ablation analysed; eight figure families prepared.
- [ ] Official full canonical VerifyReturn PASS.
- [ ] Scientifically specified primary Holm CI construction (cannot silently choose after observing results).
- [ ] Source-consistent model-only coupling adapter/matrix/scoped equivalence and complete required13M diagnostics.
- [ ] Final source-bound verified inference/release.

A negative result would not prevent closure if these gates passed. Missing required evidence does prevent closure. No reapproval of unchanged28-values, administrative HEAD change or routine execution is being requested. The unresolved items are substantive scientific/source contracts. No working full-campaign command is invented.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONUTF8 = '1'
    powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Complete-Step7.ps1 -Action VerifyReturn
    if ($LASTEXITCODE -ne 0) { throw 'Canonical return verification failed; preserve all evidence.' }
    $step8Python = (Get-Command python -ErrorAction Stop).Source
    if (Test-Path -LiteralPath '.\.venv\step7-cpu3132\Scripts\python.exe') { $step8Python = '.\.venv\step7-cpu3132\Scripts\python.exe' }
    & $step8Python .\integrated-terminal-pilot\step8\run_tests.py
    if ($LASTEXITCODE -ne 0) { throw 'Focused Step8 tests failed.' }
    & $step8Python .\integrated-terminal-pilot\step8\run_step8.py --analyze --render
    if ($LASTEXITCODE -ne 0) { throw 'Read-only Step8 refresh failed; no original record was changed.' }
    & $step8Python .\integrated-terminal-pilot\step8\run_step8.py --status
    if ($LASTEXITCODE -ne 0) { throw 'Step8 status audit failed.' }
}
```

Run from the repository root. This verifies archives and refreshes analysis only; it does NOT start new simulation. There is deliberately no claimed working13M execution command: current frozen APIs cannot implement the locked model-only switches/scoped equality. `python integrated-terminal-pilot/step8/run_step8.py --diagnostic-preflight` publishes the exact blockers and exits2. Do not treat that failure as a reason to rerun Step7. A prospectively specified diagnostic implementation and a scientifically justified Holm construction are needed before a complete Step8 launch can be provided. They cannot be administratively inferred from the existing approval.
