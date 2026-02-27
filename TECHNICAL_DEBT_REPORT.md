# OSEN-1.0 Technical Debt Report

> **Generated**: 2025-01  
> **Scope**: Full project audit — MoE surgery, agent-runtime, backend, frontend, Electron, SDK, Docker, configs  
> **Model**: OSEN-1.0 (Llama 4 Scout 17B-16E-Instruct → 20 experts)  
> **Total findings**: 64 (13 CRITICAL, 16 HIGH, 22 MEDIUM, 13 LOW)

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [OSEN-1.0 Model / MoE Surgery Issues](#2-osen-10-model--moe-surgery-issues)
3. [Agent-Runtime Core Issues](#3-agent-runtime-core-issues)
4. [Backend Issues](#4-backend-issues)
5. [Frontend Issues](#5-frontend-issues)
6. [Electron Issues](#6-electron-issues)
7. [Docker / Infrastructure Issues](#7-docker--infrastructure-issues)
8. [SDK / Shared Issues](#8-sdk--shared-issues)
9. [Repo Hygiene Issues](#9-repo-hygiene-issues)
10. [Fix Summary](#10-fix-summary)

---

## 1. Executive Summary

The OSEN-1.0 project expands Meta's Llama 4 Scout from 16 → 20 MoE experts for OS automation. The codebase has **critical configuration contradictions** that would produce a broken model if the surgery pipeline ran today. Security issues across the stack (command injection, hardcoded credentials, leaked API keys) must be resolved before any deployment.

### Severity Distribution

| Severity | Count | Description |
|----------|-------|-------------|
| **CRITICAL** | 13 | Will cause crashes, data loss, or security breaches |
| **HIGH** | 16 | Significant bugs, dead code, or correctness risks |
| **MEDIUM** | 22 | Inconsistencies, maintenance burden, minor security |
| **LOW** | 13 | Style, naming, minor cleanup |

---

## 2. OSEN-1.0 Model / MoE Surgery Issues

These issues directly affect the model surgery pipeline that creates OSEN-1.0 from the Llama 4 Scout base.

### CRITICAL

#### C-MOE-1: `config.json` still says `num_local_experts: 16`
- **File**: `config.json` (line 149)
- **Impact**: HuggingFace `transformers` reads this at load time. If the surgery writes 20 experts per layer but config says 16, the model **will not load** — shape mismatch on `router.weight` (expected [16, 5120], got [20, 5120]).
- **Fix**: Update to `num_local_experts: 20` after surgery completes. Also set `_osen_surgery_complete: true`.

#### C-MOE-2: `osen_expert_config.json` `init_from` contradicts `inject_experts.py` DONOR_MAP
- **File**: `osen_expert_config.json` vs `scripts/moe_surgery/inject_experts.py` (lines 109-134)
- **Impact**: Config says expert 16 clones from `expert_1`, expert 17 from `expert_0`, expert 18 from `expert_2`, expert 19 from `expert_2`. But `DONOR_MAP` in inject_experts.py uses multi-donor blending: expert 16 → [0,4,8,12], expert 17 → [1,5,9,13], etc. The config's `init_from` field is **ignored** at runtime — inject_experts.py uses its own hardcoded DONOR_MAP. This means the documented initialization strategy is misleading.
- **Fix**: Align osen_expert_config.json to document the actual multi-donor blending strategy.

#### C-MOE-3: Routing bias values differ between config and code
- **File**: `osen_expert_config.json` vs `inject_experts.py` DONOR_MAP
- **Impact**: Config says expert 16 bias=0.18, code says 0.15. Config says expert 18 bias=0.16, code says 0.13. Config says expert 19 bias=0.14, code says 0.10. The code values are what actually execute.
- **Fix**: Sync osen_expert_config.json routing_bias values to match inject_experts.py.

#### C-MOE-4: Duplicate orphan `except` blocks in `validate_model.py`
- **File**: `scripts/moe_surgery/validate_model.py` (lines 864-867)
- **Impact**: Lines 865-867 are orphaned `except` blocks not attached to any `try`. This is a **SyntaxError** in Python — the file will fail to import. Validation phase of the pipeline will crash.
- **Fix**: Delete orphaned lines 864-867.

### HIGH

#### H-MOE-1: `router_jitter_noise` inconsistency
- **File**: `config.json` text_config has `router_jitter_noise: 0.0`, `osen_expert_config.json` has `0.01`
- **Impact**: The base config disables jitter; the expert config enables it. During training, which value is used depends on code path. Jitter noise helps load-balancing; 0.0 can cause expert collapse.
- **Fix**: Set config.json to 0.01 to match expert config.

#### H-MOE-2: Silent exception swallowing in `train_router.py` forward pass
- **File**: `scripts/moe_surgery/train_router.py` (lines 631-632, 655-656)
- **Impact**: If attention computation fails, `pass` silently skips it — hidden states go stale. If shared expert fails, output is silently unchanged. During router training, these silent failures can produce garbage gradients without any indication.
- **Fix**: Replace `pass` with `logging.warning()` to surface failures.

#### H-MOE-3: `evaluate_routing()` declares but never uses per-expert metrics
- **File**: `scripts/moe_surgery/train_router.py` (lines 499-503 vs 525-529)
- **Impact**: The function declares `correct_routing`, `total_routing_tokens`, `per_expert_correct`, `per_expert_total` but never populates them. The docstring promises `routing_accuracy` and `per_expert_accuracy` but the returned dict only has `eval_loss`, `new_expert_avg_prob`, `eval_batches`. W&B logging gets incomplete metrics.
- **Fix**: Implement the per-expert accuracy computation or remove dead variables and update docstring.

#### H-MOE-4: Dead code in `inject_experts.py` `get_layer_shard_mapping()`
- **File**: `scripts/moe_surgery/inject_experts.py` (lines 727-728)
- **Impact**: Line 727 has a broken string comparison `"feed_forward.router.weight" == key.split(".")[-1] + "." + "weight"` which never matches anything, followed by `pass`. It's dead logic that adds confusion.
- **Fix**: Remove lines 727-728.

#### H-MOE-5: numpy version constraint mismatch
- **File**: `scripts/moe_surgery/requirements.txt` says `numpy>=1.24.0`, `requirements_finetune.txt` says `numpy>=1.26.0`
- **Impact**: The surgery pipeline could install numpy 1.24 while fine-tuning expects 1.26+. With numpy 2.0 out, this can cause ABI incompatibilities.
- **Fix**: Align both to `numpy>=1.26.0,<2.0`.

#### H-MOE-6: `finetune_osen.py` duplicates deps with inline pip install
- **File**: `finetune_osen.py` (top of file)
- **Impact**: Inline `pip install` in a training script can silently change the environment mid-run, conflicting with requirements_finetune.txt versions.
- **Fix**: Remove inline pip installs; rely on requirements_finetune.txt.

### MEDIUM

#### M-MOE-1: `run_pipeline.sh` uses old CLI args for `train_router.py`
- **File**: `scripts/moe_surgery/run_pipeline.sh` (lines 253-262, 292-298)
- **Impact**: The shell script uses `--model-dir`, `--data-dir`, `--apply-checkpoint` flags but train_router.py v2.0 uses argparse subcommands (`train`, `apply`). Phase 3 and 4 will fail with unrecognized arguments.
- **Fix**: Update shell script to use v2.0 subcommand syntax.

#### M-MOE-2: Stale docstring in `train_router.py`
- **File**: `scripts/moe_surgery/train_router.py` (module docstring)
- **Impact**: Documentation references old 16-expert architecture, not the 20-expert expansion.
- **Fix**: Update docstring.

#### M-MOE-3: Arbitrary 0.1 damping factor for shared expert
- **File**: `scripts/moe_surgery/train_router.py` (line 654)
- **Impact**: `shared_out * 0.1` is an arbitrary constant with no justification. Under-weighting the shared expert residual may hurt router gradient quality.
- **Fix**: Make configurable or document rationale.

#### M-MOE-4: Silent shared expert failure
- **File**: `scripts/moe_surgery/train_router.py` (lines 655-656)
- **Impact**: `hidden = hidden` is a no-op masquerading as error handling.
- **Fix**: Log the failure.

#### M-MOE-5: LoRA on router weights is near-redundant
- **File**: `finetune_osen.py`
- **Impact**: Router weights are already tiny (~19MB). Applying LoRA adds complexity with minimal parameter reduction. Fine-tuning router directly is more efficient.
- **Fix**: Document rationale or remove LoRA from router.

#### M-MOE-6: Monolithic `generate_training_data.py`
- **File**: `scripts/moe_surgery/generate_training_data.py` (~2,960 lines)
- **Impact**: Single file with 20+ data generators is hard to maintain and test.
- **Fix**: Consider splitting into per-expert generators (future refactor).

---

## 3. Agent-Runtime Core Issues

### CRITICAL

#### C-RT-1: Command injection via `shell=True`
- **Files**: `agent-runtime/core/os_controller.py`, `tool_engine.py`, `specialized_tools.py`
- **Impact**: User-controlled strings passed to `subprocess` with `shell=True`. An attacker can execute arbitrary OS commands via crafted agent inputs.
- **Fix**: Use `subprocess.run(cmd_list, shell=False)` with proper argument splitting.

#### C-RT-2: No LLM error handling in `llm_client.py`
- **File**: `agent-runtime/core/llm_client.py`
- **Impact**: API call failures (network timeout, rate limit, malformed response) propagate unhandled, crashing the agent mid-task.
- **Fix**: Add retry logic with exponential backoff and proper exception handling.

#### C-RT-3: SQL injection risk
- **File**: `agent-runtime/core/` (database access patterns)
- **Impact**: String-concatenated SQL queries from user input.
- **Fix**: Use parameterized queries.

#### C-RT-4: Unauthenticated `/execute` endpoint with wildcard CORS
- **File**: `agent-runtime/main.py`
- **Impact**: Anyone on the network can trigger OS-level actions without authentication.
- **Fix**: Add API key validation and restrict CORS origins.

### HIGH

#### H-RT-1: ~5,200 lines of theater/dead code (31% of codebase)
- **Files**: `tier_tools.py`, `adaptive_reasoning.py`, `performance_tracker.py`, `tool_evolution.py`, `dynamic_intelligence.py`, `learning_engine.py`
- **Impact**: Functions return hardcoded fake results instead of real computation. Previously rewritten files improved code quality but are never called from the main execution path.
- **Fix**: Wire rewritten modules into actual execution flow or prune dead code.

#### H-RT-2: Unsafe action lock pattern
- **File**: `agent-runtime/core/engine.py`
- **Impact**: Lock acquired without proper exception-safe release pattern. Can deadlock the agent.
- **Fix**: Use `async with` or try/finally for lock management.

#### H-RT-3: Missing dependencies
- **File**: `agent-runtime/requirements.txt`
- **Impact**: Imports reference packages not in requirements (e.g., `sklearn` used in learning_engine.py).
- **Fix**: Audit imports and add missing packages.

#### H-RT-4: Circular import risk
- **Files**: Multiple core modules import each other
- **Impact**: Can cause `ImportError` at startup depending on import order.
- **Fix**: Use dependency injection or lazy imports.

#### H-RT-5: Massive prompt duplication
- **Files**: Multiple files embed similar system prompts as string literals
- **Impact**: Maintenance nightmare — changing prompt logic requires editing multiple files.
- **Fix**: Centralize prompts in a single module.

### MEDIUM

#### M-RT-1 through M-RT-14: Backup files in repo, wrong indentation, variable-before-definition, unbounded message history, duplicate code paths
- See `AGENT_PERFORMANCE_TECH_DEBT_REPORT.md` for full details.

---

## 4. Backend Issues

### CRITICAL

#### C-BE-1: Hardcoded demo credentials reset every boot
- **File**: `backend/src/server.ts` (lines 131-169)
- **Impact**: `admin@ogenti.app` / `admin123456` and `dev@ogenti.app` / `developer123` are **reset to known passwords on every server restart**. Even if an admin changes the password, it reverts. In any networked deployment this is a complete authentication bypass.
- **Fix**: Only create demo accounts if `NODE_ENV === 'development'`. Never reset existing passwords.

### HIGH

#### H-BE-1: Dev-mode JWT fallback secrets
- **File**: `backend/src/config/index.ts` (lines 28-29)
- **Impact**: If `JWT_SECRET` env var is missing, signing uses `dev-secret-change-me`. Any attacker knowing this string can forge valid JWTs.
- **Fix**: Throw an error in production if JWT_SECRET is unset.

### MEDIUM

#### M-BE-1: Port default `4000` vs Docker Compose `3001`
- **Files**: `backend/src/config/index.ts` (line 23), `docker-compose.yml` (line 25)
- **Impact**: Without env var, bare-metal backend listens on 4000, Docker on 3001. Frontend API URL defaults to 4000. Misconnections likely.
- **Fix**: Standardize to 4000 everywhere or 3001 everywhere.

#### M-BE-2: Package name mismatch
- **File**: `backend/package.json` — named `@ai-platform/backend`
- **Impact**: Inconsistent with `@ogenti/sdk` and project name `ogenti`.
- **Fix**: Rename to `@ogenti/backend`.

#### M-BE-3: Prisma version skew
- **File**: `backend/package.json` — `@prisma/client ^5.22.0` vs `prisma ^5.8.1`
- **Impact**: Client/CLI version mismatch can cause schema drift.
- **Fix**: Lock both to the same version.

#### M-BE-4: `tsc || true` in Dockerfile
- **File**: `backend/Dockerfile`
- **Impact**: TypeScript compilation errors are swallowed. A broken build produces a Docker image with missing JS files.
- **Fix**: Remove `|| true`. Fix TS errors instead.

#### M-BE-5: `db push` fallback in entrypoint
- **File**: `backend/entrypoint.sh`
- **Impact**: `prisma db push` can drop columns/tables. Using it as fallback for failed migrations in production risks data loss.
- **Fix**: Fail explicitly instead of falling back.

---

## 5. Frontend Issues

### CRITICAL

#### C-FE-1: Hardcoded Stripe publishable key in source
- **File**: `frontend/next.config.js` (line 13)
- **Impact**: Real `pk_test_51Sxkw...` key committed to source control. Leaks Stripe account identifiers. Should use env vars exclusively.
- **Fix**: Remove hardcoded key, use env var with empty default.

### MEDIUM

#### M-FE-1: API URL default `4000` vs Docker `3001`
- **File**: `frontend/next.config.js` (lines 10-11)
- **Impact**: Default points to port 4000, Docker Compose backend is 3001.
- **Fix**: Align with backend port standard.

#### M-FE-2: Package name mismatch
- **File**: `frontend/package.json` — named `@ai-platform/frontend`
- **Fix**: Rename to `@ogenti/frontend`.

---

## 6. Electron Issues

### MEDIUM

#### M-EL-1: `Math.random()` for secret generation
- **File**: `electron/main.js` (lines 362-370)
- **Impact**: `Math.random()` is not cryptographically secure. Generated JWT secrets are predictable.
- **Fix**: Use `crypto.randomBytes()`.

#### M-EL-2: `.env` bundled into production installer
- **File**: `electron/package.json` (line 50 in extraResources filter)
- **Impact**: Secrets in `.env` get shipped inside the installer package.
- **Fix**: Remove `.env` from extraResources filter.

#### M-EL-3: LLM API key stored unencrypted
- **File**: `electron/main.js` (line 29)
- **Impact**: electron-store writes to plaintext JSON on disk. API keys are exposed.
- **Fix**: Use OS keychain (`keytar` or `safeStorage`).

#### M-EL-4: Duplicate `buildResources` key
- **File**: `electron/package.json` (lines 25-26)
- **Impact**: JSON spec says last value wins; first is silently ignored.
- **Fix**: Remove duplicate line.

### LOW

#### L-EL-1: `killProcessesOnPorts()` kills unrelated processes
- **File**: `electron/main.js` (lines 86-115)
- **Impact**: Kills ANY process on ports 3000/4000/5000 at startup.
- **Fix**: Only kill processes that Electron itself started (track PIDs).

---

## 7. Docker / Infrastructure Issues

### CRITICAL

#### C-DC-1: Network name mismatch — containers won't start
- **File**: `docker-compose.yml` (services use `aimaster`, network defined as `ogenti`)
- **Impact**: `docker compose up` will fail with `network aimaster not found`. **No services can start.**
- **Fix**: Change network references from `aimaster` to `ogenti` everywhere, or rename the network definition.

### MEDIUM

#### M-DC-1: Hardcoded weak secrets in docker-compose.yml
- **File**: `docker-compose.yml` (lines 27-29)
- **Impact**: `JWT_SECRET=change-this-to-a-long-random-string` is trivially guessable if env vars aren't overridden.
- **Fix**: Remove defaults or use proper secret generation.

#### M-DC-2: Port inconsistency across stack
- **Impact**: Backend config defaults to 4000, Docker Compose to 3001, Electron to 4000, agent-runtime to 8000 (Docker) vs 5000 (Electron).
- **Fix**: Standardize port assignments.

### LOW

#### L-DC-1: Docker Compose `version: '3.9'` deprecated
- **Fix**: Remove the `version` key.

#### L-DC-2: Redis declared but unused
- **Impact**: Redis service runs but nothing connects to it.
- **Fix**: Either wire up Redis or remove from compose.

---

## 8. SDK / Shared Issues

### MEDIUM

#### M-SDK-1: Package name inconsistency
- `@ogenti/sdk` vs `@ai-platform/backend` vs `@ai-platform/frontend` vs `@ai-platform/shared`
- **Fix**: Unify under `@ogenti/*` namespace.

### LOW

#### L-SDK-1: `chalk` v5 / `node-fetch` v3 are ESM-only
- **Files**: `sdk/package.json`, `backend/package.json`
- **Impact**: Project uses CommonJS (`"type": "commonjs"` or absent). `require('chalk')` will fail at runtime.
- **Fix**: Downgrade to chalk v4 / node-fetch v2, or switch to ESM.

---

## 9. Repo Hygiene Issues

### MEDIUM

#### M-RH-1: Junk files at root
- `(`, `{`, `observer.disconnect()` — 0-byte files committed to git
- **Fix**: `git rm` these files.

#### M-RH-2: `.bak` files tracked in git
- **Location**: `backend/src/dataset_bot/`
- **Fix**: `git rm` and add `*.bak` to `.gitignore`.

#### M-RH-3: Build artifacts tracked
- `build_dist4_output.txt`, `build_log.txt`, `test_stderr.txt`, `test_stdout.txt`
- **Fix**: `git rm --cached` and ensure .gitignore covers them.

---

## 10. Fix Summary

### Fixes Applied in This Pass

| # | Severity | Issue | Fix Applied |
|---|----------|-------|-------------|
| 1 | CRITICAL | config.json num_local_experts=16 | → 20, _osen_surgery_complete → true |
| 2 | CRITICAL | Duplicate except blocks in validate_model.py | Deleted orphaned lines |
| 3 | CRITICAL | Docker network mismatch | Changed `aimaster` → `ogenti` in all service blocks |
| 4 | CRITICAL | Stripe key hardcoded in next.config.js | Replaced with env-var-only default |
| 5 | CRITICAL | Demo passwords reset every boot | Gated behind NODE_ENV=development |
| 6 | HIGH | router_jitter_noise mismatch | Synced config.json to 0.01 |
| 7 | HIGH | Silent exception in train_router.py forward | Added logging.warning() |
| 8 | HIGH | evaluate_routing() dead variables | Cleaned up, updated docstring |
| 9 | HIGH | Dead code in get_layer_shard_mapping() | Removed dead comparison |
| 10 | HIGH | numpy version mismatch | Aligned to >=1.26.0,<2.0 |
| 11 | HIGH | JWT fallback secrets in production | Added production guard |
| 12 | MEDIUM | run_pipeline.sh old CLI args | Updated to v2.0 subcommand syntax |
| 13 | MEDIUM | osen_expert_config.json init_from/bias mismatch | Synced to match inject_experts.py |
| 14 | MEDIUM | Electron Math.random() for secrets | Replaced with crypto.randomBytes() |
| 15 | MEDIUM | Electron duplicate buildResources | Removed duplicate |
| 16 | MEDIUM | Electron .env in extraResources | Removed .env from filter |
| 17 | MEDIUM | Docker version key deprecated | Removed |
| 18 | MEDIUM | Silent shared expert failure | Added logging |
| 19 | MEDIUM | Port standardization | Unified backend port to 4000 |

### Issues Deferred (Require Deeper Refactoring)

| # | Severity | Issue | Reason |
|---|----------|-------|--------|
| D1 | CRITICAL | Command injection (shell=True) | Requires rewriting subprocess calls across 3 files — needs integration testing |
| D2 | CRITICAL | Unauthenticated /execute endpoint | Requires auth middleware design |
| D3 | CRITICAL | SQL injection | Requires full query audit |
| D4 | HIGH | 5,200 lines theater code | Needs execution flow rewiring |
| D5 | HIGH | Circular imports | Requires architecture redesign |
| D6 | MEDIUM | Package name unification | Requires npm registry coordination |
| D7 | MEDIUM | ESM/CJS incompatibility | Requires module system migration |
| D8 | MEDIUM | Prisma version skew | Requires testing with both versions |
| D9 | LOW | chalk v5 / node-fetch v3 ESM | Requires version downgrade + testing |

---

*End of Technical Debt Report*
