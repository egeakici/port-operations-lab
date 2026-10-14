# Step 6 Observation and Forecast Contract

This document defines what the B arms may know at a berth decision, and how the B2/B2-T forward
model is kept free of hidden future truth. Source of truth: integration specification §10
(information contract, D26) and §11 (ServiceForecaster v1). Implementation:
`src/integrated_terminal_pilot/benchmark/coordination_view.py`.

## 1. `CoordinationView` (`itp_coordination_view_v1`) — allowlist and provenance

Every field is a frozen dataclass of primitive values, built by the trusted observer from the live
kernel at the decision instant. The policy never receives the kernel.

| Field | Contents | Allowed source (spec §10) |
| --- | --- | --- |
| `berth` | Step 5 `BerthView`: revealed vessels (announced, waiting, occupying, departed) in slot order; arrival, length, nominal service; actual berth position and start; `ServiceForecaster v1` release of occupying vessels; physical legal set; WAIT bit | row 1 (from horizon entry), forecast row |
| `cranes` | id, assigned vessel, activity, working flag, nominal rate, compatibility | row 3 "crane assignments": observable to B arms |
| `vessels` | Revealed, not departed vessels only. Phase, `max_cranes`, assigned cranes, remaining inbound moves aboard, outbound manifest size, loaded count, outbound containers per yard block, outbound not yet in the terminal, rolled-over count | row 1 (manifests of announced vessels) + row 3 (realized progress) |
| `blocks` | Status, capacity, occupied/reserved/blocked TEU, handling capacity, transfer point, capabilities, sizes, active ship/landside flows | row 3 (yard occupancy, reservations, current rates) |
| `physics` | Published coefficients: efficiencies, productivity, transport, congestion, landside reserve, preparation times, minutes per move, D15, D17 | scenario physics block (all arms run on it) |
| `projection` | `SafeProjection` (B2/B2-T only), see §2 | spec §10: forward models run the same kernel on an ObservableClone |
| `digest` | SHA-256 of the canonical view content (projection represented by its digest) | — |

**Never present:** unannounced vessels (no record, slot, count or bit); future gate-in or pickup
times; the event queue; scenario id, seed, split or fingerprints; the ledger and event log; the
`TerminalKernel` or its state; random-generator state (the kernel has none).

The view does not expose the hidden-vessel id of a transshipment or export link. In the
projection, such ids are replaced by the reserved placeholder `V000`. Policies refuse anything
that is not a `CoordinationView` (`B_POLICY_GATE_G6-02`), including the kernel, its state, its
catalog or a dict.

## 2. `SafeProjection` (`itp_safe_projection_v1`) — the B2/B2-T forward-model seed

1. **Step 4 `observable_clone()`** (audited):
   - it removes every HIDDEN vessel (record, events, state) and every container that is neither in
     the terminal nor on a visible manifest;
   - it removes every future `GATE_IN_ARRIVAL` and `PICKUP_DUE` event and every gate-in time; pickup
     times survive only for requests that already occurred;
   - it removes scenario identity, seed and fingerprints, the ledger and the event log, and sets
     the drain limit to last *visible* arrival + extension.
2. **Step 6 sanitisation** closes two residual channels found in the audit:
   - **Event sequence numbers.** The originals count hidden events scheduled at initialisation, so
     they encode hidden information. They are renumbered 1…n in queue order, and
     `next_event_seq = n + 1`.
   - **Unrevealed vessel ids.** Ids still referenced by kept container and group records (yard
     exports or transshipment links to unannounced vessels) are replaced by `V000`.
3. **Freezing:** the result is held as pickled bytes plus the redacted catalog. `fork()` builds a
   private kernel per evaluation, so candidates cannot share state or caches. Sub-branches of the
   WAIT candidate use `clone()` of an already-sanitised fork, never of the real kernel.
4. **Assertions at build time:** no identity or fingerprints in the catalog, and no ledger or event
   log in the state (`G6-02`).

## 3. Forecast assumptions (`itp_step6_forecast_v1`, identical for B2 and B2-T)

| Assumption | Rule | Status |
| --- | --- | --- |
| Future landside requests | not simulated: no future gate-in or pickup; requests already due are processed | spec §10 PROPOSED rule (Q6-2) |
| Hidden vessels | absent | spec §10 (FROZEN) |
| Announced vessels | arrive at their announced time | D18 (FROZEN) |
| Physics | the same Step 4 kernel (cranes, transport, yard, D15/D16/D17/R5) on the projected state | spec §10 |
| Randomness | none: deterministic, one replication; common random numbers trivially shared across candidates | — |
| Uncertainty | `UNCALIBRATED_SYNTHETIC_FORECAST` | no calibration evidence exists |

**Why "not simulated" loses no visible outbound cargo.** The export cutoff (360 min before arrival)
exceeds the announcement horizon (240 min). Every export of a visible vessel has therefore
requested gate-in before the vessel became visible. Transshipment inbound legs connect at least
720 min earlier, so they are already-arrived vessels. A visible vessel's outbound obligations are
thus all observable at the decision.

## 4. Predictions (Q6-4, PROPOSED)

- **Cohort:** revealed, not departed vessels at the decision.
- **Predicted turnaround:** Σ over the cohort of `min(departure, T_inner) − arrival`, with
  `T_inner` = last visible arrival + drain extension. A vessel that has not departed is charged up
  to `T_inner`, which is common to every candidate, so truncation is never rewarded.
- **Predicted unfulfilled outbound:** cohort outbound obligations whose container is not `LOADED` or
  `DEPARTED_BY_VESSEL` at the inner stop. These are known obligations only; never the
  full-scenario `N_out`.
- **Invalid-candidate contract (symmetric):**
  - an inner kernel failure or validator rejection fails the decision, and therefore the run
    (`G6-15`);
  - exceeding the engineering guard (400,000 cycles per leaf) fails the decision with
    `INCOMPLETE_ENGINEERING_PROBE` (`G6-12`).

  No candidate is ever skipped or scored as infinitely good or bad.

## 5. Test evidence

`tests/unit/test_step6_coordination.py`:

- **G6-02:** the view is frozen and allowlisted; no hidden vessel or gate-in time appears; the
  sequence numbers are renumbered; raw kernel, state, catalog and dict inputs are refused.
- **G6-03:** the paired-state adversarial test covers five hidden-truth perturbations:
  - (a) the unrevealed vessel's arrival and content;
  - (b) future gate-in and pickup times;
  - (c) hidden events that tie with visible ones;
  - (d) the hidden transshipment link target;
  - (e) the scenario seed and identity.

  In all five, the view digest, the projection digest, the candidate predictions (byte-equal), the
  B2/B2-T selections and the B1 action are identical. A separate *observable* yard-placement
  perturbation changes B1's choice (V001 → V002) while the A-arm `BerthView` and the A1 decision
  stay identical.
- **G6-10:** after the view is built, the real kernel's state and catalog are set to `None`; B1
  and B2 still decide, which proves there is no path back to the kernel.
- **G6-07 / G6-14:** B2 and B2-T produce byte-identical prediction records and budget
  fingerprints, results are invariant to candidate order, and repeated runs give identical traces
  and prediction digests (full/summary parity).

The K5 probe re-checked order invariance and replication on development states (both identical).
