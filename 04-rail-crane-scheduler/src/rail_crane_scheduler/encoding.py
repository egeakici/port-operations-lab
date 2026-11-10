"""Versioned fixed tensors and action map; physical rules stay in kernel."""
import numpy as np
from gymnasium import spaces
from .environment import CraneSchedulingEnv
from .contracts import require

OBSERVATION_VERSION="p04_known_geometry_normalized_v1"
ACTION_VERSION="p04_pair_wait_v1"
REWARD_VERSION="p04_undiscounted_elapsed_failure_bound_v1"


class EncodedCraneEnv(CraneSchedulingEnv):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.observation_space=spaces.Dict({"clock":spaces.Box(0,1,(1,),np.float32),"cranes":spaces.Box(0,1,(2,7),np.float32),"tasks":spaces.Box(0,1,(self.capacity,5),np.float32),"task_mask":spaces.MultiBinary(self.capacity),"geometry":spaces.Box(0,1,(3,),np.float32)})

    def _observation(self):
        p=self.problem; raw=self._raw_observation(); span=p.rail.upper_m-p.rail.lower_m
        max_moves=max((t.workload_moves for t in p.tasks),default=1)
        max_rate=max(c.effective_moves_per_hour for c in p.cranes)
        max_speed=max(c.travel_speed_m_per_min for c in p.cranes)
        max_hold=max(span/c.travel_speed_m_per_min+c.setup_min+60*max_moves/c.effective_moves_per_hour for c in p.cranes)
        raw['clock']=(raw['clock']-p.vessel.planning_start_min)/p.rail.horizon_min
        raw['cranes'][:,0]=(raw['cranes'][:,0]-p.rail.lower_m)/span
        raw['cranes'][:,2]/=max_hold
        raw['cranes'][:,3:5]=(raw['cranes'][:,3:5]-p.rail.lower_m)/span
        raw['cranes'][:,5]/=max_speed; raw['cranes'][:,6]/=max_rate
        raw['tasks'][:len(self.jobs),0]=(raw['tasks'][:len(self.jobs),0]-p.rail.lower_m)/span
        raw['tasks'][:,1]/=max_moves
        raw['geometry']=np.array([p.rail.min_clearance_m/span,(p.vessel.orientation+1)/2,p.vessel.length_m/span])
        result={k:(v.astype(np.float32) if v.dtype.kind=='f' else v) for k,v in raw.items()}
        require(self.observation_space.contains(result),"ENCODING_RANGE","observation","unsupported numeric/profile range; no silent clipping")
        return result


def interface_candidate(env):
    return {"status":"PENDING_OWNER_APPROVAL","observation_version":OBSERVATION_VERSION,"action_version":ACTION_VERSION,"reward_version":REWARD_VERSION,"task_capacity":env.capacity,"action_count":int(env.action_space.n),"action_index":"0 WAIT; 1+physical_crane_rank*M+sorted_task_slot","normalization":"known current geometry and workload only; no fitted test statistics","reward_scale_min":env.reward_scale_min,"failure_margin_min":env.failure_margin_min,"gamma_required_for_exact_return":1.,"shaping":"NONE","yield_actions":"UNSUPPORTED; restricted immediate dispatch model"}
