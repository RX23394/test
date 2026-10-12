"""Tests for the process-wide temporary directory guarantee."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

from app.core import tempdir as tempdir_module
from app.core.tempdir import ensure_usable_temp_directory


def _make_probe_fail() -> None:
    """Make every candidate temporary directory unusable."""

    def fail() -> str:
        raise FileNotFoundError(2, "No usable temporary directory found", [])

    tempfile._get_default_tempdir = fail  # type: ignore[assignment]


def test_usable_system_temp_directory_is_kept(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """A working temporary directory is left exactly as the system set it."""
    working = tmp_path / "system-temp"
    working.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(working))

    result = ensure_usable_temp_directory(tmp_path / "fallback")

    assert result == working
    assert tempfile.gettempdir() == str(working)
    assert not (tmp_path / "fallback").exists()


def test_broken_temp_directory_falls_back_and_updates_the_process(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """An unwritable temporary directory is replaced, not tolerated.

    Python's ``tempfile`` probes each candidate by creating a file and raises
    when none works. ``torch._dynamo`` and ``huggingface_hub`` resolve a
    temporary path at import time, so that failure used to abort loading the
    encoder on the first request with an opaque error.
    """
    fallback = tmp_path / "project-temp"
    monkeypatch.setattr(tempfile, "tempdir", None)
    _make_probe_fail()

    result = ensure_usable_temp_directory(fallback)

    assert result == fallback
    assert fallback.is_dir()
    # tempfile.tempdir short-circuits the probe, so the cached failure is gone.
    assert Path(tempfile.gettempdir()) == fallback
    for variable in tempdir_module.TEMP_ENVIRONMENT_VARIABLES:
        assert os.environ[variable] == str(fallback)


def test_no_writable_location_reports_failure_without_raising(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When nothing is writable the process is told, not crashed here."""
    monkeypatch.setattr(tempfile, "tempdir", None)
    _make_probe_fail()
    monkeypatch.setattr(
        tempdir_module,
        "_is_usable",
        lambda directory: False,
    )

    assert ensure_usable_temp_directory(tmp_path / "fallback") is None
