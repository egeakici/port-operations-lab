"""Run one required regression snapshot, preserving stdout/stderr, exit code and exact nodes.

Does not generate or evaluate Project I sensitive scenarios. Full Project I slow
tests use only10M development inputs. Project03 selection excludes actual training
and historical held-out readers; safe tests in mixed modules remain included.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from integrated_terminal_pilot.benchmark import step7 as s

UNSAFE_MODULES = {
 'tests/integration/test_dynamic_ppo_integration.py':'real PPO training',
 'tests/integration/test_static_ppo_integration.py':'training fixtures or direct training in every fast test',
 'tests/integration/test_project03_results_release.py':'reads historical held-out warehouse and writes Project03 experiment directories',
 'tests/integration/test_scientific_benchmark_integration.py':'reads real historical held-out campaign records in all fixtures',
}
MIXED = {
 'tests/integration/test_static_ppo_v2_integration.py': ['test_v2_short_training_and_adapter'],
 'tests/unit/test_project03_results.py':['test_frozen_ingest_coverage_and_reconciliation','test_query_guide_sql_runs_as_written','test_source_hash_failure_is_blocking'],
 'tests/integration/test_benchmark_diagnostics_integration.py':['test_step12a_outputs_complete_and_hashed','test_wait_and_agreement_from_locked_records',
     'test_tails_traces_and_static_separation','test_fixture_plan_fixed_and_disjoint_from_test',
     'test_completed_outputs_are_immutable_and_sources_unchanged','test_tiny_bounded_latency_smoke'],
}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',required=True,choices=('unit','focused','project-i-full','project03-fast'))
    p.add_argument('--no-progress', action='store_true')
    p.add_argument('--output-root',type=Path,help='ignored portable bundle; source and test selection stay unchanged')
    a=p.parse_args()
    root=s.ROOT
    if a.output_root:
        from integrated_terminal_pilot.benchmark.step7_workspace import bundle_path
        root=bundle_path(a.output_root)
        # A killed terminal must not cause a second pytest process to duplicate a healthy child.
        import atexit
        lock_dir=root/'regression_workers'/a.suite
        lock_dir.mkdir(parents=True,exist_ok=True)
        lease=s.worker_lock(lock_dir);lease.__enter__()
        atexit.register(lease.__exit__,None,None,None)
    directory=root/'regressions'/(a.suite+'_'+uuid.uuid4().hex[:12])
    directory.mkdir(parents=True)
    temp=(s.PROJECT_ROOT/'experiments/step7_remote_work/tmp' if a.output_root else root/'tmp')/directory.name
    temp.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',
             ITP_RUN_SLOW='1' if a.suite=='project-i-full' else '0',
             ITP_STEP7_TEST_EVENT_LOG=str(directory/'events.jsonl'))
    project03=a.suite=='project03-fast'
    cwd=s.REPO/'03-berth-allocation-lab' if project03 else s.REPO
    args=[sys.executable,'-m','pytest','tests' if project03 else
          'integrated-terminal-pilot/tests/unit/test_step7_campaign.py' if a.suite=='focused' else
          'integrated-terminal-pilot/tests/unit' if a.suite=='unit' else 'integrated-terminal-pilot/tests',
          '-q','-p','no:cacheprovider','-p','integrated_terminal_pilot.benchmark.step7_pytest',
          '--basetemp='+str(temp),'--junitxml='+str(directory/'junit.xml')]
    if project03:
        args+=['-m','not slow']
        args+=['--ignore='+x for x in UNSAFE_MODULES]
        args+=['--deselect='+path+'::'+name for path,names in MIXED.items() for name in names]
    start={'utc':s.now(),'command':args,'cwd':str(cwd),'implementation_digest':s.implementation_digest(),
           'parameter_values_sha256':s.load_generator_config().parameters_fingerprint,'suite':a.suite,
           'excluded_modules':UNSAFE_MODULES if project03 else {},'excluded_nodes':MIXED if project03 else {},
           'scope_note':'all eligible fast tests; no learning or real held-out data access; fake unit-test records allowed'}
    s.seal(directory/'started.json',start)
    print(json.dumps({'log':str(directory/'stdout.log'),'started':start['utc']}),file=sys.stderr,flush=True)
    t=time.perf_counter()
    from integrated_terminal_pilot.benchmark.execution import progress_bar
    observed=0
    last_refresh=time.monotonic()
    pending=''
    cursor=0
    with (directory/'stdout.log').open('xb') as log:
        with progress_bar(None, description=a.suite+' tests', unit='test', enabled=not a.no_progress) as bar:
            completed=subprocess.Popen(args,cwd=cwd,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                while True:
                    events_path=directory/'events.jsonl'
                    if events_path.exists():
                        with events_path.open(encoding='utf-8') as stream:
                            stream.seek(cursor); pending+=stream.read(); cursor=stream.tell()
                        lines=pending.split('\n');pending=lines.pop()
                        for line in lines:
                            event=json.loads(line)
                            if event['kind']=='collection':bar.total=event['collected']
                            if event['kind']=='test':
                                if event['phase']=='teardown':observed+=1
                                bar.set_postfix(model='cpu',sim='CPU',phase=event['phase'],
                                                refresh=False)
                        bar.update(observed-bar.n)
                        # Keep elapsed time visible during a slow test, without
                        # forcing four redraws/second or wrapping long node IDs.
                        if time.monotonic()-last_refresh>=2:
                            bar.refresh();last_refresh=time.monotonic()
                    if completed.poll() is not None:break
                    time.sleep(.25)
            except KeyboardInterrupt:
                # The foreground console also delivers Ctrl+C to pytest. Preserve its teardown/logs.
                try:completed.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    completed.terminate();completed.wait()
    e={'exit_code':completed.returncode,'wall_seconds':time.perf_counter()-t,**start,
       'stdout':(directory/'stdout.log').relative_to(s.PROJECT_ROOT).as_posix(),
       'stdout_sha256':s.file_hash(directory/'stdout.log')}
    junit=directory/'junit.xml'
    if junit.exists():
        tree=ET.parse(junit);cases=tree.findall('.//testcase')
        e.update(collected=len(cases),failed=sum(x.find('failure') is not None for x in cases),
                 errors=sum(x.find('error') is not None for x in cases),
                 skipped=sum(x.find('skipped') is not None for x in cases),
                 junit=junit.relative_to(s.PROJECT_ROOT).as_posix(),junit_sha256=s.file_hash(junit))
        e['passed']=len(cases)-e['failed']-e['errors']-e['skipped']
    events_path=directory/'events.jsonl'
    events=[]
    parse_errors=[]
    for number,line in enumerate(events_path.read_text().splitlines() if events_path.exists() else [],1):
        try:events.append(json.loads(line))
        except json.JSONDecodeError:parse_errors.append(number)
    e['event_log_parse_error_lines']=parse_errors
    if parse_errors and e['exit_code']==0:e['exit_code']=2
    slow={i['nodeid'] for ev in events if ev['kind']=='collection' for i in ev['items'] if i['slow']}
    e['slow_passed']=sum(ev['nodeid'] in slow and ev['kind']=='test' and ev['phase']=='call' and ev['outcome']=='passed'
                         for ev in events if 'nodeid' in ev)
    e['deselected']=sum(len(ev['nodeids']) for ev in events if ev['kind']=='deselected')
    e['event_log_sha256']=s.file_hash(events_path) if events_path.exists() else None
    s.seal(directory/'result.json',e)
    print(json.dumps({'result':str(directory/'result.json'),**{k:e.get(k) for k in
        ('exit_code','collected','passed','failed','errors','skipped','deselected','slow_passed','wall_seconds')}}),flush=True)
    return e['exit_code']


if __name__=='__main__':
    raise SystemExit(main())
