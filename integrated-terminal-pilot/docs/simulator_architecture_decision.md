# Simulator Architecture Decision Record

ADR `ITP-ADR-001`. Status: **ACCEPTED (FROZEN, D05)**. Date: 2026-10-09.
Evidence: HEAD `66990eb`, plus empirical probes run in Step 1
([repository_capability_audit.md §7](repository_capability_audit.md#7-empirical-probes-scratch-scripts-outside-the-repository)).

## 1. Context

Project I needs one physics implementation that serves two uses:

1. **Execution** of an episode for every arm (A1, B1, A2, B2, A3).
2. **Predictive evaluation** (B2, and the integrated part of optional B3):
   from the same observed state, simulate the consequences of each candidate
   berth action and compare them.

Use 2 requires branching an in-progress simulation many times per decision:
exact, cheap, deterministic, without access to hidden future information. Writing
separate physics for lookahead is forbidden, because the forecast model and the real
terminal would silently diverge.

## 2. Options

**Approach A — reuse Project 02's SimPy engine (`mini_port_sim.simulation.PortSimulation`).**

**Approach B — a small deterministic, cloneable event kernel** that reuses
Project 01 vocabularies and validation semantics, Project 02 service and
efficiency definitions and RNG hashing pattern, and Project 03 geometry,
feasibility, candidate and objective functions.

## 3. Source evidence

| Question | Evidence | Finding |
| --- | --- | --- |
| Where does in-progress simulation state live in Project 02? | `simulation.py`: `self.env = simpy.Environment()`; `add_process` → `self.env.process(process_factory(self))`; processes such as `vessel_service_process`, `crane_task_process`, `berth_dispatcher_process` are generators that `yield simulation.env.timeout(...)` or dispatch events | Remaining work, timers and control flow are encoded in generator frames |
| Can the running simulation be copied? | Probe: `copy.deepcopy(sim)` and `pickle.dumps(sim)` → `TypeError: cannot pickle 'mappingproxy' object`; `copy.deepcopy(sim.env)`, a `Process`, its `_generator` → `TypeError: cannot pickle 'generator' object` | **No.** CPython generators cannot be copied or pickled |
| Can the SimPy queue be rebuilt from data? | Queue items are SimPy events bound to generator continuations (`yield` points in the middle of functions such as `_run_detailed_operations`) | Rebuilding requires re-expressing every process as data, which is Approach B under another name |
| Can Project 01 `Terminal` serve as cloneable state? | `copy.deepcopy(Terminal)` fails (`TerminalEvent.payload` is a `MappingProxyType`). `Terminal.from_dict(to_dict())` works but costs 5.6 ms at 42 events and 17.8 ms at 180 events. `_atomic()` performs a full `to_dict()` and a full `snapshot()` validation on **every** command | Correct but O(event log) per command; datetime-based; TEU-progress tasks; no container identity |
| Is Project 02 physics the integrated physics Project I needs? | `task_process.py`: IMPORT-only groups with `quantity = workload_moves` (20 ft) → 1 move = 1 container = 1 TEU; yard storage never released; efficiency fixed at task start; productivity RNG drawn per dispatch (policy-dependent order) | No: different physical model, unit conflation, policy-dependent randomness |
| Does Project 03 already face this? | `docs/dynamic_bap_environment.md`: SimPy processes "cannot pause at each masked online vessel-position choice without importing different physics", so Step 10 uses a local heap with three event types. `dynamic_online_rollout.py` branches a plain-data `_VisibleContinuation` with `copy.deepcopy` | Precedent: the repository already chose a plain-data heap kernel for decision-time branching |

## 4. Evaluation

| Criterion | A — SimPy reuse | B — cloneable kernel |
| --- | --- | --- |
| Determinism | Deterministic for a fixed process start order, but RNG consumption order is policy-dependent | Deterministic by construction: no runtime RNG in v1; total event order `(time, priority, stable key, sequence)` |
| Cloning | Impossible without re-implementation (probe) | Plain-data deep copy; immutable scenario shared |
| Event queue reconstruction | Not possible (continuations) | The queue *is* data |
| Performance per branch | Would need a full re-run from t=0 to the decision time per branch (replay cloning) | One copy of O(#vessels + #cranes + #blocks + #containers + #pending events) primitives |
| Reproducibility | Good in plain runs | Good in runs and in branches |
| Compatibility with existing domain APIs | Native Project 01 objects | Reuses enums, `ContainerGroup`, Project 03 core functions directly; Project 01 objects via audit projection |
| Risk of diverging from Project 02 behaviour | Low (it is Project 02) | Real but intended: Project 02 lacks export, transshipment, landside, distance and congestion. Rule-level equivalence tests (Step 3) cover the reused policies |
| Testability | Generator internals hard to unit-test | Every transition is a pure function of state; property tests and hand-worked traces |
| Complexity | Low to start; very high to add cloning | Moderate; bounded by the event list of the integration specification §8 |

Replay cloning, meaning re-running SimPy from t=0 with the decision prefix for each
branch, was considered. It is exact but costs O(episode length) per candidate per
decision, which is quadratic per episode. It would also still require the Project 02
physics to be replaced, so it offers no benefit over B.

## 5. Decision

Adopt **Approach B**. One kernel package (`integrated_terminal_pilot.kernel`,
Step 4) implements every physical transition. Execution and forward models
call the same transition functions:

```text
TerminalKernel(scenario: ScenarioDefinition, state: TerminalKernelState)
    .step_until_decision() -> DecisionRequest | EpisodeEnd
    .apply(action) -> None                     # via PhysicalActionValidator
    .clone() -> TerminalKernel                 # full state (audits, tests)
    .observable_clone() -> TerminalKernel      # hidden information removed (forward models)
```

What is reused, and how:

| Reused element | Mode |
| --- | --- |
| `berth_allocation_lab.core` geometry, candidates, feasibility, objectives | Called directly for every berth legality check |
| `berth_allocation_lab.core.numerics.is_close` / `NUMERICAL_TOLERANCE` | Same-timestamp grouping |
| `mini_port_sim.scenario.ServiceConfig` (`crane_efficiency`, nominal service fields) | Called directly |
| `mini_port_sim.rng.RandomStreams` hashing pattern | Generator (Step 2) only; entity-keyed |
| `terminal_core` enums and `ContainerGroup` | Field types |
| Project 01 reservation semantics, departure preconditions, flow rules | Re-asserted as kernel invariants; cross-checked by audit projection into `TerminalState` |
| Project 02 `GreedyCranePolicy` / `FirstFitYardPolicy` rules | Re-expressed over kernel observations; equivalence-tested on Project 01 fixtures |

## 6. Physical consistency and reproducibility strategy

1. **Single transition table.** Every state change goes through one
   function per event type or action type, and invariants are checked after
   each kernel cycle (integration specification §8.2).
2. **Same code for lookahead.** Forward models are kernel clones. A forward
   model may *restrict information* (observable clone) or *switch off
   modelled couplings* (ablation flags declared per arm). It may never
   implement alternative physics.
3. **Exact progress.** Rates are piecewise constant. Progress is settled
   before any change, and completion events carry `rate_generation`, so stale
   events are discarded.
4. **Total event order** `(time_min, priority, stable_key, sequence)`, with
   tolerance grouping from Project 03.
5. **No runtime randomness in v1.** All exogenous draws are materialized in
   the scenario (arrivals, manifests, gate-in and pickup times). Two
   executions of the same scenario and policy produce byte-identical ledgers.
   Test: run twice and compare ledger SHA-256.
6. **Clone fidelity test.** For random mid-episode states, continuing the
   original and its clone under the same policies yields identical ledgers and
   KPIs, and mutating the clone never changes the original.
7. **Independent validation.** Post-run ledger replay (foundation §8.3). The
   realized schedule is validated by Project 03 `find_schedule_violations` on the
   realized projection. Checkpoints are projected into Project 01
   `TerminalState` validation.
8. **Degenerate equivalence** against Project 03 `DynamicBAPEnv`
   ([implementation_roadmap.md](implementation_roadmap.md#step-4--cloneable-integrated-terminal-simulator)).

## 7. Consequences

- Project 02's SimPy engine remains the Project 02 reference and is not
  modified or wrapped.
- Some behaviour differs from Project 02 by design (recomputed multi-crane
  efficiency, export/transshipment/landside flows, transport and congestion).
  These differences are documented, not hidden.
- Cloning cost scales with the number of containers. If a profile in Step 4
  shows forward models dominated by container copying, the documented
  optimization is copy-on-write per container *list*, not a change of physics.
- If cloning were ever needed for Project 02 itself, it would require
  rewriting its processes as data. That is out of scope.
