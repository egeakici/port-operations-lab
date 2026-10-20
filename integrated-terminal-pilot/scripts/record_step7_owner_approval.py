"""Record an actual explicit owner message, ONLY after reviewing it in the owner conversation.

This command is a provenance recorder, not an approval generator or a natural-language
authorization classifier. The operator must supply the exact approved ID list and packet hash.
Never run it on the implementation prompt itself, which explicitly does not approve the28.
"""
import argparse
import json
import os
from pathlib import Path
import re
import uuid
import yaml
from integrated_terminal_pilot.benchmark import step7 as s


def record(message, date, source, packet_sha, ids, *, register_path=None, approval_path=None, history_root=None):
    if sorted(ids)!=list(s.PENDING_IDS) or len(ids)!=28:
        raise s.CampaignError('partial approval: exactly the28 IDs required')
    if not message.strip() or not source.strip() or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',date):
        raise s.CampaignError('actual verbatim message/date/source required')
    packet=s.unseal(s.PACKET)
    if s.digest(packet)!=packet_sha or packet['rows']!=s.value_rows():
        raise s.CampaignError('reviewed packet differs from exact existing values')
    register_path=register_path or s.PROJECT_ROOT/'configs/generator/itp_generator_v1_decisions.yaml'
    approval_path=approval_path or s.APPROVAL
    if approval_path.exists() or s.FORMAL_LOCK_PATH.exists():
        raise s.CampaignError('existing approval/lock: never replace or amend silently')
    text=register_path.read_text(encoding='utf-8')
    updated=text
    value={'packet_sha256':packet_sha,'approved_ids':list(s.PENDING_IDS),
           'status':'EXPLICIT_OWNER_APPROVAL','verbatim_message':message,'source':source,'date':date,
           'scope':'UNCALIBRATED_SYNTHETIC_V1_MEDIUM_HEAVY_PRIMARY_LOW_BOTTLENECK_DIAGNOSTIC',
           'recorded_utc':s.now(),'previous_register_file_sha256':s.file_hash(register_path)}
    for row in packet['rows']:
        key=row['decision_id']
        match=re.search(r'(?ms)^  - decision_id: '+re.escape(key)+r'\n.*?(?=^  - decision_id: |\Z)',updated)
        if match is None or match[0].count('    status: PROPOSED_PENDING_REVIEW')!=1:
            raise s.CampaignError(f'{key}: not a uniquely pending record')
        approval={'approved_by':'user','approval_source':f'Step 7 explicit owner message; packet {packet_sha}',
                  'approval_date':date,'approved_value':json.dumps(row['values_by_path'],sort_keys=True),
                  'scope':value['scope']}
        fragment=yaml.safe_dump({'approval':approval},sort_keys=False,allow_unicode=True)
        fragment='\n'.join('    '+line for line in fragment.rstrip().splitlines())+'\n'
        block=match[0].replace('    status: PROPOSED_PENDING_REVIEW\n','    status: FROZEN\n'+fragment,1)
        updated=updated[:match.start()]+block+updated[match.end():]
    # Validate all numbers/paths/source kinds before changing any register byte.
    from integrated_terminal_pilot.scenarios.config import build_generator_config
    params=s.load_generator_config().snapshot()
    configured=build_generator_config(params,yaml.safe_load(updated))
    if s.value_rows(configured)!=packet['rows']:
        raise s.CampaignError('approval would alter scientific values')
    history=(history_root or s.PROJECT_ROOT/'configs/protocol/step7_approval_history')/s.digest(value)
    s.seal(history.with_suffix('.json'),value)
    history.with_suffix('.message.txt').parent.mkdir(parents=True,exist_ok=True)
    with history.with_suffix('.message.txt').open('x',encoding='utf-8',newline='') as f:f.write(message)
    temp=register_path.with_name(register_path.name+'.'+uuid.uuid4().hex+'.tmp')
    temp.write_text(updated,encoding='utf-8',newline='\n')
    os.replace(temp,register_path)
    s.seal(approval_path,value)
    return {'approval_path':str(approval_path),'approval_sha256':s.digest(value),'packet_sha256':packet_sha}


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--message-file',required=True,type=Path)
    p.add_argument('--date',required=True)
    p.add_argument('--source',required=True)
    p.add_argument('--packet-sha',required=True)
    p.add_argument('--ids',required=True,nargs=28)
    p.add_argument('--context-file',type=Path,
                   help='Archive the actual displayed option context alongside a short owner reply')
    p.add_argument('--append-documentation',action='store_true')
    a=p.parse_args()
    context=s.read_json(a.context_file) if a.context_file else None
    if context and (context.get('packet_sha256')!=a.packet_sha or context.get('date')!=a.date
                    or context.get('source')!=a.source):
        raise s.CampaignError('owner context differs from supplied provenance')
    result=record(a.message_file.read_text(encoding='utf-8'),a.date,a.source,a.packet_sha,a.ids)
    if context:
        s.seal(s.PROJECT_ROOT/'configs/protocol/step7_approval_history'/
               (result['approval_sha256']+'.context.json'),context)
    if a.append_documentation:
        text=(f'\n\n## Step 7 explicit owner approval recorded - {a.date}\n\n'
              f'All 28 exact rows in packet `{a.packet_sha}` are now FROZEN with actual owner provenance. '
              f'Active approval canonical SHA `{result["approval_sha256"]}`. '
              'Verbatim reply and supplied option context are preserved in `configs/protocol/step7_approval_history/`. '
              'Original values, units and source kinds are unchanged. This supersedes historical pending-state '
              'prose only for these 28 records. SYNTHETIC / UNCALIBRATED; Medium/Heavy primary, '
              'Low/Bottleneck diagnostic. Execution remains manual; no validation/test was run by this recorder.\n')
        for name in ('protocol_amendments.md','pre_step6_synthetic_parameter_approval_matrix.md',
                     'step7_owner_approval_packet.md','step7_scientific_lock_and_campaign.md'):
            with (s.PROJECT_ROOT/'docs'/name).open('a',encoding='utf-8',newline='\n') as f:f.write(text)
    print(json.dumps(result,indent=2))
