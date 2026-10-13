"""Outbound loading obligations (``itp_outbound_obligation_v1``; AM-06 metric, pre-Step 6 brief section 7).

Definitions, per scenario ``s`` and arm ``a``:

* **Obligation**: one original container -> outbound vessel commitment, i.e. every container of the
  scenario manifest with a ``destination_vessel_id`` (export and outbound transshipment, including
  exports already in the yard at start). Counted once per container id. Imports (no destination
  vessel) are never outbound obligations. Units are containers - not TEU, not crane moves.
* ``N_out(s)``: number of obligations. Immutable, identical across arms and training seeds.
* **Fulfilled (primary)**: ``LOAD_COMPLETED`` recorded in the authoritative ledger at or before the
  common cutoff ``T_end(s)`` (the kernel never runs past ``T_end``). Scheduling a load never counts.
* ``U(a, s)`` = ``N_out(s)`` - fulfilled; ``R(a, s) = U / N_out`` (``NOT_APPLICABLE`` when ``N_out = 0``).

Every obligation falls in exactly one class (no double counting)::

    LOADED_DEPARTED              loaded and the vessel departed (DEPARTED_WITH_VESSEL)
    LOADED_VESSEL_AT_TERMINAL    loaded, vessel still at the quay at the stop (delivery facet pending)
    NOT_LOADED_ROLLED_OVER       ROLLED_OVER exception (D17) recorded; never loaded
    NOT_LOADED_VESSEL_PRESENT    not loaded; destination vessel not departed by the stop
    NOT_LOADED_OTHER             not loaded, vessel departed, no rollover record (should not occur;
                                 reported, never hidden)

Reconciliation: ``N_out = loaded + not_loaded`` and the class counts sum to ``N_out``; the ledger
classification is cross-checked against the final container status array.
"""

from __future__ import annotations

from typing import Any

from integrated_terminal_pilot.simulator.ledger import L_CONTAINER, L_TIME, L_TYPE

METRIC_SCHEMA = "itp_outbound_obligation_v1"
CLASSES = ("LOADED_DEPARTED", "LOADED_VESSEL_AT_TERMINAL", "NOT_LOADED_ROLLED_OVER", "NOT_LOADED_VESSEL_PRESENT",
           "NOT_LOADED_OTHER")
LOADED_STATUSES = frozenset({"LOADED", "DEPARTED_BY_VESSEL"})


class CargoMetricError(RuntimeError):
    pass


def outbound_obligations(kernel) -> dict[str, Any]:
    catalog, state = kernel.catalog, kernel.state
    if state.ledger is None:
        raise CargoMetricError("the outbound metric needs a recorded ledger (record_ledger=True)")
    t_end = catalog.drain_limit_min
    cutoff = min(state.now_min, t_end)
    loaded_at: dict[str, float] = {}
    departed: set[str] = set()
    rolled: set[str] = set()
    for record in state.ledger:
        kind = record[L_TYPE]
        if kind == "LOAD_COMPLETED" and record[L_TIME] <= t_end + 1e-9:
            if record[L_CONTAINER] in loaded_at:
                raise CargoMetricError(f"{record[L_CONTAINER]} loaded twice")
            loaded_at[record[L_CONTAINER]] = record[L_TIME]
        elif kind == "DEPARTED_WITH_VESSEL":
            departed.add(record[L_CONTAINER])
        elif kind == "ROLLED_OVER":
            rolled.add(record[L_CONTAINER])
    obligations = [c for c in catalog.containers if c.destination_vessel_id is not None]
    if len({c.container_id for c in obligations}) != len(obligations):
        raise CargoMetricError("duplicate outbound container id")
    classes = {name: 0 for name in CLASSES}
    by_flow: dict[str, dict[str, int]] = {}
    by_vessel: dict[str, dict[str, int]] = {}
    teu = {"obligations": 0.0, "not_loaded": 0.0}
    status_mismatch = []
    for c in obligations:
        vessel_departed = state.vessels[c.destination_vessel_id].phase == "DEPARTED"
        loaded = c.container_id in loaded_at
        if loaded:
            name = "LOADED_DEPARTED" if c.container_id in departed else "LOADED_VESSEL_AT_TERMINAL"
            if c.container_id in rolled:
                raise CargoMetricError(f"{c.container_id} both loaded and rolled over")
        elif c.container_id in rolled:
            name = "NOT_LOADED_ROLLED_OVER"
        elif not vessel_departed:
            name = "NOT_LOADED_VESSEL_PRESENT"
        else:
            name = "NOT_LOADED_OTHER"
        if loaded != (state.c_status[c.index] in LOADED_STATUSES):
            status_mismatch.append(c.container_id)
        classes[name] += 1
        teu["obligations"] += c.size_teu
        if not loaded:
            teu["not_loaded"] += c.size_teu
        for key, table in ((c.cargo_flow, by_flow), (c.destination_vessel_id, by_vessel)):
            row = table.setdefault(key, {"obligations": 0, "not_loaded": 0})
            row["obligations"] += 1
            row["not_loaded"] += int(not loaded)
    n_out = len(obligations)
    fulfilled = classes["LOADED_DEPARTED"] + classes["LOADED_VESSEL_AT_TERMINAL"]
    not_loaded = n_out - fulfilled
    reconciliation = {
        "classes_sum_to_n_out": sum(classes.values()) == n_out,
        "loaded_plus_not_loaded": fulfilled + not_loaded == n_out,
        "ledger_matches_final_status": not status_mismatch,
        "no_unexplained_not_loaded": classes["NOT_LOADED_OTHER"] == 0,
    }
    return {
        "schema": METRIC_SCHEMA,
        "unit": "containers (one obligation per original container -> outbound vessel)",
        "primary_definition": "LOAD_COMPLETED in the ledger at or before T_end",
        "cutoff_min": cutoff, "T_end_min": t_end,
        "N_out": n_out, "U_not_loaded": not_loaded, "loaded": fulfilled,
        "R_loss_rate": (not_loaded / n_out) if n_out else None,
        "applicability": "APPLICABLE" if n_out else "NOT_APPLICABLE",
        "classes": classes,
        "loaded_but_vessel_not_departed": classes["LOADED_VESSEL_AT_TERMINAL"],
        "teu": teu, "by_flow": by_flow, "by_destination_vessel": by_vessel,
        "reconciliation": reconciliation, "reconciliation_ok": all(reconciliation.values()),
        "status_mismatch_ids": status_mismatch[:20],
    }


__all__ = ["CLASSES", "CargoMetricError", "METRIC_SCHEMA", "outbound_obligations"]
