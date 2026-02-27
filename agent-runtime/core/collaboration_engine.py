"""
Collaboration Engine — Real-time multi-agent cooperative execution system.

Instead of a sequential planner→agent pipeline, this engine enables:
- Shared workspace: all agents see the same live screen
- Message bus: agents communicate intentions, discoveries, and requests to each other
- Role negotiation: agents claim tasks based on their capabilities
- Conflict resolution: prevents two agents from clicking different things simultaneously
- Consensus protocol: agents agree on next action before executing
- Planner as advisor: planner generates guidelines, not strict orders

Architecture:
  ┌─────────────────────────────────────────────────┐
  │              CollaborationBus                    │
  │  ┌──────┐  ┌──────┐  ┌──────┐                  │
  │  │Agent1│◄─┤ Msg  ├─►│Agent2│                  │
  │  └──┬───┘  │ Bus  │  └──┬───┘                  │
  │     │      └──┬───┘     │                      │
  │     │         │         │                      │
  │  ┌──▼─────────▼─────────▼──┐                   │
  │  │   SharedWorkspace       │                   │
  │  │  (screen, state, locks) │                   │
  │  └─────────────────────────┘                   │
  └─────────────────────────────────────────────────┘
"""

import asyncio
import json
import re
import time
import base64
from typing import Optional, Any
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

# ── Import shared prompt constants directly from core.prompts (no circular dependency).
from core.prompts import (
    TaskType,
    ACTION_DEFINITIONS,
    VALID_ACTIONS as _VALID_ACTIONS,
    TASK_STRATEGY_PROMPTS,
    BROWSER_GUIDE,
    COMPLETION_RULES,
    WINDOWS_APP_INTELLIGENCE,
    _is_ogenti_screen,
    APP_LAUNCH_GUIDE,
    PRECONDITION_RULES,
    SELF_DETECTION_WARNING,
    _BROWSER,
    _BROWSER_DISPLAY,
)

try:
    from core.shared_workspace import SharedWorkspace
    HAS_SHARED_WORKSPACE = True
except ImportError:
    HAS_SHARED_WORKSPACE = False
    SharedWorkspace = None

# ── Lazy import: only TaskAnalyzer is loaded at call time from core.engine
#    to break the engine ↔ collaboration_engine circular dependency.
HAS_TASK_INTELLIGENCE = False
TaskAnalyzer = None


def _lazy_load_engine_symbols():
    """Lazy-load TaskAnalyzer from core.engine to avoid circular import."""
    global HAS_TASK_INTELLIGENCE, TaskAnalyzer
    if HAS_TASK_INTELLIGENCE:
        return True
    try:
        from core.engine import TaskAnalyzer as _TA
        TaskAnalyzer = _TA
        HAS_TASK_INTELLIGENCE = True
        return True
    except ImportError:
        return False

try:
    from core.agent_intelligence import (
        ScreenStateClassifier, ScreenState, ScreenAnalysis, AutoActionResolver,
        ActionValidator, StuckDetector,
        TaskProgressTracker, ContextAccumulator,
    )
    HAS_INTELLIGENCE = True
except ImportError:
    HAS_INTELLIGENCE = False

try:
    from core.provider_prompt_adapter import adapt_system_prompt, get_refusal_recovery_prompt
except ImportError:
    # Fallback: no adaptation
    def adapt_system_prompt(raw, provider): return raw
    def get_refusal_recovery_prompt(provider, task, attempt): return "Continue with the task. Output ACTION and PARAMS."


class MessageType(str, Enum):
    """Types of messages agents can exchange."""
    OBSERVATION = "observation"        # "I see X on screen"
    INTENTION = "intention"            # "I plan to do X"
    ACTION_RESULT = "action_result"    # "I did X, result was Y"
    REQUEST = "request"                # "Can agent X do Y?"
    RESPONSE = "response"             # Response to a request
    DISCOVERY = "discovery"            # "I found something useful: ..."
    CONFLICT = "conflict"              # "I need the mouse/keyboard"
    CONSENSUS = "consensus"            # "I agree/disagree with plan"
    STATUS = "status"                  # "I'm done / blocked / need help"
    HANDOFF = "handoff"               # "Agent X, please take over task Y"


@dataclass
class AgentMessage:
    """A message exchanged between agents."""
    sender_id: str
    sender_name: str
    msg_type: MessageType
    content: str
    target_agent: Optional[str] = None  # None = broadcast to all
    metadata: dict = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    msg_id: str = ""

    def __post_init__(self):
        if not self.msg_id:
            self.msg_id = f"{self.sender_id}_{int(self.timestamp * 1000)}"

    def to_dict(self) -> dict:
        return {
            "id": self.msg_id,
            "sender": self.sender_id,
            "sender_name": self.sender_name,
            "type": self.msg_type.value,
            "content": self.content,
            "target": self.target_agent,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }

    def to_llm_text(self) -> str:
        """Format for inclusion in LLM context."""
        target = f" → @{self.target_agent}" if self.target_agent else ""
        return f"[{self.sender_name}{target}] ({self.msg_type.value}) {self.content}"


@dataclass
class SharedScreenState:
    """The shared view of the screen that all agents see."""
    screenshot_b64: Optional[str] = None
    screen_width: int = 1920
    screen_height: int = 1080
    som_description: str = ""
    som_result: Any = None
    last_updated: float = field(default_factory=time.time)
    active_windows: list[str] = field(default_factory=list)
    # Track what each agent last observed
    agent_observations: dict = field(default_factory=dict)


@dataclass
class ActionLock:
    """Prevents multiple agents from executing OS actions simultaneously."""
    holder: Optional[str] = None  # agent_id holding the lock
    acquired_at: float = 0
    timeout: float = 10.0  # seconds before auto-release
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    @property
    def is_locked(self) -> bool:
        if not self.holder:
            return False
        if time.time() - self.acquired_at > self.timeout:
            logger.warning(
                f"[ActionLock] Auto-releasing lock held by '{self.holder}' "
                f"after {self.timeout}s timeout (possible agent crash)"
            )
            self.holder = None
            return False
        return True


class CollaborationBus:
    """
    Central message bus for agent-to-agent communication.
    Manages shared state, message routing, and action coordination.
    
    v2 — Phase-based execution:
    - Agents are assigned to PHASES (1, 2, 3...)
    - Phase N+1 agents SLEEP until all Phase N agents finish
    - Handoff messages carry structured data (findings, URLs, etc.)
    - No more busy-loop waiting
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.agents: dict[str, dict] = {}  # agent_id → {name, capabilities, status, ...}
        self.message_history: list[AgentMessage] = []
        self.shared_screen = SharedScreenState()
        self.action_lock = ActionLock()
        self.guidelines: list[str] = []  # Planner guidelines
        self.task_claims: dict[str, str] = {}  # task_desc → agent_id
        self.completed_tasks: list[str] = []
        self._subscribers: dict[str, asyncio.Queue] = {}  # agent_id → message queue
        self._callback: Optional[Any] = None  # Backend callback function

        # ── Phase-based execution state ──
        self.agent_phases: dict[str, int] = {}       # agent_id → phase number (1-based)
        self.phase_assignments: dict[str, str] = {}  # agent_id → specific task assignment text
        self.current_phase: int = 1                   # Currently active phase
        self._phase_events: dict[int, asyncio.Event] = {}  # phase → event signaled when phase starts
        self._handoff_data: dict[str, list[dict]] = {}     # agent_id → [{type, content, from_agent}]
        self._phase_results: dict[int, list[str]] = {}     # phase → collected results/findings

    def register_agent(self, agent_id: str, agent_name: str, capabilities: list[str]):
        """Register an agent on the collaboration bus."""
        self.agents[agent_id] = {
            "name": agent_name,
            "capabilities": capabilities,
            "status": "active",
            "joined_at": time.time(),
            "actions_taken": 0,
            "last_active": time.time(),
        }
        self._subscribers[agent_id] = asyncio.Queue()
        self._handoff_data[agent_id] = []
        logger.info(f"[Collab] Agent registered: {agent_name} ({agent_id})")

    def assign_phase(self, agent_id: str, phase: int, task_assignment: str = ""):
        """Assign an agent to an execution phase. Phase 1 runs first."""
        self.agent_phases[agent_id] = phase
        self.phase_assignments[agent_id] = task_assignment
        # Ensure phase event exists
        if phase not in self._phase_events:
            self._phase_events[phase] = asyncio.Event()
        if phase not in self._phase_results:
            self._phase_results[phase] = []
        # Phase 1 starts immediately
        if phase == 1:
            self._phase_events[1].set()
        logger.info(f"[Collab] {agent_id} assigned to phase {phase}: {task_assignment[:80]}")

    async def wait_for_phase(self, agent_id: str, timeout: float = 300.0) -> bool:
        """Block until this agent's phase is active. Returns False on timeout."""
        phase = self.agent_phases.get(agent_id, 1)
        if phase <= self.current_phase:
            return True  # Already active
        event = self._phase_events.get(phase)
        if not event:
            return True  # No phase tracking, run immediately
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            logger.warning(f"[Collab] {agent_id} timed out waiting for phase {phase}")
            return False

    def advance_phase(self, completed_phase: int):
        """Called when all agents in a phase finish. Activates the next phase."""
        next_phase = completed_phase + 1
        self.current_phase = next_phase
        event = self._phase_events.get(next_phase)
        if event:
            event.set()
        logger.info(f"[Collab] Phase {completed_phase} complete → Phase {next_phase} active")

    def send_handoff(self, from_agent_id: str, to_agent_id: str, data: dict):
        """Send structured handoff data to another agent (findings, URLs, etc.)."""
        handoff = {
            "type": data.get("type", "general"),
            "content": data.get("content", ""),
            "from_agent": from_agent_id,
            "from_name": self.agents.get(from_agent_id, {}).get("name", from_agent_id),
            "timestamp": time.time(),
        }
        if to_agent_id in self._handoff_data:
            self._handoff_data[to_agent_id].append(handoff)
        # Also store in phase results
        phase = self.agent_phases.get(from_agent_id, 1)
        if phase in self._phase_results:
            self._phase_results[phase].append(data.get("content", ""))
        logger.info(f"[Collab] Handoff: {from_agent_id} → {to_agent_id}: {data.get('type', '?')}")

    def get_handoff_data(self, agent_id: str) -> list[dict]:
        """Get all handoff data sent to this agent."""
        return self._handoff_data.get(agent_id, [])

    def get_phase_results(self, phase: int) -> list[str]:
        """Get all results collected during a phase."""
        return self._phase_results.get(phase, [])

    def is_phase_complete(self, phase: int) -> bool:
        """Check if all agents in a given phase have completed."""
        agents_in_phase = [aid for aid, p in self.agent_phases.items() if p == phase]
        if not agents_in_phase:
            return True
        return all(
            self.agents.get(aid, {}).get("status") in ("completed", "standby")
            for aid in agents_in_phase
        )

    def unregister_agent(self, agent_id: str):
        """Remove an agent from the collaboration bus."""
        self.agents.pop(agent_id, None)
        self._subscribers.pop(agent_id, None)

    async def send_message(self, message: AgentMessage):
        """Send a message from one agent to others."""
        self.message_history.append(message)
        # Cap history to prevent unbounded growth
        if len(self.message_history) > 500:
            self.message_history = self.message_history[-300:]

        # Route to specific agent or broadcast
        if message.target_agent:
            queue = self._subscribers.get(message.target_agent)
            if queue:
                await queue.put(message)
        else:
            for agent_id, queue in self._subscribers.items():
                if agent_id != message.sender_id:
                    await queue.put(message)

        # Log to backend if callback available
        if self._callback:
            await self._callback(
                self.session_id, "agent_message",
                {"message": message.to_dict()}
            )

    async def receive_messages(self, agent_id: str, timeout: float = 0.5) -> list[AgentMessage]:
        """Receive pending messages for an agent (non-blocking with short timeout)."""
        queue = self._subscribers.get(agent_id)
        if not queue:
            return []

        messages = []
        try:
            while True:
                msg = queue.get_nowait()
                messages.append(msg)
        except asyncio.QueueEmpty:
            pass

        if not messages:
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=timeout)
                messages.append(msg)
            except (asyncio.TimeoutError, asyncio.QueueEmpty):
                pass

        return messages

    async def acquire_action_lock(self, agent_id: str, timeout: float = 5.0) -> bool:
        """Acquire exclusive access to OS actions (mouse/keyboard).
        
        Uses asyncio.wait_for with a timeout to prevent indefinite blocking.
        If timeout expires, force-releases the lock from the previous holder
        (assumed crashed) and retries once.
        """
        # Fast path: already holding the lock
        if self.action_lock.holder == agent_id:
            return True

        try:
            acquired = await asyncio.wait_for(
                self._try_acquire_lock(agent_id), timeout=timeout
            )
            return acquired
        except asyncio.TimeoutError:
            stale_holder = self.action_lock.holder
            logger.warning(
                f"[ActionLock] Timeout ({timeout}s) acquiring lock for '{agent_id}'. "
                f"Force-releasing lock from '{stale_holder}' (likely crashed/stuck)."
            )
            # Force-release the stale lock
            self.action_lock.holder = None
            # Retry once after force-release
            try:
                acquired = await asyncio.wait_for(
                    self._try_acquire_lock(agent_id), timeout=2.0
                )
                return acquired
            except asyncio.TimeoutError:
                logger.error(f"[ActionLock] Failed to acquire lock for '{agent_id}' even after force-release.")
                return False

    async def _try_acquire_lock(self, agent_id: str) -> bool:
        """Internal helper: spin until the action lock is free, then grab it."""
        while True:
            if not self.action_lock.is_locked:
                self.action_lock.holder = agent_id
                self.action_lock.acquired_at = time.time()
                return True
            if self.action_lock.holder == agent_id:
                return True
            await asyncio.sleep(0.1)

    def release_action_lock(self, agent_id: str):
        """Release the OS action lock."""
        if self.action_lock.holder == agent_id:
            self.action_lock.holder = None

    def update_screen(self, screenshot_b64: str, som_result=None, som_description: str = ""):
        """Update the shared screen state for all agents."""
        self.shared_screen.screenshot_b64 = screenshot_b64
        self.shared_screen.last_updated = time.time()
        if som_result:
            self.shared_screen.som_result = som_result
        if som_description:
            self.shared_screen.som_description = som_description

    def get_screen(self) -> SharedScreenState:
        """Get the current shared screen state."""
        return self.shared_screen

    def claim_task(self, agent_id: str, task_description: str) -> bool:
        """Agent claims a task. Returns False if already claimed by another."""
        if task_description in self.task_claims:
            return self.task_claims[task_description] == agent_id
        self.task_claims[task_description] = agent_id
        return True

    def complete_task(self, task_description: str):
        """Mark a task as completed."""
        self.completed_tasks.append(task_description)
        self.task_claims.pop(task_description, None)

    def get_recent_messages(self, agent_id: str, count: int = 20) -> list[str]:
        """Get recent message history formatted for LLM context."""
        recent = self.message_history[-count:]
        return [m.to_llm_text() for m in recent]

    def get_agent_status_summary(self) -> str:
        """Get a summary of all agents' current status."""
        lines = []
        for aid, info in self.agents.items():
            status = info.get("status", "unknown")
            actions = info.get("actions_taken", 0)
            lines.append(f"  - {info['name']} ({aid}): {status}, {actions} actions taken")
        return "\n".join(lines)

    def get_collaboration_context(self, agent_id: str) -> str:
        """Build a collaboration context string for an agent's LLM prompt."""
        lines = []

        # Phase info for this agent
        my_phase = self.agent_phases.get(agent_id, 0)
        my_assignment = self.phase_assignments.get(agent_id, "")
        if my_phase:
            lines.append(f"═══ YOUR PHASE: {my_phase} (current active: {self.current_phase}) ═══")
            if my_assignment:
                lines.append(f"  YOUR ASSIGNMENT: {my_assignment}")

        # Guidelines from planner
        if self.guidelines:
            lines.append("\n═══ PLANNER GUIDELINES ═══")
            for i, g in enumerate(self.guidelines, 1):
                lines.append(f"  {i}. {g}")

        # Handoff data received from previous phase agents
        handoffs = self.get_handoff_data(agent_id)
        if handoffs:
            lines.append(f"\n═══ HANDOFF DATA FROM PREVIOUS AGENTS ═══")
            for h in handoffs:
                lines.append(f"  [{h['from_name']}] ({h['type']}): {h['content'][:300]}")

        # Previous phase results
        if my_phase > 1:
            prev_results = self.get_phase_results(my_phase - 1)
            if prev_results:
                lines.append(f"\n═══ PHASE {my_phase - 1} RESULTS (use these!) ═══")
                for r in prev_results:
                    lines.append(f"  • {r[:200]}")

        # Other agents present
        other_agents = []
        for aid, info in self.agents.items():
            if aid == agent_id:
                continue
            phase = self.agent_phases.get(aid, "?")
            status = info.get("status", "unknown")
            other_agents.append(f"{info['name']} (phase {phase}, {status})")
        if other_agents:
            lines.append(f"\n═══ COLLABORATING AGENTS ═══")
            for oa in other_agents:
                lines.append(f"  - {oa}")

        # Recent inter-agent messages (only last 5 to reduce noise)
        recent = self.get_recent_messages(agent_id, count=10)
        if recent:
            lines.append(f"\n═══ RECENT TEAM COMMUNICATION ═══")
            for msg in recent[-5:]:
                lines.append(f"  {msg}")

        # Completed tasks
        if self.completed_tasks:
            lines.append(f"\n═══ COMPLETED TASKS ═══")
            for t in self.completed_tasks[-5:]:
                lines.append(f"  ✓ {t}")

        return "\n".join(lines) if lines else ""


class CollaborativeSession:
    """
    Manages a collaborative execution session where multiple agents
    work together on the same screen, each potentially using a DIFFERENT LLM.
    
    Multi-brain architecture:
    - Each agent can have its own LLM provider/model (GPT-4, Claude, Gemini, etc.)
    - Agents communicate via the CollaborationBus (shared observations, discoveries)
    - This creates genuine collaboration: different AI brains contribute unique perspectives
    """

    def __init__(
        self,
        session_id: str,
        engine,  # ExecutionEngine reference
        llm,     # Default LLM client (fallback)
        bus: Optional[CollaborationBus] = None,
        agent_llm_map: Optional[dict] = None,  # agent_id → LLMClient
    ):
        self.session_id = session_id
        self.engine = engine
        self.llm = llm  # Session-level default
        self.agent_llm_map = agent_llm_map or {}  # Per-agent LLMs
        self.bus = bus or CollaborationBus(session_id)
        self.bus._callback = engine.callback
        self._agent_tasks: dict[str, asyncio.Task] = {}
        self._runtime_config: dict = {}

        # Shared workspace for real multi-brain collaboration
        self.workspace = SharedWorkspace(session_id) if HAS_SHARED_WORKSPACE else None

    def get_agent_llm(self, agent_id: str):
        """Get the LLM client for a specific agent (per-agent → default fallback)."""
        return self.agent_llm_map.get(agent_id, self.llm)

    async def run_collaborative(
        self,
        prompt: str,
        agents: list[dict],
        config: dict,
    ):
        """
        Run all agents collaboratively on the same task.

        v2 — Phase-based execution:
        1. Planner generates PHASE ASSIGNMENTS (not vague guidelines)
        2. Agents assigned to phases: Phase 1 runs first, Phase 2 waits
        3. Phase 1 agents finish → handoff data sent → Phase 2 agents wake up
        4. Phase 2 agents receive findings/context from Phase 1
        5. No more idle busy-looping — agents sleep until their phase starts
        """
        await self.engine.log(self.session_id, "═══ Collaborative Execution Mode ═══")
        await self.engine.log(self.session_id, f"Agents: {len(agents)} | Prompt: {prompt[:150]}")

        # Persist runtime config for helper methods (screen capture / semantic SoM fallback)
        self._runtime_config = config or {}

        # Phase 1: Generate PHASE-BASED role assignments
        phase_plan = await self._generate_phase_plan(prompt, agents)
        await self.engine.log(self.session_id, f"Phase plan: {len(phase_plan)} assignments")

        # Phase 2: Register all agents on the bus WITH phase assignments
        for agent_data in agents:
            agent_id = agent_data.get("id", f"agent_{len(self.bus.agents)}")
            agent_name = agent_data.get("name", "Unknown")
            capabilities = []
            if agent_data.get("capabilities"):
                try:
                    caps = agent_data["capabilities"]
                    capabilities = json.loads(caps) if isinstance(caps, str) else caps
                except (json.JSONDecodeError, TypeError):
                    capabilities = []
            self.bus.register_agent(agent_id, agent_name, capabilities)

            # Register agent's LLM in shared workspace for attribution
            if self.workspace:
                agent_llm_cfg = agent_data.get("llm_config")
                if agent_llm_cfg and agent_llm_cfg.get("provider"):
                    self.workspace.register_agent_llm(
                        agent_id,
                        agent_llm_cfg["provider"],
                        agent_llm_cfg.get("model", "unknown"),
                    )
                else:
                    # Using session default LLM
                    self.workspace.register_agent_llm(agent_id, "default", "session-llm")

            # Assign phase from plan
            assignment = phase_plan.get(agent_name, phase_plan.get(agent_id, {}))
            if not assignment:
                # Try fuzzy match
                for key, val in phase_plan.items():
                    if key.lower() in agent_name.lower() or agent_name.lower() in key.lower():
                        assignment = val
                        break
            if isinstance(assignment, dict):
                phase_num = assignment.get("phase", 1)
                task_desc = assignment.get("task", "")
                standby = assignment.get("standby", False)
            else:
                phase_num = 1
                task_desc = str(assignment) if assignment else ""
                standby = False

            if standby:
                self.bus.agents[agent_id]["status"] = "standby"
                self.bus.assign_phase(agent_id, 999, "STANDBY — not needed for this task")
                await self.engine.log(self.session_id, f"[{agent_name}] assigned STANDBY (not needed)")
            else:
                self.bus.assign_phase(agent_id, phase_num, task_desc)
                await self.engine.log(self.session_id, f"[{agent_name}] Phase {phase_num}: {task_desc[:100]}")

        # Store guidelines as text for context
        self.bus.guidelines = [
            f"[Phase {a.get('phase', '?')}] {name} → {a.get('task', '?')}"
            for name, a in phase_plan.items()
            if isinstance(a, dict) and not a.get("standby")
        ]

        # Phase 3: Capture initial shared screen
        await self._update_shared_screen()

        # Phase 4: Launch all agents concurrently (phase-based agents will sleep)
        agent_coros = []
        for agent_data in agents:
            agent_id = agent_data.get("id", "unknown")
            agent_name = agent_data.get("name", "Unknown")
            agent_slug = agent_data.get("slug", "")

            # Skip standby agents entirely
            if self.bus.agents.get(agent_id, {}).get("status") == "standby":
                await self.engine.log(self.session_id, f"[{agent_name}] Skipping — STANDBY")
                continue

            coro = self._run_collaborative_agent(
                agent_id, agent_name, agent_slug,
                prompt, config
            )
            agent_coros.append((agent_id, agent_name, coro))

        await self.engine.log(self.session_id, f"Launching {len(agent_coros)} agents (phase-based)...")

        max_time = config.get("maxExecutionTime", 1800000) / 1000
        try:
            results = await asyncio.wait_for(
                asyncio.gather(*[c for _, _, c in agent_coros], return_exceptions=True),
                timeout=max_time,
            )
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    _, agent_name, _ = agent_coros[i]
                    logger.error(f"[Collab] {agent_name} raised: {type(result).__name__}: {result}")
                    await self.engine.log(
                        self.session_id,
                        f"[{agent_name}] FATAL ERROR: {type(result).__name__}: {result}",
                        "ERROR", "AGENT",
                    )
        except asyncio.TimeoutError:
            await self.engine.log(self.session_id, "Collaboration timeout reached", "WARN")

        # Phase 5: Synthesis
        await self._synthesize_results(prompt)

    async def _generate_phase_plan(self, prompt: str, agents: list[dict]) -> dict:
        """
        Generate PHASE-BASED role assignments with structured task decomposition.
        
        Returns: {agent_name: {phase: int, task: str, standby: bool}}
        
        Key improvement over v1:
        - Tasks are sequential (research THEN write), not parallel
        - Irrelevant agents are put on STANDBY (no busy-looping)
        - Each agent gets a concrete assignment, not vague guidelines
        """
        agent_descs = []
        for a in agents:
            caps = a.get("capabilities", [])
            if isinstance(caps, str):
                try:
                    caps = json.loads(caps)
                except (json.JSONDecodeError, TypeError):
                    caps = []
            agent_slug = a.get("slug", a.get("name", "").lower().replace(" ", "-"))
            tier_info = ""
            domain = "general"
            try:
                from core.agent_registry import get_agent_profile
                p = get_agent_profile(agent_slug)
                tier_info = f" [Tier {p.tier}, Domain: {p.domain}]"
                domain = p.domain
            except ImportError:
                pass
            agent_descs.append(f"- {a.get('name', '?')}{tier_info} (domain: {domain})")

        system = """You are a task coordinator for a team of AI agents on a shared Windows computer.
Generate a PHASE-BASED execution plan.

CRITICAL RULES:
1. Tasks that DEPEND on each other MUST be in SEQUENTIAL phases.
   Example: "Research X and write report" → Phase 1: Research, Phase 2: Write report
2. An agent whose domain is NOT relevant → set "standby": true (they do NOT run at all)
3. NEVER put two agents in the same phase if they'd use different apps simultaneously.
   Two agents clicking/typing at the same time on one computer = DISASTER.
4. For research+write tasks: Researcher = Phase 1, Writer/Automation = Phase 2
5. For download tasks: Researcher = Phase 1 (find link), Automation = Phase 2 (download)
6. Give each agent a SPECIFIC deliverable, not "help with" or "assist".
7. Phase 2 agents will receive Phase 1 findings automatically via handoff.

Output ONLY valid JSON object like:
{
  "AgentName1": {"phase": 1, "task": "Open Chrome, search Google for X, visit 3 sources, collect findings about Y", "standby": false},
  "AgentName2": {"phase": 2, "task": "Open Notepad, write a report using Phase 1 findings, save as report.txt", "standby": false},
  "AgentName3": {"phase": 999, "task": "", "standby": true}
}

No markdown. No explanation. Just JSON."""

        user_msg = f"Task: {prompt}\n\nAvailable agents:\n" + "\n".join(agent_descs)

        try:
            resp = await self.llm.chat(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
            )
            raw = resp.get("content", "{}")
            text = raw.strip()
            if text.startswith("```"):
                lines = text.split("\n")
                text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                result = json.loads(text[start:end])
                # Validate structure
                for name, assignment in result.items():
                    if isinstance(assignment, dict):
                        assignment.setdefault("phase", 1)
                        assignment.setdefault("task", "")
                        assignment.setdefault("standby", False)
                return result
            return self._fallback_phase_plan(prompt, agents)
        except Exception as e:
            logger.warning(f"Failed to generate phase plan: {e}")
            return self._fallback_phase_plan(prompt, agents)

    def _fallback_phase_plan(self, prompt: str, agents: list[dict]) -> dict:
        """Fallback: detect task type and assign phases heuristically."""
        prompt_lower = prompt.lower()
        
        # Detect if task has sequential phases
        is_research = any(kw in prompt_lower for kw in [
            "research", "search", "find", "조사", "검색", "찾아", "알아봐",
        ])
        is_write = any(kw in prompt_lower for kw in [
            "report", "write", "보고서", "작성", "메모", "문서",
        ])
        is_download = any(kw in prompt_lower for kw in [
            "download", "다운로드", "다운", "받아", "설치",
        ])

        plan = {}
        for a in agents:
            name = a.get("name", "Unknown")
            slug = a.get("slug", "")
            domain = "general"
            try:
                from core.agent_registry import get_agent_profile
                p = get_agent_profile(slug)
                domain = p.domain
            except (ImportError, Exception):
                pass

            if is_research and is_write:
                # Research + Write → sequential phases
                if domain == "research":
                    plan[name] = {"phase": 1, "task": f"Open Chrome, search for information, visit sources, collect findings", "standby": False}
                elif domain in ("automation", "writing", "general"):
                    plan[name] = {"phase": 2, "task": f"Open Notepad, write report using Phase 1 findings, save file", "standby": False}
                else:
                    plan[name] = {"phase": 999, "task": "", "standby": True}
            elif is_research:
                if domain == "research":
                    plan[name] = {"phase": 1, "task": f"Research the topic thoroughly", "standby": False}
                else:
                    plan[name] = {"phase": 999, "task": "", "standby": True}
            elif is_download:
                if domain == "research":
                    plan[name] = {"phase": 1, "task": f"Open Chrome, find download link", "standby": False}
                elif domain in ("automation", "general"):
                    plan[name] = {"phase": 2, "task": f"Download the file using the link from Phase 1", "standby": False}
                else:
                    plan[name] = {"phase": 999, "task": "", "standby": True}
            else:
                # Default: all agents phase 1
                plan[name] = {"phase": 1, "task": f"Complete the task: {prompt[:100]}", "standby": False}

        return plan

    _ogenti_consecutive_collab = 0  # Track consecutive Ogenti detections

    async def _update_shared_screen(self):
        """Capture fresh screen and update shared state."""
        try:
            # ── PRE-SCREENSHOT: Minimize all Ogenti windows via Win32 API ──
            import sys
            if sys.platform == "win32" and self._ogenti_consecutive_collab < 3:
                try:
                    import ctypes
                    import ctypes.wintypes
                    user32 = ctypes.windll.user32
                    SW_MINIMIZE = 6
                    ogenti_kw = ['ogenti', 'electron']

                    @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
                    def _minimize_ogenti_cb(hwnd, _lp):
                        if not user32.IsWindowVisible(hwnd):
                            return True
                        length = user32.GetWindowTextLengthW(hwnd)
                        if length == 0:
                            return True
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.lower()
                        if any(kw in title for kw in ogenti_kw):
                            user32.ShowWindow(hwnd, SW_MINIMIZE)
                            logger.debug(f"[Collab] Minimized Ogenti window: {buf.value}")
                        return True

                    user32.EnumWindows(_minimize_ogenti_cb, 0)
                    import time as _t
                    _t.sleep(0.15)
                except Exception as _e:
                    logger.debug(f"[Collab] Ogenti minimize failed: {_e}")

            som_result = None
            screen_b64 = None
            som_desc = ""

            if self.engine._som and self.engine._som.enabled:
                sr = self.engine._som.capture_som()
                if sr and sr.annotated_image:
                    som_result = sr
                    screen_b64 = base64.b64encode(sr.annotated_image).decode("utf-8")
                    som_desc = sr.description or ""

            if not screen_b64:
                img = self.engine.screenshot.capture()
                if img:
                    screen_b64 = base64.b64encode(img).decode("utf-8")

            # Semantic SoM fallback (LLM-vision element detection)
            if (
                (not som_result)
                and screen_b64
                and getattr(self.engine, "_semantic_som", None)
                and getattr(self.engine, "_semantic_som_config_from_runtime", None)
            ):
                try:
                    sem_cfg = self.engine._semantic_som_config_from_runtime(self._runtime_config or {})
                    if sem_cfg and getattr(sem_cfg, "enabled", False):
                        ssr = await self.engine._semantic_som.capture_semantic_som(
                            self.llm, screen_b64, sem_cfg,
                            native_width=self.engine.os_controller.screen_width,
                            native_height=self.engine.os_controller.screen_height,
                        )
                        if ssr:
                            som_result = ssr
                            som_desc = ssr.description or som_desc
                except Exception:
                    pass

            if screen_b64:
                self.bus.update_screen(screen_b64, som_result, som_desc)

            await self.engine.send_screenshot(self.session_id)
        except Exception as e:
            logger.error(f"[Collab] Screen update error: {e}")

    async def _run_collaborative_agent(
        self,
        agent_id: str,
        agent_name: str,
        agent_slug: str,
        prompt: str,
        config: dict,
    ):
        """Run a single agent in collaborative mode with tier enforcement."""
        # ── Lazy import to resolve circular dependency (engine ↔ collaboration_engine) ──
        _has_ti = _lazy_load_engine_symbols()
        _TaskType = TaskType
        _TaskAnalyzer = TaskAnalyzer
        _TASK_STRATEGY_PROMPTS = TASK_STRATEGY_PROMPTS
        _BROWSER_GUIDE = BROWSER_GUIDE
        _COMPLETION_RULES = COMPLETION_RULES
        _is_ogenti = _is_ogenti_screen

        # ── Setup phase — wrapped in try/except so errors aren't silently swallowed ──
        try:
            await self.engine.update_agent_status(self.session_id, agent_id, "RUNNING")
            await self.engine.log(
                self.session_id,
                f"[Collab] {agent_name} started collaborating",
                "INFO", "AGENT", agent_id,
            )

            # ── PHASE GATE: Wait for this agent's phase to become active ──
            my_phase = self.bus.agent_phases.get(agent_id, 1)
            my_assignment = self.bus.phase_assignments.get(agent_id, "")
            if my_phase > 1:
                await self.engine.log(
                    self.session_id,
                    f"[{agent_name}] Waiting for Phase {my_phase} (currently Phase {self.bus.current_phase})...",
                    "INFO", "AGENT", agent_id,
                )
                await self.engine.update_agent_status(self.session_id, agent_id, "WAITING_PHASE")
                phase_started = await self.bus.wait_for_phase(agent_id, timeout=900.0)
                if not phase_started:
                    await self.engine.log(
                        self.session_id,
                        f"[{agent_name}] Phase {my_phase} never started. Completing.",
                        "WARN", "AGENT", agent_id,
                    )
                    self.bus.agents.get(agent_id, {})["status"] = "completed"
                    await self.engine.update_agent_status(self.session_id, agent_id, "COMPLETED")
                    return
                await self.engine.log(
                    self.session_id,
                    f"[{agent_name}] Phase {my_phase} active! Starting work.",
                    "INFO", "AGENT", agent_id,
                )
                await self.engine.update_agent_status(self.session_id, agent_id, "RUNNING")
                # Refresh screen state since Phase 1 agents changed things
                await self._update_shared_screen()

            # ── Tier enforcement: look up agent profile ──
            profile = None
            tier_config = None
            allowed_actions = None
            try:
                from core.agent_registry import (
                    get_agent_profile, get_agent_tier_config, get_agent_allowed_actions,
                )
                profile = get_agent_profile(agent_slug)
                tier_config = get_agent_tier_config(agent_slug)
                allowed_actions = get_agent_allowed_actions(agent_slug)
                await self.engine.log(
                    self.session_id,
                    f"[{agent_name}] Tier: {profile.tier} | Domain: {profile.domain} | Steps: {tier_config.max_steps} | Actions: {len(allowed_actions)}",
                    "INFO", "AGENT", agent_id,
                )
            except ImportError:
                pass

            # Apply tier limits
            if tier_config:
                max_steps = min(config.get("maxSteps", tier_config.max_steps), tier_config.max_steps)
                action_delay = tier_config.action_delay
                max_history = tier_config.max_message_history
            else:
                max_steps = config.get("maxSteps", 30)
                action_delay = 0.5
                max_history = 40

            if not allowed_actions:
                allowed_actions = self.VALID_ACTIONS

            collab_ctx = self.bus.get_collaboration_context(agent_id)

            # Detect LLM provider for this agent (for prompt adaptation)
            _agent_llm_for_provider = self.get_agent_llm(agent_id)
            _agent_provider = getattr(_agent_llm_for_provider, 'provider', 'UNKNOWN')

            system_prompt = self._build_collab_system_prompt(
                agent_id, agent_name, collab_ctx, profile, allowed_actions, _agent_provider
            )

            # ── Task Intelligence: detect task type and inject strategy ──
            detected_task_type = None
            search_query = ""
            task_strategy = ""
            first_action_hint = ""

            if _has_ti and _TaskAnalyzer and _TaskType:
                detected_task_type = _TaskAnalyzer.detect(prompt)
                search_query = _TaskAnalyzer.extract_search_query(prompt)
                task_strategy = _TASK_STRATEGY_PROMPTS.get(detected_task_type, "")
                first_action_hint = _TaskAnalyzer.get_first_action_hint(detected_task_type, search_query)

                await self.engine.log(
                    self.session_id,
                    f"[{agent_name}] Task type: {detected_task_type.value}, query: '{search_query}'",
                    "INFO", "AGENT", agent_id,
                )

            # Build enriched initial message with task-specific guidance
            initial_parts = [f"TASK: {prompt}"]

            # ── Phase Assignment: tell agent exactly what to do ──
            if my_assignment:
                initial_parts.append(f"\n🎯 YOUR SPECIFIC ASSIGNMENT (Phase {my_phase}): {my_assignment}")

            # ── Inject handoff data from previous phases ──
            handoffs = self.bus.get_handoff_data(agent_id)
            prev_results = self.bus.get_phase_results(my_phase - 1) if my_phase > 1 else []
            if handoffs:
                initial_parts.append("\n═══ DATA FROM PREVIOUS AGENTS ═══")
                for h in handoffs:
                    initial_parts.append(f"[{h['from_name']}] ({h['type']}): {h['content']}")
            if prev_results:
                initial_parts.append("\n═══ PHASE 1 FINDINGS (use these in your work!) ═══")
                for r in prev_results:
                    initial_parts.append(f"• {r}")

            # Check if this agent's domain is relevant to the task
            agent_domain = profile.domain if profile else "general"
            domain_relevance = self._check_domain_relevance(detected_task_type, agent_domain, _has_ti, _TaskType)

            if not domain_relevance["relevant"]:
                initial_parts.append(
                    f"\n⚠️ YOUR DOMAIN ({agent_domain.upper()}) is NOT the primary domain for this task.\n"
                    f"Reason: {domain_relevance['reason']}\n"
                    f"Suggestion: {domain_relevance['suggestion']}\n"
                    f"If you have nothing to contribute, say MY_PART_DONE immediately."
                )
            else:
                initial_parts.append(f"\n✅ Your domain ({agent_domain.upper()}) is highly relevant to this task.")
                if task_strategy:
                    initial_parts.append(f"\n{task_strategy}")
                if _has_ti and _BROWSER_GUIDE:
                    initial_parts.append(f"\n{_BROWSER_GUIDE}")
                if first_action_hint:
                    initial_parts.append(f"\n{first_action_hint}")

            initial_parts.append(
                "\n\n⚠️ CRITICAL REMINDERS:\n"
                "• Do NOT open File Explorer for research tasks — open Chrome or Edge!\n"
                "• Do NOT create empty files with run_command — type actual content in an editor!\n"
                "• Do NOT say MY_PART_DONE until you have ACTUALLY DONE meaningful work!\n"
                "• The Ogenti app window is auto-minimized by the system. If you see it, just use open_app to open the app you need.\n"
                "• NEVER press Alt+Tab repeatedly. Use open_app instead.\n"
                "• ALWAYS click an input field BEFORE typing into it.\n"
                "\n"
                "██ RESEARCH AGENTS — ANTI-WASTE RULES ██\n"
                "• COOKIE BANNERS: Click 'Accept' ONCE. If it doesn't go away → IGNORE IT and scroll past. NEVER retry.\n"
                "• DO NOT USE Ctrl+A / Ctrl+C on web pages. Copying entire pages is useless garbage. READ the screen and write FINDING: lines.\n"
                "• DO NOT click 'Cite', 'Download PDF', 'Export', or any bibliographic buttons. Read the info from the screen instead.\n"
                "• SCROLL at least 5 times per page. After each scroll, write at least 1 FINDING: line. Write 3+ per page minimum.\n"
                "• FINDING: lines must contain EXACT text from the screen (names, numbers, dates, quotes). Not vague summaries."
            )

            # Track work for completion verification
            actions_used_types: set[str] = set()
            has_typed_content = False
            total_actions_executed = 0

            # ═══ INTELLIGENCE LAYER ═══
            _intel_task_type = "browsing"
            if detected_task_type and _has_ti:
                _intel_map = {
                    _TaskType.RESEARCH: "research", _TaskType.BROWSING: "browsing",
                    _TaskType.WRITING: "writing", _TaskType.CODING: "coding",
                }
                _intel_task_type = _intel_map.get(detected_task_type, "browsing")
            
            collab_progress_tracker = None
            collab_context_accumulator = None
            collab_intel_history: list[dict] = []
            if HAS_INTELLIGENCE:
                collab_progress_tracker = TaskProgressTracker(_intel_task_type)
                collab_context_accumulator = ContextAccumulator(_intel_task_type, prompt)

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": "\n".join(initial_parts)},
            ]

            consecutive_empty = 0
            consecutive_no_os_action = 0
            consecutive_llm_errors = 0   # consecutive steps with [LLM Error:] response
            _last_actions: list[str] = []
            _USELESS_REPEAT_THRESHOLD = 3
        except Exception as e:
            # Setup failed — log the error (previously silently swallowed by asyncio.gather)
            logger.error(f"[Collab] Agent {agent_name} SETUP FAILED: {type(e).__name__}: {e}")
            await self.engine.log(
                self.session_id,
                f"[{agent_name}] SETUP ERROR: {type(e).__name__}: {e}",
                "ERROR", "AGENT", agent_id,
            )
            self.bus.agents.get(agent_id, {})["status"] = "completed"
            await self.engine.update_agent_status(self.session_id, agent_id, "COMPLETED")
            return

        # ── Step loop — original try/except structure preserved ──
        try:
            for step in range(max_steps):
                if self.engine._is_cancelled(self.session_id):
                    break

                while self.engine._is_paused(self.session_id):
                    await asyncio.sleep(1)

                # ── Tier-based action delay ──
                if step > 0:
                    await asyncio.sleep(action_delay)

                # Check for messages from other agents
                incoming = await self.bus.receive_messages(agent_id, timeout=0.3)
                if incoming:
                    msg_texts = [m.to_llm_text() for m in incoming]
                    messages.append({
                        "role": "user",
                        "content": f"📬 Messages from teammates:\n" + "\n".join(msg_texts) +
                                   "\n\nNow take your next ACTION. Do NOT just observe or send messages — perform an OS action."
                    })

                # Get shared screen
                screen = self.bus.get_screen()
                screen_b64 = screen.screenshot_b64

                # Update collaboration context periodically
                if step % 3 == 0:
                    collab_ctx = self.bus.get_collaboration_context(agent_id)
                    messages[0]["content"] = self._build_collab_system_prompt(
                        agent_id, agent_name, collab_ctx, profile, allowed_actions, _agent_provider
                    )

                # Detect repeated useless actions
                # NOTE: scroll is NOT useless during research — reading pages requires
                # consecutive scrolls. Only flag truly useless repeats like wait/move_mouse.
                _repeated_useless = (
                    len(_last_actions) >= _USELESS_REPEAT_THRESHOLD
                    and len(set(_last_actions[-_USELESS_REPEAT_THRESHOLD:])) == 1
                    and _last_actions[-1] in {"wait", "move_mouse", "clipboard_get"}
                )

                # Detect excessive scrolling (10+ in a row = probably stuck at end of page)
                _excessive_scroll = (
                    len(_last_actions) >= 10
                    and len(set(_last_actions[-10:])) == 1
                    and _last_actions[-1] == "scroll"
                )

                # Detect clicking the same coordinates repeatedly (5+ in a row)
                _repeated_click = False
                if len(_last_actions) >= 5:
                    last_5 = _last_actions[-5:]
                    if all(a in ("click", "click_element") for a in last_5):
                        _repeated_click = True

                # Inject stall-breaking prompt
                if consecutive_no_os_action >= 2 or _repeated_useless or _repeated_click or _excessive_scroll:
                    if _excessive_scroll:
                        stall_msg = (
                            "⚠️ You've scrolled 10+ times in a row. You've likely reached the end of the page.\n"
                            "NEXT STEPS:\n"
                            "1. Tag your findings: FINDING: [key facts you discovered]\n"
                            "2. Go back to search results: ACTION: hotkey PARAMS: {\"keys\": [\"alt\", \"left\"]}\n"
                            "3. Visit the NEXT search result for more information\n"
                            "4. If you have enough findings → move to the next phase\n"
                            "DO NOT keep scrolling. Move on."
                        )
                    elif _repeated_useless:
                        stall_msg = (
                            f"⚠️ USELESS ACTION LOOP DETECTED: You repeated '{_last_actions[-1]}' "
                            f"{_USELESS_REPEAT_THRESHOLD}+ times. This accomplishes NOTHING.\n"
                            f"CONCRETE OPTIONS:\n"
                            f"1. If you're stuck on a page: press Ctrl+L, type a NEW URL, press Enter\n"
                            f"2. If a button won't click: try pressing Tab to focus it, then Enter\n"
                            f"3. If nothing works: Alt+Left to go back, try a different approach\n"
                            f"4. If your part is done: say MY_PART_DONE\n"
                            f"PICK ONE NOW."
                        )
                    elif _repeated_click:
                        stall_msg = (
                            "⚠️ CLICK LOOP DETECTED: You clicked 5+ times without results.\n"
                            "STOP clicking the same thing. It will NOT work.\n"
                            "Most likely cause: cookie banner or overlay popup.\n\n"
                            "DO THIS NOW (pick ONE):\n"
                            "1. IGNORE the banner — scroll past it: ACTION: scroll PARAMS: {\"clicks\": -5}\n"
                            "2. Press Escape to dismiss overlay: ACTION: press_key PARAMS: {\"key\": \"escape\"}\n"
                            "3. Go back and try a different page: ACTION: hotkey PARAMS: {\"keys\": [\"alt\", \"left\"]}\n\n"
                            "NEVER click a button/banner more than once. If it didn't work the first time, it won't work the fifth time."
                        )
                    else:
                        stall_msg = (
                            "⚠️ STALL DETECTED: No meaningful OS actions for multiple turns.\n"
                            f"YOUR ASSIGNMENT: {my_assignment}\n"
                            f"REQUIRED NEXT STEP: Look at the screen and decide:\n"
                            f"• Need to search? → open_app {_BROWSER}, then Ctrl+L, type URL, Enter\n"
                            f"• Need to type? → Click the text area first, then type_text\n"
                            f"• Task done? → MY_PART_DONE\n"
                            f"ACT NOW. No more waiting."
                        )
                    messages.append({"role": "user", "content": stall_msg})
                    await self.engine.log(
                        self.session_id,
                        f"[{agent_name}] Stall/repeat detected, forcing action or completion",
                        "WARN", "AGENT", agent_id,
                    )
                    # Force-terminate only on truly useless repeats (NOT scroll)
                    if (len(_last_actions) >= 5
                        and len(set(_last_actions[-5:])) == 1
                        and _last_actions[-1] in {"wait", "move_mouse"}):
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] Force-terminated: {_last_actions[-1]} x5 in a row",
                            "WARN", "AGENT", agent_id,
                        )
                        break

                # ═══ INTELLIGENCE: Auto-resolve trivial situations before LLM ═══
                screen_analysis_collab = None  # Initialize before conditional block
                if HAS_INTELLIGENCE and collab_progress_tracker:
                    try:
                        som_desc_collab = getattr(screen, 'som_description', '') or ''
                        active_win_collab = getattr(screen, 'active_window', '') or ''
                        som_elements_collab = list(getattr(screen.som_result, 'element_map', {}).values()) if getattr(screen, 'som_result', None) else []
                        
                        screen_analysis_collab = ScreenStateClassifier.classify(
                            som_desc_collab, active_win_collab, som_elements_collab
                        )
                        
                        # ── OGENTI_APP override: Force to UNKNOWN ──
                        # If Ogenti is still visible after minimize, override state.
                        # This prevents ALL downstream code from looping on OGENTI_APP.
                        if screen_analysis_collab.state == ScreenState.OGENTI_APP:
                            CollaborativeSession._ogenti_consecutive_collab += 1
                            if CollaborativeSession._ogenti_consecutive_collab <= 2:
                                logger.warning(f"[Collab] Ogenti still visible (attempt {CollaborativeSession._ogenti_consecutive_collab}/3) — overriding to UNKNOWN")
                            screen_analysis_collab = ScreenAnalysis(
                                state=ScreenState.UNKNOWN,
                                confidence=0.3,
                                active_app="",
                            )
                            active_win_collab = ""
                            # Do NOT auto-resolve or StuckDetect — let LLM handle
                        else:
                            CollaborativeSession._ogenti_consecutive_collab = 0
                        
                        auto_collab = AutoActionResolver.resolve(
                            screen_analysis_collab,
                            collab_progress_tracker.state.current_phase.value,
                            _intel_task_type,
                            action_history=collab_intel_history,
                        )
                        
                        # If no auto-resolve, check StuckDetector
                        if not auto_collab:
                            stuck_collab = StuckDetector.check(
                                collab_intel_history, screen_analysis_collab.state,
                                _intel_task_type, total_actions_executed
                            )
                            if stuck_collab:
                                auto_collab = stuck_collab
                                await self.engine.log(self.session_id, f"[{agent_name}] 🚨 {stuck_collab['reason']}", "WARN", "AGENT", agent_id)
                        
                        if auto_collab:
                            auto_act = auto_collab["action"]
                            auto_rsn = auto_collab["reason"]
                            await self.engine.log(self.session_id, f"[{agent_name}] 🤖 {auto_rsn}", "INFO", "AGENT", agent_id)
                            
                            try:
                                result = self.engine.os_controller.execute_action(
                                    auto_act["type"], auto_act.get("params", {})
                                )
                                auto_ok = result.get("success", True) if isinstance(result, dict) else True
                                total_actions_executed += 1
                                actions_used_types.add(auto_act["type"])
                                _last_actions.append(auto_act["type"])
                                collab_intel_history.append({
                                    "action": f"AUTO:{auto_act['type']}",
                                    "success": auto_ok,
                                    "screen_state": screen_analysis_collab.state.value,
                                })
                                collab_progress_tracker.update(
                                    auto_act["type"], auto_act.get("params", {}), 
                                    auto_ok, screen_analysis_collab.state
                                )
                            except Exception:
                                pass
                            
                            messages.append({"role": "user", "content": f"🤖 AUTO: {auto_rsn}"})
                            await asyncio.sleep(action_delay)
                            continue
                        
                        # Inject progress hint for the LLM
                        if collab_progress_tracker:
                            hint = collab_progress_tracker.get_next_phase_hint()
                            status = collab_progress_tracker.get_status_summary()
                            if hint or status:
                                messages.append({"role": "user", "content": f"{status}\nNEXT: {hint}" if hint else status})
                    except Exception:
                        pass

                # Ask LLM (per-agent brain — each agent can use its own LLM)
                # Inject shared workspace context from other agents' brains
                if self.workspace and step % 3 == 0:  # Every 3rd step to avoid prompt bloat
                    try:
                        ws_ctx = await self.workspace.get_context_for_agent(agent_id)
                        if ws_ctx:
                            messages.append({"role": "user", "content": ws_ctx})
                    except Exception:
                        pass

                agent_llm = self.get_agent_llm(agent_id)
                try:
                    llm_response = await agent_llm.chat(
                        messages=messages,
                        screenshot_b64=screen_b64,
                    )
                except Exception as e:
                    await self.engine.log(
                        self.session_id, f"LLM error: {e}", "ERROR", "LLM", agent_id
                    )
                    consecutive_llm_errors += 1
                    if consecutive_llm_errors >= 4:
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] LLM API unavailable (4 consecutive errors) — aborting phase",
                            "ERROR", "AGENT", agent_id,
                        )
                        # Handoff failure notice to next-phase agents
                        for other_id, other_phase in self.bus.agent_phases.items():
                            if other_phase > my_phase and other_id != agent_id:
                                self.bus.send_handoff(agent_id, other_id, {
                                    "type": "findings",
                                    "content": f"⚠️ [{agent_name}] Phase {my_phase} FAILED: LLM API was unavailable (502/503 server errors). No research data was collected. Please attempt the task independently or notify the user that the AI service is temporarily down.",
                                })
                        break
                    await asyncio.sleep(2)
                    continue

                assistant_msg = llm_response.get("content", "")

                # Track LLM error responses returned as content (not exception)
                if assistant_msg.startswith("[LLM Error:"):
                    consecutive_llm_errors += 1
                    if consecutive_llm_errors >= 4:
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] LLM returning errors in content (4 consecutive) — aborting phase",
                            "ERROR", "AGENT", agent_id,
                        )
                        for other_id, other_phase in self.bus.agent_phases.items():
                            if other_phase > my_phase and other_id != agent_id:
                                self.bus.send_handoff(agent_id, other_id, {
                                    "type": "findings",
                                    "content": f"⚠️ [{agent_name}] Phase {my_phase} FAILED: LLM API was unavailable. No research data was collected. Attempt the task independently or report that the AI service is down.",
                                })
                        break
                else:
                    consecutive_llm_errors = 0
                messages.append({"role": "assistant", "content": assistant_msg})

                # ═══ LLM REFUSAL DETECTION ═══
                _msg_lower_c = assistant_msg.strip().lower()
                _is_refusal_c = (
                    ("i'm sorry" in _msg_lower_c or "i cannot" in _msg_lower_c or "i can't assist" in _msg_lower_c)
                    and len(assistant_msg.strip()) < 200
                    and "ACTION" not in assistant_msg
                )
                if _is_refusal_c:
                    _refusal_key = f"_refusal_{agent_id}"
                    _rc = getattr(self, _refusal_key, 0) + 1
                    setattr(self, _refusal_key, _rc)
                    await self.engine.log(
                        self.session_id,
                        f"[{agent_name}] LLM refusal detected (attempt {_rc}), provider={_agent_provider}",
                        "WARN", "LLM", agent_id,
                    )
                    # Use provider-optimized recovery prompt
                    _recovery = get_refusal_recovery_prompt(_agent_provider, my_assignment, _rc)
                    if _rc >= 3:
                        setattr(self, _refusal_key, 0)
                    messages.append({"role": "user", "content": _recovery})
                    continue
                else:
                    _refusal_key = f"_refusal_{agent_id}"
                    if getattr(self, _refusal_key, 0) > 0:
                        setattr(self, _refusal_key, 0)

                await self.engine.log(
                    self.session_id,
                    f"[{agent_name}] {assistant_msg[:200]}",
                    "DEBUG", "LLM", agent_id,
                )

                # Parse response for actions and messages
                actions = self._parse_actions(assistant_msg)
                team_messages = self._parse_team_messages(assistant_msg, agent_id, agent_name)

                # Send any team messages
                for tm in team_messages:
                    await self.bus.send_message(tm)

                # Check for completion — with work verification
                if "TASK_COMPLETE" in assistant_msg.upper() or "MY_PART_DONE" in assistant_msg.upper():
                    # ── Completion Verification: did this agent actually do work? ──
                    is_verified = True
                    rejection_reason = ""
                    
                    if domain_relevance["relevant"]:
                        # If this agent's domain is relevant, they MUST have done work
                        if _has_ti and _COMPLETION_RULES and _TaskType:
                            rules = _COMPLETION_RULES.get(detected_task_type, _COMPLETION_RULES.get(_TaskType.GENERAL, {}))
                            min_actions = max(2, rules.get("min_actions", 2) // 2)  # Lighter check for collab
                            
                            if total_actions_executed < min_actions:
                                is_verified = False
                                rejection_reason = f"Only {total_actions_executed} actions (need at least {min_actions} for your role)"
                            elif rules.get("must_have_typed") and not has_typed_content and detected_task_type in (_TaskType.RESEARCH, _TaskType.WRITING):
                                is_verified = False
                                rejection_reason = "You haven't typed any substantial content yet"
                        elif total_actions_executed < 2:
                            is_verified = False
                            rejection_reason = "You only performed 1 or 0 actions — that's not enough work"
                    
                    if is_verified:
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] verified completion ({total_actions_executed} actions, typed={has_typed_content})",
                            "INFO", "AGENT", agent_id,
                        )
                        await self.bus.send_message(AgentMessage(
                            sender_id=agent_id,
                            sender_name=agent_name,
                            msg_type=MessageType.STATUS,
                            content=f"I have completed my part. Actions taken: {total_actions_executed}.",
                        ))

                        # ── HANDOFF: Collect findings and send to next-phase agents ──
                        handoff_content = self._extract_findings_for_handoff(messages, agent_name)
                        if handoff_content:
                            # Send handoff to all agents in later phases
                            for other_id, other_phase in self.bus.agent_phases.items():
                                if other_phase > my_phase and other_id != agent_id:
                                    self.bus.send_handoff(agent_id, other_id, {
                                        "type": "findings",
                                        "content": handoff_content,
                                    })
                                    await self.engine.log(
                                        self.session_id,
                                        f"[{agent_name}] Handoff → {self.bus.agents.get(other_id, {}).get('name', other_id)}: {len(handoff_content)} chars",
                                        "INFO", "AGENT", agent_id,
                                    )

                        self.bus.agents[agent_id]["status"] = "completed"

                        # ── PHASE ADVANCEMENT: Check if all agents in this phase are done ──
                        if self.bus.is_phase_complete(my_phase):
                            self.bus.advance_phase(my_phase)
                            await self.engine.log(
                                self.session_id,
                                f"Phase {my_phase} complete → Phase {my_phase + 1} starting",
                                "INFO", "SYSTEM",
                            )
                        break
                    else:
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] completion REJECTED: {rejection_reason}",
                            "WARN", "AGENT", agent_id,
                        )
                        messages.append({
                            "role": "user",
                            "content": (
                                f"⚠️ MY_PART_DONE REJECTED: {rejection_reason}\n\n"
                                f"You cannot quit without doing meaningful work. "
                                f"Your domain ({agent_domain.upper()}) is relevant to this task.\n"
                                f"Continue working. What's the next step?"
                            ),
                        })
                        continue

                # ── Tier enforcement: filter actions by tier+domain ──
                valid_actions = []
                for a in actions:
                    at = a.get("type", "")
                    base_action = at.replace("_element", "") if at.endswith("_element") else at
                    if base_action in allowed_actions or at in allowed_actions:
                        valid_actions.append(a)
                    else:
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] ⛔ BLOCKED: '{at}' not allowed for tier {profile.tier if profile else '?'}/{profile.domain if profile else '?'}",
                            "WARN", "AGENT", agent_id,
                        )
                        messages.append({
                            "role": "user",
                            "content": f"⚠ '{at}' is NOT available to you. Use only actions in your list."
                        })
                actions = valid_actions

                if not actions:
                    try:
                        self.engine._metric_inc(self.session_id, "no_action_turns", 1)
                    except Exception:
                        pass
                    consecutive_empty += 1
                    consecutive_no_os_action += 1
                    if consecutive_empty >= 4:
                        break
                    messages.append({
                        "role": "user",
                        "content": "You MUST provide an ACTION now. Look at the screenshot, "
                                   "determine what needs to happen next, and DO IT. "
                                   "If your part is complete, say MY_PART_DONE. "
                                   "Do not wait for another agent."
                    })
                    continue

                consecutive_empty = 0
                consecutive_no_os_action = 0

                # Execute actions (with lock to prevent conflicts)
                for action in actions:
                    action_type = action.get("type", "")
                    action_params = action.get("params", {})

                    # Track action for useless-repeat detection
                    _last_actions.append(action_type)
                    if len(_last_actions) > 10:
                        _last_actions.pop(0)

                    # Resolve SoM elements
                    if action_type.endswith("_element"):
                        if screen.som_result:
                            element_id = action_params.get("id")
                            if element_id is not None:
                                el = screen.som_result.element_map.get(int(element_id))
                                if el:
                                    action_type = action_type.replace("_element", "")
                                    action_params = {"x": el.cx, "y": el.cy}
                                else:
                                    logger.warning(f"[Collab] SoM element #{element_id} not found")
                                    try:
                                        self.engine._metric_inc(self.session_id, "element_resolution_fail", 1)
                                    except Exception:
                                        pass
                                    messages.append({
                                        "role": "user",
                                        "content": f"⚠ Could not resolve element id={element_id} to coordinates. Re-observe and choose a different element id (or use coordinate-based click)."
                                    })
                                    continue
                        else:
                            # SoM unavailable — strip _element suffix, OSController handles fallback
                            logger.warning(f"[Collab] SoM unavailable, '{action_type}' falling back to base action")
                            if "id" in action_params and "x" not in action_params and "y" not in action_params and "rel_x" not in action_params and "rel_y" not in action_params:
                                try:
                                    self.engine._metric_inc(self.session_id, "element_resolution_fail", 1)
                                except Exception:
                                    pass
                                messages.append({
                                    "role": "user",
                                    "content": f"⚠ SoM is unavailable, so element id={action_params.get('id')} cannot be clicked. Re-observe or use coordinate-based click."
                                })
                                continue
                            action_type = action_type.replace("_element", "")

                    # ── Auto focus_window before type_text to prevent cross-agent conflicts ──
                    if action_type in ("type_text", "type_text_fast", "press_key", "hotkey"):
                        # Check if we need to ensure the right window is focused
                        # Look back in messages for the target window context
                        last_focus = self.bus.agents.get(agent_id, {}).get("_last_focus_window")
                        current_focus = self.bus.shared_screen.active_windows[-1] if self.bus.shared_screen.active_windows else None
                        if last_focus and current_focus and last_focus.lower() not in (current_focus or "").lower():
                            # Another agent changed the focus — re-focus our window
                            await self.engine.log(
                                self.session_id,
                                f"[{agent_name}] Auto re-focusing: {last_focus} (was: {current_focus})",
                                "DEBUG", "AGENT", agent_id,
                            )
                            got_focus_lock = await self.bus.acquire_action_lock(agent_id, timeout=5.0)
                            if got_focus_lock:
                                try:
                                    self.engine.os_controller.execute_action("focus_window", {"title": last_focus})
                                    await asyncio.sleep(0.3)
                                finally:
                                    self.bus.release_action_lock(agent_id)

                    # Announce intention before acting
                    await self.bus.send_message(AgentMessage(
                        sender_id=agent_id,
                        sender_name=agent_name,
                        msg_type=MessageType.INTENTION,
                        content=f"About to: {action_type} {json.dumps(action_params)[:80]}",
                    ))

                    # Acquire action lock (only one agent acts at a time on OS)
                    got_lock = await self.bus.acquire_action_lock(agent_id, timeout=8.0)
                    if not got_lock:
                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] waiting for action lock...",
                            "DEBUG", "AGENT", agent_id,
                        )
                        await asyncio.sleep(1.0)
                        got_lock = await self.bus.acquire_action_lock(agent_id, timeout=5.0)
                        if not got_lock:
                            messages.append({
                                "role": "user",
                                "content": "Action lock busy. Plan your next move and try again."
                            })
                            continue

                    try:
                        # ── INTELLIGENCE: Validate before execution ──
                        if HAS_INTELLIGENCE and collab_progress_tracker:
                            try:
                                som_elements_for_val = list(getattr(screen.som_result, 'element_map', {}).values()) if getattr(screen, 'som_result', None) else []
                                screen_analysis_for_val = ScreenStateClassifier.classify(
                                    getattr(screen, 'som_description', '') or '',
                                    getattr(screen, 'active_window', '') or '',
                                    som_elements_for_val
                                )
                                validation = ActionValidator.validate(
                                    action_type, action_params, screen_analysis_for_val,
                                    _intel_task_type, collab_intel_history
                                )
                                if validation:
                                    if validation.get("block"):
                                        await self.engine.log(self.session_id, f"[{agent_name}] 🛡️ {validation['reason']}", "WARN", "AGENT", agent_id)
                                        messages.append({"role": "user", "content": f"ACTION BLOCKED: {validation['reason']}"})
                                        self.bus.release_action_lock(agent_id)
                                        continue
                                    elif validation.get("fix"):
                                        fixed = validation["action"]
                                        await self.engine.log(self.session_id, f"[{agent_name}] 🔧 {validation['reason']}", "INFO", "AGENT", agent_id)
                                        action_type = fixed["type"]
                                        action_params = fixed.get("params", {})
                            except Exception:
                                pass

                        # Execute the OS action
                        result = self.engine.os_controller.execute_action(action_type, action_params)
                        try:
                            if isinstance(result, dict):
                                self.engine.record_action_result(self.session_id, action_type, result)
                        except Exception:
                            pass
                        self.bus.agents[agent_id]["actions_taken"] += 1
                        self.bus.agents[agent_id]["last_active"] = time.time()

                        # Track window focus for auto-refocus
                        if action_type in ("focus_window", "open_app"):
                            win_title = action_params.get("title") or action_params.get("name", "")
                            self.bus.agents[agent_id]["_last_focus_window"] = win_title

                        success = result.get("success", False) if isinstance(result, dict) else True
                        result_str = json.dumps(result)[:120] if isinstance(result, dict) else str(result)[:120]

                        # ── Track for completion verification ──
                        total_actions_executed += 1
                        actions_used_types.add(action_type)
                        _last_actions.append(action_type)
                        if action_type in ("type_text", "type_text_fast"):
                            typed_text = action_params.get("text", "")
                            if len(typed_text) > 10:
                                has_typed_content = True

                        # ── Intelligence tracking ──
                        collab_intel_history.append({
                            "action": f"{action_type}({json.dumps(action_params)[:40]})",
                            "success": success,
                            "screen_state": screen_analysis_collab.state.value if screen_analysis_collab is not None else "unknown",
                        })
                        if HAS_INTELLIGENCE and collab_progress_tracker:
                            try:
                                collab_progress_tracker.update(
                                    action_type, action_params, success,
                                    screen_analysis_collab.state if screen_analysis_collab is not None else ScreenState.UNKNOWN
                                )
                            except Exception:
                                pass

                        await self.engine.log(
                            self.session_id,
                            f"[{agent_name}] {action_type} → {result_str}",
                            "INFO", "OS_ACTION", agent_id,
                        )

                        # Wait for UI to settle and update shared screen
                        await self.engine._wait_for_ui_settle(max_wait=1.5)
                        await self._update_shared_screen()

                        # Get updated SoM description for verification context
                        updated_screen = self.bus.get_screen()
                        updated_som_desc = updated_screen.som_description or ""

                        # Broadcast result to other agents
                        await self.bus.send_message(AgentMessage(
                            sender_id=agent_id,
                            sender_name=agent_name,
                            msg_type=MessageType.ACTION_RESULT,
                            content=f"{'✓' if success else '✗'} {action_type}: {result_str}",
                            metadata={"action": action_type, "success": success},
                        ))

                        # Build smart verification prompt
                        verify_parts = [
                            f"{'✓' if success else '✗'} Action result: {action_type} → {result_str}",
                        ]
                        if updated_som_desc:
                            verify_parts.append(f"\n📍 CURRENT SCREEN ELEMENTS:\n{updated_som_desc}")
                            
                            # ── Ogenti Self-Detection in collab mode ──
                            # Just note it silently — system minimizes automatically.
                            # Do NOT tell LLM to "switch away" — that creates infinite loops.
                            if _has_ti and _is_ogenti and _is_ogenti(updated_som_desc):
                                logger.debug(f"[Collab] Ogenti detected in verification — system will auto-minimize")
                        verify_parts.extend([
                            "",
                            "VERIFY & DECIDE:",
                            "1. What CHANGED on screen after the action?",
                            "2. Am I in the right window/app for what I need to do next?",
                            "3. Before typing: is the cursor in the correct input field? If not, click it first.",
                            "4. What is the next meaningful action for MY part of the task?",
                            "5. If my part is done, say MY_PART_DONE.",
                        ])
                        messages.append({
                            "role": "user",
                            "content": "\n".join(verify_parts)
                        })
                    finally:
                        self.bus.release_action_lock(agent_id)

                await asyncio.sleep(0.3)

                # ── Smart message history trimming (context-preserving) ──
                if len(messages) > max_history:
                    if HAS_INTELLIGENCE and collab_context_accumulator and collab_progress_tracker:
                        dropped_count = len(messages) - max_history + 2
                        summary_parts = [
                            f"╔══ CONTEXT SUMMARY (trimmed) ══╗",
                            f"Task: {prompt}",
                            collab_progress_tracker.get_status_summary(),
                        ]
                        if collab_context_accumulator.findings:
                            summary_parts.append(collab_context_accumulator.build_context_block())
                        summary_parts.append("╚══════════════════════════════════╝")
                        summary_msg = {"role": "user", "content": "\n".join(summary_parts)}
                        messages = [messages[0], summary_msg] + messages[dropped_count + 1:]
                    else:
                        messages = [messages[0]] + messages[-(max_history - 1):]

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"[Collab] Agent {agent_name} step-loop error: {e}")
            await self.engine.log(
                self.session_id,
                f"[{agent_name}] error: {e}",
                "ERROR", "AGENT", agent_id,
            )
        finally:
            self.bus.agents.get(agent_id, {})["status"] = "completed"
            await self.engine.update_agent_status(self.session_id, agent_id, "COMPLETED")
            # Auto-advance phase if this agent's phase is now complete
            my_phase = self.bus.agent_phases.get(agent_id, 1)
            if self.bus.is_phase_complete(my_phase) and self.bus.current_phase <= my_phase:
                self.bus.advance_phase(my_phase)

    async def _synthesize_results(self, prompt: str):
        """After all agents finish, synthesize a final summary."""
        messages_summary = "\n".join(self.bus.get_recent_messages("__system__", count=50))
        completed = "\n".join(f"  ✓ {t}" for t in self.bus.completed_tasks)

        summary_prompt = f"""The collaborative task is now complete.

Original task: {prompt}

Completed sub-tasks:
{completed or '  (tracked via agent communication)'}

Team communication log:
{messages_summary or '  (no messages recorded)'}

Agent status:
{self.bus.get_agent_status_summary()}

Summarize what was accomplished."""

        try:
            resp = await self.llm.chat(messages=[
                {"role": "system", "content": "Summarize the collaborative execution results concisely."},
                {"role": "user", "content": summary_prompt},
            ])
            summary = resp.get("content", "Collaboration session completed.")
            await self.engine.log(self.session_id, f"═══ Collaboration Summary ═══\n{summary}")
        except Exception:
            await self.engine.log(self.session_id, "Collaboration session completed.")

    def _extract_findings_for_handoff(self, messages: list[dict], agent_name: str) -> str:
        """
        Extract useful findings from an agent's message history for handoff.
        
        Looks for:
        - FINDING: tagged lines
        - OBSERVATION sections with useful data
        - URLs visited
        - Key information discovered
        
        Returns a compact summary for the next-phase agent.
        """
        findings = []
        observations = []
        urls = []
        
        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role", "")
            
            if role != "assistant":
                continue
                
            # Extract FINDING: lines
            for line in content.split("\n"):
                stripped = line.strip()
                if stripped.startswith("FINDING:"):
                    findings.append(stripped[8:].strip())
                elif stripped.startswith("**FINDING"):
                    findings.append(stripped.replace("**FINDING**:", "").replace("**", "").strip())
            
            # Extract URLs
            for url in re.findall(r'https?://[^\s\)\"\']+', content):
                if url not in urls and "google.com/search" not in url:
                    urls.append(url)
            
            # Extract key observations (first line of OBSERVATION blocks)
            if "**OBSERVATION**:" in content or "OBSERVATION:" in content:
                obs_text = content.split("OBSERVATION:", 1)[-1].split("**THINKING**")[0].split("THINKING:")[0].strip()
                if len(obs_text) > 20:
                    observations.append(obs_text[:200])
        
        parts = []
        if findings:
            parts.append("KEY FINDINGS:\n" + "\n".join(f"• {f}" for f in findings[:10]))
        if urls:
            parts.append("SOURCES VISITED:\n" + "\n".join(f"• {u}" for u in urls[:5]))
        if observations and not findings:
            parts.append("OBSERVATIONS:\n" + "\n".join(f"• {o}" for o in observations[:5]))
        
        if not parts:
            # Fallback: extract from the last few assistant messages
            last_msgs = [m for m in messages[-10:] if m.get("role") == "assistant"]
            if last_msgs:
                summary_text = last_msgs[-1].get("content", "")[:500]
                parts.append(f"LAST AGENT OUTPUT:\n{summary_text}")
        
        return "\n\n".join(parts)

    def _build_collab_system_prompt(self, agent_id: str, agent_name: str, collab_context: str,
                                     profile=None, allowed_actions: set = None,
                                     provider: str = "UNKNOWN") -> str:
        """Build system prompt for collaborative agent with deep reasoning.
        
        D6 NOTE: Shared instruction fragments (APP_LAUNCH_GUIDE, PRECONDITION_RULES,
        SELF_DETECTION_WARNING) are in core/prompts.py. The full prompt text is kept
        here (rather than fully decomposed) because prompt quality is sensitive
        to ordering and context. The collab prompt differs from engine.py's solo
        prompt in team coordination, TEAM_MSG, MY_PART_DONE, and ROLE & DOMAIN
        sections.
        See also: engine.py._build_system_prompt()
        """
        # Identity section based on profile
        identity = f"You are {agent_name}, an AI agent"
        tier_badge = ""
        domain_desc = ""
        if profile:
            identity = f"You are {agent_name}. {profile.persona}"
            tier_badge = f"\n[Tier {profile.tier} | Domain: {profile.domain.upper()} | Expertise: {profile.expertise}]\n"
            domain_desc = f"""
╔══════════════════════════════════════════════════════════════════════╗
║                    YOUR ROLE & DOMAIN                               ║
╚══════════════════════════════════════════════════════════════════════╝
You are a **{profile.domain.upper()}** specialist.
Your expertise: {profile.expertise}

ROLE RULES:
- Focus on tasks within YOUR domain. Do NOT do other agents' jobs.
- If another agent's domain covers a subtask better, let them handle it.
- If your part is complete, say MY_PART_DONE immediately. Do NOT waste turns.
- NEVER repeat an action another agent already completed successfully.
"""
        
        # Build action list dynamically based on allowed_actions
        if not allowed_actions:
            allowed_actions = self.VALID_ACTIONS
        
        element_lines = []
        action_lines = []
        for act in sorted(allowed_actions):
            if act in ACTION_DEFINITIONS:
                if act.endswith("_element"):
                    element_lines.append(ACTION_DEFINITIONS[act])
                else:
                    action_lines.append(ACTION_DEFINITIONS[act])
        
        element_section = ""
        if element_lines:
            element_section = "★ Element-based (PREFERRED — click by detected ID):\n" + "\n".join(element_lines) + "\n\n"
        
        actions_block = element_section + "Other actions:\n" + "\n".join(action_lines)
        
        raw_prompt = f"""{identity}
{tier_badge}
╔══════════════════════════════════════════════════════════════════════╗
║         COLLABORATIVE MULTI-AGENT EXECUTION SYSTEM                  ║
╚══════════════════════════════════════════════════════════════════════╝

You are collaborating with a TEAM of agents on a shared Windows computer.
You all see the SAME SCREEN and take turns performing actions.
Only ONE agent acts at a time — when it's your turn, you MUST provide an ACTION.

{domain_desc}

╔══════════════════════════════════════════════════════════════════════╗
║              ⚠⚠⚠  OGENTI SELF-DETECTION  ⚠⚠⚠                     ║
╚══════════════════════════════════════════════════════════════════════╝

You are running inside the "Ogenti" application.
The Ogenti window is a DARK-THEMED chat interface showing agent names and status.

██████████████████████████████████████████████████████████████████████
██  IF YOU SEE THIS WINDOW ON SCREEN, IT IS YOUR OWN APP!          ██
██  DO NOT CLICK ON IT. DO NOT TYPE IN IT. IGNORE IT COMPLETELY.   ██
██████████████████████████████████████████████████████████████████████

If Ogenti blocks the screen:
  → ACTION: hotkey  PARAMS: {{"keys": ["alt", "tab"]}}
  → Or: ACTION: focus_window  PARAMS: {{"title": "{_BROWSER_DISPLAY}"}}

╔══════════════════════════════════════════════════════════════════════╗
║               WINDOWS OS MASTERY GUIDE                              ║
╚══════════════════════════════════════════════════════════════════════╝

═══ APP LAUNCH COMMANDS ═══
  Web Browser:   ACTION: open_app  PARAMS: {{"name": "{_BROWSER}"}}
                 ACTION: open_app  PARAMS: {{"name": "msedge"}}  ← fallback
  Text Editor:   ACTION: open_app  PARAMS: {{"name": "notepad"}}
  Code Editor:   ACTION: open_app  PARAMS: {{"name": "code"}}
  File Manager:  ACTION: open_app  PARAMS: {{"name": "explorer"}}  ← ONLY for files!
  Terminal:      ACTION: open_app  PARAMS: {{"name": "cmd"}}

  ★ CRITICAL: "explorer" = File Explorer (for files). "{_BROWSER}" = Web Browser (for internet).
    NEVER open File Explorer for research. Use {_BROWSER_DISPLAY} or Edge.

═══ WEB BROWSER COMPLETE WORKFLOW ═══
  1. ACTION: open_app    PARAMS: {{"name": "{_BROWSER}"}}
  2. ACTION: wait         PARAMS: {{"seconds": 3}}
  3. ACTION: hotkey       PARAMS: {{"keys": ["ctrl", "l"]}}   ← MUST focus address bar first!
  4. ACTION: type_text    PARAMS: {{"text": "https://www.google.com/search?q=your+query"}}
  5. ACTION: press_key    PARAMS: {{"key": "enter"}}
  6. ACTION: wait         PARAMS: {{"seconds": 3}}
  7. Click search results using element [IDs] — skip ads!
  8. Scroll to read: ACTION: scroll PARAMS: {{"clicks": -5}}
  9. Go back: ACTION: hotkey PARAMS: {{"keys": ["alt", "left"]}}

═══ TEXT EDITOR WORKFLOW ═══
  1. ACTION: open_app    PARAMS: {{"name": "notepad"}}
     (If Notepad is already open, this will FOCUS it — no duplicate windows!)
  2. ACTION: wait         PARAMS: {{"seconds": 2}}
  3. ACTION: click        PARAMS: {{"x": 400, "y": 400}}  ← click text area first!
  4. ACTION: type_text_fast    PARAMS: {{"text": "your ENTIRE content here"}}
     ★ Use type_text_fast (NOT type_text) for long text or Korean/Unicode!
     ★ Write ALL content in a SINGLE call. Do NOT split into multiple calls.
  5. ACTION: hotkey       PARAMS: {{"keys": ["ctrl", "s"]}}

═══ PRE-CONDITION RULES ═══
  Before typing text   → FIRST click the input field or Ctrl+L (address bar)
  Before scrolling     → FIRST verify correct window is in foreground
  Before clicking      → FIRST verify element is visible on screen
  After another agent acts → FIRST use focus_window to reclaim the right app

╔══════════════════════════════════════════════════════════════════════╗
║          COGNITIVE FRAMEWORK (Follow EVERY Turn)                    ║
╚══════════════════════════════════════════════════════════════════════╝

STEP 1 — OBSERVE the screenshot:
  • What app/window is in the FOREGROUND right now?
  • What UI elements do you see? List them with [numbers].
  • Is there any dialog, popup, or unexpected state?
  • Is the Ogenti window visible? (If yes → IGNORE it, switch away)

STEP 2 — ORIENT yourself:
  • What is the overall task? What's MY part of it?
  • What did my teammates do? (check TEAM_MSG messages)
  • What did I do last? Did it work?
  • Am I in the RIGHT app for what I need to do?

STEP 3 — DECIDE on ONE action:
  • What is the single smallest step that makes progress?
  • PRE-CONDITIONS:
    ├─ To type text → Have I clicked the target input field? If not → click first
    ├─ To navigate URL → Have I pressed Ctrl+L? If not → press Ctrl+L first
    ├─ To read page → Has the page loaded? If not → wait 3 seconds first
    └─ To interact with an app → Is it in foreground? If not → focus_window first
  • Prefer element [IDs] over raw coordinates for clicking

STEP 4 — ACT by providing exactly ONE action

STEP 5 — After receiving result, VERIFY:
  • Did the action succeed?
  • Is the screen state what I expected?
  • If not → try a different approach (don't repeat the same failing action)

╔══════════════════════════════════════════════════════════════════════╗
║              COLLABORATION RULES                                    ║
╚══════════════════════════════════════════════════════════════════════╝

1. EVERY response MUST include exactly ONE ACTION (unless MY_PART_DONE or TASK_COMPLETE)
2. NEVER use 'wait' as filler. If nothing to do → say MY_PART_DONE
3. focus_window BEFORE typing if another agent was acting
4. Don't duplicate work — check TEAM_MSG for what teammates already did
5. NEVER repeat the same failing action more than 2 times → try different approach
6. Tag discoveries with FINDING: prefix for team handoff
7. MY_PART_DONE = your phase is complete, next agent takes over
8. TASK_COMPLETE = the ENTIRE team task is finished (only final phase agent says this)

╔══════════════════════════════════════════════════════════════════════╗
║              TASK COMPLETION VERIFICATION                           ║
╚══════════════════════════════════════════════════════════════════════╝

BEFORE saying TASK_COMPLETE, verify ALL of these:
  ☑ You performed MEANINGFUL actions (not just observed)
  ☑ For research: Visited 2+ websites AND compiled a report with real content
  ☑ For writing: Typed REAL substantive content (not placeholder)
  ☑ For coding: Wrote working code AND tested it
  ☑ The task output exists and contains real, useful content
  ☑ The file is saved

BEFORE saying MY_PART_DONE, verify:
  ☑ Your domain-specific contribution is complete
  ☑ You left handoff data (FINDING: tags, TEAM_MSG updates)
  ☑ The workspace is in a clean state for the next agent

━━━ RESPONSE FORMAT (MANDATORY — follow exactly) ━━━

**OBSERVATION**: [What I see — name the app, list key elements with [numbers]]
**THINKING**: [My reasoning: what did teammates do? What should I do? Pre-conditions met?]
**TEAM_MSG**: [Brief message to teammates about what I'm doing/found]
**ACTION**: [one action name from the list below]
**PARAMS**: {{...}}

When YOUR part is done: MY_PART_DONE
When ENTIRE task is done: TASK_COMPLETE

━━━ AVAILABLE ACTIONS (ONLY these — anything else REJECTED) ━━━

{actions_block}

{collab_context}"""
        # ═══ PROVIDER-AWARE PROMPT ADAPTATION ═══
        return adapt_system_prompt(raw_prompt, provider)

    # Canonical valid actions — single source of truth in core.prompts
    VALID_ACTIONS = _VALID_ACTIONS

    def _parse_actions(self, text: str) -> list[dict]:
        """Parse ACTION/PARAMS pairs from LLM response, rejecting invalid actions."""
        actions = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip().replace("**", "").strip()
            if line.startswith("ACTION:"):
                action_type = line.split("ACTION:", 1)[1].strip().lower()
                params = {}
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip().replace("**", "").strip()
                    if next_line.startswith("PARAMS:"):
                        try:
                            params = json.loads(next_line.split("PARAMS:", 1)[1].strip())
                        except (json.JSONDecodeError, ValueError):
                            pass
                        i += 1
                if action_type in self.VALID_ACTIONS:
                    actions.append({"type": action_type, "params": params})
                else:
                    logger.warning(f"[Collab] Ignoring invalid action: '{action_type}'")
            i += 1
        return actions

    def _parse_team_messages(
        self, text: str, agent_id: str, agent_name: str
    ) -> list[AgentMessage]:
        """Parse TEAM_MSG lines from LLM response."""
        messages = []
        for line in text.split("\n"):
            clean = line.strip().replace("**", "").strip()
            if clean.startswith("TEAM_MSG:"):
                content = clean.split("TEAM_MSG:", 1)[1].strip()
                if content:
                    # Check for @mention targeting
                    target = None
                    if content.startswith("@"):
                        parts = content.split(" ", 1)
                        target = parts[0][1:]  # Remove @
                        content = parts[1] if len(parts) > 1 else content
                    messages.append(AgentMessage(
                        sender_id=agent_id,
                        sender_name=agent_name,
                        msg_type=MessageType.OBSERVATION,
                        content=content,
                        target_agent=target,
                    ))
        return messages

    @staticmethod
    def _check_domain_relevance(task_type, agent_domain: str, has_ti: bool = False, _TaskType=None) -> dict:
        """
        Check if an agent's domain is relevant to the detected task type.
        Returns {relevant: bool, reason: str, suggestion: str}.
        
        This prevents the Apex Analyst (data_analysis) from trying to do research tasks,
        and similar mismatches.
        """
        if not has_ti or not _TaskType or task_type is None:
            return {"relevant": True, "reason": "", "suggestion": ""}
        
        # Domain → relevant task types mapping
        DOMAIN_TASK_MAP = {
            "research": {_TaskType.RESEARCH, _TaskType.BROWSING, _TaskType.WRITING, _TaskType.GENERAL},
            "coding": {_TaskType.CODING, _TaskType.AUTOMATION, _TaskType.GENERAL},
            "design": {_TaskType.DESIGN, _TaskType.WRITING, _TaskType.GENERAL},
            "data_analysis": {_TaskType.DATA_ANALYSIS, _TaskType.CODING, _TaskType.GENERAL},
            "automation": {_TaskType.AUTOMATION, _TaskType.CODING, _TaskType.FILE_MANAGEMENT, _TaskType.GENERAL},
            "writing": {_TaskType.WRITING, _TaskType.RESEARCH, _TaskType.GENERAL},
            "productivity": {_TaskType.FILE_MANAGEMENT, _TaskType.AUTOMATION, _TaskType.GENERAL},
            "general": {t for t in _TaskType},  # General is always relevant
        }
        
        relevant_tasks = DOMAIN_TASK_MAP.get(agent_domain, {_TaskType.GENERAL})
        
        if task_type in relevant_tasks or task_type == _TaskType.GENERAL:
            return {"relevant": True, "reason": f"{agent_domain} covers {task_type.value}", "suggestion": ""}
        
        # Not relevant
        SUGGESTIONS = {
            "data_analysis": "If numerical data is found, you could analyze it. Otherwise, say MY_PART_DONE.",
            "design": "If visual/design work is needed later, you could help. Otherwise, say MY_PART_DONE.",
            "coding": "If code needs to be written as part of this task, you could help. Otherwise, say MY_PART_DONE.",
            "automation": "If automation or scripting is part of this task, you could help. Otherwise, say MY_PART_DONE.",
        }
        
        return {
            "relevant": False,
            "reason": f"{agent_domain} domain doesn't match {task_type.value} task",
            "suggestion": SUGGESTIONS.get(agent_domain, "Say MY_PART_DONE if you have nothing to contribute."),
        }
