"""
Coding Agent v2 — Tier C (Affordable, $9.99)
Slug: code_assistant

Domain: coding
Engines: Vision only (NO SoM, NO planner, NO memory)
Tools: run_tests, code_lint (2 basic coding tools)
Actions: Coding domain actions (includes run_command, NO drag)

v2 — CODING WORKFLOW INTELLIGENCE:
- Knows how to open terminals, editors, run code
- Understands coding workflow: write → save → run → test → fix → repeat
- Terminal output analysis and error pattern detection
- Smart file creation (never empty files)
- Completion verification: must have actually written/run code
"""

import asyncio
import json
import re
from plugins.base_plugin import BasePlugin

try:
    from core.engine import AgentContext
except ImportError:
    AgentContext = None


# ── CODING WORKFLOW INTELLIGENCE ──

CODING_WORKFLOW_GUIDE = """
CODING WORKFLOW — HOW TO ACTUALLY CODE ON WINDOWS:

STEP 1: OPEN YOUR TOOLS
- Terminal: ACTION open_app {"name": "cmd"} or ACTION open_app {"name": "powershell"}
- VS Code: ACTION open_app {"name": "code"}
- Notepad (simple): ACTION open_app {"name": "notepad"}

STEP 2: NAVIGATE TO WORKING DIRECTORY
- ACTION run_command {"command": "cd C:\\\\Users\\\\%USERNAME%\\\\Desktop"}
- ACTION run_command {"command": "mkdir my_project && cd my_project"}

STEP 3: CREATE FILES (choose method based on complexity)
Method A — Terminal (for small files):
  ACTION run_command {"command": "echo print('hello') > script.py"}
  ACTION run_command {"command": "type nul > main.py"}  (creates empty, then edit)

Method B — Notepad (for longer files):
  ACTION open_app {"name": "notepad"}
  ACTION type_text {"text": "def main():\\n    print('Hello World')\\n\\nif __name__ == '__main__':\\n    main()"}
  ACTION hotkey {"keys": ["ctrl", "s"]}
  (Save As dialog opens → type filename → press Enter)

Method C — VS Code (for projects):
  ACTION open_app {"name": "code"}
  ACTION hotkey {"keys": ["ctrl", "n"]}  (new file)
  ACTION type_text {"text": "<your code>"}
  ACTION hotkey {"keys": ["ctrl", "s"]}  (save)

STEP 4: RUN CODE
- Python: ACTION run_command {"command": "python script.py"}
- Node.js: ACTION run_command {"command": "node script.js"}
- C/C++: ACTION run_command {"command": "gcc main.c -o main && main.exe"}
- Java: ACTION run_command {"command": "javac Main.java && java Main"}
- Any: ACTION run_command {"command": "your-command-here"}

STEP 5: READ OUTPUT AND FIX ERRORS
- If error occurs, READ the error message carefully
- Identify the line number and error type
- Fix the code and re-run
- DO NOT say TASK_COMPLETE until code runs without errors

STEP 6: TEST
- Run your tests: ACTION run_command {"command": "python -m pytest"}
- Or manual test: ACTION run_command {"command": "python script.py test_input"}

TERMINAL TIPS:
- See files: ACTION run_command {"command": "dir"}
- Read file: ACTION run_command {"command": "type filename.py"}
- Check Python: ACTION run_command {"command": "python --version"}
- Install packages: ACTION run_command {"command": "pip install package_name"}
- Chain commands: ACTION run_command {"command": "cd project && python main.py"}
"""

ERROR_PATTERNS = {
    "SyntaxError": "You have a syntax error. Check for missing colons, brackets, or indentation.",
    "IndentationError": "Indentation is wrong. Python requires consistent spaces (4 spaces recommended).",
    "NameError": "You used a variable/function that doesn't exist. Check spelling or add missing import.",
    "ImportError": "Missing module. Run: pip install <module_name>",
    "ModuleNotFoundError": "Module not installed. Run: pip install <module_name>",
    "TypeError": "Wrong argument type. Check function parameters and data types.",
    "FileNotFoundError": "File doesn't exist. Check the path and filename.",
    "PermissionError": "No permission. Try running as administrator or change file permissions.",
    "IndexError": "List/array index out of range. Check your loop bounds.",
    "KeyError": "Dictionary key not found. Check if the key exists before accessing.",
    "ValueError": "Invalid value. Check input data format.",
    "ZeroDivisionError": "Division by zero. Add a check before dividing.",
    "AttributeError": "Object doesn't have that attribute. Check the object type and available methods.",
    "ConnectionError": "Network error. Check internet connection.",
    "TimeoutError": "Operation timed out. Check if service is running.",
    "npm ERR!": "Node.js package error. Try: npm install, or check package.json.",
    "ENOENT": "File/directory not found. Verify the path exists.",
    "Cannot find module": "Node module missing. Run: npm install",
    "error CS": "C# compilation error. Check syntax.",
    "error LNK": "C/C++ linker error. Check library paths.",
    "Exception in thread": "Java runtime error. Check stack trace for line numbers.",
}

CODING_COMPLETION_RULES = """
CODING TASK COMPLETION RULES:
1. You MUST have actually written code to a file (not just opened an editor)
2. You MUST have run the code at least once
3. If there were errors, you MUST have fixed them
4. You MUST confirm the code produces correct output
5. Do NOT say TASK_COMPLETE if:
   - You only opened a terminal/editor
   - The code has unfixed errors
   - You haven't tested the output
   - You created an empty file
"""


class CodingAgent(BasePlugin):
    name = "Code Assistant"
    description = "Affordable coding agent with visual verification, coding workflow intelligence, and error analysis."
    version = "4.2.0"
    slug = "code_assistant"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        # Reset tracking from base_plugin
        self.reset_tracking()
        
        # Detect task type
        task_type = self._detect_task_type(prompt)

        await ctx.log(f"◇ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Task type: {task_type} | Steps: {max_steps} | Retries: {max_retries} | Tools: {len(self.tools)}")

        # Detect specific coding sub-task
        coding_sub = self._detect_coding_subtask(prompt)
        await ctx.log(f"  Coding sub-task: {coding_sub}")

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
CODE ASSISTANT — TIER C CODING AGENT
You write and run code on the user's Windows computer.

DETECTED CODING TASK: {coding_sub}

{CODING_WORKFLOW_GUIDE}

{CODING_COMPLETION_RULES}

{self._get_coding_strategy(coding_sub, prompt)}

ANTI-FAILURE RULES:
- NEVER create empty files. Always write actual code content.
- NEVER say TASK_COMPLETE without running the code first.
- If run_command shows an error, FIX IT — don't give up.
- ALWAYS read command output carefully for errors.
- If you need to install something, use run_command with pip/npm/etc.
- You CAN use run_command to create files: echo code > file.py
""")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_initial_user_message(prompt, task_type)},
        ]

        # ═══ Minimize Ogenti so LLM sees the desktop ═══
        await self._minimize_ogenti_window(ctx)

        # Tracking state
        action_failure_streak = 0
        consecutive_empty = 0
        has_written_code = False
        has_run_code = False
        last_run_output = ""
        files_created = []
        commands_run = []
        errors_seen = []

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            if step == 0:
                await ctx.log(f"  Analyzing screen & calling LLM (step {step+1}/{max_steps})...")
            elif step % 5 == 0:
                await ctx.log(f"  Step {step+1}/{max_steps} — files: {len(files_created)}, cmds: {len(commands_run)}")

            response = await ctx.ask_llm(messages, screenshot=self._tier_config.vision_enabled)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                messages = [messages[0]] + messages[-(self._tier_config.max_message_history - 1):]

            # Completion check WITH verification
            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_coding_completion(has_written_code, has_run_code, errors_seen)
                if allowed:
                    await ctx.log(f"✓ Task completed. Files: {files_created}, Commands: {len(commands_run)}")
                    break
                else:
                    messages.append({"role": "user", "content": f"❌ Cannot complete: {reason}\nYou have {max_steps - step - 1} steps left. Keep working."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    msg = self._get_coding_unstuck(has_written_code, has_run_code, coding_sub)
                    messages.append({"role": "user", "content": msg})
                    consecutive_empty = 0
                else:
                    messages.append({"role": "user", "content": "Look at the screen. What coding step should you do next? Provide an ACTION."})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    result = await self._execute_tool(action["tool_name"], action["params"])
                    messages.append({"role": "user", "content": f"Tool result: {json.dumps(result)[:400]}"})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                await ctx.log(f"  Step {step+1}: {atype}", "INFO")
                
                # Track action
                self._track_action(atype, params)

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ {result['error']}. Try another way."})
                        break
                    if result.get("success", True):
                        success = True
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(1)

                await ctx.send_screenshot()

                if success:
                    action_failure_streak = 0
                    feedback = self._get_coding_feedback(atype, params, result, has_written_code, has_run_code)
                    
                    # Update tracking
                    if atype == "type_text" and len(params.get("text", "")) > 10:
                        has_written_code = True
                    if atype == "run_command":
                        has_run_code = True
                        cmd = params.get("command", "")
                        commands_run.append(cmd)
                        output = str(result.get("result", ""))
                        last_run_output = output[:500]
                        
                        # Check for errors in output
                        detected_errors = self._analyze_command_output(output)
                        if detected_errors:
                            errors_seen.extend(detected_errors)
                            feedback += f"\n⚠ ERRORS DETECTED:\n" + "\n".join(f"  - {e}" for e in detected_errors)
                            feedback += f"\nFull output:\n{output[:600]}\nFIX these errors before completing."
                        elif output.strip():
                            feedback += f"\nOutput:\n{output[:400]}"
                        
                        # Track file creation
                        if ">" in cmd or "echo" in cmd.lower():
                            # Extracting filename from redirect
                            parts = cmd.split(">")
                            if len(parts) > 1:
                                fname = parts[-1].strip().strip('"').strip("'")
                                if fname:
                                    files_created.append(fname)
                    
                    if atype == "hotkey":
                        keys = params.get("keys", [])
                        if keys == ["ctrl", "s"]:
                            feedback += "\nFile saved. Now run it to test."
                    
                    messages.append({"role": "user", "content": feedback})
                else:
                    action_failure_streak += 1
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

        await ctx.send_screenshot()
        await ctx.log(f"◇ {self.name} finished — Written:{has_written_code} Run:{has_run_code} Files:{files_created}")

    def _detect_coding_subtask(self, prompt: str) -> str:
        """Detect specific type of coding task."""
        p = prompt.lower()
        
        patterns = {
            "web_development": ["html", "css", "javascript", "react", "vue", "angular", "website", "web page", "웹", "홈페이지"],
            "python_script": ["python", "파이썬", "스크립트", "script", ".py"],
            "data_processing": ["csv", "json", "xml", "parse", "데이터", "data", "pandas", "numpy"],
            "automation": ["automate", "자동화", "batch", "cron", "scheduler", "자동"],
            "api_development": ["api", "rest", "endpoint", "server", "flask", "fastapi", "서버"],
            "file_operations": ["file", "파일", "read", "write", "copy", "move", "rename"],
            "algorithm": ["algorithm", "알고리즘", "sort", "search", "tree", "graph", "dynamic programming"],
            "database": ["sql", "database", "db", "sqlite", "mysql", "postgres", "데이터베이스"],
            "testing": ["test", "테스트", "unittest", "pytest", "jest"],
            "debugging": ["fix", "bug", "error", "debug", "수정", "오류", "고치"],
        }
        
        for subtype, keywords in patterns.items():
            if any(kw in p for kw in keywords):
                return subtype
        return "general_coding"

    def _get_coding_strategy(self, subtask: str, prompt: str) -> str:
        """Get concrete step-by-step coding strategy."""
        strategies = {
            "web_development": """
WEB DEVELOPMENT STRATEGY:
1. Open terminal: ACTION open_app {"name": "cmd"}
2. Create project folder: ACTION run_command {"command": "mkdir web_project && cd web_project"}
3. Create HTML file with actual content:
   ACTION run_command {"command": "echo ^<!DOCTYPE html^>^<html^>^<head^>^<title^>Page^</title^>^</head^>^<body^>^<h1^>Hello^</h1^>^</body^>^</html^> > index.html"}
4. Create CSS if needed (same echo > pattern or use notepad)
5. Create JS if needed
6. Open in browser: ACTION run_command {"command": "start index.html"}
7. Verify it looks correct in the screenshot
""",
            "python_script": """
PYTHON SCRIPT STRATEGY:
1. Open terminal: ACTION open_app {"name": "cmd"}
2. Navigate: ACTION run_command {"command": "cd %USERPROFILE%\\Desktop"}
3. Write script via terminal:
   ACTION run_command {"command": "echo import sys > script.py"}
   ACTION run_command {"command": "echo print('Hello World') >> script.py"}
   OR open notepad and type the full script, then save
4. Run it: ACTION run_command {"command": "python script.py"}
5. Check output for errors. Fix if needed.
6. Re-run until it works correctly.
""",
            "data_processing": """
DATA PROCESSING STRATEGY:
1. Open terminal
2. Check if required packages exist: ACTION run_command {"command": "pip list | findstr pandas"}
3. Install if missing: ACTION run_command {"command": "pip install pandas"}
4. Write processing script (use notepad for longer scripts)
5. Run the script
6. Verify output file was created: ACTION run_command {"command": "dir output*"}
""",
            "api_development": """
API DEVELOPMENT STRATEGY:
1. Open terminal
2. Install framework: ACTION run_command {"command": "pip install flask"}
3. Create server file with actual endpoint code
4. Run server: ACTION run_command {"command": "start python server.py"}
5. Test endpoint: ACTION run_command {"command": "curl http://localhost:5000/api/test"}
6. Verify response is correct
""",
            "debugging": """
DEBUGGING STRATEGY:
1. First READ the code: ACTION run_command {"command": "type filename.py"}
2. Run it to see the error: ACTION run_command {"command": "python filename.py"}
3. Read the error message CAREFULLY — note the line number
4. Open the file and fix the specific line
5. Run again to verify the fix
6. Repeat until no errors
""",
            "algorithm": """
ALGORITHM STRATEGY:
1. Plan the algorithm on paper (think step by step)
2. Create file with implementation
3. Add test cases at the bottom
4. Run and verify all test cases pass
5. Consider edge cases (empty input, single element, large input)
""",
            "file_operations": """
FILE OPERATIONS STRATEGY:
1. Check current directory: ACTION run_command {"command": "cd && dir"}
2. Write the file handling script
3. Create test input files if needed
4. Run the script
5. Verify output: ACTION run_command {"command": "dir"} and ACTION run_command {"command": "type output_file"}
""",
        }
        
        strategy = strategies.get(subtask, """
GENERAL CODING STRATEGY:
1. Open terminal: ACTION open_app {"name": "cmd"}
2. Navigate to work directory
3. Create your code file (use echo > or notepad)
4. Write REAL code — not empty files
5. Run and test
6. Fix any errors
7. Verify output is correct
""")
        return strategy

    def _get_coding_feedback(self, atype: str, params: dict, result: dict, 
                             has_written: bool, has_run: bool) -> str:
        """Context-aware feedback after each coding action."""
        if atype == "open_app":
            app = params.get("name", "")
            if app in ("cmd", "powershell", "terminal"):
                return "Terminal opened. Now navigate to your work directory and start coding."
            elif app in ("notepad", "code", "notepad++"):
                return f"Editor '{app}' opened. Type your code, then Ctrl+S to save."
            return f"'{app}' opened. Continue with your coding task."
        
        if atype == "type_text":
            text = params.get("text", "")
            if text.startswith("http") or "://" in text:
                return (
                    "\u26a0 VERIFY: Look at the address bar in the screenshot.\n"
                    "\u2022 Is the URL visible? If YES \u2192 press Enter.\n"
                    "\u2022 If NOT visible \u2192 typing failed. Press Ctrl+L and retry."
                )
            if len(text) > 20:
                return (
                    "\u26a0 VERIFY: Look at the screenshot. Is the code visible in the editor?\n"
                    "\u2022 If YES \u2192 save with Ctrl+S and run it.\n"
                    "\u2022 If NO \u2192 click inside the editor first, then retry type_text."
                )
            return "\u26a0 VERIFY: Look at the screenshot. Did the text appear? If not, click the target field and retry."
        
        if atype == "run_command":
            return ""  # Handled separately with output analysis
        
        if atype == "hotkey":
            keys = params.get("keys", [])
            if keys == ["ctrl", "s"]:
                if has_written:
                    return "File saved. Now run it to test."
                return "Saved. If needed, type your code first."
            if keys == ["ctrl", "n"]:
                return "New file created. Type your code, then Ctrl+S to save with a filename."
            return f"Hotkey {'+'.join(keys)} pressed. Continue."
        
        if atype == "click":
            return "\u26a0 VERIFY: Look at the screenshot. Did the click change anything? Describe what you see."

        return f"\u26a0 VERIFY: '{atype}' executed. Look at the screenshot and describe what changed."

    def _analyze_command_output(self, output: str) -> list:
        """Analyze terminal output for error patterns."""
        detected = []
        for pattern, explanation in ERROR_PATTERNS.items():
            if pattern.lower() in output.lower():
                detected.append(f"{pattern}: {explanation}")
        
        # Check for common error indicators
        lower = output.lower()
        if "traceback" in lower and "error" in lower:
            # Extract the last line which usually has the error message
            lines = output.strip().split("\n")
            if lines:
                last_line = lines[-1].strip()
                if last_line and "error" in last_line.lower():
                    detected.append(f"Python error: {last_line[:200]}")
        
        if "is not recognized" in lower:
            detected.append("Command not found. Check if the program is installed and in PATH.")
        
        if "'python' is not recognized" in lower or "'python3' is not recognized" in lower:
            detected.append("Python not in PATH. Try: py instead of python, or install Python from python.org")
        
        return detected

    def _verify_coding_completion(self, has_written: bool, has_run: bool, errors: list) -> tuple:
        """Verify coding task completion requirements."""
        if not has_written and not has_run:
            return False, "You haven't written any code or run any commands yet. Actually write and test code first."
        if not has_written:
            return False, "You haven't written any code yet. Create a file with actual code content."
        if not has_run:
            return False, "You haven't run/tested the code yet. Run it at least once to verify it works."
        if errors:
            last_errors = errors[-3:]  # Check last few errors
            return False, f"Recent errors found: {'; '.join(last_errors[:2])}. Fix errors before completing."
        return True, "OK"

    def _get_coding_unstuck(self, has_written: bool, has_run: bool, subtask: str) -> str:
        """Help agent get unstuck in coding workflow."""
        if not has_written and not has_run:
            return """You're stuck at the start. Do this NOW:
ACTION open_app {"name": "cmd"}
This opens a terminal. Then you can write and run code."""
        
        if has_written and not has_run:
            return """You've written code but haven't run it. Do this NOW:
ACTION run_command {"command": "python your_script.py"}
Replace 'your_script.py' with your actual filename."""
        
        if has_run and not has_written:
            return """You've run commands but haven't created a proper code file. 
Open notepad and write actual code, then save it."""
        
        return """Re-examine the screen. What's the current state?
If terminal is open: run a command
If editor is open: write/fix code  
If nothing is open: ACTION open_app {"name": "cmd"}"""
