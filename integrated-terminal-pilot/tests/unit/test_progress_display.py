"""Owner-run terminal rendering checks; no tests, policies or scenarios launched here."""
import io


def test_piped_progress_reuses_one_line_without_cursor_up(monkeypatch):
    from integrated_terminal_pilot.benchmark import execution
    output=io.StringIO()
    monkeypatch.setattr(execution.sys,'stderr',output)
    monkeypatch.setenv('ITP_TQDM_COLUMNS','96')
    # Old launchers must not force a second row in a logged child pipe.
    monkeypatch.setenv('ITP_TQDM_POSITION','1')
    with execution.progress_bar(3,description='Regression tests',unit='test') as bar:
        for _ in range(3):
            bar.update(1);bar.refresh()
    rendered=output.getvalue()
    assert '\x1b[A' not in rendered
    assert rendered.count('\n')==1
    assert '3/3' in rendered
    assert all(len(frame)<=95 for frame in rendered.replace('\n','').split('\r'))


def test_completed_phases_each_close_their_own_single_line(monkeypatch):
    from integrated_terminal_pilot.benchmark import execution
    output=io.StringIO()
    monkeypatch.setattr(execution.sys,'stderr',output)
    monkeypatch.setenv('ITP_TQDM_COLUMNS','110')
    for name in ('First phase','Second phase'):
        with execution.progress_bar(1,description=name) as bar:bar.update(1)
    assert output.getvalue().count('\n')==2
    assert '\x1b[A' not in output.getvalue()
