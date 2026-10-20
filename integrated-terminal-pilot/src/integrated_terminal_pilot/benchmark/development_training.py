"""Optional manual PPO development sandbox, NEVER a Step 7 arm or checkpoint source.

Uses a nominal Project03 berth environment on one declared 10M development projection.
No validation selection, held-out scenarios, integrated PPO claim or frozen model write.
Checkpoint bundles include optimizer/model, vector environment and RNG states at
completed rollout/update boundaries. Resume requires identical source/device/settings.
"""
import json
import os
from pathlib import Path
import random
import time
import uuid

from integrated_terminal_pilot.benchmark import step7 as s


def sandbox_path(path):
    path = Path(path).resolve()
    root = (s.PROJECT_ROOT/'experiments/training_sandbox').resolve()
    if path == root or not path.is_relative_to(root):
        raise ValueError('run directory must be a child of integrated-terminal-pilot/experiments/training_sandbox')
    return path


def verify_bundle(path, expected):
    path = Path(path).resolve()
    m = s.unseal(path/'manifest.json')
    if m['settings'] != expected:
        raise ValueError('checkpoint source/device/scenario/settings mismatch')
    if set(m['files']) != {'model.zip','environment.pkl','rng.pkl'}:
        raise ValueError('incomplete checkpoint bundle')
    for name, sha in m['files'].items():
        if s.file_hash(path/name) != sha:
            raise ValueError('checkpoint bundle integrity failure: '+name)
    return m


def train(*, run_dir, device, total_timesteps, scenario_seed=10000000, training_seed=11,
          checkpoint_every=512, resume_from=None, show_progress=True):
    os.environ.setdefault('CUBLAS_WORKSPACE_CONFIG', ':4096:8')
    from integrated_terminal_pilot.benchmark.execution import require_torch_device, progress_bar
    from integrated_terminal_pilot.benchmark.device_benchmark import development_projection
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    import cloudpickle
    import numpy as np
    import torch
    from sb3_contrib import MaskablePPO
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.monitor import Monitor
    from stable_baselines3.common.vec_env import DummyVecEnv
    from berth_allocation_lab.envs import DynamicBAPEnv
    from berth_allocation_lab.rl.dynamic_config import DynamicPPOConfig
    from berth_allocation_lab.rl.dynamic_joint_scoring import DynamicJointMaskablePolicy
    from berth_allocation_lab.rl.dynamic_wrappers import DynamicTrainingRewardScale
    from dataclasses import asdict
    if training_seed not in (11,23,37):
        raise ValueError('training seed must be 11, 23 or 37')
    hardware = require_torch_device(device)
    directory = sandbox_path(run_dir)
    config = DynamicPPOConfig.load_yaml(s.REPO/'03-berth-allocation-lab/configs/rl/dynamic_ppo_medium_heavy.yaml')
    ppo = config.ppo
    # A separate declared one-environment development diagnostic; no approved campaign changes.
    quantum = ppo.n_steps
    if total_timesteps <= 0 or total_timesteps % quantum or checkpoint_every <= 0 or checkpoint_every % quantum:
        raise ValueError(f'positive budget/checkpoint interval must be multiples of {quantum} steps')
    doc, projection = development_projection('itp_medium',scenario_seed)
    settings = dict(scope='DEVELOPMENT_ONLY_NOMINAL_BERTH_PPO_NOT_STEP7',
        device=device, total_timesteps=total_timesteps, checkpoint_every=checkpoint_every,
        scenario_seed=scenario_seed, training_seed=training_seed, n_envs=1,
        source_digest=s.implementation_digest(), config_sha256=config.source_sha256,
        fingerprints=doc['fingerprints'], hyperparameters=asdict(ppo),
        overrides={'device':device,'n_envs':1}, torch_version=torch.__version__,
        packages=s.runtime()['packages'])
    # Dataclass hyperparameters contain tuples; compare the persisted JSON representation on resume.
    settings = json.loads(json.dumps(settings,sort_keys=True))
    frozen_before = verify_all_hashes()
    if not frozen_before['ok']:
        raise ValueError('frozen checkpoint integrity failure')
    torch.set_num_threads(1)
    torch.use_deterministic_algorithms(True)
    random.seed(training_seed);np.random.seed(training_seed);torch.manual_seed(training_seed)
    if device == 'cuda':
        torch.cuda.manual_seed_all(training_seed)
    if resume_from is None:
        directory.mkdir(parents=True,exist_ok=False)
        s.seal(directory/'settings.json',settings)
    else:
        if s.unseal(directory/'settings.json') != settings:
            raise ValueError('run settings changed; refuse ambiguous continuation')
        resume_from = Path(resume_from).resolve()
        if not resume_from.is_relative_to(directory/'checkpoints'):
            raise ValueError('resume bundle must belong to this sandbox run')
        verify_bundle(resume_from,settings)
    invocation = directory/'invocations'/uuid.uuid4().hex
    invocation.mkdir(parents=True)
    s.seal(invocation/'started.json',dict(utc=s.now(),settings=settings,hardware=hardware,
        resume_from=str(resume_from) if resume_from else None,
        serialization_warning='Only load locally created trusted bundles; pickle is executable data'))
    vec = None
    t = time.perf_counter()
    status = 'FAILED'
    reason = None
    last_checkpoint = None
    lease = s.worker_lock(directory)
    acquired = False
    try:
        lease.__enter__()
        acquired = True
        if resume_from is None:
            def factory():
                return Monitor(DynamicTrainingRewardScale(DynamicBAPEnv(scenario=projection,
                    max_vessels=24, future_horizon_min=240)))
            vec = DummyVecEnv([factory])
            vec.seed(training_seed)
            model = MaskablePPO(DynamicJointMaskablePolicy,vec,device=device,seed=training_seed,
                gamma=ppo.gamma,learning_rate=ppo.learning_rate,n_steps=ppo.n_steps,
                batch_size=ppo.batch_size,n_epochs=ppo.n_epochs,gae_lambda=ppo.gae_lambda,
                clip_range=ppo.clip_range,ent_coef=ppo.ent_coef,vf_coef=ppo.vf_coef,
                max_grad_norm=ppo.max_grad_norm,verbose=0)
        else:
            # Integrity/settings are verified BEFORE deserializing trusted local data.
            with (resume_from/'environment.pkl').open('rb') as stream:vec=cloudpickle.load(stream)
            model = MaskablePPO.load(resume_from/'model.zip',env=vec,device=device,force_reset=False)
            with (resume_from/'rng.pkl').open('rb') as stream:rng=cloudpickle.load(stream)
            random.setstate(rng['python']);np.random.set_state(rng['numpy']);torch.set_rng_state(rng['torch'])
            if device == 'cuda':torch.cuda.set_rng_state_all(rng['cuda'])
            last_checkpoint = str(resume_from)
        if model.device.type != device:
            raise RuntimeError('actual model device differs from explicitly requested device')
        episodes = int(getattr(model,'_episode_num',0))
        starting_steps = model.num_timesteps
        def checkpoint(kind):
            nonlocal last_checkpoint
            target = directory/'checkpoints'/f'step_{model.num_timesteps:012d}_{kind}'
            temp = directory/'checkpoints'/('.partial_'+uuid.uuid4().hex)
            temp.mkdir(parents=True)
            model.save(temp/'model.zip')
            with (temp/'environment.pkl').open('xb') as stream:cloudpickle.dump(vec,stream)
            rng = dict(python=random.getstate(),numpy=np.random.get_state(),torch=torch.get_rng_state(),
                       cuda=torch.cuda.get_rng_state_all() if device=='cuda' else None)
            with (temp/'rng.pkl').open('xb') as stream:cloudpickle.dump(rng,stream)
            m = dict(settings=settings,steps=model.num_timesteps,kind=kind,utc=s.now(),
                     files={name:s.file_hash(temp/name) for name in ('model.zip','environment.pkl','rng.pkl')})
            s.seal(temp/'manifest.json',m)
            # Never overwrite a prior completed checkpoint, including a resumed branch at this step.
            if target.exists():
                old=verify_bundle(target,settings)
                if old['files'] != m['files']:
                    raise ValueError('checkpoint collision; partial candidate preserved for inspection')
                last_checkpoint=str(target)
                return
            os.rename(temp,target)
            last_checkpoint=str(target)
            pointer=directory/'latest_checkpoint.json'
            tmp=pointer.with_suffix('.'+uuid.uuid4().hex+'.tmp')
            tmp.write_text(json.dumps({'checkpoint':str(target),'manifest_sha256':s.file_hash(target/'manifest.json')}),encoding='utf-8')
            os.replace(tmp,pointer)
        class MonitorProgress(BaseCallback):
            def _on_rollout_start(self):
                if self.num_timesteps > starting_steps and self.num_timesteps % checkpoint_every == 0:
                    checkpoint('boundary')
            def _on_step(self):
                nonlocal episodes
                episodes += sum(bool(x) for x in self.locals['dones'])
                bar.update(self.num_timesteps-bar.n)
                bar.set_postfix(model=device,sim='CPU',episodes=episodes,refresh=False)
                return True
        if model.num_timesteps >= total_timesteps:
            status = 'ALREADY_COMPLETE_VERIFIED'
        else:
            with progress_bar(total_timesteps,initial=model.num_timesteps,description='Development PPO',
                              unit='step',device=device,enabled=show_progress) as bar:
                model.learn(total_timesteps=total_timesteps-model.num_timesteps,
                            reset_num_timesteps=False,callback=MonitorProgress(),progress_bar=False)
            checkpoint('final')
            status = 'COMPLETED'
    except KeyboardInterrupt:
        status = 'INTERRUPTED_LAST_COMPLETE_CHECKPOINT_PRESERVED'
        reason = 'Discard in-progress rollout; explicitly resume the last verified complete bundle.'
    except BaseException as exc:
        reason = f'{type(exc).__name__}: {exc}'
        raise
    finally:
        if vec is not None:vec.close()
        unchanged = verify_all_hashes()==frozen_before
        out = dict(status=status,reason=reason,checkpoint=last_checkpoint,utc=s.now(),
            elapsed_seconds=time.perf_counter()-t,settings=settings,hardware=hardware,
            frozen_checkpoints_unchanged=unchanged,
            resume_limit='Complete update boundaries only; bitwise cross-device/version portability is not claimed. '
                         'Environment serialization parity must pass the supplied manual test before relying on replay.')
        try:
            s.seal(invocation/'result.json',out)
        finally:
            if acquired:lease.__exit__(None,None,None)
        if not unchanged:raise RuntimeError('frozen checkpoint integrity changed')
    return out
