"""One manual foreground command on the worker, or audit-only verification after copying back."""
import argparse
import json
from pathlib import Path
from integrated_terminal_pilot.benchmark import step7 as s
from integrated_terminal_pilot.benchmark.step7_workspace import DEFAULT_BUNDLE,bundle_path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--run',action='store_true')
    mode.add_argument('--verify-return',action='store_true')
    mode.add_argument('--status',action='store_true')
    p.add_argument('--bundle',type=Path,default=DEFAULT_BUNDLE)
    a=p.parse_args();root=bundle_path(a.bundle)
    try:
        if a.status:
            out=s.read_json(root/'pipeline_status.json') if (root/'pipeline_status.json').exists() else {'status':'NOT_STARTED'}
        else:
            from integrated_terminal_pilot.benchmark.step7_remote import run,verify_return
            out=run(root) if a.run else verify_return(root)
        print(json.dumps(out,indent=2,allow_nan=False));return 0
    except KeyboardInterrupt:
        print(json.dumps({'status':'FORCED_INTERRUPTION_PRESERVED','bundle':str(root),
                          'reason':'Inspect any partial scientific episode; do not delete its started marker.'}));return 130
    except Exception as exc:
        from integrated_terminal_pilot.benchmark.execution import ManualStop
        if isinstance(exc,ManualStop):
            print(json.dumps({'status':'INTERRUPTED_PRESERVED','bundle':str(root),'reason':str(exc)}));return 130
        print(json.dumps({'status':'BLOCKED_PRESERVED','bundle':str(root),'reason':f'{type(exc).__name__}: {exc}'}));return 2


if __name__=='__main__':raise SystemExit(main())
