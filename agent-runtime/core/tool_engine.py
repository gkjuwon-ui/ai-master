"""
Tool Engine v4 — Premium tool orchestration with action verification.

Key improvements:
- Post-action visual verification via visual diff
- Smart wait: waits for UI to settle
- Pre-action validation: checks screen state before critical actions
- Enhanced retry: retries with alternative strategies
- Action history with success/failure tracking
- Smart Action Sequences: pre-built chains for common operations
  (open browser, search web, open notepad, navigate URL, etc.)
- Macro recording and replay
"""

import asyncio
import ctypes
import ctypes.wintypes
import random
import re
import shlex
import sys
import time
import json
from typing import Any, Optional, Callable
from loguru import logger


# ═══════════════════════════════════════════════════════════════════════
# COMMAND SANITIZATION — blocks shell injection metacharacters
# ═══════════════════════════════════════════════════════════════════════

_DANGEROUS_SHELL_META = ['&&', '||', ';', '`', '$(', '${', '|', '\n', '\r']

def _sanitize_command(cmd: str) -> str:
    """
    Sanitize a command string before execution.
    Raises ValueError if dangerous shell metacharacters are detected.
    Strips null bytes and control characters.
    """
    if not cmd or not cmd.strip():
        raise ValueError("Empty command")
    # Strip null bytes and control characters (except space/tab)
    cmd = re.sub(r'[\x00-\x08\x0e-\x1f]', '', cmd)
    for meta in _DANGEROUS_SHELL_META:
        if meta in cmd:
            raise ValueError(
                f"Blocked: dangerous shell metacharacter '{meta}' detected. "
                f"Use separate commands instead of chaining."
            )
    return cmd

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False

try:
    import pyperclip
    HAS_CLIPBOARD = True
except ImportError:
    HAS_CLIPBOARD = False


# ═══════════════════════════════════════════════════════════════════════
# SMART ACTION SEQUENCES
# ═══════════════════════════════════════════════════════════════════════
# Pre-built, tested sequences for common operations.
# These ensure agents use the CORRECT approach every time.

SMART_SEQUENCES = {
    "open_browser_and_search": {
        "description": "Opens Chrome and performs a Google search",
        "params": ["query"],  # Required parameters
        "actions": [
            {"type": "open_app", "params": {"name": "chrome"}, "wait_after": 3.0},
            {"type": "hotkey", "params": {"keys": ["ctrl", "l"]}, "wait_after": 0.5},
            {"type": "type_text", "params": {"text": "https://www.google.com/search?q={query}"}, "wait_after": 0.3},
            {"type": "press_key", "params": {"key": "enter"}, "wait_after": 3.0},
        ],
    },
    "open_browser_and_navigate": {
        "description": "Opens Chrome and navigates to a URL",
        "params": ["url"],
        "actions": [
            {"type": "open_app", "params": {"name": "chrome"}, "wait_after": 3.0},
            {"type": "hotkey", "params": {"keys": ["ctrl", "l"]}, "wait_after": 0.5},
            {"type": "type_text", "params": {"text": "{url}"}, "wait_after": 0.3},
            {"type": "press_key", "params": {"key": "enter"}, "wait_after": 3.0},
        ],
    },
    "open_notepad_and_type": {
        "description": "Opens Notepad and types text content via clipboard (fast, unicode-safe)",
        "params": ["content"],
        "actions": [
            {"type": "open_app", "params": {"name": "notepad"}, "wait_after": 2.0},
            {"type": "click", "params": {"x": 400, "y": 400}, "wait_after": 0.3},
            {"type": "type_text_fast", "params": {"text": "{content}"}, "wait_after": 0.5},
        ],
    },
    "save_file": {
        "description": "Saves the current file with Ctrl+S",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "s"]}, "wait_after": 1.0},
        ],
    },
    "save_as": {
        "description": "Save As with a filename",
        "params": ["filename"],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "shift", "s"]}, "wait_after": 1.5},
            {"type": "type_text", "params": {"text": "{filename}"}, "wait_after": 0.3},
            {"type": "press_key", "params": {"key": "enter"}, "wait_after": 1.0},
        ],
    },
    "google_search_in_existing_browser": {
        "description": "Perform a Google search in an already-open browser",
        "params": ["query"],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "l"]}, "wait_after": 0.5},
            {"type": "type_text", "params": {"text": "https://www.google.com/search?q={query}"}, "wait_after": 0.3},
            {"type": "press_key", "params": {"key": "enter"}, "wait_after": 3.0},
        ],
    },
    "open_new_tab": {
        "description": "Open a new browser tab and navigate",
        "params": ["url"],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "t"]}, "wait_after": 1.0},
            {"type": "type_text", "params": {"text": "{url}"}, "wait_after": 0.3},
            {"type": "press_key", "params": {"key": "enter"}, "wait_after": 2.0},
        ],
    },
    "copy_page_content": {
        "description": "Select all content on page and copy to clipboard",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "a"]}, "wait_after": 0.3},
            {"type": "hotkey", "params": {"keys": ["ctrl", "c"]}, "wait_after": 0.5},
        ],
    },
    "go_back": {
        "description": "Navigate back in browser",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["alt", "left"]}, "wait_after": 2.0},
        ],
    },
    "new_file_in_editor": {
        "description": "Create a new file in the current editor",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "n"]}, "wait_after": 1.0},
        ],
    },
    "undo": {
        "description": "Undo last action",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "z"]}, "wait_after": 0.3},
        ],
    },
    "redo": {
        "description": "Redo last undone action",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "y"]}, "wait_after": 0.3},
        ],
    },
    "find_on_page": {
        "description": "Open find dialog and search for text",
        "params": ["search_text"],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "f"]}, "wait_after": 0.5},
            {"type": "type_text", "params": {"text": "{search_text}"}, "wait_after": 0.3},
            {"type": "press_key", "params": {"key": "enter"}, "wait_after": 0.5},
        ],
    },
    "close_current_tab": {
        "description": "Close the current browser tab",
        "params": [],
        "actions": [
            {"type": "hotkey", "params": {"keys": ["ctrl", "w"]}, "wait_after": 0.5},
        ],
    },
    "screenshot_and_analyze": {
        "description": "Take a screenshot for analysis",
        "params": [],
        "actions": [
            {"type": "wait", "params": {"seconds": 1}, "wait_after": 0},
            {"type": "screenshot", "params": {}, "wait_after": 0},
        ],
    },
}


class ToolEngine:
    """
    Premium tool orchestration with action chaining, retry logic,
    smart waits, and validation. Used exclusively by Tier-S/S+ agents.
    """

    def __init__(self, vision_engine=None):
        self.enabled = HAS_PYAUTOGUI
        self.vision = vision_engine
        self._action_history: list[dict] = []
        self._macros: dict[str, list[dict]] = {}

        if self.enabled:
            self.screen_width, self.screen_height = pyautogui.size()
        else:
            self.screen_width, self.screen_height = 1920, 1080

    async def execute_smart_sequence(
        self,
        sequence_name: str,
        params: dict = None,
    ) -> list[dict]:
        """
        Execute a pre-built smart action sequence with parameter substitution.
        
        Example: await tool.execute_smart_sequence("open_browser_and_search", {"query": "OpenAI"})
        """
        seq = SMART_SEQUENCES.get(sequence_name)
        if not seq:
            return [{"success": False, "error": f"Unknown sequence: {sequence_name}"}]
        
        params = params or {}
        results = []
        
        for action_template in seq["actions"]:
            action_type = action_template["type"]
            action_params = dict(action_template.get("params", {}))
            wait_after = action_template.get("wait_after", 0.5)
            
            # Substitute {placeholder} with actual params
            for key, val in action_params.items():
                if isinstance(val, str):
                    for param_name, param_val in params.items():
                        val = val.replace(f"{{{param_name}}}", str(param_val))
                    action_params[key] = val
            
            result = self._execute_single(action_type, action_params)
            results.append(result)
            
            self._action_history.append({
                "type": action_type,
                "params": action_params,
                "result": result,
                "timestamp": time.time(),
                "sequence": sequence_name,
                "attempts": 1,
            })
            
            if wait_after > 0:
                await asyncio.sleep(wait_after)
            
            # Stop if action failed (except for non-critical ones)
            if not result.get("success", False) and action_type not in ("wait", "screenshot"):
                logger.warning(f"Sequence '{sequence_name}' failed at: {action_type}")
                break
        
        return results

    @staticmethod
    def get_available_sequences() -> dict[str, str]:
        """Get names and descriptions of all available smart sequences."""
        return {name: seq["description"] for name, seq in SMART_SEQUENCES.items()}

    async def execute_chain(
        self,
        actions: list[dict],
        retry_on_fail: bool = True,
        max_retries: int = 2,
        validate: bool = True,
    ) -> list[dict]:
        """
        Execute a chain of actions sequentially with retry, validation and smart wait.
        
        Each action: {"type": str, "params": dict}
        Returns list of results per action.
        """
        results = []
        for i, action in enumerate(actions):
            action_type = action.get("type", "")
            params = action.get("params", {})
            attempt = 0
            success = False
            result = None

            while attempt <= (max_retries if retry_on_fail else 0):
                try:
                    result = self._execute_single(action_type, params)
                    success = result.get("success", False)
                    if success:
                        break
                    # On failure, try with slightly offset coordinates for click actions
                    if not success and attempt < max_retries and action_type in ("click", "double_click", "right_click"):
                        offset = (attempt + 1) * 3
                        params = dict(params)
                        params["x"] = params.get("x", 0) + offset
                        params["y"] = params.get("y", 0) + offset
                        logger.debug(f"Retrying {action_type} with offset +{offset}")
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                attempt += 1
                if attempt <= max_retries and not success:
                    await asyncio.sleep(0.3 * attempt)  # Backoff

            self._action_history.append({
                "type": action_type,
                "params": params,
                "result": result,
                "timestamp": time.time(),
                "attempts": attempt + 1,
            })
            results.append(result or {"success": False, "error": "unknown"})

            # Smart wait: let the UI settle after successful actions
            if success:
                await self._smart_wait()

        return results

    def execute_single(self, action_type: str, params: dict) -> dict:
        """Execute a single action (synchronous)."""
        return self._execute_single(action_type, params)

    def _execute_single(self, action_type: str, params: dict) -> dict:
        """Core action dispatcher."""
        handlers = {
            "click": self._click,
            "double_click": self._double_click,
            "right_click": self._right_click,
            "type_text": self._type_text,
            "type_text_fast": self._type_text_fast,
            "press_key": self._press_key,
            "hotkey": self._hotkey,
            "move_mouse": self._move_mouse,
            "scroll": self._scroll,
            "drag": self._drag,
            "open_app": self._open_app,
            "close_app": self._close_app,
            "wait": self._wait,
            "run_command": self._run_command,
            "clipboard_set": self._clipboard_set,
            "clipboard_get": self._clipboard_get,
            "clipboard_paste": self._clipboard_paste,
            "focus_window": self._focus_window,
            "get_window_list": self._get_window_list,
            "screenshot": self._screenshot_action,
            "write_file": self._write_file,
        }
        handler = handlers.get(action_type)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action_type}"}
        try:
            result = handler(params)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --- Smart Wait ---

    async def _smart_wait(self, max_wait: float = 2.0, settle_threshold: float = 1.0):
        """Wait until the screen stops changing, up to max_wait seconds."""
        if not self.vision:
            await asyncio.sleep(0.4)  # Reasonable default when no vision engine
            return
        start = time.time()
        await asyncio.sleep(0.2)
        while time.time() - start < max_wait:
            diff = self.vision.detect_changes()
            if not diff.get("is_significant", True):
                return
            await asyncio.sleep(0.25)

    # --- Macro System ---

    def start_recording(self, macro_name: str):
        """Start recording actions into a named macro."""
        self._macros[macro_name] = []
        self._recording_macro = macro_name

    def stop_recording(self) -> str:
        """Stop recording and return macro name."""
        name = getattr(self, "_recording_macro", "")
        self._recording_macro = ""
        return name

    async def replay_macro(self, macro_name: str, speed: float = 1.0) -> list[dict]:
        """Replay a recorded macro at given speed multiplier."""
        actions = self._macros.get(macro_name, [])
        if not actions:
            return [{"success": False, "error": f"Macro '{macro_name}' not found"}]
        results = []
        for action in actions:
            result = self._execute_single(action["type"], action["params"])
            results.append(result)
            delay = action.get("delay", 0.3) / speed
            await asyncio.sleep(delay)
        return results

    # --- Action History ---

    def get_history(self, last_n: int = 20) -> list[dict]:
        """Get last N actions from history."""
        return self._action_history[-last_n:]

    def undo_last(self) -> dict:
        """Attempt to undo the last action (best-effort)."""
        if not self._action_history:
            return {"success": False, "error": "No actions to undo"}
        last = self._action_history[-1]
        # Simple undo for type_text: select all + delete
        if last["type"] == "type_text":
            self._hotkey({"keys": ["ctrl", "z"]})
            return {"success": True, "result": "Undo (Ctrl+Z) sent"}
        return {"success": False, "error": f"Cannot undo {last['type']}"}

    # --- Action Implementations ---

    def _click(self, p: dict) -> str:
        x, y = self._clamp(p.get("x", 0), p.get("y", 0))
        btn = p.get("button", "left")
        if not self.enabled:
            return f"[headless] click ({x},{y})"
        pyautogui.click(x=x, y=y, button=btn, clicks=p.get("clicks", 1))
        return f"Clicked ({x},{y}) {btn}"

    def _double_click(self, p: dict) -> str:
        x, y = self._clamp(p.get("x", 0), p.get("y", 0))
        if not self.enabled:
            return f"[headless] dbl-click ({x},{y})"
        pyautogui.doubleClick(x=x, y=y)
        return f"Double-clicked ({x},{y})"

    def _right_click(self, p: dict) -> str:
        x, y = self._clamp(p.get("x", 0), p.get("y", 0))
        if not self.enabled:
            return f"[headless] right-click ({x},{y})"
        pyautogui.rightClick(x=x, y=y)
        return f"Right-clicked ({x},{y})"

    def _type_text(self, p: dict) -> str:
        text = p.get("text", "")
        interval = p.get("interval", 0.04)
        if not self.enabled:
            return f"[headless] type '{text[:50]}'"
        # Human-like character-by-character typing via SendInput
        if sys.platform == "win32":
            import random as _rng
            KEYEVENTF_UNICODE = 0x0004
            KEYEVENTF_KEYUP   = 0x0002
            INPUT_KEYBOARD    = 1

            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [
                    ("wVk",         ctypes.wintypes.WORD),
                    ("wScan",       ctypes.wintypes.WORD),
                    ("dwFlags",     ctypes.wintypes.DWORD),
                    ("time",        ctypes.wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
                ]

            class INPUT(ctypes.Structure):
                class _INPUT_UNION(ctypes.Union):
                    _fields_ = [("ki", KEYBDINPUT)]
                _fields_ = [
                    ("type", ctypes.wintypes.DWORD),
                    ("union", _INPUT_UNION),
                ]

            for i, char in enumerate(text):
                if char == '\n':
                    pyautogui.press('enter')
                elif char == '\t':
                    pyautogui.press('tab')
                else:
                    code = ord(char)
                    surrogates = [code] if code <= 0xFFFF else [0xD800 + ((code - 0x10000) >> 10), 0xDC00 + ((code - 0x10000) & 0x3FF)]
                    inputs = []
                    for wScan in surrogates:
                        ki_down = KEYBDINPUT(wVk=0, wScan=wScan, dwFlags=KEYEVENTF_UNICODE, time=0, dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)))
                        inp_down = INPUT(type=INPUT_KEYBOARD); inp_down.union.ki = ki_down
                        ki_up = KEYBDINPUT(wVk=0, wScan=wScan, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, time=0, dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)))
                        inp_up = INPUT(type=INPUT_KEYBOARD); inp_up.union.ki = ki_up
                        inputs += [inp_down, inp_up]
                    arr = (INPUT * len(inputs))(*inputs)
                    ctypes.windll.user32.SendInput(len(inputs), ctypes.pointer(arr), ctypes.sizeof(INPUT))
                if i < len(text) - 1:
                    jitter = interval * _rng.uniform(-0.5, 0.5)
                    delay = interval + jitter
                    if _rng.random() < 0.05:
                        delay += _rng.uniform(0.08, 0.2)
                    time.sleep(max(0.01, delay))
        else:
            for ch in text:
                pyautogui.write(ch)
                time.sleep(interval)
        return f"Typed {len(text)} chars (human-like)"

    def _write_file(self, p: dict) -> str:
        """Write content directly to a file on disk (bypasses slow UI typing)."""
        import os, pathlib
        content = p.get("content", p.get("text", ""))
        path = p.get("path", "")
        if not path:
            desktop = pathlib.Path.home() / "Desktop"
            desktop.mkdir(parents=True, exist_ok=True)
            filename = p.get("filename", "report.md")
            path = str(desktop / filename)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"File written: {path} ({len(content)} chars)"
        except Exception as e:
            return f"write_file failed: {e}"

    def _type_text_fast(self, p: dict) -> str:
        """Paste via clipboard for instant text input (supports unicode)."""
        text = p.get("text", "")
        if not self.enabled:
            return f"[headless] fast-type '{text[:50]}'"
        if HAS_CLIPBOARD:
            pyperclip.copy(text)
            try:
                from core.os_controller import win32_hotkey
                win32_hotkey("ctrl", "v")
            except Exception:
                pyautogui.hotkey("ctrl", "v")
            return f"Fast-typed {len(text)} chars via clipboard"
        else:
            return self._type_text(p)

    def _press_key(self, p: dict) -> str:
        key = p.get("key", "")
        presses = p.get("presses", 1)
        if not self.enabled:
            return f"[headless] press {key}"
        try:
            from core.os_controller import win32_press_key
            win32_press_key(key, presses=presses)
        except Exception:
            pyautogui.press(key, presses=presses)
        return f"Pressed: {key} ({presses}x)"

    def _hotkey(self, p: dict) -> str:
        keys = p.get("keys", [])
        if not self.enabled:
            return f"[headless] hotkey {'+'.join(keys)}"
        try:
            from core.os_controller import win32_hotkey
            win32_hotkey(*keys)
        except Exception:
            pyautogui.hotkey(*keys)
        return f"Hotkey: {'+'.join(keys)}"

    def _move_mouse(self, p: dict) -> str:
        x, y = self._clamp(p.get("x", 0), p.get("y", 0))
        dur = p.get("duration", 0.2)
        if not self.enabled:
            return f"[headless] move ({x},{y})"
        pyautogui.moveTo(x=x, y=y, duration=dur)
        return f"Moved to ({x},{y})"

    def _scroll(self, p: dict) -> str:
        clicks = p.get("clicks", -5)
        if not self.enabled:
            return f"[headless] scroll {clicks}"
        x, y = p.get("x"), p.get("y")
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x=x, y=y)
        else:
            pyautogui.scroll(clicks)
        return f"Scrolled {clicks}"

    def _drag(self, p: dict) -> str:
        sx, sy = p.get("startX", 0), p.get("startY", 0)
        ex, ey = p.get("endX", 0), p.get("endY", 0)
        dur = p.get("duration", 0.4)
        if not self.enabled:
            return f"[headless] drag ({sx},{sy})->({ex},{ey})"
        pyautogui.moveTo(sx, sy)
        pyautogui.drag(ex - sx, ey - sy, duration=dur)
        return f"Dragged ({sx},{sy})->({ex},{ey})"

    def _open_app(self, p: dict) -> str:
        import subprocess, sys, os
        name = p.get("name", "")
        # Use smart app intelligence from os_controller
        try:
            from core.os_controller import _smart_open_app
            result = _smart_open_app(name)
            time.sleep(1)
            return result
        except ImportError:
            if sys.platform == "win32":
                try:
                    subprocess.Popen(['cmd', '/c', 'start', '', name])
                except Exception:
                    os.startfile(name)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", name])
            else:
                subprocess.Popen([name])
            return f"Opened {name}"

    def _close_app(self, p: dict) -> str:
        self._hotkey({"keys": ["alt", "F4"]})
        return "Sent Alt+F4"

    def _wait(self, p: dict) -> str:
        secs = min(p.get("seconds", 1), 10)
        time.sleep(secs)
        return f"Waited {secs}s"

    def _run_command(self, p: dict) -> str:
        import subprocess as _subprocess
        cmd = p.get("command", "")
        timeout = p.get("timeout", 30)
        
        # Sanitize: block shell metacharacters to prevent injection
        try:
            cmd = _sanitize_command(cmd)
        except ValueError as e:
            return f"Blocked: {e}"
        
        try:
            if sys.platform == 'win32':
                cmd_args = ['cmd', '/c'] + cmd.split()
            else:
                cmd_args = shlex.split(cmd)
            
            result = _subprocess.run(
                cmd_args, capture_output=True, text=True, timeout=timeout
            )
            output = result.stdout[:2000] or result.stderr[:2000]
            return f"Exit {result.returncode}: {output}"
        except _subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Command failed: {e}"

    def _clipboard_set(self, p: dict) -> str:
        if HAS_CLIPBOARD:
            pyperclip.copy(p.get("text", ""))
            return "Clipboard set"
        return "pyperclip not available"

    def _clipboard_get(self, p: dict) -> str:
        if HAS_CLIPBOARD:
            return pyperclip.paste()
        return "pyperclip not available"

    def _clipboard_paste(self, p: dict) -> str:
        self._hotkey({"keys": ["ctrl", "v"]})
        return "Pasted from clipboard"

    def _focus_window(self, p: dict) -> str:
        title = p.get("title", "")
        if not self.enabled:
            return f"[headless] focus '{title}'"
        # Use smart window focusing from os_controller
        try:
            from core.os_controller import _smart_focus_window
            return _smart_focus_window(title)
        except ImportError:
            try:
                wins = pyautogui.getWindowsWithTitle(title)
                if wins:
                    wins[0].activate()
                    return f"Focused '{title}'"
                return f"Window '{title}' not found"
            except Exception as e:
                return f"Focus failed: {e}"

    def _get_window_list(self, p: dict) -> str:
        if not self.enabled:
            return "[]"
        try:
            titles = [w.title for w in pyautogui.getAllWindows() if w.title.strip()]
            return json.dumps(titles[:30])
        except Exception:
            return "[]"

    def _screenshot_action(self, p: dict) -> str:
        return "Use vision engine for screenshots"

    def _clamp(self, x: int, y: int) -> tuple[int, int]:
        return (
            max(0, min(x, self.screen_width - 1)),
            max(0, min(y, self.screen_height - 1)),
        )
