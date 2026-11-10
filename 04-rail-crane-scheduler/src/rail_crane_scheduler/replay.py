"""Read-only replay of independently validated records; no scheduler imports."""
from io import BytesIO
from .contracts import *
from .validator import verify

MAX_UPLOAD_BYTES=10*1024*1024


class Replay:
    def __init__(self,problem,schedule):
        self.problem=problem; self.schedule=schedule
        self.record_metrics=None
        self.verdict=verify(problem,schedule)
        self.motion_safe=not (set(self.verdict.errors)-{'INCOMPLETE_ORIGINAL_WORK'})

    def positions(self,time_min):
        require(self.motion_safe,"UNVERIFIED_MOTION","replay","cannot animate rejected physical path")
        require(self.problem.vessel.planning_start_min<=time_min<=self.schedule.stop_min,"REPLAY_TIME","time_min","outside recorded elapsed window")
        result=[]
        for c in self.problem.cranes:
            x=c.initial_position_m
            for s in sorted((s for s in self.schedule.segments if s.crane_id==c.crane_id),key=lambda s:(s.start_min,s.end_min)):
                if time_min<s.start_min: break
                if time_min<s.end_min:
                    x=s.start_m+(s.end_m-s.start_m)*(time_min-s.start_min)/(s.end_min-s.start_min); break
                x=s.end_m
            result.append(x)
        return tuple(result)

    def gantt(self,task_ids=None):
        require(self.motion_safe,"UNVERIFIED_MOTION","replay","invalid segment truth cannot be reconstructed")
        rows=[]; t0=self.problem.vessel.planning_start_min
        for c in self.problem.cranes:
            cursor=t0
            for s in sorted((s for s in self.schedule.segments if s.crane_id==c.crane_id),key=lambda s:(s.start_min,s.end_min)):
                if s.start_min>cursor: rows.append((c.crane_id,'IDLE',cursor,min(s.start_min,self.schedule.stop_min),None))
                end=min(s.end_min,self.schedule.stop_min)
                if end>s.start_min and (task_ids is None or s.task_id in task_ids): rows.append((c.crane_id,s.mode,s.start_min,end,s.task_id))
                cursor=max(cursor,end)
            if cursor<self.schedule.stop_min: rows.append((c.crane_id,'IDLE',cursor,self.schedule.stop_min,None))
        return tuple(row for row in rows if row[3]>row[2])


def load_replay(problem_bytes,schedule_bytes):
    require(len(problem_bytes)<=MAX_UPLOAD_BYTES and len(schedule_bytes)<=MAX_UPLOAD_BYTES,"FILE_SIZE","upload","maximum 10 MiB per JSON input")
    problem=QCSPProblem.from_json(problem_bytes)
    value=strict_json(schedule_bytes)
    if 'schedule' in value:
        from .baselines import RunRecord
        record=RunRecord.from_dict(value); schedule=record.schedule
    else: schedule=CraneSchedule.from_dict(value)
    replay=Replay(problem,schedule)
    if 'schedule' in value: replay.record_metrics=record.metrics
    return replay


def compare(replays):
    require(bool(replays) and len({r.problem.fingerprint for r in replays})==1,"COMPARISON_INPUT","replays","same scenario/physics/hash required")
    rows=[]
    for r in replays:
        travel_min=travel_m=process=0.
        stop=r.problem.vessel.planning_start_min+r.verdict.makespan_min if r.verdict.valid_complete else r.schedule.stop_min
        if r.motion_safe:
            for s in r.schedule.segments:
                dt=max(0.,min(stop,s.end_min)-max(r.problem.vessel.planning_start_min,s.start_min))
                if s.mode=='PROCESS': process+=dt
                if s.mode=='TRAVEL':
                    travel_min+=dt
                    if s.end_min>s.start_min: travel_m+=abs(s.end_m-s.start_m)*dt/(s.end_min-s.start_min)
        latencies=r.record_metrics.policy_latency_s if r.record_metrics else ()
        horizon=stop-r.problem.vessel.planning_start_min
        rows.append({'policy_id':r.schedule.policy_id,'valid_complete':r.verdict.valid_complete,'makespan_min':r.verdict.makespan_min,'travel_min':travel_min if r.motion_safe else None,'travel_m':travel_m if r.motion_safe else None,'productive_utilization':process/(2*horizon) if r.motion_safe and horizon else None,'recorded_mean_policy_latency_s':sum(latencies)/len(latencies) if latencies else None,'status':r.schedule.outcome,'violations':list(r.verdict.errors)})
    return rows


def gantt_figure(replay,task_ids=None):
    from matplotlib.figure import Figure
    fig=Figure(figsize=(9,3)); ax=fig.subplots()
    colors={'TRAVEL':'#4c78a8','SETUP':'#f2cf5b','PROCESS':'#59a14f','IDLE':'#dddddd'}
    rank={c.crane_id:i for i,c in enumerate(replay.problem.cranes)}
    for cid,mode,start,end,task in replay.gantt(task_ids):
        ax.broken_barh([(start,end-start)],(rank[cid]-.3,.6),facecolors=colors[mode])
        if task and mode=='PROCESS': ax.text((start+end)/2,rank[cid],task,ha='center',va='center',fontsize=8)
    ax.set_yticks(list(rank.values()),list(rank)); ax.set_xlabel('Elapsed simulation time (min)')
    ax.set_title(f'{replay.schedule.policy_id} | {replay.problem.metadata.origin} | complete={replay.verdict.valid_complete}')
    ax.axvline(replay.schedule.stop_min,color='black',linestyle='--')
    fig.tight_layout(); return fig


def rail_figure(replay,time_min):
    from matplotlib.figure import Figure
    positions=replay.positions(time_min); p=replay.problem
    fig=Figure(figsize=(9,2.5)); ax=fig.subplots()
    ax.plot([p.rail.lower_m,p.rail.upper_m],[0,0],color='gray')
    for b in p.bays:
        x=local_to_global(p.vessel,b.local_m); ax.axvline(x,color='gray',alpha=.2); ax.text(x,.6,b.bay_id,ha='center')
    ax.scatter(positions,[0,0],s=100,c=['#4c78a8','#e15759'])
    for x,c in zip(positions,p.cranes): ax.text(x,-.3,c.crane_id,ha='center')
    ax.set_xlim(p.rail.lower_m,p.rail.upper_m); ax.set_ylim(-.6,1); ax.set_yticks([])
    ax.set_xlabel('Global quay rail position (m)'); ax.set_title(f't={time_min:g} min; gap={positions[1]-positions[0]:g} m; required={p.rail.min_clearance_m:g} m')
    fig.tight_layout(); return fig


def png_bytes(figure):
    out=BytesIO(); figure.savefig(out,format='png',dpi=100); return out.getvalue()
