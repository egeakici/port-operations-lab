# Step 7 pre-lock repair and single-command execution - 2026-10-21

Subsequent actual remote evidence and the current v2 launcher procedure are in
[the2026-10-22 Project03 scope repair](step7_project03_scope_repair_20261022.md).
The four prerequisites and554/554 full Project I tests passed remotely; a separate
Project03 archive-consumer classification error blocked the old v1 session.

Owner evidence: campaign_final_v3 / project-i-full_90ca488c6ca7 completed545
tests:541 passed,4 failed,0 errors/skips/deselections, all9 slow gates passed.
The owner supplied the actual failure tracebacks on2026-10-21. This is failed
pre-lock verification, not scientific campaign evidence and never a clean PASS.

## Demonstrated failures and scope

Three failures in test_step4_closure.py consume the original development batch's
manifest.json.sha256. The first transport included scenario_index.csv and12
selected scenarios but omitted this sidecar. The repair packages all original
small batch metadata, including the manifest and checksum. It neither regenerates
scenarios nor changes test expectations. Original transport v1 remains immutable;
v2 includes every original member with the same checksum and additional metadata.

The fourth failure is historical A1 exact-trace reproduction in
test_pre_step6_profile.py. Expected combined SHA:
340ad5e454f89bf8ea9c636803f5e5d1986d8a648157335b54f4f4a03d27ec77.
Remote actual:1708970a95122fbd67bedbd8715a386c136cdfb6181f7f1ca2e15f78ab452bd7.
The old traceback did not identify the differing canonical stream, so a specific
numeric field is NOT claimed as proven root cause.

A material numerical-environment discrepancy is established from actual records:

| Component | Historical Step5 smoke / approved F3 | Failed remote run |
| --- | --- | --- |
| CPython | 3.13.2 | 3.11 |
| NumPy | 2.2.3 | 2.4.6 |
| Torch | 2.6.0 | 2.14.1+cpu |
| Gymnasium | 1.2.3 | 1.2.3 |
| stable-baselines3 / sb3-contrib | 2.8.0 /2.8.0 | 2.8.0 /2.8.0 |

The prior launcher accepted Python3.11+ and installed unconstrained numeric
libraries; that did not reproduce the recorded environment. The repair binds
the actual reference versions in step7_cpu_environment_v1.json and constraints.
This preserves exact comparison instead of retuning algorithms or replacing
historical hashes. Python numerical behavior can differ across releases; Python
3.12 changed float summation ([official release notes](https://docs.python.org/3.12/whatsnew/3.12.html)).
That is a supported mechanism, not a completed replay proof for this case.

The original A1/A3 strict trace assertion remains unchanged. Its diagnostic now
lists every differing stream and the reference/current KPI fields on failure.
All four originally failing tests are a mandatory first stage BEFORE the workflow
smoke/full regressions. The owner's new machine run must demonstrate exact repair;
no local runtime PASS or guaranteed completion is invented by code preparation.

## One foreground command

After the owner reviews, commits and pushes these Project I changes, on HP paste:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'C:\Users\HP\Desktop\port-operations-lab'
    git pull --ff-only origin main
    if ($LASTEXITCODE) { throw 'Git pull failed; no experiment started.' }
    powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Complete-Step7.ps1
}
```

The launcher downloads the PSF standalone Python3.13.2 x64 NuGet archive only if
absent, verifies its pinned SHA512 and size, then extracts it to a fresh staging
directory. It checks the interpreter version, architecture, standard GIL build
and venv/ensurepip imports before promoting that directory into place. It creates
.venv/step7-cpu3132 without using the Windows installer or modifying PATH.
Original .venv/Python3.11 and GPU benchmark environments are retained. Numeric
versions are pinned; no environment update is made once a session exists.
Initial setup may need network access. No driver or CUDA installation is needed.

### Subsequent bootstrap failure and repair

The owner subsequently supplied a new pre-session failure: the full Windows
installer returned without a reported nonzero exit, but the requested
.venv/step7-bootstrap/python3132/python.exe was absent. The launcher attempted
that nonexistent executable. This was a launcher postcondition defect, not a
scientific episode failure. The exact installer-internal reason is not known
from the supplied output; existing-install maintenance behavior is a possible
explanation, not an established diagnosis.

The corrected launcher no longer invokes that installer. It uses the
[PSF build-system package documented by Python](https://docs.python.org/3.13/using/windows.html#the-nuget-org-packages),
with explicit version3.13.2 (standard x64, not free-threaded or embeddable).
The14,297,314-byte archive's SHA512 was checked against NuGet's official catalog.
Static archive inspection confirmed python.exe, python313.dll, venv, ensurepip
and the bundled pip wheel are present. Both core binaries are byte-identical
to this development computer's existing historical Python3.13.2 installation:

| Binary | SHA256 (archive and existing historical installation) |
| --- | --- |
| python.exe | 7d96a4ed35d6e596cd9dd8933feafc66349cc21f75be3b15c89fd336e50140c1 |
| python313.dll | bf68cf819a1e865170430c10e91c18b427aef88db1da1742020443864aa2b749 |

New bootstrap specification: configs/protocol/step7_python_bootstrap_v1.json.
Final runtime directory: .venv/step7-bootstrap/cpython3132-nuget/tools/.
An interruption leaves a uniquely named staging/download file; a retry uses a
fresh stage and never overwrites prior files. No Python binary is executed before
the archive's integrity and required members are checked. Runtime binary hashes
and the specification hash are retained in the bundle's bootstrap receipt.
The old installer, old installation directory and setup transcripts are preserved.
The same run name remains appropriate because the supplied failure preceded
session creation. Existing scientific-session and FAILED.json guards remain.

Prepared owner-run bootstrap tests cover a same-size corrupt archive, path
traversal, valid extraction into a path with spaces, and refusal to overwrite an
existing destination. They are included in the workflow regression gate. The
coding agent performed static checks only, including read-only archive/core
binary hashing; no new Python runtime, test or scientific work was executed.
The changed launcher/tests need fresh matching regressions before the lock.

Default stable result folder:
experiments/step7_remote/step7_cpu3132_v1/. Use the SAME command to resume; no
arbitrary new run name is chosen each time. Prior failed campaign_final_v3 logs
are retained and linked inside the new bundle. Source/dependency mismatch, genuine
failure, partial scientific starts and existing lock deviations still fail closed.
The launcher never commits, deletes evidence, retrains PPO or substitutes policies.

Stages: four repaired prerequisite tests; bounded workflow tests; development-only
hardware check; clean full Project I including9 slow gates; eligible Project03
fast; matching evidence; actual existing owner approval; historical readiness;
exclusive lock;560 validation rows;1400 test rows; descriptive reporting; detailed
diagnostics; final summary/manifest. All actual counts come from the controller.
Source hashes are new, so old regressions/locks cannot authorize this snapshot.

Each failed regression prints full JUnit tracebacks, not only exit1. All errors
also have a content-addressed text receipt under support/. No failed test is
skipped, relaxed, automatically retried or relabelled passing. The command proceeds
through all stages only when the scientific prerequisites actually pass.

## Return the result folder

After READY_TO_COPY and zero exit, copy the entire step7_cpu3132_v1 folder to the
same relative location on the development computer. Do not merge different runs.
No virtual environment or CUDA package needs copying. It includes source, inputs,
models, original-owner provenance, regressions, lock/plan, every row/trace,
WAIT/cargo-pivotal/rollover/forecast diagnostics, compute/profiles, descriptive
presentation and transfer manifest. Return audit evaluates no policies:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Complete-Step7.ps1 -Action VerifyReturn
```

Scientific status remains NOT_EXECUTED_ON_DEVELOPMENT_COMPUTER. No validation/test,
training, regression or test was executed by the coding agent. Static syntax,
artifact packaging and read-only preservation checks are separate from PASS.
Step8 is not started; frozen values, QC8, original Project03 A2, checkpoints and
all policy/physics scoring remain unchanged.
