"""Scenario-level inference. No simulator, model loading, or outcome-dependent choices.

The frozen contract does NOT specify how Holm confidence intervals are constructed.
Consequently primary unadjusted intervals are calculated but cannot authorize a
Holm-confirmatory verdict. Wilcoxon is a separately labelled robustness check.
"""
from __future__ import annotations

import numpy as np
from scipy.stats import kendalltau, wilcoxon

SEEDS = (11, 23, 37)
FAMILIES = ("itp_heavy", "itp_medium")
RESAMPLES = 10_000
TIME_SEED = 120001
CARGO_SEED = 20261013
TIE = 1e-6  # inherited Project03 scenario-tail convention, vessel-minutes


class ContractError(ValueError):
    pass


def relative_difference(candidate, comparator):
    return None if comparator <= 0 else 100 * (candidate - comparator) / comparator


def nested_mean(members):
    if set(members) != set(SEEDS) or any(v is None for v in members.values()):
        raise ContractError("MISSING_INCOMPLETE_SEEDS: all 11/23/37 are required")
    return float(np.mean([members[k] for k in SEEDS]))


def bootstrap_draws(by_family, *, seed=TIME_SEED, resamples=RESAMPLES):
    """Same RNG/order/index/linear-quantile conventions as P03 stats and AM06.

    A new RNG is constructed for each estimand. Sorted family order, then sorted
    scenario identity within family. Family weights are equal. Single-family
    results independently reset the RNG, matching cargo_ni.noninferiority.
    """
    if not by_family or resamples <= 0:
        raise ContractError("No eligible paired scenarios")
    rng = np.random.default_rng(seed)
    draws = np.zeros(resamples, dtype=np.float64)
    for family in sorted(by_family):
        values = np.asarray(by_family[family], dtype=np.float64)
        if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
            raise ContractError("Bootstrap needs nonempty finite scenario differences")
        index = rng.integers(0, len(values), size=(resamples, len(values)))
        draws += values[index].mean(axis=1) / len(by_family)
    return draws


def interval(by_family, *, seed=TIME_SEED):
    draws = bootstrap_draws(by_family, seed=seed)
    lo, hi = np.quantile(draws, [.025, .975], method="linear")
    return dict(estimate=float(np.mean([np.mean(x) for x in by_family.values()])),
                lower=float(lo), upper=float(hi), n=sum(map(len, by_family.values())),
                seed=seed, resamples=RESAMPLES, method="paired stratified scenario percentile",
                quantile="numpy linear", confidence=.95, sidedness="two-sided")


def cargo_noninferiority(by_family):
    draws = bootstrap_draws(by_family, seed=CARGO_SEED)
    upper = float(np.percentile(draws, 95, method="linear"))
    lower = float(np.percentile(draws, 5, method="linear"))
    estimate = float(np.mean([np.mean(x) for x in by_family.values()]))
    return dict(estimate=estimate, upper=upper, lower_diagnostic_only=lower,
                margin=.01, verdict="PASSED" if upper <= .01 else "NOT_DEMONSTRATED",
                zero_margin="PASSED" if upper <= 0 else "NOT_DEMONSTRATED",
                n=sum(map(len, by_family.values())), seed=CARGO_SEED,
                resamples=RESAMPLES, quantile="numpy linear 95th percentile",
                sidedness="one-sided UPPER 95%", units="fraction of original obligations")


def time_label(ci, *, primary=False):
    if primary:
        return "BLOCKED_HOLM_CI_CONSTRUCTION_UNSPECIFIED"
    return "LOWER_TIME" if ci["upper"] < 0 else (
        "HIGHER_TIME" if ci["lower"] > 0 else "NO_DETECTABLE_DIFFERENCE")


def combined_label(time_verdict, cargo):
    if time_verdict.startswith("BLOCKED"):
        return "BLOCKED_PRIMARY_MULTIPLICITY"
    if time_verdict != "LOWER_TIME":
        return "NO_ESTABLISHED_TIME_GAIN"
    if cargo is None:
        return "TIME_GAIN_CARGO_NI_NOT_PREREGISTERED_FOR_THIS_PAIR"
    return ("TIME_GAIN_CARGO_NON_INFERIOR" if cargo["verdict"] == "PASSED"
            else "TIME_GAIN_CARGO_NI_NOT_DEMONSTRATED")


def tails(values, ids, *, tolerance=TIE):
    a = np.asarray(values, dtype=float)
    if len(a) != len(ids) or not len(a):
        raise ContractError("Tail identity mismatch")
    worst = float(a.max())
    return dict(wins=int((a < -tolerance).sum()), losses=int((a > tolerance).sum()),
                ties=int((np.abs(a) <= tolerance).sum()), median=float(np.median(a)),
                p95=float(np.quantile(a, .95, method="linear")), worst=worst,
                worst_ids=[sid for sid, v in zip(ids, a) if abs(v - worst) <= tolerance],
                tie_tolerance=tolerance)


def wilcoxon_robustness(values):
    """Supplementary; never used to sort Holm hypotheses or decide improvement.

    Pratt zero handling, two-sided normal approximation with continuity correction
    are explicit implementation choices, not a claimed pre-locked algorithm.
    """
    a = np.asarray(values, dtype=float)
    if not np.any(a):
        return dict(pvalue=1., method="all-zero paired differences", role="ROBUSTNESS_ONLY")
    result = wilcoxon(a, zero_method="pratt", alternative="two-sided",
                      correction=True, method="approx")
    return dict(pvalue=float(result.pvalue), statistic=float(result.statistic),
                method="Pratt, two-sided normal approximation, continuity correction",
                role="SUPPLEMENTARY_ROBUSTNESS_ONLY_NOT_DECISION_RULE")


def ranking_agreement(reference, integrated):
    return float(kendalltau(reference, integrated, variant="b").statistic)


def d24(vessels, t_end):
    if len({v["vessel_id"] for v in vessels}) != len(vessels):
        raise ContractError("Duplicate vessel")
    values = []
    for v in vessels:
        arrival = v["arrival_time_min"]
        departure = v.get("actual_departure_time_min")
        end = t_end if departure is None else min(departure, t_end)
        if end < arrival:
            raise ContractError("Departure/censor precedes arrival")
        values.append(end - arrival)
    return sum(values)


def validate_cargo(cargo, n_out, t_end):
    if cargo["N_out"] != n_out or cargo["T_end_min"] != t_end:
        raise ContractError("N_out/T_end mismatch")
    u, loaded = cargo["U_not_loaded"], cargo["loaded"]
    if n_out < 0 or u < 0 or loaded < 0 or u + loaded != n_out:
        raise ContractError("Cargo conservation")
    classes = cargo["classes"]
    if sum(classes.values()) != n_out:
        raise ContractError("Cargo classes do not partition obligations")
    if classes["LOADED_DEPARTED"] + classes["LOADED_VESSEL_AT_TERMINAL"] != loaded:
        raise ContractError("Loaded/departed facet mismatch")
    if classes["NOT_LOADED_ROLLED_OVER"] > u:
        raise ContractError("D17 is not loaded cargo")
    expected = None if n_out == 0 else u / n_out
    if cargo["R_loss_rate"] != expected:
        raise ContractError("R must use original container obligations, not TEU/moves")
    if not cargo["reconciliation_ok"] or not all(cargo["reconciliation"].values()):
        raise ContractError("Original ledger/final-state reconciliation failed")
    return expected


def validate_model_checkpoint(checkpoint, seed, expected_hash):
    if seed not in SEEDS or checkpoint["training_seed"] != seed or checkpoint["sha256"] != expected_hash:
        raise ContractError("Mismatched frozen PPO identity/SHA")
