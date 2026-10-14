"""New reporter arithmetic tests; no simulation, training, or Phase A repetition."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

path = Path(__file__).parents[2] / 'scripts' / 'report_step6_closure_f3.py'
spec = importlib.util.spec_from_file_location('closure_f3_report_tests', path)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def test_same_cohort_turnaround_and_future_wait_use_distinct_baselines():
    # At t=10, A has waited since 0, B arrives at 20, C already occupies.
    berth = SimpleNamespace(time_min=10, vessels=(
        SimpleNamespace(vessel_id='A', status='WAITING', arrival_time_min=0),
        SimpleNamespace(vessel_id='B', status='ANNOUNCED', arrival_time_min=20),
        SimpleNamespace(vessel_id='C', status='OCCUPYING', arrival_time_min=0),
        SimpleNamespace(vessel_id='D', status='DEPARTED', arrival_time_min=0)))
    actual = {key: {'berth_start_time_min': start, 'actual_departure_time_min': end}
              for key, start, end in [('A', 30, 80), ('B', 40, 90), ('C', 0, 50), ('D', 0, 5)]}
    turnaround, future_wait, censored = report.actual_cohort(berth, actual, 100, 200)
    assert turnaround == 80 + 70 + 50
    assert future_wait == 20 + 20  # elapsed waiting and occupying service excluded
    assert censored == []
    turnaround, future_wait, censored = report.actual_cohort(berth, actual, 60, 200)
    assert turnaround == 60 + 40 + 50 and future_wait == 40
    assert censored == ['A', 'B']


def test_status_at_rollover_is_not_overwritten_by_reservation_or_exception():
    def event(seq, time, kind, cls, status, location):
        r = [None] * 17
        r[0], r[1], r[2], r[3], r[7], r[9] = seq, time, kind, cls, status, location
        return r
    history = [event(1, 5, 'GATE_ARRIVED', 'PHYSICAL', 'AT_GATE', ('GATE', 'G1')),
               event(2, 10, 'YARD_RESERVATION_CREATED', 'PLAN', None, ('GATE', 'G1')),
               event(3, 15, 'ROLLED_OVER', 'EXCEPTION', 'AT_GATE', ('GATE', 'G1')),
               event(4, 20, 'RECEIVE_COMPLETED', 'PHYSICAL', 'IN_YARD', ('YARD_BLOCK', 'B1'))]
    got = report.physical_status_at(('EXPECTED_BY_LANDSIDE', 'EXTERNAL_LANDSIDE', None), history, 15)
    assert got == {'status': 'AT_GATE', 'location_kind': 'GATE', 'location_id': 'G1',
                   'last_physical_ledger_sequence': 1}
    assert report.physical_status_at(('EXPECTED_BY_LANDSIDE', 'EXTERNAL_LANDSIDE', None), history, 20)['status'] == 'IN_YARD'


@pytest.mark.parametrize('windows,expected', [((0, 10, 10, 20), 0), ((0, 20, 5, 15), 10), ((5, 15, 0, 10), 5)])
def test_wait_time_windows_do_not_double_count_touching_boundaries(windows, expected):
    assert report.interval_overlap(*windows) == expected


def test_rollover_state_uses_causal_sequence_within_one_timestamp():
    # A later same-timestamp physical record must not rewrite the earlier D17 evidence.
    def event(seq, status):
        row = [None] * 17
        row[0], row[1], row[3], row[7], row[9] = seq, 10, 'PHYSICAL', status, ('GATE', 'G1')
        return row
    history = [event(1, 'AT_GATE'), event(3, 'RECEIVING')]
    at_rollover = report.physical_status_at(('EXPECTED_BY_LANDSIDE', 'EXTERNAL_LANDSIDE', None),
                                           history, 10, max_sequence=2)
    assert at_rollover['status'] == 'AT_GATE'
    assert at_rollover['last_physical_ledger_sequence'] == 1
