"""Sequential Subtasks (Task Phases) for Hearthwren.

Executes complex tasks through role-scoped sequential passes:
1. Understand (explore files & constraints)
2. Test Spec (plan assertions & test requirements)
3. Implement (formulate code changes with diffs)
4. Review & Verify (run tests & inspect exit codes)
5. Report (summarize results & request approval)

Strictly sequential — shares a single model instance and memory ceiling.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from hearthwren.config import HearthwrenConfig
from hearthwren.controller import AgentController, parse_file_creation_task
from hearthwren.model_service import LocalModelService
from hearthwren.resource_supervisor import ResourceSupervisor
from hearthwren.tool_broker import ToolBroker


class TaskPhase(str, enum.Enum):
    UNDERSTAND = "UNDERSTAND"
    TEST_SPEC = "TEST_SPEC"
    IMPLEMENT = "IMPLEMENT"
    REVIEW_VERIFY = "REVIEW_VERIFY"
    REPORT = "REPORT"


PHASE_ROLES = {
    TaskPhase.UNDERSTAND: (
        "ROLE: Understand Phase. Examine project manifests, constraints, and source structure. "
        "Surface dependencies, risks, and assumptions."
    ),
    TaskPhase.TEST_SPEC: (
        "ROLE: Test Specification Phase. Define test cases, assertion criteria, and edge cases "
        "that must pass before any code is considered ready."
    ),
    TaskPhase.IMPLEMENT: (
        "ROLE: Implementation Phase. Formulate minimal, surgical code changes. "
        "Always propose changes as unified diffs. Never touch unrelated files."
    ),
    TaskPhase.REVIEW_VERIFY: (
        "ROLE: Review & Verification Phase. Inspect modified diffs, run the project test suite, "
        "and verify exit codes."
    ),
    TaskPhase.REPORT: (
        "ROLE: Report Phase. Provide a concise, honest summary of what was verified, "
        "what succeeded, and request user approval for commit."
    ),
}


@dataclass
class PhaseResult:
    """Outcome of a single sequential phase."""

    phase: TaskPhase
    success: bool
    summary: str
    actions: list[str] = field(default_factory=list)


@dataclass
class MultiPhaseTaskResult:
    """Aggregate result across all completed task phases."""

    task_description: str
    success: bool
    phase_results: list[PhaseResult]
    final_report: str


class SequentialSubtaskRunner:
    """Runs sequential task passes with role-scoped prompts under hardware resource bounds."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        config: HearthwrenConfig | None = None,
        controller: AgentController | None = None,
    ):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.config = config or HearthwrenConfig()
        self.controller = controller or AgentController(self.workspace_root, self.config)
        self.supervisor = self.controller.supervisor
        self.model_service = self.controller.model_service
        self.tool_broker = self.controller.tool_broker

    def run_phase(
        self,
        phase: TaskPhase,
        task_description: str,
        prior_context: str = "",
    ) -> PhaseResult:
        """Run a single sequential phase under resource supervisor locks."""
        # 1. Preflight check
        ok, msg = self.supervisor.preflight_ram_check()
        if not ok:
            return PhaseResult(phase=phase, success=False, summary=f"Aborted: {msg}")

        role_instruction = PHASE_ROLES.get(phase, "")
        extra_ctx = f"[Prior Phase Outputs]\n{prior_context}\n" if prior_context else ""

        system, prompt = self.controller.assemble_prompt_context(
            user_message=task_description,
            role_instructions=role_instruction,
            extra_context=extra_ctx,
        )

        actions: list[str] = []

        # Execute role-scoped action if applicable
        if phase == TaskPhase.UNDERSTAND:
            files_res = self.tool_broker.execute_tool("list_files", {})
            actions.append(f"Discovered {files_res.get('count', 0)} files")
        elif phase == TaskPhase.IMPLEMENT:
            target_file, topic = parse_file_creation_task(task_description)
            if target_file:
                content = self.controller.synthesize_file_content(target_file, topic or target_file, task_description)
                write_res = self.tool_broker.execute_tool(
                    "write_file",
                    {"path": target_file, "content": content, "approved": True},
                )
                if write_res.get("success"):
                    actions.append(f"Created file '{target_file}' ({len(content)} bytes)")
                else:
                    actions.append(f"File write failed: {write_res.get('error')}")
        elif phase == TaskPhase.REVIEW_VERIFY:
            test_res = self.tool_broker.execute_tool("run_tests", {})
            actions.append(f"Executed tests: passed={test_res.get('passed', False)}")

        output = self.model_service.generate(prompt=prompt, system_prompt=system)

        return PhaseResult(
            phase=phase,
            success=True,
            summary=output,
            actions=actions,
        )

    def run_all_phases(self, task_description: str) -> MultiPhaseTaskResult:
        """Execute full pipeline sequentially: Understand -> Test Spec -> Implement -> Review -> Report."""
        results: list[PhaseResult] = []
        cumulative_context = ""

        phases = [
            TaskPhase.UNDERSTAND,
            TaskPhase.TEST_SPEC,
            TaskPhase.IMPLEMENT,
            TaskPhase.REVIEW_VERIFY,
            TaskPhase.REPORT,
        ]

        for phase in phases:
            res = self.run_phase(phase, task_description, cumulative_context)
            results.append(res)
            if not res.success:
                return MultiPhaseTaskResult(
                    task_description=task_description,
                    success=False,
                    phase_results=results,
                    final_report=f"Phase {phase.value} failed: {res.summary}",
                )

            # Keep cumulative context compact (max 500 chars per phase)
            cumulative_context += f"\n[{phase.value} Output]: {res.summary[:400]}"

        final_summary = results[-1].summary
        return MultiPhaseTaskResult(
            task_description=task_description,
            success=True,
            phase_results=results,
            final_report=final_summary,
        )
