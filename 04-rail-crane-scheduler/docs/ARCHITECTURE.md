# Architecture and reproducibility handoff

`contracts.py` owns immutable fields, units, canonical JSON and identities.
`scenarios.py` consumes them, with counter-SHA256 named streams and split guards.
`kernel.py` alone advances the execution clock; `validator.py` independently
reconstructs proposed paths without importing the kernel. `baselines.py` and
`cpsat.py` choose plans under that supported model. CP-SAT's extensional path
domain is exact only for the bounded finite event-dispatch subclass.

`environment.py` exposes Gymnasium; `encoding.py` fixes tensors/masks/reward.
`training.py` owns the separate crane MaskablePPO, validation selection and
immutable checkpoints. `research.py` owns candidate locks/pairing/statistics;
`evaluation.py` performs owner-manual held-out execution and committed-cell
verification. `replay.py` and `frontend/replay_app.py` read recorded truth without
optimization. `integration.py` is a synthetic one-way adapter/harness, never a
mutation route to a historic terminal. `cli.py` provides explicit safe/manual modes.

No module imports a legacy simulator or checkpoint. Optional RL/UI/solver
dependencies are loaded only along their own paths; package/contract import is
standard-library-only. The actual supported development environment and source
hashes are recorded in receipts. All executable code lives in Project04.

The scholarly continuation order is: approve/version hypotheses; lock physical
and generator profiles; prove supported-model invariants; verify heuristic/CP
baselines; freeze observation/action/reward and cohorts; train multiple independent
model seeds with validation-only selection; freeze selected models; manually
evaluate untouched scenarios; perform prespecified scenario-paired/nested
inference; publish manifest-backed findings, failures and limitations. A fixture
smoke is neither a calibrated digital twin nor a scientific effect estimate.

Profile IDs and raw source hashes, not file names alone, establish compatibility.
Any future dynamic releases, body envelopes, yield actions, multi-vessel QCAP,
stochastic service or joint berth/crane/yard learning needs a new explicit scope.
Real AIS does not provide ship stowage or crane move logs; no empirical data were
used. Preserve old source/results and compare a separately versioned successor.
