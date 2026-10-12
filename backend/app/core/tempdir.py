"""Guarantee a usable temporary directory for the whole process.

Several dependencies resolve a temporary directory at *import* time:
``torch._dynamo`` builds its disk cache path, and ``huggingface_hub`` creates
lock files. Python's ``tempfile`` module probes every candidate location by
actually creating a file, so when none of them is writable it raises
``FileNotFoundError: No usable temporary directory found`` -- and because those
imports happen while the encoder is first loaded, the failure surfaces as an
opaque error on the first request rather than at startup.

Confined or sandboxed environments are exactly where this happens: the user's
own shell can write to ``%TEMP%`` while the server process started by an agent
harness cannot. A project-local directory is used in that case, so the
application does not depend on the machine's temporary directory at all.
"""

from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)

TEMP_ENVIRONMENT_VARIABLES = ("TEMP", "TMP")
DEFAULT_TEMP_DIRECTORY = Path(".runtime") / "tmp"
_probe_file_name = "writability-probe"


def _is_usable(directory: Path) -> bool:
    """Return whether a probe file can be created in the directory."""
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / _probe_file_name
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except OSError:
        return False
    return True


def ensure_usable_temp_directory(fallback: Path) -> Path | None:
    """Return the directory temp files should use, creating a fallback if needed.

    ``tempfile.tempdir`` is assigned rather than merely set through the
    environment, because ``tempfile`` caches an earlier failed probe: an
    explicit ``tempfile.tempdir`` short-circuits its search completely.
    """
    try:
        current = Path(tempfile.gettempdir())
    except OSError:
        current = None
    if current is not None and _is_usable(current):
        return current

    if not _is_usable(fallback):
        logger.error(
            "No writable temporary directory: neither the system temporary "
            "directory nor %s could be written to",
            fallback,
        )
        return None

    tempfile.tempdir = str(fallback)
    # Assigned rather than defaulted: child processes inherit these, and leaving
    # a broken value in place would hand the same failure to whatever torch or
    # huggingface_hub spawns next.
    for variable in TEMP_ENVIRONMENT_VARIABLES:
        os.environ[variable] = str(fallback)
    logger.warning(
        "System temporary directory is unusable; using %s instead",
        fallback,
    )
    return fallback
