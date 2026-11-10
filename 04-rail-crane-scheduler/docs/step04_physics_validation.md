# Step 04 physical fixture model

Proposed profile `p04_reference_point_constant_speed_proposed_v1`: explicit
reference-point clearance; constant-speed travel; stationary setup/processing;
non-preemptive atomic jobs; two fixed ranks; no acceleration/body/stowage model.
All numeric values come from labelled fixtures. Research execution is refused.
This is not approval of P04-S01-004 through 008.

Kernel commits immediate paths against the other crane's committed future paths
and stationary tail. The union of all path knots gives exact minima of affine
relative position on each interval. The independent validator imports no kernel
code: it rebuilds each crane path, fills stationary gaps and checks every common
breakpoint, resource intervals, speed, setup/process duration, bay/reach,
readiness, original identities, continuity and completion.

This dispatch action model holds unassigned cranes in place: unrestricted joint
yield/reposition schedules can be feasible yet unsupported by dispatch. DEADLOCK
means stuck under these actions, not certified global infeasibility. The validator
can inspect explicit standalone reposition traces; kernel does not invent them.
WAIT advances to travel/setup/process/availability events, processing completions
settle in completion-time/rank/task order, then later dispatch sees releases.
Horizon truncation never counts as completion; empty work has makespan zero.

Tests cover both Step 01 X1/X2 counterexamples, manual makespan 5 minutes,
opposite-side blocking, partial work, duplicate jobs, wrong speed/duration/hash,
clone isolation, invalid WAIT, empty work, unreachable jobs and horizon cutoff.
Source/commands/counts are in the immutable step04 attempt receipt. Missing
body-aware/dynamic/yield coverage is explicit rather than a safety assertion.
