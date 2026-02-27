"""
Shared prompt constants and definitions for the OSEN agent runtime.

Centralized here to eliminate duplication between engine.py and
collaboration_engine.py. Both modules import their shared prompt templates,
action definitions, and task intelligence data from this file.

Previously, these ~800 lines of constants were duplicated or lazily
cross-imported between engine.py and collaboration_engine.py, causing
maintenance burden and circular dependency workarounds.
"""

from enum import Enum as _Enum
import os as _os


# ═══════════════════════════════════════════════════════════════════════
# BROWSER DETECTION (lightweight)
# ═══════════════════════════════════════════════════════════════════════

def _detect_browser() -> str:
    """Detect which browser is installed. Returns 'chrome', 'msedge', or 'firefox'."""
    for name, paths in [
        ("chrome", [
            _os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            _os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            _os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ]),
        ("msedge", [
            _os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            _os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ]),
        ("firefox", [
            _os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            _os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
        ]),
    ]:
        if any(_os.path.exists(p) for p in paths):
            return name
    return "msedge"  # Safe default


# Detect once at module load
_BROWSER = _detect_browser()
_BROWSER_DISPLAY = {"chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox"}.get(_BROWSER, _BROWSER)


# ═══════════════════════════════════════════════════════════════════════
# TASK TYPE CLASSIFICATION
# ═══════════════════════════════════════════════════════════════════════

class TaskType(str, _Enum):
    """Classification of user tasks for strategy selection."""
    RESEARCH = "research"
    CODING = "coding"
    WRITING = "writing"
    DESIGN = "design"
    AUTOMATION = "automation"
    DATA_ANALYSIS = "data_analysis"
    BROWSING = "browsing"
    FILE_MANAGEMENT = "file_management"
    GENERAL = "general"


# ═══════════════════════════════════════════════════════════════════════
# SHARED ACTION DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════
# Used by both engine.py._build_system_prompt() and
# collaboration_engine.py._build_collab_system_prompt().
# Values are plain strings (NOT f-strings); they get interpolated into
# the final f-string via a variable, so use single braces for JSON.

ACTION_DEFINITIONS = {
    "click": '  ACTION: click          PARAMS: {"x": 500, "y": 300}',
    "double_click": '  ACTION: double_click   PARAMS: {"x": 500, "y": 300}',
    "right_click": '  ACTION: right_click    PARAMS: {"x": 500, "y": 300}',
    "click_element": '  ACTION: click_element          PARAMS: {"id": 5}',
    "double_click_element": '  ACTION: double_click_element   PARAMS: {"id": 5}',
    "right_click_element": '  ACTION: right_click_element    PARAMS: {"id": 5}',
    "type_text": '  ACTION: type_text      PARAMS: {"text": "hello"}',
    "type_text_fast": '  ACTION: type_text_fast PARAMS: {"text": "hello world"}',
    "press_key": '  ACTION: press_key      PARAMS: {"key": "enter"}',
    "hotkey": '  ACTION: hotkey         PARAMS: {"keys": ["ctrl", "s"]}',
    "scroll": '  ACTION: scroll         PARAMS: {"clicks": -5}  ← scroll down one full page',
    "open_app": '  ACTION: open_app       PARAMS: {"name": "notepad"}',
    "close_app": '  ACTION: close_app      PARAMS: {"name": "notepad"}',
    "focus_window": '  ACTION: focus_window   PARAMS: {"title": "Untitled"}',
    "move_mouse": '  ACTION: move_mouse     PARAMS: {"x": 500, "y": 300}',
    "drag": '  ACTION: drag           PARAMS: {"startX": 100, "startY": 100, "endX": 400, "endY": 300}',
    "run_command": '  ACTION: run_command    PARAMS: {"command": "dir"}',
    "wait": '  ACTION: wait           PARAMS: {"seconds": 2}',
    "clipboard_copy": '  ACTION: clipboard_copy PARAMS: {}',
    "clipboard_paste": '  ACTION: clipboard_paste PARAMS: {}',
    "clipboard_get": '  ACTION: clipboard_get  PARAMS: {}',
    "clipboard_set": '  ACTION: clipboard_set  PARAMS: {"text": "content"}',
}


# ═══════════════════════════════════════════════════════════════════════
# VALID ACTIONS SET
# ═══════════════════════════════════════════════════════════════════════

VALID_ACTIONS = {
    "click", "double_click", "right_click",
    "click_element", "double_click_element", "right_click_element",
    "type_text", "type_text_fast", "press_key", "hotkey",
    "move_mouse", "scroll", "drag",
    "open_app", "close_app", "focus_window", "get_window_list",
    "run_command", "screenshot", "wait",
    "clipboard_copy", "clipboard_paste", "clipboard_get", "clipboard_set",
}


# ─── Windows Application Intelligence ──────────────────────────────────

WINDOWS_APP_INTELLIGENCE = {
    "chrome": {"exe": "chrome", "title_hints": ["Chrome", "Google Chrome"], "fallback": "msedge"},
    "msedge": {"exe": "msedge", "title_hints": ["Edge", "Microsoft Edge"]},
    "firefox": {"exe": "firefox", "title_hints": ["Firefox", "Mozilla Firefox"]},
    "notepad": {"exe": "notepad", "title_hints": ["Notepad", "메모장", "Untitled"]},
    "code": {"exe": "code", "title_hints": ["Visual Studio Code"]},
    "terminal": {"exe": "wt", "title_hints": ["Terminal", "PowerShell"]},
    "cmd": {"exe": "cmd", "title_hints": ["Command Prompt"]},
    "powershell": {"exe": "powershell", "title_hints": ["PowerShell"]},
    "explorer": {"exe": "explorer", "title_hints": ["File Explorer", "탐색기"]},
    "word": {"exe": "winword", "title_hints": ["Word", "Microsoft Word"]},
    "excel": {"exe": "excel", "title_hints": ["Excel", "Microsoft Excel"]},
    "wordpad": {"exe": "wordpad", "title_hints": ["WordPad"]},
}

# ── Shared prompt fragments (D6) ──────────────────────────────────────
# Used by engine.py._build_system_prompt() and
# collaboration_engine.py._build_collab_system_prompt().
# Keep in sync with both callers.

APP_LAUNCH_GUIDE = """
CORRECT way to open apps (memorize these EXACTLY):
  ● Web browser:      ACTION: open_app   PARAMS: {{"name": "__BROWSER__"}}
  ● Edge browser:     ACTION: open_app   PARAMS: {{"name": "msedge"}}
  ● Notepad:          ACTION: open_app   PARAMS: {{"name": "notepad"}}
  ● VS Code:          ACTION: open_app   PARAMS: {{"name": "code"}}
  ● Terminal:         ACTION: open_app   PARAMS: {{"name": "cmd"}}
  ● PowerShell:       ACTION: open_app   PARAMS: {{"name": "powershell"}}
  ● File Explorer:    ACTION: open_app   PARAMS: {{"name": "explorer"}}

★ CRITICAL: File Explorer is ONLY for file management (copy, move, organize).
  NEVER use File Explorer for research, browsing, or information gathering.
  For ANYTHING involving the internet → use "__BROWSER__" or "msedge".
""".replace("__BROWSER__", _BROWSER)

PRECONDITION_RULES = """PRE-CONDITIONS CHECK (MANDATORY):
    ├─ To type text → FIRST verify cursor is in the target input field
    │   If not → click the input field first, THEN type
    ├─ To click a link → FIRST verify the page has loaded
    │   If still loading → wait 2-3 seconds
    ├─ To interact with an app → FIRST verify that app is in foreground
    │   If not → use focus_window or open_app
    └─ To scroll → FIRST verify you're in the correct window"""

SELF_DETECTION_WARNING = """The Ogenti application is YOUR OWN interface. If you see:
  - A dark window with "Ogenti", "agent runtime", "execution session"
  - An activity log, chat-like interface, agent names
→ That is YOUR OWN UI. Do NOT interact with it. Do NOT click on it.
→ The system will automatically minimize it for you. Just wait and proceed with your task.
→ Do NOT use Alt+Tab to switch away — use open_app to directly open the app you need.
→ NEVER press Alt+Tab repeatedly — this causes an infinite loop."""


# ─── Task Strategy Templates ──────────────────────────────────────────
# Injected into system prompt so the LLM knows EXACTLY how to proceed.

TASK_STRATEGY_PROMPTS = {
    TaskType.RESEARCH: """
╔══════════════════════════════════════════════════════════════════════╗
║                 RESEARCH TASK MASTER STRATEGY                        ║
╚══════════════════════════════════════════════════════════════════════╝

You MUST follow this EXACT workflow for research tasks. No shortcuts. No skipping.
You are researching REAL information from the internet and compiling a REAL report.

██████████████████████████████████████████████████████████████████████
██  CRITICAL RULES — VIOLATING THESE WASTES YOUR LIMITED STEPS     ██
██████████████████████████████████████████████████████████████████████

  1. COOKIE BANNERS / CONSENT POPUPS:
     → Click "Accept All" or "Accept" ONCE. If it doesn't dismiss, IGNORE IT.
     → NEVER click "Deny" or "Reject" — these often don't work.
     → NEVER retry a cookie banner click more than once. Just scroll past it.
     → Cookie banners do NOT block you from reading the page text.

  2. DO NOT USE Ctrl+A or Ctrl+C on web pages:
     → Copying the entire page is USELESS — it grabs menus, ads, footers.
     → Instead: READ the screen with your eyes and write FINDING: lines.
     → Your job is to UNDERSTAND and EXTRACT key facts, not copy HTML.

  3. DO NOT click "Cite", "Download PDF", "Export" or any bibliographic buttons:
     → You can see the title, authors, journal, year, and DOI on the page.
     → Just READ them from the screen and write FINDING: lines.
     → Citation buttons often open popups that waste 3-5 clicks.

  4. STEP BUDGET: You have ~30 steps total. Budget them wisely:
     → Opening browser + navigating:  3 steps
     → Per source (click + scroll×5 + back): 7 steps
     → 3 sources total:              21 steps
     → Compile report in Notepad:     6 steps
     → Total:                        30 steps
     → Every wasted click on banners/popups steals from your research.

  5. MANDATORY SCROLL-AND-READ PROTOCOL (per page):
     → You MUST scroll at least 5 times on every page you visit.
     → After EACH scroll, write at least 1 FINDING: line.
     → You MUST write at least 3 FINDING: lines per page before leaving.
     → One screenshot = ~20% of a page. If you scroll once and leave, 
       you read almost nothing.

═══ PHASE 1: OPEN WEB BROWSER (Steps 1-3) ═══

Step 1 — Launch browser:
  ACTION: open_app    PARAMS: {"name": "__BROWSER__"}

Step 2 — Wait for browser:
  ACTION: wait        PARAMS: {"seconds": 3}

Step 3 — VERIFY browser is in foreground:
  ✓ Browser title bar at the top (__BROWSER_DISPLAY__ or Edge)
  If you see File Explorer → Do: ACTION: open_app PARAMS: {"name": "msedge"}
  If you see the Ogenti window → Ignore it. Use open_app to launch browser.

═══ PHASE 2: SEARCH GOOGLE (Steps 4-7) ═══

Step 4 — Focus the address bar:
  ACTION: hotkey      PARAMS: {"keys": ["ctrl", "l"]}

Step 5 — Type the Google search URL:
  ACTION: type_text   PARAMS: {"text": "https://www.google.com/search?q=YOUR+SEARCH+TERMS+HERE"}
  ★ Replace spaces with + signs. Use specific search terms.

Step 6 — Press Enter:
  ACTION: press_key   PARAMS: {"key": "enter"}

Step 7 — Wait:
  ACTION: wait        PARAMS: {"seconds": 3}

═══ PHASE 3: VISIT SOURCES & READ CONTENT (Steps 8-22) ═══

  ═══ Source 1 (steps 8-13) ═══

Step 8 — Click the FIRST relevant blue link (NON-AD):
  ACTION: click_element   PARAMS: {"id": <number of blue link>}

Step 9 — Wait for page to load + handle cookie banner:
  ACTION: wait        PARAMS: {"seconds": 3}
  If a cookie banner appears → click "Accept All" or "Accept" ONCE.
  If it doesn't dismiss → IGNORE it and proceed to scroll.

Step 10-12 — ★★★ SCROLL AND READ (minimum 5 scrolls):
  REPEAT this loop at least 5 times:
    a) Look at the screen. READ all visible text.
    b) Write what you found:
       FINDING: [exact fact, number, name, date, quote — copied from screen]
    c) Scroll down:
       ACTION: scroll    PARAMS: {"clicks": -5}
    d) Did new content appear? YES → repeat. NO → done with this page.

  ★ You MUST have written at least 3 FINDING: lines before Step 13.

Step 13 — Go back to search results:
  ACTION: hotkey      PARAMS: {"keys": ["alt", "left"]}
  ACTION: wait        PARAMS: {"seconds": 2}

  ═══ Source 2 (steps 14-18) ═══

Step 14 — Click the SECOND relevant result.
Step 15-17 — SCROLL AND READ (same protocol: 5+ scrolls, 3+ findings).
Step 18 — Go back.

  ═══ Source 3 (steps 19-22) ═══

Step 19 — Click the THIRD relevant result.
Step 20-21 — SCROLL AND READ (same protocol: 5+ scrolls, 3+ findings).
Step 22 — Done gathering. You should have 9+ FINDING: lines total.

═══ PHASE 4: COMPILE RESEARCH REPORT (Steps 23-28) ═══

Step 23 — Open Notepad:
  ACTION: open_app    PARAMS: {"name": "notepad"}
  ACTION: wait        PARAMS: {"seconds": 2}

Step 24 — Click inside the Notepad text area:
  ACTION: click       PARAMS: {"x": 400, "y": 400}

Step 25 — Type the FULL research report:
  ACTION: type_text_fast   PARAMS: {"text": "YOUR COMPLETE REPORT"}
  
  ★★★ Use type_text_fast (NOT type_text) for the report body.
  ★★★ Write the ENTIRE report in ONE type_text_fast call.
  ★★★ The report MUST synthesize your FINDING: lines into a coherent document:
  - Title
  - Introduction / overview
  - Key findings organized by theme
  - Specific facts, numbers, dates from your FINDING: lines
  - Source URLs
  - Conclusion
  - Minimum 500 characters

Step 26 — Save the file:
  ACTION: hotkey      PARAMS: {"keys": ["ctrl", "s"]}
  ACTION: wait        PARAMS: {"seconds": 2}

Step 27 — If Save As dialog appears, type filename:
  ACTION: type_text   PARAMS: {"text": "research_report.txt"}
  ACTION: press_key   PARAMS: {"key": "enter"}

Step 28 — Verify: title bar should show the filename now.

═══ COMPLETION CHECKLIST ═══
  ☑ Opened a web BROWSER (NOT File Explorer)
  ☑ Searched Google with specific terms
  ☑ Visited and READ at least 2 pages (scrolled 5+ times each)
  ☑ Tagged at least 6 findings with FINDING: prefix
  ☑ Compiled a report in Notepad (500+ chars of real content)
  ☑ Saved the report file

Only say TASK_COMPLETE when ALL boxes above are checked.
""".replace("__BROWSER__", _BROWSER).replace("__BROWSER_DISPLAY__", _BROWSER_DISPLAY),
    TaskType.CODING: """
╔══════════════════════════════════════════════════════════════════════╗
║                  CODING TASK MASTER STRATEGY                        ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PHASE 1: SETUP ENVIRONMENT ═══
  Open terminal: ACTION: open_app  PARAMS: {"name": "cmd"}
  Navigate to workspace: ACTION: run_command PARAMS: {"command": "cd %USERPROFILE%\\Desktop"}
  Create project folder: ACTION: run_command PARAMS: {"command": "mkdir project && cd project"}

═══ PHASE 2: WRITE CODE ═══
  Option A — Terminal (for scripts):
    ACTION: run_command  PARAMS: {"command": "echo import sys > main.py"}
    Use multi-line creation with PowerShell Set-Content or echo >>
  
  Option B — VS Code (for projects):
    ACTION: open_app     PARAMS: {"name": "code"}
    ACTION: hotkey       PARAMS: {"keys": ["ctrl", "n"]}  (new file)
    Click the editor area, then type your code
    ACTION: hotkey       PARAMS: {"keys": ["ctrl", "s"]}  (save)

═══ PHASE 3: TEST & DEBUG ═══
  Run code: ACTION: run_command  PARAMS: {"command": "python main.py"}
  If errors → read output → identify line → fix → re-run
  Iterate until code works correctly.

═══ PHASE 4: VERIFY ═══
  Read file: ACTION: run_command  PARAMS: {"command": "type main.py"}
  Run again to confirm: ACTION: run_command  PARAMS: {"command": "python main.py"}

CHECKLIST before TASK_COMPLETE:
  ☑ Created file(s) with REAL working code
  ☑ Ran the code at least once
  ☑ Fixed any errors that appeared
  ☑ Code produces correct output
""",
    TaskType.WRITING: """
╔══════════════════════════════════════════════════════════════════════╗
║                  WRITING TASK MASTER STRATEGY                       ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PHASE 1: OPEN TEXT EDITOR ═══
  ACTION: open_app   PARAMS: {"name": "notepad"}
  ACTION: wait       PARAMS: {"seconds": 2}
  Click inside the text area to ensure cursor focus.

═══ PHASE 2: WRITE CONTENT ═══
  ACTION: type_text   PARAMS: {"text": "YOUR FULL DOCUMENT CONTENT"}
  
  ★ Write SUBSTANTIVE content — real paragraphs with information.
  ★ Include: title, introduction, body sections, conclusion.
  ★ Minimum 300 characters of real content.
  ★ Do NOT just type a title or placeholder.

═══ PHASE 3: SAVE ═══
  ACTION: hotkey      PARAMS: {"keys": ["ctrl", "s"]}
  If Save As dialog appears:
    ACTION: type_text   PARAMS: {"text": "document.txt"}
    ACTION: press_key   PARAMS: {"key": "enter"}

CHECKLIST before TASK_COMPLETE:
  ☑ Opened a text editor
  ☑ Typed real, substantive content (not just a title)
  ☑ Saved the file
""",
    TaskType.BROWSING: """
╔══════════════════════════════════════════════════════════════════════╗
║                 BROWSING TASK MASTER STRATEGY                       ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PHASE 1: OPEN BROWSER ═══
  Step 1: ACTION: open_app   PARAMS: {"name": "__BROWSER__"}
  Step 2: ACTION: wait       PARAMS: {"seconds": 3}
  Step 3: VERIFY — check screenshot shows browser (NOT File Explorer!)
          If File Explorer → WRONG! Do: ACTION: open_app PARAMS: {"name": "msedge"}

═══ PHASE 2: NAVIGATE TO TARGET ═══
  Step 4: ACTION: hotkey     PARAMS: {"keys": ["ctrl", "l"]}   ← focus address bar (MANDATORY)
  Step 5: ACTION: type_text  PARAMS: {"text": "https://target-url.com"}
  Step 6: ACTION: press_key  PARAMS: {"key": "enter"}
  Step 7: ACTION: wait       PARAMS: {"seconds": 3}   ← wait for page load

═══ PHASE 3: INTERACT WITH PAGE ═══
  Step 8: Examine the loaded page. What do you see?
  • If it's a search engine → click relevant result links
  • If it's an article → scroll down to read content
  • If it's a form → click input fields and fill them
  • If there's a cookie popup → click Accept/OK to dismiss
  • If page is still loading → wait 3 more seconds

  Navigation shortcuts:
    Go back:    ACTION: hotkey  PARAMS: {"keys": ["alt", "left"]}
    New tab:    ACTION: hotkey  PARAMS: {"keys": ["ctrl", "t"]}
    Close tab:  ACTION: hotkey  PARAMS: {"keys": ["ctrl", "w"]}
    Scroll:     ACTION: scroll  PARAMS: {"clicks": -5}
    Find text:  ACTION: hotkey  PARAMS: {"keys": ["ctrl", "f"]}

═══ PHASE 4: EXTRACT INFORMATION ═══
  If you need to save information from the page:
  Step 9:  Select text → Ctrl+A or highlight with mouse
  Step 10: Copy → Ctrl+C
  Step 11: Open Notepad → ACTION: open_app PARAMS: {"name": "notepad"}
  Step 12: Paste → Ctrl+V
  Step 13: Save → Ctrl+S

CHECKLIST before TASK_COMPLETE:
  ☑ Opened a web BROWSER (Chrome or Edge)
  ☑ Navigated to the target URL
  ☑ Page loaded successfully
  ☑ Interacted with the page as required by the task
  ☑ Extracted or saved any requested information
""".replace("__BROWSER__", _BROWSER),
    TaskType.DESIGN: """
╔══════════════════════════════════════════════════════════════════════╗
║                  DESIGN TASK MASTER STRATEGY                        ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PHASE 1: OPEN DESIGN TOOL ═══
  Option A — MS Paint (simple graphics):
    ACTION: open_app   PARAMS: {"name": "mspaint"}
    ACTION: wait       PARAMS: {"seconds": 2}
  Option B — Web-based tool (Figma, Canva):
    ACTION: open_app   PARAMS: {"name": "chrome"}
    ACTION: wait       PARAMS: {"seconds": 3}
    Navigate to the tool URL
  Option C — Code-based design (HTML/CSS):
    ACTION: open_app   PARAMS: {"name": "notepad"}
    Write HTML/CSS code for the design

═══ PHASE 2: CREATE THE DESIGN ═══
  • Use appropriate tools for shapes, colors, text
  • For Paint: select tools from toolbar, draw on canvas
  • For code-based: write clean HTML/CSS with proper styling
  • Regularly verify your progress by examining the screenshot

═══ PHASE 3: SAVE OUTPUT ═══
  ACTION: hotkey  PARAMS: {"keys": ["ctrl", "s"]}
  Name the file appropriately in the Save dialog

CHECKLIST before TASK_COMPLETE:
  ☑ Opened appropriate design tool
  ☑ Created actual visual content (not blank canvas)
  ☑ Design matches the requirements
  ☑ Saved the output file
""",
    TaskType.AUTOMATION: """
╔══════════════════════════════════════════════════════════════════════╗
║               AUTOMATION TASK MASTER STRATEGY                       ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PHASE 1: ANALYZE THE TASK ═══
  Understand what needs to be automated:
  • File operations (rename, move, copy, delete)
  • Software installation/configuration
  • System settings changes
  • Repetitive actions

═══ PHASE 2: OPEN APPROPRIATE TOOL ═══
  For file operations:
    ACTION: open_app  PARAMS: {"name": "explorer"}
    Or: ACTION: open_app  PARAMS: {"name": "cmd"}
  For scripting:
    ACTION: open_app  PARAMS: {"name": "powershell"}
  For system settings:
    ACTION: open_app  PARAMS: {"name": "cmd"}
    ACTION: run_command PARAMS: {"command": "start ms-settings:"}

═══ PHASE 3: EXECUTE AUTOMATION ═══
  Use run_command for terminal operations:
    ACTION: run_command PARAMS: {"command": "your command here"}
  
  Common automation commands:
  • File rename:  ren "oldname.txt" "newname.txt"
  • File copy:    copy "source.txt" "dest.txt"
  • File move:    move "source.txt" "C:\\destination\\"
  • Create dir:   mkdir "new_folder"
  • List files:   dir /b
  • Find files:   dir /s /b "*.txt"

═══ PHASE 4: VERIFY RESULTS ═══
  Check that automation worked:
    ACTION: run_command PARAMS: {"command": "dir"}
  Verify file contents:
    ACTION: run_command PARAMS: {"command": "type filename.txt"}

CHECKLIST before TASK_COMPLETE:
  ☑ Identified what needs to be automated
  ☑ Executed the automation commands/actions
  ☑ Verified the results are correct
  ☑ No errors remaining
""",
    TaskType.DATA_ANALYSIS: """
╔══════════════════════════════════════════════════════════════════════╗
║             DATA ANALYSIS TASK MASTER STRATEGY                      ║
╚══════════════════════════════════════════════════════════════════════╝

═══ PHASE 1: OPEN DATA ═══
  For CSV/text data:
    ACTION: open_app  PARAMS: {"name": "cmd"}
    ACTION: run_command PARAMS: {"command": "type data.csv"}
  For Excel:
    ACTION: open_app  PARAMS: {"name": "excel"}
  For Python analysis:
    ACTION: open_app  PARAMS: {"name": "cmd"}
    Write and run Python scripts

═══ PHASE 2: EXPLORE DATA ═══
  • Examine data structure (columns, rows, types)
  • Look for patterns, outliers, missing values
  • Note key statistics (count, min, max, average)

═══ PHASE 3: ANALYZE ═══
  • Apply requested analysis methods
  • Create calculations, aggregations, filters
  • Generate visualizations if requested (Python matplotlib, Excel charts)

═══ PHASE 4: REPORT FINDINGS ═══
  ACTION: open_app  PARAMS: {"name": "notepad"}
  ACTION: wait      PARAMS: {"seconds": 2}
  ACTION: click     PARAMS: {"x": 400, "y": 400}
  ACTION: type_text PARAMS: {"text": "YOUR ANALYSIS REPORT WITH DATA FINDINGS"}
  ACTION: hotkey    PARAMS: {"keys": ["ctrl", "s"]}

CHECKLIST before TASK_COMPLETE:
  ☑ Loaded and examined the data
  ☑ Performed the requested analysis
  ☑ Compiled findings into a readable report
  ☑ Saved the report
""",
}
# Fill defaults for any TaskType not explicitly defined
for _tt in TaskType:
    if _tt not in TASK_STRATEGY_PROMPTS:
        TASK_STRATEGY_PROMPTS[_tt] = ""


# ─── Browser Navigation Guide ──────────────────────────────────────────

BROWSER_GUIDE = """
━━━ WEB BROWSER NAVIGATION CHEATSHEET ━━━
Focus address bar:    ACTION: hotkey    PARAMS: {"keys": ["ctrl", "l"]}
Navigate to URL:      Type URL → press Enter
Search on Google:     Type "https://www.google.com/search?q=your+query" → Enter
Go back:             ACTION: hotkey    PARAMS: {"keys": ["alt", "left"]}
Go forward:          ACTION: hotkey    PARAMS: {"keys": ["alt", "right"]}
New tab:             ACTION: hotkey    PARAMS: {"keys": ["ctrl", "t"]}
Close tab:           ACTION: hotkey    PARAMS: {"keys": ["ctrl", "w"]}
Scroll down:         ACTION: scroll    PARAMS: {"clicks": -5}
Scroll up:           ACTION: scroll    PARAMS: {"clicks": 5}
Select all text:     ACTION: hotkey    PARAMS: {"keys": ["ctrl", "a"]}
Copy:                ACTION: hotkey    PARAMS: {"keys": ["ctrl", "c"]}
Find on page:        ACTION: hotkey    PARAMS: {"keys": ["ctrl", "f"]}
Refresh page:        ACTION: press_key PARAMS: {"key": "f5"}
"""


# ─── Completion Verification ──────────────────────────────────────────

COMPLETION_RULES = {
    TaskType.RESEARCH: {
        "min_actions": 8,
        "required_action_types": {"open_app"},
        "must_have_typed": True,
        "rejection": (
            "⚠️ TASK_COMPLETE REJECTED — Research task requirements not met.\n"
            "Required:\n"
            "  □ Open a web browser and visit at least 2 different sources\n"
            "  □ Tag at least 3 findings with FINDING: [fact]\n"
            "  □ Scroll through pages to read beyond just the first screen\n"
            "  □ Write a report with REAL content based on your findings\n"
            "You must complete ALL of these before saying TASK_COMPLETE.\n"
            "NOW: Continue working. What's the next step?"
        ),
    },
    TaskType.CODING: {
        "min_actions": 4,
        "required_action_types": set(),
        "must_have_typed": True,
        "rejection": "⚠️ TASK_COMPLETE REJECTED — You must write actual code before completing.",
    },
    TaskType.WRITING: {
        "min_actions": 3,
        "required_action_types": set(),
        "must_have_typed": True,
        "rejection": "⚠️ TASK_COMPLETE REJECTED — You must type substantial content before completing.",
    },
}
# Fill defaults for any TaskType not explicitly defined
for _tt2 in TaskType:
    if _tt2 not in COMPLETION_RULES:
        COMPLETION_RULES[_tt2] = {"min_actions": 1, "required_action_types": set(), "must_have_typed": False, "rejection": ""}


# ─── Ogenti Self-Detection ──────────────────────────────────────────
OGENTI_KEYWORDS = ["ogenti", "agent runtime", "execution session", "activity log", "dispatched to agent"]

def _is_ogenti_screen(som_description: str) -> bool:
    """Detect if the current screen shows Ogenti's own UI (not the target app)."""
    desc_lower = som_description.lower() if som_description else ""
    return any(kw in desc_lower for kw in OGENTI_KEYWORDS)
