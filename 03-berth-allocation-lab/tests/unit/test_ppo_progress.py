import runpy
from pathlib import Path

import pytest

pytest.importorskip("sb3_contrib", reason="requires the rl extra")

from berth_allocation_lab.rl.progress import progress_bar
from berth_allocation_lab.rl.suites import ScenarioSuite
from berth_allocation_lab.rl.training import cached_baseline_means


def test_cached_baseline_progress_reports_hits_without_changing_cache(manual_static_scenario, tmp_path, capsys):
    suite = ScenarioSuite("validation", "validation", (manual_static_scenario,))
    path = tmp_path / "cache.json"
    first = cached_baseline_means(suite, path)
    assert capsys.readouterr().err == ""
    original = path.read_bytes()
    second = cached_baseline_means(suite, path, progress=True)
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "validation FCFS references" in captured.err
    assert "validation ROLLOUT references" in captured.err
    assert "cache_hits=2" in captured.err
    assert path.read_bytes() == original
    assert first["cache_misses"] == second["cache_hits"] == 2
    for key in ("fcfs_mean_total_waiting_time_min", "rollout_mean_total_waiting_time_min"):
        assert first[key] == second[key]


@pytest.mark.parametrize("error", [RuntimeError, KeyboardInterrupt])
def test_progress_bar_closes_on_failure(error, capsys):
    with pytest.raises(error):
        with progress_bar(enabled=True, total=3, description="failing") as bar:
            bar.update(1)
            raise error()
    assert bar.disable  # tqdm.close() disables subsequent writes
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("enabled", [False, True])
def test_training_script_forwards_display_only_seed_labels(enabled, tmp_path, monkeypatch, capsys):
    from berth_allocation_lab.rl import training

    calls = []

    def fake_train(config, seed, **kwargs):
        calls.append((seed, kwargs))
        return {"status": "completed", "training_runtime_seconds": 0.0}

    monkeypatch.setattr(training, "train_static_ppo", fake_train)
    root = Path(__file__).resolve().parents[2]
    main = runpy.run_path(str(root / "scripts/train_static_ppo.py"))["main"]
    args = ["--config", str(root / "configs/rl/static_ppo_smoke.yaml"),
            "--training-seed", "11", "--training-seed", "23", "--output-dir", str(tmp_path)]
    assert main([*args, "--progress"] if enabled else args) == 0
    assert [(seed, kw["progress"]) for seed, kw in calls] == [(11, enabled), (23, enabled)]
    assert calls[0][1]["progress_description"] == "static_ppo_smoke_v1 seed 11 (1/2)"
    assert calls[1][1]["progress_description"] == "static_ppo_smoke_v1 seed 23 (2/2)"
    assert capsys.readouterr().err == ""
