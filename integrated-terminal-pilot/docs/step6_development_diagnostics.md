# Step 6 Development Diagnostics

**Label: `STEP6_DEVELOPMENT_CHARACTERIZATION`.** These are development data only (10M band, seed
10,000,000 per family) on the primary profile `itp_primary_balanced_qc8_v1`. No winner, CI or
CARGO-NI verdict is drawn: one scenario per family supports no inference, and the protocol lock is
BLOCKED. Nothing below changed any profile, rule, budget or estimator.

## 1. Plan and coverage

- **Plan:** `itp_step6_development_plan_v1`, hash
  `9babfb3068b4989d33c4b16c315f160e79c8e0ee016fe6b368586c2646d901e3`. It was written to
  `experiments/step6_development/9babfb3068b4/plan.json` **after** the K5 probe (which measures cost,
  not outcomes) and **before** any policy run.
- **Stage F1:** A1, A1n and B1 on all four families (12 runs), plus a B1 determinism repeat.
- **Stage F2:** A2, B2-T and B2 on low and medium (6 runs), plus a B2 determinism repeat. Low and
  medium were chosen because the K5 probe measured B2 there at ≤ 4.5 s per decision.
- **Stage F3 (deferred, not run):** B2/B2-T/A2 on heavy and yard-bottleneck, and seeds 10,000,001
  and 10,000,002. Status `BLOCKED_BY_COMPUTE_REVIEW` (Q6-3). These runs were planned as deferred;
  they were not omitted after seeing results.

**DEVELOPMENT_SMOKE = 20 / 20 planned items complete** (18 runs + 2 repeats).

- **Run status:** every run COMPLETED, with 0 validator rejections and all physical audits OK.
- **Shared physics:** within each scenario, every arm shares the comparison fingerprint, the
  resolved-physics fingerprint and `N_out`.
- **Repeats:** B1 (low) and B2 (low) reproduced their trace digests and their per-decision
  prediction digests.
- **Budget:** one B2/B2-T budget fingerprint (`5de88abb…`).
- **Report:** `experiments/step6_development/9babfb3068b4/reports/report_c8cbd6d85739.json`.

## 2. Outcomes (real outer kernel; D24 counts every vessel)

All runs ended COMPLETED, so there are no censored vessels; `T_end` is the scenario drain limit.

| Family | Arm | Departed | Cargo-fulfilled | Rolled over | N_out | U | R | D24 total turnaround (vessel-min) | Mean / P95 wait (min) | Decisions (WAIT) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| low | A1 | 8/8 | 8 | 0 | 2,430 | 0 | 0 | 6,827 | 94.7 / 448.4 | 8 (0) |
| low | A1n | 8/8 | 8 | 0 | 2,430 | 0 | 0 | 6,827 | 94.7 / 448.4 | 8 (0) |
| low | B1 | 8/8 | 8 | 0 | 2,430 | 0 | 0 | 6,879 | 95.6 / 452.0 | 8 (0) |
| low | A2 | 8/8 | 8 | 0 | 2,430 | 0 | 0 | 7,009 | 102.1 / 379.9 | 9 (1) |
| low | B2-T | 8/8 | 8 | 0 | 2,430 | 0 | 0 | 6,979 | 75.4 / 292.2 | 9 (1) |
| low | B2 | 8/8 | 8 | 0 | 2,430 | 0 | 0 | 6,979 | 75.4 / 292.2 | 9 (1) |
| medium | A1 | 16/16 | 16 | 0 | 4,376 | 0 | 0 | 18,166 | 415.1 / 1,520.0 | 16 (0) |
| medium | A1n | 16/16 | 16 | 0 | 4,376 | 0 | 0 | 17,156 | 350.8 / 1,449.6 | 16 (0) |
| medium | B1 | 16/16 | 16 | 0 | 4,376 | 0 | 0 | 17,973 | 406.7 / 1,204.9 | 16 (0) |
| medium | A2 | 16/16 | 16 | 0 | 4,376 | 0 | 0 | 16,136 | 293.5 / 968.0 | 17 (1) |
| medium | B2-T | 16/16 | 16 | 0 | 4,376 | 0 | 0 | 18,783 | 445.7 / 1,519.3 | 20 (4) |
| medium | B2 | 16/16 | 16 | 0 | 4,376 | 0 | 0 | 18,783 | 445.7 / 1,519.3 | 20 (4) |
| heavy | A1 | 24/24 | 24 | 0 | 6,989 | 0 | 0 | 63,630 | 1,880.3 / 4,109.4 | 24 (0) |
| heavy | A1n | 24/24 | 20 | 92 | 6,989 | 92 | 0.0132 | 62,908 | 1,802.8 / 4,475.9 | 24 (0) |
| heavy | B1 | 24/24 | 20 | 92 | 6,989 | 92 | 0.0132 | 62,710 | 1,804.4 / 4,805.1 | 24 (0) |
| bottleneck | A1 | 18/18 | 18 | 0 | 4,850 | 0 | 0 | 43,888 | 1,336.7 / 2,866.7 | 18 (0) |
| bottleneck | A1n | 18/18 | 13 | 255 | 4,850 | 255 | 0.0526 | 39,213 | 1,119.8 / 3,628.0 | 18 (0) |
| bottleneck | B1 | 18/18 | 13 | 255 | 4,850 | 255 | 0.0526 | 39,213 | 1,119.8 / 3,628.0 | 18 (0) |

Every outbound shortfall above is a D17 rollover from a departed vessel; no case is "loaded but
not departed". Crane utilization and yard-work distribution are in the run records (busiest-block
ship-move share 0.088–0.105, i.e. balanced P_y).

Observations (descriptive only, no ranking):

- **Greedy rules on heavy and bottleneck.** B1 and A1n (shortest-estimated-release greedy) give
  lower total turnaround than A1 there, but roll over 92 and 255 outbound containers where A1 rolls
  over none. This is the "turnaround gain with cargo loss" pattern the CARGO-NI rule exists to
  adjudicate.
- **B1 vs A1n.** B1's outcomes differ from A1n's on low, medium and heavy, and coincide on the
  bottleneck seed. Its integrated estimate changed some choices without changing the cargo outcome
  here.
- **B2 vs B2-T (low, medium).** They made identical choices at every decision, so their outcomes
  coincide; their trace digests differ because the decision records carry different policy ids. On medium, both waited 4 times and
  ended with a higher total turnaround than A2. The model's prediction bias (section 4) is a
  plausible contributor; it is not a conclusion.

## 3. Safeguard S4 — pivotal cargo decisions

| Run | Decisions | B2 ≠ B2-T choice | One-container pivotal | Max predicted turnaround sacrifice |
| --- | --- | --- | --- | --- |
| B2 low | 9 | 0 | 0 | — |
| B2 medium | 20 | 0 | 0 | — |

On every evaluated decision, predicted unfulfilled outbound obligations were equal across
candidates (0 in every leaf), so the cargo term never decided a choice. These development states
therefore do **not** exercise the cargo-first priority. Heavy and bottleneck states, where rollover
occurs, are deferred (F3). The pivotal-decision logic itself is unit-tested (G6-08: a
one-container advantage overrides an 8,000-minute predicted turnaround cost, with no tolerance).
Uncertainty label for all predictions: `UNCALIBRATED_SYNTHETIC_FORECAST`.

## 4. Predicted versus realized (diagnostic only; calibration unproven)

For each B2/B2-T decision, the prediction is compared with what actually happened. The predicted
visible-cohort turnaround of the chosen candidate is set against the realized turnaround of the
same cohort vessels in the real run.

| Run | Decisions | Mean error (pred − real), vessel-min | Median | Range | Predicted U (max) | Realized U |
| --- | --- | --- | --- | --- | --- | --- |
| B2 / B2-T low | 9 | −189.4 | −222.2 | −275.4 … −32.5 | 0 | 0 |
| B2 / B2-T medium | 20 | −320.5 | −118.2 | −1,629.1 … +156.3 | 0 | 0 |

The model under-predicts turnaround on average. Vessels that are still hidden at the decision
arrive later and compete for quay, cranes and yard, and the model omits future landside requests.
Both are consequences of the information contract, not defects. Predictions were never revised
using realized outcomes.

## 5. Reproduction and history

The A1 traces on the primary profile reproduce the pre-Step 6 characterization digests for all
four families, and A2 does so on low. The additive driver hook and the Step 6 modules therefore
changed no existing behaviour.

## 6. Commands

```powershell
python scripts/run_step6_coordination.py --plan
python scripts/run_step6_coordination.py --run --progress
python scripts/run_step6_coordination.py --report
```
