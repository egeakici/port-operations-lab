from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from terminal_core import Terminal, TerminalState


@dataclass
class PortSimulation:
    terminal: Terminal
    start_time: datetime
    seed: int | None = None
    _elapsed_minutes: float = field(default=0.0, init=False, repr=False)

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

    @property
    def elapsed_minutes(self) -> float:
        return self._elapsed_minutes

    def now_datetime(self) -> datetime:
        return self.start_time + timedelta(minutes=self._elapsed_minutes)

    def advance_to(self, elapsed_minutes: float) -> TerminalState:
        if elapsed_minutes < self._elapsed_minutes:
            raise ValueError("Simulation time cannot move backwards.")

        self._elapsed_minutes = elapsed_minutes
        self.terminal.advance_time_to(self.now_datetime())

        return self.terminal.snapshot()
