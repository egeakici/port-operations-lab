"""Entity-keyed exogenous random streams (scientific experiment protocol 6.3, FROZEN).

Each draw comes from its own ``random.Random`` seeded by

    int.from_bytes(sha256(f"itp_v1|{family}|{split}|{scenario_seed}|{entity_kind}|{entity_id}|{attribute}")
                   .digest()[:8], "big")

This is the Project 02 ``RandomStreams.derive_seed`` hashing pattern
(first 8 bytes of SHA-256, big-endian) with a Project I namespace and entity
keys. Python's process-randomized ``hash()`` is never used. Because every key
names one entity attribute, changing how one attribute family is drawn (or how
many draws it consumes) cannot shift any other family's values.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

STREAM_NAMESPACE = "itp_v1"


@dataclass(frozen=True)
class KeyedStreams:
    family: str
    split: str
    scenario_seed: int
    namespace: str = STREAM_NAMESPACE

    def __post_init__(self) -> None:
        for name in ("family", "split", "namespace"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value or "|" in value:
                raise ValueError(f"Stream {name} must be a non-empty string without '|'.")
        if isinstance(self.scenario_seed, bool) or not isinstance(self.scenario_seed, int):
            raise ValueError("Scenario seed must be an integer.")

    def key(self, entity_kind: str, entity_id: str, attribute: str) -> str:
        for part in (entity_kind, entity_id, attribute):
            if not isinstance(part, str) or not part or "|" in part:
                raise ValueError("Stream key parts must be non-empty strings without '|'.")
        return (f"{self.namespace}|{self.family}|{self.split}|{self.scenario_seed}|"
                f"{entity_kind}|{entity_id}|{attribute}")

    def seed_for(self, entity_kind: str, entity_id: str, attribute: str) -> int:
        digest = hashlib.sha256(self.key(entity_kind, entity_id, attribute).encode("utf-8")).digest()
        return int.from_bytes(digest[:8], byteorder="big", signed=False)

    def rng(self, entity_kind: str, entity_id: str, attribute: str) -> random.Random:
        return random.Random(self.seed_for(entity_kind, entity_id, attribute))
