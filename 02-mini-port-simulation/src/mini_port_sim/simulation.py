from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

import simpy
from terminal_core import Terminal, TerminalState

from mini_port_sim.rng import RandomStreams
from mini_port_sim.scenario import ScenarioConfig

if TYPE_CHECKING:
    from mini_port_sim.arrivals.vessel_generator import VesselArrivalPlan
    from mini_port_sim.policies.crane_policy import CraneTaskAssignment
    from mini_port_sim.policies.berth_policy import FCFSLeftmostPolicy
    from mini_port_sim.processes.task_process import TaskWorkPlan
    from mini_port_sim.processes.vessel_process import VesselLifecycleRecord


@dataclass(frozen=True)
class ActiveTaskProcess:
    crane_id: str
    task_id: str
    process: simpy.events.Process


SimulationProcessFactory = Callable[
    ["PortSimulation"],
    Generator[simpy.events.Event, Any, Any],
]


@dataclass
class PortSimulation:
    terminal: Terminal
    start_time: datetime
    seed: int | None = None
    scenario: ScenarioConfig | None = None
    env: simpy.Environment = field(init=False, repr=False)
    random_streams: RandomStreams | None = field(
        default=None,
        init=False,
        repr=False,
    )
    waiting_vessel_ids: tuple[str, ...] = field(
        default_factory=tuple,
        init=False,
    )
    completed_vessel_ids: list[str] = field(
        default_factory=list,
        init=False,
    )
    arrival_plans: tuple["VesselArrivalPlan", ...] = field(
        default_factory=tuple,
        init=False,
    )
    lifecycle_records: list["VesselLifecycleRecord"] = field(
        default_factory=list,
        init=False,
    )
    vessel_task_ids: dict[str, tuple[str, ...]] = field(
        default_factory=dict,
        init=False,
    )
    task_work_plans: dict[str, "TaskWorkPlan"] = field(
        default_factory=dict,
        init=False,
    )
    _active_task_processes_by_crane: dict[str, ActiveTaskProcess] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )
    _processes: list[simpy.events.Process] = field(
        default_factory=list,
        init=False,
        repr=False,
    )
    _berth_dispatch_event: simpy.events.Event = field(
        init=False,
        repr=False,
    )
    _crane_dispatch_event: simpy.events.Event = field(
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if not isinstance(self.terminal, Terminal):
            raise TypeError("PortSimulation requires a Terminal instance.")

        if not isinstance(self.start_time, datetime):
            raise TypeError("Simulation start time must be a datetime value.")

        if self.terminal.current_time != self.start_time:
            raise ValueError(
                "Terminal current_time must match the simulation start_time."
            )

        if (
            self.seed is not None
            and (isinstance(self.seed, bool) or not isinstance(self.seed, int))
        ):
            raise ValueError("Simulation seed must be an integer or None.")

        if self.scenario is not None:
            if not isinstance(self.scenario, ScenarioConfig):
                raise TypeError("Simulation scenario must be a ScenarioConfig.")

            if self.seed is not None and self.seed != self.scenario.seed:
                raise ValueError(
                    "Simulation seed must match the scenario seed."
                )

            self.seed = self.scenario.seed

        self.env = simpy.Environment()
        self._berth_dispatch_event = self.env.event()
        self._crane_dispatch_event = self.env.event()
        if self.seed is not None:
            self.random_streams = RandomStreams(master_seed=self.seed)

    @property
    def rng(self) -> RandomStreams:
        if self.random_streams is None:
            raise ValueError(
                "Simulation has no RandomStreams because no seed was provided."
            )

        return self.random_streams

    @classmethod
    def from_scenario(
        cls,
        *,
        terminal: Terminal,
        start_time: datetime,
        scenario: ScenarioConfig,
    ) -> "PortSimulation":
        return cls(
            terminal=terminal,
            start_time=start_time,
            seed=scenario.seed,
            scenario=scenario,
        )

    @property
    def elapsed_minutes(self) -> float:
        return float(self.env.now)

    def now_datetime(self) -> datetime:
        return self.start_time + timedelta(minutes=self.elapsed_minutes)

    def sync_terminal_time(self) -> TerminalState:
        self.terminal.advance_time_to(self.now_datetime())

        return self.terminal.snapshot()

    def add_process(
        self,
        process_factory: SimulationProcessFactory,
    ) -> simpy.events.Process:
        if not callable(process_factory):
            raise TypeError("Simulation process factory must be callable.")

        process = self.env.process(process_factory(self))
        self._processes.append(process)

        return process

    def add_vessel_arrival_process(
        self,
        plans: tuple["VesselArrivalPlan", ...] | None = None,
    ) -> simpy.events.Process:
        from mini_port_sim.arrivals import vessel_arrival_process

        return self.add_process(
            lambda simulation: vessel_arrival_process(
                simulation,
                plans,
            )
        )

    def add_berth_dispatcher(
        self,
        policy: "FCFSLeftmostPolicy | None" = None,
    ) -> simpy.events.Process:
        from mini_port_sim.processes import berth_dispatcher_process

        return self.add_process(
            lambda simulation: berth_dispatcher_process(
                simulation,
                policy,
            )
        )

    def add_crane_failure_process(self) -> simpy.events.Process:
        from mini_port_sim.disruptions import crane_failure_process

        return self.add_process(crane_failure_process)

    def start_basic_operations(self) -> None:
        self.add_berth_dispatcher()
        self.add_vessel_arrival_process()
        if (
            self.scenario is not None
            and self.scenario.disruptions.crane_failures_enabled
        ):
            self.add_crane_failure_process()

    @property
    def process_count(self) -> int:
        return len(self._processes)

    @property
    def berth_dispatch_event(self) -> simpy.events.Event:
        return self._berth_dispatch_event

    @property
    def crane_dispatch_event(self) -> simpy.events.Event:
        return self._crane_dispatch_event

    def request_berth_dispatch(self) -> None:
        if not self._berth_dispatch_event.triggered:
            self._berth_dispatch_event.succeed()

    def reset_berth_dispatch_event(self) -> None:
        if self._berth_dispatch_event.triggered:
            self._berth_dispatch_event = self.env.event()

    def request_crane_dispatch(self) -> None:
        if not self._crane_dispatch_event.triggered:
            self._crane_dispatch_event.succeed()

    def reset_crane_dispatch_event(self) -> None:
        if self._crane_dispatch_event.triggered:
            self._crane_dispatch_event = self.env.event()

    def register_active_task_process(
        self,
        crane_id: str,
        task_id: str,
        process: simpy.events.Process,
    ) -> None:
        self._active_task_processes_by_crane[crane_id] = ActiveTaskProcess(
            crane_id=crane_id,
            task_id=task_id,
            process=process,
        )

    def unregister_active_task_process(self, crane_id: str) -> None:
        self._active_task_processes_by_crane.pop(crane_id, None)

    def active_task_for_crane(
        self,
        crane_id: str,
    ) -> ActiveTaskProcess | None:
        return self._active_task_processes_by_crane.get(crane_id)

    def add_waiting_vessel(self, vessel_id: str) -> None:
        if not isinstance(vessel_id, str) or not vessel_id.strip():
            raise ValueError("Waiting vessel ID cannot be empty.")

        if vessel_id in self.waiting_vessel_ids:
            raise ValueError(f"Vessel {vessel_id} is already waiting.")

        self.waiting_vessel_ids = (*self.waiting_vessel_ids, vessel_id)

    def remove_waiting_vessel(self, vessel_id: str) -> None:
        if vessel_id not in self.waiting_vessel_ids:
            raise ValueError(f"Vessel {vessel_id} is not waiting.")

        self.waiting_vessel_ids = tuple(
            waiting_id
            for waiting_id in self.waiting_vessel_ids
            if waiting_id != vessel_id
        )

    def run(
        self,
        *,
        until_minutes: float,
    ) -> TerminalState:
        self._validate_target_minutes(until_minutes)
        self._run_inclusive_until(float(until_minutes))

        return self.sync_terminal_time()

    def run_for_hours(self, hours: float) -> TerminalState:
        if isinstance(hours, bool) or not isinstance(hours, (int, float)):
            raise TypeError("Simulation hours must be a number.")

        if hours < 0:
            raise ValueError("Simulation hours cannot be negative.")

        return self.run(until_minutes=self.env.now + (hours * 60.0))

    def run_scenario(self) -> TerminalState:
        if self.scenario is None:
            raise ValueError("Cannot run scenario without a ScenarioConfig.")

        return self.run(until_minutes=self.scenario.duration_minutes)

    def advance_to(self, elapsed_minutes: float) -> TerminalState:
        return self.run(until_minutes=elapsed_minutes)

    def _validate_target_minutes(self, elapsed_minutes: float) -> None:
        if (
            isinstance(elapsed_minutes, bool)
            or not isinstance(elapsed_minutes, (int, float))
        ):
            raise TypeError("Simulation target time must be a number.")

        if elapsed_minutes < 0:
            raise ValueError("Simulation target time cannot be negative.")

        if elapsed_minutes < self.env.now:
            raise ValueError("Simulation time cannot move backwards.")

    def _run_inclusive_until(self, until_minutes: float) -> None:
        # SimPy's numeric run(until=...) stops before events at that exact time.
        while self.env.peek() <= until_minutes:
            self.env.step()

        if self.env.now < until_minutes:
            self.env.run(until=until_minutes)
