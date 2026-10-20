"""Small manual CPU/CUDA diagnostic on identical DEVELOPMENT observations.

No policy training, sensitive split, scientific campaign or frozen checkpoint write.
This measures real frozen PPO prediction and CPU environment stepping separately.
"""
import copy
import time
import uuid
from pathlib import Path

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.execution import device_info, progress_bar, require_torch_device


def development_projection(family, seed):
    from integrated_terminal_pilot.scenarios.generator import generate_scenario
    from integrated_terminal_pilot.scenarios.validation import validate_scenario
    from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection
    c = s.load_generator_config()
    lo, hi = c.seed_band('development')
    if family not in ('itp_medium', 'itp_heavy') or not lo <= seed <= hi:
        raise ValueError('only Medium/Heavy DEVELOPMENT seeds may be used')
    doc = generate_scenario(c, family, 'development', seed)
    if not validate_scenario(doc).ok:
        raise ValueError('invalid development scenario')
    return doc, build_berth_projection(doc)


def benchmark(*, device='both', steps=32, repeats=3, warmup=2, scenario_seed=10000000,
              training_seed=11, show_progress=True, output_root=None):
    if device not in ('cpu', 'cuda', 'both') or not 1 <= steps <= 512 or not 1 <= repeats <= 20 or not 0 <= warmup <= 20:
        raise ValueError('invalid bounded benchmark settings (steps 1..512, repeats 1..20, warmup 0..20)')
    from integrated_terminal_pilot.benchmark.checkpoints import CheckpointRef, verify_all_hashes, static_checkpoint_gates
    from berth_allocation_lab.envs import DynamicBAPEnv
    from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action
    from berth_allocation_lab.rl.dynamic_checkpoint import load_dynamic_checkpoint
    import torch
    before = verify_all_hashes()
    if not before['ok']:
        raise ValueError('frozen checkpoint integrity failed')
    torch.set_num_threads(1)
    torch.manual_seed(0)
    directory = (Path(output_root) if output_root else s.ROOT.parent/'hardware_benchmarks')/uuid.uuid4().hex
    directory.mkdir(parents=True)
    doc, projection = development_projection('itp_medium', scenario_seed)
    env = DynamicBAPEnv(scenario=projection, max_vessels=24, future_horizon_min=240)
    observation, _ = env.reset(seed=scenario_seed)
    inputs = []
    simulation_seconds = 0.0
    with progress_bar(steps, description='Development CPU environment', unit='step', enabled=show_progress) as bar:
        for _ in range(steps):
            inputs.append((copy.deepcopy(observation), env.action_masks().copy()))
            action = online_fcfs_action(env)
            t = time.perf_counter()
            observation, _, terminated, truncated, _ = env.step(action)
            simulation_seconds += time.perf_counter()-t
            if terminated or truncated:
                observation, _ = env.reset(seed=scenario_seed)
            bar.update(1)
    ref = CheckpointRef('medium_heavy', training_seed)
    if not static_checkpoint_gates(ref)['pass']:
        raise ValueError('checkpoint compatibility gate failed')
    rows, actions = [], {}
    requested = ('cpu', 'cuda') if device == 'both' else (device,)
    settings = dict(device=device, steps=steps, repeats=repeats, warmup=warmup,
                    scenario_seed=scenario_seed, training_seed=training_seed)
    s.seal(directory/'started.json', dict(settings=settings, scope='DEVELOPMENT_ONLY_NOT_STEP7',
            fingerprints=doc['fingerprints'], checkpoints=before, host=device_info(device, torch_info=True),
            source_digest=s.implementation_digest(), utc=s.now()))
    try:
        for name in requested:
            try:
                info = require_torch_device(name)
            except RuntimeError as exc:
                rows.append(dict(device=name, status='UNAVAILABLE', reason=str(exc)))
                continue
            t = time.perf_counter()
            # Strict original CPU loader first. Only this private diagnostic copy moves to CUDA.
            model, _ = load_dynamic_checkpoint(ref.model_path, env, allow_cross_horizon=False)
            model.policy.to(name)
            model.device = torch.device(name)
            if model.policy.device.type != name:
                raise RuntimeError('actual inference device differs from request')
            load_seconds = time.perf_counter()-t
            def sync():
                if name == 'cuda':
                    torch.cuda.synchronize()
            for _ in range(warmup):
                model.predict(inputs[0][0], deterministic=True, action_masks=inputs[0][1])
            sync()
            times, chosen = [], []
            with progress_bar(steps*repeats, description=f'PPO inference {name}', unit='prediction',
                              device=name, enabled=show_progress) as bar:
                for repeat in range(repeats):
                    current = []
                    # Synchronize timed boundaries; include real host/device transfer in predict.
                    sync(); t = time.perf_counter()
                    for obs, mask in inputs:
                        action, _ = model.predict(obs, deterministic=True, action_masks=mask)
                        action = int(action)
                        if not mask[action]:
                            raise ValueError('diagnostic policy selected a masked action')
                        current.append(action)
                    sync(); times.append(time.perf_counter()-t)
                    chosen.append(current)
                    bar.update(steps)
            if any(a != chosen[0] for a in chosen):
                raise ValueError('same-device repeated inference is not deterministic')
            actions[name] = chosen[0]
            rows.append(dict(device=name, status='COMPLETED', hardware=info,
                inference_seconds=times, predictions_per_second=steps*repeats/sum(times),
                model_load_and_transfer_seconds=load_seconds, actions=chosen[0]))
            del model
        after = verify_all_hashes()
        if after != before:
            raise ValueError('checkpoint bytes changed during diagnostic')
        rates = {r['device']:r['predictions_per_second'] for r in rows if r['status']=='COMPLETED'}
        out = dict(status='COMPLETED' if all(r['status']=='COMPLETED' for r in rows) else 'PARTIAL_DEVICE_UNAVAILABLE',
            rows=rows, settings=settings, cpu_simulation_seconds=simulation_seconds,
            cpu_environment_steps_per_second=steps/simulation_seconds if simulation_seconds else None,
            cuda_over_cpu_prediction_throughput= rates['cuda']/rates['cpu'] if len(rates)==2 else None,
            paired_cpu_cuda_actions_equal=actions['cpu']==actions['cuda'] if len(actions)==2 else None,
            checkpoint_hashes_unchanged=True, fingerprints=doc['fingerprints'],
            limits='Fixed development observations; no PPO update or integrated rollout acceleration measurement. '
                   'Device order/load effects remain; no scientific CUDA parity authorization.',
            scope='DEVELOPMENT_ONLY_NOT_STEP7', utc=s.now())
        s.seal(directory/'result.json', out)
        return dict(result=str(directory/'result.json'), **out)
    except BaseException as exc:
        s.seal(directory/'failure.json', dict(status='INTERRUPTED' if isinstance(exc, KeyboardInterrupt) else 'FAILED',
                reason=f'{type(exc).__name__}: {exc}', utc=s.now(), rows=rows))
        raise
    finally:
        env.close()
