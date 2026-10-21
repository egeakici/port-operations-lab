"""Owner-started foreground pipeline and portable return verification. No scheduler."""
import gzip
import importlib.util
import json
import os
from pathlib import Path
import pstats
import shutil
import subprocess
import sys
import threading
import time
import traceback
import uuid

from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.execution import progress_bar,finish_current_episode_on_interrupt,device_info,ManualStop
from integrated_terminal_pilot.benchmark.step7_inputs import install,historical_audit,safe_path,normalized_sha,MANIFEST
from integrated_terminal_pilot.benchmark.step7_workspace import configure


Interrupted=ManualStop


def script_module(name):
    path=s.PROJECT_ROOT/'scripts'/(name+'.py')
    spec=importlib.util.spec_from_file_location('step7_manual_'+name,path)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m


def pointer(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,sort_keys=True,indent=2),encoding='utf-8')
    os.replace(temp,path)


def state(root,status,**data):
    value=dict(status=status,utc=s.now(),**data)
    s.seal(root/'pipeline/states'/(s.digest(value)+'.json'),value)
    pointer(root/'pipeline_status.json',value)


def child(args,root,name,stop):
    """Foreground child; tee both byte streams to terminal and exclusive logs."""
    if stop.is_set():raise Interrupted('stopped before child admission')
    d=root/'pipeline/logs'/(name+'_'+uuid.uuid4().hex[:12]);d.mkdir(parents=True)
    command=[sys.executable,*map(str,args)]
    s.seal(d/'command.json',dict(command=command,cwd=str(s.REPO),utc=s.now()))
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',
             ITP_TQDM_COLUMNS=str(shutil.get_terminal_size().columns))
    process=subprocess.Popen(command,cwd=s.REPO,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    def tee(pipe,path,terminal):
        with path.open('xb') as log:
            while True:
                block=pipe.read1(8192)
                if not block:break
                log.write(block);log.flush()
                try:terminal.buffer.write(block);terminal.flush()
                except (BrokenPipeError,OSError):pass
    readers=[threading.Thread(target=tee,args=(process.stdout,d/'stdout.log',sys.stdout)),
             threading.Thread(target=tee,args=(process.stderr,d/'stderr.log',sys.stderr))]
    for t in readers:t.start()
    # Ctrl+C is delivered to the foreground process group. The first parent signal
    # sets stop; campaign children seal their current episode, regression children exit.
    code=process.wait()
    for t in readers:t.join()
    s.seal(d/'exit.json',dict(exit_code=code,utc=s.now(),stdout_sha256=s.file_hash(d/'stdout.log'),
                            stderr_sha256=s.file_hash(d/'stderr.log')))
    if code in (130,-2) or stop.is_set():raise Interrupted('manual foreground interruption; evidence preserved')
    if code:raise s.CampaignError(f'{name} exited {code}; logs {d.relative_to(root)}')
    return d


def snapshot(root):
    paths=s.source_manifest()
    for rel,sha in paths.items():
        target=safe_path(root/'source_snapshot',rel);target.parent.mkdir(parents=True,exist_ok=True)
        if target.exists():
            if s.file_hash(target)!=sha:raise s.CampaignError('source snapshot collision')
        else:
            with target.open('xb') as f:f.write((s.REPO/rel).read_bytes())
    freeze_path=root/'requirements_execution.txt'
    freeze=subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,check=True)
    if freeze_path.exists():
        if freeze_path.read_bytes()!=freeze.stdout:raise s.CampaignError('partial session environment differs')
    else:
        with freeze_path.open('xb') as f:f.write(freeze.stdout)
    meta=dict(schema='step7_remote_session_v1',head=s.git('rev-parse','HEAD'),source_sha256=paths,
        implementation_digest=s.implementation_digest(),parameter_values_sha256=s.load_generator_config().parameters_fingerprint,
        runtime=s.runtime(),hardware=device_info('cpu',torch_info=True),transport_manifest_sha256=s.file_hash(MANIFEST),
        free_disk_bytes=shutil.disk_usage(root).free,
        requirements_sha256=s.file_hash(freeze_path),
        protocol='140 scenarios; 1960 episodes; QC8; frozen CPU A3; K5-A; validation then test; Step8 NO')
    s.seal(root/'session.json',meta)
    return meta


def verify_session(root):
    meta=s.unseal(root/'session.json');s.assert_clean()
    if s.file_hash(root/'requirements_execution.txt')!=meta['requirements_sha256']:
        raise s.CampaignError('execution environment receipt changed')
    if meta['source_sha256']!=s.source_manifest() or meta['runtime']['packages']!=s.runtime()['packages']:
        raise s.CampaignError('execution source/dependency drift; no scientific run admitted')
    s.git('merge-base','--is-ancestor',meta['head'],'HEAD')
    return meta


def retain_prelock_failure(root):
    """Link the demonstrated failed pre-lock attempt; never hide or retry it."""
    for prior_name in ('campaign_final_v3','step7_cpu3132_v1'):
        original=s.PROJECT_ROOT/'experiments/step7_remote'/prior_name
        if root==original:continue
        if (original/'protocol_lock_v1.json').exists():
            raise s.CampaignError('prior campaign reached a scientific lock; preserve it for deviation review')
        if not (original/'pipeline/FAILED.json').exists():continue
        if prior_name=='step7_cpu3132_v1':
            failure=s.unseal(original/'pipeline/FAILED.json')
            results=list((original/'regressions').glob('project03-fast_*/result.json'))
            if failure.get('stage')!='project03-fast' or len(results)!=1:
                raise s.CampaignError('prior failure differs from the reviewed Project03 eligibility defect')
            result=s.unseal(results[0]);details=result.get('failure_details',[])
            classes=[row.get('classname') for row in details]
            if (any(result.get(key)!=value for key,value in
                    dict(exit_code=1,collected=426,passed=420,failed=6,errors=0).items()) or
                classes.count('tests.integration.test_replay_frontend')!=1 or
                classes.count('tests.integration.test_replay_records')!=5 or len(classes)!=6):
                raise s.CampaignError('prior Project03 failure is outside the reviewed six archive-consumer failures')
        audit=[]
        patterns=('pipeline/FAILED.json*','pipeline/stages/*.json*','session.json*',
                  'requirements_execution.txt','numerical_environment.json*','source_snapshot/**/*',
                  'regressions/*/result.json*','regressions/*/junit.xml','regressions/*/stdout.log')
        for pattern in patterns:
            for path in sorted(original.glob(pattern)):
                if not path.is_file():continue
                rel=path.relative_to(original);target=root/'prelock_repair'/('prior_'+prior_name)/rel
                target.parent.mkdir(parents=True,exist_ok=True)
                sha=s.file_hash(path)
                if target.exists():
                    if s.file_hash(target)!=sha:raise s.CampaignError('prior failure evidence differs; never overwrite')
                else:
                    with target.open('xb') as stream:stream.write(path.read_bytes())
                audit.append(dict(path=rel.as_posix(),sha256=sha))
        s.seal(root/'prelock_repair'/('prior_'+prior_name+'_link.json'),dict(
            source=original.relative_to(s.PROJECT_ROOT).as_posix(),files=audit,
            scope='pre-lock implementation/eligibility repair; prior results retained, not reused as current-source PASS; same scientific inventory'))


def regression(root,suite,stop):
    # Recover a sealed success when the terminal died after pytest finished but
    # before the stage receipt was installed. Never rerun completed verification.
    results=sorted((root/'regressions').glob(suite+'_*/result.json'))
    good=[]
    for p in results:
        e=s.unseal(p)
        if e['implementation_digest']!=s.implementation_digest():raise s.CampaignError('regression source drift')
        if e['exit_code'] or e.get('failed') or e.get('errors'):
            raise s.CampaignError('failed regression attempt preserved; inspect, no automatic retry')
        if e.get('passed') and s.file_hash(s.PROJECT_ROOT/e['stdout'])==e['stdout_sha256'] and s.file_hash(s.PROJECT_ROOT/e['junit'])==e['junit_sha256']:
            good.append(p)
    if not good:
        child([s.PROJECT_ROOT/'scripts/verify_step7_regressions.py','--suite',suite,'--output-root',root],root,suite,stop)
        return regression(root,suite,stop)
    if len(good)!=1:raise s.CampaignError('ambiguous regression evidence; inspect instead of selecting a favorable attempt')
    return dict(result=good[0].relative_to(s.PROJECT_ROOT).as_posix(),sha256=s.file_hash(good[0]))


def record_existing_owner(root):
    e=root/'inputs/prerequisites/evidence';ctx=s.read_json(e/'owner_context.json')
    message=(e/'owner_reply.txt').read_text(encoding='utf-8')
    if (ctx['owner_answer_verbatim']!='1' or ctx['packet_sha256']!=s.digest(s.unseal(s.PACKET)) or
        ctx['displayed_option_1']!='Approve all 28 exact packet values as uncalibrated synthetic v1'):
        raise s.CampaignError('actual owner approval context mismatch')
    register=root/'inputs/approved_generator_decisions.yaml'
    if s.APPROVAL.exists():s.require_owner();return {'approval_sha256':s.digest(s.unseal(s.APPROVAL))}
    history=root/'inputs/approval_history'
    if history.exists() and list(history.iterdir()):
        raise s.CampaignError('partially recorded approval; preserve and inspect, never replace')
    original=s.PROJECT_ROOT/'configs/generator/itp_generator_v1_decisions.yaml'
    if register.exists():
        if s.file_hash(register)!=s.file_hash(original):raise s.CampaignError('partial approved register needs inspection')
    else:register.write_bytes(original.read_bytes())
    result=script_module('record_step7_owner_approval').record(message,ctx['date'],ctx['source'],ctx['packet_sha256'],
        s.PENDING_IDS,register_path=register,approval_path=s.APPROVAL,history_root=history)
    s.seal(history/'owner_context.json',ctx);s.require_owner()
    return result


def profiled_split(root,plan_path,split,stop):
    plan=s.load_plan(plan_path);d=plan_path.parent
    targets=[r for r in plan['rows'] if r['split']==split]
    before={r['row_id'] for r in targets if s.run_path(d,r).exists()}
    inv=root/'profiles'/(split+'_'+uuid.uuid4().hex);inv.mkdir(parents=True)
    s.seal(inv/'started.json',dict(split=split,rows_existing_before=sorted(before),utc=s.now()))
    try:
        child(['-m','cProfile','-o',inv/'cpu.prof',s.PROJECT_ROOT/'scripts/run_step7_campaign.py',
               '--bundle',root,'--resume','--plan-file',plan_path,'--split',split,'--device','cpu'],root,split,stop)
    finally:
        newly=[r for r in targets if r['row_id'] not in before and s.run_path(d,r).exists()]
        profile=inv/'cpu.prof'
        if profile.exists():
            stats=pstats.Stats(str(profile))
            calls=sum(v[1] for k,v in stats.stats.items() if k[2]=='_process' and k[0].replace('\\','/').endswith('/simulator/kernel.py'))
            outer=0
            for r in newly:
                e=s.unseal(s.run_path(d,r))
                for tr in e.get('traces',[]):
                    if Path(tr['path']).name=='events.jsonl.gz':
                        with gzip.open(safe_path(d,tr['path']),'rb') as f:outer+=sum(1 for _ in f)
            if calls<outer:raise s.CampaignError('profiler outer/inner event accounting mismatch')
            partial=[r['row_id'] for r in targets if r['row_id'] not in before and
                     s.run_path(d,r).with_suffix('.started.json').exists() and not s.run_path(d,r).exists()]
            s.seal(inv/'result.json',dict(profile_sha256=s.file_hash(profile),newly_executed=[r['row_id'] for r in newly],
                physical_process_calls=calls,outer_event_lines=outer,physical_inner_events=None if partial else calls-outer,
                incomplete_episode_ids=partial,
                scope='invocation totals; not per candidate; profiling overhead included; partial episodes prevent inner/outer partition'))
        else:
            s.seal(inv/'missing.json',dict(newly_executed=[r['row_id'] for r in newly],status='PROFILE_UNAVAILABLE'))
    return dict(split=split,profile=inv.relative_to(root).as_posix())


def export_manifest(root,plan_path):
    coverage=s.progress(plan_path,authorized=True)
    if coverage['status']!='COMPLETE':raise s.CampaignError('all predeclared rows must be accounted before final export')
    files={}
    selected=[p for p in root.rglob('*') if p.is_file() and p.relative_to(root).parts[0] not in ('driver','return_verification')
              and p.name not in ('pipeline_status.json','transfer_manifest.json','transfer_manifest.json.sha256.json')]
    with progress_bar(len(selected),description='Seal portable result folder',unit='file') as bar:
        for p in sorted(selected):
            files[p.relative_to(root).as_posix()]={'sha256':s.file_hash(p),'bytes':p.stat().st_size};bar.update(1)
    manifest=dict(schema='step7_transfer_manifest_v1',plan=plan_path.relative_to(root).as_posix(),
        plan_sha256=s.digest(s.unseal(plan_path)),lock_sha256=s.file_hash(s.FORMAL_LOCK_PATH),
        session_sha256=s.file_hash(root/'session.json'),coverage=coverage['counts'],files=files,
        source_revision=s.read_json(s.FORMAL_LOCK_PATH)['source_revision'],step8_started=False)
    s.seal(root/'transfer_manifest.json',manifest)
    return manifest


def run(root):
    root=configure(root);root.mkdir(parents=True,exist_ok=True)
    if (root/'transfer_manifest.json').exists():
        return verify_return(root)
    (root/'driver').mkdir(exist_ok=True)
    with s.worker_lock(root/'driver'),finish_current_episode_on_interrupt() as stop:
        if (root/'pipeline/FAILED.json').exists():raise s.CampaignError('prior failure preserved; scientific review required')
        s.assert_clean()
        from integrated_terminal_pilot.benchmark.step7_environment import verify as verify_environment
        environment=verify_environment();install(root);retain_prelock_failure(root)
        from integrated_terminal_pilot.benchmark.step7_regression_scope import audit as scope_audit
        s.seal(root/'regression_scope.json',scope_audit(s.REPO/'03-berth-allocation-lab'))
        s.seal(root/'numerical_environment.json',environment)
        if (root/'session.json').exists():verify_session(root)
        else:snapshot(root)
        print(json.dumps({'execution_hardware':s.unseal(root/'session.json')['hardware'],
            'scientific_device':'CPU; one outer worker and one Torch inference thread',
            'progress':'tqdm stages, tests and accounted episodes; elapsed/ETA/throughput; heartbeat every15s'}),flush=True)
        names=['prerequisites','workflow','hardware-diagnostic','project03-fast','project-i-full','regression-evidence','owner-approval','readiness','plan-lock',
               'validation','test','descriptive-report','detailed-diagnostics']
        values={}
        for stage_index,name in enumerate(names,1):
            print(f'\n[Step 7 {stage_index}/{len(names)}] {name}',flush=True)
            if stop.is_set():raise Interrupted('stopped before next stage')
            verify_session(root)
            receipt=root/'pipeline/stages'/(name+'.json')
            if receipt.exists():
                values[name]=s.unseal(receipt)['value'];print('Verified completed stage; skipped.',flush=True);continue
            state(root,'RUNNING',stage=name)
            started=time.perf_counter()
            try:
                if name=='hardware-diagnostic':
                    from integrated_terminal_pilot.benchmark.device_benchmark import benchmark
                    value=benchmark(output_root=root/'hardware')
                    value['result']=Path(value['result']).relative_to(root).as_posix()
                elif name in ('prerequisites','workflow','project-i-full','project03-fast'):value=regression(root,name,stop)
                elif name=='regression-evidence':
                    value=script_module('assemble_step7_regressions').assemble(
                        s.PROJECT_ROOT/values['project-i-full']['result'],s.PROJECT_ROOT/values['project03-fast']['result'])
                    # Keep all generated evidence inside the copyable bundle (s.ROOT is configured).
                    value={'evidence':Path(value['evidence']).relative_to(s.PROJECT_ROOT).as_posix(),
                           'canonical_sha256':value['canonical_sha256']}
                elif name=='owner-approval':value=record_existing_owner(root)
                elif name=='readiness':
                    audit=historical_audit(root);s.seal(root/'readiness_manifest.json',audit)
                    costs=s.unseal(root/'inputs/prerequisites/evidence/cost_model.json')
                    print(json.dumps({'stage':'pre-lock resource estimate','measured_development_proxy':costs,
                        'current_free_disk_bytes':shutil.disk_usage(root).free,
                        'limits':'No guaranteed runtime/disk bound; new lossless observation/trace layout; '
                                 'report reconstruction and other arms add real costs; no admission deadline.'}),flush=True)
                    value={'sha256':s.digest(audit)}
                elif name=='plan-lock':
                    plan_path=s.write_plan()
                    if not s.FORMAL_LOCK_PATH.exists():s.create_lock(plan_path,s.PROJECT_ROOT/values['regression-evidence']['evidence'])
                    s.verify_lock(plan_path)
                    value=dict(plan=plan_path.relative_to(root).as_posix(),lock_sha256=s.file_hash(s.FORMAL_LOCK_PATH))
                elif name in ('validation','test'):
                    value=profiled_split(root,root/values['plan-lock']['plan'],name,stop)
                elif name=='descriptive-report':
                    from integrated_terminal_pilot.benchmark.step7_report import report
                    value=report(root/values['plan-lock']['plan'],stop_requested=stop)
                    value['report']=Path(value['report']).relative_to(root).as_posix()
                else:
                    from integrated_terminal_pilot.benchmark.step7_diagnostics import report
                    value=report(root/values['plan-lock']['plan'],stop_requested=stop);value['report']=Path(value['report']).relative_to(root).as_posix()
                if stop.is_set():raise Interrupted('stopped after current stage')
                s.seal(receipt,dict(value=value,wall_seconds=time.perf_counter()-started,utc=s.now()))
                values[name]=value
            except Interrupted:
                state(root,'INTERRUPTED_PRESERVED',stage=name);raise
            except BaseException as exc:
                s.seal(root/'pipeline/FAILED.json',dict(stage=name,reason=f'{type(exc).__name__}: {exc}',
                    traceback=traceback.format_exc(),utc=s.now()))
                state(root,'BLOCKED_PRESERVED',stage=name,reason=str(exc));raise
            print(f'[Step 7 {stage_index}/{len(names)}] {name}: completed',flush=True)
        plan_path=root/values['plan-lock']['plan']
        s.verify_lock(plan_path)
        from integrated_terminal_pilot.benchmark.step7_export import finalize
        finalize(root,plan_path,values)
        state(root,'SEALING_RESULTS',planned=1960,folder=str(root),step8_started=False)
        manifest=export_manifest(root,plan_path)
        pointer(root/'pipeline_status.json',dict(status='READY_TO_COPY',planned=1960,folder=str(root),step8_started=False,utc=s.now()))
        return dict(status='READY_TO_COPY',bundle=str(root),coverage=manifest['coverage'],
                    manifest_sha256=s.digest(manifest),step8_started=False)


def verify_return(root):
    """Audit archived bytes only; no model load, pickle, simulation or live package-match requirement."""
    root=configure(root);manifest=s.unseal(root/'transfer_manifest.json')
    if manifest.get('schema')!='step7_transfer_manifest_v1':raise s.CampaignError('unknown return manifest')
    with progress_bar(len(manifest['files']),description='Verify copied files',unit='file') as bar:
        for name,info in manifest['files'].items():
            p=safe_path(root,name)
            if p.stat().st_size!=info['bytes'] or s.file_hash(p)!=info['sha256']:
                raise s.CampaignError('copied artifact missing/corrupted: '+name)
            bar.update(1)
    lock=s.read_json(s.FORMAL_LOCK_PATH);meta=s.unseal(root/'session.json')
    if s.file_hash(s.FORMAL_LOCK_PATH)!=manifest['lock_sha256'] or s.file_hash(root/'session.json')!=manifest['session_sha256']:
        raise s.CampaignError('return lock/session mismatch')
    if s.FORMAL_LOCK_PATH.with_suffix('.json.sha256').read_text().split()[0]!=s.file_hash(s.FORMAL_LOCK_PATH):
        raise s.CampaignError('return lock sidecar mismatch')
    newline_only=[]
    if set(s.source_manifest())!=set(lock['source_sha256']):
        raise s.CampaignError('local protected-source inventory differs from execution snapshot')
    if lock['source_revision']!=meta['head'] or manifest['source_revision']!=meta['head']:
        raise s.CampaignError('source revision provenance mismatch')
    for rel,sha in lock['source_sha256'].items():
        archived=safe_path(root/'source_snapshot',rel)
        if s.file_hash(archived)!=sha or meta['source_sha256'].get(rel)!=sha:
            raise s.CampaignError('execution source snapshot corrupted')
        current=safe_path(s.REPO,rel)
        if s.file_hash(current)!=sha:
            if normalized_sha(current)!=normalized_sha(archived):raise s.CampaignError('return source content differs: '+rel)
            newline_only.append(rel)
    if s.digest(s.require_owner())!=lock['owner_approval_sha256'] or s.file_hash(root/'inputs/approved_generator_decisions.yaml')!=lock['effective_register_sha256']:
        raise s.CampaignError('archived owner approval mismatch')
    transport=s.unseal(MANIFEST)
    if s.file_hash(MANIFEST)!=meta['transport_manifest_sha256'] or transport['checkpoints']!=lock['checkpoints']:
        raise s.CampaignError('checkpoint/transport inventory mismatch')
    for name,entry in transport['files'].items():
        if s.file_hash(safe_path(root/'inputs/prerequisites',name))!=entry['sha256']:
            raise s.CampaignError('returned authentic prerequisite differs: '+name)
    approval=s.require_owner();context=s.read_json(root/'inputs/prerequisites/evidence/owner_context.json')
    if (approval['verbatim_message']!=(root/'inputs/prerequisites/evidence/owner_reply.txt').read_text(encoding='utf-8') or
        approval['date']!=context['date'] or approval['source']!=context['source']):
        raise s.CampaignError('approval no longer linked to actual owner message')
    evidence=s.unseal(s.PROJECT_ROOT/lock['regression_evidence'])
    archived_digest=s.digest({p:h for p,h in lock['source_sha256'].items() if p.endswith(('.py','.ps1','.toml'))})
    if evidence['implementation_digest']!=archived_digest or s.digest(evidence)!=lock['regression_sha256']:
        raise s.CampaignError('archived regression/source mismatch')
    if evidence['parameter_values_sha256']!=s.load_generator_config().parameters_fingerprint:
        raise s.CampaignError('scientific parameter drift')
    for key in ('project_i_full','project03_eligible_fast'):
        e=evidence[key]
        if e['exit_code'] or e['failed'] or e['errors'] or not e['passed'] or e.get('skipped'):
            raise s.CampaignError('archived regression not clean')
        if key=='project_i_full' and e.get('deselected'):raise s.CampaignError('full regression was reduced')
        for name in ('stdout','junit'):
            if s.file_hash(safe_path(s.PROJECT_ROOT,e[name]))!=e[name+'_sha256']:raise s.CampaignError('regression raw evidence corruption')
    if evidence['project_i_full']['slow_passed']!=9:raise s.CampaignError('missing slow regression gates')
    plan_path=safe_path(root,manifest['plan']);plan=s.load_plan(plan_path,current=False)
    if s.digest(plan)!=lock['plan_sha256'] or s.digest(plan)!=manifest['plan_sha256'] or plan['analysis_contract']!=lock['analysis']:
        raise s.CampaignError('return plan/analysis mismatch')
    if s.digest(s.unseal(root/'readiness_manifest.json'))!=lock['readiness_sha256']:
        raise s.CampaignError('readiness proof mismatch')
    paired={}
    with progress_bar(len(plan['rows']),description='Verify paired scientific records') as bar:
        for row in plan['rows']:
            path=s.run_path(plan_path.parent,row)
            if not path.exists():raise s.CampaignError('required row missing')
            e=s.verify_result(path,plan,row)
            prior=paired.setdefault(row['scenario_id'],e['pairing'])
            if prior!=e['pairing']:raise s.CampaignError('cross-arm DQ17/N_out/T_end drift')
            if e['status']=='FAILED':raise s.CampaignError('failed row in purported completed transfer')
            bar.update(1)
    coverage=s.progress(plan_path,authorized=True)
    if coverage['status']!='COMPLETE' or coverage['counts']!=manifest['coverage']:
        raise s.CampaignError('return coverage mismatch')
    summary=s.unseal(root/'final_summary.json')
    if (summary['STEP7_LOCK']['sha256']!=manifest['lock_sha256'] or
        summary['CAMPAIGN_COVERAGE']!=coverage['counts'] or summary['STEP8_STARTED']!='NO'):
        raise s.CampaignError('consolidated summary/lock/coverage mismatch')
    for stage in ('descriptive-report','detailed-diagnostics'):
        receipt=s.unseal(root/'pipeline/stages'/(stage+'.json'))['value']
        report=s.unseal(safe_path(root,receipt['report']))
        if stage=='descriptive-report' and (report['plan_sha256']!=s.digest(plan) or report['pairing_audit']!='PASS'):
            raise s.CampaignError('descriptive evidence not paired to locked plan')
    result=dict(status='VERIFIED_RETURN_AUDIT_ONLY',coverage=coverage['counts'],manifest_sha256=s.digest(manifest),
        execution_packages=lock['packages'],local_packages_not_required_for_audit=True,newline_only_source_differences=newline_only,
        scientific_status='COMPLETE_FOR_OWNER_REVIEW',S1_S2_INFERENCE='DEFERRED_TO_STEP8',step8_started=False)
    s.seal(root/'return_verification'/(s.digest(result)+'.json'),result)
    return result
