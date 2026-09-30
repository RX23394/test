"""Start the Network RAG backend and frontend development servers."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from subprocess import Popen
from typing import Protocol
from urllib.error import URLError
from urllib.request import urlopen


@dataclass(frozen=True)
class ProcessDefinition:
    """Describe one development process and the directory it runs in."""

    name: str
    command: tuple[str, ...]
    cwd: Path
    environment: dict[str, str]
    readiness_url: str | None = None


class ReadinessProbe(Protocol):
    """Define how a launched service reports that it is ready."""

    def wait(
        self,
        url: str,
        process: Popen[bytes],
        timeout_seconds: float,
    ) -> None:
        """Wait for a service endpoint or raise when it cannot become ready."""


class HttpReadinessProbe:
    """Poll an HTTP endpoint until the launched service is ready."""

    def wait(
        self,
        url: str,
        process: Popen[bytes],
        timeout_seconds: float,
    ) -> None:
        """Wait until an HTTP endpoint responds successfully."""
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            return_code = process.poll()
            if return_code is not None:
                raise RuntimeError(
                    f"Service exited with code {return_code} before becoming ready"
                )
            try:
                with urlopen(url, timeout=1) as response:  # noqa: S310
                    if response.status < 500:
                        return
            except (OSError, URLError):
                time.sleep(0.2)
        raise TimeoutError(f"Service did not become ready within {timeout_seconds}s")


def build_process_definitions(
    project_root: Path,
    *,
    backend_host: str = "127.0.0.1",
    backend_port: int = 8000,
    frontend_host: str = "127.0.0.1",
    frontend_port: int = 5173,
    reload: bool = True,
) -> tuple[ProcessDefinition, ProcessDefinition]:
    """Build the backend and frontend commands for a local development run."""
    npm = "npm.cmd" if os.name == "nt" else "npm"
    backend_python = resolve_python_executable(project_root)
    backend_client_host = _client_host(backend_host)
    frontend_client_host = _client_host(frontend_host)
    backend_url = f"http://{backend_client_host}:{backend_port}"
    frontend_origin = f"http://{frontend_client_host}:{frontend_port}"
    base_environment = dict(os.environ)
    backend_environment = {
        **base_environment,
        "FRONTEND_ORIGIN": frontend_origin,
    }
    frontend_environment = {
        **base_environment,
        "VITE_API_BASE_URL": backend_url,
    }
    backend_command = [
        backend_python,
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        backend_host,
        "--port",
        str(backend_port),
    ]
    if reload:
        backend_command.append("--reload")
    frontend_command = (
        npm,
        "run",
        "dev",
        "--",
        "--host",
        frontend_host,
        "--port",
        str(frontend_port),
        "--strictPort",
    )
    return (
        ProcessDefinition(
            "backend",
            tuple(backend_command),
            project_root / "backend",
            backend_environment,
            f"{backend_url}/health",
        ),
        ProcessDefinition(
            "frontend",
            frontend_command,
            project_root / "frontend",
            frontend_environment,
        ),
    )


def resolve_python_executable(project_root: Path) -> str:
    """Prefer the project's virtual-environment Python when it exists."""
    relative_path = (
        Path("Scripts/python.exe") if os.name == "nt" else Path("bin/python")
    )
    virtual_environment_python = project_root / ".venv" / relative_path
    if virtual_environment_python.is_file():
        return str(virtual_environment_python)
    return sys.executable


def _client_host(bind_host: str) -> str:
    """Return a browser-accessible host for a server bind address."""
    if bind_host in {"0.0.0.0", "::"}:
        return "127.0.0.1"
    return bind_host


class DevelopmentLauncher:
    """Own and supervise the backend and frontend child processes."""

    def __init__(
        self,
        definitions: Sequence[ProcessDefinition],
        readiness_probe: ReadinessProbe | None = None,
        startup_timeout_seconds: float = 60,
    ) -> None:
        """Create a launcher for the supplied process definitions."""
        self._definitions = tuple(definitions)
        self._readiness_probe = readiness_probe or HttpReadinessProbe()
        self._startup_timeout_seconds = startup_timeout_seconds
        self._processes: list[tuple[ProcessDefinition, Popen[bytes]]] = []

    def start(self) -> None:
        """Start all configured processes, cleaning up if one cannot start."""
        try:
            for definition in self._definitions:
                process = subprocess.Popen(
                    definition.command,
                    cwd=definition.cwd,
                    env=definition.environment,
                )
                self._processes.append((definition, process))
                print(f"Started {definition.name}: {' '.join(definition.command)}")
                if definition.readiness_url is not None:
                    self._readiness_probe.wait(
                        definition.readiness_url,
                        process,
                        self._startup_timeout_seconds,
                    )
                    print(f"{definition.name} is ready")
        except (OSError, RuntimeError, TimeoutError):
            self.stop()
            raise

    def wait(self, poll_interval: float = 0.25) -> int:
        """Wait until a child exits and return its exit code."""
        try:
            while self._processes:
                for definition, process in self._processes:
                    return_code = process.poll()
                    if return_code is not None:
                        print(f"{definition.name} exited with code {return_code}")
                        return return_code
                time.sleep(poll_interval)
        except KeyboardInterrupt:
            return 130
        finally:
            self.stop()
        return 0

    def stop(self) -> None:
        """Terminate all running children and wait for them to exit."""
        for _, process in reversed(self._processes):
            if process.poll() is None:
                process.terminate()
        for _, process in self._processes:
            if process.poll() is None:
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        self._processes.clear()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line options for the development launcher."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-host", default="127.0.0.1")
    parser.add_argument("--backend-port", type=int, default=8000)
    parser.add_argument("--frontend-host", default="127.0.0.1")
    parser.add_argument("--frontend-port", type=int, default=5173)
    parser.add_argument("--no-reload", action="store_true")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Start both development servers and return their exit status."""
    args = _parse_args(argv)
    root = Path(__file__).resolve().parent.parent
    definitions = build_process_definitions(
        root,
        backend_host=args.backend_host,
        backend_port=args.backend_port,
        frontend_host=args.frontend_host,
        frontend_port=args.frontend_port,
        reload=not args.no_reload,
    )
    if shutil.which(definitions[1].command[0]) is None:
        raise SystemExit(
            "npm was not found. Install Node.js before starting the frontend."
        )
    launcher = DevelopmentLauncher(definitions)
    try:
        launcher.start()
    except (OSError, RuntimeError, TimeoutError) as error:
        raise SystemExit(f"Failed to start development servers: {error}") from error
    return launcher.wait()


if __name__ == "__main__":
    raise SystemExit(main())
