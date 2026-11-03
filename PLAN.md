# Hearthwren — Product & Engineering Plan

> **Status:** Planning phase only. No application code has been written.
> **Product name:** **Hearthwren**. CLI command: `hwren`. Package: `hearthwren`. Exact-name checks on PyPI, npm, GitHub and web search found no conflicts; formal trademark and domain clearance is still required before release.
> **Tagline:** *Local. Lean. Built right.*
> **Primary target:** CPU-only laptops, 8 GB RAM, Intel i5 (or equivalent). All design decisions flow from this constraint.
> **Model policy:** Nanbeige4.1-3B is the sole LLM. Qwen3-4B and Terminus-4B are listed as conditional extras and are **excluded from MVP**; include only if a Phase 0 measurement proves a capability cannot be delivered by Nanbeige4.1-3B plus deterministic tools.

---

## 1. Product Vision

Hearthwren is a local-first, resource-disciplined AI coding agent. A developer opens a terminal, points Hearthwren at any repository (or an empty directory), describes what they want, and Hearthwren takes them to a reviewed, tested, version-controlled change — without a GPU, without a cloud API key, and without consuming the machine.

Hearthwren is honest. When it does not know, it says so. When it needs information to proceed safely, it asks. When a check fails, it reports the real outcome rather than guessing.

Hearthwren is safe. Every consequential action — file overwrite, terminal command, commit, push — requires explicit user approval. The model proposes; the user decides.

---

## 2. Key Decisions & Constraints

| Area | Decision |
|---|---|
| **Model** | Nanbeige4.1-3B only (CPU GGUF, 4-bit quantization). No cloud fallback, no second loaded model, no embedding model. |
| **Runtime** | `llama.cpp` (CPU build) as primary candidate. Exact revision, quantization level, and chat-template fidelity are Phase 0 verification gates, not assumptions. |
| **Context window** | Default **4 096 tokens**. Optional **8 192** if memory and quality gates pass on the target device. Never adopt the published max as the default. |
| **Concurrency** | One model instance, one inference at a time. Sequential "role-scoped subtasks" share the same model and memory budget — not parallel copies. |
| **Retrieval** | Filesystem-aware ripgrep search, Git, SQLite FTS, optional lightweight symbol indexing. No vector DB, no embedding model in MVP. |
| **Interface** | CLI-first (smallest runtime footprint, works in any terminal). Editor integration is a post-MVP consideration gated on resource and safety results. |
| **Network** | Offline by default after initial model download. Package installs, GitHub push, and any outbound call are explicit, user-approved actions. |
| **Language** | Python 3.11+ (broad toolchain compatibility, strong llama.cpp bindings, easy packaging). |
| **Packaging** | Single `pip install hearthwren` (or `uv`-based) install. Model downloaded separately with hash verification on first run. |

### Conditional extras (excluded from MVP)

| Model | Include only when | Why not by default |
|---|---|---|
| Qwen3-4B | Phase 0 proves Nanbeige4.1-3B cannot reliably follow structured tool-call schema, AND the extra ~3-4 GB fits within the measured memory budget | Doubles RAM pressure; violates the single-model principle |
| Terminus-4B | Phase 0 proves a specific capability (e.g. code-fill, FIM completion) measurably improves output quality on target hardware | Same reason; add only as an opt-in with full memory gate |

---

## 3. Resource-Safety Design

> "Never OOM" is not a promise — other processes share the 8 GB. The promise is **never to be the cause of unbounded memory growth**.

### Memory budget (preliminary — refine during Phase 0 measurement)

| Component | Estimated ceiling |
|---|---|
| Nanbeige4.1-3B weights (Q4_K_M) | ~2.0 GB |
| KV cache at 4 096-token context | ~256 MB (32 layers x 4 KV heads x 128 dim x 2 x 4 096 x FP16) |
| Python runtime + Hearthwren process | ~300 MB |
| Workspace index (SQLite) | ~50 MB bounded |
| OS + browser + editor headroom | ~2 GB reserved |
| **Total Hearthwren ceiling target** | **<= 3.5 GB working set** |

### Enforcement rules

1. **Pre-flight check:** Before loading the model, measure free RAM. If `free_ram < HEARTHWREN_budget + 1.5 GB` headroom, abort with a clear message and actionable suggestions (close applications, reduce context).
2. **Bounded context:** Every prompt is assembled with a token estimator before sending. If the estimate exceeds the context ceiling, trim low-priority history, summarize tool output, or split the task. Never silently overflow.
3. **Sequential only:** No concurrent inference, build, and subtask execution. Each step completes (or is cancelled) before the next begins. Idle-time indexing is the sole exception: it may run only when the model is not inferring, must yield immediately when inference is requested, and is bounded in memory.
4. **Bounded output:** Terminal output captured with a configurable line/byte ceiling. Large files read in windowed chunks, not fully into RAM.
5. **Timeouts and cancellation:** Every subprocess and inference call has a wall-clock timeout. Ctrl+C cleanly kills child processes and returns to the agent loop.
6. **Low-memory recovery:** On `MemoryError` or OS-level signals, Hearthwren stops, flushes any partial state to the local operational cache, and surfaces a recovery prompt — it does not silently retry with a larger footprint.
7. **No background daemon:** Hearthwren runs only when the user invokes it. No always-on service consuming RAM between sessions.

---

## 4. Architecture

```
+-------------------------------------------------------------+
|                        CLI / REPL                           |
|  (task input, planning mode, confirmations, progress, help) |
+------------------------+------------------------------------+
                         |
+------------------------v------------------------------------+
|                    Agent Controller                         |
|  State machine: Understand -> Plan -> [Approve] -> Act ->   |
|  Inspect -> Verify -> Report                                |
|  Enforces turn budget, tool-call budget, timeout, memory.   |
+------+-------------------------------------------+----------+
       |                                           |
+------v------------------+             +----------v----------+
|  Local Model Service    |             |     Tool Broker     |
|  llama.cpp process      |             |  Validates &        |
|  Nanbeige4.1-3B Q4      |             |  dispatches typed,  |
|  One request/time       |             |  allowlisted ops    |
|  Health monitoring      |             |  (file, search,     |
+-------------------------+             |   git, terminal,    |
                                        |   memory)           |
                                        +----------+----------+
                                                   |
              +------------------------------------v---------------------+
              |                    Workspace Services                   |
              |  FileOps | SearchIndex | GitService | TestRunner | Mem  |
              +------------------------------------+---------------------+
                                                   |
              +------------------------------------v---------------------+
              |                  Resource Supervisor                    |
              |  RAM monitor | CPU governor | Concurrency lock | Timers |
              +----------------------------------------------------------+
```

### Component responsibilities

| Component | Responsibility |
|---|---|
| **CLI / REPL** | Project selection, task input, planning/chat mode, confirmation prompts, progress display, cancellation, readable summaries. |
| **Agent Controller** | Explicit state machine. Reads model output, extracts tool calls, enforces budgets, routes approvals, assembles next prompt from memory + context. |
| **Local Model Service** | Manages a single `llama.cpp` child process. Handles loading, health checks, warm restart, context reset, and clean shutdown. |
| **Tool Broker** | Receives structured tool calls from the controller. Validates name, schema, arguments, and policy. Returns typed results. Rejects unknown or malformed calls — never interprets them as shell commands. |
| **Workspace Services** | Safe, atomic file reads/writes/diffs. Ignore-aware search (ripgrep). SQLite FTS index. Git operations (status, diff, branch, log, stage, commit, push). Test runner discovery and execution. Project language/manifest detection. |
| **Memory System** | Reads/writes `AGENT_MEMORY.md`. Detects stale entries. Manages local operational SQLite cache (bounded, gitignored). |
| **Resource Supervisor** | Polls RAM and CPU. Enforces concurrency lock. Applies timeouts. Triggers graceful degradation or safe abort. Logs diagnostics (no source code or secrets in logs). |

---

## 5. User-Facing Capabilities

### 5.1 Interactive Chat Mode

- `hwren` (no subcommand) — starts an interactive REPL session for open-ended conversation, questions, and ad-hoc tasks.
- The agent reads `AGENT_MEMORY.md` and checks Git status on session start.
- Supports multi-turn conversation within the bounded context. Older turns are summarized as the context window fills.
- The user can switch into planning, guidance, or task mode mid-session.

### 5.2 Project Onboarding

- Work with an existing repository or an empty directory.
- Auto-detect language, manifests (`package.json`, `pyproject.toml`, `Cargo.toml`, etc.), test framework, and Git status.
- Create `.hearthwren/` directory and add it to `.gitignore` if not already present.
- Summarize detected structure in `AGENT_MEMORY.md` on first run (user-approved).
- No files are modified during detection.

### 5.3 Planning Mode

- `hwren plan "add user authentication"` — agent reads the project, produces an ordered plan with unknowns and risks surfaced, asks clarifying questions if intent is ambiguous, and outputs the plan as a numbered list.
- No code is written or executed in planning mode. The plan can be saved or passed directly into task mode.

### 5.4 File Operations

- Bounded read (configurable line window).
- Targeted search (regex, symbol, text) via ripgrep.
- Safe write: show diff -> user approves -> atomic replacement with `.hearthwren.bak` fallback.
- Refuse paths outside the project root by default; protect `.git`, env files, and ignored secrets.

### 5.5 Terminal Execution

- Commands are shown to the user before execution.
- Require confirmation for anything beyond a pre-approved safe list (build, test, lint, common package managers).
- Bounded output (configurable line ceiling).
- Working directory pinned to project root unless explicitly changed.
- Exit status and stderr always captured and surfaced.
- No secrets passed into model context.

### 5.6 Git & Version Control

- `git status`, `git diff`, `git log`, `git branch` — read-only, no approval needed.
- Stage, commit — show summary, require approval.
- Push — show destination + branch, require explicit `yes` confirmation. Verify push result from `git` exit code, not model assumption.
- Never claim a push succeeded without checking the actual command result.

### 5.7 Verification & Error Recovery

- Discover and run project-native tests, lint, build on approval.
- Inspect failures: parse output, correlate with recent edits, propose a bounded repair.
- Stop and report rather than loop indefinitely. Maximum repair attempts configurable (default: 3).
- Recovery suggestions are evidence-based (file path + line where available), not guesses.

### 5.8 Project Memory (AGENT_MEMORY.md)

- Human-readable, version-controlled file at the project root.
- Contains: project purpose, architecture snapshot, entry points, setup/test commands, conventions, known constraints, dated decisions, past failures, and open questions.
- Updated only with user approval; changes shown as a diff before writing.
- Treated as focused context, not authoritative source truth. Agent cross-checks memory against actual files and Git state.

### 5.9 Coding Index

- Incremental SQLite FTS over source files (exclude generated, binary, ignored, and secret files).
- Optional lightweight symbol index (function/class names) built only if memory measurements permit.
- Index stored in `.hearthwren/index.db` (gitignored).
- Built only during idle time (model not inferring). Yields immediately when inference is requested. Interruptible, one file at a time.
- Never runs concurrently with model inference or terminal commands.

### 5.10 Sequential Subtasks (Role-Scoped)

- For complex tasks, the agent controller can run multiple focused passes (e.g. "understand", "write tests", "implement", "review") using the same model with role-scoped system prompts.
- These are **sequential** — never parallel. Each pass has its own memory budget and time limit.
- Not marketed as "multi-agent"; described as "task phases" to avoid implying independent parallel agents.

### 5.11 Guidance Mode

- `hwren guide "how do I set up CI for this project?"` — agent explains steps without making changes.
- Walks through safe, recommended sequences.
- User can opt into executing a step directly from guidance mode.

### 5.12 GitHub End-to-End Workflow

Full journey from empty repo to pushed branch:

```
1. hwren init                    -> detect or scaffold project
2. hwren plan "feature X"        -> ordered plan + clarification
3. hwren run                     -> implement, test, diff, iterate
4. hwren verify                  -> run full test suite + lint
5. hwren commit "feat: X"        -> show staged changes, approve
6. hwren push                    -> show destination, confirm, push

Also available at any time:
   hwren                         -> interactive chat/task mode
   hwren guide "question"        -> explain steps without acting
   hwren status                  -> show project + agent state
   hwren config                  -> view/edit .hearthwren/config.toml
```

---

## 6. Memory Architecture

### AGENT_MEMORY.md (portable, human-readable, in-repo)

The file Hearthwren generates for user projects. Structure:

```markdown
# AGENT MEMORY — <ProjectName>
_Last updated: YYYY-MM-DD by Hearthwren vX.Y.Z_

## Project
[One-paragraph description. Verified from README/manifests.]

## Architecture
[Entry points, key modules, data flow. Updated only when verified.]

## Setup & Test Commands
- Install: `...`
- Run: `...`
- Test: `...`
- Lint: `...`

## Conventions
[Naming, formatting, branching, PR rules as observed in codebase.]

## Constraints
[Performance, licensing, compatibility, hardware limits.]

## Known Issues & Past Failures
| Date | Phase/Task | Issue / Mistake | What Happened | Lesson |
|---|---|---|---|---|

## Open Questions
[Unresolved design or requirement questions.]

## Key Decisions
| Date | Decision | Rationale |
|---|---|---|

## Session Log
[Every Hearthwren session appends a structured entry here:
date/time, task, actions taken, outcome, mistakes, lessons learned.
Future sessions read this before starting work to avoid repeating mistakes.]
```

**Rules:**
- Hearthwren reads this file at session start before any workspace exploration.
- Stale or conflicting entries are flagged; Hearthwren verifies against actual files before trusting.
- Never written with secrets, credentials, personal data, or unverified model conclusions.
- Updated in focused sections (not a full rewrite) with a shown diff and user approval before commit.

### Local operational cache (.hearthwren/, gitignored)

| File | Purpose |
|---|---|
| `.hearthwren/config.toml` | User-editable settings: context size, output ceiling, timeout values, safe command allowlist, model path override |
| `.hearthwren/index.db` | SQLite FTS + symbol index (disposable, rebuilds automatically) |
| `.hearthwren/session.json` | Last task state for resumption (bounded, no source code) |
| `.hearthwren/diagnostics.log` | Resource and error log (no secrets, rotated by size) |

### Model storage

The GGUF model file is stored in a shared user-level directory (e.g. `~/.hearthwren/models/`) so it is downloaded once, not per-project. On first run, if the model is missing, Hearthwren prompts the user to download it with a displayed URL and SHA-256 hash. The download requires explicit user approval (network operation). The model path can be overridden in `.hearthwren/config.toml`.

Hearthwren works correctly if `.hearthwren/` is deleted. Recovery rebuilds the cache and resumes from `AGENT_MEMORY.md`.

### Prompt / context budget assembly

```
[System prompt + role]
+ [AGENT_MEMORY.md excerpt]
+ [Relevant file/search excerpt]
+ [Recent tool results (summarized if large)]
+ [User message]
<= context ceiling (default 4 096 tokens)
```

Low-priority history is trimmed first. Tool output is summarized with paths and key facts, not raw full content. Full file reads are windowed, not dumped.

---

## 7. Safety, Privacy & Correctness

| Principle | Implementation |
|---|---|
| **Honesty** | Distinguish observed fact (evidence + path), inference (marked as such), and unknown. Never claim a test passed without checking exit code and output. |
| **Clarification-first** | Ask before high-impact assumptions, destructive actions, ambiguous tasks, or anything touching security/credentials. |
| **Least privilege** | Workspace-scoped file access. No unrestricted shell. Network gated by approval. Secrets never enter model context. |
| **Tool-call validation** | Parse only expected structured format. Validate name, schema, paths, argument sizes, policy. Malformed calls surfaced as errors, not shell execution. |
| **Prompt injection resistance** | Repo text, terminal output, file content, and web content treated as untrusted data, not instructions that can override policy. |
| **Reversibility** | Diff before write. Atomic replacement with `.hearthwren.bak`. No silent overwrites of unrelated/untracked files. |
| **Privacy** | All processing local by default. No telemetry without explicit opt-in. No project code or secrets in error reports. |
| **Git safety** | No credentials stored. Commit and push always require explicit approval. Push destination displayed before confirmation. |

---

## 8. Technical Stack

| Layer | Technology | Reason |
|---|---|---|
| Language | Python 3.11+ | Wide compatibility, strong llama.cpp bindings, easy packaging |
| LLM runtime | `llama-cpp-python` (CPU build) | Mature, cross-platform, GGUF support, no GPU required |
| Model | `Nanbeige4.1-3B` Q4_K_M GGUF | Fits ~2 GB RAM; tool-use capable per model card |
| CLI framework | `typer` or `click` | Lightweight, composable, good help output |
| Search | `ripgrep` (subprocess) | Fast, ignore-aware, no Python dep for the hot path |
| DB / index | `sqlite3` (stdlib) | Zero extra deps, bounded, portable |
| File diff | `difflib` (stdlib) | No extra deps, produces readable unified diffs |
| Git | `subprocess` -> `git` CLI | Exact, auditable, no third-party abstraction layer |
| Token counting | Model tokenizer via `llama-cpp-python` | Accurate for the loaded model |
| RAM monitoring | `psutil` | Cross-platform memory/CPU metrics for the Resource Supervisor |
| Terminal UX | `rich` | Readable diffs, progress bars, syntax highlighting in the CLI (lightweight) |
| Testing (Hearthwren itself) | `pytest` | Standard, discoverable |
| Packaging | `pyproject.toml` + `hatch` or `flit` | Modern, minimal |

**Deliberately excluded:** LangChain, LlamaIndex, Haystack, AutoGen, CrewAI (heavy transitive deps, most features unneeded, add RAM overhead). Any vector database. Any HTTP server or always-on daemon.

---

## 9. Delivery Roadmap

### Phase 0 — Feasibility Gates (before writing any product code)

**Goal:** Confirm all hard assumptions on the actual target laptop.

- [ ] Download and convert Nanbeige4.1-3B to Q4_K_M GGUF; verify tokenizer and chat template round-trip.
- [ ] Verify tool-call structured output (JSON schema compliance) on a representative test set via `llama-cpp-python`.
- [ ] Measure cold-start RAM, sustained RAM, KV-cache growth, and tokens/sec on the 8 GB i5 laptop at 4 096 and 8 192 context.
- [ ] Confirm Apache-2.0 license covers the exact pinned revision, all included artifacts, and the intended distribution model. Consult a qualified reviewer for commercial use.
- [ ] Check "Hearthwren" and intended package names against trademark databases and PyPI/npm.
- [ ] **Gate:** If single-model CPU experience cannot stay within 3.5 GB ceiling with acceptable latency, revise design before proceeding.
- [ ] If Qwen3-4B or Terminus-4B become necessary per the gate, re-evaluate memory budget and document the reason.

**Deliverable:** `docs/phase0_results.md` committed to this repository.

---

### Phase 1 — Safe Local MVP

**Goal:** End-to-end flow from task input to reviewed file edit.

- [ ] CLI skeleton: `hwren init`, `hwren plan`, `hwren run`, `hwren status`.
- [ ] Local Model Service: managed `llama-cpp-python` process, health check, clean shutdown.
- [ ] Resource Supervisor: pre-flight RAM check, concurrency lock, timeouts, cancellation.
- [ ] Tool Broker: file read (windowed), file write (diff + approve), ripgrep search.
- [ ] Agent Controller: state machine, prompt assembly with token estimator, bounded tool-call loop.
- [ ] Planning mode: ordered plan, clarifying questions, no code changes.
- [ ] Guidance mode: explain steps without executing.
- [ ] `AGENT_MEMORY.md` reader (read-only in Phase 1).

**Gate:** Core workflow usable offline after model download. No push capability yet.

---

### Phase 2 — Git, Terminal, Recovery & Memory Writes

**Goal:** Full workflow from empty repo to committed change.

- [ ] Terminal tool: command preview, approval, execution, bounded output, exit-status capture.
- [ ] Git tools: status, diff, log, branch, stage, commit (with approval).
- [ ] Test runner: discovery, execution, output parsing, failure correlation.
- [ ] Verification loop: bounded repair attempts, stop-and-report on insufficient evidence.
- [ ] `AGENT_MEMORY.md` writer: section-targeted updates, diff preview, user approval.
- [ ] Local cache: SQLite session state, incremental FTS index (idle-time only).
- [ ] Stale-memory detection: cross-check memory claims against actual files.

**Gate:** No push yet. All core safety and recovery behaviors measured.

---

### Phase 3 — GitHub Push & Hardening

**Goal:** Full end-to-end: empty repo -> tested -> pushed branch.

- [ ] Push tool: show destination + branch, require explicit confirmation, verify result from exit code.
- [ ] Adversarial tests: path traversal, prompt injection via file content, malformed tool calls, memory pressure, long sessions.
- [ ] Install, model download with hash verification, upgrade, rollback, uninstall tested on clean Windows.
- [ ] Full documentation: supported configs, model attribution, license notices, offline behavior, known limits, troubleshooting.
- [ ] Benchmark suite committed as `docs/benchmarks/`.

**Gate:** All acceptance criteria (Section 10) pass. Commercial release ready.

---

### Phase 4 — Post-Release (future, not committed)

- Optional editor extension (VS Code) as a thin wrapper around the CLI.
- Optional Qwen3-4B or Terminus-4B as opt-in modes if hardware measurements allow.
- Incremental context compression to stretch the 4 096 ceiling without increasing RAM.

---

## 10. Acceptance Criteria

Release only when **all** of the following pass on a documented 8 GB CPU-only i5 laptop:

1. **Resource bound:** Representative tasks (new feature, bug fix, test addition, GitHub push) stay within the measured 3.5 GB Hearthwren working set. No unbounded growth in context, output, index, retry count, or subprocess count. Low-memory tests abort safely with an actionable message.
2. **Single-model proof:** Runtime diagnostics confirm only the pinned Nanbeige4.1-3B GGUF is loaded. No other model downloads, remote model calls, or background inference occur.
3. **Tool correctness:** Malformed calls and out-of-scope paths are rejected and surfaced. File changes produce a correct unified diff. Commands return real exit status. Cancellation terminates child processes.
4. **Evidence-based reporting:** Test pass/fail claims match captured exit codes and output. Unknowns are surfaced. Ambiguous high-impact requests trigger clarifying questions. Failures are not reported as success.
5. **Git safety:** Unrelated files are untouched. Commit and push both require explicit approval. Push destination and result are verified from `git` exit code.
6. **Memory usefulness:** A follow-up session uses `AGENT_MEMORY.md` to skip redundant discovery; stale entries are detected and flagged; agent cross-checks memory against actual files before edits.
7. **Reliability:** Restart after a crash or corrupted `.hearthwren/` cache recovers correctly. No project files silently discarded.
8. **Distribution readiness:** All licenses (model, tokenizer, runtime, deps) reviewed for intended commercial distribution. Model download integrity verified by hash. Product name clearance documented.

Numeric latency ceilings are set after Phase 0 measurements. All benchmark results include: model revision, runtime + build flags, quantization, CPU, context length, and peak RAM.

---

## 11. Explicit Non-Goals (First Release)

- Matching frontier hosted model coding quality.
- Guaranteeing zero hallucinations (impossible for any probabilistic model).
- Parallel independent model agents or multiple simultaneously loaded models.
- Cloud model fallback or any remote LLM API call.
- Automatic destructive changes, silent package installs, autonomous commits, or unconfirmed pushes.
- Indexing the entire machine or uploading any project data.
- Requiring vector search or an embedding model.
- Including Qwen3-4B or Terminus-4B unless Phase 0 measurement proves necessity and memory budget accommodates it.
- Guaranteeing the application can prevent system-wide OOM when other processes consume the machine's memory beyond Hearthwren's control.

---

## 12. Open Questions

| # | Question | Owner | Status |
|---|---|---|---|
| 1 | Does Nanbeige4.1-3B Q4_K_M GGUF preserve tool-call structure fidelity under `llama-cpp-python`? | Phase 0 spike | Open |
| 2 | What is actual sustained RAM at 4 096 context on the target laptop? | Phase 0 measurement | Open |
| 3 | Is Apache-2.0 on the exact pinned model revision cleared for commercial redistribution of a quantized GGUF? | Legal review | Open |
| 4 | Is "Hearthwren" clear for trademark and PyPI use in the intended categories? | Trademark/domain check | Open |
| 5 | Does tokens/sec at 4-bit on i5 produce acceptable UX latency for the expected task length? | Phase 0 measurement | Open |
| 6 | Is idle-time SQLite indexing adequately interruptible on Windows without threading overhead? | Phase 1 prototype | Open |

---

## 13. References

- [Nanbeige4.1-3B model card](https://huggingface.co/Nanbeige/Nanbeige4.1-3B) — capabilities, tool-use examples, inference recommendations, limitations.
- [Nanbeige4.1-3B config.json](https://huggingface.co/Nanbeige/Nanbeige4.1-3B/resolve/main/config.json) — architecture; the published max context is not adopted as the operational default.
- [llama.cpp](https://github.com/ggml-org/llama.cpp) — candidate CPU inference runtime; Phase 0 verifies actual compatibility and performance.
- [llama-cpp-python](https://github.com/abetlen/llama-cpp-python) — Python bindings; Phase 0 verifies tool-call schema support.
- [ripgrep](https://github.com/BurntSushi/ripgrep) — fast, ignore-aware code search.
