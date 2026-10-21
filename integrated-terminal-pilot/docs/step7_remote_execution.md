# Step 7: development computer, remote execution computer, returned evidence

**Current launcher (2026-10-21):** use `scripts/Complete-Step7.ps1` as specified in
[the demonstrated pre-lock repair](step7_prelock_repair_20261021.md). It installs
the recorded Python3.13.2/numeric reference environment and supplies the missing
historical manifest metadata. The generic Python3.11+ setup and transport v1
instructions below are preserved as history; use the corrected launcher for new
execution. Its stable return folder is `step7_cpu3132_v1`.

Owner workflow instruction: 2026-10-20. This is the primary Step 7 execution
procedure. Code is prepared on the development laptop. The owner pushes it,
pulls on the stationary computer, and explicitly starts ONE foreground command.
The coding agent never launches the campaign. There is no scheduler, detached
job, background continuation, automatic Git commit or push.

## On this development computer

Only code, bounded test definitions, static checks and prerequisite packaging
are prepared. No regression, model training, policy evaluation or new scientific
scenario is executed. The supplied tests are NOT reported as passing.

`assets/step7_remote_inputs.zip` and the sealed
`configs/protocol/step7_remote_inputs.json` transport inputs that Git normally
ignores: the six exact frozen Project03 checkpoints/sidecars, their selection
record, the existing owner reply/context, historical Step4/5/F3 receipts and the
stored DEVELOPMENT fixtures required by the complete regression. No validation
or test scenario is pre-generated. The archive is additive: originals are never
modified. Include both the asset and manifest when committing/pushing Project I.
The original first Step2 batch is also included for its complete immutable
manifest regression. The prepared transport archive is approximately16.6 MiB;
it contains existing inputs only, with member checksums and an archive checksum.

The historical F3 raw outer files remain on this laptop. The remote machine
validates the transported, previously verified readiness receipt against the
original report/index and known hashes. It does not claim to rehash absent F3
raw files or re-run Step6. Frozen source text comparison permits CRLF/LF-only
checkout differences; every execution source's actual bytes are then snapshotted
and locked. The new `.gitattributes` preserves sealed transport/packet bytes.

After reviewing the diff, the owner can stage this Project I work and commit/push
normally. The root owner-prompt file is not needed by the runtime. Do not add
ignored result folders to Git. No source commit is made by a Python CLI.

## On the stationary computer: one command

Install Python 3.11+ and Git. Clone/pull the committed repository including the
transport asset. From the repository root:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Start-Step7Remote.ps1
```

The script creates the repository `.venv` if necessary and installs the four
local projects, Project03 RL/dev/viz dependencies and Project I dev dependencies
before the FIRST session. Internet is needed for initial Python packages, not
for scenario seeds. On resume it does not reinstall/update the recorded session
environment. `-SkipInstall` is available for an already prepared environment.
CUDA drivers/builds are not silently installed or selected. The short device
diagnostic explicitly records CUDA unavailability instead of pretending to use
it. CPU/CUDA action differences do not change the scientific device.

The manually started process sequences these stages, with stage and work-level
tqdm elapsed/ETA/throughput/device displays:

1. Verify/restore authentic prerequisite files, refusing conflicting existing
   artifacts. Retain all prerequisites inside the result bundle as well.
2. Save clean source revision, actual source bytes, package/hardware provenance
   and `pip freeze`; perform the small DEVELOPMENT-only CPU/CUDA diagnostic.
3. Run one full Project I regression, including all nine slow gates and the new
   unit tests. Then run the complete eligible Project03 fast scope with the
   existing documented training/held-out exclusions. Missing-dependency/fixture
   skips cannot satisfy the gate. Full raw logs, JUnit, node events, commands,
   durations and exit codes remain available.
4. Assemble matching regression evidence. Record the owner's ALREADY GIVEN
   approval of the exact 28 values in a copied register, with verbatim message,
   date, source and option context. No new owner signature is requested.
5. Verify historical receipts, Q6/controls, checkpoint hashes, primary roles,
   exact plan and dependencies. Create the actual exclusive protocol lock.
6. Execute all 560 validation episodes. Only after the existing validation
   gate passes, execute all 1400 test episodes. Each split uses its own unique
   CPU profile and pre-invocation row inventory.
7. Verify and export descriptive group/episode/vessel tables, nested A3 and
   reference S1 contrasts, WAIT/cargo/rollover/forecast diagnostics, resource
   and profiling measurements. No Step8 bootstrap, significance or NI verdict.
8. Hash the complete scientific return folder and install its transfer manifest.
   Successful completion prints `READY_TO_COPY` and exits zero.

The exact plan is unchanged: 20 validation and 50 test scenarios per primary
family Medium/Heavy; 1260 integrated plus 700 Project03-reference episodes;
A1/A1n/B1/A2/B2/B2-T/A3(11,23,37), with true A1/A2/A3 reference evaluations.
Low/Bottleneck remain diagnostic, B3 unimplemented, 13M/Step8 inaccessible.
QC8, max2 cranes/vessel, assigned efficiency, common P_c/P_y, D15/D17/R5,
D24, cargo obligations, K5-A/all legal candidates+WAIT and the400000-cycle guard
are unchanged. Two-second warnings never prune. There is no admission deadline.

**The scientific campaign remains CPU inference, one serial outer worker.** A
GPU does not run the Python event simulator or integrated inner rollouts. The
stationary machine's uptime and CPU performance are the relevant benefits.
No PPO retraining is needed or performed. The optional sandbox training command
is separate and cannot replace a Step7 checkpoint.

## Clean source and real approvals without runtime commits

All generated execution state lives under:

```text
integrated-terminal-pilot/experiments/step7_remote/campaign_v1/
```

The portable source-defined lock is `protocol_lock_v1.json` + `.json.sha256`
inside this bundle. It binds the clean owner-committed source revision and byte
map, approved copied register, actual owner provenance, numeric parameter
fingerprint, full regression evidence, readiness proof, checkpoint hashes,
dependencies, exact plan and analysis contract. It is created only after all
prerequisites, before any 11M/12M generation. No authorization boolean bypasses
it. The canonical Step2 register stays at its historical intake state, allowing
the mandatory legacy tests to remain meaningful. The effective Step7 register
has all52 FROZEN records, validated with the original schema and exact approved
values; its checksum is part of the lock. Legacy Step1-6 readiness labels are
historical, not authorization for this distinct controller.

This location/approval overlay is the operational portability change authorized
by the owner's 2026-10-20 instruction. It does not relax clean-tree checks,
scientific approvals, source drift, integrity, physical rules or split gates.
The source checkout and original policies/parameters remain unchanged during
execution. Never mix this portable mode with the older source-mutating manual
approval/lock recipe.

## Interruptions, failures and progress

Keep the same terminal open. First Ctrl+C requests a sealed episode-boundary
stop; a second forces interruption and can leave a partial scientific episode.
To continue, execute the SAME foreground command again. Successful regression
results and completed episodes are verified/skipped. An interrupted complete
regression session without a result needs a fresh complete regression invocation;
its original logs are retained. No duplicate worker is admitted while a live
worker/suite still owns its lock. Only demonstrably stale ownership is archived.

Failed regressions/episodes, changed source/dependencies, partial approvals,
corruption, validation-gate failures or partial scientific episode starts stop
the process with `BLOCKED_PRESERVED`. They are not auto-retried, replaced with
FCFS or silently omitted. Preserve that folder and bring its logs back for
inspection. Do not delete markers or edit a locked policy to continue. Post-lock
defects require an explicit documented scientific deviation/review.

Optional status query (does not run tests or experiments):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Start-Step7Remote.ps1 -Action Status
```

`-RunName another_label` selects an explicit different bundle. Changing the name
must never select favorable seeds or discard a failed scientific attempt. Keep
the SAME run-folder name when copying back; recorded relative paths depend on it.

## Copy the results back

Wait for zero exit status, `READY_TO_COPY`, and a sealed `transfer_manifest.json`.
Then copy the ENTIRE `campaign_v1` directory into the SAME relative parent on
the development computer:

```text
port-operations-lab/integrated-terminal-pilot/experiments/step7_remote/campaign_v1
```

Do not copy a live/partial folder, merge different campaigns or rename a completed
bundle. Preserve an already-existing destination before replacing anything. No
`.venv` or historical F3 raw files need copying. Temporary pytest working trees
live outside the bundle under `experiments/step7_remote_work/` and are not part
of the scientific return. Do not delete existing historical evidence.

On the development computer the owner, or the coding agent when explicitly
asked to close Step7, can perform AUDIT-ONLY verification:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Start-Step7Remote.ps1 -Action VerifyReturn
```

This checks copied files, archived source, owner approval, regression/JUnit/raw
logs, lock/plan, scenario pairing, N_out/T_end, all compressed trace hashes and
row coverage. It never loads a model, deserializes a policy pickle or evaluates
a policy. It does not require the laptop's CUDA/software versions to equal the
execution machine's; the recorded execution environment is retained. Differences
in source CONTENT fail; CRLF/LF-only differences are explicitly reported. The
result is `VERIFIED_RETURN_AUDIT_ONLY`, not a new scientific execution permission.

After that verification, the final owner-facing closure can cite the actual
results. No full-completion claim is made before the copied evidence passes.

## Returned scientific evidence

```text
campaign_v1/
  session.json + source_snapshot/ + requirements_execution.txt
  inputs/              # approval history/register, all authentic prerequisites
  regressions/         # commands, raw logs, events, JUnit, sealed results
  regression_evidence/ # source-matching combined evidence
  readiness_manifest.json + protocol_lock_v1.json + .json.sha256
  <plan_sha12>/
    plan.json + scenarios/ + pairing/
    runs/              # every row, end modes, G blocks/failures, CPU/wall/RSS
    traces/            # all seven canonical streams, lossless gzip + SHA
    observations/      # exact sanitized policy-input archives, never fed outcomes
    diagnostics/       # per-decision WAIT/pivotal/forecast and per-container losses
    reports/           # JSON, Markdown, CSV, reference S1/nested A3/vessel tables
  profiles/            # unique invocation profiles, newly executed row IDs, counts
  pipeline/            # immutable stage receipts/state history and console logs
  hardware/            # actual bounded CPU/CUDA diagnostic, including unavailability
  pipeline_status.json # replaceable convenience pointer
  final_summary.json   # exact protocol fields and owner-review status
  presentation_evidence.md # paired directional cargo/turnaround findings
  compute_summary.json # episode/report costs, profiling coverage and warnings
  transfer_manifest.json + checksum sidecar
  return_verification/ # later audit-only receipts
```

Exact input pickles are trusted local artifacts for remote reporting only; never
load third-party pickles. Cargo diagnostic causes remain UNKNOWN/multiple where
the ledger cannot identify a unique cause. WAIT coexistence is not causality.
Forecast errors retain `UNCALIBRATED_SYNTHETIC_FORECAST`. Per-decision pivotal
counts are labelled separately from unique-input counts. Sampled RSS is not peak
RSS. Actual physical-inner-event counts come from profiler calls minus new outer
event lines, not inferred cycle totals; interrupted invocations without profiles
remain explicitly missing. Reporter reconstruction costs are separate.

New source and reporting changes invalidate earlier snapshot regressions/plans.
All runtime verification is delegated to the owner-started remote pipeline.
No test/campaign outcome, speed claim or training-resume parity is invented here.
