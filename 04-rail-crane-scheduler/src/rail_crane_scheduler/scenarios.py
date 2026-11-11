"""Counter-SHA256 named streams and overwrite-safe fixture-only generation."""
from dataclasses import dataclass, replace
from pathlib import Path
import hashlib
from .contracts import *

GENERATOR_VERSION = "p04_counter_sha256_v2"


class Stream:
    def __init__(self, namespace, seed, name, nonce):
        self.key = canonical([GENERATOR_VERSION, namespace, seed, name, nonce])
        self.counter = 0

    def draw(self, lo, hi):
        require(type(lo) is int and type(hi) is int and lo <= hi, "RNG_RANGE", "stream", "invalid integer range")
        span = hi - lo + 1
        require(span <= 2**256, "RNG_RANGE", "stream", "range too large")
        limit = 2**256 - 2**256 % span
        while True:
            value = int.from_bytes(hashlib.sha256(self.key + str(self.counter).encode("ascii")).digest())
            self.counter += 1
            if value < limit: return lo + value % span


@dataclass(frozen=True)
class GeneratorConfig(Wire):
    schema_version: str
    template: QCSPProblem
    task_count: int
    min_moves: int
    max_moves: int
    bay_jitter_m: float
    geometry_nonce: int
    workload_nonce: int
    positions_nonce: int
    operation_kind: str

    def __post_init__(self):
        super().__post_init__()
        require(self.schema_version == GENERATOR_VERSION, "GENERATOR_VERSION", "config", "unsupported")
        require(0 <= self.task_count <= 32 and 0 < self.min_moves <= self.max_moves and self.bay_jitter_m >= 0, "GENERATOR_RANGE", "config", "bounded fixture config required")
        require(self.template.metadata.family in {"tiny", "small", "medium", "heavy", "dynamic_diagnostic"}, "FAMILY", "config", "unknown family")
        require(bool(self.template.bays) or self.task_count == 0, "NO_BAYS", "config", "jobs require bays")
        require(self.template.metadata.family != "dynamic_diagnostic", "DEFERRED_DYNAMIC", "config", "release/downtime extension not v1")
        require(self.operation_kind in {'LOAD','DISCHARGE'},"GENERATOR_OPERATION","config.operation_kind","explicit operation kind required")


@dataclass(frozen=True)
class GenerationPermit:
    approved_payload_hash: str
    config_hashes: tuple[str, ...]


def generate(config,permit=None):
    p = config.template
    m = p.metadata
    if permit is None:
        require(m.origin=='TEST_FIXTURE_SYNTHETIC' and m.role in {'development','diagnostic'},'PARAMETERS_PENDING','config','automatic generation is development/diagnostic fixture only')
    else:
        require(type(permit) is GenerationPermit and config.fingerprint in permit.config_hashes,'OWNER_APPROVAL_REQUIRED','config','exact configuration must be owner-manual approved')
    streams = {name: Stream(m.seed_namespace, m.seed, name, nonce) for name, nonce in (("geometry", config.geometry_nonce), ("workload", config.workload_nonce), ("positions", config.positions_nonce), ("release", 0))}
    bays = tuple(replace(b, local_m=b.local_m + streams["geometry"].draw(-1000, 1000) * config.bay_jitter_m / 1000, verified_global_m=None) for b in p.bays)
    jobs = tuple(CraneTaskGroup(f"j{i:04d}", p.vessel.vessel_id, bays[streams["positions"].draw(0, len(bays)-1)].bay_id, config.operation_kind, streams["workload"].draw(config.min_moves, config.max_moves), p.vessel.planning_start_min, (), (), ()) for i in range(config.task_count))
    identity = digest([GENERATOR_VERSION, m.seed_namespace, m.seed, m.role, config.fingerprint])
    return replace(p, metadata=replace(m, scenario_id="p04_" + identity[:24]), bays=bays, tasks=jobs, declared_workload_moves=sum(t.workload_moves for t in jobs))


def no_leakage(problems):
    seen = {}
    for p in problems:
        key = p.physical_fingerprint
        require(key not in seen, "SPLIT_LEAKAGE", p.metadata.scenario_id, "duplicate physical input, even under different IDs/roles/seeds")
        seen[key] = p.metadata.role
    return True


def write_new(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(data)


def write_fixture(config, directory):
    problem = generate(config)
    out = Path(directory)
    require(not out.exists(), "OUTPUT_EXISTS", "output", "immutable run directory already exists")
    out.mkdir(parents=True)
    write_new(out / "problem.json", canonical(problem.to_dict()))
    manifest = {"generator_version": GENERATOR_VERSION, "generator_source_sha256":hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "config_hash": config.fingerprint, "problem_hash": problem.fingerprint, "physical_hash": problem.physical_fingerprint, "origin": problem.metadata.origin, "role": problem.metadata.role, "seed_namespace": problem.metadata.seed_namespace, "seed": problem.metadata.seed, "status": "TEST_FIXTURE_NOT_RESEARCH"}
    write_new(out / "manifest.json", canonical(manifest))
    return manifest


def write_fixture_batch(configs, directory):
    """Bounded progress integration for at most eight correctness fixtures."""
    from .progress import Progress
    configs=tuple(configs)
    require(0<len(configs)<=8 and all(c.template.metadata.origin=='TEST_FIXTURE_SYNTHETIC' and
            c.template.metadata.role in {'development','diagnostic'} for c in configs),
            'FIXTURE_BOUND','configs','at most eight development/diagnostic correctness fixtures')
    out=Path(directory)
    require(not out.exists(),'OUTPUT_EXISTS','output','new fixture batch directory required')
    out.mkdir(parents=True)
    manifests=[]
    with Progress(len(configs),'Fixture generation',out) as progress:
        for i,c in enumerate(configs):
            progress.start(family=c.template.metadata.family,role=c.template.metadata.role,validation_failures=0,rejected=0)
            manifest=write_fixture(c,out/f'fixture_{i:03d}')
            manifests.append(manifest)
            progress.advance(family=c.template.metadata.family,role=c.template.metadata.role,validation_failures=0,rejected=0)
    write_new(out/'manifest.json',canonical({'origin':'TEST_FIXTURE_SYNTHETIC','entries':manifests}))
    return manifests


def generate_manual(payload,approval_path,confirmation,directory):
    """Exact owner/source/config gate before generation; not run by development."""
    from .research import manual_gate
    token=manual_gate(payload,approval_path,confirmation)
    configs=tuple(GeneratorConfig.from_dict(raw) for raw in payload['configs'])
    require(bool(configs),'EMPTY_COHORT','configs','nonempty explicit configuration list required')
    permit=GenerationPermit(token,tuple(c.fingerprint for c in configs))
    from .progress import Progress
    out=Path(directory); require(not out.exists(),'OUTPUT_EXISTS','output','new immutable generation directory required')
    out.mkdir(parents=True)
    write_new(out/'plan.json',canonical(payload))
    entries=[]; physical=set()
    with Progress(len(configs),'Manual generation',out) as progress:
        for c in configs:
            progress.start(family=c.template.metadata.family,role=c.template.metadata.role,validation_failures=0,rejected=0)
            try:
                p=generate(c,permit)
                require(p.physical_fingerprint not in physical,'SPLIT_LEAKAGE','generation','duplicate input; no reroll')
                physical.add(p.physical_fingerprint)
                p.require_fixture_execution(ExecutionPermit(token,(p.fingerprint,),(p.metadata.role,)))
                name=p.metadata.scenario_id+'.json'; write_new(out/name,canonical(p.to_dict()))
                entries.append({'file':name,'problem_hash':p.fingerprint,'physical_hash':p.physical_fingerprint,'role':p.metadata.role,'config_hash':c.fingerprint})
                progress.advance(family=p.metadata.family,role=p.metadata.role,validation_failures=0,rejected=0)
            except ContractError as exc:
                progress.record('REJECTED_STOP_NO_REROLL',validation_failures=1,rejected=1,error=str(exc))
                raise
    manifest={'status':'OWNER_MANUAL_INPUT_GENERATION_NOT_SCIENTIFIC_RESULTS','plan_hash':token,'generator_version':GENERATOR_VERSION,'entries':entries}
    write_new(out/'manifest.json',canonical(manifest)); return manifest
