# Step 6 closure owner decisions — proposed 2026-10-14

All four decisions: `PENDING_EXPLICIT_OWNER_APPROVAL`. The owner's clarification
that the prompt is complete is not approval of any Q6 item. No approval date,
signature, supersession or validation authorization has been recorded.

| Decision | Existing source contract and implementation | Exact proposed decision and consequences | Alternative |
| --- | --- | --- | --- |
| Q6-1 | Protocol §3 delegates estimator detail; `coordination_policies.B1_ESTIMATOR`, `b1_release_estimate`, `_preview_block`, `B1IntegratedGreedyPolicy.decide` | Accept existing v1: release = now + crane delay + 30 + sequential flow handling + 20; flow rate = minimum of crane/transport/current yard share; ties by release, arrival, vessel ID, position. Missing cargo is assigned preview handling, with no cargo-loss objective or future-arrival delay. | Defer approval; a changed estimator needs a separately specified amendment, not outcome-driven tuning. |
| Q6-2 | Integration specification §10/D26 proposed omission; `coordination_view.build_projection`, `simulator.observable.build_observable_clone`, `generator.export_prestaging` | Future gate-in and pickup requests are not simulated. Already observed requests continue. Label all outputs `UNCALIBRATED_SYNTHETIC_FORECAST`; omission is not universally conservative. | Defer; a different forecast needs an explicit versioned methodology. |
| Q6-3 | Protocol §5 frozen structural search and proposed 2 s trigger; AM-08; `SharedRolloutEvaluator.evaluate`, `budget_fingerprint`; authentic P03 `online_rollout_choice` | **K5-A:** uncapped full visible cohort and all legal + WAIT candidates. Supersede the proposed 2 s reduction trigger with a reported warning for Step 6 and future Step 7 research. Preserve authentic A2, no timeout/fallback. Keep the 400,000-cycle fail-closed engineering guard. | K5-B cap or K5-C alternative would need a new specification and may change authentic A2; neither is recommended or implemented. |
| Q6-4 | `SharedRolloutEvaluator.evaluate`, `_leaf`, `effective_leaf`, `select`; observable clone's drain horizon; P03 `_VisibleContinuation.finish_after_wait` | Cohort = revealed nondeparted vessels; T_inner = last visible arrival + existing extension. Sum min(departure,T_inner)-arrival, censored vessels charged to T_inner. U = original cohort obligations not LOADED/DEPARTED_BY_VESSEL at inner stop. WAIT advances to next physical berth decision and scores all legal starts, choosing the best branch under each selector. | Defer interpretation; do not silently clamp scores or alter ties. |

Source facts versus inference: the formulas and omission are directly implemented;
their acceptance as the final Step 6 detail is the owner decision. Structural
comparability is conditional on the independent gate, not a claim of equal runtime
or universal horizon equivalence. P03 accumulates future waiting and has no drain
censoring; integrated predictions include service and elapsed turnaround.

Q6-2 qualification: `request = arrival - 360 - lead`, lead >= 0, while announcement
is at max(0, arrival-240). Negative requests become initial inventory; a request at
zero is processed before horizon entry. Thus generated visible exports have requested
entry, but can still be AT_GATE or RECEIVING. Transshipment's 720-minute connection
guarantees an earlier inbound arrival, not completed discharge. The historical
observation-contract heading claiming no visible cargo loss is too broad if read as
load availability; it remains preserved, with this qualification supplied additively.

Proposed bounded F3 authorization: the prehashed 12-run Heavy/Bottleneck plan,
seeds 10000000 and 10000001, A2/B2-T/B2, one worker, 180 minutes cumulative admission
budget, 4 GiB process-RSS admission check. Finish an already-running healthy episode;
stop before another admission on overrun and request a revision. No third seed.
These are engineering proposals, not owner-approved resources or a guaranteed ETA.

Approval response requested after reviewing the closure reports:

> Approve Q6-1, Q6-2 and Q6-4 as documented, and Q6-3 = K5-A full cohort with
> the proposed 2-second trigger superseded for Step 6/Step 7 research. Approve
> the identified F3 plan and its one-worker, 180-minute admission budget; proceed
> with bounded development runs after the execution-readiness checks pass.

Approval, if given, will be appended with the actual date, verbatim response,
plan SHA, provenance “explicit project-owner approval in this Step 6 Closure
conversation”, and supersession lineage to protocol §5's proposed trigger.
The 28 pending parameter records remain pending. No formal lock or Step 7 starts.

The specific current proposal is plan SHA-256
`1c97b83d5d5537bc95b6285795a521ffd01cbfdae580fcbbcd4701c811bd43bf`.
The reviewed gate to bind in a future approval record is canonical SHA-256
`7cb84b87c78f3b2a6628a59ce4a2013b90ba8d66c347230eab24d6095f18c5c2`.
The gate and controller are ready for owner review; the successful tests do not
substitute for that approval.
