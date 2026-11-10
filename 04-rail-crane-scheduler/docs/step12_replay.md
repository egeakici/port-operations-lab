# Step 12 read-only replay

Streamlit UI accepts an existing problem JSON and schedule/run JSON uploads,
maximum 10 MiB each. It independently validates source records, shows original
provenance/failures/unfinished jobs and refuses invalid-motion animation. Gantt
supports task filtering and source intervals; rail slider interpolates only the
validated piecewise-linear model. Comparison requires the identical problem hash.
PNG export uses recorded data only; no solver/trainer/live crane action is invoked.

The headless fixture render verifies Gantt duration and intermediate rail position,
PNG output, immutable input bytes and an actual Streamlit AppTest initial page.
AppTest/Matplotlib on the managed Windows sandbox can emit a Python temporary
directory cleanup PermissionError at process exit; the actual three test
assertions pass and the warning is retained in receipts, not hidden. Normal user
frontend execution is separate and is not a background service launched here.

Run from repo root after setting PYTHONPATH as in README:

```powershell
python -m streamlit run .\04-rail-crane-scheduler\frontend\replay_app.py
```

No research charts are fabricated. Current demos are TEST_FIXTURE_SYNTHETIC;
native terminal integration and calibrated operational benefits are not delivered.
