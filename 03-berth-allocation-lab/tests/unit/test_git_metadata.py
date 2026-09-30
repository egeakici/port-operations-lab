from __future__ import annotations

from berth_allocation_lab.tracking import git_metadata


def test_git_metadata_is_nullable_when_git_is_unavailable(monkeypatch) -> None:
    def unavailable(*args, **kwargs):
        raise FileNotFoundError("git missing")

    monkeypatch.setattr(git_metadata.subprocess, "run", unavailable)
    assert git_metadata.get_git_metadata() == (None, None)
