# Project I research handoff

Project I is the eight-step Integrated Terminal Pilot. **Scientific closure
requires actual new13M diagnostics and accepted scientific resolutions; code
readiness alone does not establish it.**
Use [the current machine status](step8/CURRENT_FINAL_CLOSURE.json) and
[closure note](../PROJECT_I_SCIENTIFIC_CLOSURE.md); these pointers are refreshed
after each verified derived release. Prior releases remain immutable. No Step9.

The study asks whether berth decisions benefit from modeling shared cranes,
transport, yard and cargo obligations. This is terminal-aware berth coordination,
not three jointly trained RL controllers. No real-terminal calibration or savings
are established. Negative and mixed findings are research results, not failed tests.

1. Step1 established physical/information contracts and integration design.
2. Step2 froze deterministic synthetic traffic, cargo, fingerprints and split bands.
3. Step3 implemented common crane/yard primitives and policy interfaces.
4. Step4 implemented the shared discrete-event kernel, cargo ledger and invariants.
5. Step5 connected unchanged berth policies and frozen PPO with support gates.
6. Step6 implemented coordination and independent scoped A2/B2-T equivalence;
   owner approved Q6, uncapped evaluation and a bounded development campaign.
7. Step7 locked approved synthetic values, six checkpoints, reference runtime,
   pairing and protocol. All1960 episodes completed. The official return receipt
   verified31626 files (13,451,426,704 bytes). It must NOT be rerun as routine analysis.
8. Step8 performs scenario-paired inference, S1 reference comparisons, cargo NI,
   objective/coupling ablations, OFAT sensitivity and qualified scientific release.

Authoritative rules: [protocol](scientific_experiment_protocol.md),
[AM01-10](protocol_amendments.md), [roadmap](implementation_roadmap.md),
[scoped gate](step6_closure_contract_gate.md). These originals are not rewritten.
New source quotations, exact line numbers and proposals appear in the versioned
`step8/final_closure/<plan-id>/` packet. FC01 is a **post-hoc** interval completion;
FC02 scopes realistic none/A2 comparison; FC03 retains unsupported Heavy0.3 cells.
Explicit owner acceptance is required; no approval is implied by this handoff.

| Arm | Meaning |
| --- | --- |
| A1 | Online FCFS berth decisions |
| A1n | Nominal one-step release greedy control |
| A2 | Authentic Project03 berth-only full-visible-cohort rollout |
| A3 | Frozen berth PPO, train11/23/37, CPU inference |
| B1 | Integrated current-state one-step release estimator, accepted limitations |
| B2-T | Full integrated model, turnaround-only selector |
| B2 | Same integrated model, AM07 lexicographic original-unloaded-cargo then turnaround |

Shared primitives remain greedy crane assignment and balanced yard selection.
Primary profile is eight cranes, assigned efficiency (two cranes0.92), D15=10,
D17=240min and R5 one FIFO GATE_OUT batch per block. No cohort cap, timeout
fallback or policy substitution. Sensitivity conditions explicitly version changed
physics; model-only coupling does not change the actual outer terminal.

Medium/Heavy TEST each have50 independent traffic scenarios. PPO seeds are nested
within each scenario, never n150 independent scenarios. Validation, development
and Low/Bottleneck diagnostics have distinct roles. New13M diagnostics use20
scenarios per family/condition, not more TEST evidence for model selection.

| Primary TEST result | Medium | Heavy |
| --- | --- | --- |
| B2-A2 time change min/vessel, original raw95% CI | -20.364 [-35.051,-6.208] | -101.970 [-129.376,-75.515] |
| B2-A2 mean paired percentage | -1.377% | -5.610% |
| B2-A2 cargo upper95, percentage points | -0.248499 | -2.446716 |
| B2-A2 +1pp NI / zero-margin sensitivity | pass/pass | pass/pass |
| PPO-A1 time change min/vessel, raw95% CI | -37.833 [-53.704,-23.120] | -42.624 [-65.851,-19.345] |
| PPO-A1 cargo upper95, percentage points | +0.566327 | +2.879220 |
| PPO-A1 +1pp NI / zero-margin sensitivity | pass/not demonstrated | not demonstrated/not demonstrated |

Primary raw95% intervals above are historical counterparts. The latest report
adds fixed post-hoc97.5% marginal simultaneous intervals (m2, approximate family
coverage95%) and supporting Holm tests; it does not retroactively preregister them.
PPO is slower than A2 on mean turnaround. B2 improves mean time/cargo against A2
but loses time in18/50 Medium and6/50 Heavy scenarios. Heavy B2 vs B2-T improves
mean U45.12 to0.48 with +7.49min/vessel time change, raw95%[-0.76,15.67]; that
positive time cost is not statistically established. B1 has negative/mixed findings.

B2 Heavy selection mean8.258s, P95~26.136s, maximum69.540s versus PPO~3.7ms.
This is research compute, not a certified online deadline. WAIT/forecast and cargo
loss diagnostics are selected-trajectory associations, not causal ablation effects.
Frozen berth PPO does not demonstrate Yard RL effectiveness; that requires separate work.

Authoritative data live under `experiments/step7_remote/step7_cpu3132_v2/`:
`protocol_lock_v1.json`, `transfer_manifest.json`, sealed official return receipt,
`18738b886e1f/runs`, `traces`, `observations`, `diagnostics`, `scenarios`, `reports`.
Large data stay ignored by Git. Never edit raw records, ledgers, checkpoint ZIPs,
approvals, manifests, or historical releases. Keep a backed-up immutable master.

New outputs: `experiments/step8_final_closure/<plan-id>/plan.json`, `scenarios/`,
`cells/<fingerprint>/result.json`, canonical `trace/*.gz`, `policy_records.json.gz`,
`COMMIT.json`, `attempts/`, `approvals/`, verification receipts and `releases/`.
Each release carries a manifest, exact source snapshot, tables, PNG/SVG figures,
seven Markdown reports, all exceptions and a machine closure gate. No PDF is
currently required or generated. Historical8 figure families are retained with
their original raw95/provisional labels; new primary figures show the adjustment.

Schema glossary: TA=D24 censored vessel-minutes; min/vessel divides within scenario;
U=original outbound containers without authoritative LOAD_COMPLETED by T_end;
N_out=original export/outbound-transshipment obligations; R=U/N_out; pp=100*deltaR;
TEU, moves and containers are distinct. Mean paired percentage differs from ratio
of group means. D17 rollover is not successful loading. Check scenario/physical
fingerprints and all3 PPO seeds before pairing. Diagnostic intervals are raw95%
descriptive uncertainty, not simultaneous inference over the whole matrix.

Read-only reproduction, from repository root (existing project Python):

```powershell
python -B integrated-terminal-pilot/step8/final_closure.py status
python -B integrated-terminal-pilot/step8/final_closure.py analyze
```

These commands never simulate or load PPO. New simulation requires the explicitly
owner-started launcher and matching scientific packet approval. Exploration must
use a new output directory with author/date/source SHA, label EXPLORATORY, retain
negative findings and never replace a locked contrast or select favorable seeds.
See [the execution guide](../step8/FINAL_CLOSURE_RUNBOOK.md) for exact lifecycle,
return transfer, safe interruption, storage and reproducibility responsibilities.
