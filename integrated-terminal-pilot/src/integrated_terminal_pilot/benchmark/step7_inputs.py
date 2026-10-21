"""Small Git-transportable prerequisites. No simulation, training or split generation."""
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile
import csv

from integrated_terminal_pilot.benchmark import step7 as s

MANIFEST = s.PROJECT_ROOT/'configs/protocol/step7_remote_inputs_v2.json'
ARCHIVE = s.PROJECT_ROOT/'assets/step7_remote_inputs_v2.zip'
ORIGIN = s.PROJECT_ROOT/'experiments/step7_paired_v1'


def normalized_sha(path):
    return hashlib.sha256(Path(path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()


def safe_path(root, name):
    if '\\' in name or ':' in name or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts:
        raise s.CampaignError('unsafe portable member: '+name)
    p = (Path(root)/name).resolve()
    if not p.is_relative_to(Path(root).resolve()):
        raise s.CampaignError('portable path escaped root')
    return p


def prepare():
    """Owner-authorized packaging only. Original artifacts are read, never rewritten."""
    from integrated_terminal_pilot.benchmark.checkpoints import all_checkpoints, verify_all_hashes, DECISION_FILE
    from integrated_terminal_pilot.benchmark.step7_readiness import F3, F3_SHA, GATE_SHA
    checks = verify_all_hashes()
    if not checks['ok']:raise s.CampaignError('checkpoint inventory failed')
    readiness = s.unseal(ORIGIN/'readiness_manifest.json')
    report = s.read_json(F3/'reports/f3_b745793420a7.json')
    if s.digest(report)!=F3_SHA or readiness['F3_report_sha256']!=F3_SHA:
        raise s.CampaignError('historical F3 receipt mismatch')
    p6=s.read_json(F3/'plan.json')
    for p,h in p6['source_sha256'].items():
        if s.file_hash(s.REPO/p)!=h:raise s.CampaignError('frozen historical source changed: '+p)
    if len(readiness['F3_rows'])!=12:raise s.CampaignError('F3 receipt coverage')
    for row in readiness['F3_rows']:
        key=next((k for k in report['run_artifacts'] if k.replace('\\','/')==row['file'].replace('\\','/')),None)
        if key is None or report['run_artifacts'][key]['file_sha256']!=row['sha256']:
            raise s.CampaignError('F3 receipt/run index link failed')
    files = [DECISION_FILE,DECISION_FILE.with_name(DECISION_FILE.name+'.sha256')]
    for ref in all_checkpoints():files += [ref.model_path,ref.metadata_path]
    # Keep the complete eligible regression scope on a fresh clone (no missing-fixture skips).
    source=s.PROJECT_ROOT/'experiments/scenarios/development/dev_f5789d8c91_1ee66026'
    index=source/'scenario_index.csv';files.append(index)
    # Closure's three failing tests consume the original manifest sidecar.
    # Preserve all small batch metadata as well as the selected scenario files.
    files.extend(p for p in sorted(source.iterdir()) if p.is_file() and p!=index)
    with index.open(encoding='utf-8') as stream:index_rows={r['scenario_id']:r for r in csv.DictReader(stream)}
    for family in ('itp_low','itp_medium','itp_heavy','itp_yard_bottleneck'):
        for seed in (10000000,10000001,10000002):
            sid=f'{family}_development_seed{seed}';p=source/'scenarios'/(sid+'.scenario.json')
            if s.file_hash(p)!=index_rows[sid]['file_sha256']:raise s.CampaignError('stored development fixture changed')
            files.append(p)
    for arm in ('A1','A3-train11'):
        files.append(s.PROJECT_ROOT/'experiments/step5_development/s5dev_smoke_v1/runs/protocol_v1_first_fit'/arm/
                     'itp_low_development_seed10000000.json')
    # test_v_first_step2_run_is_unchanged verifies this entire immutable historical
    # batch. Transport it instead of accepting an absent-fixture regression skip.
    first=s.PROJECT_ROOT/'experiments/scenarios/development/dev_3f1f0d9335_3e15947a'
    from integrated_terminal_pilot.scenarios.outputs import verify_manifest
    if not verify_manifest(first)['passed'] or s.file_hash(first/'manifest.json')!='3a12da33f304d9d6322486a0834ae90730107100b2386a7ba36e73e847659352':
        raise s.CampaignError('first Step2 historical fixture changed')
    files.extend(p for p in sorted(first.rglob('*')) if p.is_file())
    metadata = {
        'owner_reply.txt':ORIGIN/'owner_reply_20261014.txt',
        'owner_context.json':ORIGIN/'owner_reply_context_20261014.json',
        'cost_model.json':ORIGIN/'cost_model.json',
        'cost_model.json.sha256.json':ORIGIN/'cost_model.json.sha256.json',
        'historical_readiness.json':ORIGIN/'readiness_manifest.json',
        'historical_readiness.json.sha256.json':ORIGIN/'readiness_manifest.json.sha256.json',
        'step6_plan.json':F3/'plan.json',
        'step6_report.json':F3/'reports/f3_b745793420a7.json',
        'step6_final_review.json':F3/'reports/final_review_manifest.json',
        'step6_owner_report.md':s.PROJECT_ROOT/'docs/step6_closure_final_report.md',
        'step6_gate.json':s.PROJECT_ROOT/'experiments/step6_closure/gates'/(GATE_SHA+'.json'),
        'step4_report.json':s.PROJECT_ROOT/'experiments/step4_equivalence/eq_20261013T213721Z/report.json',
        'step5_report.json':s.PROJECT_ROOT/'experiments/step5_development/exact_gate_20261013T224141Z/report.json',
        'step5_smoke_manifest.json':s.PROJECT_ROOT/'experiments/step5_development/s5dev_smoke_v1/manifest.json',
    }
    members={'restore/'+p.relative_to(s.REPO).as_posix():p for p in files}
    members.update({'evidence/'+name:p for name,p in metadata.items()})
    original=s.unseal(s.PROJECT_ROOT/'configs/protocol/step7_remote_inputs.json')
    reference=s.read_json(metadata['step5_smoke_manifest.json'])['packages']
    environment=s.read_json(s.PROJECT_ROOT/'configs/protocol/step7_cpu_environment_v1.json')
    if reference['python']!=environment['python'] or any(reference[k]!=v for k,v in environment['packages'].items()):
        raise s.CampaignError('numerical environment is not the actual historical reference')
    manifest=dict(schema='step7_remote_inputs_v1',transport_revision=2,
        prior_transport_canonical_sha256=s.digest(original),
        numerical_reference=reference,
        files={name:{'sha256':s.file_hash(p),'bytes':p.stat().st_size} for name,p in sorted(members.items())},
        frozen_source_canonical_sha256={p:normalized_sha(s.REPO/p) for p in p6['source_sha256']},
        historical_scope='Prior verified F3 receipt and original report/index; raw F3 outer files stay on origin. '
                         'Remote does not claim to rehash or rerun those historical outer files.',
        packet_sha256=s.digest(s.unseal(s.PACKET)),checkpoints=checks)
    for name,meta in original['files'].items():
        if manifest['files'].get(name)!=meta:raise s.CampaignError('original transport evidence changed: '+name)
    if ARCHIVE.exists() or MANIFEST.exists():
        raise s.CampaignError('prepared transport already exists; preserve it, inspect before rebuilding')
    ARCHIVE.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(ARCHIVE,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name,p in sorted(members.items()):
            info=zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            z.writestr(info,p.read_bytes())
    manifest['archive_sha256']=s.file_hash(ARCHIVE)
    s.seal(MANIFEST,manifest)
    return {'archive':str(ARCHIVE),'bytes':ARCHIVE.stat().st_size,'manifest':str(MANIFEST)}


def install(bundle):
    """Restore ONLY missing authentic ignored checkpoint artifacts; never overwrite."""
    from integrated_terminal_pilot.benchmark.execution import progress_bar
    manifest=s.unseal(MANIFEST)
    if manifest.get('schema')!='step7_remote_inputs_v1' or s.file_hash(ARCHIVE)!=manifest['archive_sha256']:
        raise s.CampaignError('transport archive integrity failed')
    with zipfile.ZipFile(ARCHIVE) as z, progress_bar(len(manifest['files']),description='Verify/restore prerequisites',unit='file') as bar:
        if len(z.namelist())!=len(set(z.namelist())) or set(z.namelist())!=set(manifest['files']):
            raise s.CampaignError('duplicate/unlisted prerequisite member')
        for name,meta in manifest['files'].items():
            data=z.read(name)
            if len(data)!=meta['bytes'] or hashlib.sha256(data).hexdigest()!=meta['sha256']:
                raise s.CampaignError('transport member checksum failed: '+name)
            if name.startswith('restore/'):
                rel=name[len('restore/'):]
                if not rel.startswith(('03-berth-allocation-lab/experiments/rl/dynamic_extended_cuda/',
                    'integrated-terminal-pilot/experiments/scenarios/development/dev_f5789d8c91_1ee66026/',
                    'integrated-terminal-pilot/experiments/scenarios/development/dev_3f1f0d9335_3e15947a/',
                    'integrated-terminal-pilot/experiments/step5_development/s5dev_smoke_v1/runs/protocol_v1_first_fit/')):
                    raise s.CampaignError('unapproved restoration target')
                target=safe_path(s.REPO,rel)
            else:target=safe_path(bundle/'inputs/prerequisites',name)
            # Retain every prerequisite inside the returned bundle as well as restoring ignored fixtures.
            retained=safe_path(bundle/'inputs/prerequisites',name)
            retained.parent.mkdir(parents=True,exist_ok=True)
            if retained.exists():
                if s.file_hash(retained)!=meta['sha256']:raise s.CampaignError('retained prerequisite changed')
            else:
                with retained.open('xb') as stream:stream.write(data)
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                if s.file_hash(target)!=meta['sha256']:raise s.CampaignError('existing artifact differs; never overwrite '+str(target))
            else:
                with target.open('xb') as stream:stream.write(data)
            bar.update(1)
    return manifest


def historical_audit(bundle):
    """Verify frozen bytes/values and the transported historical receipt; no old outer rerun."""
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    from integrated_terminal_pilot.benchmark.step7_readiness import F3_SHA,GATE_SHA
    manifest=s.unseal(MANIFEST)
    evidence=bundle/'inputs/prerequisites/evidence'
    for name,meta in manifest['files'].items():
        if name.startswith('evidence/') and s.file_hash(safe_path(bundle/'inputs/prerequisites',name))!=meta['sha256']:
            raise s.CampaignError('historical receipt corrupted')
    for p,h in manifest['frozen_source_canonical_sha256'].items():
        if normalized_sha(s.REPO/p)!=h:raise s.CampaignError('frozen source content mismatch: '+p)
    old=s.unseal(evidence/'historical_readiness.json')
    report=s.read_json(evidence/'step6_report.json');gate=s.read_json(evidence/'step6_gate.json')
    final=s.read_json(evidence/'step6_final_review.json')
    if (s.digest(report)!=F3_SHA or s.digest(gate)!=GATE_SHA or gate['contract_defects'] or
        final['machine_report_file_sha256']!=s.file_hash(evidence/'step6_report.json') or
        final['owner_report_file_sha256']!=s.file_hash(evidence/'step6_owner_report.md') or
        normalized_sha(evidence/'step6_owner_report.md')!=normalized_sha(s.PROJECT_ROOT/'docs/step6_closure_final_report.md')):
        raise s.CampaignError('historical F3/gate/report proof failed')
    checks=verify_all_hashes()
    if not checks['ok'] or checks!=manifest['checkpoints']:raise s.CampaignError('checkpoint drift')
    owner6=s.read_json(s.PROJECT_ROOT/'configs/protocol/step6_closure_owner_approval.json')
    if s.digest(owner6)!='ef4dc4463d108c31e3013e6361388aabc89e7e5c7b94b9ffaef89bad01af9118':
        raise s.CampaignError('Q6 approval changed')
    from integrated_terminal_pilot.benchmark.protocol_records import load_control_register,control_record_gaps
    if control_record_gaps(load_control_register()):raise s.CampaignError('protocol controls incomplete')
    return dict(step6_verified=True,scope=manifest['historical_scope'],F3_rows=old['F3_rows'],
                F3_report_sha256=F3_SHA,F3_gate_sha256=GATE_SHA,checkpoint_hashes=checks,
                source_sha256=s.source_manifest(),owner_packet_sha256=s.digest(s.unseal(s.PACKET)))
