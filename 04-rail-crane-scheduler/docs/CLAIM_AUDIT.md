# Claim audit

| Claim | Source / actual evidence | Inference | Status |
| --- | --- | --- | --- |
| Supported fixture motion valid | kernel.py, independent validator.py, step04 + final regression, X1/X2 | Hand calculations/negative cases, no operational certification | FIXTURE_TESTED |
| Four heuristic arms feasible on supported fixtures | baselines.py, step05/current final tests, CLI_SMOKE | Same input hash/physics; no population effect | FIXTURE_TESTED |
| CP-SAT certified optimum | cpsat.py, enumeration tests; real backend skipped | Finite event-dispatch subclass only; no executed CP certificate | DEPENDENCY_PENDING |
| Crane PPO tooling works | training.py, actual untrained model mask/save/reload tests | No optimization or selected research checkpoint | API_SMOKE_ONLY |
| PPO better/faster operationally | No research checkpoints/held-out records | No scientific comparison or latency claim | NOT_DEMONSTRATED |
| Scientific inference infrastructure | research.py/evaluation.py synthetic result tests | Scenario-paired/nested helpers; real inferential settings pending | TOOLING_ONLY |
| Read-only replay | replay.py/frontend, PNG render + AppTest | Recorded fixture only, no recomputed optimization | FIXTURE_TESTED |
| Integration | integration.py isolated source-mapped fixture | Original IDs/moves, stale rejection; no live terminal/cargo claim | ISOLATED_SMOKE_PASS |
| Earlier science preserved | PREFLIGHT 656 tracked hashes + final audit | Not a re-verification of ignored raw archives | TRACKED_PRESERVATION_VERIFIED |
| Real calibration/commercial benefit/joint RL | No data or experiment | No claim allowed | NOT_DEMONSTRATED |
