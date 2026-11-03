"""CLI interface for Hearthwren (hwren).

Built with Typer and Rich.
Provides fast, readable, local-first commands for resource-disciplined coding.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from hearthwren import __version__, __product_name__, __cli_name__
from hearthwren.config import (
    HearthwrenConfig,
    get_hearthwren_dir,
    init_workspace_dirs,
    load_config,
    save_config,
)
from hearthwren.controller import AgentController
from hearthwren.resource_supervisor import ResourceSupervisor
from hearthwren.workspace.detector import ProjectDetector
from hearthwren.workspace.git_service import GitService
from hearthwren.workspace.indexer import WorkspaceIndexer
from hearthwren.workspace.memory import MemoryManager

app = typer.Typer(
    name=__cli_name__,
    help=f"{__product_name__} — Local-first, resource-disciplined AI coding agent for CPU-only laptops.",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()


def version_callback(value: bool) -> None:
    if value:
        rprint(f"[bold cyan]{__product_name__}[/bold cyan] version [green]{__version__}[/green]")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    version: Optional[bool] = typer.Option(
        None, "--version", "-v", help="Show Hearthwren version and exit.", callback=version_callback, is_eager=True
    ),
) -> None:
    """Hearthwren entry point."""
    if ctx.invoked_subcommand is None:
        # Default behavior with no subcommand: interactive mode
        interactive_repl()


@app.command("init")
def cmd_init(
    project_dir: Optional[Path] = typer.Option(None, "--dir", "-d", help="Workspace root directory to initialize")
) -> None:
    """Initialize Hearthwren in the target directory."""
    root = (project_dir or Path.cwd()).resolve()
    console.print(f"[bold green]Initializing {__product_name__} in:[/bold green] {root}")

    paths = init_workspace_dirs(root)
    console.print(f"  [cyan]+[/cyan] Created configuration at: {paths['config_file'].relative_to(root)}")

    # Detect project characteristics
    detector = ProjectDetector(root)
    summary = detector.detect()
    console.print(f"  [cyan]+[/cyan] Detected Primary Language: [green]{summary.primary_language}[/green]")
    if summary.manifests:
        console.print(f"  [cyan]+[/cyan] Detected Manifests: [green]{', '.join(summary.manifests)}[/green]")
    if summary.test_framework:
        console.print(f"  [cyan]+[/cyan] Detected Test Framework: [green]{summary.test_framework}[/green]")

    # Check or scaffold AGENT_MEMORY.md
    memory_mgr = MemoryManager(root)
    if not memory_mgr.exists():
        scaffold = memory_mgr.generate_initial_memory(
            project_name=root.name,
            entry_points=summary.entry_points,
            test_command=summary.test_framework,
            primary_language=summary.primary_language,
        )
        (root / "AGENT_MEMORY.md").write_text(scaffold, encoding="utf-8")
        console.print("  [cyan]+[/cyan] Scaffolded AGENT_MEMORY.md with detected project context")
    else:
        console.print("  [cyan]+[/cyan] Existing AGENT_MEMORY.md found and preserved")

    # Check git status
    git_svc = GitService(root)
    if git_svc.is_git_repo():
        console.print("  [cyan]+[/cyan] Git repository detected")
    else:
        console.print("  [yellow]![/yellow] Not a Git repository (run `git init` to enable version control)")

    console.print(Panel(f"[bold green]{__product_name__} ready.[/bold green]\nUse `hwren plan \"<task>\"` to start planning.", expand=False))


@app.command("status")
def cmd_status(
    as_json: bool = typer.Option(False, "--json", help="Output status as structured JSON")
) -> None:
    """Show project, Git, memory, and hardware status."""
    root = Path.cwd()
    cfg = load_config(root)
    supervisor = ResourceSupervisor(cfg, root)

    # Hardware & RAM
    sys_mem = supervisor.get_system_memory()
    proc_mem = supervisor.get_process_memory()

    # Detected project characteristics
    detector = ProjectDetector(root)
    proj_summary = detector.detect()

    # Pre-flight check verdict
    ok, msg = supervisor.preflight_ram_check()

    # Git status
    git_svc = GitService(root)
    git_st = git_svc.status()

    # Memory file
    mem_mgr = MemoryManager(root)
    memory_exists = mem_mgr.exists()
    stale = mem_mgr.check_stale_entries() if memory_exists else []

    if as_json:
        payload = {
            "project": {
                "name": root.name,
                "primary_language": proj_summary.primary_language,
                "manifests": proj_summary.manifests,
                "test_framework": proj_summary.test_framework,
                "total_source_files": proj_summary.total_source_files,
                "entry_points": proj_summary.entry_points,
            },
            "resources": {
                "total_system_ram_gb": sys_mem["total_gb"],
                "available_ram_gb": sys_mem["available_gb"],
                "ram_ceiling_gb": cfg.ram_ceiling_gb,
                "headroom_gb": cfg.free_ram_headroom_gb,
                "process_rss_mb": proc_mem["rss_mb"],
                "preflight_ok": ok,
                "preflight_message": msg,
            },
            "git": git_st,
            "memory": {
                "exists": memory_exists,
                "stale_entries": stale,
            },
        }
        print(json.dumps(payload, indent=2))
        return

    proj_table = Table(title="Detected Project Structure", show_header=True)
    proj_table.add_column("Property", style="cyan")
    proj_table.add_column("Value", style="green")
    proj_table.add_row("Primary Language", proj_summary.primary_language)
    proj_table.add_row("Manifests", ", ".join(proj_summary.manifests) if proj_summary.manifests else "None")
    proj_table.add_row("Test Framework", proj_summary.test_framework or "Not detected")
    proj_table.add_row("Tracked Source Files", str(proj_summary.total_source_files))
    if proj_summary.entry_points:
        proj_table.add_row("Entry Points", ", ".join(proj_summary.entry_points[:4]))

    console.print(proj_table)

    mem_table = Table(title="Resource Health & Memory", show_header=True)
    mem_table.add_column("Metric", style="cyan")
    mem_table.add_column("Value", style="green")

    mem_table.add_row("Total System RAM", f"{sys_mem['total_gb']} GB")
    mem_table.add_row("Available Free RAM", f"{sys_mem['available_gb']} GB")
    mem_table.add_row("Hearthwren RAM Ceiling", f"{cfg.ram_ceiling_gb} GB")
    mem_table.add_row("Required Free Headroom", f"{cfg.free_ram_headroom_gb} GB")
    mem_table.add_row("Current Process RSS", f"{proc_mem['rss_mb']} MB")

    console.print(mem_table)

    if ok:
        console.print(f"[bold green][OK][/bold green] {msg}")
    else:
        console.print(f"[bold red][X][/bold red] {msg}")

    console.print("\n[bold]Version Control:[/bold]")
    if git_st["is_repo"]:
        console.print(f"  Branch: [cyan]{git_st['branch']}[/cyan] (Clean: {git_st['clean']})")
        if git_st["staged"]:
            console.print(f"  Staged: {', '.join(git_st['staged'])}")
        if git_st["unstaged"]:
            console.print(f"  Unstaged: {', '.join(git_st['unstaged'])}")
        if git_st["untracked"]:
            console.print(f"  Untracked: {', '.join(git_st['untracked'][:5])}")
    else:
        console.print("  [yellow]No git repository detected.[/yellow]")

    console.print("\n[bold]Agent Memory:[/bold]")
    if memory_exists:
        console.print("  AGENT_MEMORY.md: [green]Present[/green]")
        if stale:
            console.print(f"  [yellow]Stale reference flags:[/yellow] {len(stale)}")
            for s in stale[:3]:
                console.print(f"    - {s}")
    else:
        console.print("  AGENT_MEMORY.md: [yellow]Missing (run `hwren init`)[/yellow]")


@app.command("plan")
def cmd_plan(
    task: str = typer.Argument(..., help="Description of the task to plan"),
) -> None:
    """Generate an ordered implementation plan with risks surfaced. No code changes."""
    console.print(Panel(f"[bold cyan]Planning Task:[/bold cyan] {task}", expand=False))
    controller = AgentController()
    result = controller.plan_task(task)

    if not result["success"]:
        console.print(f"[bold red]Planning aborted:[/bold red] {result.get('error')}")
        raise typer.Exit(code=1)

    console.print(result["plan"])


@app.command("guide")
def cmd_guide(
    question: str = typer.Argument(..., help="Guidance or how-to question"),
) -> None:
    """Explain architectural steps or setup guidance without making changes."""
    console.print(Panel(f"[bold cyan]Guidance Query:[/bold cyan] {question}", expand=False))
    controller = AgentController()
    result = controller.guide_task(question)
    console.print(result["guidance"])


@app.command("verify")
def cmd_verify(
    as_json: bool = typer.Option(False, "--json", help="Output test verification results as JSON")
) -> None:
    """Discover and execute project tests, capturing real exit status."""
    controller = AgentController()
    result = controller.verify_project()

    details = result["details"]
    if as_json:
        print(json.dumps({
            "success": result["success"],
            "details": details,
        }, indent=2))
        if not result["success"]:
            raise typer.Exit(code=1)
        return

    console.print("[bold cyan]Running project verification tests...[/bold cyan]")
    if not details.get("executed"):
        console.print(f"[yellow]Tests could not be run:[/yellow] {details.get('error')}")
        raise typer.Exit(code=1)

    console.print(f"Executed: [cyan]{details['command']}[/cyan]")
    console.print(f"Exit code: {details['exit_code']}")

    if details["stdout"]:
        console.print("\n[bold]Output:[/bold]")
        console.print(details["stdout"])

    if details["passed"]:
        console.print("\n[bold green][PASS] All verification tests passed.[/bold green]")
    else:
        console.print("\n[bold red][FAIL] Verification tests failed.[/bold red]")
        if details.get("failures_detected"):
            console.print("[bold yellow]Failure evidence extracted:[/bold yellow]")
            for f in details["failures_detected"]:
                console.print(f"  * {f}")
        raise typer.Exit(code=1)


@app.command("run")
def cmd_run(
    task: str = typer.Argument(..., help="Task description to execute"),
    multi_phase: bool = typer.Option(False, "--multi-phase", "-m", help="Run 5 sequential role-scoped passes (Understand, Test Spec, Implement, Review, Report)"),
    as_json: bool = typer.Option(False, "--json", help="Output task results as structured JSON"),
) -> None:
    """Execute a task with sequential approval gates and verification."""
    if multi_phase:
        from hearthwren.subtasks import SequentialSubtaskRunner
        runner = SequentialSubtaskRunner()
        multi_res = runner.run_all_phases(task)

        if as_json:
            print(json.dumps({
                "task": multi_res.task_description,
                "success": multi_res.success,
                "phases": [
                    {
                        "phase": p.phase.value,
                        "success": p.success,
                        "summary": p.summary,
                        "actions": p.actions,
                    }
                    for p in multi_res.phase_results
                ],
                "final_report": multi_res.final_report,
            }, indent=2))
            return

        console.print(Panel(
            f"[bold green]Executing Multi-Phase Task:[/bold green] {task}\n"
            f"[dim]Running 5 sequential passes: Understand -> Test Spec -> Implement -> Review -> Report[/dim]",
            expand=False,
        ))

        for p in multi_res.phase_results:
            status_badge = "[bold green][PASS][/bold green]" if p.success else "[bold red][FAIL][/bold red]"
            console.print(f"\n{status_badge} [bold cyan]Phase {p.phase.value}:[/bold cyan]")
            for a in p.actions:
                console.print(f"  + {a}")
            console.print(f"  Summary: {p.summary[:300]}...")

        console.print(f"\n[bold green]Multi-phase execution complete.[/bold green]")
        return

    controller = AgentController()
    res = controller.execute_task(task)

    if not res.get("success"):
        if as_json:
            print(json.dumps(res, indent=2))
        else:
            console.print(f"[bold red]Task aborted:[/bold red] {res.get('error')}")
        raise typer.Exit(code=1)

    if as_json:
        payload = {
            "task": res.get("task"),
            "success": res.get("success"),
            "state": res.get("state").value if hasattr(res.get("state"), "value") else str(res.get("state")),
            "plan": res.get("plan"),
            "actions_taken": res.get("actions_taken", []),
            "recovery_proposal": res.get("recovery_proposal"),
        }
        print(json.dumps(payload, indent=2))
        return

    console.print(Panel(f"[bold green]Executing Task:[/bold green] {task}", expand=False))
    console.print("\n[bold]Plan Generated:[/bold]")
    console.print(res["plan"])
    console.print("\n[bold]Actions Taken:[/bold]")
    for a in res.get("actions_taken", []):
        console.print(f"  + {a}")
    if res.get("recovery_proposal"):
        console.print("\n[bold yellow]Recovery Guidance:[/bold yellow]")
        console.print(res["recovery_proposal"])
    console.print("\n[bold green]Task execution cycle complete.[/bold green]")


@app.command("memory")
def cmd_memory(
    as_json: bool = typer.Option(False, "--json", help="Output memory information as structured JSON"),
) -> None:
    """Inspect and check the in-repo AGENT_MEMORY.md file."""
    mem_mgr = MemoryManager()
    if not mem_mgr.exists():
        if as_json:
            print(json.dumps({"exists": False, "error": "AGENT_MEMORY.md missing"}, indent=2))
        else:
            console.print("[yellow]AGENT_MEMORY.md does not exist in workspace. Run `hwren init` to create it.[/yellow]")
        return

    sections = mem_mgr.parse_sections()
    stale = mem_mgr.check_stale_entries()

    if as_json:
        print(json.dumps({
            "exists": True,
            "path": str(mem_mgr.memory_path),
            "sections": list(sections.keys()),
            "stale_entries": stale,
        }, indent=2))
        return

    table = Table(title="AGENT_MEMORY.md Sections", show_header=True)
    table.add_column("Section", style="cyan")
    table.add_column("Snippet", style="white")

    for k, v in sections.items():
        first_line = v.strip().splitlines()[0] if v.strip() else "(Empty)"
        table.add_row(k, first_line[:80])
    console.print(table)

    if stale:
        console.print(f"\n[bold yellow]Stale References Detected ({len(stale)}):[/bold yellow]")
        for s in stale:
            console.print(f"  * {s}")
    else:
        console.print("\n[bold green][OK] All referenced files verified on disk.[/bold green]")


@app.command("resume")
def cmd_resume() -> None:
    """Resume execution from the last task state in .hearthwren/session.json."""
    controller = AgentController()
    res = controller.resume_task()

    if not res.get("success"):
        console.print(f"[yellow]{res.get('error')}[/yellow]")
        return

    table = Table(title="Resumed Session State", show_header=True)
    table.add_column("Property", style="cyan")
    table.add_column("Value", style="green")
    table.add_row("Task Description", res["task"])
    table.add_row("Last Known State", res["state"])
    table.add_row("Repair Attempts", str(res["repair_attempts"]))
    table.add_row("Actions Taken", "\n".join(f"+ {a}" for a in res["actions_taken"]) if res["actions_taken"] else "None")
    console.print(table)


@app.command("diff")
def cmd_diff(
    staged: bool = typer.Option(False, "--staged", "-s", help="Show staged changes only")
) -> None:
    """View git diff of workspace changes."""
    git_svc = GitService()
    diff_text = git_svc.diff(staged=staged)
    if not diff_text.strip():
        console.print("[cyan]No changes detected in working tree.[/cyan]")
        return
    mode = "Staged" if staged else "Unstaged"
    console.print(Panel(Text(diff_text), title=f"Git Diff ({mode})", expand=False))


@app.command("commit")
def cmd_commit(
    message: str = typer.Argument(..., help="Commit message"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm commit without interactive prompt"),
) -> None:
    """Commit staged changes with explicit user approval."""
    git_svc = GitService()
    if not git_svc.is_git_repo():
        console.print("[bold red]Not a Git repository.[/bold red]")
        raise typer.Exit(code=1)

    staged_diff = git_svc.diff(staged=True)
    if not staged_diff.strip():
        console.print("[yellow]No staged changes to commit. Stage files first.[/yellow]")
        return

    console.print(Panel(staged_diff[:2000], title="Staged Changes for Commit", expand=False))
    console.print(f"Commit message: [bold cyan]{message}[/bold cyan]")

    if not yes:
        confirm = typer.confirm("Do you approve committing these changes?")
        if not confirm:
            console.print("[yellow]Commit aborted by user.[/yellow]")
            return

    res = git_svc.commit(message=message, approved=True)
    if res["success"]:
        console.print(f"[bold green][OK] Committed successfully.[/bold green] {message}")
    else:
        console.print(f"[bold red][FAIL] Commit failed:[/bold red] {res.get('stderr')}")
        raise typer.Exit(code=1)


@app.command("push")
def cmd_push(
    remote: str = typer.Option("origin", "--remote", "-r", help="Git remote name"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b", help="Target branch name"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm push without interactive prompt"),
) -> None:
    """Push local commits to remote with explicit user confirmation."""
    git_svc = GitService()
    if not git_svc.is_git_repo():
        console.print("[bold red]Not a Git repository.[/bold red]")
        raise typer.Exit(code=1)

    cur_branch = branch or git_svc.status().get("branch") or "main"
    console.print(Panel(f"Target remote: [bold cyan]{remote}[/bold cyan]\nTarget branch: [bold cyan]{cur_branch}[/bold cyan]", title="Git Push Target", expand=False))

    if not yes:
        confirm = typer.confirm(f"Are you sure you want to push commits to {remote}/{cur_branch}?")
        if not confirm:
            console.print("[yellow]Push aborted by user.[/yellow]")
            return

    console.print("[cyan]Pushing commits...[/cyan]")
    res = git_svc.push(remote=remote, branch=cur_branch, approved=True)
    if res["success"]:
        console.print(f"[bold green][OK] Push verified successfully to {remote}/{cur_branch}.[/bold green]")
    else:
        console.print(f"[bold red][FAIL] Push failed:[/bold red] {res.get('stderr')}")
        raise typer.Exit(code=1)


@app.command("setup-model")
def cmd_setup_model(
    yes: bool = typer.Option(False, "--yes", "-y", help="Approve downloading model without prompt"),
) -> None:
    """Download and verify Nanbeige4.1-3B GGUF weights."""
    from hearthwren.model_downloader import ModelDownloader
    downloader = ModelDownloader()

    if downloader.check_installed():
        console.print(f"[bold green][OK] Model already installed at:[/bold green] {downloader.target_path}")
        return

    console.print(Panel(
        f"Model: [bold cyan]Nanbeige4.1-3B Q4_K_M GGUF[/bold cyan]\n"
        f"Destination: [cyan]{downloader.target_path}[/cyan]\n"
        f"Estimated size: ~2.0 GB\n"
        f"Network operation: requires explicit permission.",
        title="Model Download Setup",
        expand=False,
    ))

    if not yes:
        confirm = typer.confirm("Do you approve downloading the 2.0 GB model file over the network?")
        if not confirm:
            console.print("[yellow]Download aborted by user.[/yellow]")
            return

    console.print("[cyan]Starting download...[/cyan]")
    res = downloader.download_model(approved=True)
    if res["success"]:
        console.print(f"[bold green][OK] Model downloaded successfully to:[/bold green] {res['destination']}")
    else:
        console.print(f"[bold red][FAIL] Download error:[/bold red] {res.get('error')}")
        raise typer.Exit(code=1)


@app.command("index")
def cmd_index(
    max_files: int = typer.Option(200, "--max-files", "-m", help="Maximum files to index"),
    as_json: bool = typer.Option(False, "--json", help="Output indexing summary as JSON"),
) -> None:
    """Index workspace source files and symbols into SQLite FTS (.hearthwren/index.db)."""
    indexer = WorkspaceIndexer()
    indexed_count = indexer.index_workspace(max_files=max_files)
    db_size_kb = round(indexer.db_path.stat().st_size / 1024, 1) if indexer.db_path.exists() else 0.0

    if as_json:
        print(json.dumps({
            "indexed_files": indexed_count,
            "db_path": str(indexer.db_path),
            "db_size_kb": db_size_kb,
        }, indent=2))
        return

    console.print(f"[bold green][OK] Indexed {indexed_count} files in {indexer.db_path}[/bold green] ({db_size_kb} KB)")


@app.command("search")
def cmd_search(
    query: str = typer.Argument(..., help="Search query string or symbol name"),
    symbols_only: bool = typer.Option(False, "--symbol", "-s", help="Search symbol definitions only"),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum results to return"),
    as_json: bool = typer.Option(False, "--json", help="Output search results as JSON"),
) -> None:
    """Fast local full-text and symbol search using SQLite FTS index."""
    indexer = WorkspaceIndexer()
    if not indexer.db_path.exists():
        indexer.index_workspace(max_files=150)

    symbols = indexer.find_symbol(query)
    fts_results = [] if symbols_only else indexer.search_fts(query, limit=limit)

    if as_json:
        print(json.dumps({
            "query": query,
            "symbols": symbols,
            "matches": fts_results,
        }, indent=2))
        return

    if symbols:
        sym_table = Table(title=f"Symbols matching '{query}'", show_header=True)
        sym_table.add_column("Kind", style="cyan")
        sym_table.add_column("Symbol", style="bold green")
        sym_table.add_column("Location", style="white")
        for s in symbols[:limit]:
            sym_table.add_row(s["kind"], s["name"], f"{s['path']}:{s['line']}")
        console.print(sym_table)

    if not symbols_only:
        if fts_results:
            fts_table = Table(title=f"Full-Text Matches for '{query}'", show_header=True)
            fts_table.add_column("File", style="cyan")
            fts_table.add_column("Snippet", style="white")
            for m in fts_results[:limit]:
                clean_snippet = m["snippet"].replace("<b>", "[bold yellow]").replace("</b>", "[/bold yellow]")
                fts_table.add_row(m["path"], clean_snippet)
            console.print(fts_table)
        elif not symbols:
            console.print(f"[yellow]No matches found for '{query}'.[/yellow]")


@app.command("config")
def cmd_config() -> None:
    """Display current Hearthwren configuration."""
    cfg = load_config()
    table = Table(title="Hearthwren Configuration", show_header=True)
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="green")

    for k, v in vars(cfg).items():
        table.add_row(k, str(v))
    console.print(table)


@app.command("doctor")
def cmd_doctor(
    as_json: bool = typer.Option(False, "--json", help="Output doctor diagnostics as structured JSON")
) -> None:
    """Run an exhaustive diagnostic check of the local environment and hardware."""
    root = Path.cwd()
    cfg = load_config(root)
    supervisor = ResourceSupervisor(cfg, root)

    sys_mem = supervisor.get_system_memory()
    proc_mem = supervisor.get_process_memory()

    # 1. Python runtime
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_ok = sys.version_info >= (3, 11)

    # 2. RAM check
    ram_ok = sys_mem["available_gb"] >= 1.5

    # 3. Model weights
    model_path = Path(cfg.model_path)
    model_exists = model_path.exists()
    model_size_gb = round(model_path.stat().st_size / (1024**3), 2) if model_exists else 0.0

    # 4. Engine
    llama_available = False
    llama_ver = None
    try:
        import llama_cpp
        llama_available = True
        llama_ver = getattr(llama_cpp, "__version__", "installed")
    except ImportError:
        llama_available = False

    # 5. Search tools
    rg_bin = shutil.which("rg")

    # 6. Git
    git_bin = shutil.which("git")
    git_svc = GitService(root)
    is_repo = git_svc.is_git_repo()

    # 7. Project & Memory
    mem_mgr = MemoryManager(root)
    mem_exists = mem_mgr.exists()

    checks = [
        {
            "category": "Python Runtime",
            "name": f"Python {py_ver}",
            "status": "PASS" if py_ok else "FAIL",
            "details": f"Executable: {sys.executable}" if py_ok else "Requires Python >= 3.11",
        },
        {
            "category": "Memory (RAM)",
            "name": f"{sys_mem['available_gb']} GB free / {sys_mem['total_gb']} GB total",
            "status": "PASS" if sys_mem["available_gb"] >= 2.0 else ("WARN" if ram_ok else "FAIL"),
            "details": f"Ceiling: {cfg.ram_ceiling_gb} GB, Headroom: {cfg.free_ram_headroom_gb} GB",
        },
        {
            "category": "Model Weights",
            "name": model_path.name,
            "status": "PASS" if model_exists else "WARN",
            "details": f"Size: {model_size_gb} GB at {model_path}" if model_exists else "Missing (run `hwren setup-model` to download)",
        },
        {
            "category": "Inference Engine",
            "name": "llama-cpp-python",
            "status": "PASS" if llama_available else "INFO",
            "details": f"Version {llama_ver}" if llama_available else "Deterministic offline fallback active (CPU)",
        },
        {
            "category": "Code Search",
            "name": "ripgrep (rg)",
            "status": "PASS" if rg_bin else "INFO",
            "details": f"Found at {rg_bin}" if rg_bin else "Pure-Python regex search active",
        },
        {
            "category": "Version Control",
            "name": "Git CLI",
            "status": "PASS" if git_bin else "WARN",
            "details": f"Found at {git_bin} (Repo: {is_repo})" if git_bin else "Git binary not found on PATH",
        },
        {
            "category": "Project Memory",
            "name": "AGENT_MEMORY.md",
            "status": "PASS" if mem_exists else "WARN",
            "details": "Present in workspace root" if mem_exists else "Missing (run `hwren init` to scaffold)",
        },
    ]

    all_pass = all(c["status"] in ("PASS", "INFO") for c in checks)

    if as_json:
        payload = {
            "all_passed": all_pass,
            "checks": checks,
            "hardware_target": "CPU-only, 8 GB RAM, <= 3.5 GB ceiling",
        }
        print(json.dumps(payload, indent=2))
        return

    table = Table(title="Hearthwren Environment Diagnostics (Doctor)", show_header=True)
    table.add_column("Category", style="cyan")
    table.add_column("Component", style="white")
    table.add_column("Status", style="bold")
    table.add_column("Details", style="dim")

    for c in checks:
        status_style = "green" if c["status"] == "PASS" else ("yellow" if c["status"] in ("WARN", "INFO") else "red")
        table.add_row(c["category"], c["name"], f"[{status_style}][{c['status']}][/{status_style}]", c["details"])

    console.print(table)
    if all_pass:
        console.print("\n[bold green][OK] Hearthwren environment is healthy and ready for local development.[/bold green]")
    else:
        console.print("\n[bold yellow]! Some checks produced warnings. See suggestions above.[/bold yellow]")


def interactive_repl() -> None:
    """Interactive chat REPL mode with multi-turn support and slash commands."""
    console.print(
        Panel(
            f"[bold cyan]{__product_name__}[/bold cyan] v{__version__} -- [italic]Local. Lean. Built right.[/italic]\n"
            "Interactive mode. Type a task, or '/help' for commands, or 'exit' to quit.",
            expand=False,
        )
    )

    controller = AgentController()
    root = Path.cwd()

    # Pre-flight RAM check on start
    ok, msg = controller.supervisor.preflight_ram_check()
    if not ok:
        console.print(f"[bold red]Resource Warning:[/bold red] {msg}")

    # Display short onboarding context
    git_st = controller.tool_broker.git_service.status()
    if git_st["is_repo"]:
        console.print(f"Git: on [cyan]{git_st['branch']}[/cyan] (Clean: {git_st['clean']})")

    conversation_history: list[tuple[str, str]] = []

    while True:
        try:
            user_input = console.input("\n[bold green]hwren>[/bold green] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q", "/exit", "/quit"):
                console.print("[cyan]Goodbye![/cyan]")
                break
            if user_input.lower() in ("help", "/help", "?"):
                help_table = Table(title="Interactive Slash Commands", show_header=True)
                help_table.add_column("Command", style="cyan")
                help_table.add_column("Description", style="white")
                help_table.add_row("/plan <task>", "Generate structured implementation plan without code edits")
                help_table.add_row("/run <task>", "Execute task through state machine with interactive approval")
                help_table.add_row("/guide <query>", "Explain architectural steps and how-tos without changing files")
                help_table.add_row("/verify", "Run discovered project tests and verify real exit codes")
                help_table.add_row("/diff", "View git diff of workspace changes")
                help_table.add_row("/commit <msg>", "Stage and commit changes with user confirmation")
                help_table.add_row("/status", "Show resource health, project structure, and git status")
                help_table.add_row("/doctor", "Run diagnostic environment and hardware checks")
                help_table.add_row("/memory", "Inspect AGENT_MEMORY.md sections and stale entries")
                help_table.add_row("/search <query>", "Search symbols and full-text with SQLite FTS")
                help_table.add_row("/index", "Rebuild SQLite FTS index over workspace files")
                help_table.add_row("/resume", "Resume last active task from session.json")
                help_table.add_row("/config", "View current configuration settings")
                help_table.add_row("/clear", "Clear recent conversation turns")
                help_table.add_row("exit / quit", "Exit the interactive session")
                console.print(help_table)
                continue

            # Command routing
            cmd_lower = user_input.lower()
            if cmd_lower.startswith("/plan ") or cmd_lower.startswith("plan "):
                task = user_input.split(" ", 1)[1].strip()
                cmd_plan(task)
            elif cmd_lower.startswith("/run ") or cmd_lower.startswith("run "):
                task = user_input.split(" ", 1)[1].strip()
                cmd_run(task)
            elif cmd_lower.startswith("/guide ") or cmd_lower.startswith("guide "):
                q = user_input.split(" ", 1)[1].strip()
                cmd_guide(q)
            elif cmd_lower in ("/verify", "verify"):
                cmd_verify()
            elif cmd_lower in ("/status", "status"):
                cmd_status()
            elif cmd_lower in ("/doctor", "doctor"):
                cmd_doctor()
            elif cmd_lower in ("/memory", "memory"):
                cmd_memory()
            elif cmd_lower in ("/resume", "resume"):
                cmd_resume()
            elif cmd_lower in ("/diff", "diff"):
                cmd_diff()
            elif cmd_lower.startswith("/commit ") or cmd_lower.startswith("commit "):
                msg_txt = user_input.split(" ", 1)[1].strip()
                cmd_commit(msg_txt)
            elif cmd_lower in ("/config", "config"):
                cmd_config()
            elif cmd_lower in ("/index", "index"):
                cmd_index()
            elif cmd_lower.startswith("/search ") or cmd_lower.startswith("search "):
                sq = user_input.split(" ", 1)[1].strip()
                cmd_search(sq)
            elif cmd_lower in ("/clear", "clear"):
                conversation_history.clear()
                console.print("[cyan]Conversation context cleared.[/cyan]")
            else:
                # Open-ended multi-turn query
                system, prompt = controller.assemble_prompt_context(
                    user_message=user_input,
                    role_instructions="ROLE: Conversational assistant. Answer concisely, adhering to resource constraints.",
                    history=conversation_history,
                )
                response = controller.model_service.generate(prompt=prompt, system_prompt=system)
                console.print(f"\n{response}")
                conversation_history.append((user_input, response[:300]))

        except (KeyboardInterrupt, EOFError):
            console.print("\n[cyan]Session ended.[/cyan]")
            break


def main() -> None:
    """CLI entry point for setup scripts."""
    app()


if __name__ == "__main__":
    main()
