"""Copy an eval case under the home cache and run pytest in Docker."""

from __future__ import annotations

import shutil
import subprocess
import uuid
from pathlib import Path

from core.models import TestResult

IMAGE_NAME = "coding-agent-lab-runner"
WORKSPACE_ROOT = Path.home() / ".cache" / "coding-agent-lab"
CONTAINER_WORKSPACE = "/workspace"


def create_workspace(source: Path | str) -> Path:
    """Copy ``source`` into a disposable folder under the user's home cache.

    Workspaces must live under the home directory so Docker Desktop, Colima,
    Rancher Desktop, and Podman can all mount them into the container.
    """
    source_path = Path(source).resolve()
    if not source_path.is_dir():
        raise FileNotFoundError(f"evaluation project not found: {source_path}")

    WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
    workspace = WORKSPACE_ROOT / f"ws-{uuid.uuid4().hex}"
    shutil.copytree(source_path, workspace)
    return workspace


def run_tests(workspace: Path | str) -> TestResult:
    """Run sandboxed pytest against a workspace copy via Docker.

    Mounts only the workspace, read-only, with networking disabled. Never runs
    evaluation-project code or pytest on the host.
    """
    workspace_path = Path(workspace).resolve()
    if not workspace_path.is_dir():
        raise FileNotFoundError(f"workspace not found: {workspace_path}")

    command = [
        "docker",
        "run",
        "--rm",
        "--network",
        "none",
        "-e",
        "PYTHONDONTWRITEBYTECODE=1",
        "-v",
        f"{workspace_path}:{CONTAINER_WORKSPACE}:ro",
        "-w",
        CONTAINER_WORKSPACE,
        IMAGE_NAME,
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    output = "".join(
        part for part in (completed.stdout, completed.stderr) if part
    )
    return TestResult(
        passed=completed.returncode == 0,
        output=output,
        returncode=completed.returncode,
    )
