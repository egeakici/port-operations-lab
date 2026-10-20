"""Append-only regression observation hooks; no test selection or outcome mutation."""
import json
import os
from pathlib import Path


def emit(event):
    path=Path(os.environ['ITP_STEP7_TEST_EVENT_LOG'])
    with path.open('a',encoding='utf-8') as f:
        f.write(json.dumps(event,sort_keys=True)+'\n')


def pytest_collection_finish(session):
    emit({'kind':'collection','collected':len(session.items),
          'items':[{'nodeid':i.nodeid,'slow':bool(i.get_closest_marker('slow'))} for i in session.items]})


def pytest_runtest_logreport(report):
    emit({'kind':'test','nodeid':report.nodeid,'phase':report.when,
          'outcome':report.outcome,'seconds':report.duration})


def pytest_deselected(items):
    emit({'kind':'deselected','nodeids':[i.nodeid for i in items]})


def pytest_sessionfinish(session,exitstatus):
    emit({'kind':'sessionfinish','exitstatus':int(exitstatus)})
