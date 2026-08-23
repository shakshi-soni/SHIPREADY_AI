"""
agent/executor.py — ShipReady Executor / Tool Router

This is where the agent stops talking and starts doing. execute_step()
maps a PlanStep's tool name to a real function in tools/ and calls it —
every actual file write, test run, and deployment happens over there, not
here. This file's only job is routing + turning raw results into a
consistent ExecutionResult, so it never summarizes or interprets success.
That's the Verifier's job, not the Executor's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from agent.planner import PlanStep
from tools import deployment, docgen, repository, testing
from tools.repository import ToolError

__all__ = ["ToolError", "ExecutionResult", "Executor"]


@dataclass
class ExecutionResult:
    step_id: int
    tool: str
    success: bool
    raw_output: str
    error: Optional[str] = None


class Executor:
    def __init__(self, target_dir: str | Path):
        self.target_dir = Path(target_dir).resolve()
        if not self.target_dir.exists():
            raise ToolError(f"Target directory does not exist: {self.target_dir}")

    # ---------- Repository tools ----------

    def read_file(self, path: str) -> str:
        return repository.read_file(self.target_dir, path)

    def write_file(self, path: str, content: str) -> dict:
        return repository.write_file(self.target_dir, path, content)

    def list_files(self, pattern: str = "**/*") -> list[str]:
        return repository.list_files(self.target_dir, pattern)

    # ---------- Test / build tools ----------

    def run_tests(self) -> dict:
        return testing.run_tests(self.target_dir)

    def run_build(self) -> dict:
        return testing.run_build(self.target_dir)

    # ---------- Doc generation tools ----------

    def generate_readme(self, content: str) -> dict:
        return docgen.generate_readme(self.target_dir, content)

    def generate_architecture_doc(self, content: str) -> dict:
        return docgen.generate_architecture_doc(self.target_dir, content)

    # ---------- Deployment tools ----------

    def deploy_cloud_run(
        self,
        service_name: str = "shipready-target",
        project_id: str = "",
        region: str = "us-central1",
    ) -> dict:
        return deployment.deploy_cloud_run(
            self.target_dir, service_name=service_name, project_id=project_id, region=region
        )

    def check_health_endpoint(self, url: str) -> dict:
        return deployment.check_health_endpoint(url)

    # ---------- Tool router ----------

    _TOOL_MAP = {
        "read_file": "read_file",
        "write_file": "write_file",
        "list_files": "list_files",
        "run_tests": "run_tests",
        "run_build": "run_build",
        "generate_readme": "generate_readme",
        "generate_architecture_doc": "generate_architecture_doc",
        "deploy_cloud_run": "deploy_cloud_run",
        "check_health_endpoint": "check_health_endpoint",
    }

    def execute_step(self, step: PlanStep) -> ExecutionResult:
        method_name = self._TOOL_MAP.get(step.tool)
        if method_name is None:
            return ExecutionResult(
                step_id=step.step_id,
                tool=step.tool,
                success=False,
                raw_output="",
                error=f"Unknown tool: {step.tool!r}",
            )

        method = getattr(self, method_name)
        try:
            output = method(**step.args)
            return ExecutionResult(
                step_id=step.step_id,
                tool=step.tool,
                success=True,
                raw_output=str(output),
            )
        except ToolError as e:
            return ExecutionResult(
                step_id=step.step_id, tool=step.tool, success=False, raw_output="", error=str(e)
            )
        except TypeError as e:
            # Wrong/missing args from the LLM's plan — treat as a tool failure,
            # not a crash, so the orchestrator can hand it to recovery.
            return ExecutionResult(
                step_id=step.step_id,
                tool=step.tool,
                success=False,
                raw_output="",
                error=f"Invalid arguments for {step.tool}: {e}",
            )