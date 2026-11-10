# Step 05 deterministic baselines

Four versioned arms: ordered_sweep_v1 chooses lowest bay coordinate;
nearest_feasible_v1 chooses shortest safe distance; longest_work_v1 prioritizes
largest original workload then distance; balanced_finish_v1 minimizes assigned
original crane workload then estimated completion. Final ties are physical rank,
bay coordinate and task ID. These are dispatch heuristics, not exact solvers.

All use identical kernel legality, WAIT and independent completion validation.
No policy changes safety/rates or drops difficult jobs. Stuck cases remain
DEADLOCK with null makespan. Only kernel changes time. Decision bound follows
finite task assignments and three phase ends per task, not an infinite retry loop.

Metrics reconstruct actual executed segment durations clipped at stop, original
completed moves and independently verified makespan. Productive utilization is
process crane-minutes / (2 * elapsed minutes); setup/travel are separate, idle is
the remainder. Empty utilization and all failed makespans are null. Selection
latency and whole-episode wall seconds have distinct boundaries. Test fixture
two-job result: makespan 5, process 5 crane-min, travel 2 crane-min / 4 m,
setup 2 crane-min and idle 1 crane-min; not a scientific performance estimate.
