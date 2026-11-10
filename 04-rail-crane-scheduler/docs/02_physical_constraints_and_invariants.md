# Physical constraints and independent validation plan

These are future executable requirements, **not implemented tests**. All fixture
numbers below are hand-worked synthetic examples, not proposed operational
defaults. Conditions apply to the [reference model](01_problem_specification.md).
Validator/error names are proposed Project 04 concepts, not existing APIs.

The independent validator consumes original immutable input plus a complete
proposed plan/trace, reconstructs paths/work/time without trusting policy metrics,
and returns structured violations before any execution mutation. Invalid actions
must leave the state unchanged. Hard safety cannot be traded for reward.

| ID / future check / proposed error class | Positive fixture | Negative fixture |
| --- | --- | --- |
| INV01 `validate_identity` / `TaskIdentityError` | Original jobs A,B each occur once | A twice, B missing, or phantom C; reject even if total moves matches |
| INV02 `validate_exclusivity` / `ResourceOverlapError` | K1 processes A on `[0,2)`, B on `[2,4)` | A `[0,3)`, B `[2,4)` on K1; or A assigned to both cranes |
| INV03 `validate_duration_and_path` / `PhysicalTimingError` | 10 m at 5 m/min takes 2 min, then setup 1 and 2 moves at 60 moves/h take 2; finish at 5 | Finish at 3, negative setup, backdated departure, or jump 10 m in zero time |
| INV04 `validate_readiness` / `ReadinessError` | Release at 3, predecessor completes at 4, setup starts at 4 with crane free | Setup at 2, or starting a blocked job; blocked work cannot count as done |
| INV05 `validate_nonpreemption` / `PreemptionError` | Entire setup/process commitment runs uninterrupted | Half of A, then B, then remaining A; releasing/reassigning mid-travel also rejects |
| INV06 `validate_rail_rank` / `RailOrderError` | K1 at 2, K2 at 8, both shift +1 without changing order | Exchange endpoints or leave/cross/return between sampled instants (examples below) |
| INV07 `validate_clearance` / `SafetySeparationError` | Gap exactly d=2 throughout, including simultaneous arrival | Gap 1.9 at an interior breakpoint when d=2, even if no crossing |
| INV08 `validate_reach_and_bounds` / `ReachBoundaryError` | Rail `[0,20]`, reach K1 `[0,10]`, bay 10 served by K1 | Bay 11 on K1 or a waiting/reposition segment outside the rail |
| INV09 `validate_work_conservation` / `WorkConservationError` | Original 5 moves = 2 processed + 3 unfinished; completion only at 5 | 6 processed, hidden missing job, unexplained workload rounding or fabricated container load |
| INV10 `validate_clock_and_events` / `TimeOrderError` | All completions at time 4 settle, then crane-rank/task-ID dispatch sees releases | Process acquisition before the same-time release, clock decreases or duplicate settlement |
| INV11 `validate_terminal_status` / `IncompleteScheduleError` | A,B complete before H and all other checks pass | Report smaller makespan with B unfinished, deadlock or horizon cutoff |
| INV12 `validate_observation_boundary` / `InformationLeakageError` | Two future-hidden variants give identical visible state/actions | Hidden release/unavailability, scenario seed or full event queue changes policy input |
| INV13 `validate_numeric_domain` / `InputDomainError` | Finite positive speed/rate, integer positive workload, nonnegative d | NaN/infinite time, bool workload, negative clearance or zero speed |
| INV14 `validate_action_atomicity` / `ActionReservationError` | Two disjoint safe same-time proposals validate in canonical order | Independently safe choices moving toward each other are committed without joint path check |

INV12's hidden-future case belongs to later dynamic diagnostics: all current
static vessel jobs are visible by design. Identity checks operate on job IDs in
stand-alone scenarios; individual cargo identities require a separate validated
adapter mapping. TEU conservation alone cannot prove original containers loaded.

## Two endpoint-only false passes

Both examples have two moving cranes, ordered safe coarse endpoints, and illegal
interior paths. Linear interpolation applies **between every listed knot**. A
checker sampling only time 0 and the last time incorrectly passes them.

**X1, opposite-side assignment followed by return.** Rail `[0,10]`, d=2 m:

| Time (min) | K1 (m) | K2 (m) | Signed gap (m) |
| ---: | ---: | ---: | ---: |
| 0 | 0 | 10 | 10 |
| 5 | 8 | 2 | -6 |
| 10 | 0 | 10 | 10 |

On `[0,5]`, gap is `10-3.2t`; clearance first fails after `t=2.5`, and
the paths cross at `t=3.125`. They cross again at `t=6.875` on return. Endpoints
at 0 and 10 appear unchanged. Both cranes move at 1.6 m/min in each segment.

**X2, asymmetric legs with safe net progress.** Rail `[0,22]`, d=2 m:

| Time (min) | K1 (m) | K2 (m) | Signed gap (m) |
| ---: | ---: | ---: | ---: |
| 0 | 2 | 14 | 12 |
| 4 | 14 | 10 | -4 |
| 6 | 8 | 12 | 4 |
| 14 | 8 | 20 | 12 |

K1 speed is 3 m/min on its moving legs; K2 speed is 1 m/min. Initial gap
`12-4t` reaches zero at 3 min. During `[4,6]` gap `-4+4(t-4)` reaches zero
at 5 min. At the common final endpoint both positions increased by 6 m with a
safe 12 m gap; an endpoint-only net-displacement checker misses both crossings.
The waiting tail of K1 is still a physical trajectory requiring validation.

For single linear legs sharing the same start/end times, **signed ordered gap
checks at both endpoints are sufficient**; two safe such endpoints cannot conceal
a crossing. The failure above arises from omitting interior trajectory knots.
An even weaker checker using only absolute distance also accepts a single-step
swap `(0,10)->(10,0)`, despite collision halfway. Do not confuse this with the
correct signed, union-of-breakpoints criterion.

## Timing and numerical conventions

Proposed P04 event order is `(time_min, completion/release priority, rail_rank,
task_id, sequence)`: settle all motion/setup/process completions at a timestamp,
then readiness/releases, then validated dispatch; finally decide termination.
Processing/resource occupancy uses half-open intervals `[start,end)`; physical
paths and safety include both endpoints. Distinct same-time proposals must be
jointly validated regardless of their serialization order. An epsilon does not
authorize finite crossing or skipped work. In exact arithmetic use `gap>=d`;
the future floating implementation must document a numerical error bound, reject
material deficits and report any near-boundary ambiguity. Tolerances have separate
meter/minute units and are not a time grid. Project I/03's `1e-9` is a reference,
not an approved Project 04 value.

A future validator must inspect every breakpoint of both paths, compute relative
gap extrema on each common interval, verify speed and continuity, and reconcile
resource modes/work. It must retain infeasible, impossible, timeout and zero-work
fixtures; a solver's self-reported feasibility is insufficient. Step 04 must add
property checks for reordering of same-time inputs, split/merged collinear path
segments and independent recomputation before any policy benchmark.
