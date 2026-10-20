"""Manually compare CPU/CUDA PPO prediction; simulator stays CPU."""
import argparse
import json
from integrated_terminal_pilot.benchmark.device_benchmark import benchmark


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device', choices=('cpu','cuda','both'), default='both')
    p.add_argument('--steps', type=int, default=32)
    p.add_argument('--repeats', type=int, default=3)
    p.add_argument('--warmup', type=int, default=2)
    p.add_argument('--scenario-seed', type=int, default=10000000)
    p.add_argument('--training-seed', type=int, choices=(11,23,37), default=11)
    p.add_argument('--no-progress', action='store_true')
    a = p.parse_args()
    try:
        result = benchmark(device=a.device, steps=a.steps, repeats=a.repeats, warmup=a.warmup,
            scenario_seed=a.scenario_seed, training_seed=a.training_seed, show_progress=not a.no_progress)
        print(json.dumps(result, indent=2))
        return 0 if result['status']=='COMPLETED' else 2
    except (ValueError, RuntimeError, OSError) as exc:
        print(json.dumps({'status':'BLOCKED','reason':str(exc)}))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
