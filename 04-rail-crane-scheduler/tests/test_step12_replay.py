from dataclasses import replace
from pathlib import Path
import pytest
from test_step04_physics import solved
from rail_crane_scheduler.replay import *


def test_gantt_positions_png_and_no_source_writes():
    k=solved(); p=k.problem.to_json().encode(); s=k.schedule().to_json().encode()
    replay=load_replay(p,s)
    assert replay.positions(.5)==(1.,19.) and replay.positions(5)==(2.,18.)
    assert sum(end-start for cid,mode,start,end,task in replay.gantt() if mode=='PROCESS')==5
    assert png_bytes(gantt_figure(replay)).startswith(b'\x89PNG')
    assert png_bytes(rail_figure(replay,.5)).startswith(b'\x89PNG')
    assert p==k.problem.to_json().encode() and s==k.schedule().to_json().encode()


def test_corrupt_rejected_and_comparison():
    k=solved(); a=Replay(k.problem,k.schedule())
    b=Replay(k.problem,replace(k.schedule(),problem_hash='wrong'))
    assert not b.motion_safe
    with pytest.raises(ContractError): b.positions(1)
    q=replace(k.problem,metadata=replace(k.problem.metadata,scenario_id='other'))
    with pytest.raises(ContractError): compare([a,Replay(q,k.schedule())])
    assert len(compare([a,a]))==2
    with pytest.raises(ContractError): load_replay(b'NaN',b'{}')


def test_streamlit_initial_render():
    from streamlit.testing.v1 import AppTest
    path=Path(__file__).resolve().parents[1]/'frontend/replay_app.py'
    app=AppTest.from_file(str(path)).run(timeout=30)
    assert not app.exception
    assert app.title[0].value=='Quay crane schedule replay'
