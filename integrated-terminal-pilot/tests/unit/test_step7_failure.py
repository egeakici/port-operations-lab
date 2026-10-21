"""Owner-run diagnostics checks. Synthetic XML only; no model or simulation."""
import io

from integrated_terminal_pilot.benchmark.step7_failure import junit_failures,show_failures,support_report


def test_junit_retains_full_failure_and_error_details(tmp_path):
    path=tmp_path/'junit.xml'
    path.write_text('''<testsuites><testsuite>
      <testcase classname="tests.unit.a" name="passing"/>
      <testcase classname="tests.unit.a" name="wrong_value"><failure message="expected 4">assert 3 == 4</failure></testcase>
      <testcase classname="tests.unit.b" name="broken_setup"><error message="missing">FileNotFoundError: fixture</error></testcase>
    </testsuite></testsuites>''')
    rows=junit_failures(path);output=io.StringIO();show_failures(rows,output)
    assert len(rows)==2 and rows[1]['kind']=='error'
    assert 'assert 3 == 4' in output.getvalue() and 'FileNotFoundError: fixture' in output.getvalue()


def test_support_collector_preserves_failure_evidence_and_never_reads_scenarios(tmp_path):
    directory=tmp_path/'regressions/fixture';directory.mkdir(parents=True)
    xml=directory/'junit.xml';xml.write_text('<testsuites><testsuite><testcase name="fixture"><failure message="bad">TRACEBACK</failure></testcase></testsuite></testsuites>')
    original=xml.read_bytes()
    (tmp_path/'scenarios').mkdir();(tmp_path/'scenarios/forbidden.json').write_text('MUST_NOT_APPEAR')
    first=support_report(tmp_path,'fixture');second=support_report(tmp_path,'fixture')
    assert first==second and first['failures']==1 and xml.read_bytes()==original
    text=__import__('pathlib').Path(first['path']).read_text(encoding='utf-8')
    assert 'TRACEBACK' in text and 'MUST_NOT_APPEAR' not in text


def test_missing_junit_does_not_hide_collection_log(tmp_path):
    directory=tmp_path/'regressions/fixture';directory.mkdir(parents=True)
    (directory/'stdout.log').write_text('ImportError: broken collection')
    report=support_report(tmp_path,'collection failed')
    assert 'ImportError: broken collection' in __import__('pathlib').Path(report['path']).read_text(encoding='utf-8')
