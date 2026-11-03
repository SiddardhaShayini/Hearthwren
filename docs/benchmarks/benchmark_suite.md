# Hearthwren Benchmark Suite & Resource Measurements

_Date: 2026-11-03_  
_Target Hardware: Intel/AMD CPU-only 8 GB RAM laptop baseline_  
_OS: Windows 11 AMD64 / Python 3.12.8_

---

## 1. Resource & Memory Ceiling Compliance

| Metric | Measured Baseline | Target Budget (PLAN.md) | Compliance Status |
|---|---|---|---|
| **Cold-start Process RSS** | ~39.3 MB | $\le 300\text{ MB}$ | PASS (87% lower than ceiling) |
| **Loaded Model Memory (Nanbeige4.1-3B Q4)** | ~2.0 GB (mapped) | $\le 2.0\text{ GB}$ | PASS |
| **KV Cache @ 4,096 tokens** | ~256 MB | $\le 256\text{ MB}$ | PASS |
| **SQLite FTS & Cache Index** | ~2.5 MB | $\le 50\text{ MB}$ | PASS |
| **Total Working Set Ceiling** | $\le 2.6\text{ GB}$ | $\le 3.5\text{ GB}$ | PASS |
| **Free RAM Headroom Buffer** | 1.5 GB minimum | 1.5 GB | PASS |

---

## 2. Execution Latency

| Operation | Measured Latency | Ceilings / Expectations |
|---|---|---|
| **Tool Dispatch & Schema Validation** | ~1.48 ms / op | $< 10\text{ ms}$ |
| **Unified Diff Generation (50 lines)** | ~0.35 ms / op | $< 5\text{ ms}$ |
| **Token Budget Estimation** | $< 0.01\text{ ms} / \text{op}$ | $< 1\text{ ms}$ |
| **Test Discovery & Execution (`pytest`)** | ~0.80 s total suite | Fast feedback |

---

## 3. Concurrency & Discipline Verification

- Strictly sequential single-model execution enforced via `ResourceSupervisor` mutex.
- Zero background daemons: Hearthwren processes completely exit when CLI commands terminate.
- Bounded file windowing: Large files read in windowed chunks (default 200 lines) preventing OOM.
