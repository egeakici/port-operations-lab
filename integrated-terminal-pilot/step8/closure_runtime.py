"""Durable per-cell execution. No simulations on plan/status/verify/import."""
from contextlib import contextmanager
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import threading
import time
import uuid

from tqdm import tqdm
from evidence import publish, publish_bytes, read, sha, safe_path, s
from statistical import ContractError
from closure_matrix import scenario_key


def utc(): return datetime.now(timezone.utc).isoformat()


@contextmanager
def worker_lock(root):
    root.mkdir(parents=True,exist_ok=True)
    path = root/'worker.lock'
    stream = path.open('a+b')
    if not path.stat().st_size: stream.write(b'0'); stream.flush()
    stream.seek(0)
    try:
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(stream.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError as exc:
        stream.close()
        raise ContractError('Another diagnostic worker/approver owns this campaign') from exc
    try: yield
    finally: stream.close()  # OS lock is released even after process death.


def inventory(directory):
    return {p.relative_to(directory).as_posix():dict(sha256=sha(p),bytes=p.stat().st_size)
            for p in sorted(directory.rglob('*')) if p.is_file() and p.name!='COMMIT.json'}


def verify_cell(root, cell, plan_hash, *, canonical=False):
    directory = root/'cells'/cell['fingerprint']
    if not directory.exists(): return None
    if not (directory/'COMMIT.json').exists():
        raise ContractError('Incomplete published cell; never skip: '+cell['cell_id'])
    commit = read(directory/'COMMIT.json')
    if (commit['cell_fingerprint'] != cell['fingerprint'] or commit['plan_sha256'] != plan_hash
            or commit['status'] != 'VERIFIED' or inventory(directory) != commit['files']):
        raise ContractError('Cell integrity mismatch: '+cell['cell_id'])
    result = read(directory/'result.json')
    if result['cell_id'] != cell['cell_id'] or result['status']!='VERIFIED':
        raise ContractError('Result identity/status mismatch')
    if cell.get('role')=='DIAGNOSTIC_13M_NOT_PRIMARY_TEST':
        key=scenario_key(cell)
        source_path=root/'scenarios'/key/'scenario.json'
        source=read(source_path)
        stamp=read(source_path.with_suffix('.sha256.json'))
        if (result.get('cell_fingerprint')!=cell['fingerprint'] or result.get('plan_sha256')!=plan_hash
                or result.get('scenario_cache_key')!=key or stamp['key']!=key or stamp['sha256']!=sha(source_path)
                or result.get('source_input_sha256')!=s.digest(source)
                or result.get('physical_document_sha256')!=s.digest(source['document'])):
            raise ContractError('Diagnostic input/scenario lineage mismatch')
    if canonical:
        import hashlib
        for name, metadata in result['trace'].items():
            h, size = hashlib.sha256(), 0
            with gzip.open(directory/'trace'/(name+'.gz'),'rb') as stream:
                for chunk in iter(lambda: stream.read(1024*1024),b''):
                    h.update(chunk); size += len(chunk)
            if metadata != dict(canonical_sha256=h.hexdigest(),canonical_bytes=size):
                raise ContractError('New diagnostic canonical trace corruption')
    return result


def campaign_status(root, plan, *, canonical=False):
    counts = dict(plan['matrix']['counts'],verified=0,pending=0,failed=0,partial_attempts=0,verified_aliases=0)
    valid = set()
    plan_hash=s.digest(plan)
    commits={}
    for cell in tqdm(plan['matrix']['cells'],desc='New diagnostic integrity',unit='cell',ascii=True,leave=False):
        if cell['status']!='RUNNABLE': continue
        if verify_cell(root,cell,plan_hash,canonical=canonical):
            counts['verified'] += 1; valid.add(cell['cell_id'])
            commits[cell['fingerprint']]=sha(root/'cells'/cell['fingerprint']/'COMMIT.json')
        else: counts['pending'] += 1
    counts['verified_aliases'] = sum(c['status']=='ALIAS' and c['alias_of'] in valid for c in plan['matrix']['cells'])
    counts['failed'] = len(list((root/'attempts').glob('*/*/FAILED.json')))
    counts['partial_attempts'] = sum(not (p/'FINISHED.json').exists() and not (p/'FAILED.json').exists()
                                   for p in (root/'attempts').glob('*/*') if p.is_dir())
    counts['verified_commit_inventory_sha256']=s.digest(commits)
    return counts


def resource_check(root, *, min_free_gib=5., max_rss_gib=4.):
    import psutil
    rss = psutil.Process().memory_info().rss
    free = shutil.disk_usage(root).free
    if free < min_free_gib*1024**3 or rss > max_rss_gib*1024**3:
        raise ContractError(f'RESOURCE_ADMISSION_STOP: free={free/1024**3:.2f}GiB rss={rss/1024**3:.2f}GiB; completed episodes preserved')
    return dict(rss_bytes=rss,disk_free_bytes=free)


def gzip_json(path,value):
    with path.open('xb') as raw, gzip.GzipFile(filename='',fileobj=raw,mode='wb',mtime=0) as stream:
        stream.write((json.dumps(value,sort_keys=True,allow_nan=False)+'\n').encode())


def load_scenario(root,config,cell):
    from closure_matrix import physical_document
    path = root/'scenarios'/scenario_key(cell)/'scenario.json'
    if path.exists():
        stamp=read(path.with_suffix('.sha256.json'))
        if stamp['sha256'] != sha(path) or stamp['key'] != scenario_key(cell):
            raise ContractError('Scenario cache drift')
        return read(path)
    try:
        value=physical_document(config,cell)
    except ContractError as exc:
        if hasattr(exc,'generated_input'):
            publish(path.with_name('UNSUPPORTED_GENERATED_INPUT.json'),exc.generated_input)
        raise
    publish(path,value)
    publish(path.with_suffix('.sha256.json'),dict(sha256=sha(path),key=scenario_key(cell)))
    return value


def run_campaign(root,plan,config,preflight):
    """Only manual run/resume calls here. First Ctrl+C requests episode-boundary stop."""
    from diagnostic_episode import run_cell_episode
    plan_hash=s.digest(plan)
    with worker_lock(root):
        status=campaign_status(root,plan)
        if status['failed']:
            raise ContractError('Preserved genuine diagnostic failure requires investigation; no automatic retry')
        stop=threading.Event()
        old=signal.getsignal(signal.SIGINT)
        def interrupted(*_):
            stop.set()
            tqdm.write('Stop requested: preserving healthy episode; no new episode will be admitted.')
        signal.signal(signal.SIGINT,interrupted)
        bar=tqdm(total=status['runnable'],initial=status['verified'],desc='Step8 13M',unit='ep',ascii=True,
                 ncols=max(60,shutil.get_terminal_size((110,20)).columns-2),mininterval=1.)
        started=time.perf_counter()
        try:
            for cell in plan['matrix']['cells']:
                if cell['status']!='RUNNABLE': continue
                if verify_cell(root,cell,plan_hash): continue
                if stop.is_set(): break
                preflight()
                resources=resource_check(root)
                attempt=root/'attempts'/cell['fingerprint']/uuid.uuid4().hex
                attempt.mkdir(parents=True)
                publish(attempt/'STARTED.json',dict(cell_id=cell['cell_id'],plan_sha256=plan_hash,
                    started=utc(),pid=os.getpid(),host=socket.gethostname(),resources=resources))
                tqdm.write(f"Starting {cell['cell_id']} (CPU, one worker)")
                bar.set_postfix(f=cell['family'].removeprefix('itp_'),a=cell['arm'],dev='CPU')
                episode_started=time.perf_counter()
                pulse_stop=threading.Event()
                def pulse():
                    while not pulse_stop.wait(15):
                        bar.set_postfix(f=cell['family'].removeprefix('itp_'),a=cell['arm'],dev='CPU',active_s=int(time.perf_counter()-episode_started))
                monitor=threading.Thread(target=pulse,daemon=True); monitor.start()
                try:
                    source=load_scenario(root,config,cell)
                    output=attempt/'output'; output.mkdir()
                    result=run_cell_episode(source['document'],cell,output/'trace')
                    gzip_json(output/'policy_records.json.gz',result.pop('policy_records'))
                    result['scenario_cache_key']=scenario_key(cell)
                    result['source_input_sha256']=s.digest(source)
                    result['plan_sha256']=plan_hash
                    result['resource_after_episode']=resource_check(root,min_free_gib=0,max_rss_gib=float('inf'))
                    publish(output/'result.json',result)
                    publish(output/'COMMIT.json',dict(status='VERIFIED',cell_fingerprint=cell['fingerprint'],
                        plan_sha256=plan_hash,files=inventory(output)))
                    target=root/'cells'/cell['fingerprint']; target.parent.mkdir(parents=True,exist_ok=True)
                    if target.exists(): raise ContractError('Duplicate cell publication')
                    output.rename(target)
                    verify_cell(root,cell,plan_hash)
                    publish(attempt/'FINISHED.json',dict(completed=utc(),result_sha256=sha(target/'result.json')))
                    bar.update(1)
                except Exception as exc:
                    import traceback
                    publish(attempt/'FAILED.json',dict(time=utc(),type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc()))
                    raise
                finally:
                    pulse_stop.set(); monitor.join()
        finally:
            signal.signal(signal.SIGINT,old); bar.close()
        state=campaign_status(root,plan)
        publish(root/'sessions'/(uuid.uuid4().hex+'.json'),dict(stopped_safely=stop.is_set(),time=utc(),counts=state))
        return state
