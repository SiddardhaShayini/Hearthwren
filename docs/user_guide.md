# Hearthwren User Guide & CLI Reference

> *Local. Lean. Built right.*
> A local-first, resource-disciplined AI coding agent engineered specifically for **CPU-only laptops with 8 GB RAM**.

---

## 1. System Requirements & Hardware Target

| Requirement | Target | Notes |
|---|---|---|
| **CPU** | Intel Core i5 (or equivalent AMD/Apple Silicon) | No GPU or cloud TPU required |
| **RAM** | 8 GB total physical RAM | Strictly adheres to **<= 3.5 GB working set ceiling** |
| **OS** | Windows 10/11, Ubuntu 22.04+, macOS 12+ | Fully cross-platform |
| **Python** | Python 3.11 or 3.12 | Verified across modern runtimes |
| **Storage** | ~2.5 GB free disk space | Nanbeige4.1-3B Q4_K_M GGUF model (~2.0 GB) |

---

## 2. Installation

### From Source (Editable)
```bash
git clone https://github.com/SiddardhaShayini/Hearthwren.git
cd Hearthwren
pip install -e .
```

### From Pre-Built Wheel
```bash
pip install dist/hearthwren-0.1.0-py3-none-any.whl
```

### With Optional Local GGUF Engine
```bash
pip install hearthwren[llama]
```

---

## 3. End-to-End Workflow

```
1. hwren doctor                  -> verify hardware & dependencies
2. hwren init                    -> auto-detect project & scaffold memory
3. hwren setup-model             -> download Nanbeige4.1-3B weights
4. hwren plan "feature X"        -> ordered plan with surfaced risks
5. hwren run "feature X"         -> implementation loop with approval gates
6. hwren verify                  -> verified exit-code test execution
7. hwren diff                    -> preview unified git diff
8. hwren commit "feat: add X"    -> reviewed & confirmed git commit
9. hwren push                    -> reviewed & verified git push
```

---

## 4. CLI Commands Reference

### Environment Diagnostics
```bash
hwren doctor
hwren doctor --json
```
Runs an exhaustive health check: Python version, free RAM headroom, model file presence, local inference engine, ripgrep availability, git repository status, and `AGENT_MEMORY.md`.

### Project Initialization
```bash
hwren init
hwren init --dir /path/to/project
```
Non-destructively scans the workspace, detects primary language, manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, etc.), test frameworks, and scaffolds initial `AGENT_MEMORY.md`.

### Project & Resource Status
```bash
hwren status
hwren status --json
```
Displays active RAM headroom, current process RSS, git branch status, detected entry points, and flags stale memory references.

### Planning Mode
```bash
hwren plan "Refactor database queries to use connection pooling"
```
Reads project architecture and outputs an ordered, numbered plan with unknowns and clarifying questions. **Zero code changes are executed in planning mode.**

### Guidance Mode
```bash
hwren guide "How do I configure GitHub Actions CI for this repository?"
```
Explains architectural steps and recommended commands without modifying files.

### Task Execution
```bash
hwren run "Implement password hashing with bcrypt"
hwren run "Design user profile schema" --multi-phase
hwren run "Inspect codebase" --json
```
Enters the bounded execution state machine: `Understand -> Plan -> Approve -> Act -> Verify -> Report`. When `--multi-phase` is passed, runs 5 sequential passes (Understand, Test Spec, Implement, Review, Report). File modifications require approval and generate `.hearthwren.bak` backups.

### Session Resumption
```bash
hwren resume
```
Restores task context, repair count, and actions taken from `.hearthwren/session.json` if execution was interrupted.

### Project Memory Inspection
```bash
hwren memory
hwren memory --json
```
Inspects sections and flags stale file references in `AGENT_MEMORY.md`.

### Test Verification
```bash
hwren verify
hwren verify --json
```
Discovers project tests (`pytest`, `npm test`, `cargo test`), executes them under a timeout, captures real exit codes, and displays failure lines.

### Code Search & Symbol Indexing
```bash
hwren index
hwren index --max-files 300
hwren search "ContextCompressor"
hwren search "AgentController" --symbol
hwren search "preflight" --json
```
Fast local SQLite FTS5 full-text and symbol indexing. Displays definitions, classes, functions, file paths, line numbers, and search snippet highlights.

### Version Control
```bash
hwren diff
hwren diff --staged
hwren commit "feat: implement caching layer"
hwren push
```
Unified diff viewer with rich syntax protection. Commit and push require explicit confirmation before execution and verify results directly from `git` exit status.

### Model Weight Management
```bash
hwren setup-model
hwren setup-model --yes
```
Downloads Nanbeige4.1-3B Q4_K_M GGUF weights to `~/.hearthwren/models/` with chunked streaming SHA-256 hash verification.

---

## 5. Interactive Chat REPL Mode

Launch the multi-turn REPL by running `hwren` without subcommands:

```bash
hwren
```

### Slash Commands in REPL
- `/plan <task>`: Generate structured plan without modifying code
- `/run <task>`: Execute task with approval gates
- `/guide <query>`: Ask for architectural advice
- `/verify`: Run project tests and verify real exit codes
- `/doctor`: Run environment and hardware diagnostics
- `/status`: Show resource health and git status
- `/diff`: View workspace diff
- `/commit <msg>`: Stage and commit changes with confirmation
- `/resume`: Restore state from session.json
- `/index`: Run idle-time SQLite FTS indexing
- `/config`: View configuration settings
- `/clear`: Clear conversation history
- `exit` or `quit`: Exit the REPL

---

## 6. VS Code Extension

Hearthwren includes a lightweight, zero-dependency VS Code extension located in [`editors/vscode/`](file:///d:/Hearthwren/editors/vscode/):
- **Status Bar:** Real-time RAM and resource indicator (`$(chip) Hearthwren (8GB CPU)`).
- **Command Palette:**
  - `Hearthwren: Show Status & Resource Health`
  - `Hearthwren: Run Environment Diagnostics (Doctor)`
  - `Hearthwren: Plan a Task`
  - `Hearthwren: Verify Project Tests`
  - `Hearthwren: Ask for Guidance`
  - `Hearthwren: View Staged/Workspace Diff`
  - `Hearthwren: Resume Last Task`
