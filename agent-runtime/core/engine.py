"""
Execution Engine - Orchestrates agent execution with LLM and OS control.

v3 — "Look-Act-Verify" Architecture
====================================
Core principle: NEVER proceed to the next step without verifying the current
step actually worked by re-examining the screen.

Key improvements over v2:
- Mandatory post-action screenshot verification
- Pre-action state assertion (e.g., is input field focused before typing?)
- Visual grounding: LLM must describe what it SEES before acting
- Coordinate grid overlay for more accurate click targeting
- Smart wait: waits for UI to settle after actions
- Failure-aware: detects when actions didn't change the screen
- Progressive retry with alternative strategies
"""

import asyncio
import os
import time
import json
import base64
import hashlib
from typing import Optional
from loguru import logger
import httpx

from core.os_controller import OSController
from core.screenshot import ScreenshotCapture
from core.llm_client import LLMClient, create_llm_client

# ── ogent-1.0 token reporting ──
_BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:4000")
_RUNTIME_SECRET = os.getenv("AGENT_RUNTIME_SECRET", "")
_RUNTIME_TOKEN = os.getenv("RUNTIME_TOKEN", "")

def _get_auth_headers() -> dict:
    if _RUNTIME_TOKEN:
        return {"X-Runtime-Token": _RUNTIME_TOKEN}
    return {"X-Runtime-Secret": _RUNTIME_SECRET}

async def _report_ogent_tokens(
    owner_id: str, mode: str, input_tokens: int, output_tokens: int, session_id: str = ""
):
    """Report ogent-1.0 token usage to backend for credit deduction."""
    if not owner_id or (input_tokens + output_tokens) == 0:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(
                f"{_BACKEND_URL}/api/execution/ogent-token-report",
                json={
                    "ownerId": owner_id,
                    "mode": mode,
                    "inputTokens": input_tokens,
                    "outputTokens": output_tokens,
                    "sessionId": session_id,
                },
                headers=_get_auth_headers(),
            )
    except Exception as e:
        logger.debug(f"ogent token report failed (non-critical): {e}")
from core.plugin_loader import PluginLoader
from core.provider_prompt_adapter import adapt_system_prompt, get_refusal_recovery_prompt
from core.agent_intelligence import (
    ScreenStateClassifier, ScreenState, ScreenAnalysis,
    AutoActionResolver, ActionValidator, StuckDetector,
    TaskProgressTracker, TaskPhase,
    ContextAccumulator,
    SmartPromptBuilder,
)

try:
    from core.agent_registry import (
        get_agent_profile, get_agent_tier_config, get_agent_allowed_actions,
        get_agent_engine_flags, AgentProfile,
    )
    HAS_REGISTRY = True
except ImportError:
    HAS_REGISTRY = False

try:
    from core.tier_config import get_tier_config, TierConfig
    HAS_TIER = True
except ImportError:
    HAS_TIER = False

try:
    from core.collaboration_engine import CollaborationBus, CollaborativeSession
    HAS_COLLAB = True
except ImportError:
    HAS_COLLAB = False

try:
    from core.vision_engine import VisionEngine
    HAS_VISION = True
except ImportError:
    HAS_VISION = False

try:
    from core.som_engine import SoMEngine, SoMResult
    HAS_SOM = True
except ImportError:
    HAS_SOM = False
    SoMEngine = None
    SoMResult = None

try:
    from core.semantic_som_engine import SemanticSoMEngine, SemanticSoMConfig
    HAS_SEMANTIC_SOM = True
except ImportError:
    HAS_SEMANTIC_SOM = False
    SemanticSoMEngine = None
    SemanticSoMConfig = None

try:
    from core.ui_automation import UIAutomationEngine, uia_elements_to_som_description
    HAS_UIA = True
except ImportError:
    HAS_UIA = False
    UIAutomationEngine = None

RUNTIME_SECRET = os.getenv("AGENT_RUNTIME_SECRET", "")
if not RUNTIME_SECRET and not _RUNTIME_TOKEN:
    import warnings
    warnings.warn(
        "Neither AGENT_RUNTIME_SECRET nor RUNTIME_TOKEN set. "
        "Runtime-to-backend callbacks will fail.",
        stacklevel=1,
    )


# ═══════════════════════════════════════════════════════════════════════
# TASK INTELLIGENCE SYSTEM
# ═══════════════════════════════════════════════════════════════════════
# Analyzes user prompts to determine task type and provides concrete
# step-by-step strategies with Windows-specific app knowledge.
# This is the BRAIN — it translates vague human instructions into
# concrete, actionable OS-level procedures.
# ═══════════════════════════════════════════════════════════════════════

import re as _re

from core.prompts import (
    TaskType,
    ACTION_DEFINITIONS,
    VALID_ACTIONS as _VALID_ACTIONS,
    TASK_STRATEGY_PROMPTS,
    BROWSER_GUIDE,
    COMPLETION_RULES,
    WINDOWS_APP_INTELLIGENCE,
    OGENTI_KEYWORDS,
    _is_ogenti_screen,
    APP_LAUNCH_GUIDE,
    PRECONDITION_RULES,
    SELF_DETECTION_WARNING,
    _BROWSER,
    _BROWSER_DISPLAY,
)


class TaskAnalyzer:
    """
    Analyzes user prompts to determine task type and provide intelligent
    guidance for how to accomplish the task on a Windows computer.
    
    This bridges the gap between "research about OpenAI" and the actual
    sequence of OS actions needed: open Chrome → search Google → read pages → 
    open Notepad → write report → save.
    """
    
    # Keyword detection patterns — weighted scoring
    _PATTERNS = {
        TaskType.RESEARCH: {
            "strong": [  # 5 points each
                "research about", "research on", "write a report", "write report",
                "search for information", "find information about", "investigate",
                "look up information", "study about", "compile research",
                "리서치", "조사해", "검색해서", "보고서 작성", "알아봐",
            ],
            "medium": [  # 3 points each
                "research", "report", "search", "find out", "investigate",
                "explore", "discover", "summarize", "analyze", "study",
                "wikipedia", "google", "article", "source", "reference",
                "검색", "조사", "보고서", "리포트", "찾아",
            ],
            "weak": [  # 1 point each
                "learn", "information", "topic", "about", "what is", "who is",
            ],
        },
        TaskType.CODING: {
            "strong": [
                "write code", "write a program", "create a script", "build an app",
                "fix the bug", "debug this", "implement", "코딩해", "프로그래밍",
                "코드 작성", "개발해",
            ],
            "medium": [
                "code", "program", "script", "function", "class", "api",
                "python", "javascript", "typescript", "react", "node",
                "compile", "debug", "refactor", "test", "deploy",
                "코딩", "코드", "프로그래밍", "개발",
            ],
            "weak": ["fix", "create", "build", "make"],
        },
        TaskType.WRITING: {
            "strong": [
                "write a document", "write an essay", "compose", "draft a letter",
                "write an email", "문서 작성", "글쓰기", "이메일 작성",
            ],
            "medium": [
                "document", "essay", "article", "blog", "letter", "email",
                "memo", "manuscript", "작성", "글쓰기", "문서",
            ],
            "weak": ["write", "text", "content"],
        },
        TaskType.DESIGN: {
            "strong": [
                "design a", "create a mockup", "wireframe", "ui design",
                "디자인", "레이아웃 만들어",
            ],
            "medium": [
                "design", "layout", "mockup", "prototype", "figma",
                "photoshop", "illustrator", "logo", "banner", "icon",
                "디자인", "레이아웃",
            ],
            "weak": ["visual", "style", "color", "font"],
        },
        TaskType.BROWSING: {
            "strong": [
                "open website", "go to website", "visit the site",
                "navigate to", "웹사이트 열어", "사이트 가",
            ],
            "medium": [
                "browse", "website", "web page", "url", "download from",
                "웹사이트", "브라우저",
            ],
            "weak": ["open", "visit", "check"],
        },
        TaskType.FILE_MANAGEMENT: {
            "strong": [
                "organize files", "rename files", "move files", "copy files",
                "파일 정리", "파일 이동",
            ],
            "medium": [
                "file", "folder", "directory", "rename", "move",
                "copy", "delete", "compress", "extract", "zip",
                "파일", "폴더", "정리",
            ],
            "weak": ["organize", "clean"],
        },
        TaskType.DATA_ANALYSIS: {
            "strong": [
                "analyze data", "data analysis", "create a chart",
                "데이터 분석", "차트 만들어",
            ],
            "medium": [
                "data", "csv", "excel", "chart", "graph", "statistics",
                "correlation", "trend", "데이터", "엑셀", "차트",
            ],
            "weak": ["analyze", "numbers", "count"],
        },
        TaskType.AUTOMATION: {
            "strong": [
                "automate", "batch process", "schedule task",
                "자동화", "배치 처리",
            ],
            "medium": [
                "automation", "script", "cron", "scheduled", "batch",
                "자동화", "스크립트",
            ],
            "weak": ["auto", "repeat"],
        },
    }

    @classmethod
    def detect(cls, prompt: str) -> TaskType:
        """Detect the primary task type from the user's prompt."""
        prompt_lower = prompt.lower().strip()
        scores: dict[TaskType, int] = {t: 0 for t in TaskType}
        
        for task_type, patterns in cls._PATTERNS.items():
            for phrase in patterns.get("strong", []):
                if phrase in prompt_lower:
                    scores[task_type] += 5
            for phrase in patterns.get("medium", []):
                if phrase in prompt_lower:
                    scores[task_type] += 3
            for phrase in patterns.get("weak", []):
                if phrase in prompt_lower:
                    scores[task_type] += 1
        
        best = max(scores, key=scores.get)
        if scores[best] >= 3:
            return best
        return TaskType.GENERAL
    
    @classmethod
    def extract_search_query(cls, prompt: str) -> str:
        """Extract a clean search query from the prompt."""
        cleaned = prompt.strip()
        # Remove task instruction prefixes
        for prefix_pattern in [
            r"^research\s+about\s+", r"^research\s+on\s+", r"^search\s+for\s+",
            r"^find\s+information\s+(?:about|on)\s+", r"^look\s+up\s+",
            r"^write\s+(?:a\s+)?report\s+(?:about|on)\s+", r"^investigate\s+",
            r"^learn\s+about\s+", r"^tell\s+me\s+about\s+",
            r"^find\s+out\s+(?:about\s+)?", r"^explore\s+", r"^study\s+",
        ]:
            cleaned = _re.sub(prefix_pattern, "", cleaned, flags=_re.IGNORECASE)
        # Remove trailing actions
        for suffix_pattern in [
            r"\s+and\s+write\s+(?:a\s+)?report.*$",
            r"\s+and\s+summarize.*$", r"\s+and\s+compile.*$",
            r"\s+and\s+create.*$",
        ]:
            cleaned = _re.sub(suffix_pattern, "", cleaned, flags=_re.IGNORECASE)
        return cleaned.strip() or prompt.strip()
    
    @classmethod
    def get_recommended_apps(cls, task_type: TaskType) -> list[str]:
        """Get the recommended app launch sequence for a task type."""
        APP_MAP = {
            TaskType.RESEARCH: [_BROWSER, "notepad"],
            TaskType.CODING: ["code", "terminal"],
            TaskType.WRITING: ["notepad"],
            TaskType.DESIGN: [_BROWSER, "notepad"],
            TaskType.BROWSING: [_BROWSER],
            TaskType.FILE_MANAGEMENT: ["explorer"],
            TaskType.DATA_ANALYSIS: ["excel", "terminal"],
            TaskType.AUTOMATION: ["terminal", "powershell"],
            TaskType.GENERAL: [_BROWSER, "notepad"],
        }
        return APP_MAP.get(task_type, [_BROWSER])

    @classmethod
    def get_first_action_hint(cls, task_type: TaskType, search_query: str = "") -> str:
        """Get the concrete first action the agent should take."""
        if task_type == TaskType.RESEARCH:
            safe_query = search_query.replace(" ", "+")
            return (
                f"START HERE — Your first actions should be:\n"
                f"1. ACTION: open_app  PARAMS: {{\"name\": \"chrome\"}}\n"
                f"2. ACTION: wait      PARAMS: {{\"seconds\": 3}}\n"
                f"3. ACTION: hotkey    PARAMS: {{\"keys\": [\"ctrl\", \"l\"]}}\n"
                f"4. ACTION: type_text PARAMS: {{\"text\": \"https://www.google.com/search?q={safe_query}\"}}\n"
                f"5. ACTION: press_key PARAMS: {{\"key\": \"enter\"}}\n"
                f"Then read the search results and click on relevant links."
            )
        elif task_type == TaskType.CODING:
            return (
                "START HERE — Your first actions should be:\n"
                "1. ACTION: open_app  PARAMS: {\"name\": \"code\"}\n"
                "   (or use terminal: ACTION: run_command  PARAMS: {\"command\": \"...\"})\n"
                "2. Create or open your project files\n"
                "3. Write actual code — not placeholder stubs"
            )
        elif task_type == TaskType.WRITING:
            return (
                "START HERE — For large documents use write_file (FASTEST, no UI lag):\n"
                "  OPTION A — Direct file write (PREFERRED for long content):\n"
                "    ACTION: write_file PARAMS: {\"filename\": \"report.md\", \"content\": \"[your full text]\"}\n"
                "    Then open: ACTION: open_app PARAMS: {\"name\": \"notepad report.md\"}\n"
                "  OPTION B — Type directly into Notepad (for short content only):\n"
                "    1. ACTION: open_app  PARAMS: {\"name\": \"notepad\"}\n"
                "    2. ACTION: wait      PARAMS: {\"seconds\": 2}\n"
                "    3. ACTION: click     PARAMS: {\"x\": 400, \"y\": 400}\n"
                "    4. ACTION: type_text_fast PARAMS: {\"text\": \"[section content]\"}\n"
                "   ★ If using Notepad: write ONE SECTION per type_text_fast call (400-600 words max)\n"
                "   ★ NEVER put entire report in a single LLM response — write section by section\n"
                "   ★ write_file is INSTANT — use it for any content over 300 words"
            )
        elif task_type == TaskType.BROWSING:
            return (
                "START HERE:\n"
                f"1. ACTION: open_app  PARAMS: {{\"name\": \"{_BROWSER}\"}}\n"
                "2. ACTION: wait      PARAMS: {\"seconds\": 2}\n"
                "3. Use Ctrl+L to focus address bar, then navigate"
            )
        return "Examine the screen, decide which app you need, and open it."


# ─── Task Strategy Templates ──────────────────────────────────────────
# Now imported from core.prompts (TASK_STRATEGY_PROMPTS, BROWSER_GUIDE,
# COMPLETION_RULES, WINDOWS_APP_INTELLIGENCE, OGENTI_KEYWORDS,
# _is_ogenti_screen).


# ─── Coordinate Grid Overlay ───────────────────────────────────────────
def _generate_grid_description(width: int, height: int, cols: int = 12, rows: int = 8) -> str:
    """
    Generate a text description of screen grid zones so the LLM can reason
    about approximate positions even before identifying pixel coordinates.
    Also includes relative (0-1) coordinates for resolution independence.
    """
    cell_w = width // cols
    cell_h = height // rows
    lines = [f"Screen: {width}x{height}px. Grid ({cols}×{rows}):"]
    for r in range(rows):
        for c in range(cols):
            cx = c * cell_w + cell_w // 2
            cy = r * cell_h + cell_h // 2
            rel_x = round(cx / width, 3)
            rel_y = round(cy / height, 3)
            label = f"{chr(65+r)}{c+1}"  # A1, A2, ..., H12
            lines.append(f"  {label}: center=({cx},{cy}) rel=({rel_x},{rel_y})")
    return "\n".join(lines)


class ExecutionEngine:
    def __init__(
        self,
        backend_url: str,
        os_controller: OSController,
        screenshot: ScreenshotCapture,
        plugin_loader: PluginLoader,
    ):
        self.backend_url = backend_url
        self.os_controller = os_controller
        self.screenshot = screenshot
        self.plugin_loader = plugin_loader
        self._paused_sessions: set[str] = set()
        self._cancelled_sessions: set[str] = set()
        self._session_screenshot_interval_s: dict[str, float] = {}
        self._last_screenshot_sent_ts: dict[str, float] = {}
        self._session_metrics: dict[str, dict] = {}
        self._session_outcomes: dict[str, dict] = {}
        self._session_action_logs: dict[str, list[dict]] = {}  # action_history per session
        self._http_client = httpx.AsyncClient(timeout=30.0)
        # Vision engine for change detection
        self._vision = VisionEngine(quality=92, max_width=1920) if HAS_VISION else None
        # SoM engine for numbered element overlay
        self._som = SoMEngine(quality=92, max_width=1920) if HAS_SOM else None
        self._semantic_som = SemanticSoMEngine() if HAS_SEMANTIC_SOM else None
        # Windows UI Automation engine for accurate element detection
        self._uia = UIAutomationEngine(max_elements=50) if HAS_UIA and UIAutomationEngine else None

    def _metric_inc(self, session_id: str, key: str, delta: int = 1):
        metrics = self._session_metrics.setdefault(session_id, {})
        metrics[key] = int(metrics.get(key, 0) or 0) + int(delta)

    def _metric_set(self, session_id: str, key: str, value):
        metrics = self._session_metrics.setdefault(session_id, {})
        metrics[key] = value

    def record_action_result(self, session_id: str, action_type: str, result: dict):
        """Record OS action result for metrics (callable from plugin context)."""
        try:
            self._metric_inc(session_id, "actions_total", 1)
            success = result.get("success", False) if isinstance(result, dict) else True
            if not success:
                self._metric_inc(session_id, "actions_failed", 1)
            if action_type == "run_command" and isinstance(result, dict):
                rc = result.get("returncode")
                if rc is not None and int(rc) != 0:
                    self._metric_inc(session_id, "run_command_nonzero", 1)
        except Exception:
            pass

    @staticmethod
    def _semantic_som_config_from_runtime(config: dict) -> "SemanticSoMConfig | None":
        if not HAS_SEMANTIC_SOM or SemanticSoMConfig is None:
            return None
        enabled = bool(config.get("semanticSomEnabled", False))
        max_elements = int(config.get("semanticSomMaxElements", 40) or 40)
        cooldown_s = float(config.get("semanticSomCooldownS", 2.0) or 2.0)
        cache_ttl_s = float(config.get("semanticSomCacheTtlS", 15.0) or 15.0)
        return SemanticSoMConfig(
            enabled=enabled,
            max_elements=max(5, min(80, max_elements)),
            cooldown_s=max(0.0, cooldown_s),
            cache_ttl_s=max(0.0, cache_ttl_s),
        )

    @staticmethod
    def _llm_supports_vision(llm_config: dict) -> bool:
        provider = (llm_config.get("provider") or "").upper().strip()
        if provider in ("OPENAI", "ANTHROPIC", "GOOGLE"):
            return True
        if provider in ("MISTRAL", "LOCAL"):
            return False
        if provider == "CUSTOM":
            # Assume OpenAI-compatible unless caller explicitly disables.
            return bool(llm_config.get("vision", True))
        return False

    @staticmethod
    def _task_requires_vision(prompt: str) -> bool:
        try:
            detected = TaskAnalyzer.detect(prompt)
            return detected in (
                TaskType.RESEARCH,
                TaskType.BROWSING,
                TaskType.DESIGN,
                TaskType.WRITING,
                TaskType.AUTOMATION,
            )
        except Exception:
            # Conservative default: assume vision required for unknown prompts.
            return True

    async def callback(self, session_id: str, event_type: str, data: dict):
        """Send callback to backend."""
        try:
            url = f"{self.backend_url}/api/execution/callback"
            payload = {
                "sessionId": session_id,
                "type": event_type,
                **data,
            }
            resp = await self._http_client.post(
                url,
                json=payload,
                headers=_get_auth_headers(),
            )
            if resp.status_code != 200:
                logger.warning(f"Callback failed: {resp.status_code} - {resp.text}")
        except Exception as e:
            logger.error(f"Callback error: {e}")

    async def log(self, session_id: str, message: str, level: str = "INFO",
                  log_type: str = "SYSTEM", agent_id: Optional[str] = None):
        """Send log entry to backend."""
        await self.callback(session_id, "log", {
            "level": level,
            "logType": log_type,
            "message": message,
            "agentId": agent_id,
        })

    async def send_screenshot(self, session_id: str, force: bool = False, cached_image: bytes = None):
        """Capture and send screenshot to backend. Uses cached_image if provided."""
        try:
            interval_s = float(self._session_screenshot_interval_s.get(session_id, 0.0) or 0.0)
            if not force and interval_s > 0:
                last_ts = self._last_screenshot_sent_ts.get(session_id, 0.0)
                if time.time() - last_ts < interval_s:
                    return
            img_bytes = cached_image or self.screenshot.capture()
            if img_bytes:
                b64 = base64.b64encode(img_bytes).decode("utf-8")
                await self.callback(session_id, "screenshot", {
                    "screenshot": f"data:image/jpeg;base64,{b64}",
                })
                self._last_screenshot_sent_ts[session_id] = time.time()
        except Exception as e:
            logger.error(f"Screenshot error: {e}")

    async def update_agent_status(self, session_id: str, agent_id: str, status: str):
        """Update agent status in backend."""
        await self.callback(session_id, "agent_status", {
            "agentId": agent_id,
            "status": status,
        })

    def pause_session(self, session_id: str):
        self._paused_sessions.add(session_id)

    def resume_session(self, session_id: str):
        self._paused_sessions.discard(session_id)

    def cancel_session(self, session_id: str):
        self._cancelled_sessions.add(session_id)

    def _is_paused(self, session_id: str) -> bool:
        return session_id in self._paused_sessions

    def _is_cancelled(self, session_id: str) -> bool:
        return session_id in self._cancelled_sessions

    # ─── Wait for UI to settle ──────────────────────────────────────────
    async def _wait_for_ui_settle(self, max_wait: float = 2.0):
        """Wait until the screen stops changing, up to max_wait seconds."""
        if not self._vision:
            await asyncio.sleep(0.5)
            return
        start = time.time()
        await asyncio.sleep(0.2)
        while time.time() - start < max_wait:
            diff = self._vision.detect_changes()
            if not diff.get("is_significant", True):
                return
            await asyncio.sleep(0.25)

    async def run_session(
        self,
        session_id: str,
        prompt: str,
        agents: list[dict],
        llm_config: dict,
        config: dict,
    ):
        """Main execution loop for a session.
        
        If multiple agents are selected and collaboration engine is available,
        runs in collaborative mode where agents communicate and work together
        on the same screen. Otherwise falls back to sequential execution.
        """
        start_time = time.time()
        
        try:
            await self.log(session_id, "Execution session started")
            await self.log(session_id, f"Prompt: {prompt}")
            await self.log(session_id, f"Agents: {len(agents)}")

            # Init metrics for this session
            self._session_metrics[session_id] = {
                "plugin_hit": 0,
                "plugin_miss": 0,
                "no_action_turns": 0,
                "element_resolution_fail": 0,
                "actions_total": 0,
                "actions_failed": 0,
                "run_command_nonzero": 0,
            }

            # Apply per-session screenshot throttling (ms -> seconds)
            try:
                interval_ms = config.get("screenshotInterval", 0) or 0
                self._session_screenshot_interval_s[session_id] = max(0.0, float(interval_ms) / 1000.0)
            except Exception:
                self._session_screenshot_interval_s[session_id] = 0.0

            # Capability gate: vision-required tasks must use a vision-capable provider/model
            require_vision = bool(config.get("requireVision", False)) or self._task_requires_vision(prompt)
            supports_vision = self._llm_supports_vision(llm_config)
            if require_vision and not supports_vision:
                msg = (
                    f"Vision capability required for this task, but provider='{llm_config.get('provider')}' "
                    f"model='{llm_config.get('model')}' does not support screenshots. "
                    f"Switch to a vision-capable provider/model."
                )
                await self.log(session_id, msg, "ERROR")
                await self.callback(session_id, "error", {"message": msg})
                return

            # Initialize LLM client
            llm = create_llm_client(llm_config)
            await self.log(session_id, f"LLM initialized: {llm_config.get('provider', 'unknown')} / {llm_config.get('model', 'unknown')}")

            # Build per-agent LLM map (different brain per agent if configured)
            agent_llm_map: dict[str, LLMClient] = {}
            for agent_data in agents:
                agent_id = agent_data.get("id", "unknown")
                agent_llm_config = agent_data.get("llm_config")
                if agent_llm_config and agent_llm_config.get("provider"):
                    try:
                        agent_llm = create_llm_client(agent_llm_config)
                        agent_llm_map[agent_id] = agent_llm
                        await self.log(
                            session_id,
                            f"Agent {agent_data.get('name', agent_id)} → dedicated LLM: "
                            f"{agent_llm_config['provider']} / {agent_llm_config['model']}",
                        )
                    except Exception as e:
                        await self.log(session_id, f"Failed to init per-agent LLM for {agent_id}: {e}. Using default.", "WARN")

            multi_brain = len(agent_llm_map) > 0
            if multi_brain:
                await self.log(session_id, f"Multi-brain mode: {len(agent_llm_map)} agents with dedicated LLMs")

            # Send initial screenshot
            await self.send_screenshot(session_id, force=True)

            # ── COLLABORATIVE MODE: multiple agents work together ──
            use_collab = HAS_COLLAB and len(agents) > 1 and config.get("collaborative", True)
            
            if use_collab:
                await self.log(session_id, "═══ Collaborative mode activated ═══")
                collab_session = CollaborativeSession(
                    session_id=session_id,
                    engine=self,
                    llm=llm,
                    agent_llm_map=agent_llm_map,
                )
                await collab_session.run_collaborative(prompt, agents, config)
            else:
                # ── SEQUENTIAL MODE: agents execute one by one ──
                max_time = config.get("maxExecutionTime", 600000) / 1000
                if max_time and max_time > 0:
                    try:
                        await asyncio.wait_for(
                            self._run_sequential(session_id, prompt, agents, llm, config, agent_llm_map),
                            timeout=max_time,
                        )
                    except asyncio.TimeoutError:
                        await self.log(session_id, "Sequential execution timeout reached", "WARN")
                else:
                    await self._run_sequential(session_id, prompt, agents, llm, config, agent_llm_map)

            # Complete
            elapsed = time.time() - start_time
            was_cancelled = self._is_cancelled(session_id)
            if was_cancelled:
                await self.log(session_id, f"Session cancelled after {elapsed:.1f}s", "WARN")
                await self.callback(session_id, "error", {"message": "Session cancelled"})
                action_logs = self._session_action_logs.pop(session_id, [])
                self._session_outcomes[session_id] = {
                    "status": "CANCELLED",
                    "duration": round(elapsed, 1),
                    "agentsRun": len(agents),
                    "metrics": dict(self._session_metrics.get(session_id) or {}),
                    "action_logs": action_logs,
                }
                raise asyncio.CancelledError()
            else:
                await self.log(session_id, f"Session completed in {elapsed:.1f}s")
                await self.send_screenshot(session_id, force=True)
                metrics = dict(self._session_metrics.get(session_id) or {})
                action_logs = self._session_action_logs.pop(session_id, [])
                self._session_outcomes[session_id] = {
                    "status": "COMPLETED",
                    "duration": round(elapsed, 1),
                    "agentsRun": len(agents),
                    "mode": "collaborative" if use_collab else "sequential",
                    "metrics": metrics,
                    "action_logs": action_logs,
                }
                await self.callback(session_id, "complete", {
                    "result": {
                        "duration": elapsed,
                        "agentsRun": len(agents),
                        "mode": "collaborative" if use_collab else "sequential",
                    },
                })

        except asyncio.CancelledError:
            if session_id not in self._session_outcomes:
                action_logs = self._session_action_logs.pop(session_id, [])
                self._session_outcomes[session_id] = {
                    "status": "CANCELLED",
                    "duration": round(time.time() - start_time, 1),
                    "agentsRun": len(agents),
                    "metrics": dict(self._session_metrics.get(session_id) or {}),
                    "action_logs": action_logs,
                }
            await self.log(session_id, "Session cancelled", "WARN")
            await self.callback(session_id, "error", {"message": "Session cancelled"})
            raise  # Propagate so caller knows it was cancelled
        except Exception as e:
            logger.error(f"Session {session_id} failed: {e}")
            action_logs = self._session_action_logs.pop(session_id, [])
            self._session_outcomes[session_id] = {
                "status": "FAILED",
                "duration": round(time.time() - start_time, 1),
                "agentsRun": len(agents),
                "error": str(e),
                "metrics": dict(self._session_metrics.get(session_id) or {}),
                "action_logs": action_logs,
            }
            await self.log(session_id, f"Session error: {e}", "ERROR")
            await self.callback(session_id, "error", {"message": str(e)})
        finally:
            self._paused_sessions.discard(session_id)
            self._cancelled_sessions.discard(session_id)
            self._session_screenshot_interval_s.pop(session_id, None)
            self._last_screenshot_sent_ts.pop(session_id, None)

            # Emit metrics (best effort)
            try:
                metrics = self._session_metrics.get(session_id) or {}
                metrics = {**metrics, "duration_s": round(time.time() - start_time, 3)}
                await self.callback(session_id, "log", {
                    "level": "INFO",
                    "logType": "METRIC",
                    "message": "session_metrics",
                    "data": metrics,
                    "agentId": "system",
                })
            except Exception:
                pass
            self._session_metrics.pop(session_id, None)

    def get_session_outcome(self, session_id: str) -> dict | None:
        """Return and consume the session outcome (status, duration, metrics)."""
        return self._session_outcomes.pop(session_id, None)

    async def _run_sequential(
        self,
        session_id: str,
        prompt: str,
        agents: list[dict],
        llm: LLMClient,
        config: dict,
        agent_llm_map: dict[str, LLMClient] | None = None,
    ):
        """Sequential execution: each agent runs with its own LLM brain."""
        agent_llm_map = agent_llm_map or {}

        for agent_data in agents:
            agent_id = agent_data.get("id", "unknown")
            agent_name = agent_data.get("name", "Unknown Agent")
            agent_slug = agent_data.get("slug", "")

            # Resolve per-agent LLM: agent's dedicated LLM → session default
            agent_llm = agent_llm_map.get(agent_id, llm)
            
            if self._is_cancelled(session_id):
                await self.log(session_id, "Session cancelled by user", "WARN")
                break

            await self.update_agent_status(session_id, agent_id, "RUNNING")
            await self.log(session_id, f"Starting agent: {agent_name}", agent_id=agent_id)

            try:
                plugin = self.plugin_loader.get_plugin(agent_slug or agent_name.lower().replace(" ", "_"))
                
                # Resolve user's custom persona
                user_persona = agent_data.get("persona") or ""
                persona_prompt = prompt
                if user_persona and plugin:
                    # For plugin agents, inject persona into the prompt itself
                    persona_prompt = f"[PERSONA INSTRUCTIONS: {user_persona}]\n\n{prompt}"
                
                if plugin:
                    self._metric_inc(session_id, "plugin_hit", 1)
                    await self.log(session_id, f"Plugin loaded: {plugin.name}", "DEBUG", "AGENT", agent_id)
                    await self._run_plugin_agent(
                        session_id, agent_id, agent_name,
                        plugin, persona_prompt, agent_llm, config,
                        registry_slug=agent_slug,
                    )
                else:
                    self._metric_inc(session_id, "plugin_miss", 1)
                    await self.log(session_id, f"No specific plugin found, using generic agent", "DEBUG", "SYSTEM", agent_id)
                    await self._run_generic_agent(
                        session_id, agent_id, agent_name,
                        prompt, agent_llm, agent_data, config
                    )
                
                await self.update_agent_status(session_id, agent_id, "COMPLETED")
                await self.log(session_id, f"Agent completed: {agent_name}", "INFO", "AGENT", agent_id)

            except asyncio.CancelledError:
                await self.update_agent_status(session_id, agent_id, "CANCELLED")
                raise
            except Exception as e:
                logger.error(f"Agent {agent_name} error: {e}")
                await self.update_agent_status(session_id, agent_id, "FAILED")
                await self.log(session_id, f"Agent failed: {e}", "ERROR", "AGENT", agent_id)

    async def _run_plugin_agent(
        self, session_id: str, agent_id: str, agent_name: str,
        plugin, prompt: str, llm: LLMClient, config: dict,
        registry_slug: str = "",
    ):
        """Run a specific plugin agent with tier-aware context."""
        # Prefer the backend/marketplace slug (e.g. "apex-researcher") over
        # the plugin's internal slug (e.g. "research_agent") because the
        # AGENT_REGISTRY is keyed by marketplace slug.
        agent_slug = registry_slug or getattr(plugin, 'slug', agent_name.lower().replace(" ", "_"))
        profile = get_agent_profile(agent_slug) if HAS_REGISTRY else None
        tier_config_obj = get_agent_tier_config(agent_slug) if HAS_REGISTRY else None
        
        # SoM access depends on tier
        som = self._som if (not tier_config_obj or tier_config_obj.som_enabled) else None
        
        context = AgentContext(
            session_id=session_id,
            agent_id=agent_id,
            engine=self,
            llm=llm,
            os_controller=self.os_controller,
            screenshot=self.screenshot,
            som_engine=som,
            agent_profile=profile,
        )
        await plugin.execute(context, prompt, config)

    async def _run_generic_agent(
        self, session_id: str, agent_id: str, agent_name: str,
        prompt: str, llm: LLMClient, agent_data: dict, config: dict
    ):
        """
        Generic agent with "Think-Plan-Act-Verify" architecture.
        
        v4 — Smart Agent Architecture
        ==============================
        Core principle: THINK DEEPLY before every action, VERIFY thoroughly after.
        
        Intelligence improvements:
        - Chain-of-thought reasoning with structured mental model
        - Action history with success/failure tracking
        - Spatial memory: track known UI elements and their positions
        - Pre-action validation: check preconditions before acting
        - Smart error recovery with progressive strategy changes
        - SoM element list injected every turn (not just first)
        - Window state awareness: knows which app is foreground
        """
        # ── Tier enforcement: look up agent profile ──
        agent_slug = agent_data.get("slug", agent_name.lower().replace(" ", "_"))
        tier_config = None
        allowed_actions = None
        profile = None
        
        if HAS_REGISTRY:
            profile = get_agent_profile(agent_slug)
            tier_config = get_agent_tier_config(agent_slug)
            allowed_actions = get_agent_allowed_actions(agent_slug)
            await self.log(session_id, f"Tier: {profile.tier} | Domain: {profile.domain} | Actions: {len(allowed_actions)}", "INFO", "AGENT", agent_id)
        
        # Apply tier limits (fallback to config/defaults)
        if tier_config:
            max_steps = min(config.get("maxSteps", tier_config.max_steps), tier_config.max_steps)
            max_retries = tier_config.max_retries
            action_delay = tier_config.action_delay
            max_history = tier_config.max_message_history
            use_som = tier_config.som_enabled
            use_vision = tier_config.vision_enabled
        else:
            max_steps = config.get("maxSteps", 60)
            max_retries = 2
            action_delay = 0.5
            max_history = 40
            use_som = True
            use_vision = True
        
        if not allowed_actions:
            allowed_actions = self.VALID_ACTIONS  # Fallback to legacy full set
        step = 0
        consecutive_empty = 0
        retry_count = 0
        action_failure_streak = 0
        som_result = None   # latest SoM detection result
        
        # ── Intelligence state ──
        action_history: list[dict] = []  # Track all actions taken with results
        known_windows: dict[str, str] = {}  # window_title → status
        current_window: str = ""  # What window is currently in foreground
        task_progress: list[str] = []  # What subtasks have been accomplished
        strategies_tried: list[str] = []  # Failed strategies to avoid repeating
        
        # Generate grid reference for coordinate reasoning
        sw = self.os_controller.screen_width
        sh = self.os_controller.screen_height
        grid_desc = _generate_grid_description(sw, sh)
        
        # Detect LLM provider for prompt adaptation
        _llm_provider = getattr(llm, 'provider', 'UNKNOWN')
        
        system_prompt = self._build_system_prompt(agent_data, grid_desc, allowed_actions, profile, sw, sh, _llm_provider)
        
        # ── Task Intelligence: detect task type and inject strategy ──
        detected_task_type = TaskAnalyzer.detect(prompt)
        search_query = TaskAnalyzer.extract_search_query(prompt)
        recommended_apps = TaskAnalyzer.get_recommended_apps(detected_task_type)
        first_action_hint = TaskAnalyzer.get_first_action_hint(detected_task_type, search_query)
        task_strategy = TASK_STRATEGY_PROMPTS.get(detected_task_type, "")
        
        await self.log(session_id, f"Task analysis: type={detected_task_type.value}, query='{search_query}', apps={recommended_apps}", "INFO", "AGENT", agent_id)
        
        # ═══ INTELLIGENCE LAYER INITIALIZATION ═══
        # Map TaskType to intelligence module's task type string
        _task_type_map = {
            TaskType.RESEARCH: "research", TaskType.BROWSING: "browsing",
            TaskType.WRITING: "writing", TaskType.CODING: "coding",
            TaskType.AUTOMATION: "coding", TaskType.DATA_ANALYSIS: "research",
            TaskType.DESIGN: "writing", TaskType.GENERAL: "browsing",
        }
        intel_task_type = _task_type_map.get(detected_task_type, "browsing")
        
        # Initialize the three intelligence components
        progress_tracker = TaskProgressTracker(intel_task_type)
        context_accumulator = ContextAccumulator(intel_task_type, prompt)
        intel_action_history: list[dict] = []  # For SmartPromptBuilder
        
        await self.log(session_id, f"Intelligence layer initialized: tracker={intel_task_type}, phases={progress_tracker.get_total_phases()}", "INFO", "AGENT", agent_id)
        
        # Build the enriched initial prompt with CONCRETE task-specific guidance
        initial_parts = [f"TASK: {prompt}"]
        
        if task_strategy:
            initial_parts.append(f"\n{task_strategy}")
        
        initial_parts.append(f"\n{BROWSER_GUIDE}")
        initial_parts.append(f"\n{first_action_hint}")
        
        initial_parts.append(
            "\n\n⚠️ CRITICAL REMINDERS:\n"
            "• Do NOT open File Explorer for research tasks — open Chrome or Edge!\n"
            "• Do NOT create empty files with run_command — type actual content in an editor!\n"
            "• Do NOT say TASK_COMPLETE until you have ACTUALLY DONE the work!\n"
            "• If you don't know which element to click, describe what you see FIRST.\n"
            "• Follow the strategy above STEP BY STEP."
        )
        
        # Track actions used for completion verification
        actions_used_types: set[str] = set()
        has_typed_content = False
        total_actions_executed = 0
        
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "\n".join(initial_parts)},
        ]

        await self.log(session_id, f"Smart agent (task={detected_task_type.value}): max {max_steps} steps, delay {action_delay}s", "INFO", "AGENT", agent_id)

        # ═══ AUTO-START: Minimize Ogenti window so LLM sees the desktop ═══
        try:
            import pyautogui
            win = pyautogui.getActiveWindow()
            if win and ("ogenti" in (win.title or "").lower() or "agent" in (win.title or "").lower()):
                win.minimize()
                await asyncio.sleep(0.5)
                await self.log(session_id, "Ogenti window minimized — LLM now sees desktop", "INFO", "AGENT", agent_id)
        except Exception:
            pass

        _ogenti_consecutive = 0  # Track consecutive Ogenti detections
        
        while step < max_steps:
            step += 1
            
            if self._is_cancelled(session_id):
                break
            
            while self._is_paused(session_id):
                await asyncio.sleep(1)
                if self._is_cancelled(session_id):
                    return

            await self.log(session_id, f"Step {step}/{max_steps}", "DEBUG", "AGENT", agent_id)

            # ── Tier-based action delay ──
            if step > 1:
                await asyncio.sleep(action_delay)

            # ── PRE-LOOK: Aggressively minimize ALL Ogenti windows ──
            # Uses Win32 API to find and minimize every window with "ogenti" in title.
            # pyautogui.minimize() is unreliable; direct ShowWindow(SW_MINIMIZE) works.
            # Skip if we've already tried 3+ times — no point hammering it.
            _ogenti_minimized = False
            if _ogenti_consecutive < 3:
                try:
                    import ctypes
                    import ctypes.wintypes
                    _SW_MINIMIZE = 6
                    _ogenti_kws = ("ogenti", "agent marketplace", "agent runtime")
                    
                    def _enum_cb(hwnd, _):
                        nonlocal _ogenti_minimized
                        if not ctypes.windll.user32.IsWindowVisible(hwnd):
                            return True
                        length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
                        if length == 0:
                            return True
                        buf = ctypes.create_unicode_buffer(length + 1)
                        ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.lower()
                        if any(kw in title for kw in _ogenti_kws):
                            ctypes.windll.user32.ShowWindow(hwnd, _SW_MINIMIZE)
                            _ogenti_minimized = True
                        return True
                    
                    _WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                    ctypes.windll.user32.EnumWindows(_WNDENUMPROC(_enum_cb), 0)
                    
                    if _ogenti_minimized:
                        await asyncio.sleep(0.8)
                        await self.log(session_id, "Ogenti windows force-minimized (Win32)", "DEBUG", "AGENT", agent_id)
                except Exception:
                    pass

            # ── LOOK: Capture SoM-annotated screenshot (if tier allows) ──
            screen_b64 = None
            som_result = None
            som_desc = ""
            ocr_text = ""
            try:
                await self._wait_for_ui_settle(max_wait=1.5)
                # Prefer SoM capture (only if tier allows SoM)
                if use_som and self._som and self._som.enabled:
                    sr = self._som.capture_som()
                    if sr and sr.annotated_image:
                        som_result = sr
                        screen_b64 = base64.b64encode(sr.annotated_image).decode("utf-8")
                        som_desc = sr.description or ""
                # Fallback to raw screenshot (if vision enabled)
                if not screen_b64 and use_vision:
                    img_bytes = self.screenshot.capture()
                    if img_bytes:
                        screen_b64 = base64.b64encode(img_bytes).decode("utf-8")

                # Semantic SoM fallback (LLM-vision element detection)
                if (
                    use_vision
                    and screen_b64
                    and (not som_result)
                    and self._semantic_som
                    and HAS_SEMANTIC_SOM
                ):
                    sem_cfg = self._semantic_som_config_from_runtime(config)
                    if sem_cfg and sem_cfg.enabled:
                        try:
                            ssr = await self._semantic_som.capture_semantic_som(
                                llm, screen_b64, sem_cfg,
                                native_width=self.os_controller.screen_width,
                                native_height=self.os_controller.screen_height,
                            )
                            if ssr:
                                som_result = ssr
                                som_desc = ssr.description or som_desc
                        except Exception:
                            pass

                # Optional OCR channel (best effort)
                if use_vision and bool(config.get("ocrEnabled", False)) and self._vision:
                    try:
                        ocr_text = (self._vision.ocr_screen(max_chars=2500) or "").strip()
                    except Exception:
                        ocr_text = ""

                # ── Windows UI Automation: add accurate element detection ──
                uia_desc = ""
                if self._uia and self._uia.enabled:
                    try:
                        uia_elements = self._uia.detect_elements(sw, sh)
                        if uia_elements:
                            from core.ui_automation import uia_elements_to_som_description, _classify_som_type
                            uia_desc = uia_elements_to_som_description(uia_elements, sw, sh)
                            # Merge UIA elements into SoM result for cross-validation
                            if som_result:
                                from core.som_engine import SoMElement
                                next_id = max((el.id for el in som_result.elements), default=0) + 1
                                for ue in uia_elements:
                                    # Check if UIA element overlaps an existing SoM element
                                    overlaps = False
                                    for se in som_result.elements:
                                        dx = abs(ue.cx - se.cx)
                                        dy = abs(ue.cy - se.cy)
                                        if dx < 30 and dy < 30:
                                            overlaps = True
                                            break
                                    if not overlaps:
                                        som_el = SoMElement(
                                            id=next_id, x=ue.x, y=ue.y,
                                            w=ue.w, h=ue.h, cx=ue.cx, cy=ue.cy,
                                            type=_classify_som_type(ue.control_type),
                                            score=0.8,
                                        )
                                        som_result.elements.append(som_el)
                                        som_result.element_map[next_id] = som_el
                                        next_id += 1
                    except Exception as e:
                        logger.debug(f"UIA detection failed: {e}")

                # Use SoM raw image for frontend screenshot (avoids double capture)
                cached_raw = som_result.raw_image if (som_result and som_result.raw_image) else None
                await self.send_screenshot(session_id, cached_image=cached_raw)
            except Exception:
                pass

            # ═══════════════════════════════════════════════════════════════
            # INTELLIGENCE LAYER: Classify → Auto-Resolve → Smart Prompt
            # ═══════════════════════════════════════════════════════════════
            
            # Step A: Classify screen state PROGRAMMATICALLY
            active_window_hint = ""
            som_elements = []
            if som_result:
                active_window_hint = getattr(som_result, 'active_window', '') or ''
                som_elements = getattr(som_result, 'elements', []) or []
            if not active_window_hint:
                try:
                    import pyautogui
                    win = pyautogui.getActiveWindow()
                    if win:
                        active_window_hint = win.title or ""
                except Exception:
                    pass
            
            screen_analysis = ScreenStateClassifier.classify(
                som_desc, active_window_hint, som_elements
            )
            current_window = active_window_hint
            
            # ── If Ogenti is STILL visible after minimize, override state ──
            # This prevents any downstream code from looping on OGENTI_APP.
            if screen_analysis.state == ScreenState.OGENTI_APP:
                _ogenti_consecutive += 1
                if _ogenti_consecutive <= 2:
                    await self.log(session_id, f"Ogenti still visible after minimize (attempt {_ogenti_consecutive}/3) — treating as UNKNOWN", "WARN", "AGENT", agent_id)
                screen_analysis = ScreenAnalysis(
                    state=ScreenState.UNKNOWN,
                    confidence=0.3,
                    active_app="",
                )
                # Clear window hint so LLM doesn't see "ogenti" and try to interact
                active_window_hint = ""
                current_window = ""
            else:
                _ogenti_consecutive = 0  # Reset on non-Ogenti detection
            
            # Step B: Try AUTO-RESOLVE (bypass LLM entirely for trivial decisions)
            auto_result = AutoActionResolver.resolve(
                screen_analysis, 
                progress_tracker.state.current_phase.value,
                intel_task_type,
                action_history=intel_action_history,
            )
            
            # Step B2: If no auto-resolve, check STUCK DETECTOR
            if not auto_result:
                stuck_result = StuckDetector.check(
                    intel_action_history, screen_analysis.state,
                    intel_task_type, total_actions_executed
                )
                if stuck_result:
                    auto_result = stuck_result
                    await self.log(session_id, f"🚨 {stuck_result['reason']}", "WARN", "AGENT", agent_id)
            
            if auto_result:
                # Execute the auto-resolved action WITHOUT asking the LLM
                auto_action = auto_result["action"]
                auto_reason = auto_result["reason"]
                
                await self.log(session_id, f"🤖 {auto_reason}", "INFO", "AGENT", agent_id)
                
                auto_type = auto_action["type"]
                auto_params = auto_action.get("params", {})
                
                # Execute auto action
                auto_success = False
                auto_result_text = ""
                try:
                    result = self.os_controller.execute_action(auto_type, auto_params)
                    auto_result_text = json.dumps(result)[:200]
                    auto_success = result.get("success", True) if isinstance(result, dict) else True
                    try:
                        if isinstance(result, dict):
                            self.record_action_result(session_id, auto_type, result)
                    except Exception:
                        pass
                except Exception as e:
                    auto_result_text = f"FAILED: {e}"
                    auto_success = False
                
                # Record in both histories
                action_record = {
                    "step": step, "action": f"AUTO:{auto_type}({json.dumps(auto_params)[:60]})",
                    "success": auto_success, "result_brief": auto_result_text[:80],
                    "screen_state": screen_analysis.state.value,
                }
                action_history.append(action_record)
                intel_action_history.append(action_record)
                total_actions_executed += 1
                actions_used_types.add(auto_type)
                
                # Update intelligence tracker
                progress_tracker.update(auto_type, auto_params, auto_success, screen_analysis.state)
                
                # Add to messages so LLM knows what happened
                messages.append({"role": "user", "content": f"🤖 AUTO-RESOLVED: {auto_reason}\nResult: {auto_result_text[:120]}"})
                
                await asyncio.sleep(action_delay)
                continue  # Skip to next step — no LLM call needed
            
            # Step C: Build SMART context prompt (replaces the old verbose injection)
            if som_desc or screen_analysis.state != ScreenState.UNKNOWN:
                smart_prompt = SmartPromptBuilder.build_step_prompt(
                    screen_state=screen_analysis,
                    task_state=progress_tracker.state,
                    tracker=progress_tracker,
                    context=context_accumulator,
                    som_desc=som_desc,
                    action_history=intel_action_history,
                    last_action_result=action_history[-1].get("result_brief", "") if action_history else "",
                )

                if ocr_text:
                    smart_prompt += f"\n\n🧾 OCR TEXT (best-effort):\n{ocr_text}"
                
                # Append Windows UI Automation elements (accurate positions)
                if uia_desc:
                    smart_prompt += f"\n\n📐 ACCURATE ELEMENT POSITIONS (Windows UI Automation):\n{uia_desc}"
                
                # Also append accumulated knowledge if we have findings
                if context_accumulator.findings or context_accumulator.urls_visited:
                    smart_prompt += f"\n\n{context_accumulator.build_context_block()}"
                
                messages.append({"role": "user", "content": smart_prompt})
            else:
                # ═══ CRITICAL FIX: ALWAYS add a user message so screenshot is attached ═══
                # Without a user message as the last entry, the LLM client won't
                # attach the screenshot, and the agent flies completely blind.
                fallback_parts = [f"Step {step}: Observe the current screen and decide your next action."]
                if current_window:
                    fallback_parts.append(f"Active window: {current_window}")
                if action_history:
                    last = action_history[-1]
                    fallback_parts.append(f"Last action: {last.get('action', '?')} → {'OK' if last.get('success') else 'FAILED'}")
                messages.append({"role": "user", "content": "\n".join(fallback_parts)})

            # ── ASK LLM (with mandatory screen analysis) ──
            if not screen_b64:
                await self.log(session_id, "⚠️ No screenshot captured this turn — LLM has no visual input", "WARN", "AGENT", agent_id)
            try:
                llm_response = await llm.chat(
                    messages=messages,
                    screenshot_b64=screen_b64,
                )
            except Exception as e:
                await self.log(session_id, f"LLM error: {e}", "ERROR", "LLM", agent_id)
                if retry_count < max_retries:
                    retry_count += 1
                    await self.log(session_id, f"Retrying LLM call ({retry_count}/{max_retries})...", "WARN", "LLM", agent_id)
                    await asyncio.sleep(2)
                    continue
                break

            retry_count = 0

            assistant_msg = llm_response.get("content", "")
            messages.append({"role": "assistant", "content": assistant_msg})

            # ogent-1.0 token billing: report actual usage to backend
            if getattr(llm, "_ogent", False) and llm_response.get("_usage"):
                usage = llm_response["_usage"]
                asyncio.create_task(_report_ogent_tokens(
                    owner_id=getattr(llm, "_ogent_owner_id", ""),
                    mode="execute",
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    session_id=session_id,
                ))

            # ═══ LLM REFUSAL DETECTION: Catch "I'm sorry, I can't assist" ═══
            # Some LLMs refuse legitimate tasks due to overly aggressive content filters.
            # Detect this and retry with a rephrased prompt instead of stalling.
            _msg_lower = assistant_msg.strip().lower()
            _is_refusal = (
                ("i'm sorry" in _msg_lower or "i cannot" in _msg_lower or "i can't assist" in _msg_lower)
                and len(assistant_msg.strip()) < 200
                and "ACTION" not in assistant_msg
            )
            if _is_refusal:
                refusal_count = getattr(self, '_refusal_count', {})
                refusal_count[session_id] = refusal_count.get(session_id, 0) + 1
                self._refusal_count = refusal_count
                await self.log(session_id, f"LLM content-policy refusal detected (attempt {refusal_count[session_id]}), provider={_llm_provider}", "WARN", "LLM", agent_id)

                # Use provider-optimized recovery prompt (avoids re-triggering the same filter)
                recovery_msg = get_refusal_recovery_prompt(_llm_provider, prompt, refusal_count[session_id])
                if refusal_count[session_id] >= 3:
                    await self.log(session_id, "3x refusal — forcing screenshot + re-evaluation", "WARN", "AGENT", agent_id)
                    refusal_count[session_id] = 0
                messages.append({"role": "user", "content": recovery_msg})
                continue
            else:
                # Reset refusal counter on successful response
                if hasattr(self, '_refusal_count') and session_id in self._refusal_count:
                    self._refusal_count[session_id] = 0
            
            # ═══ THINKING VISIBILITY: Parse and log agent reasoning at INFO level ═══
            # This lets the user SEE what the agent is thinking in real-time.
            self._log_agent_thinking(session_id, agent_id, assistant_msg)

            # Extract progress notes from LLM response
            for line in assistant_msg.split("\n"):
                clean = line.strip().replace("**", "").strip()
                if clean.startswith("PROGRESS:"):
                    note = clean.split("PROGRESS:", 1)[1].strip()
                    if note and note not in task_progress:
                        task_progress.append(note)

            # Parse actions from LLM response (filtered by tier+domain)
            actions = self._parse_actions(assistant_msg, allowed_actions)
            
            if not actions:
                try:
                    self._metric_inc(session_id, "no_action_turns", 1)
                except Exception:
                    pass
                await self.log(session_id, f"No actions parsed from LLM response (preview: {assistant_msg[:100]}...)", "WARN", "AGENT", agent_id)
                if "DONE" in assistant_msg.upper() or "COMPLETE" in assistant_msg.upper() or "TASK_COMPLETE" in assistant_msg.upper():
                    # ── Completion Verification: did the agent ACTUALLY do the work? ──
                    rules = COMPLETION_RULES.get(detected_task_type, COMPLETION_RULES[TaskType.GENERAL])
                    is_verified = True
                    rejection_reasons = []
                    
                    if total_actions_executed < rules["min_actions"]:
                        is_verified = False
                        rejection_reasons.append(f"Only {total_actions_executed} actions executed (minimum: {rules['min_actions']})")
                    
                    if rules["required_action_types"] and not rules["required_action_types"].issubset(actions_used_types):
                        missing = rules["required_action_types"] - actions_used_types
                        is_verified = False
                        rejection_reasons.append(f"Missing required actions: {missing}")
                    
                    if rules.get("must_have_typed") and not has_typed_content:
                        is_verified = False
                        rejection_reasons.append("No text content was typed (must use type_text)")
                    
                    # ── Intelligence Layer: additional tracker-based verification ──
                    tracker_ok, tracker_reason = progress_tracker.can_complete()
                    if not tracker_ok:
                        is_verified = False
                        rejection_reasons.append(f"Tracker: {tracker_reason}")
                    
                    if is_verified:
                        await self.log(session_id, "Agent reports task complete (verified)", "INFO", "AGENT", agent_id)
                        break
                    else:
                        await self.log(session_id, f"Completion REJECTED: {'; '.join(rejection_reasons)}", "WARN", "AGENT", agent_id)
                        rejection_msg = rules.get("rejection", "")
                        if rejection_msg:
                            messages.append({"role": "user", "content": rejection_msg + f"\n\nDetails: {'; '.join(rejection_reasons)}"})
                        else:
                            messages.append({"role": "user", "content": f"⚠️ TASK_COMPLETE REJECTED: {'; '.join(rejection_reasons)}\nContinue working."})
                        continue
                
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    await self.log(session_id, "No actions for 3 turns — wrapping up", "WARN", "AGENT", agent_id)
                    break
                
                messages.append({"role": "user", "content": (
                    "⚠ NO ACTION DETECTED in your response.\n\n"
                    "You MUST follow this exact format:\n"
                    "1. Look at the screenshot — what elements do you see? List them with their numbers [1], [2], etc.\n"
                    "2. What is the CURRENT STATE? Which app is open? What window is focused?\n"
                    "3. What is the NEXT CONCRETE STEP toward completing the task?\n"
                    "4. Write your ACTION and PARAMS.\n\n"
                    "Example:\n"
                    "**OBSERVATION**: I see Chrome browser open with Google search. Search bar [3] is visible at top.\n"
                    "**THINKING**: I need to search for 'OpenAI'. The search bar [3] is the target.\n"
                    "**ACTION**: click_element\n"
                    "**PARAMS**: {\"id\": 3}"
                )})
                continue

            consecutive_empty = 0

            # ── ACT: Execute actions with verification ──
            for action in actions:
                if self._is_cancelled(session_id):
                    break
                    
                action_type = action.get("type", "")
                action_params = action.get("params", {})

                # ── SoM Resolution: convert click_element → click with real coords ──
                if action_type.endswith("_element"):
                    if som_result:
                        element_id = action_params.get("id")
                        if element_id is not None:
                            el = som_result.element_map.get(int(element_id))
                            if el:
                                base_type = action_type.replace("_element", "")
                                await self.log(session_id, f"SoM: element #{element_id} → ({el.cx},{el.cy})", "DEBUG", "AGENT", agent_id)
                                action_type = base_type
                                action_params = {"x": el.cx, "y": el.cy, "_from_som": True}
                            else:
                                await self.log(session_id, f"SoM: element #{element_id} not found — trying auto-scroll recovery", "WARN", "AGENT", agent_id)
                                recovered = False
                                for scroll_attempt in range(3):
                                    try:
                                        self.os_controller.execute_action("scroll", {"clicks": -5})
                                        await self._wait_for_ui_settle(max_wait=1.0)
                                        if use_som and self._som and self._som.enabled:
                                            retry_som = self._som.capture_som()
                                            if retry_som and retry_som.element_map:
                                                retry_el = retry_som.element_map.get(int(element_id))
                                                if retry_el:
                                                    som_result = retry_som
                                                    action_type = action_type.replace("_element", "")
                                                    action_params = {"x": retry_el.cx, "y": retry_el.cy, "_from_som": True}
                                                    await self.log(session_id, f"SoM: element #{element_id} found after scroll #{scroll_attempt + 1} → ({retry_el.cx},{retry_el.cy})", "INFO", "AGENT", agent_id)
                                                    recovered = True
                                                    break
                                    except Exception:
                                        pass
                                if not recovered:
                                    strategies_tried.append(f"click_element #{element_id} — element not found on screen")
                                    try:
                                        self._metric_inc(session_id, "element_resolution_fail", 1)
                                    except Exception:
                                        pass
                                    if "x" not in action_params and "y" not in action_params and "rel_x" not in action_params and "rel_y" not in action_params:
                                        messages.append({"role": "user", "content": f"⚠ Could not resolve element id={element_id} to coordinates (tried scrolling 3 times). Re-observe the screen and pick a different element id (or use coordinate-based click)."})
                                        continue
                                    action_type = action_type.replace("_element", "")
                    else:
                        await self.log(session_id, f"SoM unavailable, '{action_type}' falling back to base action", "WARN", "AGENT", agent_id)
                        if "id" in action_params and "x" not in action_params and "y" not in action_params and "rel_x" not in action_params and "rel_y" not in action_params:
                            try:
                                self._metric_inc(session_id, "element_resolution_fail", 1)
                            except Exception:
                                pass
                            messages.append({"role": "user", "content": f"⚠ SoM is unavailable, so element id={action_params.get('id')} cannot be clicked. Re-observe or use coordinate-based click."})
                            continue
                        action_type = action_type.replace("_element", "")
                
                await self.log(session_id, f"Action: {action_type} {json.dumps(action_params)[:100]}", "INFO", "OS_ACTION", agent_id)

                # ── COORDINATE CROSS-VALIDATION: snap raw coords to nearest SoM element ──
                if (
                    action_type in ("click", "double_click", "right_click")
                    and "x" in action_params and "y" in action_params
                    and som_result and som_result.elements
                ):
                    try:
                        click_x = int(action_params["x"])
                        click_y = int(action_params["y"])
                        # Find nearest SoM element center
                        best_el = None
                        best_dist = float("inf")
                        for el in som_result.elements:
                            dx = click_x - el.cx
                            dy = click_y - el.cy
                            dist = (dx * dx + dy * dy) ** 0.5
                            if dist < best_dist:
                                best_dist = dist
                                best_el = el
                        # If within 50px of a SoM element center, snap to it
                        # This corrects LLM coordinate estimation errors
                        # BUT: skip snapping to large blob elements (area > 40000px²)
                        # because their centers are in the middle of text blocks, not on
                        # any specific clickable target.
                        if best_el and best_dist <= 50 and (best_el.w * best_el.h) < 40000:
                            old_x, old_y = click_x, click_y
                            action_params["x"] = best_el.cx
                            action_params["y"] = best_el.cy
                            if best_dist > 5:  # Only log if actually snapping
                                await self.log(
                                    session_id,
                                    f"📐 Coord snap: ({old_x},{old_y}) → element #{best_el.id} ({best_el.cx},{best_el.cy}) dist={best_dist:.0f}px",
                                    "DEBUG", "AGENT", agent_id
                                )
                    except (TypeError, ValueError):
                        pass

                # ── Tier enforcement: block disallowed actions ──
                base_action = action_type.replace("_element", "") if action_type.endswith("_element") else action_type
                if allowed_actions and base_action not in allowed_actions and action_type not in allowed_actions:
                    await self.log(session_id, f"⛔ BLOCKED: '{action_type}' not allowed for this agent's tier/domain", "WARN", "AGENT", agent_id)
                    messages.append({"role": "user", "content": f"⚠ '{action_type}' is NOT available to you. You can only use: {', '.join(sorted(allowed_actions))}. Use a different approach."})
                    continue

                # ── INTELLIGENCE: Validate action before execution ──
                validation = ActionValidator.validate(
                    action_type, action_params, screen_analysis,
                    intel_task_type, intel_action_history,
                    screen_width=sw, screen_height=sh,
                )
                if validation:
                    if validation.get("block"):
                        await self.log(session_id, f"🛡️ {validation['reason']}", "WARN", "AGENT", agent_id)
                        messages.append({"role": "user", "content": f"⚠ ACTION BLOCKED: {validation['reason']}\nTry a different action."})
                        continue
                    elif validation.get("fix"):
                        fixed = validation["action"]
                        await self.log(session_id, f"🔧 {validation['reason']} → {fixed['type']}", "INFO", "AGENT", agent_id)
                        action_type = fixed["type"]
                        action_params = fixed.get("params", {})

                pre_action_hash = hashlib.md5((screen_b64 or "").encode("utf-8", errors="ignore")).hexdigest() if screen_b64 else None

                action_success = False
                action_result_text = ""
                for attempt in range(max_retries + 1):
                    try:
                        result = self.os_controller.execute_action(action_type, action_params)
                        action_result_text = json.dumps(result)[:200]
                        action_success = result.get("success", True) if isinstance(result, dict) else True
                        try:
                            if isinstance(result, dict):
                                self.record_action_result(session_id, action_type, result)
                        except Exception:
                            pass
                        break
                    except Exception as e:
                        action_result_text = f"FAILED: {e}"
                        action_success = False
                        if attempt < max_retries:
                            await self.log(session_id, f"Action failed, retrying ({attempt + 1}/{max_retries})...", "WARN", "OS_ACTION", agent_id)
                            await asyncio.sleep(1)
                        else:
                            await self.log(session_id, action_result_text, "ERROR", "OS_ACTION", agent_id)

                # ── Record in action history ──
                action_record = {
                    "step": step,
                    "action": f"{action_type}({json.dumps(action_params)[:60]})",
                    "success": action_success,
                    "result_brief": action_result_text[:80],
                    "screen_state": screen_analysis.state.value,
                }
                action_history.append(action_record)
                intel_action_history.append(action_record)
                
                # ── Track for completion verification ──
                total_actions_executed += 1
                actions_used_types.add(action_type)
                if action_type in ("type_text", "type_text_fast") and action_params.get("text", "").strip():
                    text_len = len(action_params.get("text", ""))
                    if text_len > 10:  # More than trivial text
                        has_typed_content = True
                        # Update context accumulator with typed content
                        context_accumulator.update_content_summary(action_params.get("text", ""))
                if action_type == "write_file":
                    content = action_params.get("content", action_params.get("text", ""))
                    if len(content) > 10:
                        has_typed_content = True
                        context_accumulator.update_content_summary(content)
                
                # Track URLs in context accumulator and progress tracker
                if action_type in ("type_text", "type_text_fast"):
                    typed = action_params.get("text", "")
                    if typed.startswith("http") or "google.com" in typed:
                        context_accumulator.add_url(typed[:200])
                        progress_tracker.add_url(typed[:200])
                
                # Track window state
                if action_type in ("open_app", "focus_window"):
                    win = action_params.get("name") or action_params.get("title", "")
                    if win:
                        current_window = win
                        known_windows[win] = "opened"

                # ── UPDATE INTELLIGENCE TRACKER ──
                progress_tracker.update(
                    action_type, action_params, action_success, screen_analysis.state
                )
                
                # Extract findings from LLM responses for context accumulator
                for line in assistant_msg.split("\n"):
                    clean = line.strip()
                    if clean.upper().startswith("FINDING:"):
                        finding = clean.split(":", 1)[1].strip()
                        context_accumulator.add_finding(finding)
                        progress_tracker.add_finding(finding)

                # ── VERIFY: Wait for UI to settle, capture new SoM screenshot ──
                await self._wait_for_ui_settle(max_wait=1.5)
                
                verify_b64 = None
                verify_som_desc = ""
                try:
                    # Use SoM for verification screenshot too
                    if use_som and self._som and self._som.enabled:
                        vsr = self._som.capture_som()
                        if vsr and vsr.annotated_image:
                            som_result = vsr  # update for next iteration
                            verify_b64 = base64.b64encode(vsr.annotated_image).decode("utf-8")
                            verify_som_desc = vsr.description or ""
                    if not verify_b64:
                        verify_img = self.screenshot.capture()
                        if verify_img:
                            verify_b64 = base64.b64encode(verify_img).decode("utf-8")
                    await self.send_screenshot(session_id)
                except Exception:
                    pass

                screen_unchanged = False
                if pre_action_hash and verify_b64 and action_type in ("click", "click_element", "hotkey", "press_key", "scroll"):
                    post_hash = hashlib.md5(verify_b64.encode("utf-8", errors="ignore")).hexdigest()
                    if pre_action_hash == post_hash:
                        screen_unchanged = True
                        await self.log(session_id, f"Screen unchanged after {action_type} — possible miss", "WARN", "AGENT", agent_id)

                # ── Build intelligent verification prompt ──
                if action_success:
                    action_failure_streak = 0
                    
                    # Build action-specific smart guidance
                    verify_parts = [
                        f"✓ Action succeeded: {action_type}({json.dumps(action_params)[:80]}) → {action_result_text[:120]}",
                        "",
                    ]
                    
                    if screen_unchanged:
                        verify_parts.append("⚠ SCREEN DID NOT CHANGE after this action. The click/key may have missed its target. Consider:")
                        verify_parts.append("  - Re-examining the screen to find the correct target")
                        verify_parts.append("  - Scrolling to reveal the element if it is off-screen")
                        verify_parts.append("  - Using different coordinates or a different element ID")
                    
                    if verify_som_desc:
                        verify_parts.append(f"📍 UPDATED SCREEN ELEMENTS:\n{verify_som_desc}")
                    
                    # Context-aware next-step guidance based on what action just completed
                    if action_type == "open_app":
                        app = action_params.get("name", "").lower()
                        if app in ("chrome", "msedge", "edge", "firefox"):
                            verify_parts.extend([
                                "",
                                "═══ BROWSER JUST OPENED — YOUR NEXT STEPS ═══",
                                "1. Wait for browser to fully load: ACTION: wait PARAMS: {\"seconds\": 3}",
                                "2. VERIFY the screenshot shows a BROWSER window (not File Explorer!)",
                                "3. Focus address bar: ACTION: hotkey PARAMS: {\"keys\": [\"ctrl\", \"l\"]}",
                                "4. Then type URL: ACTION: type_text PARAMS: {\"text\": \"https://...\"}",
                                "5. Press Enter: ACTION: press_key PARAMS: {\"key\": \"enter\"}",
                                "★ Do NOT type anything before pressing Ctrl+L first!",
                            ])
                        elif app in ("notepad", "notepad++"):
                            verify_parts.extend([
                                "",
                                "═══ TEXT EDITOR READY — YOUR NEXT STEPS ═══",
                                "★ For REPORTS / LONG DOCUMENTS (over 300 words): Use write_file instead of typing!",
                                "  ACTION: write_file PARAMS: {\"filename\": \"report.md\", \"content\": \"[your content]\"}",
                                "  This writes directly to Desktop — instant, no lag.",
                                "★ For SHORT content only: click text area, then type:",
                                "1. Click inside the text area: ACTION: click PARAMS: {\"x\": 400, \"y\": 400}",
                                "2. Type ONE SECTION (max 500 words): ACTION: type_text_fast PARAMS: {\"text\": \"...\"}",
                                "★ Do NOT generate the entire report in a single LLM response!",
                                "★ Do NOT open another Notepad — use this one!",
                            ])
                        elif app in ("cmd", "powershell", "terminal"):
                            verify_parts.extend([
                                "",
                                "═══ TERMINAL JUST OPENED — YOUR NEXT STEPS ═══",
                                "1. The terminal should be ready for commands",
                                "2. Type your command: ACTION: run_command PARAMS: {\"command\": \"...\"}",
                            ])
                        else:
                            verify_parts.append(f"\nApp '{app}' opened. Verify it's in foreground, then proceed.")
                    elif action_type in ("type_text", "type_text_fast"):
                        typed = action_params.get("text", "")
                        if "google.com" in typed or "search?q=" in typed or typed.startswith("http"):
                            verify_parts.extend([
                                "",
                                "═══ ⚠ MANDATORY VERIFICATION — DO NOT SKIP ═══",
                                "A URL was typed. BEFORE pressing Enter, you MUST:",
                                "1. Look at the screenshot RIGHT NOW.",
                                "2. Is the URL visible in the address bar? Describe what you see.",
                                "3. If the address bar shows the URL → press Enter.",
                                "4. If the address bar is EMPTY or shows something else → typing FAILED.",
                                "   Recovery: ACTION: hotkey PARAMS: {\"keys\": [\"ctrl\", \"l\"]}",
                                "   Then retry: ACTION: type_text PARAMS: {\"text\": \"...\"}",
                                "★ NEVER press Enter unless you can SEE the URL in the screenshot.",
                            ])
                        else:
                            verify_parts.extend([
                                "",
                                "═══ ⚠ VERIFY TEXT INPUT ═══",
                                f"Text was typed ({len(typed)} chars). Look at the screenshot:",
                                "• Can you see the typed text in the target field/area?",
                                "• If YES → continue with next action.",
                                "• If NO → the text input failed. Click the target field and retry.",
                            ])
                    elif action_type == "press_key" and action_params.get("key") == "enter":
                        verify_parts.extend([
                            "",
                            "═══ ENTER PRESSED — WAIT FOR RESPONSE ═══",
                            "Wait for the page/dialog to respond:",
                            "ACTION: wait PARAMS: {\"seconds\": 3}",
                            "Then examine the new screenshot carefully.",
                        ])
                    elif action_type == "hotkey":
                        keys = action_params.get("keys", [])
                        if keys == ["ctrl", "l"]:
                            verify_parts.extend([
                                "",
                                "═══ ADDRESS BAR FOCUSED — TYPE YOUR URL NOW ═══",
                                "The address bar should be highlighted. Type your URL:",
                                "ACTION: type_text PARAMS: {\"text\": \"https://www.google.com/search?q=...\"}",
                            ])
                        elif keys == ["ctrl", "s"]:
                            verify_parts.append("\nFile save initiated. Check if a Save As dialog appeared.")
                        elif keys == ["alt", "left"]:
                            verify_parts.append("\nNavigated back. Wait 2 seconds, then examine the page.")
                        elif keys == ["alt", "tab"]:
                            verify_parts.append("\nSwitched window. Check what app is now in the foreground.")
                    elif action_type in ("click", "click_element"):
                        verify_parts.extend([
                            "",
                            "═══ ⚠ VERIFY CLICK RESULT ═══",
                            "Look at the screenshot. Describe what changed:",
                            "1. Did the page/UI change from before?",
                            "2. If you clicked a link → did a new page load? If not, wait or retry.",
                            "3. If you clicked an input field → is a cursor blinking there now?",
                            "4. If NOTHING changed → the click missed. Re-examine the screen and pick a different element.",
                            "★ Do NOT proceed unless you see evidence the click worked.",
                        ])
                    elif action_type == "scroll":
                        verify_parts.extend([
                            "",
                            "Read the new content visible on screen.",
                            "If you found useful information → tag it: FINDING: [the fact]",
                            "If you need more content → scroll again.",
                            "If you've read enough → proceed to next phase of your task.",
                        ])
                    elif action_type == "wait":
                        verify_parts.append("\nWait complete. Examine the screenshot — has the content loaded?")
                    elif action_type == "run_command":
                        verify_parts.append("\nCommand executed. Read the output. Did it succeed or show errors?")
                    else:
                        verify_parts.extend([
                            "",
                            "━━━ VERIFICATION CHECKLIST ━━━",
                            "1. WHAT CHANGED? Compare the new screenshot to before.",
                            "2. DID IT WORK? Did the action achieve what you intended?",
                            "3. WHAT'S NEXT? What is the very next step toward your task?",
                        ])
                    
                    if verify_som_desc and action_type not in ("open_app",):
                        verify_parts.append(f"\nIf you accomplished a subtask, note it: PROGRESS: [what you accomplished]")
                    
                    verify_msg = "\n".join(verify_parts)
                else:
                    action_failure_streak += 1
                    strategies_tried.append(f"{action_type}({json.dumps(action_params)[:60]}) — failed")
                    
                    if action_failure_streak < 3:
                        # Specific recovery advice based on what failed
                        recovery_advice = ""
                        if action_type in ("click", "click_element"):
                            recovery_advice = (
                                "CLICK RECOVERY:\n"
                                "• Element may have moved — look at the screenshot and find the element again.\n"
                                "• Use click_element with [ID] if available (more accurate than coordinates).\n"
                                "• If element is off-screen, scroll first, then click.\n"
                                "• If the element is behind a popup/dialog, dismiss the popup first."
                            )
                        elif action_type in ("type_text", "type_text_fast"):
                            recovery_advice = (
                                "TYPE RECOVERY:\n"
                                "• No input field may be focused. Click the target field first.\n"
                                "• For browser address bar: Press Ctrl+L first.\n"
                                "• For text editors: Click inside the text area first.\n"
                                "• Check if a dialog/popup is blocking the input."
                            )
                        elif action_type == "open_app":
                            app = action_params.get("name", "")
                            recovery_advice = (
                                f"APP OPEN RECOVERY for '{app}':\n"
                                f"• The app may not be installed. Try an alternative:\n"
                                f"  chrome → msedge | code → notepad | cmd → powershell\n"
                                f"• The app may already be open — try: ACTION: focus_window PARAMS: {{\"title\": \"{app}\"}}\n"
                                f"• Try Alt+Tab to find if it opened behind other windows."
                            )
                        elif action_type == "focus_window":
                            recovery_advice = (
                                "FOCUS RECOVERY:\n"
                                "• Window may not exist. Try: ACTION: open_app to launch it.\n"
                                "• Try Alt+Tab to cycle through windows.\n"
                                "• Try a different window title (partial match works)."
                            )
                        else:
                            recovery_advice = (
                                "GENERAL RECOVERY:\n"
                                "• Look at the screenshot carefully. What is ACTUALLY on screen?\n"
                                "• Try a different action or different parameters.\n"
                                "• Make sure the right window is in the foreground."
                            )
                        
                        verify_msg = (
                            f"✗ ACTION FAILED: {action_type} → {action_result_text[:120]}\n\n"
                            f"{recovery_advice}\n\n"
                            f"Try a DIFFERENT approach now. Do NOT repeat the same action."
                        )
                    else:
                        verify_msg = (
                            f"🚨 CRITICAL: {action_failure_streak} CONSECUTIVE FAILURES.\n\n"
                            f"Failed strategies so far:\n"
                            + "\n".join(f"  ✗ {s}" for s in strategies_tried[-5:]) +
                            f"\n\nEMERGENCY RECOVERY:\n"
                            f"1. FORGET everything you tried. Start fresh.\n"
                            f"2. Describe the ENTIRE screenshot in detail — every window, button, text field.\n"
                            f"3. What is the original task? Break it into the smallest possible step.\n"
                            f"4. Pick the SIMPLEST possible action that makes any progress.\n"
                            f"5. If you're stuck on coordinates, try open_app or focus_window instead of clicking.\n"
                            f"6. If nothing works, type TASK_COMPLETE to stop."
                        )

                messages.append({"role": "user", "content": verify_msg})

            # ── SMART message history trimming (context-preserving) ──
            if len(messages) > max_history:
                # Instead of just dropping old messages, build a summary
                dropped_count = len(messages) - max_history + 2  # +2 for system + summary
                dropped_msgs = messages[1:dropped_count + 1]  # Skip system msg
                
                # Build compact summary of dropped messages
                summary_parts = [
                    "╔══ CONTEXT SUMMARY (older messages trimmed for token limits) ══╗",
                    f"Task: {prompt}",
                    f"Progress: {progress_tracker.get_status_summary()}",
                ]
                
                # Extract key info from dropped messages
                for msg in dropped_msgs:
                    content = msg.get("content", "")
                    # Preserve any FINDING: or PROGRESS: lines
                    for line in content.split("\n"):
                        if "FINDING:" in line.upper() or "PROGRESS:" in line.upper():
                            summary_parts.append(f"  • {line.strip()[:150]}")
                
                # Always inject accumulated knowledge
                if context_accumulator.findings or context_accumulator.urls_visited:
                    summary_parts.append(context_accumulator.build_context_block())
                
                summary_parts.append("╚══════════════════════════════════════════════════════════════╝")
                
                summary_msg = {"role": "user", "content": "\n".join(summary_parts)}
                messages = [messages[0], summary_msg] + messages[dropped_count + 1:]

            await asyncio.sleep(0.5)

        # Store action history for community post generation
        self._session_action_logs[session_id] = action_history[-30:]  # last 30 actions max

    def _build_system_prompt(self, agent_data: dict, grid_desc: str = "", 
                            allowed_actions: set[str] = None, profile=None,
                            screen_width: int = 1920, screen_height: int = 1080,
                            provider: str = "UNKNOWN") -> str:
        """Build system prompt for smart agent with Think-Plan-Act-Verify architecture.
        Tier-aware: only shows actions the agent is allowed to use.
        
        v5 — SUPREME INTELLIGENCE PROMPT
        ==================================
        This is the most critical piece of the entire system. The quality of this prompt
        directly determines agent success rate. Every word is carefully chosen.
        
        D6 NOTE: Shared instruction fragments (APP_LAUNCH_GUIDE, PRECONDITION_RULES,
        SELF_DETECTION_WARNING) are in core/prompts.py. The full prompt text is kept
        here (rather than fully decomposed) because prompt quality is extremely
        sensitive to ordering and context.
        See also: collaboration_engine.py._build_collab_system_prompt()
        """
        capabilities = agent_data.get("capabilities", [])
        cap_str = ", ".join(c.lower().replace("_", " ") for c in capabilities) if capabilities else "full OS control"
        
        # Use profile persona/expertise if available
        identity = ""
        if profile:
            identity = f"\n{profile.persona}\nExpertise: {profile.expertise}\n"
            cap_str = profile.expertise

        # User-defined persona (prompt engineering from settings)
        user_persona = agent_data.get("persona") or ""
        if user_persona:
            identity += f"\n═══ USER-DEFINED PERSONA ═══\n{user_persona}\n═══ END PERSONA ═══\nYou MUST follow the persona instructions above in addition to your base capabilities.\n"

        # Build action list dynamically based on allowed_actions
        if allowed_actions is None:
            allowed_actions = self.VALID_ACTIONS
        
        element_actions = []
        action_lines = []
        for act in sorted(allowed_actions):
            if act in ACTION_DEFINITIONS:
                if act.endswith("_element"):
                    element_actions.append(ACTION_DEFINITIONS[act])
                else:
                    action_lines.append(ACTION_DEFINITIONS[act])
        
        element_section = ""
        if element_actions:
            element_section = "★ PREFERRED — Element-based (click by detected element ID — MORE ACCURATE):\n" + "\n".join(element_actions) + "\n\n"
        
        actions_block = element_section + "Coordinate-based & other actions:\n" + "\n".join(action_lines)

        # Tier badge
        tier_badge = ""
        if profile:
            tier_badge = f"\n[Tier {profile.tier} | {profile.domain.upper()} domain | {len(allowed_actions)} actions]\n"
        
        # Screen dimension variables for coordinate specification
        sw = screen_width
        sh = screen_height
        sw_max = sw - 1
        sh_max = sh - 1
        sw_mid = sw // 2
        sh_mid = sh // 2
        
        raw_prompt = f"""You are an expert AI agent operating a real Windows computer via OS-level actions.
You see the screen via annotated screenshots with numbered UI element labels [1], [2], [3]...
You output exactly ONE action per turn, then verify the result.
{identity}Capabilities: {cap_str}
{tier_badge}

╔══════════════════════════════════════════════════════════════════════╗
║                 IRON RULES (HIGHEST PRIORITY)                       ║
╚══════════════════════════════════════════════════════════════════════╝

1. ONE action per turn. No exceptions.
2. ALWAYS click input fields BEFORE typing. Never assume focus.
3. Before typing English/URLs: ensure IME is English. Korean IME active → ACTION: hotkey PARAMS: {{"keys": ["hangul"]}}
4. AFTER EVERY type_text → LOOK AT SCREENSHOT. Verify text appeared. If NOT visible → click target field and retry.
5. NEVER press Enter after typing a URL unless you can SEE the URL in the address bar.
6. Use click_element with [ID] for clicking (most accurate). Use raw coordinates only as fallback.
7. For LONG/KOREAN text: use type_text_fast (clipboard paste). For DOCUMENTS over 300 words: use write_file.
8. NEVER open File Explorer for research/browsing. Use browser.
9. NEVER repeat a failed action identically. Change approach.
10. NEVER say TASK_COMPLETE until you have ACTUALLY DONE the work.
11. If you see the Ogenti window (dark chat UI) → switch apps immediately.
12. After opening an app → verify it's in foreground before proceeding.
13. Do NOT open duplicate app windows.

╔══════════════════════════════════════════════════════════════════════╗
║                    COGNITIVE FRAMEWORK                              ║
╚══════════════════════════════════════════════════════════════════════╝

Every turn, follow this process:

▌ OBSERVE → What app is in foreground? Key elements with [numbers]? Any popup/error/loading?
▌ ORIENT  → What did my last action achieve? Am I in the right app? Is cursor in the right place?
▌ DECIDE  → Pre-conditions: type→verify focus, click→verify loaded, app→verify foreground.
▌ ACT     → Execute ONE action.
▌ VERIFY  → Next turn: FIRST check if previous action worked by examining screenshot.

╔══════════════════════════════════════════════════════════════════════╗
║                    REFERENCE COMMANDS                                ║
╚══════════════════════════════════════════════════════════════════════╝

Apps:
  Browser: ACTION: open_app PARAMS: {{"name": "{_BROWSER}"}}
  Notepad: ACTION: open_app PARAMS: {{"name": "notepad"}}
  Terminal: ACTION: open_app PARAMS: {{"name": "cmd"}}
  Switch window: ACTION: focus_window PARAMS: {{"title": "..."}} or ACTION: hotkey PARAMS: {{"keys": ["alt", "tab"]}}

Browser:
  Address bar: ACTION: hotkey PARAMS: {{"keys": ["ctrl", "l"]}}
  Search: ACTION: type_text PARAMS: {{"text": "https://www.google.com/search?q=..."}} then ACTION: press_key PARAMS: {{"key": "enter"}}
  Back: ACTION: hotkey PARAMS: {{"keys": ["alt", "left"]}}
  New tab: ACTION: hotkey PARAMS: {{"keys": ["ctrl", "t"]}}
  Close tab: ACTION: hotkey PARAMS: {{"keys": ["ctrl", "w"]}}
  Scroll: ACTION: scroll PARAMS: {{"clicks": -5}} (down) / {{"clicks": 5}} (up)
  Find: ACTION: hotkey PARAMS: {{"keys": ["ctrl", "f"]}}

Save As dialog:
  1. Click filename input field
  2. Select all: ACTION: hotkey PARAMS: {{"keys": ["end"]}} then ACTION: hotkey PARAMS: {{"keys": ["shift", "home"]}}
  3. Type name: ACTION: type_text PARAMS: {{"text": "filename.txt"}}
  4. Confirm: ACTION: press_key PARAMS: {{"key": "enter"}}
  ⚠ NEVER use ctrl+a in Save As — it selects FILE LIST, not filename text.

Writing (for reports over 300 words):
  ACTION: write_file PARAMS: {{"filename": "report.md", "content": "[full text]"}}
  write_file saves to Desktop instantly — no UI lag.
  If typing in Notepad: max 500 words per type_text_fast call.

╔══════════════════════════════════════════════════════════════════════╗
║              VISUAL DECISION TREE                                    ║
╚══════════════════════════════════════════════════════════════════════╝

Match the FIRST rule that applies to what you see on screen:

Desktop/no app → open_app for the task (browser for research, notepad for writing)
Ogenti window (dark chat UI) → hotkey alt+tab or open_app to switch away
File Explorer (wrong for research) → alt+f4, then open browser
Browser — new tab → hotkey ctrl+l to focus address bar
Browser — address bar focused → type URL, VERIFY it appears, then press Enter
Browser — search results → click_element on relevant non-ad link
Browser — article page → read content, scroll {{"clicks": -5}} for more, tag FINDING: [fact], go back with alt+left
Browser — loading → wait {{"seconds": 3}}
Cookie/popup dialog → click Accept/OK/X button
Notepad — empty → write_file for long content, or click then type_text_fast for short
Notepad — has content → ctrl+s to save
Terminal → run_command
Error dialog → dismiss (click OK/Close), try different approach
Taskbar only → open_app
Default → describe what you see, reason, take smallest step toward goal

╔══════════════════════════════════════════════════════════════════════╗
║                 FAILURE RECOVERY                                     ║
╚══════════════════════════════════════════════════════════════════════╝

1 failure → different element ID or coordinates
2 failures → completely different approach (keyboard nav instead of click, etc.)
3+ failures → STOP, describe everything on screen, start fresh

{grid_desc}

━━━ AVAILABLE ACTIONS ━━━

{actions_block}

━━━ RESPONSE FORMAT ━━━

**OBSERVATION**: [What you see: app, key UI elements with [numbers], popups/errors, cursor]
**THINKING**: [Last action result? Preconditions for next? Best next step?]
**ACTION**: [one action name]
**PARAMS**: [JSON]

Screen: {sw}x{sh}px. Coordinates: absolute pixels, X: 0–{sw_max}, Y: 0–{sh_max}, center: ({sw_mid},{sh_mid}).
Prefer click_element [ID] over raw coordinates.

Subtask done: **PROGRESS**: [what was accomplished]
Full task done: TASK_COMPLETE
"""
        # ═══ PROVIDER-AWARE PROMPT ADAPTATION ═══
        # Rewrite trigger phrases that cause content-policy refusals on specific providers
        return adapt_system_prompt(raw_prompt, provider)

    # Valid actions the OS controller and tool engine can handle
    # (imported from core.prompts to avoid duplication)
    VALID_ACTIONS = _VALID_ACTIONS

    def _log_agent_thinking(self, session_id: str, agent_id: str, llm_response: str):
        """Parse and log the agent's reasoning process at INFO level.
        
        Extracts OBSERVATION, THINKING, and ACTION blocks from the LLM response
        so the user can see exactly what the agent is perceiving and deciding.
        This is CRITICAL for debugging — without it, the user has zero visibility.
        """
        import re as _re
        
        lines = llm_response.split("\n")
        observation = []
        thinking = []
        action_line = ""
        params_line = ""
        current_section = None
        
        for line in lines:
            clean = line.strip().replace("**", "").strip()
            upper = clean.upper()
            
            if upper.startswith("OBSERVATION:") or upper.startswith("OBSERVE:"):
                current_section = "obs"
                text = clean.split(":", 1)[1].strip() if ":" in clean else ""
                if text:
                    observation.append(text)
            elif upper.startswith("THINKING:") or upper.startswith("THINK:") or upper.startswith("REASONING:"):
                current_section = "think"
                text = clean.split(":", 1)[1].strip() if ":" in clean else ""
                if text:
                    thinking.append(text)
            elif upper.startswith("ACTION:"):
                current_section = "action"
                action_line = clean.split(":", 1)[1].strip() if ":" in clean else ""
            elif upper.startswith("PARAMS:"):
                current_section = None
                params_line = clean.split(":", 1)[1].strip() if ":" in clean else ""
            elif current_section == "obs" and clean:
                observation.append(clean)
            elif current_section == "think" and clean:
                thinking.append(clean)
        
        # Log each section at INFO level so the user can SEE the reasoning
        import asyncio
        loop = asyncio.get_event_loop()
        
        if observation:
            obs_text = " ".join(observation)[:300]
            loop.create_task(self.log(session_id, f"👁️ OBSERVATION: {obs_text}", "INFO", "AGENT", agent_id))
        
        if thinking:
            think_text = " ".join(thinking)[:300]
            loop.create_task(self.log(session_id, f"🧠 THINKING: {think_text}", "INFO", "AGENT", agent_id))
        
        if action_line:
            action_display = f"⚡ DECISION: {action_line}"
            if params_line:
                action_display += f" → {params_line[:100]}"
            loop.create_task(self.log(session_id, action_display, "INFO", "AGENT", agent_id))
        
        # If we couldn't parse structured thinking, log the raw response summary
        if not observation and not thinking and not action_line:
            summary = llm_response[:400].replace("\n", " ").strip()
            loop.create_task(self.log(session_id, f"🤖 LLM Response: {summary}", "INFO", "LLM", agent_id))

    def _parse_actions(self, text: str, allowed_actions: set[str] = None) -> list[dict]:
        """Parse actions from LLM response.

        Supports:
        - Legacy lines: ACTION: <type> then PARAMS: <json>
        - Fenced JSON blocks: ```json ...```
        - Inline JSON object/array containing action(s)

        Always enforces tier+domain `allowed_actions`.
        """
        import json as json_module

        if allowed_actions is None:
            allowed_actions = self.VALID_ACTIONS

        def _normalize_action_type(v: str) -> str:
            return (v or "").strip().lower()

        def _base_action(atype: str) -> str:
            return atype.replace("_element", "") if atype.endswith("_element") else atype

        def _is_allowed(atype: str) -> bool:
            ba = _base_action(atype)
            return atype in allowed_actions or ba in allowed_actions

        def _coerce_actions(obj) -> list[dict]:
            if obj is None:
                return []
            if isinstance(obj, dict):
                if isinstance(obj.get("actions"), list):
                    return [a for a in obj["actions"] if isinstance(a, dict)]
                if "type" in obj or "action" in obj:
                    atype = _normalize_action_type(obj.get("type") or obj.get("action"))
                    params = obj.get("params") or obj.get("arguments") or {}
                    if not isinstance(params, dict):
                        params = {}
                    return [{"type": atype, "params": params}]
                return []
            if isinstance(obj, list):
                out = []
                for it in obj:
                    if isinstance(it, dict):
                        atype = _normalize_action_type(it.get("type") or it.get("action"))
                        params = it.get("params") or it.get("arguments") or {}
                        if not isinstance(params, dict):
                            params = {}
                        out.append({"type": atype, "params": params})
                return out
            return []

        def _filter(actions_list: list[dict]) -> list[dict]:
            filtered: list[dict] = []
            for a in actions_list:
                atype = _normalize_action_type(a.get("type") or a.get("action"))
                params = a.get("params") if isinstance(a.get("params"), dict) else {}
                if not atype:
                    continue
                if _is_allowed(atype):
                    filtered.append({"type": atype, "params": params})
            return filtered

        # 1) Fenced JSON blocks
        try:
            stripped = (text or "").strip()
            if "```" in stripped:
                parts = stripped.split("```")
                for idx in range(1, len(parts), 2):
                    block = parts[idx]
                    lines = block.split("\n")
                    if lines and lines[0].strip().lower() in ("json", "javascript"):
                        block = "\n".join(lines[1:])
                    block = block.strip()
                    if not block:
                        continue
                    try:
                        obj = json_module.loads(block)
                        filtered = _filter(_coerce_actions(obj))
                        if filtered:
                            return filtered
                    except Exception:
                        continue
        except Exception:
            pass

        # 2) Inline JSON snippet (object/array) — RESTRICTED to action context
        # Only search for JSON AFTER the last ACTION/PARAMS/THINKING marker to avoid
        # capturing coordinates from OBSERVATION section or reasoning text.
        try:
            stripped = (text or "").strip()
            # Find the last ACTION-related marker to narrow search scope
            search_text = stripped
            for marker in ("**ACTION**", "ACTION:", "**PARAMS**", "PARAMS:"):
                marker_pos = stripped.rfind(marker)
                if marker_pos >= 0:
                    search_text = stripped[marker_pos:]
                    break
            
            starts = [p for p in (search_text.find("["), search_text.find("{")) if p >= 0]
            if starts:
                start = min(starts)
                # Find MATCHING closing bracket, not the last one in the entire text
                open_char = search_text[start]
                close_char = "]" if open_char == "[" else "}"
                depth = 0
                end = -1
                for ci in range(start, len(search_text)):
                    ch = search_text[ci]
                    if ch in ("{", "["):
                        depth += 1
                    elif ch in ("}", "]"):
                        depth -= 1
                        if depth == 0:
                            end = ci + 1
                            break
                if end > start:
                    snippet = search_text[start:end]
                    obj = json_module.loads(snippet)
                    filtered = _filter(_coerce_actions(obj))
                    if filtered:
                        return filtered
        except Exception:
            pass

        # 3) Legacy ACTION/PARAMS lines (robust parsing)
        import re as _re
        actions: list[dict] = []
        lines = (text or "").split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Strip markdown formatting: **, *, -, bullet numbers, >
            clean_line = line.replace("**", "").strip()
            clean_line = clean_line.lstrip("*->#").strip()
            clean_line = _re.sub(r'^\d+[\.\)]\s*', '', clean_line).strip()
            
            if clean_line.upper().startswith("ACTION:"):
                action_type = _normalize_action_type(clean_line[len("ACTION:"):])
                params: dict = {}

                # Check for inline PARAMS: on the same line
                if "PARAMS:" in clean_line.upper():
                    idx_p = clean_line.upper().index("PARAMS:")
                    action_type = _normalize_action_type(clean_line[len("ACTION:"):idx_p])
                    params_str = clean_line[idx_p + len("PARAMS:"):].strip()
                    try:
                        parsed = json_module.loads(params_str)
                        if isinstance(parsed, dict):
                            params = parsed
                    except json_module.JSONDecodeError:
                        try:
                            parsed = json_module.loads(params_str.replace("'", '"'))
                            if isinstance(parsed, dict):
                                params = parsed
                        except:
                            pass
                elif i + 1 < len(lines):
                    next_line = lines[i + 1].strip().replace("**", "").strip()
                    next_clean = next_line.lstrip("*->#").strip()
                    next_clean = _re.sub(r'^\d+[\.\)]\s*', '', next_clean).strip()
                    if next_clean.upper().startswith("PARAMS:"):
                        params_str = next_clean[len("PARAMS:"):].strip()
                        try:
                            parsed = json_module.loads(params_str)
                            if isinstance(parsed, dict):
                                params = parsed
                        except json_module.JSONDecodeError:
                            try:
                                parsed = json_module.loads(params_str.replace("'", '"'))
                                if isinstance(parsed, dict):
                                    params = parsed
                            except:
                                pass
                        i += 1

                if _is_allowed(action_type):
                    actions.append({"type": action_type, "params": params})
                else:
                    if action_type in self.VALID_ACTIONS:
                        logger.warning(f"⛔ Tier/domain blocked action: '{action_type}'")
                    else:
                        logger.warning(f"Ignoring invalid action: '{action_type}'")
            i += 1

        return actions


class AgentContext:
    """Context passed to plugin agents for execution — with SoM + verification support."""
    
    def __init__(
        self,
        session_id: str,
        agent_id: str,
        engine: ExecutionEngine,
        llm: LLMClient,
        os_controller: OSController,
        screenshot: ScreenshotCapture,
        som_engine=None,
        agent_profile=None,
    ):
        self.session_id = session_id
        self.agent_id = agent_id
        self.engine = engine
        self.llm = llm
        self.os = os_controller
        self.screenshot = screenshot
        self._som = som_engine
        self._last_som_result = None
        self._last_action_success: Optional[bool] = None
        self._action_failure_streak = 0
        # Tier awareness
        self.agent_profile = agent_profile
        self.tier = agent_profile.tier if agent_profile else "F"
        self.domain = agent_profile.domain if agent_profile else "general"

    async def log(self, message: str, level: str = "INFO"):
        await self.engine.log(self.session_id, message, level, "AGENT", self.agent_id)

    async def send_screenshot(self):
        await self.engine.send_screenshot(self.session_id)

    async def ask_llm(self, messages: list[dict], screenshot: bool = False) -> str:
        screen_b64 = None
        if screenshot:
            await self.engine._wait_for_ui_settle(max_wait=1.0)
            # Prefer SoM-annotated screenshot (numbered elements)
            if self._som and self._som.enabled:
                sr = self._som.capture_som()
                if sr and sr.annotated_image:
                    self._last_som_result = sr
                    screen_b64 = base64.b64encode(sr.annotated_image).decode("utf-8")
            # Fallback to regular screenshot
            if not screen_b64:
                img = self.screenshot.capture()
                if img:
                    screen_b64 = base64.b64encode(img).decode("utf-8")
        try:
            resp = await self.llm.chat(messages=messages, screenshot_b64=screen_b64)
        except Exception as e:
            logger.error(f"ask_llm: LLM chat call raised exception: {e}")
            resp = {"content": f"[LLM Error: {e}]"}
        return resp.get("content", "")

    async def ask_llm_with_verification(
        self, messages: list[dict], action_description: str = ""
    ) -> str:
        """
        Ask LLM with a fresh screenshot AND a verification prompt appended.
        Forces the LLM to analyze the current screen state.
        """
        await self.engine._wait_for_ui_settle(max_wait=1.0)
        img = self.screenshot.capture()
        screen_b64 = None
        if img:
            screen_b64 = base64.b64encode(img).decode("utf-8")

        if action_description:
            verify_prompt = (
                f"Previous action: {action_description}\n"
                f"LOOK at the screenshot and describe what you see. "
                f"Did the action work as expected? What should happen next?"
            )
            messages = messages + [{"role": "user", "content": verify_prompt}]

        resp = await self.llm.chat(messages=messages, screenshot_b64=screen_b64)
        return resp.get("content", "")

    def resolve_som_action(self, action: dict) -> dict:
        """Resolve element-based actions (click_element) to coordinate-based actions."""
        atype = action.get("type", "")
        params = action.get("params", {})
        if atype.endswith("_element"):
            if self._last_som_result:
                eid = params.get("id")
                if eid is not None:
                    el = self._last_som_result.element_map.get(int(eid))
                    if el:
                        base = atype.replace("_element", "")
                        new_params = {"x": el.cx, "y": el.cy}
                        for k, v in params.items():
                            if k != "id":
                                new_params[k] = v
                        return {"type": base, "params": new_params}
                # element not found – fallback to base action type
                logger.warning(f"SoM element #{params.get('id')} not found, falling back")
            else:
                # SoM unavailable – strip _element suffix
                logger.warning(f"SoM unavailable for '{atype}', stripping _element suffix")
            # In both fallback cases, strip _element and pass through
            base = atype.replace("_element", "")
            fallback_params = {k: v for k, v in params.items() if k != "id"}
            return {"type": base, "params": fallback_params}
        return action

    def get_som_description(self) -> str:
        """Return latest SoM element description, or empty string."""
        if self._last_som_result and self._last_som_result.description:
            return self._last_som_result.description
        return ""

    def click(self, x: int, y: int, button: str = "left"):
        result = self.os.execute_action("click", {"x": x, "y": y, "button": button})
        self._track_action_result(result)
        return result

    def type_text(self, text: str):
        result = self.os.execute_action("type_text", {"text": text})
        self._track_action_result(result)
        return result

    def press_key(self, key: str):
        result = self.os.execute_action("press_key", {"key": key})
        self._track_action_result(result)
        return result

    def hotkey(self, *keys):
        result = self.os.execute_action("hotkey", {"keys": list(keys)})
        self._track_action_result(result)
        return result

    def move_mouse(self, x: int, y: int):
        result = self.os.execute_action("move_mouse", {"x": x, "y": y})
        self._track_action_result(result)
        return result

    def scroll(self, clicks: int):
        result = self.os.execute_action("scroll", {"clicks": clicks})
        self._track_action_result(result)
        return result

    def open_app(self, name: str):
        result = self.os.execute_action("open_app", {"name": name})
        self._track_action_result(result)
        return result

    def get_mouse_position(self) -> tuple[int, int]:
        return self.os.get_mouse_position()

    def get_screen_size(self) -> tuple[int, int]:
        return self.os.get_screen_size()

    @property
    def action_failure_streak(self) -> int:
        return self._action_failure_streak

    def _track_action_result(self, result):
        """Track action success/failure for streak detection."""
        success = result.get("success", False) if isinstance(result, dict) else True
        if success:
            self._action_failure_streak = 0
            self._last_action_success = True
        else:
            self._action_failure_streak += 1
            self._last_action_success = False
