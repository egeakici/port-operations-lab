"""Optional manual development-only PPO; never replaces frozen Step 7 checkpoints."""
import argparse
import json
from pathlib import Path
from integrated_terminal_pilot.benchmark.development_training import train


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--device',required=True,choices=('cpu','cuda'))
    p.add_argument('--run-dir',required=True,type=Path)
    p.add_argument('--total-timesteps',required=True,type=int)
    p.add_argument('--checkpoint-every',type=int,default=512)
    p.add_argument('--scenario-seed',type=int,default=10000000)
    p.add_argument('--training-seed',type=int,choices=(11,23,37),default=11)
    p.add_argument('--resume-from',type=Path)
    p.add_argument('--acknowledge-development-only',required=True,action='store_true')
    p.add_argument('--no-progress',action='store_true')
    a=p.parse_args()
    result=train(run_dir=a.run_dir,device=a.device,total_timesteps=a.total_timesteps,
        checkpoint_every=a.checkpoint_every,scenario_seed=a.scenario_seed,training_seed=a.training_seed,
        resume_from=a.resume_from,show_progress=not a.no_progress)
    print(json.dumps(result,indent=2))
    raise SystemExit(130 if result['status'].startswith('INTERRUPTED') else 0)
