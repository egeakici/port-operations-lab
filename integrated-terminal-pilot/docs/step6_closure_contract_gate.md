# Step 6 closure contract gate

## Phase A preregistration — 2026-10-14, before fixture comparisons

Development only. Starting HEAD: `76ced62b94e5419fea98933b3cb17debf1bd8a62`.
The owner confirmed that the single closure prompt is the complete specification.
This does not approve Q6. No existing algorithm or research profile is changed.

### Applicability predicate

`EXACT_ELIGIBLE` requires all of the following, established from fixture construction
and the decision state before scores are compared:

1. Identical revealed cohort, legal physical positions, slot/action ordering and WAIT bit.
2. Each unstarted vessel has fixed service `30 + 0.5 * moves + 20`, independent
   of position, branch and other vessels: one 120 moves/hour crane per vessel,
   enough compatible cranes, no transport/yard rate constraints, ample storage,
   and all outbound cargo already in the yard. Occupying vessels have exact forecasts.
3. All branches finish before the common inner drain horizon; no cargo delay or rollover.
4. Same next visible arrival/release event and legal WAIT subbranches, FCFS continuation,
   no hidden entrants, exact half-minute fixture arithmetic and action-index tie-break.

If a construction violates these conditions it is `NOT_EXACT_ELIGIBLE`, even if
its selected actions happen to agree. An unexplained eligible mismatch is
`CONTRACT_DEFECT` or `UNKNOWN`, never permission to retune a policy.

For cohort C at time t, authentic P03 scores only *future queue waiting* W(a).
For completed fixed-service branches, integrated turnaround is W(a) + K, where
K = sum(service_i + max(t-arrival_i,0)) for unstarted vessels, plus
sum(fixed_departure_i-arrival_i) for occupying vessels. Departed vessels are
excluded; they contribute no future waiting. K is candidate independent.
This establishes full preference-order equivalence including ties, not equality
of the numerical objectives. Censoring breaks this proof: P03 stops accruing
waiting when all vessels are assigned and has no matching drain-censor rule.

### Predeclared fixtures and scope

Use small hand-written development fixtures, counts 2 and 4 moves per vessel:
one vessel; two competing vessels; announced arrival at t=10; exact horizon
entry at t=0 for arrival=240; simultaneous release/arrival at the fixed service
end; and a state after one same-timestamp assignment (occupancy present).
Two legal end positions, stable ties, WAIT legal/illegal and no-fit intervals
are included. Compare all decisions while eligibility remains supported; a
later mismatch in physics ends an exact PREFIX, never a full episode claim.

Negative controls: 30 rather than 120 moves/hour; active distance coupling;
short drain horizon; unavailable export; unavailable transshipment with D17.
They are diagnostic constructions, not changed research scenarios.
Preserve fixture SHA, all candidate scores and WAIT branches, decision times,
constant residuals, complete preference orders and first divergence.
The B evaluator must remain the independent physical implementation; direct
P03 calls are reference observations only, never injected into B decisions.

### Post-observation correction rules

This gate follows the observed Medium result (A2 16,136 versus B2/B2-T 18,783
vessel-min). Fixture construction is therefore a diagnostic, not confirmatory evidence.

| Classification | Permitted response |
| --- | --- |
| CONTRACT_DEFECT | Cite an existing rule; minimal repair, pre/post evidence and regressions |
| NOT_EXACT_ELIGIBLE | Record the violated condition; do not force equivalence |
| MODEL_DIFFERENCE | Preserve negative findings and report the mechanism as scoped evidence |
| UNKNOWN | Block broad F3 until resolved; no favorable scoring or skipped candidate |

No score, tolerance, cohort cap, continuation, physics, profile, information
boundary or checkpoint may change to improve observed performance.

Results will be appended after execution; this preregistration is not a PASS.

## Phase A observed result — 2026-10-14

`PASS_WITH_SCOPED_CLAIMS`: 12 FULL fixtures, 0 PREFIX fixtures, 20 eligible
decisions, 5 noneligible controls, 0 demonstrated contract defects. At every
eligible decision the independent authentic P03 reference, A2 wrapper, and B2-T
agree on legal candidates, full preference order, ties, selected action, WAIT
next epoch and subbranch scores after the candidate-independent constant.
Independent hand calculations also check one-vessel and competing-vessel scores.

Immutable evidence:
`experiments/step6_closure/gates/7cb84b87c78f3b2a6628a59ce4a2013b90ba8d66c347230eab24d6095f18c5c2.json`.
The filename is its canonical JSON SHA-256. Fixture source and input hashes,
candidate tables and first divergent decisions are retained there.

| Negative construction | Observed interpretation |
| --- | --- |
| Crane rate mismatch | The nominal/physical service constant fails; the observed choice still agrees. Agreement does not make it eligible. |
| Distance coupling | Turnaround residual depends on position (4.336 versus 5.496 minutes at the first state); fixed-service proof fails. |
| Drain censoring | All integrated candidates score 50 while P03 assignment scores 0 waiting and WAIT scores 10. P03 chooses assignment; B2-T chooses WAIT by the action-index tie-break. The objectives have different censoring semantics. |
| Unavailable export | Fixed ready-cargo premise fails. This deliberately constructed fixture bypasses generator validation and is not a research scenario. |
| Unavailable transshipment | Fixed service and ready-cargo premises fail under the preserved connection/D17 semantics. |

These are `NOT_EXACT_ELIGIBLE` observations with model-difference mechanisms,
not defects to repair by changing objectives or physics. This gate establishes
the stated conditional contract only. It does not explain the complete Medium
performance gap, establish universal A2/B2-T equivalence, or authorize F3.

Existing policy algorithms were left unchanged. The only existing-source edit
is optional sanitized observation capture in `benchmark/runner.py`, disabled by
default. Capture/plain fixture comparisons preserve trace and prediction digests
for A2, B2 and B2-T. No P03 file, frozen policy or research profile was edited.
