# Step 06: bounded finite-event reference, dependency pending

OR-Tools is not installed in the inspected Python. Source is provided; actual
CP-SAT execution is DEPENDENCY_PENDING, not PASS. Optional dependency range
`ortools>=9.11,<10` is a compatibility proposal, not an executed/pinned environment.
An owner-created isolated environment must resolve and freeze its exact version;
no installation or broad dependency upgrade was performed.

Formulation `p04_exact_finite_event_dispatch_paths_v1` first exhaustively enumerates
the kernel's finite immediate-assignment/next-event-WAIT action tree for <=5 jobs.
Every complete path independently passes the physical verifier. Exceeding the
explicit node bound returns unsupported, never a partial optimality certificate.
The CP model selects exactly one admissible full path, with assignment binaries
and optional crane-occupied intervals/NoOverlap. The admissible path domain is
an extensional motion/separation constraint: unsafe paths cannot be selected.

Only exactly representable event ticks are accepted; non-grid times/overflow
return UNSUPPORTED_FORMULATION. There is no silent processing/travel rounding.
This certifies, at most, the finite event-dispatch subclass, not arbitrary
continuous waits, coordinated yielding or unrestricted global QCSP. Enumeration
cost is separately included in whole-call wall time; solver time limit bounds the
CP call, while node/job limits bound enumeration. Solver status/bound/gap are
reported only when available; returned paths are independently reverified.

Tests execute independent tiny enumeration and known optimum 5 minutes, missing
dependency behavior, incomplete enumeration and grid rejection. A separate real
OR-Tools integration test is skipped with its explicit dependency reason. Baseline
and RL development may proceed without an exact CP-SAT performance claim.
