"""
Apex Coder Agent v2 — Tier S+ ($129.99)
Slug: apex_coder

Domain: coding (with cross-domain tool access)
Engines: ALL — Vision + SoM + Planner + Memory + ToolEngine
Tools: ALL coding tools + cross-domain tools
Actions: FULL coding action set (includes run_command, keyboard, scroll, type, click)

v2 — ADVANCED CODING INTELLIGENCE:
- Detects coding sub-task (web dev, data, API, etc.)
- Multi-file project workflow: scaffold → implement → test → fix → commit
- Terminal output analysis with error pattern detection
- Completion verification: must write code + run it + tests pass
- Memory integration for multi-session projects
- Language-specific strategies (Python, JS, C++, Java, etc.)
- IDE navigation knowledge (VS Code shortcuts, file management)
"""

import asyncio
import json
import re
from plugins.base_plugin import BasePlugin

try:
    from core.engine import AgentContext
    from core.planner_engine import PlannerEngine
    from core.memory_engine import MemoryEngine
except ImportError:
    AgentContext = None
    PlannerEngine = None
    MemoryEngine = None


# ── ADVANCED CODING INTELLIGENCE ──

APEX_CODING_WORKFLOW = """
APEX CODING WORKFLOW — SUPREME TIER:

PHASE 1: ANALYZE & PLAN
- Read the requirements carefully
- Identify: language, framework, dependencies, file structure
- Plan architecture before writing any code

PHASE 2: SETUP ENVIRONMENT
- Terminal: ACTION open_app {"name": "cmd"} or ACTION open_app {"name": "powershell"}
- Navigate: ACTION run_command {"command": "cd %USERPROFILE%\\\\Desktop && mkdir project && cd project"}
- Init project:
  Python: ACTION run_command {"command": "python -m venv venv && venv\\\\Scripts\\\\activate"}
  Node.js: ACTION run_command {"command": "npm init -y"}
  Git: ACTION run_command {"command": "git init"}

PHASE 3: IMPLEMENT (choose best method)
Method A — Terminal file creation (quick scripts):
  ACTION run_command {"command": "echo import sys > main.py"}
  ACTION run_command {"command": "echo print('hello') >> main.py"}

Method B — VS Code (complex projects):
  ACTION open_app {"name": "code"}
  ACTION run_command {"command": "code ."}  (open folder in VS Code)
  ACTION hotkey {"keys": ["ctrl", "n"]}  (new file)
  ACTION type_text {"text": "<your code>"}
  ACTION hotkey {"keys": ["ctrl", "s"]}  (save)

Method C — Notepad (medium files):
  ACTION open_app {"name": "notepad"}
  ACTION type_text {"text": "<full file content>"}
  ACTION hotkey {"keys": ["ctrl", "s"]}

Method D — PowerShell heredoc (multi-line files):
  ACTION run_command {"command": "@'\\nimport sys\\n\\ndef main():\\n    print('Hello')\\n'@ | Out-File main.py -Encoding utf8"}

PHASE 4: TEST & DEBUG  
- Run: ACTION run_command {"command": "python main.py"}
- Test: ACTION run_command {"command": "python -m pytest tests/"}
- If error: Read output → identify line → fix → re-run
- Lint: Use code_lint TOOL or ACTION run_command {"command": "python -m pylint main.py"}

PHASE 5: VERIFY & COMMIT
- Read file to verify: ACTION run_command {"command": "type main.py"}
- Test again to confirm: ACTION run_command {"command": "python main.py"}
- Git commit: ACTION run_command {"command": "git add . && git commit -m 'feat: initial implementation'"}
"""

LANGUAGE_STRATEGIES = {
    "python": """
PYTHON STRATEGY:
- Create .py files using echo or notepad
- Use 'python' or 'py' to run (Windows may use 'py' if 'python' not in PATH)
- Install packages: pip install package_name
- Virtual env: python -m venv .venv && .venv\\Scripts\\activate
- Test: python -m pytest or python -m unittest discover
- Format: python -m black .
- Lint: python -m pylint *.py
""",
    "javascript": """
JAVASCRIPT/NODE.JS STRATEGY:
- Initialize: npm init -y
- Create .js files
- Run: node script.js
- Install deps: npm install express axios etc
- Test: npm test (needs package.json scripts)
- For web: create index.html + script.js, open in browser
""",
    "typescript": """
TYPESCRIPT STRATEGY:
- Init: npm init -y && npm install typescript @types/node -D
- Create tsconfig.json: npx tsc --init
- Write .ts files → compile: npx tsc
- Run compiled: node dist/index.js
- Or use ts-node: npx ts-node src/index.ts
""",
    "html_css": """
HTML/CSS STRATEGY:
- Create index.html with full HTML structure
- Create style.css and link it
- Open in browser: start index.html
- Add JavaScript for interactivity
""",
    "cpp": """
C/C++ STRATEGY:
- Create .c or .cpp file
- Compile: gcc main.c -o main.exe (C) or g++ main.cpp -o main.exe (C++)
- Run: .\\main.exe
- Debug: compile with -g flag, use gdb
""",
    "java": """
JAVA STRATEGY:
- Create .java file (class name MUST match filename)
- Compile: javac Main.java
- Run: java Main
- Package: jar cvf app.jar *.class
""",
    "csharp": """
C# STRATEGY:
- Create with dotnet: dotnet new console -n MyApp
- cd MyApp
- Edit Program.cs
- Run: dotnet run
- Test: dotnet test
""",
}

IDE_SHORTCUTS = """
VS CODE KEYBOARD SHORTCUTS:
  Ctrl+N          New file
  Ctrl+S          Save file
  Ctrl+Shift+S    Save As
  Ctrl+O          Open file
  Ctrl+`          Toggle terminal
  Ctrl+Shift+`    New terminal
  Ctrl+P          Quick open file
  Ctrl+Shift+P    Command palette
  Ctrl+B          Toggle sidebar
  Ctrl+/          Toggle comment
  Ctrl+D          Select next occurrence
  Ctrl+Shift+K    Delete line
  Alt+Up/Down     Move line up/down
  Ctrl+Shift+F    Search in files
  F5              Start debugging
  Ctrl+F5         Run without debugging

CMD/POWERSHELL TIPS:
  dir             List files
  type file.txt   Read file content
  cd folder       Change directory
  cd ..           Go up one directory
  mkdir name      Create directory
  del file        Delete file
  copy src dst    Copy file
  ren old new     Rename file
  cls             Clear screen
  exit            Close terminal
"""

CODING_ERROR_PATTERNS = {
    "SyntaxError": "Check for missing colons, brackets, or quotes.",
    "IndentationError": "Fix indentation — use 4 spaces consistently.",
    "NameError": "Variable/function not defined. Check spelling or add import.",
    "ImportError": "Module not found. Install with: pip install <module>",
    "ModuleNotFoundError": "Module not installed. Run: pip install <module>",
    "TypeError": "Wrong argument type or count. Check function signature.",
    "FileNotFoundError": "File/path doesn't exist. Check cd and spelling.",
    "PermissionError": "Access denied. Try running as admin.",
    "npm ERR!": "NPM error. Try: npm install, or delete node_modules & reinstall.",
    "Cannot find module": "Node module missing. Run: npm install",
    "ENOENT": "File/directory not found. Check the path.",
    "'python' is not recognized": "Python not in PATH. Try 'py' instead, or install Python.",
    "'node' is not recognized": "Node.js not installed or not in PATH.",
    "error TS": "TypeScript compilation error. Check the error line and fix types.",
    "FAILED": "Test failed. Read the assertion error to understand what went wrong.",
    "BUILD FAILED": "Build failed. Check for compilation/syntax errors.",
}

APEX_COMPLETION_RULES = """
APEX CODER COMPLETION RULES:
1. You MUST have created at least one code file with real content
2. You MUST have run the code at least once
3. If there are test failures, you MUST fix them first
4. If there are compilation errors, you MUST fix them first
5. Files must contain actual, working code (not empty or placeholder)
6. For multi-file projects: ALL required files must exist
7. Do NOT complete if:
   - You only opened an editor without writing code
   - The code has unfixed errors/test failures
   - You created a project structure but didn't implement anything
"""


class ApexCoderAgent(BasePlugin):
    name = "Apex Coder Agent"
    description = "Supreme S+ coding agent. Full engine stack, all coding tools, planning with memory, advanced coding intelligence."
    version = "4.2.0"
    slug = "apex_coder"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()
        flags = self._engine_flags

        # Reset tracking
        self.reset_tracking()

        # ═══ Minimize Ogenti so LLM sees the desktop ═══
        await self._minimize_ogenti_window(ctx)
        
        # Detect task type and coding language
        task_type = self._detect_task_type(prompt)
        coding_lang = self._detect_language(prompt)
        coding_sub = self._detect_coding_project_type(prompt)

        await ctx.log(f"★ {self.name} v{self.version} [Tier {self.tier}/coding] — SUPREME CODER")
        await ctx.log(f"  Task: {task_type} | Lang: {coding_lang} | Project: {coding_sub}")
        await ctx.log(f"  Steps: {max_steps} | Retries: {max_retries} | Tools: {len(self.tools)}")

        # ── MEMORY: Recall previous coding sessions ──
        memory = None
        memory_context = ""
        if flags.get("memory") and MemoryEngine:
            memory = MemoryEngine()
            past = memory.recall(query=prompt, top_k=10)
            if past:
                memory_context = "\n\nPREVIOUS SESSION MEMORY:\n" + "\n".join(
                    f"  [{m.get('created_at', '?')}] {m.get('content', '')[:200]}" for m in past
                )
                await ctx.log(f"  Memory: {len(past)} recalled items")

        # ── PLANNER: Full architecture planning ──
        plan = None
        plan_text = ""
        planner = None
        if flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Coding task [{coding_lang}/{coding_sub}]. Full terminal+editor access. Plan: setup → architecture → implement → test → fix → verify.{memory_context}"
            )
            plan_text = "\n\nArchitecture Plan:\n" + "\n".join(
                f"  [{s.step_id}] {'✓' if s.status=='completed' else '→' if s.status=='running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        # Get language-specific strategy
        lang_strategy = LANGUAGE_STRATEGIES.get(coding_lang, "")

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
APEX CODER — SUPREME CODING TIER ★
You are the ultimate coding agent with FULL capabilities.

DETECTED: Language={coding_lang} | Project Type={coding_sub}

{APEX_CODING_WORKFLOW}

{lang_strategy}

{IDE_SHORTCUTS}

CODING TOOLS (use heavily):
- run_tests: Execute test suites, get pass/fail counts
- code_lint: Run linters (eslint, pylint, etc.)
- code_format: Auto-format (prettier, black, etc.)
- git_operation: commit, branch, diff, status
- dependency_install: pip install, npm install, etc.
- code_search: Regex search across codebase
- debug_inspect: Read variables, stack traces
- project_scaffold: Generate project structure

{APEX_COMPLETION_RULES}

ANTI-FAILURE RULES:
- NEVER create empty files. Write REAL, WORKING code.
- NEVER say TASK_COMPLETE without running the code first.
- If run_command shows errors, FIX THEM — don't give up.
- ALWAYS read command output carefully for errors.
- For multi-file projects, create ALL required files.
- Test after implementing. Lint before committing.
- Use 'type filename' to verify file contents after creating them.
{memory_context}
{plan_text}""")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_apex_initial_message(prompt, coding_lang, coding_sub)},
        ]

        # Tracking
        action_failure_streak = 0
        step_successes = 0
        tools_used = set()
        commands_run = 0
        tests_passed = 0
        tests_failed = 0
        replan_count = 0
        consecutive_empty = 0
        has_written_code = False
        has_run_code = False
        has_tested = False
        files_modified = []
        last_error = ""

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            if step == 0:
                await ctx.log(f"  Analyzing screen & calling LLM (step {step+1}/{max_steps})...")
            elif step % 5 == 0:
                await ctx.log(f"  Step {step+1}/{max_steps} — files: {len(files_modified)}, tested: {has_tested}")

            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan: {ready[0].description}]"

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            # Store significant code decisions in memory
            if memory and any(k in response for k in ["ARCHITECTURE:", "DECISION:", "BUG_FOUND:", "FIXED:", "IMPORTANT:", "ERROR:"]):
                memory.remember(
                    content=response[:500],
                    memory_type="episodic",
                    importance=0.7,
                    tags=["code_decision", f"step_{step}"],
                )

            if len(messages) > self._tier_config.max_message_history:
                messages = [messages[0]] + messages[-(self._tier_config.max_message_history - 1):]

            # Completion verification
            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_apex_completion(
                    has_written_code, has_run_code, has_tested, 
                    tests_failed, last_error
                )
                if allowed:
                    await ctx.log(f"★ Coding complete: {step_successes} actions, {commands_run} cmds, {tests_passed} tests passed")
                    break
                else:
                    messages.append({"role": "user", "content": f"❌ Cannot complete: {reason}\nYou have {max_steps - step - 1} steps left. Keep working."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    msg = self._get_apex_unstuck(has_written_code, has_run_code, coding_lang, coding_sub)
                    messages.append({"role": "user", "content": msg})
                    consecutive_empty = 0
                else:
                    messages.append({"role": "user", "content": f"Examine screen.{step_context} Provide ACTION or TOOL."})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    tools_used.add(tool_name)
                    await ctx.log(f"  ★ Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])

                    # Rich tool result reporting
                    msg = self._format_apex_tool_result(tool_name, result, action.get("params", {}))
                    
                    # Track test results
                    if tool_name == "run_tests" and result.get("success"):
                        has_tested = True
                        tests_passed += result.get("passed", 0)
                        tests_failed = result.get("failed", 0)
                        if tests_failed > 0:
                            last_error = f"{tests_failed} tests failed"
                    
                    messages.append({"role": "user", "content": msg + f"\nContinue...{step_context}"})
                    continue

                atype, params = action["type"], action["params"]

                # SoM resolution
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]
                
                # Track action
                self._track_action(atype, params)

                if atype == "run_command":
                    commands_run += 1
                    cmd = params.get("command", "")
                    await ctx.log(f"  Step {step+1}: $ {cmd[:80]}", "INFO")
                else:
                    await ctx.log(f"  Step {step+1}: {atype}{step_context}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ Blocked: {result['error']}. Try another approach."})
                        break
                    if result.get("success", True):
                        success = True
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(0.5)
                        await ctx.send_screenshot()

                await asyncio.sleep(0.3)
                await ctx.send_screenshot()

                if success:
                    step_successes += 1
                    action_failure_streak = 0
                    
                    # Smart feedback based on action + coding context
                    feedback = self._get_apex_feedback(
                        atype, params, result, 
                        has_written_code, has_run_code, coding_lang, step_context
                    )
                    
                    # Update tracking
                    if atype == "type_text" and len(params.get("text", "")) > 10:
                        has_written_code = True
                    if atype == "run_command":
                        has_run_code = True
                        cmd = params.get("command", "")
                        output = str(result.get("result", result.get("output", "")))[:800]
                        
                        # Track files
                        if ">" in cmd:
                            parts = cmd.split(">")
                            if len(parts) > 1:
                                fname = parts[-1].strip().strip('"').strip("'").strip()
                                if fname and not fname.startswith("-"):
                                    files_modified.append(fname)
                        
                        # Detect errors in output
                        errors = self._analyze_output(output)
                        if errors:
                            last_error = errors[0]
                            feedback += f"\n⚠ ERRORS DETECTED:\n" + "\n".join(f"  - {e}" for e in errors[:3])
                            feedback += f"\n\nFull output:\n{output[:600]}\n\nFIX these errors."
                        elif output.strip():
                            feedback += f"\nOutput:\n{output[:500]}"
                        else:
                            feedback += "\n(No output)"

                    if atype == "hotkey":
                        keys = params.get("keys", [])
                        if keys == ["ctrl", "s"]:
                            feedback += "\nFile saved."
                    
                    messages.append({"role": "user", "content": feedback})
                else:
                    action_failure_streak += 1
                    if action_failure_streak >= 4 and plan and planner and replan_count < self._tier_config.max_replans:
                        replan_count += 1
                        plan = await planner.create_plan(
                            ctx.llm, prompt,
                            context=f"Code approach failed ({action_failure_streak} failures). Try different method. Replan #{replan_count}."
                        )
                        action_failure_streak = 0
                        messages.append({"role": "user", "content": f"🔄 REPLANNED (#{replan_count}). New coding strategy ready."})
                    else:
                        msg = self._get_apex_unstuck(has_written_code, has_run_code, coding_lang, coding_sub)
                        messages.append({"role": "user", "content": msg})

            # Mark plan step complete
            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        # Final memory save
        if memory:
            memory.remember(
                content=f"Coding task '{prompt[:100]}' done. Lang={coding_lang}. {step_successes} actions, {commands_run} cmds, {tests_passed} tests OK. Files: {files_modified[:10]}. Tools: {list(tools_used)}",
                memory_type="episodic",
                importance=0.6,
                tags=["session_summary"],
            )

        await ctx.send_screenshot()
        await ctx.log(f"★ {self.name} — {step_successes} actions, {commands_run} cmds, {tests_passed} tests, {len(tools_used)} tools")

    # ── LANGUAGE DETECTION ──

    def _detect_language(self, prompt: str) -> str:
        """Auto-detect programming language from prompt."""
        p = prompt.lower()
        
        lang_signals = {
            "python": ["python", "파이썬", ".py", "django", "flask", "fastapi", "pandas", "numpy", "pip", "pytorch", "tensorflow"],
            "javascript": ["javascript", "자바스크립트", ".js", "node", "react", "vue", "express", "npm", "webpack"],
            "typescript": ["typescript", "타입스크립트", ".ts", "angular", "nest", "deno", "tsx"],
            "html_css": ["html", "css", "웹페이지", "web page", "website", "homepage", "홈페이지"],
            "java": ["java ", "자바", ".java", "spring", "maven", "gradle", "jvm"],
            "cpp": ["c++", "cpp", ".cpp", ".c ", "gcc", "g++", "cmake", "pointer"],
            "csharp": ["c#", "csharp", ".cs", "dotnet", ".net", "unity"],
            "rust": ["rust", "러스트", "cargo", ".rs"],
            "go": ["golang", " go ", ".go", "goroutine"],
            "sql": ["sql", "database", "query", "select", "insert", "데이터베이스"],
            "shell": ["bash", "shell", "sh ", "script", "batch", ".bat", ".ps1", "powershell"],
        }
        
        for lang, signals in lang_signals.items():
            if any(s in p for s in signals):
                return lang
        return "python"  # Default to Python

    def _detect_coding_project_type(self, prompt: str) -> str:
        """Detect the type of coding project."""
        p = prompt.lower()
        
        types = {
            "web_app": ["web app", "웹앱", "website", "web application", "full stack", "풀스택"],
            "api_server": ["api", "rest", "server", "서버", "endpoint", "backend"],
            "cli_tool": ["cli", "command line", "terminal", "명령줄", "tool", "utility"],
            "data_science": ["data", "데이터", "analysis", "분석", "csv", "visualization", "시각화", "machine learning"],
            "automation": ["automate", "자동화", "bot", "scrape", "크롤링", "crawl"],
            "game": ["game", "게임", "pygame", "unity"],
            "library": ["library", "라이브러리", "package", "패키지", "module", "모듈", "sdk"],
            "mobile": ["mobile", "모바일", "android", "ios", "react native", "flutter"],
            "desktop": ["desktop", "데스크톱", "gui", "tkinter", "electron", "qt"],
            "algorithm": ["algorithm", "알고리즘", "leetcode", "coding challenge", "sort", "search"],
            "testing": ["test", "테스트", "unit test", "integration test"],
            "devops": ["docker", "kubernetes", "ci/cd", "deploy", "배포", "dockerfile"],
        }
        
        for ptype, keywords in types.items():
            if any(kw in p for kw in keywords):
                return ptype
        return "general"

    def _build_apex_initial_message(self, prompt: str, lang: str, project_type: str) -> str:
        """Build smart initial message for apex coding tasks."""
        first_action = {
            "python": 'ACTION open_app {"name": "cmd"}',
            "javascript": 'ACTION open_app {"name": "cmd"}',
            "typescript": 'ACTION open_app {"name": "cmd"}',
            "html_css": 'ACTION open_app {"name": "notepad"}',
            "cpp": 'ACTION open_app {"name": "cmd"}',
            "java": 'ACTION open_app {"name": "cmd"}',
            "csharp": 'ACTION open_app {"name": "cmd"}',
        }
        
        action = first_action.get(lang, 'ACTION open_app {"name": "cmd"}')
        
        return f"""Coding task: {prompt}

Language: {lang} | Project type: {project_type}

YOUR FIRST ACTION should be to open a terminal:
{action}

Then:
1. Navigate to a working directory (Desktop or a project folder)
2. Create your file(s) with REAL CODE content
3. Run and test the code
4. Fix any errors
5. ONLY then say TASK_COMPLETE

Do NOT create empty files. Write actual, working code."""

    def _format_apex_tool_result(self, tool_name: str, result: dict, params: dict) -> str:
        """Format tool result with rich coding context."""
        if tool_name == "run_tests" and result.get("success"):
            passed = result.get("passed", 0)
            failed = result.get("failed", 0)
            total = result.get("total", 0)
            status = "✅ ALL PASSED" if failed == 0 else f"❌ {failed} FAILED"
            return f"Tests: {status} — {passed}/{total} passed, {failed} failed"
        elif tool_name == "code_lint" and result.get("success"):
            errors = result.get("error_count", 0)
            warnings = result.get("warning_count", 0)
            status = "✅ Clean" if errors == 0 else f"❌ {errors} errors"
            return f"Lint: {status} — {errors} errors, {warnings} warnings"
        elif tool_name == "git_operation" and result.get("success"):
            op = params.get("operation", "?")
            return f"Git [{op}]: {result.get('message', 'done')}"
        elif tool_name == "code_search" and result.get("success"):
            return f"Search: {result.get('match_count', 0)} matches in {result.get('file_count', 0)} files"
        elif tool_name == "dependency_install" and result.get("success"):
            return f"Installed: {params.get('packages', '?')}. Ready to use."
        elif tool_name == "project_scaffold" and result.get("success"):
            return f"Project scaffold created: {result.get('structure', 'done')}. Now implement the code."
        elif tool_name == "debug_inspect" and result.get("success"):
            return f"Debug: {json.dumps(result.get('data', {}))[:400]}"
        else:
            return f"Tool [{tool_name}]: {json.dumps(result)[:600]}"

    def _get_apex_feedback(self, atype: str, params: dict, result: dict, 
                          has_written: bool, has_run: bool, lang: str, step_context: str) -> str:
        """Context-aware feedback for coding actions."""
        if atype == "open_app":
            app = params.get("name", "")
            if app in ("cmd", "powershell", "terminal"):
                return f"Terminal opened. Navigate to work directory and start coding.{step_context}"
            elif app == "code":
                return f"VS Code opened. Create/open a project, then start implementing.{step_context}"
            elif app in ("notepad", "notepad++"):
                return f"Editor opened. Write your {lang} code, then save (Ctrl+S).{step_context}"
            return f"'{app}' opened.{step_context}"
        
        if atype == "type_text":
            text = params.get("text", "")
            if text.startswith("http") or "://" in text:
                return (
                    "\u26a0 VERIFY: Look at the address bar in the screenshot.\n"
                    "\u2022 Is the URL visible? If YES \u2192 press Enter.\n"
                    f"\u2022 If NOT visible \u2192 typing failed. Press Ctrl+L and retry.{step_context}"
                )
            if len(text) > 50:
                return (
                    f"\u26a0 VERIFY: Look at the screenshot. Is the code visible in the editor ({len(text)} chars)?\n"
                    f"\u2022 If YES \u2192 save with Ctrl+S, then run to test.\n"
                    f"\u2022 If NO \u2192 click inside the editor first, then retry.{step_context}"
                )
            return f"\u26a0 VERIFY: Look at the screenshot. Did the text appear? If not, click the target and retry.{step_context}"
        
        if atype == "run_command":
            return f"Command executed.{step_context}"  # Output handled separately
        
        if atype == "hotkey":
            keys = params.get("keys", [])
            if keys == ["ctrl", "s"]:
                if has_written:
                    return f"File saved. Run it to test.{step_context}"
                return f"Saved.{step_context}"
            if keys == ["ctrl", "`"]:
                return f"Terminal toggled in VS Code.{step_context}"
        
        return f"'{atype}' done.{step_context}"

    def _analyze_output(self, output: str) -> list:
        """Analyze command output for errors."""
        detected = []
        for pattern, explanation in CODING_ERROR_PATTERNS.items():
            if pattern.lower() in output.lower():
                detected.append(f"{pattern}: {explanation}")
        
        lower = output.lower()
        if "traceback" in lower and "error" in lower:
            lines = output.strip().split("\n")
            if lines:
                last = lines[-1].strip()
                if last and "error" in last.lower():
                    detected.append(f"Python: {last[:200]}")
        
        if "is not recognized" in lower:
            detected.append("Command not recognized. Check PATH or use full path.")
        
        return detected

    def _verify_apex_completion(self, has_written: bool, has_run: bool, 
                                has_tested: bool, tests_failed: int, last_error: str) -> tuple:
        """Verify apex coding completion."""
        if not has_written and not has_run:
            return False, "You haven't written or run any code yet. Actually implement the solution."
        if not has_written:
            return False, "No code written to files. Create file(s) with actual code."
        if not has_run:
            return False, "Code not tested. Run it at least once."
        if tests_failed > 0:
            return False, f"{tests_failed} tests still failing. Fix them first."
        if last_error:
            return False, f"Last error unfixed: {last_error[:100]}. Fix it first."
        return True, "OK"

    def _get_apex_unstuck(self, has_written: bool, has_run: bool, lang: str, project_type: str) -> str:
        """Help apex coder get unstuck."""
        if not has_written and not has_run:
            return f"""You're stuck at the start. Do this NOW:
ACTION open_app {{"name": "cmd"}}
Then:
ACTION run_command {{"command": "cd %USERPROFILE%\\Desktop"}}
Then create your {lang} file with actual code."""
        
        if has_written and not has_run:
            run_cmds = {
                "python": 'ACTION run_command {"command": "python your_file.py"}',
                "javascript": 'ACTION run_command {"command": "node your_file.js"}',
                "typescript": 'ACTION run_command {"command": "npx ts-node your_file.ts"}',
                "cpp": 'ACTION run_command {"command": "g++ your_file.cpp -o out && .\\out"}',
                "java": 'ACTION run_command {"command": "javac Main.java && java Main"}',
                "csharp": 'ACTION run_command {"command": "dotnet run"}',
            }
            cmd = run_cmds.get(lang, 'ACTION run_command {"command": "python your_file.py"}')
            return f"Code written but not tested. Run it NOW:\n{cmd}"
        
        return f"""Re-examine the screen. Current state:
- Code written: {has_written}
- Code run: {has_run}
Next step: {'Fix errors and re-run' if has_run else 'Run the code to test it'}
If stuck: ACTION run_command {{"command": "dir"}}  to see files"""
