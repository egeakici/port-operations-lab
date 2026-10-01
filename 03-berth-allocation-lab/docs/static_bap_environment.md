# StaticBAP Environment

Step 8 implements `StaticBAPEnv` (`static_bap_env_v1`, observation encoding
`static_obs_v1`), a Gymnasium environment exposing exactly the frozen Step 5-7
static decision model. It is ready for agent integration; no PPO model, policy
network or training loop exists.

**Core defines physics. Environment exposes decisions. Policies choose actions.
Evaluation measures results.**

## What The Environment Represents

StaticBAPEnv is an offline, sequential schedule-construction environment.
The entire vessel population of the instance is known in advance and is
visible in every observation. It is not a real-time online agent, not a
chronological discrete-event simulator, and it has no operational clock, WAIT
action, automatic advance or drain phase. Those belong to the future
DynamicBAPEnv.

An episode schedules every vessel exactly once:

```text
static scenario -> canonical vessel order -> observation
  -> agent picks candidate index -> canonical earliest feasible start
  -> placement appended -> reward = -waiting -> next vessel
  -> after N decisions: final Step 5 validation, terminated=True
```

- **Fixed order.** Vessels are always scheduled in
  `(arrival_time_min, vessel_id)` order via the shared `ordered_vessels`. The
  agent cannot reorder vessels in v1.
- **Decision.** The agent chooses only a candidate berth-position index. It
  never chooses a vessel, an arbitrary metre value, a start time or WAIT.
- **Start time.** `s_i = earliestFeasibleStart(v_i, x_i, P_{i-1})` from the
  Step 5 core (through the shared `candidate_starts` helper).
- **Construction is not chronology.** A later decision may receive an earlier
  physical service start; the decision index is not simulation time.

The environment contains no geometry of its own. Candidates, starts, waiting,
validation and metrics all come from `core`, `policies.base` helpers and
`evaluation.metrics`. It never calls FCFS, Greedy Rollout or the exact solver.

## API

```python
from berth_allocation_lab.envs import StaticBAPEnv, SyntheticScenarioProvider

env = StaticBAPEnv(scenario=scenario, max_vessels=8)       # fixed instance
env = StaticBAPEnv(scenario_provider=provider, max_vessels=8)  # generated

obs, info = env.reset(seed=42)
mask = env.action_masks()              # bool, shape (2 * max_vessels,)
obs, reward, terminated, truncated, info = env.step(int(mask.nonzero()[0][0]))
```

Constructor keywords: exactly one of `scenario` / `scenario_provider`;
required `max_vessels`; `time_scale_min=1440.0`; `length_scale_m=1000.0`;
`policy_id="external_agent"` (written into in-memory decision records, since
the environment cannot know who chose the actions); `render_mode=None` or
`"ansi"` (plain text).

Read-only properties: `scenario`, `ordered_vessels`, `placements`,
`decision_records`, `current_candidates`, `episode_return`, `terminated`,
`final_metrics`.

## Fixed Action Capacity And Index Mapping

Step 5's `candidate_positions` emits two quay boundaries plus two
clearance-adjusted sides of every existing placement, then filters, sorts and
deduplicates. At decision `k` there are at most `2 + 2k` candidates, so for at
most `M` vessels `|C_k| <= 2M`:

```python
action_capacity = 2 * max_vessels
action_space = spaces.Discrete(action_capacity)
```

`max_vessels` is an environment capacity, independent of Step 7's 8-vessel
solver limit. A scenario with more vessels raises; it is never truncated. If
the generator ever produced more candidates than the capacity, the environment
raises `StaticBAPEnvConsistencyError` instead of truncating.

Action `j` means "the `j`-th canonical candidate of the current decision".
It is not a fixed coordinate across decisions or episodes, and there is no
metre grid. The candidate list is computed exactly once per decision (at reset
and after each valid step) and shared by the observation, `action_masks()` and
`step()`.

## Action Masking And Invalid Actions

`action_masks()` returns a fresh boolean array of shape `(action_capacity,)`:
the first `candidate_count` entries are True, the rest False, and all entries
are False after termination. It reads the cached list and never recomputes
geometry or mutates state. It matches `obs["candidate_mask"]` exactly. The
method name follows the sb3-contrib Maskable PPO convention for Step 9.

Invalid actions raise and change nothing (index, placements, return,
candidates, scenario, termination flag):

| Action | Exception |
| --- | --- |
| index outside `[0, action_capacity)` or negative | `ValueError` |
| index within capacity but masked | `ValueError` |
| bool, float, string, `None`, non-scalar array | `TypeError` |
| any step after termination, or before reset | `RuntimeError` |

Python `int`, NumPy integer scalars and 0-d integer arrays (as returned by
Stable-Baselines3 `predict`) are accepted. There is no automatic repair, no
FCFS fallback and no invalid-action penalty: a masked action is an API error,
not a BAP decision.

### Gymnasium checker limitation

`gymnasium.utils.env_checker.check_env` samples `action_space.sample()`
without consulting masks, which conflicts with strict rejection in general
multi-vessel states. The checker is therefore run on a one-vessel fixture with
`max_vessels=1` (capacity 2), where both boundary candidates `0` and `Q - L`
are distinct and valid, for fixed and generated modes and both render modes,
with checker warnings treated as errors (except the note that an unregistered
env has no spec). This does not validate arbitrary multi-vessel mask states;
those are covered by dedicated contract tests (space membership, dtypes,
finiteness, mask/feature agreement, masked-action rejection, freshness).

## Observation

A fixed-shape `spaces.Dict`. `M = max_vessels`, `C = action_capacity = 2M`.
Rows follow canonical vessel order; the row index is the vessel identity
within an episode (vessel ID strings are not encoded numerically).

| Key | Space | Shape / dtype | Content |
| --- | --- | --- | --- |
| `vessel_features` | Box | `(M, 3)` float32 | arrival_rel, length/Q, service/T |
| `vessel_mask` | MultiBinary | `(M,)` int8 | 1 = real vessel, 0 = padding |
| `placement_features` | Box | `(M, 3)` float32 | position/Q, start_rel, end_rel |
| `scheduled_mask` | MultiBinary | `(M,)` int8 | 1 = placed (authoritative) |
| `current_vessel_index` | Discrete(M+1) | scalar int64 | row `k`, or sentinel `M` |
| `current_vessel_features` | Box | `(3,)` float32 | copy of row `k`; zeros at end |
| `candidate_features` | Box | `(C, 3)` float32 | position/Q, start_rel, waiting/T |
| `candidate_mask` | MultiBinary | `(C,)` int8 | equals `action_masks()` |
| `terminal_features` | Box | `(2,)` float32 | Q/length_scale, d/Q |

`terminal_features` describes the marine terminal quay, not the terminated
episode state. Padding rows are zeros; masks, not zero values, define meaning
(a placement at `x = 0` is valid). Current-vessel features are given directly
so a feedforward network does not have to learn a dynamic row lookup.

At termination: `current_vessel_index = M` (never indexed as a vessel),
`current_vessel_features = 0`, candidate features/mask are all zero, and
shapes are unchanged.

The observation intentionally excludes any exact-reference objective, optimal
or Rollout-preferred action, rollout score or optimality label. Each call
returns freshly allocated arrays; the environment stores no arrays, so callers
cannot mutate internal state.

### Time and space encoding

`time_scale_min = 1440.0` is a fixed observation scale, not a simulation
duration or constraint. The reference time is the current vessel's arrival;
after termination it is the last canonical vessel's arrival.

```text
absolute minute m  ->  (m - reference_time) / time_scale_min
duration h, wait w ->  h / time_scale_min,  w / time_scale_min
position x, len L  ->  x / Q,  L / Q
quay Q, clearance d -> Q / length_scale_m,  d / Q
```

Durations never have the reference subtracted. The current vessel's own
arrival feature is therefore 0, and a candidate's `start_rel` equals its
`waiting/T`; both are kept so each column keeps a stable meaning. Shifting all
arrivals by a constant leaves observations, candidate positions and rewards
unchanged (regression-tested). Unbounded columns use the finite float32 range
as bounds: values are never clipped, and a value that would not be finite in
float32 raises. All physics, rewards and validation use raw float64 units.

## Scenario Modes, Seeds And Identity

**Fixed mode.** Every reset uses the same instance; `reset(seed=...)` seeds
Gymnasium's RNG but never changes the scenario.

**Generated mode.** `provider(seed) -> BAPScenarioInstance`. On reset the
environment calls `super().reset(seed=seed)` and draws a generation seed from
`self.np_random`: with `provider.sample_seed(self.np_random)` when the provider
defines `sample_seed`, otherwise uniformly in `[0, 2**31 - 1]`. It then calls
the provider and validates type, static formulation, capacity and that
`scenario.seed` equals the drawn seed. `reset(seed=42)` reproduces the same
scenario and initial observation; `reset(seed=None)` continues the existing RNG
stream. A failed reset leaves no usable episode.

`SyntheticScenarioProvider(config, base_scenario_id=..., split=...)` wraps the
existing generator. For seed `s` it generates with
`scenario_id = f"{base_scenario_id}_{split}_seed{s}"`, `seed = s` and the
explicit `split`, preserving every other configuration field and never
mutating the source config. A base ID already ending in `_seed<N>` is
rejected, and a dynamic config must be converted explicitly with
`with_formulation("static")`.

### Split-disjoint seed partition

Generation seeds are partitioned by split so that training and evaluation
instances cannot overlap:

```text
offset(train) = 0, offset(validation) = 1, offset(test) = 2
seed s belongs to split p  <=>  s % 3 == offset(p)
```

- `provider(s)` raises `ValueError` when `s` belongs to another split, so the
  same base ID and seed can never yield one instance for two splits.
- `provider.sample_seed(rng)` returns `3 * u + offset(split)` with `u` drawn
  uniformly by `rng.integers`, covering exactly that split's seeds in
  `[0, 2**31 - 1)`.
- Each split therefore yields different seeds, scenario IDs, vessel sets and
  fingerprints for the same generation index `u`.
- `split_of_seed(s)` returns the owning split; `SPLIT_SEED_OFFSETS`,
  `SPLIT_SEED_STRIDE` and `SAMPLED_SEED_LIMIT` are exported from
  `berth_allocation_lab.envs`.

Explicit evaluation seed lists (for example a fixed validation or test set in
Step 9 or the Step 12 benchmark) must follow the same partition: validation
seeds are `1, 4, 7, ...`, test seeds `2, 5, 8, ...`. A list that ignores the
partition is rejected by the provider rather than silently overlapping with
training. A plain callable provider without `sample_seed` keeps the uniform
draw and receives no partition guarantee.

Reset info: `scenario_id`, `scenario_seed`, `scenario_fingerprint`,
`scenario_split`, `vessel_count`, `environment_version`.

Both modes reject non-static scenarios through `require_static_scenario`.

**Known issue for Step 9 planning.** The current presets assign the split by
traffic family (`low -> train`, `medium -> validation`, `heavy -> test`, and
the Step 7 tiny congested preset is `test`). The Step 2 contract intends
splits as disjoint instances/seeds. The provider therefore ignores the preset
split, requires an explicit one, writes it into each instance's identity and
fingerprint, and enforces the seed partition above. Step 9 must still define
explicit training configurations rather than reusing the test-oriented Step 7
preset as a training distribution.

## Reward, Return And Termination

```text
r_k = -W_k,   W_k = s_k - a_k   (canonical waiting_time)
R = sum_k r_k = -J,   J = total vessel waiting
```

There is no terminal, utilization, position or priority term, no clipping and
no normalization. A successful episode ends after exactly N valid actions with
`terminated=True, truncated=False`. Before termination is committed, the
environment checks that each vessel is placed once in order, runs
`find_schedule_violations`, recomputes `total_waiting_time`, verifies
`R = -J` and `StaticMetrics.objective_value = J` within the central tolerance,
and checks the scenario fingerprint. Any disagreement raises
`StaticBAPEnvConsistencyError`; an invalid schedule is never reported as
success. An empty candidate list is also a consistency error (no WAIT, skip or
silent success).

Step info: `decision_index`, `vessel_id`, `candidate_count`,
`selected_candidate_index`, `selected_berth_position_m`,
`selected_start_time_min`, `incremental_waiting_time_min`. Terminal info adds
`total_waiting_time_min`, `episode_return`, `objective_value`,
`schedule_valid`, `vessel_count_completed` and `static_metrics`.

### Discounted versus undiscounted return

The undiscounted return equals `-J` exactly. Discounted RL training commonly
optimizes `G = sum_k gamma^k r_k`; for `gamma < 1` this weights early
decisions more and is not in general equivalent to minimizing total waiting.
Step 8 does not alter rewards to compensate. Step 9 should consider
`gamma = 1.0` to preserve exact objective alignment (episodes have fixed
length N); any other value must be reported as an objective difference. All
evaluation uses canonical undiscounted total waiting.

## Records And Persistence

Each step appends a `StaticDecisionRecord` (unchanged Step 6/7 schema) built
from that decision's own candidate list. Records, placements and final
metrics stay in memory. `step()` writes no files; persisting evaluation runs
remains the responsibility of the tracking layer and later evaluation
adapters.

## Replay Validation

Replays use only `reset`, `action_masks` and `step` with recorded
`selected_candidate_index` values. For every decision the mask must allow the
index, candidate positions must equal the recorded list, and position, start
and waiting must match; final placements, objective, metrics and return must
match. The environment does not know which policy produced the indices.

- **FCFS** and **Greedy Rollout**: manual 3-vessel fixture, tiny congested
  n6 seed 42, and the LOW static preset (8 vessels).
- **Exact reference** (`optimality_status=optimal`,
  `reference_scope=candidate_space`): manual fixture (0), a two-vessel
  positive case (100), tiny congested n3 (282.313763), n6 (1612.784630), and
  as a slow test n8 (3188.254108, where Rollout replays to 3297.398421).
- **Reference dominance**: enumerating every legal trajectory through the
  environment for the manual, two-vessel, n3 and n4 cases gives exactly the
  same number of complete schedules as Step 7's unpruned search; no return
  exceeds `-J*` beyond tolerance, the best equals `-J*`, and the first best
  trajectory equals Step 7's certified trajectory.

## Worked Example

Specification Example A: `Q = 500 m`, `d = 20 m`; A `(a=0, L=180, h=120)`,
B `(30, 140, 90)`, C `(40, 260, 150)`. `max_vessels = 4`, capacity 8.

1. Decision 0 (A): candidates `x = [0, 320]`, mask `[1, 1, 0, 0, 0, 0, 0, 0]`.
   Action 0 places A at `x = 0`, `[0, 120)`, reward 0.
2. Decision 1 (B, reference time 30): candidates `(x, s, W)` are
   `(0, 120, 90)`, `(200, 30, 0)`, `(360, 30, 0)`. A's row has
   `arrival_rel = -30/1440`, placement `(0, -30/1440, 90/1440)`. Action 1
   places B at the clearance boundary `x = 180 + 20 = 200`, reward 0.
3. Decision 2 (C): candidates `x = [0, 200, 240]`. Action 0 places C at
   `x = 0`; it must wait for A and B, so `s = 120`, reward `-80`.

The episode terminates with return `-80 = -J`, matching the specification.

## Step 9 Compatibility

Step 9 can rely on a stable `Discrete` action space, a structured `Dict`
observation space, boolean `action_masks()`, deterministic resets, reproducible
multi-scenario episodes and canonical rewards. A `Dict` observation will need
a multi-input policy configuration such as Stable-Baselines3
`MultiInputPolicy`. No policy, network, training configuration or
registration with `gym.register` is part of Step 8.

## Remaining Limitations

- Vessel ordering is fixed; vessel sequencing is not a decision.
- Decisions are restricted to the finite candidate model; this is not an
  unrestricted continuous BAP environment.
- Candidate generation and earliest-start evaluation are recomputed per
  decision in pure Python; very large instances are slower than tiny ones.
- The one-vessel Gymnasium checker does not exercise multi-vessel masks.
