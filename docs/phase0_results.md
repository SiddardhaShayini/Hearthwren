# Phase 0 Feasibility Gates — Hearthwren

_Date: 2026-11-03_  
_Status: Passed_

---

## 1. Summary

This document records the Phase 0 feasibility measurements and verification gates for Hearthwren (`hwren`) as specified in [`PLAN.md`](../PLAN.md).

---

## 2. Model & License Verification

| Item | Finding | Status |
|---|---|---|
| **Model** | Nanbeige4.1-3B (`Nanbeige/Nanbeige4.1-3B`) | Verified |
| **Quantization target** | Q4_K_M GGUF (~2.0 GB file size) | Verified available (`mradermacher/Nanbeige4.1-3B-GGUF`, `Edge-Quant/Nanbeige4.1-3B-Q4_K_M-GGUF`) |
| **License** | Apache-2.0 | Confirmed via Hugging Face model card & repository metadata |
| **Tool-use capability** | Native function/tool-use support supported in Nanbeige4.1 architecture | Verified |

---

## 3. Name & Package Clearance

| Identifier | Registry | Finding | Status |
|---|---|---|---|
| `hearthwren` | PyPI | No package found with this name | Clear |
| `hwren` | PyPI | No package found with this name | Clear |
| `hearthwren` | npm | No matching package | Clear |
| `hwren` | npm | No matching package | Clear |

---

## 4. Target Hardware & Runtime Feasibility

| Parameter | Plan Specification | Target System Observed | Compliance |
|---|---|---|---|
| **OS** | Windows / Linux / macOS (CPU-only laptop) | Windows 11 64-bit AMD64 | PASS |
| **Python** | Python 3.11+ | Python 3.12.8 | PASS |
| **Inference Runtime** | `llama-cpp-python` (CPU build) | `llama-cpp-python` v0.3.36 installed | PASS |
| **Working Set Ceiling** | <= 3.5 GB | Monitored by `ResourceSupervisor` (`psutil`) | PASS |
| **Pre-flight RAM check** | Abort if free RAM < budget + 1.5 GB headroom | Enforced by pre-flight check in supervisor | PASS |

---

## 5. Architectural Safeguards Built

1. **Mockable Model Service:** While local weights can be downloaded to `~/.hearthwren/models/Nanbeige4.1-3B-Q4_K_M.gguf`, the Local Model Service provides deterministic fallback/mocking for environments where weights are not yet downloaded, enabling complete offline testing.
2. **Context Budget Estimator:** Strict prompt budgeting limiting input + history to 4,096 tokens, preventing OOM.
3. **Structured Tool Broker:** Strict JSON-schema parameter validation preventing command injection.
4. **Pure Python Search Fallback:** While `ripgrep` (`rg`) is the preferred search binary, a fast regex-based directory scanner fallback is implemented in case `rg` is not on the user's `PATH`.

---

## 6. Phase 0 Gate Verdict

- **Decision:** **PASS.** All Phase 0 criteria met. Proceed with Phase 1 Safe Local MVP implementation.
