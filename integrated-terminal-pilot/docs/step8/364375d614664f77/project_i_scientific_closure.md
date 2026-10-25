# Project I scientific closure

**PROVISIONAL — SYNTHETIC / UNCALIBRATED. Project I is NOT finally closed.**

Official full canonical return verification is BYTES_METADATA_ONLY_PENDING. Primary Holm interval construction and the required diagnostic campaign remain blocked. The numerical calculations below are conditional previews, not final public inferential claims.

Analysis `364375d614664f77b7e36ae945e533df2380f42a97f0c6d49bf22ca66d9565e6`; code `adc41af1525ffe89aa2fb32e4dc8d9a3f46a57bd3b22366a6a358ea165031664`. Step7 manifest `d180f1dec4fb212185b40658f7be47dc66d0bd08e66b6636f88cb45c42b8357d`; lock `1e62f58554ad97d29356243b99975f4d494b4ac58009a0fc19d464fb027cbcac`. Frozen scientific revision `8cc697f26575ca18ed98a164390a5a40e137b343`; analysis HEAD `901602e1df803ba7f9b5b3f56972c31d10176941`.

```json
{
  "STEP7_CAMPAIGN_EXECUTION": "COMPLETED_1960_OF_1960",
  "STEP7_TRANSFER_METADATA_AUDIT": "VERIFIED",
  "STEP7_OFFICIAL_RETURN_GATE": "PENDING_MANUAL",
  "STEP8_PRIMARY_ANALYSIS": "PROVISIONAL_PENDING_RETURN",
  "STEP8_S1_INFERENCE": "PROVISIONAL",
  "STEP8_S2_INFERENCE": "BLOCKED_PRIMARY_HOLM_IMPLEMENTATION_GAP",
  "STEP8_CARGO_NONINFERIORITY": "PROVISIONAL",
  "STEP8_DIAGNOSTIC_ABLATIONS": "BLOCKED_SOURCE_CONTRACT_NOT_EXECUTABLE",
  "STEP8_ANALYSIS_TESTS": "PASS",
  "STEP8_FINAL_REPORT": "PROVISIONAL",
  "PROJECT_I_FINAL_CLOSED": "NO",
  "reasons": [
    "Official full canonical VerifyReturn pending owner execution",
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
