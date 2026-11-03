"""Tool Broker for Hearthwren.

Validates and dispatches typed, allowlisted tool calls.
Strictly rejects malformed calls and enforces safety policies.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from pathlib import Path
from typing import Any, Callable

from hearthwren.config import HearthwrenConfig
from hearthwren.resource_supervisor import ResourceSupervisor
from hearthwren.workspace.file_ops import FileOps
from hearthwren.workspace.git_service import GitService
from hearthwren.workspace.memory import MemoryManager
from hearthwren.workspace.search import SearchService
from hearthwren.workspace.test_runner import TestRunner


class ToolExecutionError(Exception):
    """Raised when tool arguments fail validation or tool execution fails."""


class ToolBroker:
    """Dispatches validated tool calls to underlying workspace services."""

    def __init__(
        self,
        workspace_root: Path | None = None,
        config: HearthwrenConfig | None = None,
        supervisor: ResourceSupervisor | None = None,
    ):
        self.workspace_root = (workspace_root or Path.cwd()).resolve()
        self.config = config or HearthwrenConfig()
        self.supervisor = supervisor or ResourceSupervisor(self.config, self.workspace_root)

        # Services
        self.file_ops = FileOps(self.workspace_root, max_read_lines=self.config.output_line_ceiling)
        self.search_service = SearchService(self.workspace_root)
        self.git_service = GitService(self.workspace_root)
        self.test_runner = TestRunner(self.workspace_root, output_line_ceiling=self.config.output_line_ceiling)
        self.memory_manager = MemoryManager(self.workspace_root)

        self._tools: dict[str, dict[str, Any]] = self._register_tools()

    def get_tool_schemas(self) -> list[dict[str, Any]]:
        """Return JSON-schema definitions of all registered tools."""
        return [
            {"name": name, "description": meta["description"], "parameters": meta["parameters"]}
            for name, meta in self._tools.items()
        ]

    def _register_tools(self) -> dict[str, dict[str, Any]]:
        """Register allowable tools with strict JSON schemas."""
        return {
            "read_file": {
                "description": "Read lines from a file within the workspace. Large files are windowed.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative workspace file path"},
                        "start_line": {"type": "integer", "default": 1},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
                "handler": self._handle_read_file,
            },
            "write_file": {
                "description": "Write or overwrite file contents with safety backup and diff preview.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative file path to write"},
                        "content": {"type": "string", "description": "New file content"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["path", "content"],
                },
                "handler": self._handle_write_file,
            },
            "search_code": {
                "description": "Search workspace files for a text string or regex pattern.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search string"},
                        "is_regex": {"type": "boolean", "default": False},
                        "file_pattern": {"type": "string"},
                    },
                    "required": ["query"],
                },
                "handler": self._handle_search,
            },
            "list_files": {
                "description": "List files in the workspace (ignores .git, virtualenvs, etc.).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "subpath": {"type": "string", "default": ""},
                    },
                },
                "handler": self._handle_list_files,
            },
            "run_tests": {
                "description": "Run discovered or specified test suite.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Optional custom test command"},
                    },
                },
                "handler": self._handle_run_tests,
            },
            "git_status": {
                "description": "Get git branch and working directory status.",
                "parameters": {"type": "object", "properties": {}},
                "handler": self._handle_git_status,
            },
            "git_diff": {
                "description": "Show unified diff of changes in git.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "staged": {"type": "boolean", "default": False},
                    },
                },
                "handler": self._handle_git_diff,
            },
            "git_commit": {
                "description": "Commit staged changes with approval.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Commit message"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["message"],
                },
                "handler": self._handle_git_commit,
            },
            "read_memory": {
                "description": "Read AGENT_MEMORY.md summary and parsed sections.",
                "parameters": {"type": "object", "properties": {}},
                "handler": self._handle_read_memory,
            },
            "update_memory_section": {
                "description": "Update a specific section in AGENT_MEMORY.md with diff preview and approval.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "section_title": {"type": "string", "description": "Title or keyword of the section (e.g. 'Conventions', 'Key Decisions')"},
                        "content": {"type": "string", "description": "New section body text"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["section_title", "content"],
                },
                "handler": self._handle_update_memory_section,
            },
            "run_command": {
                "description": "Run an approved shell command from the safe command allowlist.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command string to execute"},
                        "approved": {"type": "boolean", "default": False},
                    },
                    "required": ["command"],
                },
                "handler": self._handle_run_command,
            },
        }

    def execute_tool(self, tool_name: str, arguments: dict[str, Any] | str) -> dict[str, Any]:
        """Validate and dispatch a tool call."""
        if tool_name not in self._tools:
            return {
                "success": False,
                "error": f"Unknown tool '{tool_name}'. Available tools: {list(self._tools.keys())}",
            }

        # Handle JSON string args if passed directly from LLM
        if isinstance(arguments, str):
            try:
                args_dict = json.loads(arguments)
            except json.JSONDecodeError as err:
                return {
                    "success": False,
                    "error": f"Malformed JSON arguments for tool '{tool_name}': {err}",
                }
        else:
            args_dict = arguments or {}

        # Validate required parameters
        schema = self._tools[tool_name]["parameters"]
        required = schema.get("required", [])
        for req in required:
            if req not in args_dict:
                return {
                    "success": False,
                    "error": f"Missing required parameter '{req}' for tool '{tool_name}'.",
                }

        handler = self._tools[tool_name]["handler"]
        try:
            return handler(args_dict)
        except Exception as ex:
            return {
                "success": False,
                "error": f"Tool '{tool_name}' execution error: {ex}",
            }

    # Handlers
    def _handle_read_file(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.file_ops.read_file(
            path=args["path"],
            start_line=args.get("start_line", 1),
            end_line=args.get("end_line"),
        )

    def _handle_write_file(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.file_ops.write_file(
            path=args["path"],
            content=args["content"],
            approved=args.get("approved", False),
        )

    def _handle_search(self, args: dict[str, Any]) -> dict[str, Any]:
        results = self.search_service.search(
            query=args["query"],
            is_regex=args.get("is_regex", False),
            file_pattern=args.get("file_pattern"),
        )
        return {"success": True, "count": len(results), "matches": results}

    def _handle_list_files(self, args: dict[str, Any]) -> dict[str, Any]:
        files = self.file_ops.list_files(subpath=args.get("subpath", ""))
        return {"success": True, "count": len(files), "files": files}

    def _handle_run_tests(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.test_runner.run_tests(command=args.get("command"))

    def _handle_git_status(self, _args: dict[str, Any]) -> dict[str, Any]:
        return {"success": True, "status": self.git_service.status()}

    def _handle_git_diff(self, args: dict[str, Any]) -> dict[str, Any]:
        diff_text = self.git_service.diff(staged=args.get("staged", False))
        return {"success": True, "diff": diff_text}

    def _handle_git_commit(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.git_service.commit(message=args["message"], approved=args.get("approved", False))

    def _handle_read_memory(self, _args: dict[str, Any]) -> dict[str, Any]:
        if not self.memory_manager.exists():
            return {"success": False, "error": "AGENT_MEMORY.md not found in workspace."}
        sections = self.memory_manager.parse_sections()
        stale = self.memory_manager.check_stale_entries()
        return {
            "success": True,
            "sections": list(sections.keys()),
            "stale_entries": stale,
            "content_preview": self.memory_manager.read_raw()[:1000],
        }

    def _handle_update_memory_section(self, args: dict[str, Any]) -> dict[str, Any]:
        return self.memory_manager.update_section(
            section_title=args["section_title"],
            new_content=args["content"],
            approved=args.get("approved", False),
        )

    def _handle_run_command(self, args: dict[str, Any]) -> dict[str, Any]:
        cmd_str = args["command"].strip()
        approved = args.get("approved", False)

        try:
            tokens = shlex.split(cmd_str)
        except ValueError as err:
            return {"success": False, "error": f"Failed to parse command string: {err}"}

        if not tokens:
            return {"success": False, "error": "Empty command."}

        base_cmd = Path(tokens[0]).stem.lower()

        # Check safe command allowlist
        is_safe = base_cmd in [c.lower() for c in self.config.safe_commands]
        if not is_safe and not approved:
            return {
                "success": False,
                "needs_approval": True,
                "command": cmd_str,
                "warning": f"Command '{base_cmd}' is not in safe command allowlist {self.config.safe_commands}. Explicit approval required.",
            }

        if not approved:
            return {
                "success": False,
                "needs_approval": True,
                "command": cmd_str,
                "message": f"Proposal to execute: `{cmd_str}`. Approval required.",
            }

        # Run with timeout under supervisor
        try:
            def exec_fn() -> subprocess.CompletedProcess[str]:
                return subprocess.run(
                    tokens,
                    capture_output=True,
                    text=True,
                    timeout=float(self.config.subprocess_timeout_seconds),
                    cwd=str(self.workspace_root),
                )

            res = self.supervisor.run_with_timeout(
                exec_fn,
                timeout_seconds=float(self.config.subprocess_timeout_seconds),
                task_name=f"run_command: {base_cmd}",
            )

            stdout_lines = res.stdout.splitlines()[: self.config.output_line_ceiling]
            stderr_lines = res.stderr.splitlines()[: self.config.output_line_ceiling]

            return {
                "success": res.returncode == 0,
                "exit_code": res.returncode,
                "stdout": "\n".join(stdout_lines),
                "stderr": "\n".join(stderr_lines),
            }
        except Exception as e:
            return {"success": False, "error": f"Command execution failed: {e}"}
