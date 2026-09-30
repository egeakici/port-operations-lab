"""Project-owned JSON/JSONL artifacts for static scientific runs."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from berth_allocation_lab.data import BAPScenarioInstance
from berth_allocation_lab.tracking.records import (
    RunManifest,
    RunSummary,
    ScientificRunResult,
    VesselResult,
)


class ScientificRunRecorder:
    """Write one self-contained run directory under a caller-chosen root."""

    def __init__(self, output_dir: str | Path, run_id: str) -> None:
        self.run_dir = Path(output_dir) / run_id

    def start(self, manifest: RunManifest, scenario: BAPScenarioInstance) -> None:
        self.run_dir.mkdir(parents=True, exist_ok=False)
        _write_json(self.run_dir / "manifest.json", asdict(manifest))
        _write_json(self.run_dir / "scenario.json", scenario.to_dict())

    def finish(self, result: ScientificRunResult) -> None:
        _write_jsonl(
            self.run_dir / "placements.jsonl",
            (
                {
                    "run_id": result.manifest.run_id,
                    "scenario_id": result.scenario.scenario_id,
                    **asdict(placement),
                }
                for placement in result.placements
            ),
        )
        _write_jsonl(
            self.run_dir / "vessels.jsonl",
            (asdict(vessel) for vessel in result.vessels),
        )
        _write_jsonl(
            self.run_dir / "decisions.jsonl",
            (
                {
                    "run_id": result.manifest.run_id,
                    "scenario_id": result.scenario.scenario_id,
                    **asdict(decision),
                }
                for decision in result.decisions
            ),
        )
        _write_json(
            self.run_dir / "violations.json",
            [
                {
                    "code": violation.code.value,
                    "vessel_ids": violation.vessel_ids,
                    "message": violation.message,
                }
                for violation in result.violations
            ],
        )
        _write_json(self.run_dir / "run_summary.json", asdict(result.summary))
        _write_json(self.run_dir / "manifest.json", asdict(result.manifest))

    def record_failure(
        self,
        manifest: RunManifest,
        summary: RunSummary,
        vessels: tuple[VesselResult, ...],
    ) -> None:
        """Preserve a failed manifest when normal artifact serialization fails."""

        _write_jsonl(
            self.run_dir / "vessels.jsonl",
            (asdict(vessel) for vessel in vessels),
        )
        _write_json(self.run_dir / "run_summary.json", asdict(summary))
        _write_json(self.run_dir / "manifest.json", asdict(manifest))


def _write_json(path: Path, data: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


def _write_jsonl(path: Path, rows: object) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
