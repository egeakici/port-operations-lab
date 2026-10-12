# Protocol Amendment Register (`itp_protocol_v1`)

Append-only register of proposed and approved amendments to
[scientific_experiment_protocol.md](scientific_experiment_protocol.md). The frozen protocol text is
never edited in place: an amendment records what changes, why, and its approval state. A superseded
rule stays documented; it is marked superseded by a later record, never deleted.

Amendments may be approved only **before** any validation result is read (protocol §9).

---

## AM-01 — Common yard baseline: occupancy balancing for every arm

- **Status:** PROPOSED / PENDING USER APPROVAL
- **Proposed:** 2026-10-12 (Step 4 closure)
- **Affects:** protocol §3 (definition of the common primitive P_y). Physics is unchanged.
- **Approved:** no. Until it is approved, the frozen protocol §3 P_y (`yard_first_fit_v1`) remains the
  experimental default everywhere, including `default_policies()` and
  `simulator.diagnostics.REFERENCE_YARD_POLICY_ID`.

### Proposed text

> For all primary arms A1, A2, A3, B1, B2 and the optional B3, the common yard primitive P_y is the
> Step 3 policy `yard_occupancy_balance_v1`, applied identically in every arm. Among the blocks
> that pass the unchanged Step 3 eligibility tests (OPEN status, size, capabilities, TEU test
> `capacity − occupied − reserved − blocked ≥ required`), it chooses the lowest projected
> occupancy `(occupied_teu + reserved_teu + required_teu) / capacity_teu`; ties go to the lower
> `block_id`. The former P_y, `yard_first_fit_v1`, is retained unchanged as the diagnostic
> reference `P_y_ff`.

### Rationale and limits

- **Same primitive in every arm.** AM-01 changes the *common* operational primitive. It gives no
  arm additional yard knowledge, so it does not create an A/B information difference. Coordination
  still changes berth decisions only.
- **Why.** Step 4 development runs showed that first fit sends every discharge and gate receipt to
  the lowest-id block with free TEU. That block's handling share then caps the whole terminal's
  discharge throughput and makes berth-position effects depend on B01 alone. A common primitive
  with such a pathology could mask real differences between arms.
- **Information.** The balancing rule reads only fields of the Step 3 `YardObservation`: block
  status, capabilities, sizes, capacity, occupied, reserved and blocked TEU, and the request's cargo
  identity and flow. It does not read berth positions, crane state, transport distance, handling
  rates, future gate or pickup truth, or any future terminal state (tested).
- **Not an optimum.** Balancing is a design-motivated pre-validation candidate, not an empirically
  established best rule and not a calibrated terminal yard planner. It may have its own
  shortcomings. For example, it ignores transfer distance and spreads landside work over many blocks.
- **Implementations unchanged.** Both Step 3 policies keep their ids and decision logic; the switch
  is a configuration choice.

### Approval checklist (to be completed by the user)

1. [ ] Review the closure diagnostics ([step4_closure_diagnostics.md](step4_closure_diagnostics.md))
   for C1 (balanced vs first fit).
2. [ ] Confirm that a common balanced P_y is wanted for every arm (A1/A2/A3/B1/B2/B3).
3. [ ] Confirm that first fit is kept as the diagnostic reference `P_y_ff`.
4. [ ] Record the approval below (date, approver, scope).

**After approval (one-line switch, no physics change):** set
`REFERENCE_YARD_POLICY_ID = "yard_occupancy_balance_v1"` in
`src/integrated_terminal_pilot/simulator/diagnostics.py`, and set the `default_policies()` yard
policy to the same id. Then append a record "AM-01 APPROVED" and a record "Protocol §3 P_y
(`yard_first_fit_v1`) SUPERSEDED by AM-01" to this register. Update the Step 3 registry role of
`yard_occupancy_balance_v1` from `diagnostic` to `primitive`, and the role of `yard_first_fit_v1`
to `diagnostic_reference`.

### Approval record

_(none — pending)_
