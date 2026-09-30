"""Best-effort local Git traceability without network access."""

from __future__ import annotations

import subprocess
from pathlib import Path


def get_git_metadata() -> tuple[str | None, bool | None]:
    """Return (HEAD commit, dirty state), or nulls outside a usable repository."""

    repository = Path(__file__).resolve().parents[4]
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repository,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repository,
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None, None
    return commit or None, bool(status.strip())
