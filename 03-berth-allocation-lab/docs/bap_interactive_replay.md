# BAP Interactive Replay

This optional, read-only Project 03 presentation layer replays completed
Dynamic BAP held-out H=240 records. It does not train, load a checkpoint,
run a new evaluation or alter the frozen Project 03 release.

## Architecture and sources

`frontend/bap_replay_app.py` is a thin Streamlit entry point. It imports the
Project 02 `app.styles.apply_styles` and `app.ui_helpers.metric_card` modules
from the sibling project, reuses its sidebar/KPI/tabs/SVG/Plotly conventions,
and has no dependency on the Project 02 running simulation engine. Project 02
files were not modified. Pure read-only adaptation, event reconstruction and
rendering live in `berth_allocation_lab.replay`.

The catalog comes from the completed Step 12A Dynamic manifest, hashed
`source_inventory.json` and hashed `paired_differences.csv`. A selected
scenario loads its actual Step 11 `test_h240` evaluation JSON by recorded
SHA-256. The source configuration hash, physical fingerprints, vessel inputs,
core schedule feasibility and canonical total waiting are checked before
display. Final KPI values are the recorded evaluation values, not fresh
optimizer results. Original placement and event timestamps retain full
precision internally; only labels are rounded. The Step 13 warehouse remains
a derived summary and is not used to invent physical trajectories.

Five families are available when their Git-ignored artifacts are present:
Tiny n6/n7/n8, Medium n16 and Heavy n24. Each selected scenario offers
Online FCFS, Online Rollout and Dynamic PPO seeds 11/23/37. The three-seed
aggregate is **not** a replayable schedule. The neutral default is the first
replayable smallest-family scenario by stable scenario ID. Static replay is
omitted because historic Static records do not reliably retain full
placements and action traces.

## Launch

Run each PowerShell command from `03-berth-allocation-lab`:

```powershell
python -m pip install -e ".[viz]"
python -m streamlit run frontend/bap_replay_app.py
```

The sibling `02-mini-port-simulation/app/` presentation modules must remain
available in the repository. No database server, API, JavaScript build, GPU or
training process is required. If the Git-ignored Step 11/12 evidence is not
restored on another machine, the app shows a missing-data message instead of
generating substitute outcomes. Checkpoints are unnecessary for replay.

## Reading the replay

Choose a family, recorded scenario and policy in the sidebar. Play/Pause,
Previous/Next Event and Restart traverse recorded event boundaries;
the slider scrubs absolute simulation minutes. Speed changes visual playback
only. Changing policy preserves absolute simulation time where possible;
changing scenario resets to the first event. Same-time events remain separate
steps. Compare mode keeps FCFS, the selected PPO seed and Rollout at the same
absolute time, never the same action index.

The top-down quay is one continuous berth. Hull widths and positions use
recorded meters; the dashed amber guide denotes clearance separately from
hull length. Active service occupies `[start, end)`. Waiting and ANNOUNCED
lists contain only vessels visible at the recorded event prefix. Future
hidden vessel IDs are not displayed as policy knowledge. The Space-Time tab
shows complete recorded placements retrospectively, with position on the
horizontal axis and simulation minutes on the vertical axis. Its complete
schedule was not available to the online policy in advance.

The Decisions tab shows the actual recorded assignment or intentional WAIT,
plus a policy-visible state reconstructed from events **before** that action.
Automatic advances are not intentional WAIT. If only a schedule is available,
occupancy can be shown from derived start/completion boundaries, but the
inspector explicitly reports missing decision history. It never supplies an
unrecorded neural-network rationale or legal-alternative set.

Final episode KPIs are labeled separately from the current waiting queue.
Comparison deltas are `policy - FCFS`: negative means less recorded waiting.
Only runs with matching fingerprints, scenario IDs, splits and vessel inputs
may be compared.

## Scientific limits

The scenarios are synthetic and uncalibrated. Service durations are
exogenous; crane/yard optimization is absent. Online Rollout is heuristic,
not a dynamic optimum. H=240 information value, WAIT causality, CPU/CUDA
action parity and commercial gains have not been established. Decision
latency measurements are bounded engineering results. This interface is a
post-completion demonstration, not Step 14 or a new benchmark.
