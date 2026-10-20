# Foreground progress display repair - 2026-10-20

Owner evidence: remote PowerShell output shows the initial mandatory Project I
regression at1/543 selected tests, repeatedly appending the same progress frame
approximately four times per second. This is a demonstrated display defect,
not evidence that the selected test or scientific episode is being re-executed.

The previous parent forced child tqdm position1 over logged stdout/stderr pipes,
while keeping a separate parent stage bar. The regression monitor additionally
called refresh every250ms. The child did not inherit the real console width and
printed complete long node IDs. Cursor positioning and line wrapping made the
intended redraw appear as hundreds of separate bars in the reported console.

Repair:

- One active tqdm bar at position0, using carriage-return redraws and ASCII.
- Parent stage progress becomes one heading/completion line per stage; no nested
  parent cursor positioning competes with the logged child's bar.
- Pass the actual console width to the child, leaving a column to prevent wrap.
- Let normal updates obey tqdm throttling; slow-test elapsed-time refresh is
  every2s. Full test names remain in immutable node events and logs, rather than
  in an overlong terminal postfix. Test selection and raw result evidence remain.

No policy, physics, parameter, seed, scientific inventory, gate, checkpoint or
scoring code changes. Test definitions are added for a redirected stream's
carriage-return frames, no cursor-up escapes, bounded width and phase completion.
The coding agent does not run them, regressions or a campaign. Python syntax and
diff checks are permitted; actual PowerShell rendering is verified by the owner.

## Updating the remote computer safely

Do not pull while the old process is running. Use Ctrl+C and wait for the command
to return. Retain its complete original bundle and logs. The supplied output was
pre-lock regression work, with no Step7 scientific episode shown. If execution
has since reached protocol locking/validation/test, preserve it and obtain a
scientific deviation review before restarting a campaign on changed source.

This repair changes protected implementation/test fingerprints. Existing sessions
must continue to reject source drift; no lock/approval/receipt is hand-edited and
no old regression is relabelled valid on new source. For the demonstrated pre-lock
case, after the owner commits/pushes the repair, pull and start a separate bundle:

```powershell
git pull origin main
powershell -NoProfile -ExecutionPolicy Bypass -File .\integrated-terminal-pilot\scripts\Start-Step7Remote.ps1 -RunName campaign_progress_v2 -SkipInstall
```

`-SkipInstall` reuses the successfully installed environment; it does not bypass
any scientific verification. The new source requires fresh full mandatory
regressions and a genuine new lock before evaluation. The original campaign_v1
folder remains unchanged, including any interrupted/failed regression evidence.
The new run name is an operational separation, not seed or outcome selection.
Copy the entire campaign_progress_v2 folder back under the same relative name
and use `-RunName campaign_progress_v2` for status and return verification.
