from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field


ARRIVAL_STREAM = "arrival"
ETA_STREAM = "eta"
FAILURE_STREAM = "failure"
PRODUCTIVITY_STREAM = "productivity"
WORKLOAD_STREAM = "workload"

DEFAULT_STREAM_NAMES = (
    ARRIVAL_STREAM,
    ETA_STREAM,
    FAILURE_STREAM,
    PRODUCTIVITY_STREAM,
    WORKLOAD_STREAM,
)


@dataclass
class RandomStreams:
    master_seed: int
    _streams: dict[str, random.Random] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def __post_init__(self) -> None:
        if isinstance(self.master_seed, bool) or not isinstance(
            self.master_seed,
            int,
        ):
            raise ValueError("Master seed must be an integer.")

    def get(self, stream_name: str) -> random.Random:
        self._validate_stream_name(stream_name)

        if stream_name not in self._streams:
            self._streams[stream_name] = random.Random(
                self.derive_seed(stream_name)
            )

        return self._streams[stream_name]

    def derive_seed(self, stream_name: str) -> int:
        self._validate_stream_name(stream_name)
        payload = f"{self.master_seed}:{stream_name}".encode("utf-8")
        digest = hashlib.sha256(payload).digest()

        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    def manifest(self) -> dict[str, int]:
        return {
            stream_name: self.derive_seed(stream_name)
            for stream_name in DEFAULT_STREAM_NAMES
        }

    @staticmethod
    def _validate_stream_name(stream_name: str) -> None:
        if not isinstance(stream_name, str) or not stream_name.strip():
            raise ValueError("Random stream name cannot be empty.")
