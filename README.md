<p align="center">
  <img src="assets/hearthwren-logo.svg" alt="Hearthwren Logo" width="560">
</p>

<p align="center">
  <strong>Local. Lean. Built right.</strong><br>
  <em>A local-first, resource-disciplined AI coding agent for CPU-only laptops with 8 GB RAM.</em>
</p>

<p align="center">
  <a href="#quickstart">Quickstart</a> •
  <a href="#desktop-studio--one-click-launch">Desktop Studio</a> •
  <a href="docs/user_guide.md">User Guide</a> •
  <a href="#architecture-overview">Architecture</a>
</p>

---

## What is Hearthwren?

A developer opens a terminal, points Hearthwren (`hwren`) at any repository or empty directory, describes what they want, and Hearthwren takes them to a reviewed, tested, version-controlled change — **without a GPU, without a cloud API key, and without consuming the machine**.

- **CLI command:** `hwren`
- **Package name:** `hearthwren`
- **Model:** Nanbeige4.1-3B Q4_K_M GGUF (~2.0 GB)
- **RAM ceiling:** $\le 3.5\text{ GB}$ total working set (weights + KV cache + runtime)
- **Architecture:** Strictly sequential, offline-by-default, zero background daemons

---

## Core Principles

1. **Honesty:** Distinguishes observed fact (file paths, exit codes) from inference. Never claims a test passed without verifying the exit code.
2. **Safety & Least Privilege:** Every consequential action (file write, terminal command, git commit, git push) requires explicit user confirmation.
3. **Hardware Discipline:** Pre-flight RAM verification prevents OOM crashes. Bounded context ceilings ($\le 4\,096$ tokens) and windowed file readers protect memory.
4. **Reversibility:** Every file write generates a unified diff and automatic `.hearthwren.bak` backup.
5. **Portable Memory:** In-repo [`AGENT_MEMORY.md`](./AGENT_MEMORY.md) maintains project conventions, architecture snapshots, dated decisions, and session logs.

---

## Quickstart

### 1. Installation

```bash
# Clone the repository
git clone https://github.com/Hearthwren/hearthwren.git
cd hearthwren

# Install locally
pip install -e .
```

### 2. Verify System Health

Check system memory, available headroom, git status, and memory integrity:

```bash
hwren status
```

### 3. Initialize in a Project

Scaffold `.hearthwren/` configuration and project `AGENT_MEMORY.md`:

```bash
hwren init
```

### 4. End-to-End Workflow

```bash
# 1. Plan a task without touching code
hwren plan "add email validation to signup"

# 2. Get step-by-step guidance
hwren guide "how do I structure database migrations?"

# 3. Execute with sequential approval checkpoints
hwren run "implement signup route and validation"

# 4. Verify project test suite
hwren verify

# 5. Inspect unified diffs
hwren diff

# 6. Commit staged changes (explicit approval gate)
hwren commit "feat: add email validation"

# 7. Push to remote (verified exit status)
hwren push
```

---

## Desktop Studio & One-Click Launch

Hearthwren includes an ultra-lightweight desktop application that consumes **< 25 MB RAM idle** (built with zero Electron / zero Node.js):

- **Windows:** Double-click [`Hearthwren.bat`](Hearthwren.bat) in the repository root.
- **macOS / Linux:** Run [`./hearthwren.sh`](hearthwren.sh).
- **CLI / Python:**
  ```bash
  python run_hearthwren.py
  # or
  hwren app
  ```

### Desktop Features
- **Working Repository Switcher:** Switch between any codebase or project on disk directly from the UI header badge.
- **Real-Time RAM Meter:** Visual headroom tracking with danger thresholds against the strict 3.5 GB ceiling.
- **Agent Studio:** Run single tasks or 5-phase sequential pipelines with instant action logs.
- **Diff & Git Inspector:** Inspect unified diffs before changes are finalized, commit, and push.
- **Symbol & Code Search:** Full-text and symbol search via SQLite FTS5.
- **Diagnostics Dashboard:** One-click hardware and environment health check.

---

## CLI Command Reference

| Command | Description |
|---|---|
| `hwren` | Launch interactive chat REPL mode |
| `hwren app` / `hwren ui` | Launch the ultra-lightweight Desktop Studio UI (< 25 MB RAM) |
| `hwren init` | Auto-detect workspace, scaffold config and `AGENT_MEMORY.md` |
| `hwren status` | Display resource health, RAM headroom, git status, and memory integrity |
| `hwren plan "<task>"` | Generate ordered implementation plan with surfaced risks (zero code writes) |
| `hwren run ["<task>"]` | Execute steps through state machine with interactive approval gates |
| `hwren verify` | Auto-discover and run project-native tests, reporting real exit status |
| `hwren diff` | Display unified git diff of changes |
| `hwren commit "<msg>"` | Show staged diff and commit with user confirmation |
| `hwren push` | Show destination/branch and push with confirmation and verified exit code |
| `hwren guide "<q>"` | Provide architectural guidance without executing modifications |
| `hwren setup-model` | Download and verify Nanbeige4.1-3B GGUF weights to `~/.hearthwren/models/` |
| `hwren config` | View and edit `.hearthwren/config.toml` |
| `hwren doctor` | Run exhaustive hardware, RAM headroom, and environment diagnostics |
| `hwren memory` | Parse and inspect `AGENT_MEMORY.md` sections and stale file references |
| `hwren index` | Rebuild SQLite FTS5 code search and symbol index |
| `hwren search "<query>"` | Fast local symbol and full-text search |


---

## Architecture Overview

```
Resource Supervisor  (RAM monitor, concurrency lock, timeouts, abort)
  └── CLI / REPL  (Typer + Rich)
        └── Agent Controller  (State machine: Understand -> Plan -> Approve -> Act -> Verify -> Report)
              ├── Local Model Service  (llama-cpp-python, Nanbeige4.1-3B Q4, single inference)
              └── Tool Broker  (validate & dispatch typed allowlisted ops)
                    └── Workspace Services
                          ├── FileOps       (bounded read/write/diff, atomic replace, backups)
                          ├── SearchIndex   (ripgrep + pure-Python regex fallback)
                          ├── GitService    (status/diff/log/branch/commit/push)
                          ├── TestRunner    (discover + run project-native tests)
                          ├── MemoryManager (AGENT_MEMORY.md reader/writer + stale detection)
                          ├── RecoveryEngine(evidence-based error analysis & bounded repair)
                          └── WorkspaceIndexer (SQLite FTS5 + symbol index in .hearthwren/index.db)
```

---

## Testing

Run the full Hearthwren unit and adversarial test suite:

```bash
pytest -v
```

Or self-verify using Hearthwren's own test runner:

```bash
hwren verify
```

---

## License

Licensed under the [Apache-2.0 License](./pyproject.toml).
