# Project04 manual PowerShell runbook

**Historical implementation-stage runbook.** Its missing-dependency observations
describe the earlier development run. The unified environment is now installed
and OR-Tools fixture integration is verified. Use the current
[manual research sequence](research_readiness/MANUAL_RESEARCH.md),
[environment setup](research_readiness/ENVIRONMENT_SETUP.md) and
[exact owner review](research_readiness/OWNER_REVIEW.md). The material below is
retained for provenance; fixture parameters still do not authorize primary runs.

Long training, held-out evaluation and primary generation **were not run**.
The commands below are prepared interfaces, not authorization or evidence.
First review OWNER_DECISIONS.md and approve exact profiles/cohorts/budgets.
No runtime estimate is asserted. CPU/GPU, seeds, timesteps, memory and CP node/time
limits must be sized explicitly for the selected machine and recorded environment.

## Safe checks and fixture replay

From repository root using the inspected existing Python (no install needed):

```powershell
$env:PYTHONPATH = (Resolve-Path .\04-rail-crane-scheduler\src).Path
python -B -m rail_crane_scheduler training --mode check
python -B -m rail_crane_scheduler solver --mode check
python -B -m rail_crane_scheduler generator --mode validate --config .\04-rail-crane-scheduler\tests\fixtures\generator_config.json
python -B -m rail_crane_scheduler benchmark --mode validate --problem .\04-rail-crane-scheduler\tests\fixtures\problem.json
python -B -m rail_crane_scheduler evaluation --mode status
python -B 04-rail-crane-scheduler/scripts/check_stage.py 14
```

Stage14 runs only Project04 fixtures with a 180-second process limit. It does not
train or read held-out datasets; one OR-Tools test is dependency-skipped until
installed. Test attempts/JUnit/stdout/source hashes are preserved; reruns append
new attempts. Managed Windows test temp cleanup warnings are retained in receipts.

Create a new fixture run directory (existing paths refuse overwrite), then upload
its problem.json and policy JSON files in the read-only Streamlit app:

```powershell
python -B -m rail_crane_scheduler benchmark --mode run-development-small --problem .\04-rail-crane-scheduler\tests\fixtures\problem.json --output .\04-rail-crane-scheduler\experiments\my_fixture_review
python -m streamlit run .\04-rail-crane-scheduler\frontend\replay_app.py
```

All tests/fixtures numbers are TEST_FIXTURE_SYNTHETIC; never promote their
training_plan_fixture.json or geometry/rates to primary defaults by convenience.

## OR-Tools dependency verification — owner action only

OR-Tools is missing. Do not modify the shared legacy numerical environment.
A proposed separate solver fixture environment can be prepared manually:

```powershell
Set-Location .\04-rail-crane-scheduler
python -m venv .venv-cpsat
.\.venv-cpsat\Scripts\python.exe -m pip install -e ".[test,solver]"
.\.venv-cpsat\Scripts\python.exe scripts\check_stage.py 6
.\.venv-cpsat\Scripts\python.exe -m pip freeze
```

The compatibility range ortools>=9.11,<10 is proposed, not a verified pin. Record
the actual resolved version/dependencies and pass the real Step06 test before
accepting that environment. A unified CP+PPO research environment needs its own
reviewed compatible lock; success in an isolated solver env does not prove that.
No install above was executed by Codex.

## Plans and owner receipt format

Plans are canonical JSON payloads tied to all Project04 src SHA256 values.
Planning without --output is read-only. An explicit --output writes an exclusive
new candidate plan. The JSON response includes plan_hash and no invented duration.
Any source/config/input change requires a new review/approval, not bypassing hashes.

Owner receipt format, created **only after actual separate authorization**:

```json
{
  "status": "OWNER_APPROVED",
  "approved_payload_sha256": "EXACT_CANONICAL_PLAN_SHA256",
  "owner_evidence": "ACTUAL_OWNER_DECISION_REFERENCE_AND_SCOPE"
}
```

No such receipt was created by development. A candidate status or source metadata
is not approval. manual-confirm must match the approved digest exactly. O1–O6
choices and numerical values must be present in the reviewed payload/source
contract; an approval of high-level direction alone is insufficient.

## Primary input generation — manual, currently PARAMETERS_PENDING

Prepare an explicit draft payload with `configs`: a list of GeneratorConfig
dictionaries from the typed schema. Include every numeric geometry/rate/setup/
clearance/horizon/tolerance, operation kind, move range, nonces, seed/namespace,
family and role. Use PROPOSED_SYNTHETIC provenance, not empirical or fixture tags.
Review split counts/ranges before generation. Nothing chooses these values for you.

```powershell
$p04GenerationReview = python -B -m rail_crane_scheduler generator --mode plan-manual --config .\04-rail-crane-scheduler\experiments\generation_draft.json --output .\04-rail-crane-scheduler\experiments\generation_plan.json | ConvertFrom-Json
# Only after separate approval of that exact digest:
python -B -m rail_crane_scheduler generator --mode generate-manual --config .\04-rail-crane-scheduler\experiments\generation_plan.json --approval .\04-rail-crane-scheduler\experiments\generation_owner_receipt.json --manual-confirm $p04GenerationReview.plan_hash --output .\04-rail-crane-scheduler\experiments\primary_inputs_v1
```

Generation is deterministic and immutable; duplicate physical inputs across roles
reject. There is no scheduling or training in this command. Inspect its manifest;
use exact problem_hash values and Project04-relative paths in later plans.

## Multi-seed training and validation-only selection — NOT_RUN

Create training_draft.json with `training_config` (all TrainingConfig fields),
`train_inputs` and `validation_inputs` arrays of `{path, problem_hash}`. Explicit
multiple seeds, task capacity, bounds, network, optimizer settings and device are
required. No test list belongs in this training payload. Set gamma=1 for the
supported elapsed-time reward. No implicit CUDA/CPU fallback is permitted.

```powershell
$p04TrainingReview = python -B -m rail_crane_scheduler training --mode plan --config .\04-rail-crane-scheduler\experiments\training_draft.json --output .\04-rail-crane-scheduler\experiments\training_plan.json | ConvertFrom-Json
# Only after separate profile/budget/execution approval:
python -B -m rail_crane_scheduler training --mode train --config .\04-rail-crane-scheduler\experiments\training_plan.json --approval .\04-rail-crane-scheduler\experiments\training_owner_receipt.json --manual-confirm $p04TrainingReview.plan_hash --output .\04-rail-crane-scheduler\experiments\crane_training_v1
python -B -m rail_crane_scheduler training --mode status --existing .\04-rail-crane-scheduler\experiments\crane_training_v1
```

Training is foreground-only. JSON progress is emitted at validation boundaries;
immutable model.zip/metadata.json checkpoints and validation selection receipts
are per seed. These record config/source/model/dependency/interface hashes, actual
device, RNG and training steps. Selection prioritizes failure rate, then valid
makespan, then earlier step, using only validation. All seeds/failures remain.

Interrupt with Ctrl+C; use only the last complete optimizer-boundary checkpoint.
Resume one predeclared seed into a **new** run directory, preserving the old run:

```powershell
python -B -m rail_crane_scheduler training --mode resume --config .\04-rail-crane-scheduler\experiments\training_plan.json --approval .\04-rail-crane-scheduler\experiments\training_owner_receipt.json --manual-confirm $p04TrainingReview.plan_hash --resume-checkpoint .\04-rail-crane-scheduler\experiments\crane_training_v1\seed_11\checkpoint_REPLACE_WITH_ACTUAL_STEP --seed 11 --output .\04-rail-crane-scheduler\experiments\crane_training_resume_v1
```

The seed/step above is illustrative; use an actual predeclared seed and actual
checkpoint path. Resume preserves optimizer/RNG but restarts episodes, so it is
not bitwise uninterrupted training. Do not stitch unrelated seeds/configurations.
No optimization/interrupt/resume campaign was executed in development.

## Held-out evaluation and existing-record reports — NOT_RUN

Prepare evaluation_draft.json with identical `training_config`, all seed selection
receipts `{path,sha256}`, untouched `test_inputs` `{path,problem_hash}`, optional
`cp_reference` explicit tick/time/node budget (or null), and `analysis` fields:
`reference_policy`, `draws`, `bootstrap_seed`, `confidence`, `min_scenarios`.
The plan lists metadata/hashes without reading test problems for tuning.

```powershell
$p04EvaluationReview = python -B -m rail_crane_scheduler evaluation --mode prepare-test-manifest --config .\04-rail-crane-scheduler\experiments\evaluation_draft.json --output .\04-rail-crane-scheduler\experiments\evaluation_plan.json | ConvertFrom-Json
# Only after selection, protocol and separate evaluation approval:
python -B -m rail_crane_scheduler evaluation --mode evaluate --config .\04-rail-crane-scheduler\experiments\evaluation_plan.json --approval .\04-rail-crane-scheduler\experiments\evaluation_owner_receipt.json --manual-confirm $p04EvaluationReview.plan_hash --output .\04-rail-crane-scheduler\experiments\heldout_v1
```

Use the same command plus --resume for the same output directory. It verifies the
original plan and committed cell hashes; it never overwrites immutable cells.
Partial directories/failures are retained. Wrong selection/source/checkpoint/input
hash, missing seed, split overlap or absent approval fails closed.

```powershell
python -B -m rail_crane_scheduler evaluation --mode verify --existing .\04-rail-crane-scheduler\experiments\heldout_v1
python -B -m rail_crane_scheduler evaluation --mode analyze-existing --existing .\04-rail-crane-scheduler\experiments\heldout_v1
python -B -m rail_crane_scheduler evaluation --mode render-existing --existing .\04-rail-crane-scheduler\experiments\heldout_v1 --output .\04-rail-crane-scheduler\experiments\heldout_report_v1.md
python -B -m rail_crane_scheduler evaluation --mode render-plots --existing .\04-rail-crane-scheduler\experiments\heldout_v1 --output .\04-rail-crane-scheduler\experiments\heldout_figures_v1
```

These commands do not train. Scientific closure still requires verified complete
cohorts, approved inference/multiplicity, model/physical matching and claim audit.
CP OPTIMAL is finite-subclass-only; dependency/FEASIBLE/timeout cannot become a
global optimum. No calibrated data, native Project I execution or joint RL exists.

## Final-review commit plan

No automatic commit/push. First review the root ignore rule and intentionally
allow Project04 source; leave experiments, models, caches and environments ignored.
Then stage only reviewed README/pyproject/local ignore/src/tests/frontend/scripts/
configs/docs files, inspect `git diff --cached --stat`, and make one source/docs
commit such as `feat: add Project 04 fixture-tested QCSP research tooling`.
Do not force-add the entire directory or include local model binaries/results.
