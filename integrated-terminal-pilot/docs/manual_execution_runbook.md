# Code-only development and manual execution

**Current procedure (2026-10-20):** use [the remote execution runbook](step7_remote_execution.md).
Its single owner-started foreground command sequences the required stages.
The older independent-phase commands below are historical; do not mix their
source-mutating approval/lock recipe with portable bundle execution.

The owner superseded unattended execution on 2026-10-14. Agents prepare/review
code and commands; the owner runs tests, benchmarks, training and experiments in
a foreground terminal. No automatic continuation, background launch, automatic
Git commit or automatic phase transition is permitted. The original Step 7
scientific design and explicit 28-value approval remain intact.

## Audit and preservation

- HEAD at transition: `e364b80548a209ee4d9c04d2a060856c8d8aaa4e`.
- The old continuation PID 25564, regression PID 23428 and launcher PID 30872
  were absent when inspected. No active job was killed. The cause of their exit
  is unknown. The full regression has 84 passed calls and no recorded failure,
  but **no JUnit/result completion evidence**. It is incomplete, never PASS.
- The continuation is now a refusing stub. Its exact original bytes are archived
  at `experiments/step7_paired_v1/disabled_automation/5a039d8d8a732fc29a26882cad470ea612daa0e5c8b36bc826574c8748268310.py.txt`.
  The transition manifest is `experiments/step7_paired_v1/manual_execution_transition.json`.
- Previous 426-pass/16-deselected Project03 evidence and 30-pass focused evidence
  remain historical evidence for their old source snapshot. They are not a pass
  for these new files. Old stdout, events, results, approval reply/context and
  all F3 evidence/checkpoints are retained. No formal Step 7 lock or campaign
  episode existed at transition. No tests or expensive operations were launched
  while implementing this workflow.
- The actual owner reply `1` approved all 28 rows of packet
  `823c39239b289571da0047d87fe2d80863fe6840323bd34d8c7ad6fec99d0636`.
  This is not another approval request. Live register activation is a separate
  manual recording operation below, after the required intake-state regressions.

## Devices and progress

Step 7's frozen checkpoint contract uses CPU inference with one Torch thread.
`run_step7_campaign.py --device cuda` fails explicitly. A2/B2/B2-T and the physical
event simulator remain CPU workloads; RTX hardware does not move Python events
or candidate evaluation onto CUDA. The separate diagnostic can move a private
loaded PPO copy to CUDA, without writing or replacing any frozen checkpoint.

The diagnostic times actual deterministic PPO prediction on the same bounded
development observation/mask sequence, with warmup and synchronized CUDA timing
boundaries. It reports prediction throughput and CPU environment-step cost
separately, hashes before/after and CPU/CUDA selected-action agreement. Loading,
device transfer, observation copying and warmup are outside the prediction timer
and separately labelled where measured. It does not benchmark PPO updates or
integrated rollout acceleration; one-device ordering and short-sample effects
remain. No CUDA absence falls back silently. Diagnostic action agreement alone
does not authorize CUDA in Step 7.

Timing/progress references: [PyTorch CUDA timing semantics](https://docs.pytorch.org/docs/stable/notes/cuda.html#asynchronous-execution)
and [tqdm display fields](https://tqdm.github.io/docs/tqdm/).

Tqdm displays completed/total work, elapsed, ETA and throughput on stderr; JSON
results stay on stdout. Campaign progress includes completed/G-blocked accounted
episodes and preserves their separate statuses in JSON. Prior verified rows are
included in the initial count. A 15-second heartbeat refreshes the live display
during a long episode. ETA is observational and may be poor for heterogeneous
arms/congestion; there is no timeout, cohort cap, resource admission deadline or
policy substitution. Regression progress counts completed test teardowns and
identifies the active test/phase. Training uses a known step budget and an
observed completed-episode count; its total episode count is inherently unknown.

## Required manual sequence for Step 7

Run these blocks from the repository root in the **same PowerShell session**.
Stop on any nonzero exit code, inspect the preserved evidence, and fix only
demonstrated pre-lock defects. Do not substitute old-source results.

### 1. Environment and unit tests

On a new machine, install the four editable local packages into an isolated
Python environment. Install a CUDA-enabled Torch build appropriate for that
machine separately using the official PyTorch installation selector if desired;
the repository does not choose or install a CUDA driver automatically.

```powershell
$env:PYTHONDONTWRITEBYTECODE = '1'
$env:PYTHONUTF8 = '1'
python -m pip install -e ./01-terminal-operations-core -e ./02-mini-port-simulation -e ./03-berth-allocation-lab -e './integrated-terminal-pilot[dev]'
if ($LASTEXITCODE) { throw 'Environment installation failed' }
python integrated-terminal-pilot/scripts/verify_step7_regressions.py --suite unit
if ($LASTEXITCODE) { throw 'Unit tests failed; inspect the printed result/log path' }
```

The new bounded tests cover explicit device failure, two-stage Ctrl+C, admission
stop, validation-cache identity, sandbox containment, checkpoint tampering and
environment serialization. No unit test trains PPO. Existing development-only
instrumentation tests retain action/prediction/ledger parity checks.

### 2. Optional small hardware diagnostic (not a required scientific run)

```powershell
python integrated-terminal-pilot/scripts/benchmark_itp_devices.py --device both --steps 32 --repeats 3 --warmup 2 --scenario-seed 10000000 --training-seed 11
# If CUDA is unavailable, the report explicitly says so and returns exit 2.
# A CPU-only measurement is a separate explicit invocation:
# python integrated-terminal-pilot/scripts/benchmark_itp_devices.py --device cpu --steps 32 --repeats 3
```

This is intentionally not executed automatically. It neither trains nor changes
the campaign's CPU device. Review its output before selecting hardware for
optional development training.

### 3. Required clean regressions on this exact implementation snapshot

```powershell
$full = python integrated-terminal-pilot/scripts/verify_step7_regressions.py --suite project-i-full | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Full Project I regression did not pass' }
$fast = python integrated-terminal-pilot/scripts/verify_step7_regressions.py --suite project03-fast | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Eligible Project03 fast regression did not pass' }
$evidence = python integrated-terminal-pilot/scripts/assemble_step7_regressions.py --project-i-result $full.result --project03-result $fast.result | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Regression evidence rejected' }
```

Each command owns a unique temp/log directory. The full command opts into all
nine slow gates once; no separate 80/400 campaign is required. Project03's exact
training/real-held-out exclusions remain in the runner/result. Original module
exclusions and mixed-module safe tests are preserved. Interrupted runs keep logs
and exit status; they cannot satisfy the lock. Pytest is not resumable halfway
through the mandatory complete suite: a fresh manual full command is necessary.

### 4. Record the existing owner approval, then prepare the exact current plan

The legacy regression includes assertions about the original intake state.
Record owner-only approval metadata after its clean completion; the evidence
verifier independently requires unchanged numeric values and executable code.
Do not rerun this recorder if an active approval already exists; use preflight
to verify that provenance instead. This recorder does not run a campaign.

```powershell
$r = 'integrated-terminal-pilot/experiments/step7_paired_v1'
$ctx = Get-Content "$r/owner_reply_context_20261014.json" -Raw | ConvertFrom-Json
$ids = '005,007,008,010,011,012,013,014,015,026,027,028,035,040,041,043,050,051,052,053,054,060,071,073,074,077,078,079'.Split(',') | ForEach-Object { "S2-$_" }
python integrated-terminal-pilot/scripts/record_step7_owner_approval.py --message-file "$r/owner_reply_20261014.txt" --context-file "$r/owner_reply_context_20261014.json" --date $ctx.date --source $ctx.source --packet-sha $ctx.packet_sha256 --ids $ids --append-documentation
if ($LASTEXITCODE) { throw 'Approval recording failed; preserve partial evidence and inspect' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --preflight
if ($LASTEXITCODE) { throw 'Preflight failed' }
$plan = python integrated-terminal-pilot/scripts/run_step7_campaign.py --plan | ConvertFrom-Json
if ($LASTEXITCODE) { throw 'Plan rejected' }
$p = $plan.plan
$plan | ConvertTo-Json | Set-Content "$r/manual_plan_selection.json" -Encoding utf8
$evidence | ConvertTo-Json | Set-Content "$r/manual_regression_selection.json" -Encoding utf8
$plan
```

The old `ed9679b42562` plan is historical, not executable on this source. These
changes require a new source/plan fingerprint, clean current regressions and the
normal formal lock. The same 140 scenarios/1960 episodes, approved 28 numeric
values, QC8, Q6/K5-A, CPU checkpoints and scientific analysis contract are kept.
No 11M/12M/13M scenario is generated by planning or preflight.

### 5. Owner-reviewed local source commit and exclusive lock

Do not broadly stage unrelated work. Review `git status --short`, stage only the
Project I changes and generated small approval history, review the staged diff,
and make the source commit manually. `git add` or `git commit` is never called by
these CLIs. Large ignored results stay ignored. The owner-supplied root prompt
does not need staging. The controller refuses dirty or unknown untracked Project
I source, even when that is inconvenient.

```powershell
git status --short
# After reviewing exactly these Project I changes and confirming no unrelated work:
git add -- integrated-terminal-pilot/AGENTS.md integrated-terminal-pilot/pyproject.toml integrated-terminal-pilot/configs/protocol/step7_analysis_contract.json integrated-terminal-pilot/configs/protocol/step7_pending_values_packet.json integrated-terminal-pilot/configs/protocol/step7_pending_values_packet.json.sha256.json integrated-terminal-pilot/configs/protocol/step7_owner_28_approval.json integrated-terminal-pilot/configs/protocol/step7_owner_28_approval.json.sha256.json integrated-terminal-pilot/configs/protocol/step7_approval_history integrated-terminal-pilot/configs/generator/itp_generator_v1_decisions.yaml
git add -- integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/step7.py integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/step7_readiness.py integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/step7_pytest.py integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/step7_report.py integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/execution.py integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/device_benchmark.py integrated-terminal-pilot/src/integrated_terminal_pilot/benchmark/development_training.py
git add -- integrated-terminal-pilot/scripts/run_step7_campaign.py integrated-terminal-pilot/scripts/record_step7_owner_approval.py integrated-terminal-pilot/scripts/verify_step7_regressions.py integrated-terminal-pilot/scripts/assemble_step7_regressions.py integrated-terminal-pilot/scripts/benchmark_itp_devices.py integrated-terminal-pilot/scripts/train_itp_development_ppo.py integrated-terminal-pilot/tests/unit/test_step7_campaign.py integrated-terminal-pilot/tests/unit/test_manual_execution.py
git add -- integrated-terminal-pilot/docs/manual_execution_runbook.md integrated-terminal-pilot/docs/step7_manual_execution_audit.md integrated-terminal-pilot/docs/step7_owner_approval_packet.md integrated-terminal-pilot/docs/step7_scientific_lock_and_campaign.md integrated-terminal-pilot/docs/step7_source_and_readiness_audit.md integrated-terminal-pilot/docs/step7_presentation_evidence.md integrated-terminal-pilot/docs/protocol_amendments.md integrated-terminal-pilot/docs/pre_step6_synthetic_parameter_approval_matrix.md
git diff --cached --check
git diff --cached --stat
# Review staged changes before this explicit owner-run command:
git commit -m 'feat: prepare manual-only Step 7 execution with progress and device diagnostics'
if ($LASTEXITCODE) { throw 'Source commit failed' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --preflight
if ($LASTEXITCODE) { throw 'Preflight failed' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --lock --plan-file "$p" --regression-evidence $evidence.evidence
if ($LASTEXITCODE) { throw 'Exclusive lock rejected; do not hand-edit it' }
git add -- integrated-terminal-pilot/protocol_lock_v1.json integrated-terminal-pilot/protocol_lock_v1.json.sha256
git commit -m 'chore: lock owner-approved Step 7 manual experimental campaign'
if ($LASTEXITCODE) { throw 'Lock commit failed' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --verify --plan-file "$p"
if ($LASTEXITCODE) { throw 'Locked state verification failed' }
```

HEAD-only descendant metadata changes are allowed when protected bytes match.
Moving the run to a CUDA computer does not waive source, dependency or checkpoint
gates. Install/verify the intended environment **before** final regressions/lock.
Do not edit source after locking; record any post-lock defect and request scoped
scientific review instead of quietly updating the lock.

### 6. Foreground validation, then foreground test, verification and reporting

```powershell
python integrated-terminal-pilot/scripts/run_step7_campaign.py --resume --split validation --plan-file "$p" --device cpu
if ($LASTEXITCODE) { throw 'Validation stopped; inspect progress before proceeding' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --verify --plan-file "$p"
if ($LASTEXITCODE) { throw 'Validation evidence failed verification' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --resume --split test --plan-file "$p" --device cpu
if ($LASTEXITCODE) { throw 'Test campaign stopped; inspect evidence' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --verify --plan-file "$p"
if ($LASTEXITCODE) { throw 'Final evidence failed verification' }
python integrated-terminal-pilot/scripts/run_step7_campaign.py --status --plan-file "$p"
python integrated-terminal-pilot/scripts/run_step7_campaign.py --report --plan-file "$p"
```

Validation has 560 episodes, test 1400. Test stays sealed until all validation
rows are accounted for with the unchanged failure/deadlock gates. Valid completed
episodes are verified and skipped on resume. Failed or partially started rows
are never overwritten or silently retried. All old evidence stays immutable.

First Ctrl+C requests completion/sealing of the current episode and prevents a
new admission, then exits 130. The normal `--resume` command continues completed
work. Second Ctrl+C/OS loss may leave a partial marker; inspect it rather than
delete it. No mid-simulator episode checkpoint is claimed. A stale worker lock
can be archived only after host/PID/create-time checks; a live/foreign worker
blocks another. One serial worker remains the validated design; no automatic
retry, process pool or automatic next stage is present.

In a fresh terminal, recover the exact chosen paths without guessing which old
plan was approved:

```powershell
$r = 'integrated-terminal-pilot/experiments/step7_paired_v1'
$p = (Get-Content "$r/manual_plan_selection.json" -Raw | ConvertFrom-Json).plan
$evidence = Get-Content "$r/manual_regression_selection.json" -Raw | ConvertFrom-Json
```

For the previously preregistered physical-inner-event count, run each campaign
invocation under a unique stdlib cProfile file instead of the plain resume command:

```powershell
$prof = "$r/manual_$([guid]::NewGuid().ToString('N')).prof"
python -m cProfile -o "$prof" integrated-terminal-pilot/scripts/run_step7_campaign.py --resume --split validation --plan-file "$p" --device cpu
```

Use `--split test` only at its later stage. Profiling overhead is part of measured
cost and must be labelled. Preserve which rows were newly executed in each
invocation; inner events are actual kernel `_process` calls minus their canonical
outer event lines, never an inferred cycle count. A crash can leave profiler
counts unavailable. All policy WAIT/forecast/cargo diagnostics remain in sealed
records. The benchmark is not a replacement for these scientific diagnostics.

## Optional separate PPO development training

**Not part of the Step 7 sequence.** No training is required or authorized to
replace its frozen arms. These commands are for an explicit owner-chosen future
development run only. This sandbox trains the unchanged Project03 joint-scoring
PPO on one nominal berth projection of a declared 10M development scenario, one
environment, with original reward/hyperparameters and explicitly recorded
device/n_envs overrides. It is not integrated PPO or a new scientifically eligible
checkpoint. It opens no validation/test outcomes and performs no model selection.

```powershell
$train = "integrated-terminal-pilot/experiments/training_sandbox/manual_$([guid]::NewGuid().ToString('N'))"
python integrated-terminal-pilot/scripts/train_itp_development_ppo.py --acknowledge-development-only --device cuda --run-dir "$train" --total-timesteps 4096 --checkpoint-every 512 --scenario-seed 10000000 --training-seed 11
# Use --device cpu for an explicitly separate CPU run; no automatic fallback.
# After an interruption, use exactly the same settings and the last complete bundle:
$ck = (Get-Content "$train/latest_checkpoint.json" -Raw | ConvertFrom-Json).checkpoint
python integrated-terminal-pilot/scripts/train_itp_development_ppo.py --acknowledge-development-only --device cuda --run-dir "$train" --total-timesteps 4096 --checkpoint-every 512 --scenario-seed 10000000 --training-seed 11 --resume-from "$ck"
```

Bundles are exclusively installed after complete rollout/update boundaries and
contain model/optimizer, serialized vector environment, Python/NumPy/Torch/CUDA
RNG and checksummed settings. Only trusted locally generated pickle bundles may
be loaded. Settings/source/device/version mismatch or corruption fails closed.
Ctrl+C keeps the last complete bundle and invocation record, discarding the
in-progress rollout. An interruption before the first complete boundary may
have no resumable checkpoint; use a new run directory after inspection.
The supplied environment serialization test and all new code are **prepared,
not executed**. Full training-resume bitwise parity across processes/hardware
has not been measured; never claim it from a checksum alone.

## Re-verification and limits

The progress/interrupt/controller, manual test runner, sandbox, tests and explicit
dependencies change executable source fingerprints. Old regression evidence and
old plans must not be relabelled current. Required before the formal lock:
manual unit/focused review, one clean full Project I regression (all slow gates),
complete eligible Project03 fast regression, exact owner provenance activation,
new plan, clean source commit, exclusive lock and lock verification.

The validation cache repair changes only the cached identity: the previous code
overwrote its plan key with the last arm key and never hit the intended cache.
The same validation records and criteria are still checked before caching.
No scoring, candidate set, horizon, physics, approved numeric values, analytical
thresholds, PPO weights, Projects 01-03 or historical artifacts were changed.
Step 8 has not started and no scientific performance conclusion is added.


## Primary workflow update - 2026-10-20

The earlier separate-command recipe above is retained as history. For Step7 use
[the two-computer runbook](step7_remote_execution.md) and its ONE owner-started
foreground `Start-Step7Remote.ps1` command. Do not mix the older source-mutating
approval/lock commands with portable bundle execution. Separate unit/regression,
benchmark and sandbox-training CLIs remain available for deliberate manual use;
PPO training is never part of the Step7 pipeline. No unattended continuation is
restored. The coding agent has not run the prepared tests or campaign.
