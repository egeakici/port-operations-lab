"""Single fixed post-hoc method; no method selection from observed outcomes."""
from pathlib import Path
import numpy as np
from statistical import bootstrap_draws, TIME_SEED, RESAMPLES, ContractError
from evidence import read, sha

METHOD_PATH = Path(__file__).with_name('final_method_20261025.json')


def holm(pvalues):
    if not pvalues or any(not 0 <= p <= 1 for p in pvalues.values()):
        raise ContractError('Invalid Holm family')
    result, running = {}, 0.
    for i, key in enumerate(sorted(pvalues, key=lambda k: (pvalues[k], k))):
        running = max(running, (len(pvalues)-i)*pvalues[key])
        result[key] = min(1., running)
    return result


def simultaneous_interval(by_family, *, m=2, alpha=.05):
    if m != 2 or alpha != .05:
        raise ContractError('Frozen post-hoc method requires m2 alpha.05')
    draws = bootstrap_draws(by_family)
    estimate = float(np.mean([np.mean(v) for v in by_family.values()]))
    lo, hi = np.quantile(draws, [alpha/(2*m), 1-alpha/(2*m)], method='linear')
    p = (1 + np.count_nonzero(np.abs(draws-estimate) >= abs(estimate)))/(len(draws)+1)
    return dict(estimate=estimate, lower=float(lo), upper=float(hi),
                p_raw_centered_bootstrap=float(p), m=m, alpha=alpha,
                marginal_confidence=1-alpha/m, simultaneous_confidence=.95,
                method='POST_HOC conservative Bonferroni simultaneous percentile; supporting Holm tests',
                coverage='APPROXIMATE_BOOTSTRAP_NOT_FINITE_SAMPLE_EXACT',
                seed=TIME_SEED, resamples=RESAMPLES,
                verdict='LOWER_TIME' if hi < 0 else ('HIGHER_TIME' if lo > 0 else 'NO_DETECTABLE_DIFFERENCE'))


def complete(data):
    method = read(METHOD_PATH)
    output = []
    for population in method['populations']:
        families = ('itp_heavy','itp_medium') if population == 'equal_family_overall' else (population,)
        for metric in method['metrics']:
            rows = {}
            for name in method['hypotheses']:
                paired = data['source_pairs'][name]
                values = {f:[r[metric] for r in paired if r['family']==f] for f in families}
                rows[name] = simultaneous_interval(values)
            adjusted = holm({name:v['p_raw_centered_bootstrap'] for name,v in rows.items()})
            for name, result in rows.items():
                output.append(dict(population=population, metric=metric, hypothesis=name, **result,
                    p_holm=adjusted[name], holm_reject=adjusted[name] <= .05,
                    interval_test_disagreement=(result['verdict'] != 'NO_DETECTABLE_DIFFERENCE') != (adjusted[name] <= .05)))
    return dict(status='COMPLETE_WITH_POST_HOC_QUALIFICATION', method=method,
                method_file_sha256=sha(METHOD_PATH), rows=output,
                LOCKED_PROTOCOL_CONFIRMATORY='S1 and registered secondary/NI analyses only; primary adjusted interval construction not preregistered',
                POST_HOC_MULTIPLICITY_COMPLETION='Computed; owner acceptance required for qualified final release')
