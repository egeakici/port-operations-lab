# Step8: analysis and isolated final-closure diagnostics

Current workflow: [FINAL_CLOSURE_RUNBOOK.md](FINAL_CLOSURE_RUNBOOK.md).
The owner's Final Closure specification2026-10-25 supersedes the capability-gap
status below. `final_closure.py` implements the missing isolated13M diagnostic
runner and the fixed explicitly post-hoc statistical completion. New execution
requires the exact consolidated scientific packet acceptance. Imports, plan,
status, verify, analyze and finalize NEVER simulate. Only manual run/resume does.

Only three specifically named NEW closure launcher/handoff files extend Step8's
operational inventory. Original413 frozen entries remain content-verified;
unexpected additions/removals and scientific changes still block. The ORIGINAL
Step7 verifier is unchanged and its official receipt is reused, never rerun.
This explicit extension supersedes this older README's no-new-top-level-file
constraint and is part of the exact scientific review packet. Old release source
snapshots retain the previous code and wording.

The remainder documents the historical first Step8 analysis entrypoint, which
still reports its original provisional gates; use the current closure CLI above.

This directory is outside the frozen Step7 inventory. New documents are nested
under `docs/step8/<analysis-id>/`; the original scanner includes `docs/*.md`, so
placing them at the old top level would break its source gate. No verifier is
patched, no source exemption is introduced, and no frozen policy is edited.

The owner's 25 October Step8 specification §14 authorizes the focused independent
fixture tests and bounded analysis here. This supersedes the generic AGENTS.md
test restriction for these tests only. Deep canonical verification and any new
simulation remain owner-manual. None of these Python commands evaluates a policy,
loads a checkpoint/pickle, generates a scenario, or starts background work.

From the repository root, with the existing project Python environment:

```powershell
python -B integrated-terminal-pilot/step8/run_step8.py --verify
python -B integrated-terminal-pilot/step8/run_tests.py
python -B integrated-terminal-pilot/step8/run_step8.py --analyze --render
python -B integrated-terminal-pilot/step8/run_step8.py --status
```

Outputs are immutable/content-addressed in ignored
`experiments/step8_analysis/<analysis-id>/`. A scenario cache avoids repeatedly
parsing original summary records; the original files are still hash checked.
The diagnostic cache reads existing post-run JSON, never policy-input pickle.
Source/code/input hashes and the actual return receipt determine each revision.
`review_reference/` contains about85KiB of exact historical reconciliation targets
and repair receipts for portability. These are checked against their original
review manifest and are NEVER substituted for original campaign outcomes or a
canonical verifier PASS. The inherited scoped gate comes from the returned bundle.
Different Git metadata does not require new scientific parameter approval.
Ctrl+C leaves the source untouched; already published matching artifacts are
reused byte-for-byte. A differing artifact is refused. No failed cell is retried.

`--verify` means bounded source/summary-input/receipt intake, **not** canonical
reinflation of all13GB. Only the original official `VerifyReturn` receipt passes
that gate. `--analyze --render` can produce provisional results while it is pending.
The frozen time bootstrap is10,000 draws, seed120001. Cargo uses10,000 draws,
seed20261013 and its one-sided95% UPPER bound. All three PPO models are nested
within scenario. Secondary95% CIs do not replace the primary Holm criterion.

Two substantive issues prevent an honest complete campaign command:

- The protocol requires Holm-adjusted primary confidence intervals but never
  specifies their construction; no frozen implementation exists. The CLI exposes
  unadjusted95% primary intervals and explicitly blocks primary confirmation.
  It does not use Wilcoxon robustness p-values as a replacement decision rule.
- Required model-only coupling switches are absent; the frozen runner rejects B2 outside its primary profile, and the
  approved none/A2 equivalence is scoped. Heavy occupancy0.3 is explicitly
  unsupported. A new source-consistent prospective diagnostic implementation is
  needed; it is not a routine execution permission or parameter reapproval.
  The literal coupling requirement is4conditions x2families x20scenarios;
  the frozen source does not define the necessary operational state adapter.

The exact literal requirements/cell inventory can be inspected with:

```powershell
python -B integrated-terminal-pilot/step8/run_step8.py --diagnostic-preflight
```

This deliberately exits2, reports the actual blockers and performs no simulation.
There is no fake `--run-diagnostics` entry point and no promise of automatic full
closure once the archive audit alone passes. Do not repeat Step7 to resolve this.

After the owner executes the original archive verifier, repeat the focused tests
and read-only analysis command to produce a new source-bound revision. All old
analyses remain. Final closure stays NO until **every** required scientific gate
passes. No automatic Git operation is performed.
