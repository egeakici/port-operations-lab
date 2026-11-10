"""New crane MaskablePPO tooling. Training is reachable only via manual gates.

No model is created/loaded at import. Checkpoints are immutable directories;
resume restarts episodes at an optimizer boundary, never claims bitwise replay.
"""
from dataclasses import dataclass
from pathlib import Path
import importlib.metadata
import os
import random
import statistics
import time
from uuid import uuid4
from .contracts import *
from .encoding import EncodedCraneEnv, interface_candidate
from .research import source_snapshot, manual_gate
from .scenarios import no_leakage, write_new

TRAINER_VERSION="p04_crane_maskableppo_v1"
DEPENDENCIES=("numpy","gymnasium","torch","stable-baselines3","sb3-contrib")


@dataclass(frozen=True)
class TrainingConfig(Wire):
    schema_version: str
    seeds: tuple[int, ...]
    task_capacity: int
    max_episode_steps: int
    reward_scale_min: float
    failure_margin_min: float
    total_steps: int
    rollout_steps: int
    batch_size: int
    epochs: int
    learning_rate: float
    gamma: float
    gae_lambda: float
    clip_range: float
    entropy_coef: float
    value_coef: float
    max_grad_norm: float
    net_sizes: tuple[int, ...]
    validation_interval_steps: int
    device: str
    permit_cpu_fallback: bool

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version==TRAINER_VERSION and len(set(self.seeds))==len(self.seeds)>=2 and all(s>=0 for s in self.seeds),"TRAINING_CONFIG","config","multiple unique predeclared training seeds required")
        require(all(x>0 for x in (self.task_capacity,self.max_episode_steps,self.reward_scale_min,self.failure_margin_min,self.total_steps,self.rollout_steps,self.batch_size,self.epochs,self.learning_rate,self.max_grad_norm,self.validation_interval_steps)) and self.rollout_steps>=2,"TRAINING_CONFIG","budgets","positive explicit budgets required")
        require(self.total_steps%self.rollout_steps==0 and self.rollout_steps%self.batch_size==0,"ROLLOUT_BUDGET","config","whole rollouts/batches only")
        require(self.gamma==1. and 0<self.gae_lambda<=1 and 0<self.clip_range<1 and self.entropy_coef>=0 and self.value_coef>=0 and self.net_sizes and all(x>0 for x in self.net_sizes),"REWARD_OR_ARCHITECTURE","config","undiscounted profile and explicit network required")
        require(self.device in {"cpu","cuda","auto"},"DEVICE","config.device","explicit supported device required")


def versions(): return {name:importlib.metadata.version(name) for name in DEPENDENCIES}


def resolve_device(config):
    import torch
    if config.device=="cpu": return "cpu"
    if torch.cuda.is_available(): return "cuda"
    require(config.permit_cpu_fallback,"DEVICE_UNAVAILABLE","device","CUDA unavailable; no implicit CPU fallback")
    return "cpu"


def make_env(problem,config,permit=None):
    return EncodedCraneEnv(problem,task_capacity=config.task_capacity,max_steps=config.max_episode_steps,reward_scale_min=config.reward_scale_min,failure_margin_min=config.failure_margin_min,invalid_action_mode="truncate",permit=permit)


def make_model(env,config,seed):
    import numpy as np
    import torch
    from sb3_contrib import MaskablePPO
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    device=resolve_device(config)
    if device=="cuda": torch.cuda.manual_seed_all(seed)
    return MaskablePPO("MultiInputPolicy",env,learning_rate=config.learning_rate,n_steps=config.rollout_steps,batch_size=config.batch_size,n_epochs=config.epochs,gamma=config.gamma,gae_lambda=config.gae_lambda,clip_range=config.clip_range,ent_coef=config.entropy_coef,vf_coef=config.value_coef,max_grad_norm=config.max_grad_norm,policy_kwargs={"net_arch":list(config.net_sizes)},seed=seed,device=device,verbose=0)


def _rng_state():
    import numpy as np
    import torch
    state=np.random.get_state()
    return {"python":random.getstate(),"numpy":[state[0],state[1].tolist(),int(state[2]),int(state[3]),float(state[4])],"torch_cpu":torch.get_rng_state().tolist(),"torch_cuda":[s.tolist() for s in torch.cuda.get_rng_state_all()] if torch.cuda.is_initialized() else []}


def restore_rng(state):
    import numpy as np
    import torch
    def tuples(value): return tuple(tuples(x) for x in value) if isinstance(value,list) else value
    random.setstate(tuples(state['python']))
    n=state['numpy']; np.random.set_state((n[0],np.array(n[1],dtype=np.uint32),n[2],n[3],n[4]))
    torch.set_rng_state(torch.tensor(state['torch_cpu'],dtype=torch.uint8))
    if state['torch_cuda']:
        require(torch.cuda.is_available(),"DEVICE_UNAVAILABLE","rng","saved CUDA state requires CUDA")
        torch.cuda.set_rng_state_all([torch.tensor(s,dtype=torch.uint8) for s in state['torch_cuda']])


def save_checkpoint(model,directory,config,env,*,seed,label,extra=None):
    directory=Path(directory)
    require(not directory.exists(),"CHECKPOINT_EXISTS","checkpoint","immutable output already exists")
    directory.parent.mkdir(parents=True,exist_ok=True)
    stage=directory.with_name(directory.name+'.partial_'+uuid4().hex); stage.mkdir()
    model.save(stage/'model.zip')
    data={"trainer_version":TRAINER_VERSION,"policy_id":"p04_new_crane_maskableppo_v1","config_hash":config.fingerprint,"interface":interface_candidate(env),"source_sha256":source_snapshot(),"dependency_versions":versions(),"training_seed":seed,"actual_device":str(model.device),"trained_steps":int(model.num_timesteps),"label":label,"resume_mode":"OPTIMIZER_BOUNDARY_EPISODES_RESTART_NOT_BITWISE","model_sha256":__import__('hashlib').sha256((stage/'model.zip').read_bytes()).hexdigest(),"rng":_rng_state(),"extra":extra or {}}
    write_new(stage/'metadata.json',canonical(data))
    # Unique final path; partial directories on failure are retained for inspection.
    stage.rename(directory)
    return data


def load_checkpoint(directory,config,env,*,expected_seed=None,require_trained=False):
    directory=Path(directory); data=strict_json((directory/'metadata.json').read_text(encoding='utf-8'))
    require(data['trainer_version']==TRAINER_VERSION and data['policy_id']=='p04_new_crane_maskableppo_v1' and data['config_hash']==config.fingerprint and data['interface']==interface_candidate(env),"CHECKPOINT_COMPATIBILITY","checkpoint","not the same crane interface/config; never substitute berth PPO")
    require(data['source_sha256']==source_snapshot() and data['dependency_versions']==versions(),"CHECKPOINT_SOURCE","checkpoint","source/dependency drift")
    require(__import__('hashlib').sha256((directory/'model.zip').read_bytes()).hexdigest()==data['model_sha256'],"CHECKPOINT_HASH","model.zip","corruption")
    require(expected_seed is None or data['training_seed']==expected_seed,"CHECKPOINT_SEED","checkpoint","seed mismatch")
    if require_trained: require(data['trained_steps']>0 and data['label']=='OWNER_MANUAL_TRAINING',"NO_TRAINED_CHECKPOINT","checkpoint","smoke is not research training")
    from sb3_contrib import MaskablePPO
    model=MaskablePPO.load(directory/'model.zip',env=env,device=resolve_device(config))
    return model,data


def validate_model(model,problems,config,permit=None):
    """Validation-only selection; never accepts a held-out test role."""
    infos=[]; latencies=[]; waits=0; decisions=0
    for p in problems:
        require(p.metadata.role=='validation',"SPLIT_GUARD","validation","test/development input not eligible for checkpoint selection")
        env=make_env(p,config,permit); obs,info=env.reset(seed=p.metadata.seed)
        require(not info['success'],"ZERO_WORK_SELECTION","validation","exclude empty correctness fixture")
        for _ in range(config.max_episode_steps):
            start=time.perf_counter(); obs=env._observation(); mask=env.action_masks()
            action,_=model.predict(obs,deterministic=True,action_masks=mask)
            latencies.append(time.perf_counter()-start); decisions+=1; waits+=int(action)==0
            obs,_,done,truncated,info=env.step(int(action))
            if done or truncated: break
        infos.append(info)
    require(bool(infos),"EMPTY_VALIDATION","validation","nonempty cohort required")
    valid=[x['makespan_min'] for x in infos if x['success']]
    return {"success_rate":len(valid)/len(infos),"mean_valid_makespan_min":statistics.fmean(valid) if valid else None,"scenario_count":len(infos),"failure_count":len(infos)-len(valid),"wait_fraction":waits/decisions if decisions else None,"decision_latencies_s":latencies,"episodes":infos}


def selection_key(result,step):
    return (1-result['success_rate'],result['mean_valid_makespan_min'] if result['mean_valid_makespan_min'] is not None else float('inf'),step)


def train_manual(payload,approval_path,confirmation,output,*,resume_checkpoint=None,only_seed=None):
    """Foreground only; no call from fixture tests. Failure guards precede learning."""
    token=manual_gate(payload,approval_path,confirmation)
    config=TrainingConfig.from_dict(payload['training_config'])
    project=Path(__file__).resolve().parents[2]
    def inputs(key,role):
        found=[]
        for item in payload[key]:
            path=(project/item['path']).resolve()
            require(path.is_relative_to(project),"INPUT_PATH","path","inputs must be Project04-local")
            problem=QCSPProblem.from_json(path.read_text(encoding='utf-8'))
            require(problem.fingerprint==item['problem_hash'] and problem.metadata.role==role,"INPUT_LOCK",key,"changed input/role")
            found.append(problem)
        require(bool(found),"EMPTY_COHORT",key,"nonempty inputs required")
        return found
    train=inputs('train_inputs','train'); validation=inputs('validation_inputs','validation')
    no_leakage(train+validation)
    permit=ExecutionPermit(token,tuple(p.fingerprint for p in train+validation),('train','validation'))
    for p in train+validation:
        checked=make_env(p,config,permit); _,info=checked.reset(seed=p.metadata.seed)
        require(not info['success'],'ZERO_WORK_SELECTION','cohort','empty correctness cases are not training/selection performance instances')
    out=Path(output); require(not out.exists(),"OUTPUT_EXISTS","output","new run directory required, including resume attempts")
    out.mkdir(parents=True)
    write_new(out/'plan.json',canonical(payload)); write_new(out/'approval_snapshot.json',canonical(strict_json(Path(approval_path).read_text(encoding='utf-8'))))
    from stable_baselines3.common.callbacks import BaseCallback
    from stable_baselines3.common.vec_env import DummyVecEnv, VecEnvWrapper
    import gymnasium as gym
    import numpy as np
    class ScenarioCycle(gym.Env):
        def __init__(self):
            self.index=0; self.env=make_env(train[0],config,permit)
            self.observation_space=self.env.observation_space; self.action_space=self.env.action_space
        def reset(self,*,seed=None,options=None):
            super().reset(seed=seed)
            self.env=make_env(train[int(self.np_random.integers(len(train)))],config,permit)
            return self.env.reset(seed=seed,options=options)
        def step(self,action): return self.env.step(action)
        def action_masks(self): return self.env.action_masks()
    class AbsorbingFailureVec(VecEnvWrapper):
        def reset(self): return self.venv.reset()
        def step_wait(self):
            obs,rewards,dones,infos=self.venv.step_wait()
            for info in infos:
                if not info.get('success',False): info['TimeLimit.truncated']=False
            return obs,rewards,dones,infos
    seeds=(only_seed,) if only_seed is not None else config.seeds
    require(set(seeds)<=set(config.seeds) and (resume_checkpoint is None or len(seeds)==1),"RESUME_SEED","seed","resume exactly one predeclared seed")
    for seed in seeds:
        env=make_env(train[0],config,permit); vector=AbsorbingFailureVec(DummyVecEnv([ScenarioCycle]))
        if resume_checkpoint:
            model,previous=load_checkpoint(resume_checkpoint,config,env,expected_seed=seed,require_trained=True)
            model.set_env(vector); restore_rng(previous['rng'])
        else: model=make_model(vector,config,seed)
        seed_out=out/f'seed_{seed}'; seed_out.mkdir()
        class BoundaryCallback(BaseCallback):
            def __init__(self):
                super().__init__(); self.next_validation=config.validation_interval_steps; self.best=None; self.best_path=None
                if resume_checkpoint:
                    old=previous['extra'].get('validation')
                    if old:
                        self.best=selection_key(old,previous['trained_steps']); self.best_path=str(Path(resume_checkpoint).resolve())
            def _on_step(self): return True
            def boundary(self,force=False):
                step=int(self.model.num_timesteps)
                if not force and (step==0 or step<self.next_validation): return
                rng=_rng_state()
                result=validate_model(self.model,validation,config,permit)
                restore_rng(rng)
                checkpoint=seed_out/f'checkpoint_{step:012d}'
                if checkpoint.exists(): return
                save_checkpoint(self.model,checkpoint,config,env,seed=seed,label='OWNER_MANUAL_TRAINING',extra={'validation':result,'plan_hash':token,'resume_from':str(resume_checkpoint) if resume_checkpoint else None})
                key=selection_key(result,step)
                if self.best is None or key<self.best: self.best=key; self.best_path=str(checkpoint.resolve())
                with (seed_out/'progress.jsonl').open('a',encoding='utf-8') as stream: stream.write(json.dumps({'step':step,'validation':result,'selected_checkpoint':self.best_path})+'\n')
                print(json.dumps({'seed':seed,'step':step,'total':config.total_steps,'validation_success':result['success_rate']}),flush=True)
                self.next_validation=step+config.validation_interval_steps
            def _on_rollout_start(self): self.boundary()
            def _on_training_end(self): self.boundary(force=True)
        callback=BoundaryCallback(); remaining=config.total_steps-int(model.num_timesteps)
        require(remaining>0,"TRAINING_BUDGET_COMPLETE","resume","no remaining steps")
        try:
            model.learn(total_timesteps=remaining,callback=callback,reset_num_timesteps=resume_checkpoint is None)
        except KeyboardInterrupt:
            write_new(seed_out/'INTERRUPTED.json',canonical({'status':'INTERRUPTED_RESUME_LAST_COMPLETE_OPTIMIZER_BOUNDARY','seed':seed,'trained_checkpoint_claim':False}))
            raise
        selection={'status':'TRAINING_COMPLETE_VALIDATION_SELECTED','seed':seed,'plan_hash':token,'selected_checkpoint':callback.best_path,'best_key':callback.best,'source_sha256':source_snapshot(),'test_data_read':False}
        write_new(seed_out/'selection.json',canonical(selection)); vector.close()
    return {'status':'OWNER_MANUAL_TRAINING_COMPLETE','output':str(out)}


def validate_manual(payload,approval_path,confirmation,checkpoint):
    token=manual_gate(payload,approval_path,confirmation)
    from .evaluation import _locked_problem,_local
    config=TrainingConfig.from_dict(payload['training_config'])
    problems=[_locked_problem(item,'validation') for item in payload['validation_inputs']]
    require(bool(problems),"EMPTY_VALIDATION","validation","nonempty locked cohort required")
    permit=ExecutionPermit(token,tuple(p.fingerprint for p in problems),('validation',))
    model,_=load_checkpoint(_local(checkpoint),config,make_env(problems[0],config,permit),require_trained=True)
    return validate_model(model,problems,config,permit)
