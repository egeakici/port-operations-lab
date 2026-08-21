from __future__ import annotations

from dataclasses import dataclass

from terminal_core import ContainerGroup, Terminal, YardBlockStatus


@dataclass(frozen=True)
class YardDecision:
    group_id: str
    block_id: str


class FirstFitYardPolicy:
    def choose(
        self,
        terminal: Terminal,
        group: ContainerGroup,
    ) -> YardDecision | None:
        for block_id in terminal.yard_block_ids:
            block = terminal.get_yard_block(block_id)

            if block.status != YardBlockStatus.OPEN:
                continue

            if not block.supports_requirements(
                group.required_yard_capabilities
            ):
                continue

            if block.available_teu < group.total_teu:
                continue

            return YardDecision(
                group_id=group.group_id,
                block_id=block_id,
            )

        return None
