# DynamicBAPEnv v1

`DynamicBAPEnv` (`dynamic_bap_env_v1`, `dynamic_obs_v1`) is an online,
event-driven Gymnasium environment. StaticBAP constructs an offline schedule
with all arrivals known; DynamicBAP reveals only arrived vessels and arrivals
inside the configurable future horizon `H` (minutes). No StaticBAP action or
checkpoint is directly compatible with this environment.

## Time and information

The clock starts at minute zero and jumps between service completions, vessel
arrivals and horizon entries. At a shared timestamp it charges waiting over
the preceding interval, then processes completions, arrivals and horizon
entries, each ordered by vessel ID. Post-assignment choices are recomputed at
the same timestamp. There are no one-minute control ticks.

Each vessel moves `HIDDEN -> ANNOUNCED -> WAITING -> IN_SERVICE -> COMPLETED`.
At `H=0`, the announcement phase is skipped. An arrival in `(t,t+H]` is
announced; it cannot be assigned until its actual arrival. Hidden vessels
have no slot, candidate, status bit or feature row. An event queue knows their
future timestamps internally, but the observation does not disclose these or
count hidden vessels. Scenario IDs/fingerprints live only in `info` for
scientific provenance, never in the observation. `H` defaults to the scenario
horizon and may be overridden at construction, including `H=0`.

Project 02's `RandomStreams` and synthetic traffic configuration are reused.
Its SimPy terminal processes were not reused for the decision clock: they
couple berth dispatch with crane/yard operations and cannot pause at each
masked online vessel-position choice without importing different physics.
The local heap therefore handles only the three Step 10 event types.

## Actions and candidates

For `M=max_vessels`, `P=2*M` bounds two quay boundaries and two sides per
other active vessel. There are `1 + M*P` discrete actions: `0=WAIT`, or
`1 + slot*P + candidate_index` for an immediate berth assignment. The slot is
allocated at first reveal, using timestamp/event priority/vessel ID order, and
is never reused. `M` must cover the entire episode. Action-space sizes for
`M=8,16,24` are respectively `129`, `513`, `1153`; the large joint space is a
Step 11 learning consideration, not a reason to change physics here.

The dynamic candidate adapter calls shared `candidate_positions` and
`is_placement_feasible` with **IN_SERVICE placements only**. Completed vessels
neither block the quay nor add boundaries. Candidates are ordered by position
and cached once per decision. The same cache supplies observation features,
`action_masks()` and execution. Returned masks/observations are fresh arrays.
Invalid, masked or non-integer actions raise before state mutation. Every
assignment starts at `current_time_min`; backdating and future reservations
are prohibited. The half-open service interval and clearance rules come from
the shared core.

WAIT is available only when a vessel is WAITING, an immediate assignment is
feasible, and a **visible** event lies strictly in the future: completion of
an IN_SERVICE vessel or arrival of an ANNOUNCED vessel. A hidden arrival or
horizon entry does not make WAIT available. This rule keeps the WAIT bit of
both `action_masks()` and the observation's `action_mask` non-anticipatory;
it fixes the Step 10 hidden-event mask leak without changing
`dynamic_bap_env_v1` (no dynamic checkpoints or results depended on it).

Once legally selected, WAIT advances through the actual event queue. A hidden
vessel may enter the horizon or arrive before the next previously visible
event; the clock stops at that earlier event if it creates a decision. The
new information is then visible because time has passed. When no choice is
available, automatic advancement still uses internal events without exposing
them beforehand or charging an agent WAIT. Horizon entries can be automatic
events even when they create no assignment.
Consecutive same-time assignments are legal. A consistency error is raised
for unresolved waiting vessels with no future event.

## Observation

All arrays are fixed-shape; zeros mean unused/unrevealed. Physics remains in
raw minutes/meters. The default fixed scales are 1440 minutes and 1000 meters;
they are never derived from hidden scenario duration or population.

| Key | Shape | Meaning |
| --- | --- | --- |
| `current_time` | `(1,)` float32 | elapsed minute / time scale |
| `horizon` | `(1,)` float32 | H / time scale |
| `terminal_features` | `(2,)` float32 | quay / length scale, clearance / quay |
| `vessel_features` | `(M,3)` float32 | (ETA or arrival minus now) / time scale, length / quay, service / time scale |
| `visible_mask` | `(M,)` int8 | slot allocated |
| `status_features` | `(M,4)` int8 | ANNOUNCED, WAITING, IN_SERVICE, COMPLETED one-hot |
| `placement_features` | `(M,3)` float32 | active position / quay, (start-now) / time scale, (end-now) / time scale |
| `candidate_features` | `(1+M*P,2)` float32 | action-indexed position / quay and accrued vessel waiting / time scale |
| `action_mask` | `(1+M*P,)` int8 | valid immediate actions and WAIT |

The terminal observation has the same shapes, with no valid actions. It does
not reveal full-future vessel data as StaticBAP does. `observation_space.contains`
is checked in tests. Gymnasium's default `check_env` samples unmasked actions,
so it is not a valid strict-action checker here; explicit API tests are used.

## Reward, drain and validation

Each elapsed interval charges `Q_wait * delta_t`, where `Q_wait` includes only
arrived vessels not yet in service. A step returns the negative sum of those
charges; same-time assignment itself adds zero. A clean episode satisfies
`sum(rewards) = -total_waiting_time` from the independent core objective.
There are no bonuses or reward scaling.

After the last start, the simulator drains service completions automatically.
Success requires all vessels completed and a core-validated feasible schedule.
The drain limit is `last_arrival_time + max_drain_extension_min`; at the limit,
an unresolved episode is truncated with explicit unresolved IDs and is never
reported as a completed schedule. Fixed service duration is exogenous and read
through one `_service_duration_min` hook for future integration. No crane,
yard, ETA-noise or variable-duration decisions are modeled here.

Dynamic instances default to `termination_mode=drain` and a 10080-minute
extension for compatibility with existing scenario constructors; a synthetic
config can override `max_drain_extension_min` explicitly.

`event_records` and `decision_records` retain ordered in-memory logs; export
and persistent benchmark tracking remain separate. Positive automatic clock
jumps are logged as `AUTOMATIC_ADVANCE`, distinct from policy `WAIT` records.
`online_fcfs_action` uses
only current legal choices, chooses earliest arrival then vessel ID and lowest
position, and never reads hidden scenario vessels. It is an engineering
baseline, not a complete Step 12 benchmark.

## Scenarios and examples

`DynamicSyntheticScenarioProvider` keeps the static provider's seed-modulo-3
split, exclusion and ID protocol. `MixtureScenarioProvider` accepts dynamic
providers. The static provider continues to reject dynamic configs. LOW is
static in the shipped preset; convert it **outside** the environment:

A generated dynamic instance with no horizon is accepted only when the
environment constructor supplies `future_horizon_min` explicitly.

```python
from dataclasses import replace

low_dynamic = replace(low_config.with_formulation("dynamic"),
                      future_horizon_min=240.0,
                      scenario_id="synthetic_low_dynamic")
```

Hand-worked tests cover immediate start (0 waiting), a full-quay queue (10
minutes), simultaneous arrivals (0 artificial delay), intentional WAIT to a
horizon entry (40 waiting minutes), variable-length concurrent placements,
no-future WAIT masking, automatic drain, an announcement at minute 40 for a
minute-100 arrival with `H=60`, and completed-vessel candidate removal.

Run targeted and full tests from Project 03:

```powershell
python -m pytest tests/unit/test_dynamic_bap_env.py tests/integration/test_dynamic_bap_integration.py -q
python -m pytest -m "not slow" -q
python -m pytest -q
python scripts/run_dynamic_smoke.py
```

Step 11 can add a training wrapper for reward normalization and a joint-action
policy, but must preserve these physical units, masks and causal observations.
