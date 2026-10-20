"""Manual evidence assembly, never a test runner, approval recorder or lock creator."""
import argparse
import json
from integrated_terminal_pilot.benchmark import step7 as s


def assemble(full_path, fast_path):
    a, b = s.unseal(full_path), s.unseal(fast_path)
    if a.get('suite') != 'project-i-full' or b.get('suite') != 'project03-fast':
        raise ValueError('exact full Project I and eligible-fast Project03 results required')
    for e in (a,b):
        if e.get('implementation_digest') != s.implementation_digest():
            raise ValueError('regression belongs to another source snapshot; rerun manually')
        e['selected_junit_cases'] = e['collected']
        e['collected_total'] = e['collected'] + e['deselected']
    evidence = dict(implementation_digest=s.implementation_digest(),
        parameter_values_sha256=s.load_generator_config().parameters_fingerprint,
        project_i_full=a, project03_eligible_fast=b,
        source_result_files={str(p):s.file_hash(p) for p in (full_path,fast_path)})
    target = s.ROOT/'regression_evidence'/(s.digest(evidence)+'.json')
    # No PASS claim until the existing clean-suite/9-slow/source/checksum verifier passes.
    for e in (a,b):
        if e['exit_code'] or e['failed'] or e['errors'] or not e['passed']:
            raise ValueError('required regression is not clean')
    s.seal(target,evidence)
    s.verify_regressions(target)
    return {'evidence':str(target),'canonical_sha256':s.digest(evidence)}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    from pathlib import Path
    p.add_argument('--project-i-result',required=True,type=Path)
    p.add_argument('--project03-result',required=True,type=Path)
    a = p.parse_args()
    print(json.dumps(assemble(a.project_i_result,a.project03_result),indent=2))
