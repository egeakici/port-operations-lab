# Recommended owner-reviewed commit scope

Nothing was staged, committed or pushed. Preserve the existing 14 owner commits.
The only changed file outside Project 04 is the explicitly requested root
`.gitignore` repair: remove its blanket Project 04 exclusion. The project ignore
continues to exclude environments, experiments, caches, model ZIP/PT files, raw
logs and Windows pytest scratch directories. Source/config/test/script/docs paths
are now normally trackable; no force-add of an entire directory is necessary.

Project-local `.gitattributes` preserves the current LF/CRLF bytes of hash-bound
source, PowerShell, environment/config and readiness artifacts across Git checkouts.
This prevents core.autocrlf from invalidating an otherwise unchanged approval or
checkpoint. No source/config bytes were changed by this attribute declaration.

Review the current readiness report and approval payload before committing. The
root profile records the inspection HEAD plus actual content hashes: that HEAD
alone does not contain this uncommitted readiness patch. An owner commit without
changing bytes preserves the content lock; changing execution code/config/tools
requires a new candidate and approval. Historical development receipts remain
unchanged and refer to their historical source snapshots.

Suggested single readiness commit after owner review:

```powershell
git add -- .gitignore 04-rail-crane-scheduler/.gitignore 04-rail-crane-scheduler/.gitattributes 04-rail-crane-scheduler/pyproject.toml 04-rail-crane-scheduler/README.md
git add -- 04-rail-crane-scheduler/src 04-rail-crane-scheduler/tests 04-rail-crane-scheduler/scripts 04-rail-crane-scheduler/configs/research
git add -- 04-rail-crane-scheduler/docs/ARCHITECTURE.md 04-rail-crane-scheduler/docs/MANUAL_EXECUTION.md 04-rail-crane-scheduler/docs/research_readiness
git commit -m "feat(project04): prepare pinned research environment and approval-gated manual campaigns"
```

Special handling: raw install/test logs are retained locally and ignored; actual
JUnit/JSON receipts and environment metadata are trackable. Installation reports
contain local paths/platform/download provenance, intentionally included for
reproducibility. Do not include `.venv-research`, pip caches, fixture model ZIPs,
PNG outputs, primary generated cohorts, training logs or scientific result
archives from experiments. A future approved owner receipt lives with its campaign
under ignored experiments and must be archived deliberately with the approved
study, never fabricated as part of source commits. The root prompt package and
standalone orchestrator remain unrelated untracked user files.
