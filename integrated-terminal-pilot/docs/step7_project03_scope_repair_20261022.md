# Step 7 pre-lock Project03 regression eligibility repair - 2026-10-22

## Actual owner evidence

The owner supplied the complete remote failure output from step7_cpu3132_v1:

| Gate | Actual outcome |
| --- | --- |
| Reference environment | PASS: Python3.13.2, NumPy2.2.3, Torch2.6.0+cpu, Gymnasium1.2.3, SB3/contrib2.8.0 |
| Previously failing prerequisites | 4 passed, 0 failed/errors/skipped |
| Project I complete regression | 554 passed, 0 failed/errors/skipped/deselected, all9 slow gates; 1954.8593901 seconds |
| Project03 attempted fast scope | 426 collected,420 passed,6 failed,0 errors/skipped,16 deselected;15.5809886 seconds |
| Scientific campaign | Not started; failure at project03-fast, before approval recording and formal lock |

The earlier Python bootstrap and four regression defects were repaired, as the
actual remote results demonstrate. This new failure has a separate demonstrated
cause: two historical-result consumers were incorrectly included in the pre-lock
fast scope. This was a Step7 runner classification omission.

Five failing cases in tests/integration/test_replay_records.py call load_catalog
against the real Project03 root. The source opens the old Step12A held-out catalog
and selected archived test results. Its manifest is absent on HP, so loading stops.
One case in test_replay_frontend.py starts the actual replay UI backed by that
same catalog. The app handles the missing archive; the test then cannot find its
expected Scenario family widget and raises StopIteration. Both are archive
dependencies. This is not six scientific-policy failures, nor six missing pip
dependencies, nor a reason to copy held-out archives to the remote computer.

## Corrected authorized regression scope

The original prompt requires the complete **eligible** fast Project03 suite with
no learning or forbidden held-out actions. The runner now ignores both archive
consumer modules before collection, documenting why. The four already excluded
training/archive modules and existing exclusions within three mixed modules remain.
No Project03 test, application, policy, expected assertion or archive was modified.
Synthetic unit replay tests remain included. No missing-input skip, xfail, fake
manifest, replacement result, changed scenario or policy substitution is added.

step7_regression_scope.py classifies all44 current Project03 test modules:
35 fully eligible modules,3 mixed modules,6 ineligible modules. A source-only audit
blocks unclassified/missing modules or stale mixed-node exclusions before test
collection. The audit hashes test source only, never archived results. The exact
eligibility receipt is bound into the fast regression result and checked again by
the scientific lock gate; excluded coverage is never described as a full unscoped
Project03 pass.

The fast Project03 gate now precedes the long Project I gate. New owner-run tests
cover archive-consumer isolation, retention of synthetic replay, unknown-module
and stale-node rejection, scope receipt tampering, preserved prior failure and
rejection of a predecessor that already reached a scientific lock.

## Preservation and one foreground command

The current Complete-Step7.ps1 default is **step7_cpu3132_v2**. The old v1 session
has a FAILED marker and a different source snapshot, so it cannot be resumed as
if the source were unchanged. It is retained intact. The successor links the old
source snapshot, environment, pipeline/regression evidence and actual failures
inside prelock_repair. For the v1 predecessor, the transition is accepted only
when sealed results match the reviewed6 failures (420/426, one frontend case and
five records cases). A different failure or existing scientific lock blocks the
transition. This is a specific reviewed pre-lock repair, not automatic retry of
arbitrary failed experiments.

The existing exact CPU environment is reused, without reinstalling dependencies.
Changing the executable verification code changes the protected source digest,
so the archived554/554 result remains valid evidence for its old snapshot but
cannot authorize the new lock. The new snapshot requires one complete mandatory
Project I regression and the corrected complete eligible fast gate. Step6 F3 is
not repeated. The1960-run scientific inventory, approvals, parameters, algorithms,
checkpoints, physics, full-cohort rule and validation/test ordering are unchanged.

After the owner commits/pushes the Project I changes, on HP use the same command:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'C:\Users\HP\Desktop\port-operations-lab'
    git pull --ff-only origin main
    if ($LASTEXITCODE) { throw 'Pull failed; execution not started.' }
    powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Complete-Step7.ps1
    if ($LASTEXITCODE) { throw 'Stopped; preserve the bundle and diagnostic logs.' }
}
```

The successor result folder is experiments/step7_remote/step7_cpu3132_v2/.
Use that same command to resume. Do not delete the v1 FAILED marker or merge v1/v2
result files. Completion is READY_TO_COPY with the sealed transfer manifest;
copy the entire v2 directory back for independent audit and owner review.

No failure-free execution guarantee or48-hour completion guarantee is made.
Healthy foreground episodes are preserved; real scientific/integrity failures
must stop admission and retain evidence. The coding agent performs static source
checks only, with no local regression, simulation, training or held-out access.
