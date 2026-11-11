"""Concrete proposed study, environment verification and strict profile checks.

Construction validates configurations only. It never generates primary tasks.
"""
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from .contracts import *
from .research import source_snapshot
from .scenarios import GeneratorConfig, GENERATOR_VERSION
from .training import TrainingConfig, TRAINER_VERSION

PROJECT = Path(__file__).resolve().parents[2]
PROFILE_PATH = PROJECT/"configs/research/primary_candidate_v1.json"
ENV_LOCK = PROJECT/"configs/research/environment_lock_v1.json"
PACKAGES = ("numpy", "scipy", "pandas", "pytest", "tqdm", "gymnasium", "stable-baselines3",
            "sb3-contrib", "torch", "ortools", "matplotlib", "streamlit", "psutil")


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tooling_snapshot():
    files = [PROJECT/"pyproject.toml", *sorted((PROJECT/"scripts").glob("*.ps1"))]
    return {p.relative_to(PROJECT).as_posix(): file_hash(p) for p in files}


def environment(check_lock=True, *, tensor=True):
    import psutil
    import torch
    versions = {n: importlib.metadata.version(n) for n in PACKAGES}
    properties = {"python": platform.python_version(), "implementation": platform.python_implementation(),
                  "machine": platform.machine(), "system": platform.system(), "packages": versions,
                  "torch_cuda_build": torch.version.cuda, "cuda_available": torch.cuda.is_available()}
    properties['all_distributions']={name:version for name,version in sorted(
        ((d.metadata['Name'].lower().replace('_','-'),d.version) for d in importlib.metadata.distributions()))}
    if check_lock:
        require(properties == strict_json(ENV_LOCK.read_text(encoding="utf-8"))["identity"],
                "ENVIRONMENT_CHANGED", "environment", "rebuild/review exact environment lock")
        expected = PROJECT/".venv-research/Scripts/python.exe"
        require(Path(sys.executable).resolve() == expected.resolve(), "WRONG_ENVIRONMENT", "python", str(expected))
    if tensor:
        x = torch.arange(16, dtype=torch.float32).reshape(4, 4)
        require(float((x@x.T).sum()) == 3680., "TENSOR_CHECK", "cpu", "real CPU matmul failed")
        if torch.cuda.is_available():
            gpu=x.cuda(); torch.cuda.synchronize()
            require(torch.equal((gpu@gpu.T).cpu(), x@x.T), "TENSOR_CHECK", "cuda", "GPU result mismatch")
    return {"status": "VERIFIED", "identity": properties, "executable": sys.executable,
            "selected_device": "cpu", "cuda_policy": "explicit CPU; no fallback",
            "memory_available_bytes": psutil.virtual_memory().available,
            "memory_total_bytes": psutil.virtual_memory().total,
            "disk_free_bytes": shutil.disk_usage(PROJECT).free,
            "logical_cpus": os.cpu_count(), "physical_cpus": psutil.cpu_count(logical=False),
            "nvidia_smi": shutil.which("nvidia-smi"), "cpu_tensor_verified": tensor,
            "cuda_tensor_verified": bool(tensor and torch.cuda.is_available())}


def require_resources(profile):
    info = environment()
    resources = profile["compute"]
    require(info["memory_available_bytes"] >= resources["minimum_available_ram_bytes"],
            "INSUFFICIENT_FREE_RAM", "compute", "close applications; minimum 2 GiB free RAM required")
    require(info["disk_free_bytes"] >= resources["minimum_free_disk_bytes"],
            "INSUFFICIENT_FREE_DISK", "compute", "minimum 10 GiB free required")
    return info


def proposed_profile():
    """All numbers are explicit design choices, not inferred terminal data."""
    return {
        "schema_version": "p04_primary_research_profile_v1", "status": "PROPOSED",
        "study_id": "p04_qcsp_synthetic_v1", "evidence_class": "PROPOSED_SYNTHETIC",
        "source_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "source_revision_kind": "BASE_HEAD_PLUS_APPROVED_CONTENT_HASHES; readiness patch is uncommitted",
        "source_sha256": source_snapshot(), "tooling_sha256": tooling_snapshot(),
        "environment_lock_sha256": file_hash(ENV_LOCK),
        "approval_scope": {
            "decisions": ["O1", "O2", "O3", "O4", "O5", "O6"],
            "operations": ["generation", "baselines", "training", "evaluation", "report"],
            "derived_plan_rule": "p04_exact_campaign_derivation_v1",
            "manual_foreground_only": True,
            "future_bindings": "generated immutable input hashes and validation-only selected checkpoint identities; exact re-derivation required",
            "no_scientific_closure_delegation": True},
        "coordinates": {"origin": "synthetic terminal rail lower endpoint", "positive": "rail left to right",
            "ship_reference": "origin is global hull lower edge; local reference reverses with orientation",
            "conversion": "origin+u if orientation=+1 else origin+length-u", "crane_reference": "rail center reference point",
            "body_dimensions": "DATA_GAP; excluded", "boundaries": "closed space; half-open resource intervals; closed safety",
            "safety_roundoff_policy": "kernel never relaxes d; validator tolerance is comparison error only"},
        "motion": {"model": ASSUMPTIONS, "travel": "straight committed constant speed", "wait": "next strictly later travel/setup/completion event",
            "ties": "settle completions before next dispatch; completion time then crane rank then task id",
            "yield_reposition": "UNSUPPORTED", "preemption": False, "concurrent_safe_cranes": True,
            "task_precedence": "NONE_SUPPORTED_V1", "task_release_min": 0.0},
        "physical": {"crane_count": 2, "rail_lower_m": 0.0, "rail_upper_m": 360.0,
            "vessel_origin_m": 36.0, "vessel_length_m": 288.0, "initial_positions_m": [36.0,324.0],
            "reach_bounds_m": [0.0,360.0], "clearance_m": 24.0, "travel_speed_m_per_min": 45.0,
            "effective_moves_per_hour": 30.0, "setup_min": 1.0, "horizon_min": 17280.0,
            "time_tolerance_min": 1e-8, "position_tolerance_m": 1e-6,
            "available_at_min": 0.0, "planning_start_min": 0.0,
            "bay_jitter_m": 0.0, "orientations": [-1,1], "operation_types": ["LOAD","DISCHARGE"],
            "precedence": [], "workload_distribution": "independent discrete uniform integer per task",
            "task_bay_distribution": "independent discrete uniform; repeated bays allowed; no outcome filtering"},
        "families": {
            "tiny": {"task_count":4,"bay_locations_local_m":[36.0,108.0,180.0,252.0],"min_moves":6,"max_moves":18,"weight":0.25},
            "small": {"task_count":8,"bay_locations_local_m":[float(12+24*i) for i in range(12)],"min_moves":20,"max_moves":60,"weight":0.25},
            "medium": {"task_count":20,"bay_locations_local_m":[float(12+24*i) for i in range(12)],"min_moves":30,"max_moves":90,"weight":0.25},
            "heavy": {"task_count":32,"bay_locations_local_m":[float(12+24*i) for i in range(12)],"min_moves":60,"max_moves":180,"weight":0.25,
                      "clearance_m":36.0,"travel_speed_m_per_min":30.0,"effective_moves_per_hour":24.0}},
        "cohorts": {"train":{"count_per_family":128,"seed_start":100000},
                    "validation":{"count_per_family":32,"seed_start":200000},
                    "test":{"count_per_family":64,"seed_start":300000}},
        "randomness": {"namespace":"p04_qcsp_synthetic_v1", "family_order":["tiny","small","medium","heavy"],
            "family_seed_stride":10000, "geometry_nonce":0,"workload_nonce":0,"positions_nonce":0,
            "generator_version":GENERATOR_VERSION,"orientation_rule":"even seed +1; odd -1",
            "operation_rule":"seed modulo 4 in {0,1}: DISCHARGE; otherwise LOAD",
            "ppo_namespace":"p04_qcsp_synthetic_v1/rl_training_rng"},
        "cp_reference": {"tick_min":1.0/30.0,"wall_limit_s":10.0,"max_nodes":100000},
        "cp_eligibility": {"max_jobs":5,"integer_limit":2**50,"threads":1,"solver_seed":0,
            "no_rounding":True,"complete_enumeration_required":True,"primary_family":"tiny",
            "status_policy":"OPTIMAL only finite model; FEASIBLE incumbent only; UNKNOWN and TIMEOUT distinct; skipped eligibility retained"},
        "training_config": TrainingConfig(TRAINER_VERSION,(1103,2207,3301,4409,5501),32,256,60.,1.,
            1048576,2048,128,10,.0003,1.,.95,.2,.01,.5,.5,(128,128),65536,"cpu",False).to_dict(),
        "rl_contract": {"action_count":65,"decision_limit":256,"learning_rate_schedule":"constant",
            "checkpoint_interval_steps":65536,"normalization":"known-state v1; no fitted statistics; no clipping",
            "clock_scale_min":17280.0,"position_scale_m":360.0,"workload_scale":"scenario maximum original moves",
            "speed_rate_scale":"scenario maximum crane speed and effective rate",
            "remaining_hold_scale":"360/speed+setup+60*max_moves/rate; maximum over cranes",
            "network_activation":"Tanh","optimizer":"Adam; SB3 default epsilon", "adam_epsilon":1e-5,
            "selection":"minimum validation failure rate, then mean valid makespan, then earliest step",
            "seed_selection":"all five seeds retained; never choose best seed",
            "gamma":1.0,"reward":"negative elapsed minutes / 60; terminal failure subtracts (17280+1)/60; no shaping"},
        "analysis": {"primary_metric":"valid_complete_makespan_min", "primary_reference":"balanced_finish_v1",
            "confirmatory_references":["ordered_sweep_v1","nearest_feasible_v1","longest_work_v1","balanced_finish_v1"],
            "bootstrap_seed":7042026,"draws":20000,"confidence":0.95,"minimum_pairs_per_family":60,
            "bootstrap_unit":"scenario within family; same sampled scenarios across all seeds and references",
            "seed_aggregation":"scenario-first arithmetic mean over all five seeds; quality uses common complete intersection of all five seeds and all four comparators",
            "weights":"equal 0.25 families; never weight by successful counts",
            "multiplicity":"Bonferroni eight simultaneous two-sided percentile intervals (four makespan and four failure contrasts) at 99.375%; nominal joint confidence 95%; no unadjusted confirmatory claim",
            "failure_endpoint":"unconditional scenario mean PPO seed failure minus comparator failure; simultaneous intervals also reported",
            "claim_rule":"all per-family support>=60; primary adjusted makespan upper<0 and primary failure-difference upper<=0; otherwise no superiority",
            "cp_comparison":"tiny-only descriptive certified-gap; no confirmatory general optimum claim",
            "latency":"CPU two threads, deterministic sequential; 16 unrecorded inference warmups per model/environment; every measured decision includes encoding+mask+predict; record cold load separately; mean/P95/max",
            "failure_policy":"no imputed makespan; all attempts retained; conditional complete-pair effect and unconditional failures; no rerolls",
            "secondary_metrics":["utilization","idle_crane_min","travel_min","travel_m","completion_moves","decision_latency_s","validator_violations","failures"]},
        "compute": {"device":"cpu","torch_threads":2,"vector_envs":1,"minimum_available_ram_bytes":2147483648,
                    "minimum_free_disk_bytes":10737418240,"estimated_runtime":"UNMEASURED; no optimizer benchmark authorized"},
        "limitations": ["synthetic not terminal calibrated", "reference points exclude crane bodies and boom geometry",
            "no joint reposition/yield, acceleration, downtime, stack precedence or yard coupling", "no real Project I rail/TOS interoperability; DATA_GAP",
            "CP-SAT finite event-dispatch subclass only", "bootstrap is approximate finite-sample uncertainty; no power guarantee"]}


def generator_configs(profile):
    """Expand only immutable parameter contracts; no random workload generation."""
    ph=profile['physical']; r=profile['randomness']
    for role,cohort in profile['cohorts'].items():
        for rank,family in enumerate(r['family_order']):
            f=profile['families'][family]
            for i in range(cohort['count_per_family']):
                seed=cohort['seed_start']+rank*r['family_seed_stride']+i
                meta=ProblemMetadata(SCHEMA,'QCSP_V1',f'proposed_{role}_{family}_{seed}',family,role,
                     r['namespace']+'/'+role+'/'+family,seed,'PROPOSED_SYNTHETIC',ASSUMPTIONS,'Project04',profile['source_revision'])
                vessel=VesselContext('synthetic_vessel','synthetic_berth',ph['vessel_length_m'],ph['vessel_origin_m'],
                                     1 if seed%2==0 else -1,ph['planning_start_min'],None)
                rail=RailGeometry('synthetic_rail','terminal_global_x_m',ph['rail_lower_m'],ph['rail_upper_m'],
                     f.get('clearance_m',ph['clearance_m']),'REFERENCE_POINT',ph['time_tolerance_min'],ph['position_tolerance_m'],ph['horizon_min'])
                cranes=tuple(CraneDefinition(f'QC{k}',rail.rail_id,k,x,*ph['reach_bounds_m'],
                     f.get('travel_speed_m_per_min',ph['travel_speed_m_per_min']),f.get('effective_moves_per_hour',ph['effective_moves_per_hour']),
                     ph['setup_min'],ph['available_at_min']) for k,x in enumerate(ph['initial_positions_m']))
                bays=tuple(BayDefinition(f'B{j:02d}',x,None) for j,x in enumerate(f['bay_locations_local_m']))
                template=QCSPProblem(meta,vessel,rail,cranes,bays,(),0,('min','m','moves','moves/hour'))
                yield GeneratorConfig(GENERATOR_VERSION,template,f['task_count'],f['min_moves'],f['max_moves'],
                    ph['bay_jitter_m'],r['geometry_nonce'],r['workload_nonce'],r['positions_nonce'],'DISCHARGE' if seed%4<2 else 'LOAD')


def validate_profile(profile, *, current=True):
    require(profile['schema_version']=='p04_primary_research_profile_v1' and profile['status']=='PROPOSED',
            'PROFILE_VERSION','profile','candidate must remain proposed; receipt supplies authorization')
    require(profile['approval_scope']['derived_plan_rule']=='p04_exact_campaign_derivation_v1', 'APPROVAL_SCOPE','profile','unknown rule')
    TrainingConfig.from_dict(profile['training_config'])
    require(set(profile['cohorts'])=={'train','validation','test'},'COHORTS','profile','exact roles required')
    require(all(type(c['count_per_family']) is int and c['count_per_family']>0 and type(c['seed_start']) is int and c['seed_start']>=0
                for c in profile['cohorts'].values()),'COHORT_COUNTS','profile','positive explicit counts and nonnegative seed bands')
    require(set(profile['families'])==set(profile['randomness']['family_order']) and len(profile['families'])==4,
            'FAMILY_SET','profile','four unique predeclared families required')
    require(profile['physical']['crane_count']==2 and profile['physical']['horizon_min']>0,'PHYSICAL_PROFILE','profile','unsupported')
    require(profile['training_config']['task_capacity']>=max(f['task_count'] for f in profile['families'].values()),'CAPACITY','profile','no truncation')
    require(profile['training_config']['validation_interval_steps']%profile['training_config']['rollout_steps']==0,'BOUNDARY_INTERVAL','profile','whole optimizer boundaries')
    require(sum(f['weight'] for f in profile['families'].values())==1.,'FAMILY_WEIGHT','profile','sum must equal one')
    require(profile['compute']['device']==profile['training_config']['device']=='cpu' and not profile['training_config']['permit_cpu_fallback']
            and profile['compute']['vector_envs']==1,'DEVICE_PROFILE','profile','reviewed CPU single-vector profile required')
    require(profile['rl_contract']['clock_scale_min']==profile['physical']['horizon_min'] and
            profile['rl_contract']['position_scale_m']==profile['physical']['rail_upper_m']-profile['physical']['rail_lower_m'] and
            profile['rl_contract']['action_count']==1+2*profile['training_config']['task_capacity'] and
            profile['rl_contract']['checkpoint_interval_steps']==profile['training_config']['validation_interval_steps'],
            'INTERFACE_PROFILE','profile','normalization/action/checkpoint values must match implementation')
    require(profile['cp_eligibility']['max_jobs']==5 and profile['cp_eligibility']['threads']==1 and profile['cp_eligibility']['solver_seed']==0
            and 0<profile['cp_reference']['max_nodes']<=100000 and profile['cp_reference']['wall_limit_s']>0 and profile['cp_reference']['tick_min']>0,
            'CP_PROFILE','profile','supported finite reference limits only')
    require(profile['analysis']['draws']>0 and 0<profile['analysis']['confidence']<1 and
            0<profile['analysis']['minimum_pairs_per_family']<=profile['cohorts']['test']['count_per_family'],
            'INFERENCE_PROFILE','profile','positive draws/confidence and feasible support required')
    ids=set(); namespaces=set(); count=0
    for c in generator_configs(profile):
        key=c.template.metadata.seed
        require(key not in ids,'SEED_COLLISION','cohorts','overlapping numeric bands')
        ids.add(key); namespaces.add(c.template.metadata.seed_namespace); count+=1
        require(c.max_moves*60/min(k.effective_moves_per_hour for k in c.template.cranes)*c.task_count+c.task_count*13 < c.template.rail.horizon_min,
                'HORIZON_DESIGN','profile','conservative sequential budget exceeds horizon')
    if current:
        require(profile['source_sha256']==source_snapshot() and profile['tooling_sha256']==tooling_snapshot(), 'SOURCE_CHANGED','profile','review new payload')
        require(profile['environment_lock_sha256']==file_hash(ENV_LOCK),'ENVIRONMENT_CHANGED','profile','lock bytes changed')
    return {'status':'CONFIGURATIONS_VALID_OWNER_APPROVAL_PENDING','profile_sha256':digest(profile),
            'scenario_configs_validated':count,'primary_scenarios_generated':0,'namespaces':sorted(namespaces)}
