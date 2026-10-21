# Integrated Terminal Pilot: manual execution only

The owner requires CODE-ONLY DEVELOPMENT / MANUAL EXECUTION. Implement, inspect,
review and prepare commands. Do not launch tests, regressions, training, scientific
campaigns, large simulations, background jobs or automatic continuation. The owner
runs these in their terminal. Syntax/static checks are permitted. Do not commit
automatically. Preserve existing evidence, approvals, checkpoints and hashes.

Prepare separate foreground CLIs and exact PowerShell commands. Source changes
invalidate matching regression/plan fingerprints; report re-verification needs.
Never bypass approval, lock, checkpoint, split-isolation or failure gates.
Step 7 frozen inference remains CPU; CUDA diagnostics and optional development
training are separate and cannot supply replacement Step 7 checkpoints.

Owner update 2026-10-20: a single OWNER-STARTED FOREGROUND command on the remote
computer may sequence required regressions, approval recording, locking,
validation, test and export. This is not permission for the coding agent to run
it. No scheduled/background continuation or automatic Git commits. Keep the
source checkout clean; generated approval overlays/locks/results live in the
portable result bundle. Return verification must not evaluate policies.

2026-10-21 repair: fresh remote runs use Complete-Step7.ps1 and the actual
historical CPython3.13.2 / NumPy2.2.3 / Torch2.6 reference environment. Keep the
original v1 transport and every failed run. V2 adds missing original batch
metadata. Strict historical replay must pass before long regressions; do not
replace expected hashes or claim the remote four failures pass without execution.
