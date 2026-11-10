# QCSP v1 problem specification

Formulation `P04-QCSP-V1`; decision IDs refer to the
[register](05_step1_decision_register.md). The owner's qualitative scope is fixed.
Detailed engineering choices below form a coherent **proposed reference model**
where marked; their acceptance deadlines are explicit. There is no executable
model or empirically validated coefficient in this Step 01 release.

## Scope and information

One stationary, already berthed vessel; two fixed, ordered ship-to-shore quay
cranes on one shared rail; deterministic finite workload; known bay positions
and service requirements; non-preemptive atomic bay/workload jobs. All mandatory
jobs are visible at planning start and initially ready. The primary problem is
QCSP: crane-to-job assignment, order, movement, start and finish times. Fixed
crane identities are inputs, not QCAP decisions. Vessel berth/time optimization,
fleet allocation across vessels, yard scheduling and terminal-wide RL are absent.

Future versioned extensions: multiple vessels/shared fleet, dynamic releases,
unavailability, stack precedence, stochastic rates, yard blocking, online
replanning and QCAP. An event-driven interface later does not itself make static
workload stochastic or reveal genuinely hidden future arrivals.

## Sets, units and parameters

| Symbol / future field | Definition / unit | Status |
| --- | --- | --- |
| `V={v}`, `K={1,2}` | Vessel and cranes, fixed left-to-right rail rank | OWNER_SCOPE_ACCEPTED |
| `J`, `B`, `b(j)` | Unique original jobs, bays, job-to-bay mapping; counts differ | OWNER_SCOPE_ACCEPTED; data NEW_PROJECT04_REQUIRED |
| `t0`, `H` | Planning start and maximum elapsed horizon, minutes; domain `[t0,t0+H]` | Parameter values pending |
| `L_v`, `q`, `o` | Hull length and global left hull position, meters; orientation `+1` or `-1` | Geometry representation PROPOSED |
| `u_b`, `x_b` | Local distance from named ship reference, global rail coordinate, meters | DATA_GAP in inherited vessel manifests |
| `[R_lo,R_hi]`, `[a_k,z_k]` | Rail interval and crane service reach interval, meters | Required inputs, values pending |
| `x_k^0`, `v_k` | Initial rail position (m), constant travel speed (m/min), `v_k>0` | Required inputs, values pending |
| `d=min_clearance_m` | Minimum crane reference-point separation (m), `d>=0` | Geometry convention PROPOSED; value pending |
| `w_j`, `rho_kj` | Positive integer moves/job; effective processing rate moves/hour, `>0` | Required inputs, values pending |
| `h_kj` | Stationary per-job setup/handling overhead, minutes, `>=0` | PROPOSED; input must be explicit, even zero |
| `r_j`, `P_j` | Release minute and predecessor ID set | v1 `r_j=t0`, `P_j=empty`; extension fields reserved |
| `epsilon_t`, `epsilon_x` | Numeric comparison tolerances, minutes/meters | Proposed representation, values pending |

All numeric inputs must be finite, exclude booleans where numbers are expected,
and satisfy domains. Moves are not TEU or individual container counts. Real
timestamps, if adapted, require an explicit timezone-aware epoch; elapsed minutes
are `(timestamp-epoch).total_seconds()/60`. Physical values remain in these
units; any future neural normalization uses recorded training-only scales and
never changes authoritative geometry/time.

Coordinate transform: with `u_b` measured from the named ship reference,
`x_b=q+u_b` for positive orientation and `x_b=q+L_v-u_b` for reverse orientation.
Require `0<=u_b<=L_v`; the hull and service points must lie inside declared quay
and rail/reach bounds. Bay IDs alone do not specify meter offsets. Project I's
mid-hull transport point is not a bay coordinate. Berth clearance between hulls
is not crane separation; identical field spelling does not equate these values.

## State and task identity

At time `t`, state contains the clock; each crane's position, fixed rail rank,
mode (`IDLE`, `TRAVEL`, `SETUP`, `PROCESS`), availability, committed trajectory,
active job and remaining setup/work; each job's original ID, bay, original moves,
remaining/processed moves, assigned crane, readiness, start and completion.
`BLOCKED/UNRELEASED` is never `COMPLETED`. Include predecessor/release status even
when trivially ready in v1. No policy owns physical state mutation.

A job is one atomic operation type at one bay with one explicitly specified
move workload. Multiple jobs may share a bay; one job cannot silently span bays.
No job splitting, concurrent cooperative cranes, task preemption or cancellation
counts as v1 completion. A safe reconsideration point is before dispatch or after
completion, never during a committed move/setup/process. Job metadata reserves
source operation/group/container IDs and a mapping provenance tag. Aggregated
synthetic moves do not establish individual cargo fulfillment. A future adapter
must explicitly map original identities and operation semantics; absent container
data remain absent rather than creating plausible IDs.

## Proposed continuous-time reference formulation

Offline decisions are assignment `y_kj in {0,1}`, crane job orders, setup starts
`U_j`, processing starts `S_j`, completions `C_j`, movement departure/arrival
times, waits, and piecewise-linear continuous trajectories `x_k(t)`.

Processing duration for a chosen crane is

`p_kj = 60*w_j/rho_kj`; `S_j=U_j+h_kj`; `C_j=S_j+p_kj`.

Setup is stationary at the job bay. `rho_kj` is a fixed deterministic **effective**
input rate, not an unverified nominal-to-effective conversion. A separately
versioned derivation may use nominal rate times a declared efficiency factor and
productivity; it must state which losses are included and avoid double counting
setup. No Project I efficiency or throughput equivalence is presumed. The
recommended initial stand-alone profile uses explicit effective rates, pending
the owner's model-basis choice (P04-S01-006).

The admissible set is defined by:

1. `sum_k y_kj=1` for every original `j`; exactly one setup/process interval per
   job, with positive process duration; finite times within `[t0,t0+H]`.
2. `U_j>=r_j` and `U_j>=C_i` for each `i in P_j`; availability precedes departure
   and setup. V1 has no additional prerequisites; richer stowage/yard dependencies
   must not be implied by this empty graph.
3. For consecutive jobs `i,j` on crane `k`,
   `U_j>=C_i+abs(x_b(j)-x_b(i))/v_k`. For its first job,
   `U_j>=t0+abs(x_b(j)-x_k^0)/v_k`. These lower bounds alone are insufficient:
   actual travel reservations and trajectories must also pass all constraints.
4. A crane occupies exactly one mode at a time. It is stationary at `x_b(j)`
   throughout `[U_j,C_j]` for each assigned job; travels along straight rail
   segments at speed `v_k` (zero displacement has zero travel time); otherwise
   waits at its actual position. Gaps cannot hide unrecorded repositioning.
5. `x_k(t0)=x_k^0`, `R_lo<=x_k(t)<=R_hi`; jobs must lie in assigned crane reach
   `[a_k,z_k]`. Reach is a simplified longitudinal service interval, not full
   boom/trolley/hoist kinematics.
6. **For every real `t` in the horizon**, `x_2(t)-x_1(t)>=d`. Rail ranks never
   change, including when `d=0`. Check the union of every trajectory breakpoint,
   including waiting, arrival and simultaneous service events; linear relative
   displacement attains extrema at those endpoints. Checking only decision times
   or only each crane's own endpoints is insufficient.

Different cranes may travel/process concurrently if the entire joint trajectory
is legal; a single crane cannot overlap its own travel/setup/process. Travel is
committed, not instantly reassigned. V1 acceleration, bodies, sway, lifting
envelopes and detailed operational certification are excluded. The recommended
separation model treats `d` as an externally specified reference-point distance;
a body-aware extension would need both crane widths and edge clearance, with
`d=(width_1+width_2)/2+edge_clearance`. Neither widths nor clearance are inferred.

This defines continuous physical feasibility independently of an optimizer. A
future limited action interface may search a subset of these schedules and must
disclose that restriction. Makespan is `max_j C_j - t0`, including unavoidable
initial idle/travel/setup. Minimize it **only among complete valid schedules**.
Do not subtract first release or first processing start to improve a score.

## Online decision interface, WAIT and outcomes

Candidate future interface: an idle crane selects a ready unclaimed job and a
validated immediate travel/setup/process commitment; movement may only begin
after atomic joint validation against other committed trajectories. Other
uncommitted cranes hold position until dispatched. Sequential same-time dispatch
uses stable rail rank and task ID; a later choice cannot invalidate earlier
reservations. This conservative proposal may exclude coordinated yielding plans;
Step 08–09 must decide whether bounded reposition/yield actions are needed.
Do not claim its optimal solution equals the unrestricted offline formulation.

WAIT advances to the next strictly later admissible completion/release or
predeclared bounded wait boundary; it never consumes zero physical time in a
loop. With unfinished work and no future event, a missing action is
`DEADLOCK/UNSUPPORTED_ACTION_MODEL`, not successful WAIT. Masking all legal
dispatches just to force a favorable result is invalid. The specific action
grammar remains pending review; offline schedules can include explicit safe
repositioning/waits provided their physical paths are recorded.

Successful termination requires all original mandatory jobs complete, workload
reconciled and independent physical validation passed. At `t0+H`, process
completions exactly at the boundary before deciding success/truncation. Outcomes
are `SOLVED_VALID`, `INVALID_INPUT`, `INVALID_PLAN`, `INFEASIBLE_CERTIFIED`,
`DEADLOCK`, `TRUNCATED_HORIZON`, `SOLVER_TIMEOUT_NO_PLAN` or
`UNSUPPORTED_MODEL`. A timeout may retain a separately validated feasible incumbent
with its solver status; it is never certified optimal by timeout alone.
Insufficient rail reach can make validly formed input impossible; preserve all
unfinished jobs and the reason. Empty workload is valid only with valid initial
geometry: no work, makespan zero, utilization undefined. No discarded work can
create a solved episode.
