"""Gymnasium API over the authoritative fixture kernel, never a second clock."""
import numpy as np
import gymnasium as gym
from gymnasium import spaces
from .contracts import *
from .kernel import CraneSchedulingKernel
from .validator import verify

ENVIRONMENT_VERSION="p04_crane_env_fixture_v1"


class CraneSchedulingEnv(gym.Env):
    metadata={"render_modes":["ansi"],"render_fps":1}

    def __init__(self,problem,*,task_capacity,max_steps,reward_scale_min,failure_margin_min,invalid_action_mode,render_mode=None,permit=None):
        problem.require_fixture_execution(permit)
        self.permit=permit
        require(type(task_capacity) is int and task_capacity>=max(1,len(problem.tasks)),"UNSUPPORTED_PROFILE","task_capacity","no silent mandatory job truncation")
        require(type(max_steps) is int and max_steps>0 and all(type(x) in (int,float) and math.isfinite(x) and x>0 for x in (reward_scale_min,failure_margin_min)),"ENV_CONFIG","environment","explicit finite positive limits/scales required")
        require(invalid_action_mode in {"raise","truncate"} and render_mode in {None,"ansi"},"ENV_CONFIG","environment","unsupported rejection/render mode")
        self.problem=problem; self.capacity=task_capacity; self.max_steps=max_steps
        self.reward_scale_min=float(reward_scale_min); self.failure_margin_min=float(failure_margin_min)
        self.invalid_action_mode=invalid_action_mode; self.render_mode=render_mode
        self.jobs=tuple(sorted(problem.tasks,key=lambda t:t.task_id))
        self.action_space=spaces.Discrete(1+2*task_capacity)
        bound=np.finfo(np.float32).max
        self.observation_space=spaces.Dict({"clock":spaces.Box(0,bound,(1,),np.float32),"cranes":spaces.Box(-bound,bound,(2,7),np.float32),"tasks":spaces.Box(-bound,bound,(task_capacity,5),np.float32),"task_mask":spaces.MultiBinary(task_capacity)})
        self.kernel=None; self.steps=0; self._done=True

    def reset(self,*,seed=None,options=None):
        super().reset(seed=seed)
        require(not options,"RESET_OPTIONS","options","no hidden scenario replacement")
        self.kernel=CraneSchedulingKernel(self.problem,self.permit); self.steps=0
        if self.kernel.status=="RUNNING" and not self.kernel.legal_pairs() and not self.kernel.can_wait():
            raise ContractError("DEADLOCK_INITIAL","problem","unsolved under declared dispatch action model")
        self._done=self.kernel.status=="COMPLETED"
        return self._observation(),self._info()

    def decode(self,index):
        require(isinstance(index,(int,np.integer)) and not isinstance(index,(bool,np.bool_)) and 0<=index<self.action_space.n,"ACTION_INDEX","action","out of range")
        if index==0: return SchedulingDecision("WAIT",None,None)
        crane,slot=divmod(int(index)-1,self.capacity)
        require(slot<len(self.jobs),"PADDING_ACTION","action","no task in slot")
        return SchedulingDecision("ASSIGN_TASK",self.problem.cranes[crane].crane_id,self.jobs[slot].task_id)

    def action_masks(self):
        require(self.kernel is not None,"RESET_REQUIRED","environment","reset first")
        mask=np.zeros(self.action_space.n,dtype=bool)
        if self._done: return mask
        mask[0]=self.kernel.can_wait()
        for k,c in enumerate(self.problem.cranes):
            for slot,t in enumerate(self.jobs): mask[1+k*self.capacity+slot]=self.kernel.legal_pair(c.crane_id,t.task_id)
        return mask

    def _raw_observation(self):
        k=self.kernel; crane_features=[]; task_features=np.zeros((self.capacity,5),dtype=np.float64)
        for c in self.problem.cranes:
            left=max([0.]+[r.completion_min-k.time for r in k.records if r.crane_id==c.crane_id])
            crane_features.append([k.position(c.crane_id),float(not k.busy(c.crane_id) and c.available_at_min<=k.time),left,c.reach_lower_m,c.reach_upper_m,c.travel_speed_m_per_min,c.effective_moves_per_hour])
        assigned={r.task_id:r for r in k.records}
        for i,t in enumerate(self.jobs):
            r=assigned.get(t.task_id); remaining=float(t.workload_moves)
            if r:
                c=k._cranes[r.crane_id]
                remaining=max(0.,t.workload_moves-max(0.,min(k.time,r.completion_min)-r.process_start_min)*c.effective_moves_per_hour/60)
            task_features[i]=[k._bayx[t.bay_id],remaining,float(t.release_min<=k.time and t.task_id not in assigned),float(t.task_id in assigned),float(t.task_id in k.completed)]
        visible=np.zeros(self.capacity,dtype=np.int8); visible[:len(self.jobs)]=1
        return {"clock":np.array([k.time],dtype=np.float64),"cranes":np.asarray(crane_features,dtype=np.float64),"tasks":task_features,"task_mask":visible}

    def _observation(self):
        result={k:(v.astype(np.float32) if v.dtype.kind=='f' else v) for k,v in self._raw_observation().items()}
        require(all(np.isfinite(v).all() for v in result.values()),"OBSERVATION_OVERFLOW","observation","cannot represent features in float32")
        return result

    def _info(self):
        complete=self.kernel.status=="COMPLETED"
        verdict=verify(self.problem,self.kernel.schedule(),permit=self.permit) if complete else None
        return {"problem_hash":self.problem.fingerprint,"environment_version":ENVIRONMENT_VERSION,"status":self.kernel.status,"success":bool(verdict and verdict.valid_complete),"makespan_min":verdict.makespan_min if verdict else None,"completed_jobs":len(self.kernel.completed),"original_jobs":len(self.problem.tasks)}

    def step(self,action):
        require(self.kernel is not None and not self._done,"EPISODE_ENDED","environment","reset required")
        before=self.kernel.time
        try:
            decision=self.decode(action)
            require(self.action_masks()[int(action)],"ILLEGAL_ACTION","action","masked action")
            self.kernel.step(decision)
        except ContractError as exc:
            if self.invalid_action_mode=="raise": raise
            self._done=True
            info=self._info(); info.update(status="INVALID_ACTION",success=False,error_code=exc.code)
            return self._observation(),-(self.problem.rail.horizon_min+self.failure_margin_min)/self.reward_scale_min,False,True,info
        self.steps+=1
        if self.kernel.status=="RUNNING" and not self.kernel.legal_pairs() and not self.kernel.can_wait(): self.kernel.mark_deadlock()
        terminated=self.kernel.status=="COMPLETED"
        truncated=not terminated and (self.kernel.status!="RUNNING" or self.steps>=self.max_steps)
        reward=-(self.kernel.time-before)/self.reward_scale_min
        if truncated: reward-=(self.problem.rail.horizon_min+self.failure_margin_min)/self.reward_scale_min
        self._done=terminated or truncated
        info=self._info()
        if terminated: require(info['success'],'PHYSICAL_VALIDATION_FAILURE','episode','kernel completion must independently validate')
        if truncated and self.kernel.status=="RUNNING": info.update(status="TRUNCATED_STEP_LIMIT",success=False)
        return self._observation(),float(reward),terminated,truncated,info

    def render(self):
        return "reset required" if self.kernel is None else f"{self.kernel.time:g} min | {self.kernel.status} | completed {len(self.kernel.completed)}/{len(self.jobs)}"


def masked_rollout(env,seed):
    observation,info=env.reset(seed=seed); rng=np.random.default_rng(seed); total=0.
    if info['success']: return total,info
    for _ in range(env.max_steps):
        choices=np.flatnonzero(env.action_masks())
        require(len(choices)>0,"NO_LEGAL_ACTION","environment","nonterminal empty mask")
        observation,reward,terminated,truncated,info=env.step(int(rng.choice(choices))); total+=reward
        if terminated or truncated: return total,info
    raise ContractError("PROGRESS_BOUND","environment","rollout failed finite bound")
