# Berth Allocation Lab

Project 03 is the berth-allocation optimization laboratory for the Port
Operations Lab roadmap.

Current status: Step 1 / problem specification.

The project scope is continuous berth allocation with two branches:

- Static Continuous BAP, where all vessel information is known before schedule
  construction.
- Dynamic Continuous BAP, where vessels appear over event-driven simulation time
  and future information is limited by a configurable visibility horizon.

The v1 primary objective is to minimize total vessel waiting time. Quay-crane,
yard, truck, and equipment scheduling policies are treated as fixed or
exogenous behavior in Project 03 v1.

Planned method families include FCFS, greedy policies, small-instance exact
optimization, rolling-horizon references, Maskable PPO, and later DQN-family
experiments. These methods are not implemented yet.

Read the frozen Step 1 specification:

- [docs/problem_specification.md](docs/problem_specification.md)

