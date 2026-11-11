# Project 04 research readiness completion report

2026-11-11, Europe/Istanbul. **ENGINEERING_READY; OWNER_APPROVAL_PENDING.**

112 tests passed, zero failures/errors/skips; 17 CLI checks passed. OR-Tools is installed and the genuine small CP-SAT fixture is OPTIMAL with objective/bound 5 min and independent physical validation. This is a fixture certificate for the finite model only.

No primary synthetic campaign, PPO optimizer update or held-out scientific episode was executed. No owner receipt, stage, commit or push was created. Full scientific closure remains incomplete.

## A. Environment and dependencies

One isolated environment: `.venv-research`, CPython 3.13.2 Windows AMD64. PyTorch runtime 2.6.0+cpu; explicit CPU, torch 2 threads, one vector environment. Intel Iris Xe detected, no available CUDA device/build; no silent fallback. Real CPU tensor, SciPy linear solve, pandas/NumPy compatibility, genuine solver, untrained candidate-policy inference and reload passed.

| Capability package | Exact version |
| --- | --- |
| numpy | 2.2.3 |
| scipy | 1.15.2 |
| pandas | 2.3.3 |
| pytest | 9.1.1 |
| tqdm | 4.67.1 |
| gymnasium | 1.2.3 |
| stable-baselines3 | 2.8.0 |
| sb3-contrib | 2.8.0 |
| torch | 2.6.0 |
| ortools | 9.12.4544 |
| matplotlib | 3.10.1 |
| streamlit | 1.61.1 |
| psutil | 7.2.2 |

All **70 distributions**, including transitive packages/pip/local package, are listed in [INSTALLED_PACKAGES.md](INSTALLED_PACKAGES.md) and the exact environment lock. The 68 dependency-wheel SHA-256 values and actual install reports are retained. `pip check` reports no broken requirements. See [environment setup](ENVIRONMENT_SETUP.md).

Initial sandbox ensurepip temporary-directory failures were resolved with authorized isolated setup execution, without changing shared environments. Matplotlib/Pyparsing deprecation warnings remain (14); final tests returned zero and no broad upgrade was made merely to silence warnings.

## B. One exact scientific owner review

Canonical proposed profile SHA-256: `d06b10d8e04fd0d3655c22267a4ed6cb48b9caa745fec12ac71a8a7bb19dddbc`.

| Choice | Concrete recommendation |
| --- | --- |
| O1 | Global x meters, rail [0,360], hull origin36/length288, two orientations; reference-point d24 m /heavy36, epsilon_t1e-8 min, epsilon_x1e-6 m. Body geometry excluded. |
| O2 | Existing two-crane committed constant-speed dispatch, stationary setup/process, safe concurrency and event WAIT; no joint yield/reposition, dynamic releases or stack precedence. |
| O3 | Base speed45 m/min, productive rate30 moves/h, setup1 min; heavy speed30/rate24/d36. Job counts4/8/20/32; move ranges6..18/20..60/30..90/60..180; horizon17280 min. Exact bays/seeds/roles frozen in the profile. |
| O4 | Finite-event CP reference <=5 jobs, primary tiny4; tick1/30 min, 100000 nodes, total wall10 s, one thread, seed0, no rounding. OPTIMAL/FEASIBLE/INFEASIBLE/UNKNOWN/TIMEOUT kept distinct. |
| O5 | Stable M32/actions65/256 decisions; [128,128] Tanh, gamma1, no shaping; 1048576 steps/seed, five seeds1103/2207/3301/4409/5501. Rollout2048/batch128/epochs10/lr0.0003, checkpoints/validation65536. CPU only. |
| O6 | 512 train/128 validation/256 test, equal family weights; scenario-first seed nesting; four heuristic contrasts, primary balanced_finish_v1; 20000 stratified draws seed7042026; eight adjusted intervals99.375% each, joint nominal95%; >=60 common complete pairs/family and unconditional failure accounting. |

All are **PROPOSED**, not approved or empirical. [SCIENTIFIC_PROPOSAL.md](SCIENTIFIC_PROPOSAL.md) gives rationales, references, limits and full values. [NUMERICAL_PROVENANCE.json](NUMERICAL_PROVENANCE.json) covers every one of the 136 numeric leaves with units/origin/rationale/sensitivity/uncertainty. Heavy is a bundled stress family, not a factorial causal estimate; no power/convergence claim is made.

[OWNER_REVIEW.md](OWNER_REVIEW.md) contains the exact declaration. The approved root would expressly authorize only the named exact derivation rule for future generated-input and validation-selected checkpoint identities; no fictitious child approval is issued. Source, tools, environment, inputs, budgets, roles, full seed coverage and checkpoint hashes are rechecked. Changing them requires a new reviewed payload.

## C. Engineering evidence and limitations

- Final exact-source suite: [FINAL_ENGINEERING_VERIFICATION_V3.json](FINAL_ENGINEERING_VERIFICATION_V3.json), 112 passed; source snapshot unchanged during tests.
- CLI: [CLI_VERIFICATION_V2.json](CLI_VERIFICATION_V2.json), 17 passed, including PowerShell help/status/environment/profile/preparation; missing approval/input/model rejections; existing-environment setup branch; actual solver; untrained candidate-policy save; fixture baselines/replay; honest empty report.
- [FINAL_ENVIRONMENT_AND_INFERENCE_V2.json](FINAL_ENVIRONMENT_AND_INFERENCE_V2.json): real numerical/import checks, exact [128,128] actor/critic, Adam epsilon1e-5, CPU2 threads; 32 bounded masked predictions after reload; actual timesteps and optimizer updates both zero. These timings are fixture inference only, not training throughput.
- Real tqdm tested on bounded fixture generation, real environment-step callback wiring, committed cells/interruption telemetry, and nested bootstrap. Progress is stderr; machine stdout stays JSON. Logs retain completed units and immutable checkpoint/cell boundaries.
- Repairs: full CP total-time bound/status handling; owner-commit-compatible historical audit; finite all-failed selection keys; preserved best selection on resume; deterministic episode restart; partial-checkpoint exclusion; RNG-preserving verification; model/sidecar counter consistency; fractional tick certificate comparison at declared tolerance.
- No optimizer update or full primary pipeline was run. Genuine optimized-policy quality and live optimizer-interruption/resume behavior remain for the approved owner run; resume explicitly restarts episodes and does not promise bitwise uninterrupted equivalence.
- Fresh hashed environment recreation was prepared and syntax-checked; the already installed environment was not deleted/recreated merely to repeat installation. Actual installed packaging and compatibility were verified.

All attempted failures/earlier successful receipts remain, with resolutions in [WORKLOG.md](WORKLOG.md). Historical development records are unchanged.

## D. Exact manual sequence

Run from repository root. Execute each long action deliberately, after reviewing its predecessor outputs. No wrapper starts the next campaign automatically. Full conditions, outputs, recovery and exact seed commands are in [MANUAL_RESEARCH.md](MANUAL_RESEARCH.md).

```powershell
.\04-rail-crane-scheduler\scripts\Project04.ps1 ValidateEnvironment
.\04-rail-crane-scheduler\scripts\Project04.ps1 ValidateProfile
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareGeneration
# Only after the exact OWNER_REVIEW declaration and genuine matching receipt:
.\04-rail-crane-scheduler\scripts\Project04.ps1 Generate
.\04-rail-crane-scheduler\scripts\Project04.ps1 VerifyGeneration
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareBaselines
.\04-rail-crane-scheduler\scripts\Project04.ps1 Baselines
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareTraining
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 1103
.\04-rail-crane-scheduler\scripts\Project04.ps1 TrainingStatus
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 2207
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 3301
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 4409
.\04-rail-crane-scheduler\scripts\Project04.ps1 Train -Seed 5501
.\04-rail-crane-scheduler\scripts\Project04.ps1 SelectModels
.\04-rail-crane-scheduler\scripts\Project04.ps1 PrepareEvaluation
.\04-rail-crane-scheduler\scripts\Project04.ps1 Evaluate
.\04-rail-crane-scheduler\scripts\Project04.ps1 VerifyResults
.\04-rail-crane-scheduler\scripts\Project04.ps1 GenerateReport
```

Generate produces 896 disjoint committed input cells; verify before references/training. Baselines uses validation only (640 cells). All five full-budget seed selections must freeze before evaluation. Evaluate plans 2560 held-out cells including CP ineligibility counts. VerifyResults independently reconstructs physical validity/metrics and model identities; GenerateReport emits all CSV/JSON results, adjusted effect/failure figures, finite CP gaps and an immutable report manifest.

Resume actions are ResumeGeneration, ResumeBaselines, ResumeTraining -Seed N and ResumeEvaluation. Complete boundaries are verified; partials retained. A training interruption before the first checkpoint cannot be resumed from a nonexistent optimizer state; preserve the attempt and review a fresh attempt/amendment. Minimum free RAM2 GiB/disk10 GiB is checked before owner training/evaluation.

## E. Scientific acceptance and preservation

Functioning software is established by passing engineering checks; it is not a trained PPO. Physical success requires independently valid complete schedules. Training requires genuine nonzero optimizer state plus every declared full seed budget. Improvement requires the prespecified adjusted paired criterion and unconditional failure companion; a negative/inconclusive result must be retained. Mathematical reference quality requires independently valid OPTIMAL for the matching supported finite domain, never a continuous global optimum. Held-out support requires all planned cells, all five seeds, untouched cohorts and >=60 complete common pairs/family.

Technical Project I interoperability remains DATA_GAP: no real bay/cargo/rail telemetry/native successor interface was invented. The isolated adapter is preserved. Full scientific closure requires audited real campaign results/statistics/figures/claims and explicit review; no automatic closure flag is set.

Protected legacy files unchanged: **656**. Historical Project 04 development records unchanged: **71**. HEAD remains `4a01b9181bd08818bece3a154781acacca00f7b3`, main, index empty. No legacy source/result/checkpoint rerun or rewrite occurred.

The root ignore repair now exposes Project 04 source/config/tests/scripts/docs while keeping environments/experiments/models/caches/logs excluded. See [COMMIT_SCOPE.md](COMMIT_SCOPE.md); no force-add of the whole project and no automatic stage/commit/push.

## F. Final state and next action

INSTALLED; VERIFIED; ENGINEERING_READY; OWNER_APPROVAL_PENDING; PRIMARY_GENERATION_NOT_RUN; PPO_TRAINING_NOT_RUN; HELDOUT_EVALUATION_NOT_RUN; SCIENTIFIC_CLOSURE_NOT_COMPLETE.

No unresolved installation/engineering blocker remains. Owner review of the exact O1-O6 payload and declared manual scope is the next action. Local available RAM must satisfy preflight when the owner starts training. [FINAL_STATUS.json](FINAL_STATUS.json) is the machine-readable summary.

Project-local `.gitattributes` also preserves the exact current LF/CRLF checkout bytes of hash-bound code/config/tools, avoiding core.autocrlf fingerprint drift; GIT_CHECKOUT_BYTE_POLICY.json verifies this without changing executable bytes.

Changed-file scope: [CHANGE_INVENTORY.json](CHANGE_INVENTORY.json). Final handoff SHA-256 manifest: [READINESS_INTEGRITY.json](READINESS_INTEGRITY.json), excluding itself.
