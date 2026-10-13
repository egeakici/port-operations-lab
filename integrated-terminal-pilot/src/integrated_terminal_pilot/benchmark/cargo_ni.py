"""CARGO-NI pre-registered analysis rule (AM-06, safeguard S1) - pure computation, no simulation.

For policy ``p``, its mandatory reference ``c`` and scenario ``s``: ``d_s = R(p, s) - R(c, s)`` with
``R`` the outbound-obligation loss rate (``benchmark.cargo``). Non-inferiority holds when the one-sided
95 % upper confidence bound of the across-scenario paired mean of ``d_s`` is ``<= +0.01``.

* Reference map (``COMPARATOR_MAP``): A2->A1, A3-train{k}->A1 (descriptive per seed), A3 (nested
  aggregate)->A1, B1->A1, B2->A2, B2-T->A2 (ablation), B2 vs B2-T (objective ablation),
  B3-train{k}->A3-train{k}, B3 aggregate->A3 aggregate. A1 is never compared with itself. Anything
  else fails closed.
* A3 / B3 nesting: per scenario, the arithmetic mean over **all three** training seeds 11/23/37; a
  missing seed makes that scenario's aggregate MISSING (never an average of the survivors).
  Resampling is over scenario seeds only.
* Bootstrap: paired, scenario-level, 10,000 resamples with replacement, RNG seed 20261013
  (``numpy.random.default_rng``); the upper bound is the 95th percentile (numpy ``linear``) of the
  resampled means. Per-family results are primary; the optional stratified overall estimate resamples
  within each family and averages family means with equal family weight.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

MARGIN = 0.01
SENSITIVITY_MARGIN = 0.0
CONFIDENCE = 0.95
RESAMPLES = 10_000
BOOTSTRAP_SEED = 20261013
TRAINING_SEEDS = (11, 23, 37)
SMALL_N = 10

COMPARATOR_MAP: tuple[dict[str, str], ...] = (
    {"purpose": "S1", "policy": "A2", "reference": "A1", "kind": "primary"},
    {"purpose": "S1", "policy": "A3-train11", "reference": "A1", "kind": "per_seed_descriptive"},
    {"purpose": "S1", "policy": "A3-train23", "reference": "A1", "kind": "per_seed_descriptive"},
    {"purpose": "S1", "policy": "A3-train37", "reference": "A1", "kind": "per_seed_descriptive"},
    {"purpose": "S1", "policy": "A3", "reference": "A1", "kind": "primary_nested_aggregate"},
    {"purpose": "S2", "policy": "B1", "reference": "A1", "kind": "primary"},
    {"purpose": "S2", "policy": "B2", "reference": "A2", "kind": "primary_package_effect"},
    {"purpose": "S2", "policy": "B2-T", "reference": "A2", "kind": "objective_ablation"},
    {"purpose": "S2", "policy": "B2", "reference": "B2-T", "kind": "objective_ablation_within_coordinated"},
    {"purpose": "S2", "policy": "B3-train11", "reference": "A3-train11", "kind": "optional_per_seed"},
    {"purpose": "S2", "policy": "B3-train23", "reference": "A3-train23", "kind": "optional_per_seed"},
    {"purpose": "S2", "policy": "B3-train37", "reference": "A3-train37", "kind": "optional_per_seed"},
    {"purpose": "S2", "policy": "B3", "reference": "A3", "kind": "optional_nested_aggregate"},
)
NESTED = {"A3": "A3-train", "B3": "B3-train"}


class ComparisonContractError(ValueError):
    """Unknown or non-canonical pair, or inconsistent paired inputs: fails closed."""


def comparison(policy: str, reference: str) -> dict[str, str]:
    for row in COMPARATOR_MAP:
        if row["policy"] == policy and row["reference"] == reference:
            return dict(row)
    raise ComparisonContractError(f"{policy} vs {reference} is not a pre-registered comparison")


def references_for(policy: str) -> tuple[str, ...]:
    refs = tuple(r["reference"] for r in COMPARATOR_MAP if r["policy"] == policy)
    if not refs:
        raise ComparisonContractError(f"{policy!r} has no pre-registered reference (A1 is a comparator only)")
    return refs


@dataclass(frozen=True)
class ArmOutcome:
    """One run's outbound accounting: arm label (e.g. 'A3-train11'), scenario identity and counts."""

    scenario_id: str
    family: str
    arm: str
    n_out: int
    not_loaded: int | None          # None = run missing / failed (no fabricated value)

    @property
    def rate(self) -> float | None:
        if self.not_loaded is None or self.n_out == 0:
            return None
        return self.not_loaded / self.n_out


def scenario_rates(outcomes: Iterable[ArmOutcome], arm: str) -> dict[str, dict[str, Any]]:
    """Per-scenario rate for a plain arm or a nested aggregate ('A3', 'B3'); records missing/NA explicitly."""
    by_scenario: dict[str, dict[str, ArmOutcome]] = {}
    for o in outcomes:
        by_scenario.setdefault(o.scenario_id, {})[o.arm] = o
    out: dict[str, dict[str, Any]] = {}
    for scenario_id, arms in sorted(by_scenario.items()):
        if arm in NESTED:
            members = [arms.get(f"{NESTED[arm]}{k}") for k in TRAINING_SEEDS]
            present = [m for m in members if m is not None]
            if not present:
                continue
            n_out = {m.n_out for m in present}
            if len(n_out) != 1:
                raise ComparisonContractError(f"{scenario_id}: training seeds disagree on N_out {sorted(n_out)}")
            n = n_out.pop()
            family = present[0].family
            if n == 0:
                out[scenario_id] = {"status": "NOT_APPLICABLE", "rate": None, "n_out": 0, "family": family}
            elif len(present) < 3 or any(m.rate is None for m in present):
                out[scenario_id] = {"status": "MISSING_INCOMPLETE_SEEDS", "rate": None, "n_out": n, "family": family,
                                    "seeds_present": [k for k, m in zip(TRAINING_SEEDS, members)
                                                      if m is not None and m.rate is not None]}
            else:
                out[scenario_id] = {"status": "OK", "rate": sum(m.rate for m in present) / 3.0, "n_out": n,
                                    "family": family, "per_seed": {k: m.rate for k, m in zip(TRAINING_SEEDS, members)}}
        elif arm in arms:
            o = arms[arm]
            status = "NOT_APPLICABLE" if o.n_out == 0 else ("MISSING" if o.rate is None else "OK")
            out[scenario_id] = {"status": status, "rate": o.rate, "n_out": o.n_out, "family": o.family}
    return out


def paired_differences(outcomes: Iterable[ArmOutcome], policy: str, reference: str) -> dict[str, Any]:
    spec = comparison(policy, reference)
    outcomes = list(outcomes)
    p, r = scenario_rates(outcomes, policy), scenario_rates(outcomes, reference)
    pairs, excluded = [], []
    for scenario_id in sorted(set(p) | set(r)):
        a, b = p.get(scenario_id), r.get(scenario_id)
        if a is None or b is None:
            excluded.append({"scenario_id": scenario_id, "reason": "MISSING_ARM"})
            continue
        if a["n_out"] != b["n_out"]:
            raise ComparisonContractError(f"{scenario_id}: N_out differs between {policy} ({a['n_out']}) and "
                                          f"{reference} ({b['n_out']}); not a paired case")
        if a["status"] != "OK" or b["status"] != "OK":
            excluded.append({"scenario_id": scenario_id, "reason": a["status"] if a["status"] != "OK" else b["status"]})
            continue
        pairs.append({"scenario_id": scenario_id, "family": a["family"], "d": a["rate"] - b["rate"],
                      "policy_rate": a["rate"], "reference_rate": b["rate"], "n_out": a["n_out"]})
    return {"comparison": spec, "pairs": pairs, "excluded": excluded}


def _bootstrap_means(values: np.ndarray, rng: np.random.Generator, resamples: int) -> np.ndarray:
    index = rng.integers(0, len(values), size=(resamples, len(values)))
    return values[index].mean(axis=1)


def noninferiority(differences: list[float], *, margin: float = MARGIN, resamples: int = RESAMPLES,
                   seed: int = BOOTSTRAP_SEED, confidence: float = CONFIDENCE) -> dict[str, Any]:
    values = np.asarray(differences, dtype=float)
    n = len(values)
    if n == 0:
        return {"verdict": "NO_ELIGIBLE_PAIRS", "n_pairs": 0, "margin": margin}
    means = _bootstrap_means(values, np.random.default_rng(seed), resamples)
    upper = float(np.percentile(means, 100 * confidence))
    estimate = float(values.mean())
    if upper <= margin:
        verdict = "NON_INFERIOR"
    elif estimate <= margin:
        verdict = "INCONCLUSIVE"
    else:
        verdict = "INFERIOR"
    diagnostics = []
    if n < SMALL_N:
        diagnostics.append(f"small N ({n} < {SMALL_N}): bootstrap interval unreliable")
    if float(values.std()) == 0.0:
        diagnostics.append("zero variance: the bound equals the estimate")
    return {"verdict": verdict, "n_pairs": n, "estimate": estimate, "upper_bound": upper, "margin": margin,
            "confidence": confidence, "resamples": resamples, "seed": seed, "method": "paired scenario bootstrap, "
            "one-sided percentile upper bound (numpy linear)", "diagnostics": diagnostics}


def stratified_noninferiority(pairs: list[dict[str, Any]], *, margin: float = MARGIN, resamples: int = RESAMPLES,
                              seed: int = BOOTSTRAP_SEED) -> dict[str, Any]:
    """Per-family results (primary) plus an equal-family-weight stratified overall bound."""
    families = sorted({p["family"] for p in pairs})
    per_family = {f: noninferiority([p["d"] for p in pairs if p["family"] == f], margin=margin,
                                    resamples=resamples, seed=seed) for f in families}
    if not families:
        return {"per_family": {}, "overall": {"verdict": "NO_ELIGIBLE_PAIRS", "n_pairs": 0}}
    rng = np.random.default_rng(seed)
    family_means = np.stack([_bootstrap_means(np.asarray([p["d"] for p in pairs if p["family"] == f]), rng, resamples)
                             for f in families])
    overall_means = family_means.mean(axis=0)
    estimate = float(np.mean([np.mean([p["d"] for p in pairs if p["family"] == f]) for f in families]))
    upper = float(np.percentile(overall_means, 95))
    verdict = "NON_INFERIOR" if upper <= margin else ("INCONCLUSIVE" if estimate <= margin else "INFERIOR")
    return {"per_family": per_family, "overall": {"verdict": verdict, "estimate": estimate, "upper_bound": upper,
                                                 "n_pairs": len(pairs), "families": families,
                                                 "weighting": "equal weight per family"}}


def turnaround_claim_label(turnaround_improved: bool, cargo_result: dict[str, Any]) -> str:
    if not turnaround_improved:
        return "NO_TURNAROUND_GAIN"
    if cargo_result.get("verdict") == "NON_INFERIOR":
        return "TURNAROUND_GAIN_CARGO_NON_INFERIOR"
    return "TURNAROUND_GAIN_WITH_UNPROVEN_OR_EXCESS_CARGO_LOSS"


__all__ = ["ArmOutcome", "BOOTSTRAP_SEED", "COMPARATOR_MAP", "ComparisonContractError", "MARGIN", "RESAMPLES",
           "SENSITIVITY_MARGIN", "comparison", "noninferiority", "paired_differences", "references_for",
           "scenario_rates", "stratified_noninferiority", "turnaround_claim_label"]
