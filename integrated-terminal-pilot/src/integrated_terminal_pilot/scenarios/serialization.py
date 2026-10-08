"""Scenario file serialization (unified data contract section 13).

Files are ``{scenario_id}.scenario.json``: UTF-8, ``indent=2``, ``sort_keys=True``,
no NaN, trailing newline. The byte layout is therefore a pure function of the
document, which makes regeneration byte-identical.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

SCENARIO_SUFFIX = ".scenario.json"


def scenario_bytes(doc: dict[str, Any]) -> bytes:
    text = json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
    return (text + "\n").encode("utf-8")


def scenario_filename(doc: dict[str, Any]) -> str:
    return f"{doc['identity']['scenario_id']}{SCENARIO_SUFFIX}"


def write_scenario(doc: dict[str, Any], directory: str | Path) -> Path:
    """Write exclusively; an existing file is never overwritten."""
    path = Path(directory) / scenario_filename(doc)
    with path.open("xb") as stream:
        stream.write(scenario_bytes(doc))
    return path


def load_scenario(path: str | Path) -> dict[str, Any]:
    data = Path(path).read_bytes()
    doc = json.loads(data.decode("utf-8"), parse_constant=_reject_constant)
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: scenario document must be a JSON object.")
    return doc


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_constant(name: str) -> Any:
    raise ValueError(f"Non-finite JSON constant {name} is not allowed in scenarios.")
