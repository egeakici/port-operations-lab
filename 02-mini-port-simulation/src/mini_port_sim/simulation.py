from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import simpy
from terminal_core import Terminal, TerminalState

from mini_port_sim.rng import RandomStreams
from mini_port_sim.scenario import ScenarioConfig


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
    _processes: list[simpy.events.Process] = field(
        default_factory=list,
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

    @property
    def process_count(self) -> int:
        return len(self._processes)

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
