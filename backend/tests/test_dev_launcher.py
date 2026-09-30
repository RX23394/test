"""Tests for the local development process launcher."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from scripts.dev import (
    DevelopmentLauncher,
    build_process_definitions,
    resolve_python_executable,
)


def test_build_process_definitions_contains_expected_commands() -> None:
    """Commands include configured hosts and ports for both services."""
    definitions = build_process_definitions(
        Path("project"), backend_port=8100, frontend_port=5200
    )

    assert definitions[0].name == "backend"
    assert "--port" in definitions[0].command
    assert "8100" in definitions[0].command
    assert definitions[0].readiness_url == "http://127.0.0.1:8100/health"
    assert definitions[0].environment["FRONTEND_ORIGIN"] == ("http://127.0.0.1:5200")
    assert definitions[1].name == "frontend"
    assert "5200" in definitions[1].command
    assert "--strictPort" in definitions[1].command
    assert definitions[1].environment["VITE_API_BASE_URL"] == ("http://127.0.0.1:8100")


def test_resolve_python_executable_prefers_project_venv(tmp_path: Path) -> None:
    """Backend commands use the project virtual environment when available."""
    relative_path = (
        Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    )
    virtual_environment_python = tmp_path / ".venv" / relative_path
    virtual_environment_python.parent.mkdir(parents=True)
    virtual_environment_python.touch()

    assert resolve_python_executable(tmp_path) == str(virtual_environment_python)


@patch("scripts.dev.subprocess.Popen")
def test_launcher_stops_started_processes_when_start_fails(
    popen: MagicMock,
) -> None:
    """A failed child startup terminates any process started before it."""
    first = MagicMock()
    first.poll.return_value = None
    popen.side_effect = [first, OSError("frontend unavailable")]
    definitions = build_process_definitions(Path("project"))
    readiness_probe = MagicMock()
    launcher = DevelopmentLauncher(definitions, readiness_probe)

    with pytest.raises(OSError, match="frontend unavailable"):
        launcher.start()

    first.terminate.assert_called_once()
    first.wait.assert_called_once_with(timeout=5)


@patch("scripts.dev.subprocess.Popen")
def test_wait_stops_sibling_when_a_process_exits(popen: MagicMock) -> None:
    """The remaining service is stopped after either service exits."""
    backend = MagicMock()
    frontend = MagicMock()
    backend.poll.return_value = 1
    frontend.poll.return_value = None
    popen.side_effect = [backend, frontend]
    launcher = DevelopmentLauncher(
        build_process_definitions(Path("project")), MagicMock()
    )

    launcher.start()

    assert launcher.wait(poll_interval=0) == 1
    frontend.terminate.assert_called_once()


@patch("scripts.dev.subprocess.Popen")
def test_launcher_waits_for_backend_before_starting_frontend(
    popen: MagicMock,
) -> None:
    """Frontend startup begins only after the backend readiness check."""
    backend = MagicMock()
    frontend = MagicMock()
    events: list[str] = []

    def start_process(*args: object, **kwargs: object) -> MagicMock:
        del args, kwargs
        events.append("start")
        return backend if len(events) == 1 else frontend

    popen.side_effect = start_process
    readiness_probe = MagicMock()
    readiness_probe.wait.side_effect = lambda *args: events.append("ready")
    definitions = build_process_definitions(Path("project"))
    launcher = DevelopmentLauncher(definitions, readiness_probe)

    launcher.start()

    readiness_probe.wait.assert_called_once_with(
        "http://127.0.0.1:8000/health", backend, 60
    )
    assert events == ["start", "ready", "start"]
