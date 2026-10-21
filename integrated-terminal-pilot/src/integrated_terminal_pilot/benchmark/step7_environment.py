"""Pre-lock numerical environment check, derived from the historical references."""
from importlib import metadata
import platform

from integrated_terminal_pilot.benchmark import step7 as s


def verify():
    spec=s.read_json(s.PROJECT_ROOT/'configs/protocol/step7_cpu_environment_v1.json')
    actual={'python':platform.python_version()}
    for name in spec['packages']:
        try:actual[name]=metadata.version(name)
        except metadata.PackageNotFoundError:actual[name]='MISSING'
    expected={'python':spec['python'],**spec['packages']}
    mismatches={name:{'expected':version,'actual':actual[name]} for name,version in expected.items()
                if actual[name].split('+')[0]!=version}
    if platform.python_implementation()!='CPython':mismatches['implementation']='CPython required'
    if mismatches:raise s.CampaignError('numerical reference environment differs; use Complete-Step7.ps1: '+str(mismatches))
    return dict(status='PASS',actual=actual,reference=expected)
