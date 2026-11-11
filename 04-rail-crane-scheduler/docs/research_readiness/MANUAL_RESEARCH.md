# Foreground manual research sequence

Run commands from the repository root in Windows PowerShell. `Project04.ps1 Help`
lists every implemented action. No activation or PYTHONPATH is necessary. Every
long action runs in the foreground with real stderr tqdm and append-only JSONL
progress. Stdout remains JSON. No action automatically starts the next campaign.

## 0. One owner review, before any primary execution

Review SCIENTIFIC_PROPOSAL.md, NUMERICAL_PROVENANCE.json, primary_candidate_v1.json,
APPROVAL_PACKAGE.json and OWNER_REVIEW.md. Approval must explicitly cover O1-O6,
the exact profile digest, declared budgets and the named deterministic child-plan
derivation rule. Merely approving general direction does not authorize anything.

After an actual owner declaration of that exact text in this conversation, Codex
may record the matching receipt; it must not start a campaign. Alternatively the
owner can record their declaration locally using `RecordApproval -ApprovalText`
and `-OwnerEvidence` with the exact declaration returned by ValidateProfile and a
genuine owner decision reference. No owner receipt exists at delivery time.

The root receipt authorizes only exact child plans produced by the approved rule:
generation configs from the frozen recipe; training inputs from the committed
generation; evaluation inputs and models from committed generation plus the
declared validation-only selections. All child hashes are saved/displayed; the
same root receipt is rechecked, not copied into fictitious child approvals. Any
changed source/tool/config/env/budget/cohort/selection rule invalidates execution
and requires a new profile/review. Future input/model bytes are bound mechanically,
not guessed in advance or selected by held-out performance.

## 1. Verify environment/profile; prepare generation

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 ValidateEnvironment
.\04-rail-crane-scheduler\scripts\Project04.ps1 ValidateProfile
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareGeneration
```

Expect VERIFIED and CONFIGURATIONS_VALID_OWNER_APPROVAL_PENDING (the immutable
candidate itself keeps PROPOSED even after an external receipt). PrepareGeneration
prints the exact plan SHA-256 and receipt path, creates only a parameter plan,
and never calls primary random generation. Its 896 parameter configurations are
validated before owner review. The candidate stage JSON files are readable review
views; the root profile is the execution authority.

## 2. Generate primary synthetic inputs, only after exact owner approval

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 Generate
```

Expect PRIMARY_GENERATION_COMPLETE, 896 committed scenario cells and an immutable
manifest under the profile-specific ignored `experiments/research_v1_HASH/`.
Progress reports family, role, completed scenarios, rate/elapsed/ETA and rejection
counts. A validation failure or duplicate physical fingerprint stops; it is never
silently replaced. Generated origin is OWNER_APPROVED_SYNTHETIC only after the
real receipt/source/derivation checks. No scheduler or PPO is run here.

Ctrl+C preserves committed cells and logs; use this action explicitly:

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 ResumeGeneration
```

## 3. Verify cohorts, then validation baseline references

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 VerifyGeneration
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareBaselines
.\04-rail-crane-scheduler\scripts\Project04.ps1 Baselines
```

VerifyGeneration checks hashes, role/family/seed counts and disjoint physical
fingerprints. Baselines executes 640 validation cells, including explicit CP
ineligibility on larger families. This is VALIDATION_RESULTS, not held-out proof.
Every CP result records exact status/bound/model scope. A timeout is retained, not
called infeasible. Do not use this run to change the already frozen study without
a new reviewed amendment. Resume explicitly with `ResumeBaselines` if interrupted.

## 4. Prepare training and run only the first approved seed

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareTraining
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 1103
```

PrepareTraining binds only train/validation inputs, exact hashes, source and all
hyperparameters. Train checks the genuine root receipt, child derivation, exact
environment/device, minimum free RAM/disk and no-overwrite rules before learning.
Budget is 1,048,576 actual timesteps; tqdm uses SB3 callbacks, not episode counts.
It shows seed, actual device, updates, latest checkpoint and next validation.
At fixed optimizer boundaries it reports validation completion/failure/mean
quality, saves immutable model.zip+metadata/RNG and retains every candidate.

## 5. Inspect progress/checkpoint integrity and resume only safe boundaries

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 TrainingStatus
```

The status verifies model hashes and reports each seed's target, latest committed
checkpoint and complete-selection count. Inspect per-seed progress.jsonl and
validation metadata. A successful seed finishes its entire budget and writes a
validation-only selection.json. It never reads test inputs.

After Ctrl+C, resume explicitly into a fresh attempt directory:

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 ResumeTraining -Seed 1103
```

Only a complete optimizer-boundary directory with model/metadata/source/config/
dependency/seed hashes is eligible; `.partial` files are retained but ignored.
Resume preserves optimizer/RNG and earlier best validation selection, restarts
episodes under a deterministic resume namespace, and is not bitwise identical to
uninterrupted training. An interruption before the first checkpoint has no safe
resume state: preserve that attempt; review a fresh-attempt authorization/amendment
rather than deleting it or silently stitching a new trajectory. If the final
checkpoint exists but selection writing was interrupted, ResumeTraining finalizes
selection without further optimization. Actual optimization/resume throughput has
not been tested in this readiness task because optimizer updates were forbidden.

## 6. Run the remaining seeds, one deliberate command at a time

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 2207
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 3301
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 4409
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 5501
.\04-rail-crane-scheduler\scripts\Project04.ps1 TrainingStatus
```

These are separate manual actions, not an automatic multi-campaign launcher. All
five seeds must have a full-budget checkpoint and complete validation selection;
never omit a difficult or unfavorable seed. No checkpoint from Project 03 is valid.

## 7. Validate/freeze the validation-only selections

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 SelectModels
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareEvaluation
```

SelectModels independently checks selection ranking across retained checkpoints,
all five full budgets, model hashes and original training plans, then writes
immutable FROZEN_SELECTIONS.json. It does not optimize or evaluate test tasks.
PrepareEvaluation prints the exact child digest and binds all selected identities
and untouched test input hashes from the generation index. It cannot prepare
missing/untrained/partial/favorable-subset selections.

## 8. Execute the held-out campaign deliberately

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 Evaluate
```

Expect 2560 attempted cells, 256 independent scenarios, four heuristics, all five
PPO seeds and CP with explicit eligibility. This action is the first held-out
policy evaluation. It verifies owner/profile/source/selection/input/environment
locks before reading test task bytes. Failure cells remain committed; objectives
are null for incomplete/invalid schedules. Progress includes method, PPO seed,
family, scenarios/cells completed, elapsed/rate/ETA, failures and skipped cases.

Ctrl+C preserves committed result cells. Resume only with:

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 ResumeEvaluation
```

Completed cells are hash-verified and never overwritten. An interrupted in-flight
cell is re-executed; its wall timing can differ. Partial directories remain as
interruption evidence. No uncommitted partial result is counted as completed.

## 9. Verify, analyze and produce the scientific report

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 VerifyResults
.\04-rail-crane-scheduler\scripts\Project04.ps1 GenerateReport
.\04-rail-crane-scheduler\scripts\Project04.ps1 Status
```

VerifyResults checks exact cell coverage/identities, frozen checkpoint hashes,
physical schedules and recomputed metrics. GenerateReport reads only verified
recorded cells and executes the prespecified stratified bootstrap with tqdm;
exports analysis.json, all cells CSV, adjusted-effect and failure figures, finite
CP gaps, a human report and file/hash manifest. Exports are immutable; a repeated
GenerateReport refuses overwrite. It does not manufacture empty charts or infer
success from software tests. SCIENTIFIC_CLOSURE_NOT_COMPLETE remains until final
evidence/claims/interoperability review, even if execution and statistics finish.

Project I's live rail/bay/cargo API and empirical data remain DATA_GAP; this study
does not run or modify that terminal, implement Project 05, or train joint BAP+QCSP.
