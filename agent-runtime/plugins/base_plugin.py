"""
Base Plugin v2 — Abstract base class for all agent plugins.

v4.2 — Tier-aware, domain-enforced plugins with INTELLIGENCE.

Every plugin is bound to a tier and domain via the AgentRegistry.
The base class provides:
  - Tier-gated action validation (blocks disallowed actions)
  - Domain-locked specialized tools
  - Tier-appropriate system prompt generation
  - Standard _parse_actions with enforcement
  - TASK INTELLIGENCE: Concrete strategies for research/coding/writing/browsing
  - VERIFICATION: Prevents premature completion (TASK_COMPLETE/MY_PART_DONE)
  - BROWSER GUIDE: Step-by-step browser navigation instructions
  - WINDOWS KNOWLEDGE: Knows how to open common apps
  - SELF-DETECTION: Prevents agents from clicking on their own UI
"""

import json
import asyncio
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING
from loguru import logger

if TYPE_CHECKING:
    from core.engine import AgentContext

from core.agent_registry import (
    get_agent_profile, get_agent_allowed_actions, get_agent_tools,
    get_agent_tier_config, get_agent_engine_flags, AgentProfile,
)
from core.tier_config import TierConfig
from core.specialized_tools import SpecializedTool, build_tools_prompt, execute_tool


# ═══════════════════════════════════════════════════════
# TASK INTELLIGENCE — Concrete knowledge injected into every agent
# ═══════════════════════════════════════════════════════

BROWSER_QUICK_REFERENCE = """
╔══════════════════════════════════════════════════════════════════════╗
║                BROWSER MASTERY CHEATSHEET                           ║
╚══════════════════════════════════════════════════════════════════════╝

═══ OPENING A BROWSER ═══
  ACTION: open_app   PARAMS: {"name": "browser"}     ← auto-detects installed browser
  ACTION: open_app   PARAMS: {"name": "msedge"}      ← fallback (always available on Windows)
  ⚠ NEVER use open_app "explorer" for web browsing! That opens FILE EXPLORER!
  After opening, ALWAYS wait 3 seconds before next action.

═══ NAVIGATING TO A URL ═══
  Step 1: ACTION: hotkey     PARAMS: {"keys": ["ctrl", "l"]}   ← focus address bar
  Step 2: ACTION: type_text  PARAMS: {"text": "https://www.google.com"}
  Step 3: ACTION: press_key  PARAMS: {"key": "enter"}
  Step 4: ACTION: wait       PARAMS: {"seconds": 3}   ← ALWAYS wait for page load!
  ★★★ You MUST press Ctrl+L BEFORE typing any URL. Otherwise text goes to wrong place!

═══ SEARCHING GOOGLE ═══
  Fastest method: Navigate directly to search URL
    ACTION: type_text  PARAMS: {"text": "https://www.google.com/search?q=your+search+terms"}
  ★ Replace spaces with + signs in the URL

═══ INTERACTING WITH WEB PAGES ═══
  Click a link:     Use click_element with [ID number] from screenshot
  Scroll down:      ACTION: scroll     PARAMS: {"clicks": -30}
  Scroll up:        ACTION: scroll     PARAMS: {"clicks": 30}
  Go back:          ACTION: hotkey     PARAMS: {"keys": ["alt", "left"]}
  New tab:          ACTION: hotkey     PARAMS: {"keys": ["ctrl", "t"]}
  Close tab:        ACTION: hotkey     PARAMS: {"keys": ["ctrl", "w"]}
  Find on page:     ACTION: hotkey     PARAMS: {"keys": ["ctrl", "f"]}
  Refresh:          ACTION: press_key  PARAMS: {"key": "f5"}

═══ READING SEARCH RESULTS ═══
  Google results show:
  • Blue text = clickable links (your targets)
  • Green URL text below each = the website address
  • Gray snippets = preview text
  • "Ad" labels = ADVERTISEMENTS — skip these!
  • "People also ask" = expandable Q&A boxes
  
  Click the BLUE LINK TEXT using its element [ID] number.
  After clicking, wait 3 seconds, then scroll to read content.

═══ COMMON MISTAKES TO AVOID ═══
  ✗ Typing URL without pressing Ctrl+L first → text goes to search box or nowhere
  ✗ Not waiting after pressing Enter → page hasn't loaded, you act on old content
  ✗ Clicking coordinate instead of element ID → misses the link
  ✗ Opening File Explorer instead of Chrome → wrong app entirely
  ✗ Typing in the Ogenti window → waste of action
"""

WINDOWS_APP_CHEATSHEET = """
╔══════════════════════════════════════════════════════════════════════╗
║                 WINDOWS OS OPERATION GUIDE                          ║
╚══════════════════════════════════════════════════════════════════════╝

═══ APPLICATION LAUNCH COMMANDS ═══
  Web Browser:     ACTION: open_app  PARAMS: {"name": "browser"}
                   ACTION: open_app  PARAMS: {"name": "msedge"}     ← if browser fails
  Text Editor:     ACTION: open_app  PARAMS: {"name": "notepad"}
  Code Editor:     ACTION: open_app  PARAMS: {"name": "code"}
  File Manager:    ACTION: open_app  PARAMS: {"name": "explorer"}   ← ONLY for file management!
  Terminal:        ACTION: open_app  PARAMS: {"name": "cmd"}
  PowerShell:      ACTION: open_app  PARAMS: {"name": "powershell"}

  ★ CRITICAL RULE: "explorer" = File Explorer (for files). "browser"/"msedge" = Web Browser (for internet).
    NEVER confuse these two. Research tasks need a BROWSER, not File Explorer.

═══ WINDOW MANAGEMENT ═══
  Switch windows:    ACTION: hotkey   PARAMS: {"keys": ["alt", "tab"]}
  Focus by title:    ACTION: focus_window PARAMS: {"title": "window name"}
  Minimize all:      Win+D (useful to escape Ogenti overlay)
  Close current app: ACTION: hotkey   PARAMS: {"keys": ["alt", "f4"]}

═══ FILE OPERATIONS ═══
  Save:            ACTION: hotkey   PARAMS: {"keys": ["ctrl", "s"]}
  Save As:         ACTION: hotkey   PARAMS: {"keys": ["ctrl", "shift", "s"]}
  Undo:            ACTION: hotkey   PARAMS: {"keys": ["ctrl", "z"]}
  Redo:            ACTION: hotkey   PARAMS: {"keys": ["ctrl", "y"]}

═══ TEXT EDITING ═══
  Select all:      ACTION: hotkey   PARAMS: {"keys": ["ctrl", "a"]}
  Copy:            ACTION: hotkey   PARAMS: {"keys": ["ctrl", "c"]}
  Paste:           ACTION: hotkey   PARAMS: {"keys": ["ctrl", "v"]}
  Cut:             ACTION: hotkey   PARAMS: {"keys": ["ctrl", "x"]}

═══ PRE-CONDITION RULES ═══
  Before typing text → FIRST click the target input field or press Ctrl+L (for address bar)
  If typing English/URLs but IME is Korean → toggle: ACTION: hotkey PARAMS: {"keys": ["hangul"]}
  Before saving      → FIRST ensure you have content (not an empty document)
  Before scrolling   → FIRST ensure the right window is in foreground
  Before clicking    → FIRST verify the element is visible on screen
"""

TASK_COMPLETION_RULES = """
╔══════════════════════════════════════════════════════════════════════╗
║              TASK COMPLETION VERIFICATION                           ║
╚══════════════════════════════════════════════════════════════════════╝

You are FORBIDDEN from saying TASK_COMPLETE unless EVERY condition below is met:

  ┌─ RESEARCH TASKS ─────────────────────────────────────┐
  │ ☐ Opened a web BROWSER (Chrome/Edge — NOT File Explorer!)  │
  │ ☐ Searched on Google with relevant terms                    │
  │ ☐ Visited and READ at least 2 different web pages           │
  │ ☐ Found at least 3 concrete facts/findings                  │
  │ ☐ Opened a text editor (Notepad/VS Code)                    │
  │ ☐ Typed a report with REAL factual content (500+ chars)     │
  │ ☐ Saved the report file                                     │
  └──────────────────────────────────────────────────────────────┘

  ┌─ WRITING TASKS ──────────────────────────────────────┐
  │ ☐ Opened a text editor                                      │
  │ ☐ Typed REAL, substantive content (not just a title)         │
  │ ☐ Content has clear structure (intro, body, conclusion)      │
  │ ☐ Saved the file                                             │
  └──────────────────────────────────────────────────────────────┘

  ┌─ CODING TASKS ───────────────────────────────────────┐
  │ ☐ Created files with ACTUAL working code                     │
  │ ☐ Ran/tested the code at least once                          │
  │ ☐ Fixed any errors that appeared                             │
  │ ☐ Code produces correct output                               │
  └──────────────────────────────────────────────────────────────┘

  ┌─ BROWSING TASKS ─────────────────────────────────────┐
  │ ☐ Navigated to the target URL                                │
  │ ☐ Interacted with the page as required                       │
  │ ☐ Extracted or noted the requested information               │
  └──────────────────────────────────────────────────────────────┘

ABSOLUTE PROHIBITIONS:
  ✗ NEVER say TASK_COMPLETE after only looking at the screen
  ✗ NEVER create empty placeholder files — write REAL content
  ✗ NEVER fake results or claim you found information you didn't actually read
  ✗ NEVER skip the verification step — check your work before completing
  ✗ If you cannot fulfill the task, explain WHY instead of faking completion
"""

SELF_DETECTION_WARNING = """
╔══════════════════════════════════════════════════════════════════════╗
║         ⚠⚠⚠  OGENTI SELF-DETECTION WARNING  ⚠⚠⚠                   ║
╚══════════════════════════════════════════════════════════════════════╝

You are an AI agent running inside the "Ogenti" application.
The Ogenti window is a DARK-THEMED chat interface that shows:
  • Agent names and status messages
  • Chat bubbles with agent activity logs
  • Buttons like "Stop", "Cancel", step counters
  • The text "Ogenti" or agent tier badges

██████████████████████████████████████████████████████████████████████
██  IF YOU SEE THIS WINDOW ON THE SCREENSHOT, IT IS YOUR OWN APP! ██
██  DO NOT CLICK ON IT. DO NOT TYPE IN IT. DO NOT INTERACT.        ██
██████████████████████████████████████████████████████████████████████

WHAT TO DO WHEN YOU SEE THE OGENTI WINDOW:
  1. IGNORE it completely — it is YOUR application, not a workspace tool
  2. Look for OTHER windows BEHIND or BESIDE the Ogenti window
  3. If Ogenti blocks the screen, use: ACTION: hotkey PARAMS: {"keys": ["alt", "tab"]}
  4. If that doesn't work: ACTION: focus_window PARAMS: {"title": "Edge"}
     or: ACTION: open_app PARAMS: {"name": "browser"}

HOW TO IDENTIFY THE OGENTI WINDOW:
  • Dark background with chat-like message bubbles
  • Shows agent names (e.g., "Apex Researcher", "Apex Analyst")
  • Shows task progress like "Step 3/20"
  • Has a text input area at the bottom
  → ANY window matching these features = Ogenti = YOUR APP = DO NOT TOUCH
"""


class BasePlugin(ABC):
    """
    Base class for agent plugins.
    
    v4.2 — Tier-enforced with task intelligence:
    - Each plugin declares a slug → AgentRegistry resolves tier/domain
    - allowed_actions is computed from tier ∩ domain whitelist
    - specialized_tools are domain-exclusive, tier-gated
    - System prompt budget is tier-limited
    - Engine access (vision, planner, memory) is tier-gated
    - Concrete task strategies injected based on detected task type
    - Completion verification prevents premature TASK_COMPLETE
    - Browser/Windows knowledge embedded for reliable navigation
    
    Subclass this to create new agent plugins. Each plugin must:
    1. Set name, description, version, slug
    2. Implement the execute() method
    3. Use self._execute_action() instead of raw ctx.os calls (enforces boundaries)
    4. Use self._parse_actions() to parse LLM responses (filters disallowed actions)
    """

    name: str = "Base Plugin"
    description: str = ""
    version: str = "4.2.0"
    slug: str = ""
    capabilities: list[str] = []

    def __init__(self):
        """Initialize with tier-aware configuration from agent registry."""
        self._profile: AgentProfile = get_agent_profile(self.slug)
        self._tier_config: TierConfig = get_agent_tier_config(self.slug)
        self._allowed_actions: set[str] = get_agent_allowed_actions(self.slug)
        self._tools: list[SpecializedTool] = get_agent_tools(self.slug)
        self._engine_flags: dict[str, bool] = get_agent_engine_flags(self.slug)
        # Execution tracking
        self._actions_executed: int = 0
        self._actions_by_type: dict[str, int] = {}
        self._has_typed_content: bool = False
        self._has_opened_app: bool = False
        self._has_saved: bool = False
        self._execution_start: float = 0

    @property
    def tier(self) -> str:
        return self._profile.tier
    
    @property
    def domain(self) -> str:
        return self._profile.domain
    
    @property
    def allowed_actions(self) -> set[str]:
        """Actions this agent is PERMITTED to execute (tier ∩ domain)."""
        return self._allowed_actions
    
    @property
    def tools(self) -> list[SpecializedTool]:
        """Specialized tools available to this agent."""
        return self._tools

    @abstractmethod
    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        """
        Execute the agent's task.
        
        Args:
            ctx: AgentContext with access to OS control, LLM, logging, etc.
            prompt: User's task description
            config: Execution configuration (maxSteps will be overridden by tier)
        """
        pass

    # ─── TASK TYPE DETECTION ──────────────────────────────

    def _detect_task_type(self, prompt: str) -> str:
        """Detect what kind of task the prompt is asking for."""
        prompt_lower = prompt.lower()
        
        TASK_KEYWORDS = {
            "research": ["research", "find information", "look up", "search for", "investigate",
                        "what is", "how does", "learn about", "study", "analyze topic",
                        "find out", "gather information", "조사", "검색", "찾아"],
            "coding": ["code", "program", "develop", "debug", "fix bug", "implement",
                       "create function", "write script", "build app", "compile", "error",
                       "코딩", "프로그래밍", "개발"],
            "writing": ["write", "compose", "draft", "essay", "article", "report",
                       "document", "letter", "blog", "story", "작성", "글쓰기"],
            "design": ["design", "layout", "mockup", "wireframe", "ui", "ux",
                       "figma", "color", "image", "디자인"],
            "browsing": ["open website", "go to", "navigate to", "visit", "browse",
                        "download from", "사이트", "웹사이트"],
            "automation": ["automate", "batch", "schedule", "move files", "rename",
                          "install", "configure", "setup", "자동화", "설정"],
            "data_analysis": ["analyze data", "csv", "excel", "chart", "graph",
                             "statistics", "dataset", "데이터", "분석"],
        }
        
        scores = {}
        for task_type, keywords in TASK_KEYWORDS.items():
            score = sum(2 for kw in keywords if kw in prompt_lower)
            if score > 0:
                scores[task_type] = score
        
        if not scores:
            return "general"
        return max(scores, key=scores.get)

    def _get_task_strategy(self, task_type: str) -> str:
        """Get concrete step-by-step strategy for a task type."""
        STRATEGIES = {
            "research": """
╔══════════════════════════════════════════════════════════════════════╗
║             RESEARCH TASK — EXACT ACTION SEQUENCE                   ║
╚══════════════════════════════════════════════════════════════════════╝

Follow these steps IN EXACT ORDER. Do NOT skip any step.

═══ PHASE 1: LAUNCH BROWSER ═══
  Step 1: ACTION: open_app    PARAMS: {"name": "browser"}
  Step 2: ACTION: wait        PARAMS: {"seconds": 3}
  Step 3: VERIFY — screenshot must show Chrome/Edge window (NOT File Explorer, NOT Ogenti)
          If wrong window → ACTION: open_app PARAMS: {"name": "msedge"}

═══ PHASE 2: SEARCH GOOGLE ═══
  Step 4: ACTION: hotkey      PARAMS: {"keys": ["ctrl", "l"]}
  Step 5: ACTION: type_text   PARAMS: {"text": "https://www.google.com/search?q=your+search+terms+here"}
  Step 6: ACTION: press_key   PARAMS: {"key": "enter"}
  Step 7: ACTION: wait        PARAMS: {"seconds": 3}

═══ PHASE 3: READ SEARCH RESULTS ═══
  Step 8:  Click FIRST relevant blue link (use element [ID], skip ads)
  Step 9:  ACTION: wait       PARAMS: {"seconds": 3}
  Step 10: Scroll and read content. Tag: FINDING: [fact discovered]
  Step 11: ACTION: hotkey     PARAMS: {"keys": ["alt", "left"]}  ← go back
  Step 12: Click SECOND relevant result
  Step 13: Scroll, read, tag findings
  Step 14: Go back, visit THIRD source if needed

═══ PHASE 4: COMPILE REPORT ═══
  Step 15: ACTION: open_app   PARAMS: {"name": "notepad"}
           (If Notepad is already open, this focuses it — no duplicates!)
  Step 16: ACTION: wait       PARAMS: {"seconds": 2}
  Step 17: ACTION: click      PARAMS: {"x": 400, "y": 400}  ← click text area
  Step 18: ACTION: type_text_fast  PARAMS: {"text": "YOUR FULL RESEARCH REPORT WITH ALL FINDINGS"}
           ★ Use type_text_fast for the report — works perfectly with Korean/Unicode!
           ★ Write the ENTIRE report in a single type_text_fast call.
  Step 19: ACTION: hotkey     PARAMS: {"keys": ["ctrl", "s"]}

DO NOT say TASK_COMPLETE before Step 15. You MUST compile findings into a report.
""",

            "writing": """
╔══════════════════════════════════════════════════════════════════════╗
║              WRITING TASK — EXACT ACTION SEQUENCE                   ║
╚══════════════════════════════════════════════════════════════════════╝

  Step 1: ACTION: open_app   PARAMS: {"name": "notepad"}
          (If Notepad is already open, this focuses it — no duplicates!)
  Step 2: ACTION: wait       PARAMS: {"seconds": 2}
  Step 3: ACTION: click      PARAMS: {"x": 400, "y": 400}  ← click text area
  Step 4: ACTION: type_text_fast  PARAMS: {"text": "YOUR FULL DOCUMENT CONTENT HERE"}
          ★ Use type_text_fast for text content — works perfectly with Korean/Unicode!
          ★ Write REAL paragraphs — title, intro, body sections, conclusion
          ★ Write ALL content in a single type_text_fast call
          ★ Minimum 300 characters of substantive content
  Step 5: ACTION: hotkey     PARAMS: {"keys": ["ctrl", "s"]}
  Step 6: If Save As dialog → type filename → press Enter

DO NOT create empty files. DO NOT type only a title. Write REAL content.
""",

            "coding": """
╔══════════════════════════════════════════════════════════════════════╗
║              CODING TASK — EXACT ACTION SEQUENCE                    ║
╚══════════════════════════════════════════════════════════════════════╝

  Step 1: ACTION: open_app   PARAMS: {"name": "cmd"}  (or "code" for projects)
  Step 2: Navigate to working directory
  Step 3: Create file: ACTION: run_command PARAMS: {"command": "echo code > file.py"}
          OR type code in VS Code editor
  Step 4: Write COMPLETE, WORKING code — not stubs or placeholders
  Step 5: Save file (Ctrl+S in editor)
  Step 6: Run: ACTION: run_command PARAMS: {"command": "python file.py"}
  Step 7: If errors → read output → fix → re-run
  Step 8: Iterate until code works correctly

DO NOT create empty files. Write COMPLETE working code. TEST it before completing.
""",

            "browsing": """
╔══════════════════════════════════════════════════════════════════════╗
║              BROWSING TASK — EXACT ACTION SEQUENCE                  ║
╚══════════════════════════════════════════════════════════════════════╝

  Step 1: ACTION: open_app   PARAMS: {"name": "browser"}
  Step 2: ACTION: wait       PARAMS: {"seconds": 3}
  Step 3: ACTION: hotkey     PARAMS: {"keys": ["ctrl", "l"]}
  Step 4: ACTION: type_text  PARAMS: {"text": "https://target-url.com"}
  Step 5: ACTION: press_key  PARAMS: {"key": "enter"}
  Step 6: ACTION: wait       PARAMS: {"seconds": 3}
  Step 7: Interact with the page as needed (click, scroll, type)

★ If browser opens File Explorer → try: open_app "msedge"
★ ALWAYS Ctrl+L before typing URL
★ ALWAYS wait 3 seconds after pressing Enter
""",

            "automation": """
╔══════════════════════════════════════════════════════════════════════╗
║            AUTOMATION TASK — EXACT ACTION SEQUENCE                  ║
╚══════════════════════════════════════════════════════════════════════╝

  Step 1: Analyze what needs to be automated
  Step 2: ACTION: open_app   PARAMS: {"name": "cmd"}  (or appropriate tool)
  Step 3: Execute each automation step with run_command
  Step 4: Verify each step worked by examining output
  Step 5: Report results

Use run_command for scripting. Verify each step before moving on.
""",

            "data_analysis": """
╔══════════════════════════════════════════════════════════════════════╗
║           DATA ANALYSIS TASK — EXACT ACTION SEQUENCE                ║
╚══════════════════════════════════════════════════════════════════════╝

  Step 1: Open the data file or tool (Excel, Python, etc.)
  Step 2: Examine data structure (columns, types, rows)
  Step 3: Perform analysis using appropriate methods
  Step 4: Generate visualizations/summaries if requested
  Step 5: Write findings report in Notepad
  Step 6: Save report
""",

            "design": """
╔══════════════════════════════════════════════════════════════════════╗
║              DESIGN TASK — EXACT ACTION SEQUENCE                    ║
╚══════════════════════════════════════════════════════════════════════╝

  Step 1: Open design tool (Paint, Figma, etc.)
  Step 2: Examine the current canvas
  Step 3: Use design tools for your specific task
  Step 4: Verify visual output against requirements
  Step 5: Save/export the result
""",
        }
        return STRATEGIES.get(task_type, """
Look at the screenshot. Identify what app/window is open.
Determine what needs to be done for this task.
Execute step by step — ONE action at a time.
Verify each action worked before proceeding.
""")

    # ─── COMPLETION VERIFICATION ──────────────────────────

    def _verify_completion_allowed(self, task_type: str) -> tuple[bool, str]:
        """
        Check if the agent has done enough work to claim TASK_COMPLETE.
        Returns (allowed, reason).
        """
        MIN_ACTIONS = {
            "research": 8, "writing": 4, "coding": 4, "browsing": 4,
            "design": 3, "automation": 3, "data_analysis": 3, "general": 2,
        }
        
        min_required = MIN_ACTIONS.get(task_type, 3)
        
        if self._actions_executed < min_required:
            return False, f"Only {self._actions_executed} actions done, need at least {min_required} for {task_type}. Keep working."
        
        # Research tasks MUST have typing (report)
        if task_type == "research" and not self._has_typed_content:
            return False, "Research requires compiling findings. Open Notepad and write a report with your findings."

        if task_type == "research" and not self._has_saved:
            return False, "Research requires saving the report. Use Ctrl+S (hotkey) and complete the save dialog if shown."
        
        # Writing tasks MUST have typing
        if task_type == "writing" and not self._has_typed_content:
            return False, "Writing task but no content typed. Open an editor and write."

        if task_type == "writing" and not self._has_saved:
            return False, "Writing task requires saving the document. Use Ctrl+S (hotkey) and complete the save dialog if shown."
        
        # Coding tasks should have either typed or run commands
        if task_type == "coding" and not self._has_typed_content and self._actions_by_type.get("run_command", 0) == 0:
            return False, "Coding task requires writing code or running commands. Do the actual work."

        if task_type == "coding" and not self._has_saved and self._actions_by_type.get("run_command", 0) == 0:
            return False, "Coding task likely requires saving your edits. Use Ctrl+S in your editor or use run_command to write files."
        
        # Browsing tasks need at least some navigation
        if task_type == "browsing" and self._actions_by_type.get("type_text", 0) == 0:
            if self._actions_by_type.get("click", 0) + self._actions_by_type.get("click_element", 0) < 2:
                return False, "Browsing task requires navigating to URLs and interacting with pages."
        
        return True, "OK"

    def _track_action(self, action_type: str, params: dict):
        """Track executed actions for completion verification."""
        self._actions_executed += 1
        self._actions_by_type[action_type] = self._actions_by_type.get(action_type, 0) + 1
        
        if action_type in ("type_text", "type_text_fast"):
            text = params.get("text", "")
            if len(text) > 5:  # Meaningful typing, not just a single character
                self._has_typed_content = True
        
        if action_type == "open_app":
            self._has_opened_app = True

        if action_type == "hotkey":
            keys = params.get("keys", [])
            if isinstance(keys, list) and [k.lower() for k in keys] == ["ctrl", "s"]:
                self._has_saved = True

    # ─── TIER-ENFORCED ACTION EXECUTION ──────────────────

    async def _execute_action(self, ctx: "AgentContext", action_type: str, params: dict) -> dict:
        """
        Execute an OS action WITH tier/domain enforcement.
        Also tracks actions for completion verification.
        Returns {"success": False, "error": "..."} if action is not allowed.
        """
        # Check if action is allowed for this agent's tier+domain
        if action_type not in self._allowed_actions:
            msg = f"ACTION BLOCKED: '{action_type}' is not allowed for {self.name} (tier {self.tier}, domain {self.domain})"
            logger.warning(msg)
            await ctx.log(msg, "WARN")
            return {"success": False, "error": msg, "blocked": True}
        
        # Track action for completion verification
        self._track_action(action_type, params)
        
        # Execute via OS controller
        try:
            result = ctx.os.execute_action(action_type, params)
            result_dict = result if isinstance(result, dict) else {"success": True, "result": result}
            try:
                ctx.engine.record_action_result(ctx.session_id, action_type, result_dict)
            except Exception:
                pass
            return result_dict
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _execute_tool(self, tool_name: str, params: dict) -> dict:
        """Execute a specialized tool WITH domain enforcement."""
        return await execute_tool(tool_name, params, self._tools)

    # ─── SYSTEM PROMPT BUILDER ───────────────────────────

    def _build_base_system_prompt(self, extra_context: str = "", task_type: str = "") -> str:
        """
        Build tier-appropriate system prompt WITH task intelligence.
        
        - Lower tiers get shorter, simpler prompts
        - Higher tiers get full engine descriptions
        - All prompts include domain-specific action whitelist
        - Specialized tools section only for tiers that have them
        - NEW: Task strategy, browser guide, Windows knowledge, completion rules
        """
        profile = self._profile
        config = self._tier_config
        
        # Identity
        parts = [profile.persona]
        parts.append(f"Specialization: {profile.expertise}")
        parts.append(f"Tier: {profile.tier} | Domain: {profile.domain}")
        
        # Domain boundary warning
        parts.append(f"\n⚠ DOMAIN RESTRICTION: You are a {profile.domain} specialist. Stay within your domain.")
        
        # Self-detection warning (always include)
        parts.append(SELF_DETECTION_WARNING)
        
        # Engine capabilities description (only mention what's available)
        engines = []
        if self._engine_flags.get("vision"):
            engines.append("Vision (screenshot analysis)")
        if self._engine_flags.get("som"):
            engines.append("SoM (numbered UI element detection)")
        if self._engine_flags.get("planner"):
            engines.append("Planner (multi-step planning)")
        if self._engine_flags.get("memory"):
            engines.append("Memory (context retention)")
        if self._engine_flags.get("tool_engine"):
            engines.append("Tool Engine (action chaining with auto-retry)")
        
        if engines:
            parts.append(f"\nActive engines: {', '.join(engines)}")
        
        # Task completion rules (prevent premature completion)
        parts.append(TASK_COMPLETION_RULES)
        
        # Task strategy (if task type detected)
        if task_type:
            strategy = self._get_task_strategy(task_type)
            if strategy:
                parts.append(strategy)
        
        # Browser guide (for domains that use browsers)
        if profile.domain in ("research", "automation", "general") or task_type in ("research", "browsing"):
            parts.append(BROWSER_QUICK_REFERENCE)
        
        # Windows app knowledge (for all agents above F tier)
        if profile.tier != "F":
            parts.append(WINDOWS_APP_CHEATSHEET)
        
        # Mandatory rules (scaled by tier)
        parts.append("\n━━━ RULES ━━━")
        if config.vision_enabled:
            parts.append("1. LOOK FIRST: Describe what you see on the screenshot before acting.")
        parts.append(f"{'2' if config.vision_enabled else '1'}. ONE ACTION AT A TIME: Execute one action, then verify.")
        if config.verification_enabled:
            parts.append("3. VERIFY: Check the new screenshot after every action.")
        
        # SoM element-click instructions (only if SoM enabled)
        if config.som_enabled:
            parts.append("\n━━━ ELEMENT-BASED CLICKING (PREFERRED) ━━━")
            parts.append("The screenshot has NUMBERED LABELS [1], [2], [3]...")
            parts.append("★ Use click_element with element ID for accuracy:")
            parts.append("  ACTION: click_element    PARAMS: {\"id\": 5}")
            parts.append("Fallback — raw coordinates when no label:")
            parts.append("  ACTION: click            PARAMS: {\"x\": 500, \"y\": 300}")
        
        # Allowed actions (ONLY show what this agent can use)
        parts.append("\n━━━ ALLOWED ACTIONS ━━━")
        sorted_actions = sorted(self._allowed_actions)
        action_lines = []
        for act in sorted_actions:
            if act == "click": action_lines.append('  ACTION: click            PARAMS: {"x": 500, "y": 300}')
            elif act == "click_element": action_lines.append('  ACTION: click_element    PARAMS: {"id": 5}')
            elif act == "double_click": action_lines.append('  ACTION: double_click     PARAMS: {"x": 500, "y": 300}')
            elif act == "type_text": action_lines.append('  ACTION: type_text        PARAMS: {"text": "hello"}  ← clipboard paste for short text')
            elif act == "type_text_fast": action_lines.append('  ACTION: type_text_fast   PARAMS: {"text": "long text..."}  ← clipboard paste (BEST for Korean/Unicode and long text!)')
            elif act == "press_key": action_lines.append('  ACTION: press_key        PARAMS: {"key": "enter"}')
            elif act == "hotkey": action_lines.append('  ACTION: hotkey           PARAMS: {"keys": ["ctrl", "s"]}')
            elif act == "scroll": action_lines.append('  ACTION: scroll           PARAMS: {"clicks": -30}  ← scroll down one full page')
            elif act == "open_app": action_lines.append('  ACTION: open_app         PARAMS: {"name": "notepad"}')
            elif act == "run_command": action_lines.append('  ACTION: run_command      PARAMS: {"command": "dir"}')
            elif act == "drag": action_lines.append('  ACTION: drag             PARAMS: {"startX": 100, "startY": 100, "endX": 400, "endY": 300}')
            elif act == "move_mouse": action_lines.append('  ACTION: move_mouse       PARAMS: {"x": 500, "y": 300}')
            elif act == "close_app": action_lines.append('  ACTION: close_app        PARAMS: {"name": "notepad"}')
            elif act == "focus_window": action_lines.append('  ACTION: focus_window     PARAMS: {"title": "window name"}')
            elif act == "wait": action_lines.append('  ACTION: wait             PARAMS: {"seconds": 2}')
            else: action_lines.append(f'  ACTION: {act:18s} PARAMS: {{}}')
        parts.extend(action_lines)
        
        # Specialized tools (unique to this agent's domain+tier)
        tools_prompt = build_tools_prompt(self._tools)
        if tools_prompt:
            parts.append(tools_prompt)
        
        # Response format
        parts.append("\n━━━ RESPONSE FORMAT ━━━")
        if config.vision_enabled:
            parts.append("**OBSERVATION**: [What you see on screen]")
        parts.append("**REASONING**: [Why this action]")
        parts.append("**ACTION**: [action name]")
        parts.append("**PARAMS**: [JSON params]")
        parts.append("\nSay TASK_COMPLETE when done (only after meaningful work).")
        
        # Extra context (plan, memory, etc.)
        if extra_context:
            parts.append(f"\n{extra_context}")
        
        # Enforce prompt budget
        full_prompt = "\n".join(parts)
        if len(full_prompt) > config.system_prompt_budget:
            full_prompt = full_prompt[:config.system_prompt_budget - 20] + "\n[prompt truncated]"
        
        return full_prompt

    # ─── SMART INITIAL MESSAGE ───────────────────────────

    def _build_initial_user_message(self, prompt: str, task_type: str) -> str:
        """Build the initial user message with smart task-specific guidance."""
        
        TASK_OPENERS = {
            "research": (
                f"═══ RESEARCH TASK ═══\n{prompt}\n\n"
                "Look at the screenshot RIGHT NOW.\n"
                "• What window is in the foreground?\n"
                "• If you see the Ogenti dark chat window → IGNORE IT, press Alt+Tab\n"
                "• Your VERY FIRST action MUST be: ACTION: open_app PARAMS: {\"name\": \"chrome\"}\n"
                "• After Chrome opens, you will press Ctrl+L, type a Google search URL, and press Enter.\n"
                "• Do NOT skip the browser step. Do NOT use File Explorer. Do NOT say TASK_COMPLETE until you have a report saved."
            ),
            "writing": (
                f"═══ WRITING TASK ═══\n{prompt}\n\n"
                "Look at the screenshot.\n"
                "Your FIRST action: ACTION: open_app PARAMS: {\"name\": \"notepad\"}\n"
                "Then click the text area and start typing REAL content.\n"
                "Do NOT create empty files or type just a title."
            ),
            "coding": (
                f"═══ CODING TASK ═══\n{prompt}\n\n"
                "Look at the screenshot.\n"
                "Open VS Code or a terminal, then write ACTUAL working code.\n"
                "Test it before saying TASK_COMPLETE."
            ),
            "browsing": (
                f"═══ BROWSING TASK ═══\n{prompt}\n\n"
                "Look at the screenshot.\n"
                "FIRST action: ACTION: open_app PARAMS: {\"name\": \"chrome\"}\n"
                "Then Ctrl+L → type URL → Enter → wait for page load."
            ),
            "design": f"═══ DESIGN TASK ═══\n{prompt}\n\nOpen the design tool and describe the canvas state.",
            "automation": f"═══ AUTOMATION TASK ═══\n{prompt}\n\nAnalyze what needs automating, open the right tool, and execute step by step.",
            "data_analysis": f"═══ DATA ANALYSIS TASK ═══\n{prompt}\n\nOpen the data tool and begin analysis.",
        }
        
        return TASK_OPENERS.get(task_type, f"═══ TASK ═══\n{prompt}\n\nLook at the screenshot. Provide your first ACTION.")

    # ─── STUCK DETECTION ─────────────────────────────────

    def _get_unstuck_message(self, consecutive_failures: int, consecutive_empty: int, task_type: str) -> str:
        """Generate a context-aware unstuck message with visual decision tree guidance."""
        
        if consecutive_failures >= 4:
            return (
                "🚨 CRITICAL: MULTIPLE FAILURES IN A ROW. FULL RESET REQUIRED.\n\n"
                "STOP everything. You must use the VISUAL DECISION TREE:\n\n"
                "1. LOOK at the screenshot — what EXACTLY is on screen?\n"
                "   □ Dark chat window with agent names? → That's OGENTI (your own app). Switch away:\n"
                "     ACTION: hotkey PARAMS: {\"keys\": [\"alt\", \"tab\"]}\n"
                "   □ File Explorer with folders? → WRONG APP (unless task is file management). Close it:\n"
                "     ACTION: hotkey PARAMS: {\"keys\": [\"alt\", \"f4\"]}\n"
                "   □ Windows desktop with no apps? → START FRESH with the right app.\n"
                "   □ A dialog/popup blocking? → Dismiss it: click OK/Cancel/X button.\n"
                "   □ Correct app but wrong state? → Navigate to the right place.\n\n"
                "2. START FRESH with the RIGHT app for your task:\n"
                + {
                    "research": (
                        "   ACTION: open_app PARAMS: {\"name\": \"chrome\"}\n"
                        "   Then follow the EXACT sequence:\n"
                        "     wait 3s → Ctrl+L → type Google URL → Enter → wait 3s → click result"
                    ),
                    "writing": (
                        "   ACTION: open_app PARAMS: {\"name\": \"notepad\"}\n"
                        "   Then: wait 2s → click text area (x:400,y:400) → type_text your content"
                    ),
                    "coding": (
                        "   ACTION: open_app PARAMS: {\"name\": \"cmd\"}\n"
                        "   Then: run_command to create/edit files and run code"
                    ),
                    "browsing": (
                        "   ACTION: open_app PARAMS: {\"name\": \"chrome\"}\n"
                        "   Then: wait 3s → Ctrl+L → type URL → Enter → wait 3s"
                    ),
                }.get(task_type, "   ACTION: open_app PARAMS: {\"name\": \"notepad\"}") +
                "\n\n3. Use element [IDs] from the screenshot when clicking. They are MORE ACCURATE than coordinates."
            )
        
        if consecutive_empty >= 3:
            return (
                "⚠ You are NOT providing actions. Every response MUST end with ACTION and PARAMS.\n\n"
                "Look at the screenshot. USE THE VISUAL DECISION TREE:\n\n"
                "  IF you see: Browser window        → Continue browsing (Ctrl+L, type URL, click links)\n"
                "  IF you see: Text editor            → Click text area, start typing content\n"
                "  IF you see: Desktop/no app          → Open the right app\n"
                "  IF you see: Ogenti dark chat window → Switch away: Alt+Tab\n"
                "  IF you see: Popup/dialog            → Dismiss it (click OK/X)\n\n"
                f"For your {task_type} task, execute this RIGHT NOW:\n"
                + {
                    "research": "ACTION: open_app\nPARAMS: {\"name\": \"chrome\"}\n\nThen: Ctrl+L → type Google search URL → Enter → wait → click result → read → go back → repeat",
                    "writing": "ACTION: open_app\nPARAMS: {\"name\": \"notepad\"}\n\nThen: wait 2s → click text area → type your full content → Ctrl+S",
                    "coding": "ACTION: open_app\nPARAMS: {\"name\": \"cmd\"}\n\nThen: run_command to write code into files, then test it",
                    "browsing": "ACTION: open_app\nPARAMS: {\"name\": \"chrome\"}\n\nThen: Ctrl+L → type URL → Enter → wait → interact with page",
                }.get(task_type, "ACTION: open_app\nPARAMS: {\"name\": \"notepad\"}")
            )
        
        if consecutive_failures >= 2:
            return (
                f"⚠ {consecutive_failures} consecutive failures. Change your approach.\n\n"
                "TROUBLESHOOTING CHECKLIST:\n"
                "  □ Is the RIGHT app in the foreground? If not → focus_window or open_app\n"
                "  □ Are you clicking the right element? Use element [IDs] instead of coordinates\n"
                "  □ Is there a popup/dialog blocking? Dismiss it first\n"
                "  □ Did you try keyboard shortcut instead of clicking? Hotkeys are more reliable\n"
                "  □ Is the page still loading? Wait 3 seconds\n"
                "  □ Try a COMPLETELY different action. If clicking fails, try keyboard. If typing fails, click the field first."
            )
        
        return f"Continue your {task_type} task. Examine the screenshot and provide your next ACTION."

    # ─── ACTION PARSER WITH ENFORCEMENT ──────────────────

    def _parse_actions(self, text: str) -> list[dict]:
        """
        Parse ACTION: / PARAMS: pairs from LLM response.
        
        ENFORCES domain+tier whitelist — silently drops disallowed actions.
        Also parses TOOL: / TOOL_PARAMS: for specialized tools.
        """
        def _normalize_action_type(v: str) -> str:
            return (v or "").strip().lower()

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

        def _filter_allowed(actions_list: list[dict]) -> list[dict]:
            filtered: list[dict] = []
            for a in actions_list:
                atype = _normalize_action_type(a.get("type") or a.get("action"))
                params = a.get("params") if isinstance(a.get("params"), dict) else {}
                if not atype:
                    continue
                if atype in self._allowed_actions:
                    filtered.append({"type": atype, "params": params})
            return filtered

        # Try JSON blocks (fenced or inline) first
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
                        obj = json.loads(block)
                        actions_json = _filter_allowed(_coerce_actions(obj))
                        if actions_json:
                            return actions_json
                    except Exception:
                        continue

            starts = [p for p in (stripped.find("["), stripped.find("{")) if p >= 0]
            if starts:
                start = min(starts)
                end = max(stripped.rfind("]"), stripped.rfind("}")) + 1
                if end > start:
                    snippet = stripped[start:end]
                    obj = json.loads(snippet)
                    actions_json = _filter_allowed(_coerce_actions(obj))
                    if actions_json:
                        return actions_json
        except Exception:
            pass

        actions = []
        lines = text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            # Strip markdown formatting: **, *, -, bullet numbers, >
            line = line.replace("**", "").strip()
            line = line.lstrip("*->#").strip()
            # Strip numbered list prefixes: "1.", "2.", etc.
            import re as _re
            line = _re.sub(r'^\d+[\.\)]\s*', '', line).strip()
            
            # Parse standard OS actions (case-insensitive match)
            line_upper = line.upper()
            if line_upper.startswith("ACTION:"):
                action_rest = line[len("ACTION:"):].strip()
                params = {}

                # Handle inline format: ACTION: open_app PARAMS: {"name":"chrome"}
                if "PARAMS:" in action_rest.upper():
                    idx_p = action_rest.upper().index("PARAMS:")
                    action_type = action_rest[:idx_p].strip().lower()
                    params_str = action_rest[idx_p + len("PARAMS:"):].strip()
                    try:
                        params = json.loads(params_str)
                    except json.JSONDecodeError:
                        try:
                            params = json.loads(params_str.replace("'", '"'))
                        except:
                            pass
                else:
                    action_type = action_rest.lower()
                    # Also check next line for PARAMS: (case-insensitive)
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip().replace("**", "").strip()
                        next_line_clean = _re.sub(r'^\d+[\.\)]\s*', '', next_line.lstrip("*->#").strip()).strip()
                        if next_line_clean.upper().startswith("PARAMS:"):
                            params_str = next_line_clean[len("PARAMS:"):].strip()
                            try:
                                params = json.loads(params_str)
                            except json.JSONDecodeError:
                                try:
                                    params = json.loads(params_str.replace("'", '"'))
                                except:
                                    pass
                            i += 1
                
                # ENFORCE: only allow actions in this agent's whitelist
                if action_type in self._allowed_actions:
                    actions.append({"type": action_type, "params": params})
                else:
                    logger.warning(f"[{self.name}] Blocked disallowed action: '{action_type}'")
            
            # Parse specialized tool invocations (case-insensitive)
            elif line_upper.startswith("TOOL:"):
                tool_rest = line[len("TOOL:"):].strip()
                tool_params = {}

                # Handle inline format: TOOL: google_search TOOL_PARAMS: {"query":"..."}
                if "TOOL_PARAMS:" in tool_rest.upper():
                    idx_tp = tool_rest.upper().index("TOOL_PARAMS:")
                    tool_name = tool_rest[:idx_tp].strip().lower()
                    params_str = tool_rest[idx_tp + len("TOOL_PARAMS:"):].strip()
                    try:
                        tool_params = json.loads(params_str)
                    except json.JSONDecodeError:
                        try:
                            tool_params = json.loads(params_str.replace("'", '"'))
                        except:
                            pass
                else:
                    tool_name = tool_rest.lower()
                    if i + 1 < len(lines):
                        next_line = lines[i + 1].strip().replace("**", "").strip()
                        next_line_clean = _re.sub(r'^\d+[\.\)]\s*', '', next_line.lstrip("*->#").strip()).strip()
                        if next_line_clean.upper().startswith("TOOL_PARAMS:"):
                            params_str = next_line_clean[len("TOOL_PARAMS:"):].strip()
                            try:
                                tool_params = json.loads(params_str)
                            except json.JSONDecodeError:
                                try:
                                    tool_params = json.loads(params_str.replace("'", '"'))
                                except:
                                    pass
                            i += 1
                # Mark as tool action for separate handling
                actions.append({"type": "__tool__", "tool_name": tool_name, "params": tool_params})
            
            i += 1
        return actions

    # ─── TIER-AWARE CONFIG ───────────────────────────────

    def get_max_steps(self, config: dict) -> int:
        """Get max steps, capped by tier limit."""
        requested = config.get("maxSteps", self._tier_config.max_steps)
        return min(requested, self._tier_config.max_steps)

    def get_max_retries(self) -> int:
        return self._tier_config.max_retries

    def get_action_delay(self) -> float:
        return self._tier_config.action_delay

    async def _minimize_ogenti_window(self, ctx):
        """Minimize the Ogenti window so the LLM sees the actual desktop, not our app."""
        try:
            import pyautogui
            win = pyautogui.getActiveWindow()
            if win and ("ogenti" in (win.title or "").lower() or "agent" in (win.title or "").lower()):
                win.minimize()
                import asyncio
                await asyncio.sleep(0.5)
                await ctx.log("  Ogenti window minimized — LLM now sees desktop")
        except Exception as e:
            await ctx.log(f"  Could not minimize Ogenti window: {e}", "WARN")

    def reset_tracking(self):
        """Reset execution tracking for a new task."""
        self._actions_executed = 0
        self._actions_by_type = {}
        self._has_typed_content = False
        self._has_opened_app = False
        self._has_saved = False
        self._execution_start = time.time()

    def __repr__(self) -> str:
        return f"<Plugin: {self.name} v{self.version} [Tier {self.tier}/{self.domain}]>"
