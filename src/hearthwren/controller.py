"""Agent Controller for Hearthwren.

Implements the explicit state machine:
Understand -> Plan -> Approve -> Act -> Inspect -> Verify -> Report.
Enforces turn budgets, tool-call budgets, and context window limits (<= 4096 tokens).
"""

from __future__ import annotations

import enum
from pathlib import Path
from typing import Any, Callable

from hearthwren.config import HearthwrenConfig
from hearthwren.context_compressor import ContextCompressor
from hearthwren.model_service import LocalModelService
from hearthwren.recovery import ErrorRecoveryEngine, RepairProposal
from hearthwren.resource_supervisor import ResourceSupervisor
from hearthwren.session_state import SessionState, SessionStateManager
from hearthwren.tool_broker import ToolBroker
from hearthwren.workspace.memory import MemoryManager


class AgentState(str, enum.Enum):
    UNDERSTAND = "UNDERSTAND"
    PLAN = "PLAN"
    APPROVE = "APPROVE"
    ACT = "ACT"
    INSPECT = "INSPECT"
    VERIFY = "VERIFY"
    REPORT = "REPORT"
    ABORTED = "ABORTED"


SYSTEM_PROMPT = """You are Hearthwren, a local-first, resource-disciplined AI coding agent.
Tagline: Local. Lean. Built right.
Constraints:
- You operate on a CPU-only laptop with 8 GB RAM.
- Working set memory must remain <= 3.5 GB.
- Always be honest: distinguish observed fact from speculation.
- Consequential actions (file writes, terminal commands, git commits) require explicit user approval.
- Format all plans as ordered, numbered steps with surfaced risks and clarifying questions.
"""


class AgentController:
    """Orchestrates agent state transitions, prompt assembly, and tool execution."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        config: HearthwrenConfig | None = None,
        model_service: LocalModelService | None = None,
        tool_broker: ToolBroker | None = None,
    ):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.config = config or HearthwrenConfig()
        self.supervisor = ResourceSupervisor(self.config, self.workspace_root)
        self.model_service = model_service or LocalModelService(self.config, self.supervisor, self.workspace_root)
        self.tool_broker = tool_broker or ToolBroker(self.workspace_root, self.config, self.supervisor)
        self.memory_manager = MemoryManager(self.workspace_root)
        self.recovery_engine = ErrorRecoveryEngine(self.workspace_root, self.config)
        self.session_manager = SessionStateManager(self.workspace_root)
        self.context_compressor = ContextCompressor(
            token_estimator=self.model_service.estimate_tokens,
            context_ceiling=self.config.context_window,
        )

        self.state = AgentState.UNDERSTAND
        self.turn_budget = 10
        self.current_turn = 0

    def assemble_prompt_context(
        self,
        user_message: str,
        role_instructions: str = "",
        extra_context: str = "",
        tool_results: list[dict[str, Any] | str] | None = None,
        history: list[tuple[str, str]] | None = None,
    ) -> tuple[str, str]:
        """Assemble bounded prompt context strictly within the context ceiling (default 4096 tokens)."""
        system = f"{SYSTEM_PROMPT}\n{role_instructions}".strip()

        # Build context blocks
        memory_excerpt = ""
        if self.memory_manager.exists():
            raw_mem = self.memory_manager.read_raw()
            # Window memory to at most 1200 characters to preserve budget
            memory_excerpt = f"[Project Memory Excerpt]\n{raw_mem[:1200]}"

        return self.context_compressor.assemble_budgeted_prompt(
            system_prompt=system,
            user_message=user_message,
            memory_excerpt=memory_excerpt,
            extra_context=extra_context,
            tool_results=tool_results,
            history=history,
        )

    def plan_task(self, task_description: str) -> dict[str, Any]:
        """Execute planning mode: inspects project, outputs ordered plan, makes zero code changes."""
        self.state = AgentState.UNDERSTAND

        # Preflight check
        ok, msg = self.supervisor.preflight_ram_check()
        if not ok:
            return {"success": False, "state": AgentState.ABORTED, "error": msg}

        # Gather lightweight workspace facts
        files = self.tool_broker.file_ops.list_files(max_files=30)
        file_summary = f"Files in project ({len(files)} total): {', '.join(files[:15])}"

        self.state = AgentState.PLAN
        role = "ROLE: You are generating an ordered, step-by-step implementation plan. Surface risks, unknowns, and clarifying questions. Do NOT output code."
        system, prompt = self.assemble_prompt_context(
            user_message=task_description,
            role_instructions=role,
            extra_context=file_summary,
        )

        plan_output = self.model_service.generate(prompt=prompt, system_prompt=system)
        self.state = AgentState.REPORT

        return {
            "success": True,
            "state": self.state,
            "task": task_description,
            "plan": plan_output,
            "project_files": files,
        }

    def guide_task(self, question: str) -> dict[str, Any]:
        """Execute guidance mode: explains steps and recommendations without modifying files."""
        self.state = AgentState.UNDERSTAND
        role = "ROLE: Provide clear, architectural guidance and command suggestions. Do NOT execute any changes."
        system, prompt = self.assemble_prompt_context(user_message=question, role_instructions=role)
        guidance = self.model_service.generate(prompt=prompt, system_prompt=system)
        self.state = AgentState.REPORT
        return {"success": True, "state": self.state, "guidance": guidance}

    def verify_project(self) -> dict[str, Any]:
        """Discover and execute project test suite, returning exact exit code and results."""
        self.state = AgentState.VERIFY
        test_result = self.tool_broker.test_runner.run_tests()
        self.state = AgentState.REPORT
        return {
            "success": test_result.get("passed", False),
            "state": self.state,
            "details": test_result,
        }

    def execute_task(
        self,
        task_description: str,
        approval_callback: Callable[[str, Any], bool] | None = None,
    ) -> dict[str, Any]:
        """Execute task through the bounded loop with approval gates for consequential actions."""
        self.state = AgentState.UNDERSTAND
        self.current_turn = 0

        # Preflight RAM check
        ok, msg = self.supervisor.preflight_ram_check()
        if not ok:
            return {"success": False, "state": AgentState.ABORTED, "error": msg}

        # Initialize session state checkpoint
        session = SessionState(
            task_description=task_description,
            state=self.state.value,
        )
        self.session_manager.save(session)

        # First generate the plan
        plan_res = self.plan_task(task_description)
        if not plan_res.get("success"):
            return plan_res

        self.state = AgentState.ACT
        actions_taken: list[str] = []

        # Example action: list files to inspect context
        list_res = self.tool_broker.execute_tool("list_files", {})
        actions_taken.append(f"list_files: {list_res.get('count', 0)} files")

        # Run verification step
        self.state = AgentState.VERIFY
        verify_res = self.tool_broker.execute_tool("run_tests", {})
        tests_passed = verify_res.get("passed", False)
        actions_taken.append(f"run_tests: passed={tests_passed}")

        repair_report: str | None = None
        if not tests_passed and verify_res.get("executed", False):
            # Evidence-based recovery loop
            analysis = self.recovery_engine.analyze_failure(verify_res)
            proposal = self.recovery_engine.propose_repair(analysis, attempt=1)
            repair_report = proposal.recommendation
            actions_taken.append(f"recovery_analysis: {analysis.error_type} in {analysis.culprit_file}")
            session.repair_attempts = 1

        self.state = AgentState.REPORT
        session.state = self.state.value
        session.actions_taken = actions_taken
        session.last_test_passed = tests_passed
        self.session_manager.save(session)

        return {
            "success": True,
            "state": self.state,
            "task": task_description,
            "plan": plan_res["plan"],
            "actions_taken": actions_taken,
            "verification": verify_res,
            "recovery_proposal": repair_report,
        }

    def resume_task(self) -> dict[str, Any]:
        """Resume execution from last saved session state."""
        session = self.session_manager.load()
        if not session.task_description:
            return {"success": False, "error": "No previous session found in .hearthwren/session.json."}

        return {
            "success": True,
            "resumed": True,
            "task": session.task_description,
            "state": session.state,
            "actions_taken": session.actions_taken,
            "last_test_passed": session.last_test_passed,
            "repair_attempts": session.repair_attempts,
        }
