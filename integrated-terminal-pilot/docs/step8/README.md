# Step8 results and honest closure status

**Current reviewed release: `af6b483cfaee4774` — PROVISIONAL. Project I is not finally closed.**

The completed Step7 campaign remains1960/1960, with no reruns or training.
All413 protected source paths retain their scientific content. Analysis uses
50 test traffic scenarios per family, three PPO checkpoints nested within scenario,
10,000 paired bootstrap draws and the original cargo upper-bound rule.

- [Scientific report](af6b483cfaee4774/project_i_final_scientific_report.md)
- [Executive summary](af6b483cfaee4774/project_i_executive_results_summary.md)
- [Statistical methods and results](af6b483cfaee4774/step8_statistical_analysis_protocol_and_results.md)
- [Source and evidence audit](af6b483cfaee4774/step8_source_and_evidence_audit.md)
- [Ablation and sensitivity requirements](af6b483cfaee4774/step8_ablations_and_sensitivity.md)
- [Failure modes and limitations](af6b483cfaee4774/step8_failure_modes_and_limitations.md)
- [Closure checklist and exact manual commands](af6b483cfaee4774/project_i_scientific_closure.md)
- [Machine release manifest](../../experiments/step8_analysis/af6b483cfaee4774/step8_release_manifest.json)
- [Eight PNG/SVG figure families](../../experiments/step8_analysis/af6b483cfaee4774/figures)
- [Analysis CLI and independent fixture tests](../../step8/README.md)

Release SHA256:
`c59d35c6349df7551d8e151ebaece3a999acef7c0dbed79cd7ca53c6a9710726`.
The final source-matching focused regression passed58/58 tests; its immutable
receipt is linked from the release. Earlier development reports and the initial
Windows temporary-directory permission failure remain preserved, not relabelled.

Interpretation: B2's time/cargo coordination package is favorable in both traffic
families, especially Heavy. Its primary time intervals are unadjusted previews;
the frozen protocol never specified the required Holm interval construction.
PPO versus FCFS passes the approved+1percentage-point cargo margin in Medium
but not Heavy or the equal-family overall summary. Zero-margin cargo sensitivity
fails for PPO in both families. B2 is not RL; no Yard RL or joint three-agent
optimization was evaluated.

Three closure gates remain: official full canonical archive verification;
scientifically justified resolution of the missing primary Holm construction;
and a source-consistent required13M diagnostic implementation/campaign. The
pre-execution inventory has4320 sensitivity cells (120 explicitly unsupported
Heavy0.3 occupancy cells) and160 coupling cells before any proven base overlap.
There is no working diagnostic-run command yet: the frozen model-only coupling
adapter and scoped-none mapping are absent. A manifest is not a completed
campaign or a tested runner. No false automatic-finalization promise is made.

These documents are nested deliberately: Step7's protected-source scanner reads
`docs/*.md`. Adding the Step8 names directly at that level would break its gate.
The original scanner, lock, approvals, frozen policies and historical docs are
unchanged. Numerical output and figure folders remain Git-ignored; do not force
the13GB primary archive into Git.
