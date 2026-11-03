"""CLI interface for Hearthwren (hwren).

Built with Typer and Rich.
Provides fast, readable, local-first commands for resource-disciplined coding.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

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
from hearthwren.workspace.git_service import GitService
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

    # Check or scaffold AGENT_MEMORY.md
    memory_mgr = MemoryManager(root)
    if not memory_mgr.exists():
        scaffold = memory_mgr.generate_initial_memory(root.name)
        (root / "AGENT_MEMORY.md").write_text(scaffold, encoding="utf-8")
        console.print("  [cyan]+[/cyan] Scaffolded AGENT_MEMORY.md")
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
def cmd_status() -> None:
    """Show project, Git, memory, and hardware status."""
    root = Path.cwd()
    cfg = load_config(root)
    supervisor = ResourceSupervisor(cfg, root)

    # Hardware & RAM
    sys_mem = supervisor.get_system_memory()
    proc_mem = supervisor.get_process_memory()

    mem_table = Table(title="Resource Health & Memory", show_header=True)
    mem_table.add_column("Metric", style="cyan")
    mem_table.add_column("Value", style="green")

    mem_table.add_row("Total System RAM", f"{sys_mem['total_gb']} GB")
    mem_table.add_row("Available Free RAM", f"{sys_mem['available_gb']} GB")
    mem_table.add_row("Hearthwren RAM Ceiling", f"{cfg.ram_ceiling_gb} GB")
    mem_table.add_row("Required Free Headroom", f"{cfg.free_ram_headroom_gb} GB")
    mem_table.add_row("Current Process RSS", f"{proc_mem['rss_mb']} MB")

    console.print(mem_table)

    # Pre-flight check verdict
    ok, msg = supervisor.preflight_ram_check()
    if ok:
        console.print(f"[bold green][OK][/bold green] {msg}")
    else:
        console.print(f"[bold red][X][/bold red] {msg}")

    # Git status
    git_svc = GitService(root)
    git_st = git_svc.status()
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

    # Memory file
    mem_mgr = MemoryManager(root)
    console.print("\n[bold]Agent Memory:[/bold]")
    if mem_mgr.exists():
        stale = mem_mgr.check_stale_entries()
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
def cmd_verify() -> None:
    """Discover and execute project tests, capturing real exit status."""
    console.print("[bold cyan]Running project verification tests...[/bold cyan]")
    controller = AgentController()
    result = controller.verify_project()

    details = result["details"]
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
) -> None:
    """Execute a task with sequential approval gates and verification."""
    console.print(Panel(f"[bold green]Executing Task:[/bold green] {task}", expand=False))
    controller = AgentController()
    res = controller.execute_task(task)

    if not res.get("success"):
        console.print(f"[bold red]Task aborted:[/bold red] {res.get('error')}")
        raise typer.Exit(code=1)

    console.print("\n[bold]Plan Generated:[/bold]")
    console.print(res["plan"])
    console.print("\n[bold]Actions Taken:[/bold]")
    for a in res.get("actions_taken", []):
        console.print(f"  + {a}")
    console.print("\n[bold green]Task execution cycle complete.[/bold green]")


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
    console.print(Panel(diff_text, title=f"Git Diff ({mode})", expand=False))


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


def interactive_repl() -> None:
    """Interactive chat REPL mode."""
    console.print(
        Panel(
            f"[bold cyan]{__product_name__}[/bold cyan] v{__version__} -- [italic]Local. Lean. Built right.[/italic]\n"
            "Interactive mode. Type your task, or 'help', or 'exit' to quit.",
            expand=False,
        )
    )

    controller = AgentController()
    # Check RAM
    ok, msg = controller.supervisor.preflight_ram_check()
    if not ok:
        console.print(f"[bold red]Warning:[/bold red] {msg}")

    while True:
        try:
            user_input = console.input("\n[bold green]hwren>[/bold green] ").strip()
            if not user_input:
                continue
            if user_input.lower() in ("exit", "quit", "q"):
                console.print("[cyan]Goodbye![/cyan]")
                break
            if user_input.lower() == "help":
                console.print("Commands available: plan <task>, guide <question>, verify, status, config, exit")
                continue

            if user_input.lower().startswith("plan "):
                cmd_plan(user_input[5:].strip())
            elif user_input.lower().startswith("guide "):
                cmd_guide(user_input[6:].strip())
            elif user_input.lower() == "verify":
                cmd_verify()
            elif user_input.lower() == "status":
                cmd_status()
            elif user_input.lower() == "config":
                cmd_config()
            else:
                # Default to plan & inspect
                cmd_plan(user_input)

        except (KeyboardInterrupt, EOFError):
            console.print("\n[cyan]Session ended.[/cyan]")
            break


def main() -> None:
    """CLI entry point for setup scripts."""
    app()


if __name__ == "__main__":
    main()
