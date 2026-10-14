"""Predeclared bounded Phase A A2 timing diagnostic, no F3 episodes."""
from dataclasses import asdict
import platform
import time
import psutil

from integrated_terminal_pilot.benchmark import step6
from integrated_terminal_pilot.benchmark.closure_gate import next_berth
from integrated_terminal_pilot.benchmark.policies import create_berth_policy
from integrated_terminal_pilot.benchmark.runner import resolve_research_profile
from integrated_terminal_pilot.benchmark.step6_closure import ROOT, digest, publish
from integrated_terminal_pilot.simulator.kernel import TerminalKernel


def probe():
    row = step6._scenario_row('itp_heavy', 10000000)
    doc = step6._load(row)
    _, catalog, _ = resolve_research_profile(doc, step6.PRIMARY)
    samples = []
    started = time.perf_counter()
    for arm in ('A1', 'A2'):
        kernel = TerminalKernel.from_catalog(catalog)
        driver = create_berth_policy(arm)
        for ordinal in range(1, 6):
            next_berth(kernel)
            view = kernel.berth_view()
            if ordinal in (1, 5):
                repeats = []
                for repeat in range(3):
                    policy = create_berth_policy('A2')
                    t = time.perf_counter()
                    policy.decide(view)
                    elapsed = time.perf_counter() - t
                    repeats.append({'repeat': repeat + 1, 'seconds': elapsed,
                                    'action': policy.records[0]['p03_action'], 'scores': policy.records[0]['scores']})
                samples.append({'trajectory': arm, 'ordinal': ordinal, 'time_min': view.time_min,
                                'view_sha256': digest(asdict(view)), 'revealed': len(view.vessels),
                                'nondeparted': sum(v.status != 'DEPARTED' for v in view.vessels),
                                'legal_assignments': len(view.legal_choices), 'wait_legal': view.wait_legal,
                                'repeats': repeats})
            if ordinal < 5:
                kernel.apply_berth_action(driver.decide(view))
    return {'kind': 'BOUNDED_DEVELOPMENT_A2_TIMING', 'scenario': row, 'samples': samples,
            'wall_seconds': time.perf_counter() - started, 'completed_episodes': 0,
            'host': {'platform': platform.platform(), 'python': platform.python_version(),
                     'cpu_count': psutil.cpu_count(), 'rss_mb': psutil.Process().memory_info().rss / 1024**2,
                     'load': 'uncontrolled; Project I regression suite also running'},
            'timing': 'decision call only; setup and trajectory excluded; all three repeats retained'}


if __name__ == '__main__':
    report = probe()
    print(publish(ROOT / 'phase_a' / ('a2_probe_' + digest(report)[:12] + '.json'), report))
