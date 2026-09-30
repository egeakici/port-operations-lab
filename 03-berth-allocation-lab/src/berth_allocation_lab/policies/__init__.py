"""Future home for berth-allocation policies."""

from berth_allocation_lab.policies.base import (
    StaticDecisionRecord,
    StaticPolicy,
    StaticScheduleResult,
)
from berth_allocation_lab.policies.fcfs import StaticFCFS
from berth_allocation_lab.policies.greedy import StaticGreedyLookahead

__all__ = [
    "StaticDecisionRecord",
    "StaticFCFS",
    "StaticGreedyLookahead",
    "StaticPolicy",
    "StaticScheduleResult",
]
