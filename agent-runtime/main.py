"""
ogenti Agent Runtime
=======================
Python-based agent execution engine that controls the OS
(mouse, keyboard, screen capture, app management) using
commands from the backend orchestrated by LLM providers.

v2 — Multi-environment support:
- Session isolation: each execution runs independently
- Concurrent user support: multiple sessions can run (queued OS access)
- Cross-platform: works on Windows, macOS, Linux
- Dynamic resolution: adapts to any screen size
"""

import os
import sys

# ═══ CRITICAL: Force sys.path to THIS directory FIRST ═══
# This prevents Python from loading old modules from __pycache__,
# .venv, PYTHONPATH, or any other cached location.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if sys.path[0] != _THIS_DIR:
    sys.path.insert(0, _THIS_DIR)
# Also remove any duplicate paths that might shadow our modules
sys.path = [_THIS_DIR] + [p for p in sys.path[1:] if os.path.abspath(p) != _THIS_DIR]
# Disable bytecode caching to prevent stale .pyc issues
sys.dont_write_bytecode = True

import json
import time
import asyncio
import signal
from typing import Optional
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Depends, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from loguru import logger

# Load .env from project root (parent of agent-runtime/) BEFORE importing core modules
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '.env')
load_dotenv(_env_path)
load_dotenv()  # also try cwd

from core.engine import ExecutionEngine
from core.os_controller import OSController
from core.llm_client import LLMClient, create_llm_client
from core.screenshot import ScreenshotCapture
from core.plugin_loader import PluginLoader
from core.idle_engagement import IdleCommunityEngine

# ═══ DIAGNOSTIC: Print EXACT file paths being used ═══
# Use safe print to avoid cp949/cp932 encoding crashes on Windows console
import io as _io
if sys.platform == 'win32':
    try:
        sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass

_diag_modules = {
    'main.py': __file__,
    'engine': getattr(sys.modules.get('core.engine'), '__file__', 'N/A'),
    'os_controller': getattr(sys.modules.get('core.os_controller'), '__file__', 'N/A'),
    'collaboration_engine': getattr(sys.modules.get('core.collaboration_engine'), '__file__', 'N/A'),
    'agent_intelligence': getattr(sys.modules.get('core.agent_intelligence'), '__file__', 'N/A'),
    'prompts': getattr(sys.modules.get('core.prompts'), '__file__', 'N/A'),
}
print("=" * 70)
print("  OGENTI RUNTIME - MODULE PATH DIAGNOSTIC")
print("=" * 70)
print(f"  CWD:        {os.getcwd()}")
print(f"  sys.path[0]: {sys.path[0] if sys.path else 'EMPTY'}")
for name, fpath in _diag_modules.items():
    print(f"  {name:25s} → {fpath}")

# Check if Win32 keyboard fix exists
_has_sendip = hasattr(OSController, 'win32_press_key')
_has_ensure_focus = hasattr(OSController, '_ensure_target_focus')
print(f"  Win32 SendInput fix:    {'YES' if _has_sendip else '*** NO - OLD CODE ***'}")
print(f"  _ensure_target_focus:   {'YES' if _has_ensure_focus else '*** NO - OLD CODE ***'}")

# Check os_controller.py file size
try:
    _osc_path = getattr(sys.modules.get('core.os_controller'), '__file__', '')
    _osc_size = os.path.getsize(_osc_path) if _osc_path else 0
    print(f"  os_controller.py size:  {_osc_size} bytes")
except:
    pass

# Check collaboration_engine for Ogenti fix
try:
    from core.collaboration_engine import CollaborativeSession
    _has_ogenti_collab = hasattr(CollaborativeSession, '_ogenti_consecutive_collab')
    print(f"  Collab Ogenti fix:      {'YES' if _has_ogenti_collab else '*** NO - OLD CODE ***'}")
    _collab_path = getattr(sys.modules.get('core.collaboration_engine'), '__file__', '')
    _collab_size = os.path.getsize(_collab_path) if _collab_path else 0
    print(f"  collaboration.py size:  {_collab_size} bytes")
except Exception as _ce:
    print(f"  Collab check error:     {_ce}")

print("=" * 70)
# ═══ END DIAGNOSTIC ═══

# === Config ===
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:4000")
RUNTIME_PORT = int(os.getenv("RUNTIME_PORT", "5000"))
RUNTIME_HOST = os.getenv("RUNTIME_HOST", "0.0.0.0")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
MAX_CONCURRENT_SESSIONS = int(os.getenv("MAX_CONCURRENT_SESSIONS", "5"))
STRICT_PLUGIN_MAPPING = os.getenv("AGENT_RUNTIME_STRICT_PLUGIN_MAPPING", "0") in ("1", "true", "TRUE", "yes", "YES")
RUNTIME_API_KEY = os.getenv("AGENT_RUNTIME_SECRET", "")
RUNTIME_TOKEN = os.getenv("RUNTIME_TOKEN", "")
ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:4000").split(",")

if not RUNTIME_API_KEY and os.getenv("NODE_ENV") == "production":
    print("WARNING: AGENT_RUNTIME_SECRET not set in production — API endpoints are unprotected!")

logger.remove()
logger.add(sys.stderr, level=LOG_LEVEL, format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | {message}")
logger.add("logs/runtime.log", rotation="10 MB", retention="7 days", level="DEBUG")

# === Models ===
class ExecutionRequest(BaseModel):
    session_id: str
    prompt: str
    agent_ids: list[str]
    agents: list[dict] = Field(default_factory=list)
    llm_config: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)

class PauseRequest(BaseModel):
    session_id: str

class CancelRequest(BaseModel):
    session_id: str

class AgentStatusUpdate(BaseModel):
    session_id: str
    agent_id: str
    status: str
    message: Optional[str] = None

class HealthResponse(BaseModel):
    status: str
    version: str
    active_sessions: int
    max_sessions: int = MAX_CONCURRENT_SESSIONS
    platform: str = sys.platform

# === Global state ===
engine: Optional[ExecutionEngine] = None
active_sessions: dict[str, asyncio.Task] = {}
_session_semaphore: Optional[asyncio.Semaphore] = None
_idle_engine: Optional[IdleCommunityEngine] = None
_ws_command_task: Optional[asyncio.Task] = None


# === WebSocket Command Channel (central server mode) ===

async def _ws_command_loop():
    """Connect to central backend via WebSocket to receive execution commands."""
    import websockets
    base = BACKEND_URL.rstrip("/")
    ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
    token = RUNTIME_TOKEN
    if not token:
        logger.info("No RUNTIME_TOKEN set — WebSocket command channel disabled (local mode)")
        return

    backoff = 1.0
    max_backoff = 60.0

    while True:
        try:
            async with websockets.connect(ws_url, ping_interval=20, ping_timeout=10) as ws:
                logger.info(f"WebSocket command channel connected to {ws_url}")
                backoff = 1.0

                await ws.send(json.dumps({"event": "auth", "data": {"token": token}}))
                auth_resp = json.loads(await ws.recv())
                if auth_resp.get("event") != "connected":
                    logger.error(f"WS auth failed: {auth_resp}")
                    await asyncio.sleep(5)
                    continue

                await ws.send(json.dumps({"event": "runtime_register"}))
                reg_resp = json.loads(await ws.recv())
                logger.info(f"Runtime registered: {reg_resp}")

                async for raw_msg in ws:
                    try:
                        msg = json.loads(raw_msg)
                        if msg.get("event") == "runtime_command":
                            await _handle_ws_command(msg.get("data", {}))
                    except Exception as e:
                        logger.error(f"WS command handler error: {e}")

        except asyncio.CancelledError:
            logger.info("WS command loop cancelled")
            return
        except Exception as e:
            logger.warning(f"WS command channel disconnected: {e}, reconnecting in {backoff:.0f}s")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)


async def _handle_ws_command(cmd: dict):
    """Process a command received from the central backend via WebSocket."""
    cmd_type = cmd.get("type", "")
    if cmd_type == "execute":
        if not engine:
            logger.error("Engine not initialized, cannot execute")
            return
        session_id = cmd.get("session_id", "")
        if session_id in active_sessions:
            logger.warning(f"Session {session_id} already running")
            return

        req = ExecutionRequest(
            session_id=session_id,
            prompt=cmd.get("prompt", ""),
            agent_ids=cmd.get("agent_ids", []),
            agents=cmd.get("agents", []),
            llm_config=cmd.get("llm_config", {}),
            config=cmd.get("config", {}),
        )
        try:
            await _do_execute(req)
        except Exception as e:
            logger.error(f"WS execute error: {e}")

    elif cmd_type == "pause":
        session_id = cmd.get("session_id", "")
        if engine and session_id in active_sessions:
            engine.pause_session(session_id)
            logger.info(f"WS: Paused session {session_id}")

    elif cmd_type == "cancel":
        session_id = cmd.get("session_id", "")
        if session_id in active_sessions:
            task = active_sessions.pop(session_id)
            task.cancel()
        if engine:
            engine.cancel_session(session_id)
        logger.info(f"WS: Cancelled session {session_id}")

    elif cmd_type == "user_input":
        session_id = cmd.get("session_id", "")
        user_input = cmd.get("input", "")
        logger.info(f"WS: Received user_input for session {session_id}: {user_input[:80] if user_input else ''}")

    else:
        logger.warning(f"Unknown WS command type: {cmd_type}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, _session_semaphore, _idle_engine
    logger.info("Starting ogenti Agent Runtime v2 (multi-env)")
    
    _session_semaphore = asyncio.Semaphore(MAX_CONCURRENT_SESSIONS)
    
    os_controller = OSController()
    screenshot = ScreenshotCapture()
    plugin_loader = PluginLoader()
    
    # Load available plugins
    plugin_loader.discover_plugins()

    # Plugin mapping report (registry slugs vs loaded plugin keys)
    try:
        registry_slugs = set()
        try:
            from core.agent_registry import AGENT_REGISTRY
            registry_slugs = set(AGENT_REGISTRY.keys())
        except Exception:
            registry_slugs = set()

        plugin_keys = set(plugin_loader.plugins.keys())
        intersection = sorted(registry_slugs & plugin_keys)
        missing_plugins = sorted(registry_slugs - plugin_keys)
        extra_plugins = sorted(plugin_keys - registry_slugs)

        report = {
            "registry_count": len(registry_slugs),
            "plugin_count": len(plugin_keys),
            "intersection_count": len(intersection),
            "missing_plugin_for_registry_count": len(missing_plugins),
            "extra_plugin_without_registry_count": len(extra_plugins),
            "intersection": intersection[:30],
            "missing_plugin_for_registry": missing_plugins[:50],
            "extra_plugin_without_registry": extra_plugins[:50],
        }

        os.makedirs("logs", exist_ok=True)
        with open("logs/plugin_mapping_report.json", "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(
            f"Plugin mapping: registry={len(registry_slugs)} plugins={len(plugin_keys)} "
            f"intersection={len(intersection)} missing={len(missing_plugins)} extra={len(extra_plugins)}"
        )

        if STRICT_PLUGIN_MAPPING and registry_slugs and len(intersection) == 0:
            raise RuntimeError(
                "STRICT_PLUGIN_MAPPING enabled but no registry slugs matched any loaded plugin keys. "
                "See logs/plugin_mapping_report.json"
            )
    except Exception as e:
        logger.error(f"Plugin mapping report failed: {e}")
        if STRICT_PLUGIN_MAPPING:
            raise
    
    engine = ExecutionEngine(
        backend_url=BACKEND_URL,
        os_controller=os_controller,
        screenshot=screenshot,
        plugin_loader=plugin_loader,
    )
    
    logger.info(f"Runtime ready on {RUNTIME_HOST}:{RUNTIME_PORT}")
    logger.info(f"Backend URL: {BACKEND_URL}")
    logger.info(f"Screen: {os_controller.screen_width}x{os_controller.screen_height}")
    logger.info(f"Max concurrent sessions: {MAX_CONCURRENT_SESSIONS}")
    logger.info(f"Loaded plugins: {list(plugin_loader.plugins.keys())}")
    
    # Start idle community engagement engine
    _idle_engine = IdleCommunityEngine(
        backend_url=BACKEND_URL,
        runtime_api_key=RUNTIME_API_KEY,
        runtime_token=RUNTIME_TOKEN,
    )
    _idle_engine.set_active_sessions(active_sessions)
    _idle_engine.start()
    logger.info("Idle community engagement engine initialized")
    
    # Start WebSocket command channel (central server mode)
    global _ws_command_task
    if RUNTIME_TOKEN:
        _ws_command_task = asyncio.create_task(_ws_command_loop())
        logger.info("WebSocket command channel started (central server mode)")
    else:
        logger.info("Local mode — no WebSocket command channel")
    
    yield
    
    # Cleanup
    logger.info("Shutting down runtime...")
    
    # Stop WS command channel
    if _ws_command_task and not _ws_command_task.done():
        _ws_command_task.cancel()
        try:
            await _ws_command_task
        except asyncio.CancelledError:
            pass
    
    # Stop idle engagement
    if _idle_engine:
        _idle_engine.stop()
    
    for session_id, task in active_sessions.items():
        task.cancel()
    active_sessions.clear()

app = FastAPI(
    title="ogenti Agent Runtime",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# === Auth ===

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
_runtime_secret_header = APIKeyHeader(name="X-Runtime-Secret", auto_error=False)

async def verify_api_key(
    api_key: str = Security(_api_key_header),
    runtime_secret: str = Security(_runtime_secret_header),
):
    """Validate API key for protected endpoints. Accepts both X-API-Key and X-Runtime-Secret headers."""
    if not RUNTIME_API_KEY:
        # No secret configured — allow (development mode)
        return None
    key = api_key or runtime_secret
    if key != RUNTIME_API_KEY:
        raise HTTPException(status_code=403, detail="Invalid or missing API key")
    return key

# === Routes ===

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        version="2.0.0",
        active_sessions=len(active_sessions),
        max_sessions=MAX_CONCURRENT_SESSIONS,
        platform=sys.platform,
    )


# ── Post-execution community sharing ──────────────────────

async def _browse_community_knowledge(limit: int = 10) -> list[dict]:
    """Browse the community knowledge feed for learning before execution."""
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{BACKEND_URL}/api/community/knowledge-feed",
                params={"limit": limit},
            )
            if resp.status_code == 200:
                data = resp.json()
                posts = data.get("data", [])
                logger.info(f"Community: browsed {len(posts)} know-how posts")
                return posts
            else:
                logger.debug(f"Community browse failed: HTTP {resp.status_code}")
                return []
    except Exception as e:
        logger.warning(f"Community browse failed (non-critical): {e}")
        return []


async def _build_community_context(prompt: str, agents: list[dict]) -> str:
    """Build a context string from relevant community knowledge for the LLM."""
    try:
        posts = await _browse_community_knowledge(limit=5)
        if not posts:
            return ""
        
        relevant = []
        prompt_lower = prompt.lower()
        for post in posts:
            title = (post.get("title") or "").lower()
            content = (post.get("content") or "").lower()
            # Include posts that share keywords with the current task
            prompt_words = set(w for w in prompt_lower.split() if len(w) > 3)
            post_words = set(w for w in (title + " " + content).split() if len(w) > 3)
            overlap = prompt_words & post_words
            if overlap or post.get("score", 0) >= 3:
                relevant.append(post)
        
        if not relevant:
            # Fall back to top-scored posts
            relevant = posts[:3]
        
        lines = ["[Community Knowledge — tips from past agent executions]"]
        for p in relevant[:3]:
            outcome = p.get("executionOutcome", "")
            badge = "✅" if outcome == "COMPLETED" else "❌" if outcome == "FAILED" else ""
            lines.append(f"- {badge} {p.get('title', 'Untitled')} (score: {p.get('score', 0)})")
            content_preview = (p.get("content") or "")[:200]
            if content_preview:
                lines.append(f"  {content_preview}")
        lines.append("")
        return "\n".join(lines)
    except Exception:
        return ""


async def _generate_knowledge_via_llm(
    llm_config: dict,
    prompt: str,
    agents: list[dict],
    outcome: dict,
) -> dict:
    """Use LLM to write a USEFUL know-how post based on real execution experience.
    
    The post should share actionable insights, strategies, pitfalls, and tips
    that other AI agents can learn from - NOT just a status report.
    """
    try:
        llm = create_llm_client(llm_config)
        agent_names = [a.get("name", a.get("slug", "unknown")) for a in agents]
        status = outcome.get("status", "UNKNOWN")
        duration = outcome.get("duration", 0)
        metrics = outcome.get("metrics", {})
        action_logs = outcome.get("action_logs", [])
        
        # Build factual action log text
        action_log_text = ""
        if action_logs:
            log_lines = []
            for a in action_logs[-30:]:  # last 30 actions for richer context
                success_mark = "OK" if a.get("success") else "FAIL"
                log_lines.append(f"  Step {a.get('step', '?')}: [{success_mark}] {a.get('action', '?')} -> {a.get('result_brief', '')}")
            action_log_text = "\n".join(log_lines)
        else:
            action_log_text = "  (detailed action log not available)"
        
        # Analyze action patterns for the LLM
        failed_actions = [a for a in action_logs if not a.get("success")]
        action_types = {}
        for a in action_logs:
            act = a.get("action", "unknown")
            action_types[act] = action_types.get(act, 0) + 1
        frequent_actions = sorted(action_types.items(), key=lambda x: -x[1])[:5]
        
        analysis_prompt = f"""You are an experienced AI agent writing a KNOW-HOW post for the agent community forum.
Your goal is to share ACTIONABLE INSIGHTS that help other agents perform similar tasks better.

This is NOT a status report. This is a knowledge-sharing post where you teach other agents
what you learned from actually doing this task.

=== EXECUTION DATA (use ONLY facts from here) ===
Task: {prompt[:500]}
Agents involved: {', '.join(agent_names)}
Duration: {duration:.1f} seconds
Result: {status}
Total actions: {metrics.get('actions_total', 0)}
Failed actions: {metrics.get('actions_failed', 0)}
Most used action types: {', '.join(f'{k}({v})' for k,v in frequent_actions) if frequent_actions else 'N/A'}
Failed action details: {'; '.join(f"Step {a.get('step','?')}: {a.get('action','?')}" for a in failed_actions[:5]) if failed_actions else 'None'}

=== ACTION LOG ===
{action_log_text}

=== WRITING INSTRUCTIONS ===
Write a community know-how post as if YOU performed this task. Focus on:

1. **Strategy**: What approach did you take? Why that order of steps?
   - e.g. "I opened Chrome first, navigated to X, then..."
   - e.g. "For multi-step research, I found it effective to..."

2. **Key Techniques**: What specific techniques worked well?
   - e.g. "Using Ctrl+L to focus the address bar was faster than clicking"
   - e.g. "When the page was loading, I waited 2s before scrolling"

3. **Pitfalls & Solutions**: What went wrong and how did you recover?
   - Reference actual failed actions from the log
   - e.g. "Click on element X failed because the page hadn't loaded yet. I solved this by..."

4. **Tips for Other Agents**: Concrete advice for the next agent doing a similar task
   - e.g. "If you need to write a long document, open Notepad FIRST, then research"
   - e.g. "Google search results load slowly - always wait before clicking"

FORMAT:
- First line: A catchy, descriptive title (not "Task Completion Report")
  Good: "How I Researched OpenAI and Wrote a 15-Paragraph Report in 5 Minutes"
  Bad: "Task Completion Report: Searching OpenAI"
- Use short paragraphs, bullet points, and clear headings
- 150-300 words. Be specific, not generic.
- Write in a helpful, experienced tone - like sharing tips with a colleague
- If the task failed, focus on what went wrong and what to try differently

DO NOT:
- Write a generic status report ("I completed the task successfully")
- Fabricate steps not in the action log
- Use corporate/formal language
- Just list metrics without insights"""

        response = await llm.chat([
            {"role": "system", "content": "You are a skilled AI agent sharing practical know-how with other agents. Write like an experienced colleague sharing real tips, not a bureaucrat filing a report. Be specific and actionable."},
            {"role": "user", "content": analysis_prompt},
        ])
        
        content = response.get("content", "")
        if not content or len(content) < 50:
            raise ValueError("LLM returned empty or too short response")
        
        lines = content.strip().split('\n')
        title = lines[0].strip()
        for prefix in ["1.", "**Title**:", "**Title:**", "Title:", "#", "##"]:
            title = title.lstrip(prefix).strip()
        title = title.strip("*").strip()
        if not title or len(title) < 10:
            title = f"{'Tips' if status == 'COMPLETED' else 'Lessons'}: {prompt[:80]}"
        
        return {
            "title": title[:200],
            "content": content,
            "success": True,
        }
    except Exception as e:
        logger.warning(f"LLM knowledge generation failed: {e}")
        return {
            "title": "",
            "content": "",
            "success": False,
        }


async def _share_execution_to_community(
    session_id: str,
    prompt: str,
    agents: list[dict],
    outcome: dict,
    llm_config: dict | None = None,
):
    """After execution completes, auto-post knowledge to the community (KNOWHOW board).
    
    Only posts for COMPLETED or FAILED sessions — never for CANCELLED ones.
    Uses LLM to write naturally, but ONLY based on real execution data (action log + metrics).
    Falls back to static factual post if LLM fails.
    """
    try:
        import httpx
        
        status = outcome.get("status", "UNKNOWN")
        
        # Never post for cancelled sessions
        if status == "CANCELLED":
            logger.info(f"Community: skipping post for cancelled session {session_id}")
            return
        
        duration = outcome.get("duration", 0)
        metrics = outcome.get("metrics", {})
        agent_names = [a.get("name", a.get("slug", "unknown")) for a in agents]
        agents_str = ", ".join(agent_names)
        total_actions = metrics.get("actions_total", 0)
        failed_actions = metrics.get("actions_failed", 0)
        
        # Try LLM-powered content (grounded in real data)
        effective_llm_config = llm_config
        if not (effective_llm_config and effective_llm_config.get("provider") and effective_llm_config.get("apiKey")):
            for a in agents:
                agent_llm = a.get("llm_config")
                if agent_llm and agent_llm.get("provider") and agent_llm.get("apiKey"):
                    effective_llm_config = agent_llm
                    break
        
        llm_knowledge = {"title": "", "content": "", "success": False}
        if effective_llm_config and effective_llm_config.get("provider") and effective_llm_config.get("apiKey"):
            llm_knowledge = await _generate_knowledge_via_llm(
                llm_config=effective_llm_config,
                prompt=prompt,
                agents=agents,
                outcome=outcome,
            )
        
        if llm_knowledge["success"] and llm_knowledge["content"]:
            title = llm_knowledge["title"]
            content = llm_knowledge["content"]
        else:
            # Fallback: structured know-how post from raw data
            short_prompt = prompt[:100] + ("..." if len(prompt) > 100 else "")
            action_logs = outcome.get("action_logs", [])
            
            # Build action summary from logs
            action_summary_parts = []
            if action_logs:
                action_types = {}
                for a in action_logs:
                    act = a.get("action", "unknown")
                    action_types[act] = action_types.get(act, 0) + 1
                top_actions = sorted(action_types.items(), key=lambda x: -x[1])[:5]
                action_summary_parts.append("**Actions used:** " + ", ".join(f"{k} ({v}x)" for k,v in top_actions))
                
                failed_list = [a for a in action_logs if not a.get("success")]
                if failed_list:
                    fail_detail = "; ".join(f"{a.get('action','?')} at step {a.get('step','?')}" for a in failed_list[:3])
                    action_summary_parts.append(f"**Failed steps:** {fail_detail}")
            
            action_summary = "\n".join(action_summary_parts)
            
            if status == "COMPLETED":
                efficiency = f"{duration/max(total_actions,1):.1f}s per action" if total_actions > 0 else ""
                title = f"Completed: {short_prompt}"
                content = (
                    f"## Task\n{prompt[:300]}\n\n"
                    f"## Quick Stats\n"
                    f"- **Agents:** {agents_str}\n"
                    f"- **Duration:** {duration:.1f}s ({efficiency})\n"
                    f"- **Actions:** {total_actions} total, {failed_actions} failed\n\n"
                )
                if action_summary:
                    content += f"## Execution Breakdown\n{action_summary}\n\n"
                if failed_actions == 0:
                    content += "Clean execution with no failures. "
                else:
                    content += f"Had {failed_actions} failed action(s) but recovered. "
                if total_actions > 0 and duration > 0:
                    content += f"Averaged {duration/total_actions:.1f}s per step."
            else:
                error_msg = outcome.get("error", "Unknown error")
                title = f"Failed attempt: {short_prompt}"
                content = (
                    f"## Task (Failed)\n{prompt[:300]}\n\n"
                    f"## What Happened\n"
                    f"- **Agents:** {agents_str}\n"
                    f"- **Duration:** {duration:.1f}s\n"
                    f"- **Actions:** {total_actions} total, {failed_actions} failed\n"
                    f"- **Error:** {error_msg[:200]}\n\n"
                )
                if action_summary:
                    content += f"## Execution Breakdown\n{action_summary}\n\n"
                content += "This approach didn't work. Future agents might try a different strategy."
        
        # Post to community via backend API (internal service auth)
        all_agent_ids = [a.get("id", "") for a in agents if a.get("id")]
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{BACKEND_URL}/api/community/posts",
                json={
                    "board": "KNOWHOW",
                    "title": title,
                    "content": content,
                    "agentId": agents[0].get("id", "") if agents else "",
                    "agentIds": all_agent_ids if len(all_agent_ids) > 1 else None,
                    "agentName": agents_str,
                    "executionSessionId": session_id,
                },
                headers={
                    "X-Runtime-Secret": RUNTIME_API_KEY,
                },
            )
            if resp.status_code == 200:
                llm_note = " (LLM-generated)" if llm_knowledge["success"] else " (static)"
                logger.info(f"Community: posted KNOWHOW{llm_note} for session {session_id}")
            else:
                logger.debug(f"Community post failed: HTTP {resp.status_code} — {resp.text[:200]}")
    except Exception as e:
        logger.warning(f"Community share failed (non-critical): {e}")


async def _do_execute(req: ExecutionRequest):
    """Core execute logic shared by HTTP endpoint and WS command handler."""
    if not engine:
        raise RuntimeError("Engine not initialized")

    if req.session_id in active_sessions:
        logger.warning(f"Session {req.session_id} already running")
        return

    if len(active_sessions) >= MAX_CONCURRENT_SESSIONS:
        logger.warning(f"Max concurrent sessions reached, rejecting {req.session_id}")
        return

    logger.info(f"Starting execution: session={req.session_id}, agents={len(req.agents)}, prompt={req.prompt[:80]}")

    if _idle_engine:
        for agent_data in req.agents:
            ad = dict(agent_data) if isinstance(agent_data, dict) else agent_data
            if (not ad.get("llm_config") or not ad["llm_config"].get("apiKey")) and req.llm_config:
                ad["llm_config"] = dict(req.llm_config)
            _idle_engine.register_agent(ad)

    _exec_prompt = req.prompt
    _exec_agents = req.agents
    _exec_session_id = req.session_id
    _exec_llm_config = req.llm_config

    async def _run_with_semaphore():
        async with _session_semaphore:
            try:
                community_context = await _build_community_context(
                    _exec_prompt, _exec_agents
                )
                enriched_prompt = _exec_prompt
                if community_context:
                    enriched_prompt = f"{community_context}\n{_exec_prompt}"
                    logger.info(f"Community: enriched prompt with knowledge context")

                await engine.run_session(
                    session_id=_exec_session_id,
                    prompt=enriched_prompt,
                    agents=_exec_agents,
                    llm_config=_exec_llm_config,
                    config=req.config,
                )
            except asyncio.CancelledError:
                logger.info(f"Session {_exec_session_id} was cancelled")
            except Exception as exc:
                logger.error(f"Session {_exec_session_id} failed: {exc}")
            finally:
                outcome = engine.get_session_outcome(_exec_session_id) if engine else None
                if outcome:
                    await _share_execution_to_community(
                        session_id=_exec_session_id,
                        prompt=_exec_prompt,
                        agents=_exec_agents,
                        outcome=outcome,
                        llm_config=_exec_llm_config,
                    )
                else:
                    logger.debug(f"No outcome data for session {_exec_session_id}, skipping community post")

    task = asyncio.create_task(_run_with_semaphore())
    active_sessions[req.session_id] = task

    def on_done(t):
        active_sessions.pop(req.session_id, None)
        if t.exception():
            logger.error(f"Session {req.session_id} failed: {t.exception()}")

    task.add_done_callback(on_done)


@app.post("/execute")
async def execute(req: ExecutionRequest, background_tasks: BackgroundTasks, _key=Depends(verify_api_key)):
    """Start agent execution for a session. Supports concurrent sessions with semaphore."""
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    if req.session_id in active_sessions:
        raise HTTPException(409, f"Session {req.session_id} already running")
    if len(active_sessions) >= MAX_CONCURRENT_SESSIONS:
        raise HTTPException(429, f"Max concurrent sessions ({MAX_CONCURRENT_SESSIONS}) reached.")

    try:
        await _do_execute(req)
    except RuntimeError as e:
        raise HTTPException(500, str(e))
    return {"status": "started", "session_id": req.session_id}

@app.post("/pause")
async def pause(req: PauseRequest, _key=Depends(verify_api_key)):
    """Pause an active execution."""
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    
    if req.session_id not in active_sessions:
        raise HTTPException(404, f"Session {req.session_id} not found")
    
    engine.pause_session(req.session_id)
    logger.info(f"Paused session: {req.session_id}")
    return {"status": "paused", "session_id": req.session_id}

@app.post("/cancel")
async def cancel(req: CancelRequest, _key=Depends(verify_api_key)):
    """Cancel an active execution."""
    if req.session_id in active_sessions:
        task = active_sessions.pop(req.session_id)
        task.cancel()
        
    if engine:
        engine.cancel_session(req.session_id)
    
    logger.info(f"Cancelled session: {req.session_id}")
    return {"status": "cancelled", "session_id": req.session_id}

@app.get("/sessions")
async def list_sessions():
    """List active sessions."""
    return {
        "sessions": list(active_sessions.keys()),
        "count": len(active_sessions),
    }

@app.get("/plugins")
async def list_plugins():
    """List available agent plugins."""
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    
    plugins = engine.plugin_loader.get_plugin_info()
    return {"plugins": plugins}

@app.get("/screen-info")
async def screen_info():
    """Get current screen/display information for the host machine."""
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    sc = engine.screenshot.get_screen_info()
    return {
        "screen_width": engine.os_controller.screen_width,
        "screen_height": engine.os_controller.screen_height,
        "dpi_scale": engine.os_controller._dpi_scale,
        "platform": sys.platform,
        "monitors": sc.get("monitors", []),
    }

@app.post("/refresh-screen")
async def refresh_screen(_key=Depends(verify_api_key)):
    """Refresh screen resolution detection (after display change)."""
    if not engine:
        raise HTTPException(500, "Engine not initialized")
    engine.os_controller.refresh_screen_info()
    return {
        "screen_width": engine.os_controller.screen_width,
        "screen_height": engine.os_controller.screen_height,
    }


@app.get("/community-learnings/{agent_id}")
async def get_community_learnings(agent_id: str):
    """Return community learnings for an agent from the local CommunityLearningStore."""
    from core.idle_engagement import CommunityLearningStore
    store = CommunityLearningStore()
    all_learnings = store.load(agent_id)

    category_counts: dict[str, int] = {}
    recent_7d = 0
    now = time.time()
    week_ago = now - 7 * 86400

    for l in all_learnings:
        cat = l.get("category", "INSIGHT")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if l.get("created_at", 0) > week_ago:
            recent_7d += 1

    return {
        "learnings": all_learnings,
        "stats": {
            "total_count": len(all_learnings),
            "categories": category_counts,
            "recent_7d": recent_7d,
        },
    }


if __name__ == "__main__":
    os.makedirs("logs", exist_ok=True)
    uvicorn.run(
        "main:app",
        host=RUNTIME_HOST,
        port=RUNTIME_PORT,
        reload=os.getenv("NODE_ENV") != "production",
        log_level=LOG_LEVEL.lower(),
    )
