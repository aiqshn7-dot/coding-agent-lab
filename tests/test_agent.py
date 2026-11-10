"""RepairAgent loop tests using ScriptedClient and fake tools."""

from __future__ import annotations

from pathlib import Path

from adapters.models.scripted import ScriptedClient
from core.models import TestResult
from core.repair_agent import DECISION_BUDGET, RepairAgent


class FakeTools:
    """In-memory tools that never touch Docker or host pytest."""

    def __init__(
        self,
        files: dict[str, str] | None = None,
        test_results: list[TestResult] | None = None,
    ) -> None:
        self.files = dict(files or {})
        self.test_results = list(test_results or [])
        self.changed_files: list[str] = []
        self.edit_calls: list[tuple[str, str]] = []
        self.run_tests_calls = 0

    def read_file(self, path: str) -> str:
        if path not in self.files:
            raise FileNotFoundError(path)
        return self.files[path]

    def edit_file(self, path: str, content: str) -> None:
        self.edit_calls.append((path, content))
        self.files[path] = content
        if path not in self.changed_files:
            self.changed_files.append(path)

    def run_tests(self) -> TestResult:
        self.run_tests_calls += 1
        if not self.test_results:
            raise RuntimeError("no scripted test results remaining")
        return self.test_results.pop(0)


def _agent(replies: list[str], tools: FakeTools) -> RepairAgent:
    return RepairAgent(ScriptedClient(replies), tools)


def test_successful_read_fail_edit_pass_sequence(tmp_path: Path) -> None:
    """A full valid evidence order ends as a successful repair."""
    tools = FakeTools(
        files={
            "test_calculator.py": "assert add(2, 3) == 5",
            "calculator.py": "def add(a, b): return a - b",
        },
        test_results=[
            TestResult(passed=False, output="failed", returncode=1),
            TestResult(passed=True, output="passed", returncode=0),
        ],
    )
    agent = _agent(
        [
            '{"tool":"read_file","path":"test_calculator.py","summary":"Read the test"}',
            '{"tool":"run_tests","summary":"Reproduce the failure"}',
            '{"tool":"edit_file","path":"calculator.py","content":"def add(a, b): return a + b","summary":"Fix add"}',
            '{"tool":"run_tests","summary":"Verify the repair"}',
        ],
        tools,
    )

    result = agent.repair(
        case_name="arithmetic",
        relative_files=["calculator.py", "test_calculator.py"],
        workspace=tmp_path,
    )

    assert result.passed is True
    assert result.changed_files == ["calculator.py"]
    assert result.test_result == TestResult(
        passed=True, output="passed", returncode=0
    )
    assert [event["event"] for event in result.trace] == [
        "repair_started",
        "model_response",
        "tool_result",
        "model_response",
        "tool_result",
        "model_response",
        "tool_result",
        "model_response",
        "tool_result",
        "repair_finished",
    ]
    assert tools.files["calculator.py"] == "def add(a, b): return a + b"


def test_invalid_json_calls_no_tool(tmp_path: Path) -> None:
    """Malformed replies stop the loop without invoking tools."""
    tools = FakeTools(
        files={"calculator.py": "x"},
        test_results=[TestResult(passed=True, output="ok", returncode=0)],
    )
    agent = _agent(["this is not json"], tools)

    result = agent.repair("arithmetic", ["calculator.py"], tmp_path)

    assert result.passed is False
    assert tools.run_tests_calls == 0
    assert tools.edit_calls == []
    assert result.trace[-1]["event"] == "repair_finished"
    assert "invalid reply" in result.trace[-1]["reason"]


def test_edit_rejected_before_failing_test(tmp_path: Path) -> None:
    """Edits before a failing test become policy errors and do not write."""
    tools = FakeTools(
        files={
            "test_calculator.py": "assert True",
            "calculator.py": "broken",
        },
        test_results=[
            TestResult(passed=False, output="failed", returncode=1),
        ],
    )
    agent = _agent(
        [
            '{"tool":"read_file","path":"test_calculator.py"}',
            '{"tool":"edit_file","path":"calculator.py","content":"fixed"}',
        ],
        tools,
    )

    result = agent.repair(
        "arithmetic",
        ["calculator.py", "test_calculator.py"],
        tmp_path,
    )

    assert result.passed is False
    assert tools.edit_calls == []
    assert tools.changed_files == []
    assert tools.files["calculator.py"] == "broken"
    policy_events = [
        event
        for event in result.trace
        if event.get("event") == "tool_result"
        and "policy-error" in str(event.get("observation", ""))
    ]
    assert policy_events
    assert result.trace[-1]["reason"].startswith("client error:")


def test_decision_budget_exhausted(tmp_path: Path) -> None:
    """Eight decisions without success finish as a budget failure."""
    failing = TestResult(passed=False, output="failed", returncode=1)
    tools = FakeTools(
        files={"calculator.py": "broken"},
        test_results=[failing for _ in range(DECISION_BUDGET)],
    )
    replies = ['{"tool":"run_tests"}' for _ in range(DECISION_BUDGET)]
    agent = _agent(replies, tools)

    result = agent.repair("arithmetic", ["calculator.py"], tmp_path)

    assert result.passed is False
    assert tools.run_tests_calls == DECISION_BUDGET
    assert result.trace[-1]["reason"] == "decision budget exhausted"


def test_passing_baseline_is_not_a_repair(tmp_path: Path) -> None:
    """Tests that already pass before an edit are not reported as success."""
    tools = FakeTools(
        files={"calculator.py": "ok"},
        test_results=[TestResult(passed=True, output="passed", returncode=0)],
    )
    agent = _agent(['{"tool":"run_tests","summary":"Baseline"}'], tools)

    result = agent.repair("arithmetic", ["calculator.py"], tmp_path)

    assert result.passed is False
    assert result.test_result is not None
    assert result.test_result.passed is True
    assert "no reproducible bug" in result.trace[-1]["reason"]


def test_client_error_still_returns_repair_result(tmp_path: Path) -> None:
    """A chat failure still yields a failed RepairResult."""
    tools = FakeTools(files={"calculator.py": "x"})
    agent = _agent([], tools)

    result = agent.repair("arithmetic", ["calculator.py"], tmp_path)

    assert result.passed is False
    assert result.workspace == tmp_path
    assert result.trace[0]["event"] == "repair_started"
    assert result.trace[-1]["event"] == "repair_finished"
    assert "client error" in result.trace[-1]["reason"]
    assert tools.run_tests_calls == 0
