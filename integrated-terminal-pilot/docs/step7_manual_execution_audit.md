# Step 7 manual-execution transition audit

Owner instruction: CODE-ONLY DEVELOPMENT / MANUAL EXECUTION, 2026-10-14.
This supersedes previous permission for unattended continuation and automatic
local commits. See [ordered manual runbook](manual_execution_runbook.md).

## Actual state

- HEAD: `e364b80548a209ee4d9c04d2a060856c8d8aaa4e`.
- Previous executable snapshot: `c32d766d939b74b6c61cd596ee431aceea747a72931ee2e923e34ee31136947a`.
- No formal lock or Step 7 campaign episode at transition. Live generator register
  still has 28 pending statuses; actual approval is archived and remains valid.
  The manual recorder activates this approval without inventing a new decision.
- Known old supervisor/regression processes are absent. The regression stopped
  without a sealed result; do not call its observed 84 passed calls a full pass.
- Old continuation code archived by SHA and replaced with a refusing stub; active
  convenience status says `DISABLED_BY_OWNER_MANUAL_EXECUTION_ONLY`. All historical
  immutable artifacts and raw progress/evidence files are retained.

## Prepared changes

- Project-local AGENTS.md persists the manual-only owner boundary.
- Separate foreground CLIs for units, mandatory regressions, small device
  benchmark, optional development PPO, evidence assembly and locked campaign.
- Tqdm totals/elapsed/ETA/throughput with model and CPU simulation labels.
  Regression JSON/stdout remains capturable; raw combined logs are preserved.
- First Ctrl+C requests an episode-boundary stop; second interrupts immediately
  with partial starts retained for inspection. Completed rows resume by full
  integrity verification and skip, without retrying failures.
- Step 7 CPU inference remains frozen; CUDA fails explicitly there. Hardware
  comparison and development training alone accept explicit CPU/CUDA.
- Development training is segregated from all frozen checkpoint directories,
  scientific arms, validation/test data and checkpoint selection. It writes
  immutable boundary checkpoint bundles and refuses drift/tampering on resume.
- Validation-cache key shadowing repaired without changing its scientific gate.
- Exact current-source re-verification is required; no lock, approval metadata,
  commit, regression or scientific run is created automatically.

## Verification status

Syntax/static review only in this development turn. New tests are supplied for
manual execution, not reported as passing. CPU/CUDA speed, device availability,
cross-device action parity and training-resume parity are **unmeasured**. Historical
six-checkpoint integrity is checked read-only separately; no model is loaded for
evaluation or training by the development agent. Final source/changed-file hashes
are in `experiments/step7_paired_v1/manual_execution_code_audit.json`.

The scientific inventory remains 40 validation +100 test scenarios, 1260
integrated +700 nominal-reference episodes, Medium/Heavy primary, frozen arms
and three nested A3 seeds. QC8, Q6/K5-A, D24 and cargo obligations are unchanged.
No Step 7 outcome or universal coordination claim is available. Step 8: NO.


## Foreground two-computer workflow - 2026-10-20

Owner instruction now permits sequencing all required stages under ONE explicitly
owner-started foreground process on the remote computer. It does not permit the
coding agent to launch it, scheduled/background continuation, automatic commits,
or model retraining. This supersedes the older no-auto-advance wording only for
that manually launched foreground sequence. Historical disabled-automation evidence
and earlier partial regression logs remain unchanged. No previous incomplete suite
is relabelled PASS. See [step7_remote_execution.md](step7_remote_execution.md).
