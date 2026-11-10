"""Select an allowed eval project, copy it, and run one repair."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from core.models import RepairResult
from core.ports import ChatClient, RepairToolsPort
from core.repair_agent import RepairAgent

CreateWorkspace = Callable[[Path], Path]
MakeTools = Callable[[Path], RepairToolsPort]
MakeClient = Callable[[str], ChatClient]


class RepairService:
    """Gatekeeper that accepts only supplied evals/ projects."""

    def __init__(
        self,
        *,
        make_client: MakeClient,
        create_workspace: CreateWorkspace,
        make_tools: MakeTools,
        evals_root: Path,
    ) -> None:
        self._make_client = make_client
        self._create_workspace = create_workspace
        self._make_tools = make_tools
        self._evals_root = evals_root.resolve()

    def repair(self, selected_path: str | Path) -> RepairResult:
        """Copy one allowed project and return its ``RepairResult``."""
        case_dir = self._resolve_case(selected_path)
        workspace = self._create_workspace(case_dir)
        tools = self._make_tools(workspace)
        agent = RepairAgent(self._make_client(case_dir.name), tools)
        return agent.repair(
            case_name=case_dir.name,
            relative_files=list_relative_files(workspace),
            workspace=workspace,
        )

    def _resolve_case(self, selected_path: str | Path) -> Path:
        """Accept only a relative path to a known project under evals/."""
        raw = Path(selected_path)
        if raw.is_absolute():
            raise ValueError("absolute paths are not allowed")

        candidate = (Path.cwd() / raw).resolve()
        try:
            candidate.relative_to(self._evals_root)
        except ValueError as exc:
            raise ValueError(
                f"path outside evals/: {selected_path}"
            ) from exc

        if candidate.parent != self._evals_root or not candidate.is_dir():
            raise ValueError(f"unknown project: {selected_path}")
        return candidate


def list_relative_files(workspace: Path | str) -> list[str]:
    """Return sorted relative file paths inside a workspace copy."""
    root = Path(workspace)
    files: list[str] = []
    for path in sorted(root.rglob("*")):
        if path.is_file():
            files.append(path.relative_to(root).as_posix())
    return files
