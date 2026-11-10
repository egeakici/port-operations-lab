# Step 08 environment

CraneSchedulingEnv implements Gymnasium 1.2.3 reset/step API using the same kernel,
typed actions, observations, finite action/step bounds and independent success
verification. Deadlock-at-reset is rejected; empty workload is a diagnostic
already-complete reset. Neither is silently admitted to primary performance.
Raw physical features are copies, not mutable state. masked_rollout is a bounded
non-PPO development harness.

Illegal actions either raise or truncate with a finite explicit failure penalty;
the mode is required input and no alternative action is substituted. Only valid
completion yields terminated=True; failures/bounds truncate and success=False.
WAIT changes the physical clock at a relevant event; no zero-time reward loop.

Gymnasium's installed check_step_determinism samples before reset and rejects
first-step truncation. The checker test supplies a reset-state legal sampling
adapter, retaining all checker assertions and original step semantics. Separate
negative tests exercise illegal actions directly. Failed checker attempts remain
in append-only receipts. Full mask/oracle agreement is tested in Step 09.
