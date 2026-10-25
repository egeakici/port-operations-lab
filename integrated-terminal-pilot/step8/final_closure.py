"""Project I final closure: explicit manual run/resume; all other verbs analysis-only."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys

from evidence import (DEFAULT_BUNDLE, PROJECT, REPO, EXPECTED_LOCK, EXPECTED_MANIFEST,
                      code_inventory, intake, protected_source, read, sha, publish, publish_bytes, s)
from statistical import ContractError
from closure_matrix import matrix
from closure_runtime import campaign_status, run_campaign, worker_lock

ROOT=PROJECT/'experiments/step8_final_closure'
PREVIOUS=PROJECT/'experiments/step8_analysis/ac9db68020c4079d'
PREVIOUS_RELEASE_SHA='6965e827dd47036c8ed2b572f5806ba76a9b65394872678f494844bd14d8ba5a'


def original_inputs(bundle):
    restore_original_receipt(Path(bundle))
    ctx=intake(bundle)
    if ctx['gate']['RETURN_VERIFY']!='VERIFIED_FULL_CANONICAL':
        raise ContractError('Existing official canonical receipt required; do NOT rerun VerifyReturn')
    if not any(r['sha256']=='e903d0dc2f61c686fcdd4942dcfc813a6c05a5ba05f78b5e16dd2736b127e0cc' for r in ctx['gate']['receipts']):
        raise ContractError('Known verified original full return receipt hash differs; no replacement receipt accepted')
    from integrated_terminal_pilot.benchmark.checkpoints import verify_all_hashes
    if verify_all_hashes()!=ctx['lock']['checkpoints']:
        raise ContractError('Frozen model checkpoint or decision-file mismatch')
    return ctx


def restore_original_receipt(bundle):
    """Copy exact existing original PASS bytes to another owner computer only.

    This is transport, NOT a new scientific verification or synthetic receipt.
    Never replace an existing differing artifact. Original bundle identity first.
    """
    import hashlib
    import zipfile
    from integrated_terminal_pilot.benchmark.step7_workspace import bundle_path
    bundle=bundle_path(bundle)
    filename='09499de0840d7bdc7c152ee0bdf543c95716c86cf97b7273f418e1209b1dca3f.json'
    target=bundle/'return_verification'/filename
    side=target.with_suffix('.json.sha256.json')
    expected='e903d0dc2f61c686fcdd4942dcfc813a6c05a5ba05f78b5e16dd2736b127e0cc'
    if target.exists() and sha(target)!=expected:raise ContractError('Existing original return receipt corrupted; no overwrite')
    if target.exists() and side.exists():return
    if sha(bundle/'protocol_lock_v1.json')!=EXPECTED_LOCK or s.digest(s.unseal(bundle/'transfer_manifest.json'))!=EXPECTED_MANIFEST:
        raise ContractError('Cannot transport receipt to a different scientific bundle')
    with zipfile.ZipFile(Path(__file__).with_name('reference')/'closure_reference_v2.zip') as archive:
        raw=archive.read('verified_step7_return/'+filename)
        side_bytes=archive.read('verified_step7_return/'+filename+'.sha256.json')
    if hashlib.sha256(raw).hexdigest()!=expected or json.loads(side_bytes)!=dict(file_sha256=expected,canonical_sha256=filename.removesuffix('.json')):
        raise ContractError('Portable original receipt bytes fail hash checks')
    publish_bytes(target,raw);publish_bytes(side,side_bytes)
    publish(ROOT/'receipt_transport'/expected/(str(s.digest(dict(bundle=str(bundle))))+'.json'),
        dict(operation='BYTE_IDENTICAL_EXISTING_OFFICIAL_RECEIPT_TRANSPORT_ONLY',
             original_file_sha256=expected,target=str(target),verification_rerun=False))


def predecessor():
    import hashlib
    blob=predecessor_bytes('step8_release_manifest.json')
    if hashlib.sha256(blob).hexdigest()!=PREVIOUS_RELEASE_SHA:
        raise ContractError('Verified predecessor release manifest changed')
    release=json.loads(blob)
    # Reuse sealed derived work; no Step7 archive inflation or episode parsing.
    names=('derived_arrays.json','cargo_noninferiority.json','wait_cargo_forecast_diagnostics.json',
           'diagnostic_cost_proxy.json','policy_seed_diagnostics.json','compute_cost.json','closure_status.json')
    for name in names:
        item=release['files'][name]; raw=predecessor_bytes(name)
        if hashlib.sha256(raw).hexdigest()!=item['sha256'] or len(raw)!=item['bytes']:
            raise ContractError('Predecessor derived artifact changed: '+name)
    if release['provenance']['manifest_sha256']!=EXPECTED_MANIFEST:
        raise ContractError('Wrong predecessor scientific campaign')
    return release


def predecessor_bytes(name):
    p=PREVIOUS/name
    if p.is_file(): return p.read_bytes()
    import zipfile
    with zipfile.ZipFile(Path(__file__).with_name('reference')/'closure_reference_v2.zip') as archive:
        return archive.read(name)


def predecessor_json(name): return json.loads(predecessor_bytes(name))


def scientific_audit():
    """Quote exact source lines, including all amendment records, not old prose alone."""
    docs=['implementation_roadmap.md','scientific_experiment_protocol.md','protocol_amendments.md',
          'step6_closure_contract_gate.md','step6_closure_final_report.md','step7_results_owner_review_20261023.md',
          'manual_execution_runbook.md']
    paths=[PROJECT/'docs'/name for name in docs]
    paths += [PROJECT/'configs/protocol/step7_analysis_contract.json',
              PROJECT/'step8/statistical.py',PROJECT/'step8/diagnostic_plan.py']
    # Project03 methodological references ONLY. Never inspect its held-out results.
    p03=REPO/'03-berth-allocation-lab'
    paths += sorted(p03.glob('src/**/*stats*.py'))
    paths += sorted(p03.glob('src/**/*statistic*.py'))
    paths += sorted(p03.glob('docs/*protocol*.md'))
    paths += sorted(p03.glob('docs/*analysis*.md'))
    words=('holm','bootstrap','10,000','10000','120001','20261013','primary','hypothes',
           'none','equivalen','unsupported','occupancy0.3','13m','6.5','post-hoc')
    records=[]
    for p in dict.fromkeys(paths):
        lines=p.read_text(encoding='utf-8-sig').splitlines()
        quotes=[dict(line=i+1,text=line) for i,line in enumerate(lines) if any(w in line.lower() for w in words)]
        records.append(dict(path=p.relative_to(REPO).as_posix(),sha256=sha(p),line_count=len(lines),quotes=quotes))
    return dict(date='2026-10-25',schema='post_hoc_source_audit_v1',files=records,
        finding='No pre-existing unambiguous primary Holm CI construction. Frozen primary identities m2; raw percentile bootstrap and NI rules exist.',
        missing=['Holm interval inversion/local test convention','population-wise vs joint family scope','sidedness implementation beyond below/above-zero interval rule'],
        correction='One frozen-before-new-computation post-hoc specification, not retroactive preregistration',
        original_none_rule='Protocol11 universal equality conflicts with ready-cargo/fixed-service/uncensored scoped gate and Q6 retained availability/censoring.',
        heavy_03='Locked step7_analysis_contract.step8_ranges_only_not_executed.note explicitly unsupported; maintain all120 cells; owner confirms N/A interpretation.',
        original_full_verification_repeated=False)


def plan_for(ctx):
    from multiplicity import METHOD_PATH
    return dict(schema='project_i_final_closure_plan_v1',source_lock_file_sha256=EXPECTED_LOCK,
        step7_manifest_sha256=EXPECTED_MANIFEST,scientific_source_revision=ctx['lock']['source_revision'],
        original_source_inventory_sha256=ctx['source']['original_inventory_sha256'],
        source_content_sha256=ctx['source']['original_inventory_sha256'],
        # CRLF/LF-only transport changes have already been checked against the original archive.
        code_inventory=code_inventory(),method_sha256=sha(METHOD_PATH),
        matrix=matrix(),checkpoints=ctx['lock']['checkpoints'],
        scientific_roles='13M diagnostic, no primary TEST repetition; six A identities; both/base aliases40',
        execution=dict(workers=1,torch_threads=1,ppo_device='cpu',simulation_device='cpu',
            wall_time_admission_limit=None,min_disk_free_gib=5,max_rss_admission_gib=4,
            interrupt='Finish healthy episode then stop admission; durable cell commits; OS lock',
            failed='Preserve FAILED attempt; investigate, never silently retry or omit'),
        method_classification='POST_HOC_MULTIPLICITY_COMPLETION_REQUIRES_OWNER_ACCEPTANCE')


def plan_directory(plan): return ROOT/s.digest(plan)[:16]


def install_plan(plan):
    root=plan_directory(plan)
    publish(root/'plan.json',plan)
    publish_bytes(root/'plan.json.sha256',(sha(root/'plan.json')+'\n').encode())
    return root


def packet_path(plan): return PROJECT/'docs/step8/final_closure'/s.digest(plan)[:16]/'owner_amendment_packet.json'


def write_packet(ctx,plan,tests,probe):
    from multiplicity import METHOD_PATH
    packet=dict(schema='project_i_scientific_resolution_packet_v1',date='2026-10-25',
        status='PENDING_EXPLICIT_OWNER_APPROVAL',plan_sha256=s.digest(plan),
        matrix_sha256=s.digest(plan['matrix']),method_file_sha256=sha(METHOD_PATH),
        code_sha256=s.digest(plan['code_inventory']),source_lock_file_sha256=EXPECTED_LOCK,
        step7_manifest_sha256=EXPECTED_MANIFEST,official_return_receipts=ctx['gate']['receipts'],
        test_receipt=tests,engineering_probe=probe,
        previously_observed='All Step7 held-out results and raw Step8 CIs. New13M scientific scenarios have NOT been generated or run.',
        requests=[
            dict(id='FC-01',frozen_rule='Protocol10 primary Holm-adjusted CIs; no construction specified',
                proposal=read(METHOD_PATH),effect='Qualified post-hoc primary inference, not LOCKED_CONFIRMATORY_PASS; no outcome-driven method selection'),
            dict(id='FC-02',frozen_rule='Protocol11 none must reproduce A2 on same states',
                proposal='Retain existing exact scoped A2/B2-T proof unchanged. Realistic MODEL_COUPLING_NONE uses .5min/move dedicated per-visible-vessel capacity, no transport/yard rate coupling, but keeps cargo availability, berth geometry, D15/D17, FCFS, AM07 and full WAIT. Realistic none/A2 agreement is measured, not required universally.',
                proof='Engineering short-horizon counterexample retains AM07: A2 favors short vessel; MODEL_COUPLING_NONE favors loading more containers before censoring. Availability and D17 also invalidate fixed-service premise.',
                classification='POST_HOC_CONTRACT_SCOPE_CORRECTION',effect='160 coupling requirements retained; both40 aliases share verified baseB2'),
            dict(id='FC-03',frozen_rule='Locked analysis explicitly heavy0.3 occupancy unsupported; protocol sensitivity still lists0.3',
                proposal='All120 original Heavy0.3 requirements remain NOT_APPLICABLE_PREDECLARED_UNSUPPORTED on owner acceptance, never executed, imputed, resampled, or counted as successes.',
                effect='4480 requirements;40 exact aliases;4440 unique;4320 runnable;120 unsupported. Any other new support failure still blocks closure.'),
            dict(id='FC-04',frozen_rule='Frozen source inventory predates new launcher and requested top-level handoff documents',
                proposal='Allow only THREE specifically named new operational/analysis files in Step8 intake; retain unchanged content checks for all413 original paths. Original Step7 verifier and historical PASS untouched. New files included in independent Step8 code fingerprint.',
                classification='OPERATIONAL_SCOPE_EXTENSION_NOT_SCIENTIFIC_POLICY_CHANGE',
                effect='No approval for parameters, seeds beyond published matrix, training or any policy retuning')],
        qualified_closure='Owner accepts a qualified synthetic study after actual4320 diagnostic results verify; negative results do not prevent procedural closure. No three-branch RL/real-port claims.',
        approval_provenance=None)
    publish(packet_path(plan),packet)
    return packet


def require_approval(root,packet):
    approvals=list((root/'approvals').glob('*.json'))
    if not approvals: raise ContractError('SCIENTIFIC_APPROVAL_REQUIRED: review exact packet before new diagnostic execution')
    for p in approvals:
        a=read(p)
        if a['packet_sha256']!=s.digest(packet) or a['plan_sha256']!=packet['plan_sha256'] or not a['owner'] or not a['provenance']:
            raise ContractError('Approval does not match exact plan/packet')
    return [dict(path=p.relative_to(REPO).as_posix(),sha256=sha(p)) for p in approvals]


def execution_runtime(ctx):
    from integrated_terminal_pilot.benchmark.development import package_versions
    actual=package_versions()
    if {k:v for k,v in actual.items() if k!='platform'}!={k:v for k,v in ctx['lock']['packages'].items() if k!='platform'}:
        raise ContractError('Diagnostic runtime differs from frozen reference packages; use existing step7-cpu3132 environment')
    import torch
    torch.set_num_threads(1)
    if torch.get_num_threads()!=1: raise ContractError('One inference thread required')


def bounded_preflight(ctx,plan):
    if code_inventory()!=plan['code_inventory']:
        raise ContractError('Diagnostic implementation drift; no administrative Git HEAD restriction')
    protected_source(ctx['lock'],ctx['bundle'])
    if sha(ctx['bundle']/'protocol_lock_v1.json')!=EXPECTED_LOCK:
        raise ContractError('Source lock drift')


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['plan','status','approve','run','resume','verify','analyze','finalize','engineering-probe'])
    p.add_argument('--bundle',type=Path,default=DEFAULT_BUNDLE)
    p.add_argument('--accept-packet',help='Explicit owner approval, canonical SHA256 of reviewed packet; only approve verb')
    p.add_argument('--owner'); p.add_argument('--provenance')
    p.add_argument('--canonical',action='store_true',help='New diagnostic traces only; NEVER original Step7 archive')
    args=p.parse_args(argv)
    try:
        if args.action=='engineering-probe':
            from closure_probe import execute
            print(json.dumps(execute(),indent=2)); return 0
        ctx=original_inputs(args.bundle)
        predecessor()
        plan=plan_for(ctx); root=install_plan(plan)
        if args.action=='plan':
            if packet_path(plan).exists():
                existing=read(packet_path(plan))
                if existing['plan_sha256']!=s.digest(plan) or existing['code_sha256']!=s.digest(code_inventory()):
                    raise ContractError('Existing exact packet/source mismatch')
                print(json.dumps(dict(plan=str(root/'plan.json'),plan_sha256=s.digest(plan),
                    packet=str(packet_path(plan)),packet_sha256=s.digest(existing),counts=plan['matrix']['counts']),indent=2));return 0
            from run_step8 import matching_tests
            from closure_probe import latest_probe
            tests=matching_tests(s.digest(code_inventory()))
            if not tests: raise ContractError('Run focused current-source fixture tests before sealing review packet')
            probe=latest_probe()
            packet=write_packet(ctx,plan,tests,probe)
            from closure_reporting import prepare_documents
            prepare_documents(ctx,plan,packet,scientific_audit())
            print(json.dumps(dict(plan=str(root/'plan.json'),plan_sha256=s.digest(plan),
                packet=str(packet_path(plan)),packet_sha256=s.digest(packet),counts=plan['matrix']['counts']),indent=2)); return 0
        packet=read(packet_path(plan))
        if args.action=='approve':
            if args.accept_packet!=s.digest(packet) or not args.owner or not args.provenance:
                raise ContractError('Explicit exact packet hash, owner and provenance required')
            with worker_lock(root):
                if list((root/'approvals').glob('*.json')):
                    require_approval(root,packet)
                    print('Matching explicit owner approval already recorded; preserved unchanged');return 0
                value=dict(packet_sha256=s.digest(packet),plan_sha256=s.digest(plan),owner=args.owner,
                    provenance=args.provenance,time=datetime.now(timezone.utc).isoformat(),
                    scope='All FC01-04; qualified final release only after all gates')
                publish(root/'approvals'/(s.digest(value)+'.json'),value)
            print('Append-only explicit owner approval recorded'); return 0
        if args.action in ('run','resume'):
            require_approval(root,packet); execution_runtime(ctx)
            bounded_preflight(ctx,plan)
            state=run_campaign(root,plan,s.load_generator_config(),lambda:bounded_preflight(ctx,plan))
            print(json.dumps(state,indent=2)); return 0 if state['pending']==0 else 3
        if args.action in ('status','verify'):
            bounded_preflight(ctx,plan)
            state=campaign_status(root,plan,canonical=args.canonical and args.action=='verify')
            if args.action=='verify' and state['pending']==0 and state['failed']==0:
                publish(root/('VERIFIED_CANONICAL.json' if args.canonical else 'VERIFIED_BYTES.json'),dict(status='VERIFIED_NEW_DIAGNOSTICS',counts=state,
                    canonical=bool(args.canonical),plan_sha256=s.digest(plan)))
            print(json.dumps(state,indent=2)); return 0 if args.action=='status' or state['pending']==0 else 3
        from closure_reporting import release
        result=release(ctx,plan,packet,root,finalize=args.action=='finalize')
        print(json.dumps(result,indent=2)); return 0 if args.action!='finalize' or result['PROJECT_I_FINAL_CLOSED']=='YES' else 3
    except Exception as exc:
        print(json.dumps(dict(status='BLOCKED_PRESERVED',error=str(exc),type=type(exc).__name__,
            STEP7_OUTER_RERUNS=0,PPO_RETRAINING='NONE'),ensure_ascii=False),file=sys.stderr)
        return 2


if __name__=='__main__': raise SystemExit(main())
