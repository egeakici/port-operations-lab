# Step 7 scientific lock and paired campaign

Current status: **LOCK_BLOCKED_OWNER_APPROVAL**. Implementation/preparation is
authorized by the owner's Step7 brief; all28 synthetic decisions are still
pending. No formal lock, validation/test generation, policy evaluation, training,
commit or Step8 work has been performed by this implementation stage.

The exact decision packet is [step7_owner_approval_packet.md](step7_owner_approval_packet.md).
It includes values/units/source kind, uncertainty, KPI impacts and the13 deliberate
choices. Recommended retention is uncalibrated SYNTHETIC V1, not real-port evidence.
Its machine rows preserve every live register value. Partial approvals fail closed.

## Inventory and access ordering

| Split | Medium scenarios | Heavy scenarios | Integrated episodes | Reference episodes | Total |
| --- | ---: | ---: | ---: | ---: | ---: |
| validation |20|20|360|200|560|
| test |50|50|900|500|1400|
| total |70|70|1260|700|1960|

Integrated identities per scenario: A1, A1n, B1, A2, B2, B2-T, A3-train11,
A3-train23, A3-train37. Reference identities: A1,A2,A3-train11/23/37.
PPO identities are nested within traffic scenarios. All are expected eligible
on Medium/Heavy subject to actual G01–G21 support/load/per-epoch gates.
Any G block remains an explicit row; missing models are never imputed.
Low/Bottleneck have diagnostic roles; no Step7 primary or13M rows are added.

The plan enumerates recipes/IDs/seed lists/physical profile/budgets/comparators
without generating sensitive data. Plans and sidecars are immutable and
content-addressed under `experiments/step7_paired_v1/<sha12>/plan.json`.
After approvals, a new pre-lock plan incorporates only actual approved register
metadata; unchanged numeric values and predeclared rows remain the same.
The final plan hash is recorded in the formal lock.

The existing Step2 generator stays development-only. The distinct Step7
consumer verifies the actual scientific lock and then creates an in-memory
permission overlay allowing development/validation/test; no stored parameter,
distribution, physics or Step2 historical file changes. The overlay is explicit
in every generation recipe and effective generator fingerprint. Diagnostic
generation is refused. A boolean authorization switch cannot bypass the gate.

Source protocol9 permits test generation after verified lock. This controller
first completes all validation rows, requires no FAILED rows and deadlock below5%
for each family/arm/checkpoint, then unseals test. There are no remaining
predeclared policy options to select; validation cannot retune the accepted Q6
semantics. A failed validation gate requires scientific review, not tuning.

## Lock and Git provenance

The lock lives at `integrated-terminal-pilot/protocol_lock_v1.json` and
`protocol_lock_v1.json.sha256`, written exclusively with x mode only after
actual28-record provenance, approved controls/Q6, Step6 evidence, checkpoint
hashes, exact plan/analysis and clean required regressions pass.

The lock binds a pre-lock implementation commit, all protected byte hashes,
canonical plan, values/roles/recipes, dependencies, approvals, regression evidence,
profile/physics/objectives/censoring/analysis and Step8 ranges. It never hashes a
future commit containing itself. The two small lock files may be committed in a
separate scoped local commit, then verified from a clean tracked worktree.
Later harmless descendant Git metadata commits are accepted only if every
protected hash and dependency remains identical. Unknown untracked source under
ProjectI blocks locking; ignored results do not. The owner-supplied untracked
root prompt is an accounted input, not discarded or staged automatically.

The Step7 brief permits necessary scoped local commits only once real owner
approval/test prerequisites pass. None has been made while28 decisions remain
pending. No push/history rewrite/reset/rebase/stash or deletion is authorized.

## Execution, preservation and resume

Use `scripts/run_step7_campaign.py` for preflight/plan/dry-run/lock/run/resume/
status/verify/report. Serial outer execution is the declared configuration.
No process pool, nested candidate pool, timeout, cohort cap, substitute arm or
wall-time admission budget is present. No parallel configuration is claimed
verified. The400000-cycle guard and2s warning semantics are preserved.

An episode starts only after lock/split/source checks and actual host memory/disk
safety checks. Healthy episodes are never cancelled for elapsed time.15-second
RSS/heartbeat samples are not a continuous peak. Cost warnings never prune.
The1GiB free-memory and2GiB free-disk admission checks are resource safety
checks, not scientific caps. An unexpected failure is sealed and stops affected
inference. A valid D24-censored DEADLOCK/drain result remains an included
scientific outcome with its terminal status and cargo shortfall.

Results/sidecars/start markers are exclusive, immutable per row. Canonical
events/decisions/ledger/blocking/rejections/final state/result streams are
losslessly gzip-compressed with deterministic headers and hashes checked
against the original runner's digests. All original result/audit/KPI/cargo and
decision records are retained. Raw historical helper labels are explicitly
identified as historical; they are never used as split authorization.

Every scenario's T_end, N_out, exogenous/physical/comparison fingerprint is
checked across arms, including reference ties. Physical duplicate scenarios
are refused. Successful resume verifies and skips completed episodes. Failed
or partial episodes are not overwritten/retried. Stale worker ownership is
archived only after host/PID/create-time checks; partial starts still require
inspection. Live/foreign workers block a second worker. Progress uses small
sealed indexes; --verify/--report verify complete raw/compressed evidence.
Immutable progress snapshots accompany the replaceable convenience pointer
`campaign_progress.json`. Heartbeat is explicitly a replaceable live pointer.

For resumable nonparallel shards, `--shard 0 --shards N` selects fixed row ordinals.
Finish **all** validation shards before test shards. A shard is not a reduced
scientific sample. One worker lock prevents simultaneous shard execution.

## Cost model and analysis contract

`experiments/step7_paired_v1/cost_model.json` separates measured Heavy A2/B2/B2-T
costs (two development observations per arm) from unmeasured Medium, other arms,
reference runs and serialization. The full sum is
70×sum(Heavy integrated+reference arm costs) +70×sum(Medium integrated+reference
arm costs) + generation/verification/serialization overhead. A Heavy-based
three-arm proxy for both families is illustrative, not a guaranteed ETA or
upper bound; slow congestion may exceed every observed case.

F3 boundary/sample maxima675.277/729.203MiB are not peak RSS. F3 raw result bytes
also contain snapshots; the new gzip trace layout differs. Raw-layout disk
scales are explicitly proxies, and actual per-run sizes/throughput update the
progress evidence. No ETA guarantee is made and planned seeds are not reduced.

`configs/protocol/step7_analysis_contract.json` preserves D24, the source10k
scenario bootstrap seed120001, Holm primary C1b/C3 family, descriptive contrasts,
S1 reference differences-in-differences, AM-06 cargo margin+0.01/seed20261013,
all-three-seed A3 nesting, failures/censoring and Step8 ranges. Final inference,
Holm interval implementation/claims, sensitivity and13M experiments remain Step8.
No NI verdict is fabricated from a positive/negative point estimate.

### External compute instrumentation preregistration (before any sensitive draw)

Run each authorized execution/resume invocation under standard-library `cProfile`,
with a unique never-reused `.prof` output path. This does not change simulator or
policy source. Count actual `TerminalKernel._process` calls and subtract the
canonical outer `events.jsonl` line counts for the **newly executed rows in that
invocation**. The difference is the actual physical-inner-event count. It does
not double-count copied WAIT prefixes and does not equate cycles with events.
Reference/A2 nominal continuations do not use the physical kernel; their call
counts/advances are separate rather than counterfeit physical-event counts.
Counts are invocation-level; per-leaf cycle diagnostics retain their original
limitations. Unique invocation inventories and profiler hashes must accompany
the report. Failed/interrupted invocations remain visible; an abrupt OS loss
may leave profiler counts unavailable, which must be reported as missing.

Development parity proof:
`experiments/step7_paired_v1/profile_fixture/parity.json` verifies identical
actions, candidate predictions and all canonical trace digests for A2/B2-T/B2.
The fixture has33 outer processed events; B2 and B2-T each process99 additional
inner events, while A2 has0 physical-inner events. These are fixture counts,
not measurements of unseen scenarios. Profiling overhead is included in
campaign wall/CPU costs and must be labelled; F3 unprofiled costs are not
direct latency comparators. The production controller/algorithm source is unchanged.

## Reproduction boundary

From the repository root, preflight and planning are safe before approval:

```powershell
python integrated-terminal-pilot/scripts/run_step7_campaign.py --preflight
python integrated-terminal-pilot/scripts/run_step7_campaign.py --plan
```

Use the exact resulting plan path for --status. After actual approvals and a
verified committed lock, --verify, --resume and --report consume that same plan.
No command in this document grants owner approval or substitutes for the lock.
The final checkpoint report supplies one exact copy/paste block and actual paths.


## Manual-only execution update - 2026-10-14

The owner supersedes unattended continuation and automatic commits with CODE-ONLY DEVELOPMENT / MANUAL EXECUTION. The old supervisor is disabled with its original bytes archived by hash. The known old processes are absent and the full regression has no sealed completion result; it is incomplete, not PASS. Actual 28-value approval is archived and remains valid, but live activation, fresh current-source regressions, the new pre-lock plan, commits, lock and campaign are explicit owner-run steps. No new scientific episode, training, expensive test or commit was executed during this adaptation. Prior pending-state descriptions above are historical intake state, not a request for repeated approval. See [manual_execution_runbook.md](manual_execution_runbook.md) and [step7_manual_execution_audit.md](step7_manual_execution_audit.md). All scientific values/roles, frozen policy source and checkpoints are retained.


## Portable remote execution update - 2026-10-20

The new primary procedure is [step7_remote_execution.md](step7_remote_execution.md).
The owner-approved two-computer workflow runs from a clean committed checkout,
records existing actual28 approval in a copied register after clean regressions,
and creates the exclusive source-defined lock inside the copyable result bundle.
See OP-STEP7-REMOTE-20261020 for the operational location amendment. No scientific
values, arms, sample counts, frozen policies or split gates change. The complete
inventory remains140 scenarios /1960 episodes (560 validation,1400 test).

All new code requires owner-run source-matching verification. Older regression
fingerprints cannot authorize this implementation. No tests, model evaluation,
new validation/test scenario, lock or campaign has been executed by the coding
agent under this workflow. `final_summary.json`, `presentation_evidence.md`,
`compute_summary.json` and `transfer_manifest.json` are generated on the worker;
return verification precedes any final Step7 closure claim. Step8 is not started.
