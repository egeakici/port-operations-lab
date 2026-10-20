"""Prepared for OWNER execution: bounded manual-workflow safety and serialization checks."""
from contextlib import nullcontext
import json
import signal
import threading

import pytest


def test_explicit_cuda_never_silently_falls_back(monkeypatch):
    from integrated_terminal_pilot.benchmark import execution as e
    monkeypatch.setattr(e,'device_info',lambda *a,**k:{'cuda_available':False})
    with pytest.raises(RuntimeError,match='no CPU fallback'):
        e.require_torch_device('cuda')
    with pytest.raises(ValueError):e.require_torch_device('auto')


def test_cooperative_first_interrupt_and_forced_second_restore_handler():
    from integrated_terminal_pilot.benchmark.execution import finish_current_episode_on_interrupt
    before=signal.getsignal(signal.SIGINT)
    with finish_current_episode_on_interrupt() as requested:
        handler=signal.getsignal(signal.SIGINT)
        handler(signal.SIGINT,None)
        assert requested.is_set()
        with pytest.raises(KeyboardInterrupt):handler(signal.SIGINT,None)
    assert signal.getsignal(signal.SIGINT)==before


def test_boundary_stop_never_generates_or_executes(monkeypatch,tmp_path):
    from integrated_terminal_pilot.benchmark import step7 as s
    row={'row_id':'unborn','split':'validation','family':'itp_medium'}
    monkeypatch.setattr(s,'verify_lock',lambda *a:{})
    monkeypatch.setattr(s,'load_plan',lambda *a:{'rows':[row]})
    monkeypatch.setattr(s,'save_progress',lambda *a:{'preserved':True})
    monkeypatch.setattr(s,'worker_lock',lambda *a:nullcontext())
    monkeypatch.setattr(s,'require_split',lambda *a:pytest.fail('new admission after stop'))
    flag=threading.Event();flag.set()
    assert s.run_campaign(tmp_path/'plan.json',stop_requested=flag)=={'preserved':True}


def test_validation_cache_uses_plan_identity_not_last_arm(monkeypatch,tmp_path):
    from integrated_terminal_pilot.benchmark import step7 as s
    row={'row_id':'fixture','scenario_id':'fixture','world':'integrated','family':'itp_medium',
         'arm':'A1','ppo_training_seed':None,'split':'validation'}
    monkeypatch.setattr(s,'_VALIDATION_VERIFIED',set())
    monkeypatch.setattr(s,'load_plan',lambda *a:{'rows':[row]})
    path=s.run_path(tmp_path,row);path.parent.mkdir(parents=True);path.write_text('{}')
    calls=[]
    def verify(*a):
        calls.append(1)
        return {'status':'COMPLETED','result':{'status':'COMPLETED'}}
    monkeypatch.setattr(s,'verify_result',verify)
    s.validation_gate(tmp_path/'plan.json');s.validation_gate(tmp_path/'plan.json')
    assert calls==[1]


def test_training_output_cannot_escape_or_replace_frozen_paths(tmp_path):
    from integrated_terminal_pilot.benchmark.development_training import sandbox_path
    from integrated_terminal_pilot.benchmark import step7 as s
    for p in (s.REPO/'03-berth-allocation-lab/experiments',s.PROJECT_ROOT/'experiments/step7_paired_v1',tmp_path):
        with pytest.raises(ValueError):sandbox_path(p)
    assert sandbox_path(s.PROJECT_ROOT/'experiments/training_sandbox/test').name=='test'


def test_training_bundle_tamper_detected_before_deserialization(tmp_path):
    from integrated_terminal_pilot.benchmark.development_training import verify_bundle
    from integrated_terminal_pilot.benchmark import step7 as s
    files={}
    for name in ('model.zip','environment.pkl','rng.pkl'):
        (tmp_path/name).write_bytes(b'NOT DESERIALIZED')
        files[name]=s.file_hash(tmp_path/name)
    s.seal(tmp_path/'manifest.json',{'settings':{'fixture':True},'files':files})
    assert verify_bundle(tmp_path,{'fixture':True})['files']==files
    (tmp_path/'rng.pkl').write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'):verify_bundle(tmp_path,{'fixture':True})


def test_development_vector_environment_roundtrip_preserves_next_transitions():
    import cloudpickle
    import numpy as np
    from tests.step6_support import leakage_doc
    from integrated_terminal_pilot.scenarios.berth_projection import build_berth_projection
    from berth_allocation_lab.envs import DynamicBAPEnv
    from berth_allocation_lab.policies.dynamic_fcfs import online_fcfs_action
    from stable_baselines3.common.vec_env import DummyVecEnv
    scenario=build_berth_projection(leakage_doc())
    original=DummyVecEnv([lambda:DynamicBAPEnv(scenario=scenario,max_vessels=24,future_horizon_min=240)])
    original.seed(11);original.reset()
    restored=cloudpickle.loads(cloudpickle.dumps(original))
    try:
        for _ in range(5):
            action=online_fcfs_action(original.envs[0])
            assert action==online_fcfs_action(restored.envs[0])
            left,right=original.step([action]),restored.step([action])
            for k in left[0]:assert np.array_equal(left[0][k],right[0][k])
            assert np.array_equal(left[1],right[1]) and np.array_equal(left[2],right[2])
    finally:
        original.close();restored.close()
