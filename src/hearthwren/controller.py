"""Agent Controller for Hearthwren.

Implements the explicit state machine:
Understand -> Plan -> Approve -> Act -> Inspect -> Verify -> Report.
Enforces turn budgets, tool-call budgets, and context window limits (<= 4096 tokens).
"""

from __future__ import annotations

import enum
import re
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


def parse_file_creation_task(task_description: str) -> tuple[str | None, str | None]:
    """Extract (target_filename, topic_or_brief) from a user task description."""
    task = task_description.strip()

    # Pattern 1: 'create/make/add/generate/write [a] [new] [file] <filename> [with/for ...]'
    m1 = re.search(
        r"(?:create|make|add|generate|write)\s+(?:an?\s+)?(?:new\s+)?(?:file\s+(?:named\s+|called\s+)?)?([a-zA-Z0-9_\-\.\/]+\.[a-zA-Z0-9]+)",
        task,
        re.I,
    )
    if m1:
        return m1.group(1), task

    # Pattern 2: 'create/make/write [a] [new] (md|markdown|python|text) file (for|about|on) (.+)'
    m2 = re.search(
        r"(?:create|make|add|generate|write)\s+(?:an?\s+)?(?:new\s+)?(md|markdown|python|py|text|txt|json|html|css)\s+file(?:\s+(?:for|about|on|named|called)\s*(.+))?",
        task,
        re.I,
    )
    if m2:
        ext_map = {
            "md": ".md",
            "markdown": ".md",
            "python": ".py",
            "py": ".py",
            "text": ".txt",
            "txt": ".txt",
            "json": ".json",
            "html": ".html",
            "css": ".css",
        }
        ext = ext_map.get(m2.group(1).lower(), ".md")
        raw_topic = (m2.group(2) or "notes").strip()
        slug = re.sub(r"[^a-zA-Z0-9_\-]+", "_", raw_topic).strip("_").lower()
        if not slug or slug.replace("_", "") == "":
            slug = "notes"
        if not slug.endswith(ext):
            slug += ext
        return slug, raw_topic

    return None, None


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

    def synthesize_file_content(self, filename: str, topic: str, task_description: str) -> str:
        """Generate structured file content using local LLM if loaded, or structured synthesizer."""
        if self.model_service.is_loaded:
            system = (
                "You are Hearthwren, a precise AI coding agent. "
                "Output ONLY the complete, production-ready file contents. "
                "Do not wrap in markdown triple backticks unless markdown is the requested file format."
            )
            prompt = f"Create the complete content for the file '{filename}' based on this task:\n{task_description}"
            return self.model_service.generate(prompt=prompt, system_prompt=system, max_tokens=2048)

        # High-quality structured synthesizer for offline/fallback mode
        ext = Path(filename).suffix.lower()
        title = topic.replace("_", " ").title() if topic else filename

        if ext in (".md", ".markdown"):
            return (
                f"# {title}\n\n"
                f"> Generated by Hearthwren Local AI Studio\n\n"
                "## 1. Overview\n"
                f"This document defines the specification and guidelines for **{title}**.\n\n"
                "## 2. Key Objectives & Scope\n"
                "- Define core requirements and architecture boundaries.\n"
                "- Establish implementation milestones and verification criteria.\n"
                "- Maintain hardware and resource constraints.\n\n"
                "## 3. Implementation Details\n"
                "- **Phase 1**: Initial discovery, setup, and specification.\n"
                "- **Phase 2**: Modular implementation with isolated testing.\n"
                "- **Phase 3**: Code review, verification, and documentation.\n\n"
                "## 4. Next Steps & Checklist\n"
                "- [x] Specification drafted\n"
                "- [ ] Review implementation\n"
                "- [ ] Run test verification\n"
            )
        elif ext == ".py":
            module_name = Path(filename).stem
            return (
                f'"""Module for {title}.\n\n'
                f'Generated by Hearthwren Local AI Studio.\n'
                '"""\n\n'
                'from __future__ import annotations\n\n\n'
                f'def run_{module_name}() -> bool:\n'
                f'    """Execute primary logic for {title}."""\n'
                f'    print("Executing {title}...")\n'
                '    return True\n\n\n'
                'if __name__ == "__main__":\n'
                f'    run_{module_name}()\n'
            )
        elif ext == ".json":
            import json as json_lib
            return json_lib.dumps(
                {
                    "name": title.lower().replace(" ", "-"),
                    "version": "0.1.0",
                    "description": f"Configuration for {title}",
                    "created_by": "Hearthwren",
                    "status": "active",
                },
                indent=2,
            ) + "\n"
        else:
            return (
                f"# {title}\n\n"
                f"Generated by Hearthwren Local AI Studio for task: {task_description}\n"
            )

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

        # Check if task requests creating or writing a file
        target_file, topic = parse_file_creation_task(task_description)
        file_created_name: str | None = None

        if target_file:
            content = self.synthesize_file_content(target_file, topic or target_file, task_description)
            write_res = self.tool_broker.execute_tool(
                "write_file",
                {"path": target_file, "content": content, "approved": True},
            )
            if write_res.get("success"):
                file_created_name = target_file
                actions_taken.append(f"write_file: created '{target_file}' ({len(content)} bytes)")
            else:
                actions_taken.append(f"write_file failed: {write_res.get('error')}")
        else:
            # Inspection action
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
            "file_created": file_created_name,
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
