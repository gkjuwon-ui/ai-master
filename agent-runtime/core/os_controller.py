"""
OS Controller - Wraps pyautogui and other OS interaction libraries.
Handles mouse, keyboard, app management, and system commands.

v3 — Smart App Intelligence:
- Resolution-independent coordinate normalization (0.0-1.0 relative coords)
- Dynamic DPI/scaling awareness
- Cross-platform compatibility (Windows, macOS, Linux)
- Session isolation for concurrent multi-user support
- Headless mode for server/CI environments
- Smart app name resolution (e.g., "chrome" → actual Chrome executable)
- Fuzzy window title matching
- Unicode text input support via clipboard-paste
- Window state tracking
"""

import os
import re
import shlex
import sys
import time
import random
import subprocess
import threading
import ctypes
import ctypes.wintypes
from typing import Any, Optional
from loguru import logger


# ═══════════════════════════════════════════════════════════════════════
# COMMAND SANITIZATION — blocks shell injection metacharacters
# ═══════════════════════════════════════════════════════════════════════

_DANGEROUS_SHELL_META = ['&&', '||', ';', '`', '$(', '${', '|', '\n', '\r']

def sanitize_command(cmd: str) -> str:
    """
    Sanitize a command string before execution.
    Raises ValueError if dangerous shell metacharacters are detected.
    Strips null bytes and control characters.
    """
    if not cmd or not cmd.strip():
        raise ValueError("Empty command")
    # Strip null bytes and control characters (except space/tab)
    cmd = re.sub(r'[\x00-\x08\x0e-\x1f]', '', cmd)
    # Check for shell metacharacters that enable injection / chaining
    for meta in _DANGEROUS_SHELL_META:
        if meta in cmd:
            raise ValueError(
                f"Blocked: dangerous shell metacharacter '{meta}' detected in command. "
                f"Use separate commands instead of chaining."
            )
    return cmd

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.1
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False
    logger.warning("pyautogui not available — OS control disabled (headless mode)")

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# ═══════════════════════════════════════════════════════════════════════
# BROWSER DETECTION — find which browser is actually installed
# ═══════════════════════════════════════════════════════════════════════

_cached_browser: Optional[str] = None

def detect_installed_browser() -> str:
    """
    Detect which web browser is actually installed on this system.
    Returns 'chrome', 'msedge', or 'firefox'. Caches result after first call.
    On Windows, Edge is pre-installed so it's used as the safe default.
    """
    global _cached_browser
    if _cached_browser is not None:
        return _cached_browser

    # Check Chrome
    chrome_paths = [
        os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    ]
    if any(os.path.exists(p) for p in chrome_paths):
        _cached_browser = "chrome"
        logger.info("Detected installed browser: Chrome")
        return "chrome"

    # Check Edge (pre-installed on Windows 10/11)
    edge_paths = [
        os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
        os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
    ]
    if any(os.path.exists(p) for p in edge_paths):
        _cached_browser = "msedge"
        logger.info("Detected installed browser: Edge")
        return "msedge"

    # Check Firefox
    firefox_paths = [
        os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
        os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
    ]
    if any(os.path.exists(p) for p in firefox_paths):
        _cached_browser = "firefox"
        logger.info("Detected installed browser: Firefox")
        return "firefox"

    # Default fallback — Edge is always on Windows
    _cached_browser = "msedge"
    logger.warning("No browser detected via paths — defaulting to msedge")
    return "msedge"


# ═══════════════════════════════════════════════════════════════════════
# SMART APP INTELLIGENCE
# ═══════════════════════════════════════════════════════════════════════
# Maps common app names/aliases to actual Windows executables and
# provides multiple fallback strategies for opening them.

APP_LAUNCH_INTELLIGENCE = {
    # Browsers (MOST IMPORTANT — agents need these for research)
    "chrome": {
        "exe_names": ["chrome.exe"],
        "search_paths": [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
        ],
        "start_cmd": "chrome",
        "fallback": "msedge",
        "window_hints": ["Chrome", "Google Chrome"],
    },
    "google chrome": {  # alias
        "redirect": "chrome",
    },
    "msedge": {
        "exe_names": ["msedge.exe"],
        "search_paths": [
            os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
        ],
        "start_cmd": "msedge",
        "window_hints": ["Edge", "Microsoft Edge"],
    },
    "edge": {"redirect": "msedge"},
    "microsoft edge": {"redirect": "msedge"},
    "firefox": {
        "exe_names": ["firefox.exe"],
        "search_paths": [
            os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe"),
        ],
        "start_cmd": "firefox",
        "window_hints": ["Firefox", "Mozilla Firefox"],
    },
    "browser": {"redirect": "__detect__"},  # Auto-detect installed browser
    
    # Text Editors
    "notepad": {
        "exe_names": ["notepad.exe"],
        "search_paths": [r"C:\Windows\notepad.exe", r"C:\Windows\System32\notepad.exe"],
        "start_cmd": "notepad",
        "window_hints": ["Notepad", "메모장", "Untitled - Notepad"],
    },
    "메모장": {"redirect": "notepad"},
    "wordpad": {
        "exe_names": ["wordpad.exe"],
        "start_cmd": "wordpad",
        "window_hints": ["WordPad"],
    },
    
    # IDEs
    "code": {
        "exe_names": ["Code.exe"],
        "search_paths": [
            os.path.expandvars(r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe"),
        ],
        "start_cmd": "code",
        "window_hints": ["Visual Studio Code"],
    },
    "vscode": {"redirect": "code"},
    "visual studio code": {"redirect": "code"},
    
    # Terminals
    "terminal": {
        "exe_names": ["WindowsTerminal.exe", "wt.exe"],
        "start_cmd": "wt",
        "fallback": "cmd",
        "window_hints": ["Terminal", "Windows Terminal"],
    },
    "wt": {"redirect": "terminal"},
    "cmd": {
        "exe_names": ["cmd.exe"],
        "start_cmd": "cmd",
        "window_hints": ["Command Prompt", "cmd.exe"],
    },
    "powershell": {
        "exe_names": ["powershell.exe"],
        "start_cmd": "powershell",
        "window_hints": ["PowerShell"],
    },
    
    # File Management
    "explorer": {
        "exe_names": ["explorer.exe"],
        "start_cmd": "explorer",
        "window_hints": ["File Explorer", "탐색기", "Explorer"],
    },
    "file explorer": {"redirect": "explorer"},
    "탐색기": {"redirect": "explorer"},
    
    # Office
    "word": {
        "exe_names": ["WINWORD.EXE"],
        "start_cmd": "winword",
        "window_hints": ["Word", "Microsoft Word"],
    },
    "excel": {
        "exe_names": ["EXCEL.EXE"],
        "start_cmd": "excel",
        "window_hints": ["Excel", "Microsoft Excel"],
    },
    "powerpoint": {
        "exe_names": ["POWERPNT.EXE"],
        "start_cmd": "powerpnt",
        "window_hints": ["PowerPoint"],
    },
    
    # Utilities
    "calculator": {
        "exe_names": ["Calculator.exe"],
        "start_cmd": "calc",
        "window_hints": ["Calculator", "계산기"],
    },
    "calc": {"redirect": "calculator"},
    "paint": {
        "exe_names": ["mspaint.exe"],
        "start_cmd": "mspaint",
        "window_hints": ["Paint"],
    },
    "snipping tool": {
        "start_cmd": "SnippingTool",
        "window_hints": ["Snipping Tool"],
    },
}


def _resolve_app_name(name: str) -> dict:
    """
    Resolve an app name to its launch configuration.
    Follows redirect chains and returns the final config.
    """
    name_lower = name.lower().strip()
    visited = set()
    
    while name_lower in APP_LAUNCH_INTELLIGENCE and len(visited) < 5:
        config = APP_LAUNCH_INTELLIGENCE[name_lower]
        if "redirect" in config:
            visited.add(name_lower)
            redirect_target = config["redirect"]
            # Dynamic browser detection
            if redirect_target == "__detect__":
                name_lower = detect_installed_browser()
            else:
                name_lower = redirect_target
            continue
        return config
    
    # Not found in intelligence map — return minimal config
    return {
        "exe_names": [],
        "start_cmd": name_lower,
        "window_hints": [name],
    }


def _smart_open_app(name: str) -> str:
    """
    Intelligent app opening with multiple fallback strategies.
    
    Strategy order:
    1. Check if already running → focus existing window (prevents duplicates!)
    2. Try direct executable path from known locations
    3. Try 'where' command to find executable in PATH
    4. For browsers without exe: try URL launch (opens default browser)
    5. Try 'start' command (only if exe was confirmed)
    6. Try fallback app
    """
    config = _resolve_app_name(name)
    name_lower = name.lower().strip()
    is_browser = name_lower in ("chrome", "msedge", "edge", "firefox", "browser", "google chrome", "microsoft edge")
    exe_found = False  # Track whether we confirmed the exe exists
    
    # ══ Strategy 1: Focus existing window FIRST (prevents duplicate windows) ══
    # This is critical for apps like Notepad — avoids opening 5 empty windows.
    if HAS_PYAUTOGUI:
        for hint in config.get("window_hints", []):
            if not hint or not hint.strip():
                continue  # Skip empty hints
            try:
                windows = pyautogui.getWindowsWithTitle(hint)
                if windows:
                    w = windows[0]
                    # ── Cross-validate: make sure the matched window is ACTUALLY the app we want ──
                    # Without this, requesting "Chrome" could match an Edge window titled "...Chrome Topic - Edge"
                    window_title = getattr(w, 'title', '') or ''
                    if is_browser and window_title:
                        # For browsers: verify the actual browser name appears in the window title
                        _browser_identity_hints = {
                            "chrome": ["chrome", "chromium"],
                            "msedge": ["edge", "microsoft edge"],
                            "firefox": ["firefox", "mozilla"],
                        }
                        _identity_keys = _browser_identity_hints.get(name_lower, [])
                        if _identity_keys:
                            title_lower = window_title.lower()
                            # Window title must end with browser name (e.g., "page title - Google Chrome")
                            _title_suffix = title_lower.rsplit(" - ", 1)[-1] if " - " in title_lower else title_lower
                            if not any(k in _title_suffix for k in _identity_keys):
                                logger.debug(f"Window '{window_title}' matched hint '{hint}' but is not {name_lower} — skipping")
                                continue
                    try:
                        if hasattr(w, 'isMinimized') and w.isMinimized:
                            w.restore()
                        # Use Win32 SetForegroundWindow for guaranteed focus
                        hwnd = w._hWnd if hasattr(w, '_hWnd') else None
                        if hwnd and sys.platform == "win32":
                            ctypes.windll.user32.SetForegroundWindow(hwnd)
                        else:
                            w.activate()
                    except Exception:
                        # Try to focus anyway
                        pass
                    time.sleep(0.3)
                    logger.info(f"{name} already open — focused window: '{window_title or hint}'")
                    return f"Already open — focused: {window_title or hint}"
            except Exception:
                pass
    
    # ══ Strategy 2: Try known executable paths (MOST RELIABLE) ══
    for path in config.get("search_paths", []):
        if os.path.exists(path):
            exe_found = True
            try:
                subprocess.Popen([path])
                logger.info(f"Opened {name} via direct path: {path}")
                time.sleep(2.0)
                # After launch, try to focus the new window
                _post_launch_focus(config.get("window_hints", []))
                return f"Opened: {name} (via {os.path.basename(path)})"
            except Exception as e:
                logger.debug(f"Direct path failed for {path}: {e}")
    
    # ══ Strategy 3: Use 'where' command to find executable in PATH ══
    for exe_name in config.get("exe_names", []):
        try:
            result = subprocess.run(
                ['where', exe_name], capture_output=True, 
                text=True, timeout=5
            )
            if result.returncode == 0 and result.stdout.strip():
                exe_path = result.stdout.strip().split('\n')[0].strip()
                if os.path.exists(exe_path):
                    exe_found = True
                    subprocess.Popen([exe_path])
                    logger.info(f"Opened {name} via 'where': {exe_path}")
                    time.sleep(2.0)
                    _post_launch_focus(config.get("window_hints", []))
                    return f"Opened: {name} (via where → {exe_path})"
        except Exception as e:
            logger.debug(f"'where' lookup failed for {exe_name}: {e}")
    
    # ── EARLY FALLBACK: If exe not found AND we have a fallback, skip to it ──
    if not exe_found and config.get("fallback"):
        fallback = config["fallback"]
        logger.warning(f"{name} exe NOT found on system — skipping to fallback: {fallback}")
        return _smart_open_app(fallback)
    
    # For browsers that weren't found at all, try URL launch (opens default browser)
    if not exe_found and is_browser:
        try:
            subprocess.Popen(['cmd', '/c', 'start', '', 'https://www.google.com'])
            logger.info(f"{name} not installed — opened default browser via URL launch")
            time.sleep(2.5)
            return f"Opened: default browser (via URL launch — {name} not installed)"
        except Exception as e:
            logger.debug(f"URL launch failed: {e}")
    
    # ══ Strategy 4: Try 'start' command — ONLY if exe was confirmed to exist ══
    if exe_found:
        start_cmd = config.get("start_cmd", name_lower)
        try:
            subprocess.Popen(['cmd', '/c', 'start', '', start_cmd])
            logger.info(f"Opened {name} via start command: {start_cmd}")
            time.sleep(2.0)
            _post_launch_focus(config.get("window_hints", []))
            return f"Opened: {name} (via start '{start_cmd}')"
        except Exception as e:
            logger.debug(f"Start command failed for {start_cmd}: {e}")
    
    # Strategy 5: For BROWSERS — open a URL to force default browser open
    if is_browser:
        try:
            subprocess.Popen(['cmd', '/c', 'start', '', 'https://www.google.com'])
            logger.info(f"Opened browser via URL launch (default browser)")
            time.sleep(2.5)
            return f"Opened: default browser (via URL launch)"
        except Exception as e:
            logger.debug(f"URL launch failed: {e}")
    
    # Strategy 6: Try fallback app (if not already tried above)
    fallback = config.get("fallback")
    if fallback:
        logger.info(f"{name} not found — trying fallback: {fallback}")
        return _smart_open_app(fallback)
    
    # Last resort: use cmd /c start with the raw name
    try:
        subprocess.Popen(['cmd', '/c', 'start', name_lower], shell=False)
        time.sleep(1.5)
        return f"Opened: {name} (cmd /c start)"
    except Exception as e:
        return f"Failed to open: {name} — {e}"


def _post_launch_focus(window_hints: list[str]):
    """After launching an app, try to bring its window to the foreground using Win32 SetForegroundWindow."""
    if not HAS_PYAUTOGUI or not window_hints:
        return
    for hint in window_hints:
        if not hint or not hint.strip():
            continue  # Skip empty hints
        try:
            windows = pyautogui.getWindowsWithTitle(hint)
            if windows:
                window = windows[0]
                try:
                    # Use Win32 SetForegroundWindow for guaranteed focus
                    hwnd = window._hWnd if hasattr(window, '_hWnd') else None
                    if hwnd and sys.platform == "win32":
                        ctypes.windll.user32.SetForegroundWindow(hwnd)
                        time.sleep(0.3)
                    else:
                        window.activate()
                except Exception:
                    pass
                try:
                    if hasattr(window, 'restore') and window.isMinimized:
                        window.restore()
                except Exception:
                    pass
                return
        except Exception:
            pass


def _smart_focus_window(title: str) -> str:
    """
    Smart window focusing with fuzzy title matching and robust error handling.
    
    Windows pyautogui.activate() often returns "Error code from Windows: 0"
    which actually means SUCCESS (error code 0 = no error). We handle this gracefully.
    
    Strategies: exact match → window hints → substring match → word match → Alt+Tab
    CRITICAL FIX: Use SetForegroundWindow directly (Win32 API) instead of pyautogui.activate()
    to guarantee foreground window change even from Electron subprocess context.
    """
    if not HAS_PYAUTOGUI:
        return f"[headless] focus window: {title}"
    
    def _try_activate(window):
        """Activate a window using Win32 SetForegroundWindow for guaranteed focus."""
        try:
            # If minimized, restore first
            if hasattr(window, 'isMinimized') and window.isMinimized:
                try:
                    window.restore()
                    time.sleep(0.3)
                except Exception:
                    pass
            
            # Get the window handle
            hwnd = window._hWnd if hasattr(window, '_hWnd') else None
            if not hwnd:
                # Fallback to pyautogui.activate()
                window.activate()
                return True
            
            # Use Win32 SetForegroundWindow directly for guaranteed focus
            # (pyautogui.activate() sometimes fails from Electron subprocess context)
            if sys.platform == "win32":
                try:
                    result = ctypes.windll.user32.SetForegroundWindow(hwnd)
                    if result:
                        time.sleep(0.5)  # Give window time to become active
                        # Verify the window is now foreground
                        fg_hwnd = ctypes.windll.user32.GetForegroundWindow()
                        if fg_hwnd == hwnd:
                            return True
                        else:
                            logger.warning(f"SetForegroundWindow claimed success but window not in foreground. Expected {hwnd}, got {fg_hwnd}")
                            return False
                    else:
                        logger.debug(f"SetForegroundWindow returned False for hwnd {hwnd}")
                        return False
                except Exception as e:
                    logger.debug(f"SetForegroundWindow failed: {e}")
                    return False
            else:
                # Non-Windows: fallback to standard activate
                window.activate()
                return True
        except Exception as e:
            logger.debug(f"Window activate failed: {e}")
            return False
    
    try:
        # Strategy 1: Exact title match
        windows = pyautogui.getWindowsWithTitle(title)
        if windows:
            if _try_activate(windows[0]):
                return f"Focused window: {title}"
        
        # Strategy 2: Try window hints from app intelligence
        name_lower = title.lower()
        config = _resolve_app_name(name_lower)
        for hint in config.get("window_hints", []):
            windows = pyautogui.getWindowsWithTitle(hint)
            if windows:
                if _try_activate(windows[0]):
                    return f"Focused window: {hint} (matched from '{title}')"
        
        # Strategy 3: Partial/substring match across all windows
        all_windows = pyautogui.getAllWindows()
        title_lower = title.lower()
        for w in all_windows:
            if w.title and title_lower in w.title.lower():
                if _try_activate(w):
                    return f"Focused window: {w.title} (partial match for '{title}')"
        
        # Strategy 4: Try matching just the first word
        first_word = title.split()[0].lower() if title.split() else ""
        if first_word:
            for w in all_windows:
                if w.title and first_word in w.title.lower():
                    if _try_activate(w):
                        return f"Focused window: {w.title} (word match for '{first_word}')"
        
        # Strategy 5: For common app names, try opening the app (it may focus the existing instance)
        if name_lower in APP_LAUNCH_INTELLIGENCE:
            return _smart_open_app(name_lower)
        
        return f"Window not found: {title}"
    except Exception as e:
        return f"Focus failed: {e}"


# ═══════════════════════════════════════════════════════════════════════
# WIN32 DIRECT KEYBOARD INPUT — bypasses pyautogui entirely
# ═══════════════════════════════════════════════════════════════════════
# pyautogui's keyboard functions use SendInput but NEVER check return
# values, silently failing in Electron subprocess contexts (windowsHide,
# piped stdio).  This module uses SendInput directly with:
#   - AttachThreadInput for foreground-thread access
#   - GetLastError + return-value checks for real success verification
#   - Comprehensive VK code mapping
# Mouse operations still use pyautogui (they work fine).
# ═══════════════════════════════════════════════════════════════════════

VK_MAP = {
    # ── Modifiers ──
    'ctrl': 0x11, 'control': 0x11, 'lctrl': 0xA2, 'rctrl': 0xA3,
    'alt': 0x12, 'menu': 0x12, 'lalt': 0xA4, 'ralt': 0xA5,
    'shift': 0x10, 'lshift': 0xA0, 'rshift': 0xA1,
    'win': 0x5B, 'lwin': 0x5B, 'rwin': 0x5C, 'windows': 0x5B,
    'command': 0x5B, 'super': 0x5B,
    # ── Navigation / Editing ──
    'enter': 0x0D, 'return': 0x0D,
    'tab': 0x09,
    'escape': 0x1B, 'esc': 0x1B,
    'backspace': 0x08, 'back': 0x08, 'bs': 0x08,
    'delete': 0x2E, 'del': 0x2E,
    'space': 0x20, ' ': 0x20,
    'up': 0x26, 'down': 0x28, 'left': 0x25, 'right': 0x27,
    'home': 0x24, 'end': 0x23,
    'pageup': 0x21, 'pgup': 0x21,
    'pagedown': 0x22, 'pgdn': 0x22,
    'insert': 0x2D,
    # ── Function keys ──
    'f1': 0x70, 'f2': 0x71, 'f3': 0x72, 'f4': 0x73,
    'f5': 0x74, 'f6': 0x75, 'f7': 0x76, 'f8': 0x77,
    'f9': 0x78, 'f10': 0x79, 'f11': 0x7A, 'f12': 0x7B,
    # ── Letters ──
    'a': 0x41, 'b': 0x42, 'c': 0x43, 'd': 0x44, 'e': 0x45,
    'f': 0x46, 'g': 0x47, 'h': 0x48, 'i': 0x49, 'j': 0x4A,
    'k': 0x4B, 'l': 0x4C, 'm': 0x4D, 'n': 0x4E, 'o': 0x4F,
    'p': 0x50, 'q': 0x51, 'r': 0x52, 's': 0x53, 't': 0x54,
    'u': 0x55, 'v': 0x56, 'w': 0x57, 'x': 0x58, 'y': 0x59,
    'z': 0x5A,
    # ── Digits ──
    '0': 0x30, '1': 0x31, '2': 0x32, '3': 0x33, '4': 0x34,
    '5': 0x35, '6': 0x36, '7': 0x37, '8': 0x38, '9': 0x39,
    # ── Numpad ──
    'num0': 0x60, 'num1': 0x61, 'num2': 0x62, 'num3': 0x63,
    'num4': 0x64, 'num5': 0x65, 'num6': 0x66, 'num7': 0x67,
    'num8': 0x68, 'num9': 0x69,
    'multiply': 0x6A, 'add': 0x6B, 'subtract': 0x6D,
    'decimal': 0x6E, 'divide': 0x6F,
    # ── IME / Lock ──
    'hangul': 0x15, 'hanguel': 0x15, 'han_eng': 0x15, 'ko_en': 0x15,
    'capslock': 0x14, 'numlock': 0x90, 'scrolllock': 0x91,
    # ── Media / System ──
    'printscreen': 0x2C, 'prtsc': 0x2C, 'prtscn': 0x2C,
    'volumeup': 0xAF, 'volumedown': 0xAE, 'volumemute': 0xAD,
    # ── Punctuation (US keyboard VK codes) ──
    'plus': 0xBB, '=': 0xBB,
    'minus': 0xBD, '-': 0xBD,
    'comma': 0xBC, ',': 0xBC,
    'period': 0xBE, '.': 0xBE,
    'semicolon': 0xBA, ';': 0xBA,
    'slash': 0xBF, '/': 0xBF,
    'backquote': 0xC0, '`': 0xC0,
    'bracketleft': 0xDB, '[': 0xDB,
    'bracketright': 0xDD, ']': 0xDD,
    'backslash': 0xDC, '\\': 0xDC,
    'quote': 0xDE, "'": 0xDE,
}

# Keys that require KEYEVENTF_EXTENDEDKEY flag
_EXTENDED_VKS = {
    0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22,  # Insert, Delete, Home, End, PgUp, PgDn
    0x25, 0x26, 0x27, 0x28,                # Arrow keys
    0x5B, 0x5C,                             # Win keys
    0x2C,                                   # PrintScreen
    0xA3, 0xA5,                             # RCtrl, RAlt
    0x90,                                   # NumLock
}


def _vk_resolve(key_name: str) -> int:
    """Resolve a key name to a Win32 Virtual Key code."""
    vk = VK_MAP.get(str(key_name).lower())
    if vk is not None:
        return vk
    # Single character → VkKeyScanW
    s = str(key_name)
    if len(s) == 1 and sys.platform == "win32":
        result = ctypes.windll.user32.VkKeyScanW(ord(s))
        vk = result & 0xFF
        if vk != 0xFF:
            return vk
    raise ValueError(f"Unknown key: {key_name}")


if sys.platform == "win32":
    # ── Win32 struct definitions (module-level, reused everywhere) ──
    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk",         ctypes.wintypes.WORD),
            ("wScan",       ctypes.wintypes.WORD),
            ("dwFlags",     ctypes.wintypes.DWORD),
            ("time",        ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx",          ctypes.wintypes.LONG),
            ("dy",          ctypes.wintypes.LONG),
            ("mouseData",   ctypes.wintypes.DWORD),
            ("dwFlags",     ctypes.wintypes.DWORD),
            ("time",        ctypes.wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class _INPUT_UNION(ctypes.Union):
        _fields_ = [
            ("ki", _KEYBDINPUT),
            ("mi", _MOUSEINPUT),
        ]

    class _INPUT(ctypes.Structure):
        _fields_ = [
            ("type",  ctypes.wintypes.DWORD),
            ("union", _INPUT_UNION),
        ]

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP       = 0x0002
    _KEYEVENTF_EXTENDEDKEY = 0x0001
    _KEYEVENTF_UNICODE     = 0x0004

    def _make_key_input(vk: int, flags: int = 0) -> _INPUT:
        """Create one keyboard INPUT struct for SendInput."""
        if vk in _EXTENDED_VKS:
            flags |= _KEYEVENTF_EXTENDEDKEY
        scan = ctypes.windll.user32.MapVirtualKeyW(vk, 0)
        ki = _KEYBDINPUT()
        ki.wVk = vk
        ki.wScan = scan
        ki.dwFlags = flags
        ki.time = 0
        ki.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
        inp = _INPUT()
        inp.type = _INPUT_KEYBOARD
        inp.union.ki = ki
        return inp

    def _send_inputs(inputs: list) -> int:
        """Send INPUT structs via SendInput. Returns count of events injected."""
        n = len(inputs)
        if n == 0:
            return 0
        arr = (_INPUT * n)(*inputs)
        result = ctypes.windll.user32.SendInput(n, ctypes.pointer(arr), ctypes.sizeof(_INPUT))
        if result == 0:
            err = ctypes.get_last_error()
            logger.warning(f"SendInput returned 0 (failed). GetLastError={err}, n_inputs={n}")
        return result

    def _attach_to_foreground() -> tuple:
        """Attach our thread to the foreground window's input queue.

        Returns (our_tid, fg_tid, fg_hwnd) for detach, or None on failure.
        """
        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            fg_hwnd = user32.GetForegroundWindow()
            if not fg_hwnd:
                logger.debug("No foreground window — skipping AttachThreadInput")
                return None
            fg_tid = user32.GetWindowThreadProcessId(fg_hwnd, None)
            our_tid = kernel32.GetCurrentThreadId()
            if fg_tid == our_tid:
                return None  # Same thread, no need
            # Attach
            user32.AttachThreadInput(our_tid, fg_tid, True)
            return (our_tid, fg_tid, fg_hwnd)
        except Exception as e:
            logger.debug(f"AttachThreadInput failed: {e}")
            return None

    def _force_english_ime() -> None:
        """Force English input mode by disabling Korean IME Hangul mode.

        Uses ImmGetConversionStatus to detect if Korean (Hangul) mode is active.
        If so, sends VK_HANGUL to toggle to English mode.
        This prevents typing gibberish when the user's system has Korean IME.
        """
        try:
            user32 = ctypes.windll.user32
            imm32 = ctypes.windll.imm32

            fg_hwnd = user32.GetForegroundWindow()
            if not fg_hwnd:
                return

            himc = imm32.ImmGetContext(fg_hwnd)
            if not himc:
                return

            try:
                conversion = ctypes.c_uint()
                sentence = ctypes.c_uint()
                if imm32.ImmGetConversionStatus(himc, ctypes.byref(conversion), ctypes.byref(sentence)):
                    # IME_CMODE_NATIVE (0x1) = Korean/Hangul mode active
                    if conversion.value & 0x1:
                        logger.info("Korean IME (Hangul mode) detected — toggling to English")
                        # Send VK_HANGUL to toggle to English (with thread attachment)
                        vk_hangul = 0x15
                        attach_info = _attach_to_foreground()
                        try:
                            down = _make_key_input(vk_hangul, 0)
                            up = _make_key_input(vk_hangul, _KEYEVENTF_KEYUP)
                            _send_inputs([down, up])
                        finally:
                            _detach_from_foreground(attach_info)
                        time.sleep(0.15)  # Wait for IME toggle to take effect
                    else:
                        logger.debug("IME already in English mode")
            finally:
                imm32.ImmReleaseContext(fg_hwnd, himc)
        except Exception as e:
            logger.debug(f"_force_english_ime: {e}")

    def _detach_from_foreground(info: tuple) -> None:
        """Detach from foreground window's input queue."""
        if info is None:
            return
        try:
            our_tid, fg_tid, _ = info
            ctypes.windll.user32.AttachThreadInput(our_tid, fg_tid, False)
        except Exception:
            pass

    def win32_press_key(key_name: str, presses: int = 1) -> bool:
        """Press and release a key using direct Win32 SendInput.

        Returns True if SendInput reported success.
        """
        vk = _vk_resolve(key_name)
        attach_info = _attach_to_foreground()
        try:
            total_sent = 0
            for _ in range(presses):
                down = _make_key_input(vk, 0)
                up = _make_key_input(vk, _KEYEVENTF_KEYUP)
                sent = _send_inputs([down, up])
                total_sent += sent
                if presses > 1:
                    time.sleep(0.05)
            success = total_sent > 0
            if success:
                logger.debug(f"win32_press_key({key_name}) OK — {total_sent} events")
            else:
                logger.error(f"win32_press_key({key_name}) FAILED — SendInput returned 0")
            return success
        finally:
            _detach_from_foreground(attach_info)

    def _ime_commit_composition() -> None:
        """Commit any pending IME composition on the foreground window.

        Prevents Korean IME from swallowing modifier key (ctrl/alt) events:
        when Korean IME has an active composition and receives a ctrl keydown,
        it commits the composition first, releasing stray characters (s/S/s)
        into the text buffer before ctrl+key reaches the app.
        ImmNotifyIME(NI_COMPOSITIONSTR, CPS_COMPLETE) forces the commit cleanly.
        """
        try:
            user32 = ctypes.windll.user32
            imm32 = ctypes.windll.imm32
            fg_hwnd = user32.GetForegroundWindow()
            if not fg_hwnd:
                return
            himc = imm32.ImmGetContext(fg_hwnd)
            if not himc:
                return
            try:
                NI_COMPOSITIONSTR = 0x0015
                CPS_COMPLETE      = 0x0001
                imm32.ImmNotifyIME(himc, NI_COMPOSITIONSTR, CPS_COMPLETE, 0)
                logger.debug("_ime_commit_composition: composition committed")
            finally:
                imm32.ImmReleaseContext(fg_hwnd, himc)
        except Exception as e:
            logger.debug(f"_ime_commit_composition: {e}")

    def win32_hotkey(*key_names: str) -> bool:
        """Press a key combination using direct Win32 SendInput.

        E.g., win32_hotkey('ctrl', 'v') sends Ctrl down → V down → V up → Ctrl up.
        Returns True if SendInput reported success.

        Implementation note: keys are sent one-at-a-time in separate SendInput
        calls (not batched) with a small inter-key delay. Batching all events in
        a single SendInput causes some apps (e.g. Windows 11 Notepad) to not
        register the modifier as pressed when the main key arrives — resulting in
        ctrl being "swallowed" and only the bare key ('s') being typed.
        pyautogui uses the same per-key approach for this reason.
        AttachThreadInput is intentionally NOT used here: SendInput already
        injects into the active window's queue, and thread attachment can
        actually mis-route events on some app/thread configurations.
        """
        _MODIFIER_VKS = {'ctrl', 'alt', 'win', 'lctrl', 'rctrl', 'lalt', 'ralt', 'shift', 'lshift', 'rshift'}
        _KEY_DELAY = 0.05  # 50 ms — Notepad/IME needs more than 20 ms to register modifier state

        # ── PRE-HOTKEY FIX 1: Commit any pending IME composition ──
        # Korean IME with an active composition intercepts Ctrl-down and commits
        # the composition first, injecting stray characters (s/S/sss) into the
        # text buffer before the actual ctrl+key reaches the app.
        # This is THE root cause of "ctrl+s types 'sss' instead of saving".
        # _ime_commit_composition forces a clean commit BEFORE we send keys.
        try:
            _ime_commit_composition()
        except Exception as _ice:
            logger.debug(f"win32_hotkey: IME commit failed (non-fatal): {_ice}")

        # ── PRE-HOTKEY FIX 2: Release any stuck modifier keys ──
        # If a prior action crashed or timed out mid-hotkey, a modifier key may
        # be stuck in the DOWN state.  Our new Ctrl-down would then be a no-op
        # (the OS thinks it's already held), so only the bare main key registers.
        _STUCK_CHECK_VKS = [0x11, 0x10, 0x12, 0x5B]  # Ctrl, Shift, Alt, Win
        for _mvk in _STUCK_CHECK_VKS:
            try:
                if ctypes.windll.user32.GetAsyncKeyState(_mvk) & 0x8000:
                    _send_inputs([_make_key_input(_mvk, _KEYEVENTF_KEYUP)])
                    logger.warning(f"win32_hotkey: released stuck modifier VK=0x{_mvk:02X} before hotkey")
            except Exception:
                pass

        time.sleep(0.03)  # Let IME commit and modifier releases settle

        keys_lower = [k.lower() for k in key_names]
        vks = [_vk_resolve(k) for k in key_names]

        # Split into modifier keys and non-modifier keys (preserving order)
        modifier_vks = [vks[i] for i, k in enumerate(keys_lower) if k in _MODIFIER_VKS]
        main_vks     = [vks[i] for i, k in enumerate(keys_lower) if k not in _MODIFIER_VKS]

        total_sent = 0
        all_inputs = len(vks) * 2  # each key gets a down and an up event

        # 1. Send all modifier keys DOWN
        for vk in modifier_vks:
            total_sent += _send_inputs([_make_key_input(vk, 0)])
            time.sleep(_KEY_DELAY)

        # 2. Send main keys DOWN then UP (each pair in its own call)
        for vk in main_vks:
            total_sent += _send_inputs([_make_key_input(vk, 0)])
            time.sleep(_KEY_DELAY)
            total_sent += _send_inputs([_make_key_input(vk, _KEYEVENTF_KEYUP)])
            time.sleep(_KEY_DELAY)

        # 3. Release modifier keys UP (reverse order)
        for vk in reversed(modifier_vks):
            total_sent += _send_inputs([_make_key_input(vk, _KEYEVENTF_KEYUP)])
            time.sleep(_KEY_DELAY)

        success = total_sent > 0
        if success:
            logger.debug(f"win32_hotkey({'+'.join(key_names)}) OK — {total_sent}/{all_inputs} events")
        else:
            logger.warning(f"win32_hotkey({'+'.join(key_names)}) FAILED — SendInput returned 0 for all events")
        return success

    def win32_type_unicode(char: str) -> bool:
        """Type a single Unicode character via SendInput KEYEVENTF_UNICODE."""
        code = ord(char)
        if code > 0xFFFF:
            high = 0xD800 + ((code - 0x10000) >> 10)
            low  = 0xDC00 + ((code - 0x10000) & 0x3FF)
            surrogates = [high, low]
        else:
            surrogates = [code]

        inputs = []
        for wScan in surrogates:
            ki_down = _KEYBDINPUT()
            ki_down.wVk = 0
            ki_down.wScan = wScan
            ki_down.dwFlags = _KEYEVENTF_UNICODE
            ki_down.time = 0
            ki_down.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
            inp_down = _INPUT()
            inp_down.type = _INPUT_KEYBOARD
            inp_down.union.ki = ki_down
            inputs.append(inp_down)

            ki_up = _KEYBDINPUT()
            ki_up.wVk = 0
            ki_up.wScan = wScan
            ki_up.dwFlags = _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP
            ki_up.time = 0
            ki_up.dwExtraInfo = ctypes.pointer(ctypes.c_ulong(0))
            inp_up = _INPUT()
            inp_up.type = _INPUT_KEYBOARD
            inp_up.union.ki = ki_up
            inputs.append(inp_up)

        sent = _send_inputs(inputs)
        return sent > 0

    def _get_foreground_window_title() -> str:
        """Get the title of the current foreground window."""
        try:
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            if not hwnd:
                return "(no foreground window)"
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length == 0:
                return "(untitled)"
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:
            return "(unknown)"

    HAS_WIN32_KEYBOARD = True
    logger.info("Win32 direct keyboard initialized — bypassing pyautogui for keyboard ops")

else:
    HAS_WIN32_KEYBOARD = False

    def win32_press_key(key_name, presses=1):
        pyautogui.press(key_name, presses=presses)
        return True

    def win32_hotkey(*key_names):
        pyautogui.hotkey(*key_names)
        return True

    def win32_type_unicode(char):
        pyautogui.write(char)
        return True

    def _get_foreground_window_title():
        return "(non-windows)"


class OSController:
    """Cross-platform OS controller with resolution-independent operation.
    
    Supports:
    - Absolute pixel coordinates (legacy)
    - Normalized coordinates (0.0-1.0) via rel_x, rel_y params
    - Automatic DPI scaling detection
    - Thread-safe execution for concurrent sessions
    """

    # The screenshot is always normalized to this width for the LLM
    SCREENSHOT_NORMALIZED_WIDTH = 1920

    def __init__(self):
        self.enabled = HAS_PYAUTOGUI
        self._lock = threading.Lock()  # Thread safety for concurrent sessions
        
        if self.enabled:
            # CRITICAL: Set DPI awareness BEFORE querying screen size
            self._set_dpi_awareness()
            self.screen_width, self.screen_height = pyautogui.size()
            # Coordinate scale factor: LLM sees 1920px-wide screenshot,
            # but screen may be larger. We need to map LLM coords → screen coords.
            self._coord_scale_x = self.screen_width / self.SCREENSHOT_NORMALIZED_WIDTH
            # Use same ratio for Y to maintain aspect ratio
            self._coord_scale_y = self._coord_scale_x
            logger.info(
                f"OS Controller initialized: {self.screen_width}x{self.screen_height} "
                f"(coord scale: {self._coord_scale_x:.3f}x)"
            )
        else:
            self.screen_width = 1920
            self.screen_height = 1080
            self._coord_scale_x = 1.0
            self._coord_scale_y = 1.0
            logger.warning("OS Controller running in headless mode")

    @staticmethod
    def _set_dpi_awareness():
        """Set process DPI awareness so pyautogui reports physical pixels."""
        if sys.platform != "win32":
            return
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"DPI awareness setup failed: {e}")

    def get_coord_scale(self) -> float:
        """Return the coordinate scale factor (screen_width / 1920)."""
        return self._coord_scale_x

    def refresh_screen_info(self):
        """Refresh screen dimensions — call if display changes."""
        if self.enabled:
            self.screen_width, self.screen_height = pyautogui.size()
            self._coord_scale_x = self.screen_width / self.SCREENSHOT_NORMALIZED_WIDTH
            self._coord_scale_y = self._coord_scale_x
            logger.info(f"Screen refreshed: {self.screen_width}x{self.screen_height} (scale: {self._coord_scale_x:.3f}x)")

    def _resolve_coordinates(self, params: dict) -> dict:
        """Resolve coordinates from LLM / SoM coordinate space to actual screen pixels.
        
        Coordinate resolution pipeline:
        1. Check _from_som flag — SoM coords are already in screen space, skip scaling
        2. rel_x/rel_y → screen pixels
        3. Detect fractional 0.0-1.0 coords → screen pixels
        4. Scale from 1920-normalized screenshot space → actual screen space
        5. Clamp to screen bounds
        """
        resolved = dict(params)
        
        # Pop internal flags
        from_som = resolved.pop("_from_som", False)
        
        # Relative coordinates (resolution-independent)
        if "rel_x" in resolved or "rel_y" in resolved:
            rel_x = resolved.get("rel_x", 0.5)
            rel_y = resolved.get("rel_y", 0.5)
            resolved["x"] = int(max(0, min(1.0, rel_x)) * self.screen_width)
            resolved["y"] = int(max(0, min(1.0, rel_y)) * self.screen_height)
            resolved.pop("rel_x", None)
            resolved.pop("rel_y", None)
            from_som = True  # Already in screen space
        
        # Auto-detect normalized 0~1 coordinates (BOTH must be fractional, not integers 0 or 1)
        if not from_som and "x" in resolved and "y" in resolved:
            try:
                xf = float(resolved["x"])
                yf = float(resolved["y"])
                # Only treat as normalized if both are fractional (not 0.0 or 1.0 exactly)
                is_fractional_x = 0.0 < xf < 1.0 and xf != int(xf)
                is_fractional_y = 0.0 < yf < 1.0 and yf != int(yf)
                if is_fractional_x and is_fractional_y:
                    resolved["x"] = int(xf * self.screen_width)
                    resolved["y"] = int(yf * self.screen_height)
                    logger.debug(f"Normalized coords detected: ({xf:.3f}, {yf:.3f}) → ({resolved['x']}, {resolved['y']})")
                    from_som = True  # Already scaled to screen space
            except (TypeError, ValueError):
                pass
        
        # ═══ COORDINATE SCALING: 1920-normalized → actual screen pixels ═══
        # The LLM sees a 1920px-wide screenshot. Its coordinate estimates are
        # in that 1920-space. We must scale to actual screen resolution.
        # SoM-resolved coordinates are already in screen space (skip).
        if not from_som and abs(self._coord_scale_x - 1.0) > 0.01:
            for key in ("x",):
                if key in resolved:
                    try:
                        val = float(resolved[key])
                        resolved[key] = int(val * self._coord_scale_x)
                    except (TypeError, ValueError):
                        pass
            for key in ("y",):
                if key in resolved:
                    try:
                        val = float(resolved[key])
                        resolved[key] = int(val * self._coord_scale_y)
                    except (TypeError, ValueError):
                        pass
            for key in ("startX", "endX"):
                if key in resolved:
                    try:
                        resolved[key] = int(float(resolved[key]) * self._coord_scale_x)
                    except (TypeError, ValueError):
                        pass
            for key in ("startY", "endY"):
                if key in resolved:
                    try:
                        resolved[key] = int(float(resolved[key]) * self._coord_scale_y)
                    except (TypeError, ValueError):
                        pass
        
        # Clamp absolute coordinates to screen bounds
        if "x" in resolved:
            raw_x = int(resolved["x"]) if not isinstance(resolved["x"], int) else resolved["x"]
            if raw_x > self.screen_width * 1.5 or raw_x < -100:
                logger.warning(f"Extreme X coordinate: {raw_x} (screen: {self.screen_width})")
            resolved["x"] = max(0, min(raw_x, self.screen_width - 1))
        if "y" in resolved:
            raw_y = int(resolved["y"]) if not isinstance(resolved["y"], int) else resolved["y"]
            if raw_y > self.screen_height * 1.5 or raw_y < -100:
                logger.warning(f"Extreme Y coordinate: {raw_y} (screen: {self.screen_height})")
            resolved["y"] = max(0, min(raw_y, self.screen_height - 1))
        
        # Handle start/end coordinates for drag
        for prefix in ("startX", "endX"):
            if prefix in resolved:
                resolved[prefix] = max(0, min(int(resolved[prefix]), self.screen_width - 1))
        for prefix in ("startY", "endY"):
            if prefix in resolved:
                resolved[prefix] = max(0, min(int(resolved[prefix]), self.screen_height - 1))
                
        return resolved

    def execute_action(self, action_type: str, params: dict) -> dict[str, Any]:
        """Execute an OS action thread-safely with resolution-independent coords."""
        action_map = {
            "click": self._click,
            "double_click": self._double_click,
            "right_click": self._right_click,
            "type_text": self._type_text,
            "type_text_fast": self._type_text_fast,  # explicit clipboard paste mode
            "press_key": self._press_key,
            "hotkey": self._hotkey,
            "move_mouse": self._move_mouse,
            "scroll": self._scroll,
            "drag": self._drag,
            "open_app": self._open_app,
            "close_app": self._close_app,
            "screenshot": self._screenshot_action,
            "wait": self._wait,
            "get_window_list": self._get_window_list,
            "focus_window": self._focus_window,
            "run_command": self._run_command,
            "clipboard_copy": self._clipboard_copy,
            "clipboard_set": self._clipboard_copy,  # alias
            "clipboard_paste": self._clipboard_paste,
            "clipboard_get": self._clipboard_get,
        }

        # Resolve *_element suffix → base action (SoM fallback when element coords not resolved)
        if action_type.endswith("_element"):
            base_type = action_type.replace("_element", "")
            if base_type in action_map:
                if "id" in params and "x" not in params and "y" not in params and "rel_x" not in params and "rel_y" not in params:
                    return {"success": False, "error": f"Unresolved element action: {action_type} requires coordinates (SoM element id={params.get('id')})"}
                logger.warning(f"SoM unavailable — '{action_type}' resolved to '{base_type}'.")
                action_type = base_type

        handler = action_map.get(action_type)
        if not handler:
            return {"success": False, "error": f"Unknown action: {action_type}"}

        # Resolve coordinates (relative → absolute, clamp to screen)
        resolved_params = self._resolve_coordinates(params)

        try:
            with self._lock:  # Thread-safe: one OS action at a time
                result = handler(resolved_params)

            # Action-specific success semantics
            if action_type == "run_command":
                returncode = None
                if isinstance(result, dict):
                    returncode = result.get("returncode")
                if returncode is None and isinstance(result, str) and result.startswith("Exit "):
                    try:
                        returncode = int(result.split(":", 1)[0].replace("Exit", "").strip())
                    except Exception:
                        returncode = None
                success = (returncode == 0) if returncode is not None else False
                return {"success": success, "result": result, "returncode": returncode}

            return {"success": True, "result": result}
        except Exception as e:
            if HAS_PYAUTOGUI and hasattr(pyautogui, 'FailSafeException') and isinstance(e, pyautogui.FailSafeException):
                return {"success": False, "error": "Failsafe triggered (mouse moved to corner)"}
            logger.error(f"Action {action_type} failed: {e}")
            return {"success": False, "error": str(e)}

    # === Mouse Actions ===

    def _click(self, params: dict) -> str:
        x = params.get("x", 0)
        y = params.get("y", 0)
        button = params.get("button", "left")
        clicks = params.get("clicks", 1)
        
        if not self.enabled:
            return f"[headless] click at ({x}, {y})"
        
        # Clamp coordinates
        x = max(0, min(x, self.screen_width - 1))
        y = max(0, min(y, self.screen_height - 1))
        
        pyautogui.click(x=x, y=y, button=button, clicks=clicks)
        return f"Clicked at ({x}, {y}) with {button} button"

    def _double_click(self, params: dict) -> str:
        x = params.get("x", 0)
        y = params.get("y", 0)
        
        if not self.enabled:
            return f"[headless] double-click at ({x}, {y})"
        
        pyautogui.doubleClick(x=x, y=y)
        return f"Double-clicked at ({x}, {y})"

    def _right_click(self, params: dict) -> str:
        x = params.get("x", 0)
        y = params.get("y", 0)
        
        if not self.enabled:
            return f"[headless] right-click at ({x}, {y})"
        
        pyautogui.rightClick(x=x, y=y)
        return f"Right-clicked at ({x}, {y})"

    def _move_mouse(self, params: dict) -> str:
        x = params.get("x", 0)
        y = params.get("y", 0)
        duration = params.get("duration", 0.3)
        
        if not self.enabled:
            return f"[headless] move mouse to ({x}, {y})"
        
        pyautogui.moveTo(x=x, y=y, duration=duration)
        return f"Moved mouse to ({x}, {y})"

    def _drag(self, params: dict) -> str:
        startX = params.get("startX", 0)
        startY = params.get("startY", 0)
        endX = params.get("endX", 0)
        endY = params.get("endY", 0)
        duration = params.get("duration", 0.5)
        
        if not self.enabled:
            return f"[headless] drag from ({startX}, {startY}) to ({endX}, {endY})"
        
        pyautogui.moveTo(startX, startY)
        pyautogui.drag(endX - startX, endY - startY, duration=duration)
        return f"Dragged from ({startX}, {startY}) to ({endX}, {endY})"

    def _scroll(self, params: dict) -> str:
        clicks = params.get("clicks", -5)
        x = params.get("x")
        y = params.get("y")
        
        if not self.enabled:
            return f"[headless] scroll {clicks}"
        
        if x is not None and y is not None:
            pyautogui.scroll(clicks, x=x, y=y)
        else:
            pyautogui.scroll(clicks)
        return f"Scrolled {clicks} clicks"

    # === Keyboard Actions ===

    @staticmethod
    def _win_clipboard_get_text() -> str:
        if sys.platform != "win32":
            return ""
        try:
            CF_UNICODETEXT = 13
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
            if not user32.OpenClipboard(None):
                return ""
            try:
                handle = user32.GetClipboardData(CF_UNICODETEXT)
                if not handle:
                    return ""
                locked = kernel32.GlobalLock(handle)
                if not locked:
                    return ""
                try:
                    text = ctypes.wstring_at(locked)
                    return text or ""
                finally:
                    kernel32.GlobalUnlock(handle)
            finally:
                user32.CloseClipboard()
        except Exception:
            return ""

    @staticmethod
    def _win_clipboard_set_text(text: str) -> bool:
        if sys.platform != "win32":
            return False
        try:
            CF_UNICODETEXT = 13
            GMEM_MOVEABLE = 0x0002
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32

            if not user32.OpenClipboard(None):
                return False
            try:
                user32.EmptyClipboard()

                if text is None:
                    text = ""
                data = (text + "\x00").encode("utf-16-le")
                h_global = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
                if not h_global:
                    return False
                locked = kernel32.GlobalLock(h_global)
                if not locked:
                    kernel32.GlobalFree(h_global)
                    return False
                try:
                    ctypes.memmove(locked, data, len(data))
                finally:
                    kernel32.GlobalUnlock(h_global)

                if not user32.SetClipboardData(CF_UNICODETEXT, h_global):
                    kernel32.GlobalFree(h_global)
                    return False

                # Ownership transferred to system.
                return True
            finally:
                user32.CloseClipboard()
        except Exception:
            return False

    def _paste_text_via_clipboard(self, text: str) -> bool:
        """Paste text with minimal IME interference.

        ENHANCED: Verifies clipboard was set, adds focus check + delay,
        and deactivates IME before pasting to prevent Korean IME interference.
        Returns True if clipboard-paste was used successfully.
        """
        if not self.enabled:
            return False
        if text is None:
            text = ""

        old_clipboard = ""
        clipboard_saved = False
        restored = False

        try:
            try:
                import pyperclip  # type: ignore
                try:
                    old_clipboard = pyperclip.paste() or ""
                    clipboard_saved = True
                except Exception:
                    old_clipboard = ""

                # Set clipboard
                pyperclip.copy(text)
                time.sleep(0.05)  # Let clipboard settle

                # Verify clipboard was actually set
                try:
                    verify = pyperclip.paste() or ""
                    if verify != text:
                        logger.warning(f"Clipboard verify mismatch: set {len(text)} chars, got {len(verify)} chars")
                        # Retry once
                        pyperclip.copy(text)
                        time.sleep(0.1)
                except Exception:
                    pass  # Verification is best-effort

                # Ensure focus is on target window (NOT Ogenti)
                self._ensure_target_focus()
                time.sleep(0.1)

                # Force English IME before paste (Korean IME can interfere with Ctrl+V)
                _force_english_ime()
                time.sleep(0.05)  # Extra settle time after IME toggle

                fg_title = _get_foreground_window_title()
                logger.info(f"Clipboard paste: Ctrl+V → foreground='{fg_title}', text={len(text)} chars")

                # Paste — split Ctrl+V into separate SendInput calls for reliability
                # Single-batch SendInput can drop Ctrl modifier in some apps (Edge, etc.)
                attach_info = _attach_to_foreground()
                try:
                    vk_ctrl = _vk_resolve('ctrl')
                    vk_v = _vk_resolve('v')
                    # Step 1: Ctrl down
                    _send_inputs([_make_key_input(vk_ctrl, 0)])
                    time.sleep(0.05)  # Let modifier register
                    # Step 2: V down + up
                    _send_inputs([_make_key_input(vk_v, 0), _make_key_input(vk_v, _KEYEVENTF_KEYUP)])
                    time.sleep(0.05)
                    # Step 3: Ctrl up
                    _send_inputs([_make_key_input(vk_ctrl, _KEYEVENTF_KEYUP)])
                finally:
                    _detach_from_foreground(attach_info)
                # Longer delay for large text / Korean text
                paste_delay = 0.3 if len(text) > 200 else 0.2
                time.sleep(paste_delay)

                try:
                    pyperclip.copy(old_clipboard)
                    restored = True
                    logger.debug("Clipboard restored after paste-based typing")
                except Exception:
                    logger.warning("Failed to restore clipboard after paste-based typing")
                return True
            except ImportError:
                if sys.platform == "win32":
                    old_clipboard = self._win_clipboard_get_text()
                    clipboard_saved = bool(old_clipboard)
                    if not self._win_clipboard_set_text(text):
                        return False

                    self._ensure_target_focus()
                    time.sleep(0.1)

                    # Force English IME before paste
                    _force_english_ime()
                    time.sleep(0.05)  # Extra settle time after IME toggle

                    fg_title = _get_foreground_window_title()
                    logger.info(f"Clipboard paste (win32 path): Ctrl+V → foreground='{fg_title}'")
                    # Split Ctrl+V for reliability (same as pyperclip path)
                    attach_info = _attach_to_foreground()
                    try:
                        vk_ctrl = _vk_resolve('ctrl')
                        vk_v = _vk_resolve('v')
                        _send_inputs([_make_key_input(vk_ctrl, 0)])
                        time.sleep(0.05)
                        _send_inputs([_make_key_input(vk_v, 0), _make_key_input(vk_v, _KEYEVENTF_KEYUP)])
                        time.sleep(0.05)
                        _send_inputs([_make_key_input(vk_ctrl, _KEYEVENTF_KEYUP)])
                    finally:
                        _detach_from_foreground(attach_info)
                    time.sleep(0.3)
                    try:
                        self._win_clipboard_set_text(old_clipboard)
                        restored = True
                        logger.debug("Clipboard restored after paste-based typing (win32)")
                    except Exception:
                        logger.warning("Failed to restore clipboard after paste-based typing (win32)")
                    return True
                return False
        finally:
            if not restored and clipboard_saved:
                logger.debug("Clipboard restoration via finally block")
                time.sleep(0.05)  # Brief delay to ensure paste completes
                try:
                    import pyperclip
                    pyperclip.copy(old_clipboard)
                except Exception:
                    if sys.platform == "win32":
                        try:
                            self._win_clipboard_set_text(old_clipboard)
                        except Exception:
                            logger.warning("Clipboard restoration failed in finally block")

    # ================================================================
    # Focus management — ensure keyboard goes to correct window
    # ================================================================

    @staticmethod
    def _ensure_target_focus() -> None:
        """Ensure the foreground window is NOT the Ogenti/Electron app.

        If Ogenti is focused, find the next visible window and activate it.
        This prevents keyboard input from being swallowed by the agent's own UI.
        """
        if sys.platform != "win32":
            return

        try:
            user32 = ctypes.windll.user32
            fg_hwnd = user32.GetForegroundWindow()
            if not fg_hwnd:
                logger.warning("_ensure_target_focus: no foreground window")
                return

            fg_title = _get_foreground_window_title()
            fg_lower = fg_title.lower()

            # Check if Ogenti/Electron is focused
            ogenti_keywords = ['ogenti', 'electron', 'ai_master']
            is_ogenti = any(kw in fg_lower for kw in ogenti_keywords)

            if not is_ogenti:
                logger.debug(f"Focus OK: foreground='{fg_title}'")
                return

            logger.warning(f"Ogenti window is focused ('{fg_title}') — finding target window...")

            # Enumerate top-level windows and find the best non-Ogenti candidate
            candidates = []

            @ctypes.WINFUNCTYPE(ctypes.wintypes.BOOL, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
            def enum_cb(hwnd, _lp):
                if not user32.IsWindowVisible(hwnd):
                    return True
                if user32.IsIconic(hwnd):  # Minimized
                    return True
                length = user32.GetWindowTextLengthW(hwnd)
                if length == 0:
                    return True
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value
                title_lower = title.lower()
                # Skip Ogenti, desktop, shell windows
                skip_words = ['ogenti', 'electron', 'program manager',
                              'windows input experience', 'textinputhost',
                              'windows default lock screen',
                              'settings', 'microsoft text input']
                if any(sw in title_lower for sw in skip_words):
                    return True
                candidates.append((hwnd, title))
                return True

            user32.EnumWindows(enum_cb, 0)

            if candidates:
                target_hwnd, target_title = candidates[0]  # Top Z-order non-Ogenti window
                logger.info(f"Activating target window: '{target_title}'")
                # Try SetForegroundWindow with AllowSetForegroundWindow trick
                user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
                user32.SetForegroundWindow(target_hwnd)
                time.sleep(0.1)
                # Verify
                new_fg = _get_foreground_window_title()
                logger.info(f"After focus switch: foreground='{new_fg}'")
            else:
                logger.warning("No suitable target window found — keyboard may go to desktop")
        except Exception as e:
            logger.error(f"_ensure_target_focus error: {e}")

    # ================================================================
    # Human-like character-by-character typing via Win32 SendInput
    # ================================================================
    # Uses KEYEVENTF_UNICODE flag to inject each character through the
    # OS input pipeline (including IME processing), rather than crude
    # clipboard paste.  Random inter-key delays simulate human cadence.
    # ================================================================

    @staticmethod
    def _send_unicode_char(char: str) -> None:
        """Send a single Unicode character via SendInput (KEYEVENTF_UNICODE).

        Uses the module-level win32_type_unicode which does proper
        AttachThreadInput + SendInput with return value checking.
        """
        win32_type_unicode(char)

    @staticmethod
    def _human_delay(base_interval: float = 0.04) -> None:
        """Sleep with human-like variance.

        Simulates realistic typing cadence:
        - Base interval: ~40ms (reasonable ~25 WPM equivalent for Korean)
        - Random jitter: ±50% of base
        - Occasional micro-pauses: 5% chance of 80-200ms pause (thinking)
        """
        jitter = base_interval * random.uniform(-0.5, 0.5)
        delay = base_interval + jitter
        # Occasional micro-pause (simulates thinking between words)
        if random.random() < 0.05:
            delay += random.uniform(0.08, 0.2)
        time.sleep(max(0.01, delay))

    def _type_text_humanlike(self, text: str, interval: float = 0.04) -> bool:
        """Type text one character at a time via SendInput, like a real human.

        Returns True on success.
        """
        if not self.enabled or not text:
            return False

        # Force English IME before character-by-character typing
        _force_english_ime()

        if sys.platform != "win32":
            # Non-Windows: fall back to pyautogui character-by-character
            for ch in text:
                pyautogui.write(ch)
                self._human_delay(interval)
            return True

        attach_info = _attach_to_foreground()
        try:
            for i, char in enumerate(text):
                if char == '\n':
                    win32_press_key('enter')
                elif char == '\t':
                    win32_press_key('tab')
                else:
                    self._send_unicode_char(char)
                # Human-like delay between characters
                if i < len(text) - 1:
                    self._human_delay(interval)
        finally:
            _detach_from_foreground(attach_info)

        return True

    def _type_text(self, params: dict) -> str:
        text = params.get("text", "")
        interval = params.get("interval", 0.04)
        mode = params.get("mode", "auto")  # "auto" (default) | "human" | "fast"
        
        if not self.enabled:
            return f"[headless] type: {text[:50]}"
        
        if not text:
            return "Nothing to type (empty text)"

        # ── Ensure a non-Ogenti window has focus before typing ──
        self._ensure_target_focus()

        # ── Force English IME to prevent Korean gibberish ──
        _force_english_ime()

        # ═══ RELIABILITY-FIRST: Default to clipboard paste for ALL text ═══
        # Human-like SendInput typing is fragile: fails with IME, autocomplete,
        # certain apps, focus issues. Clipboard paste works universally.
        # Only use human-like typing when explicitly requested with mode="human".

        if mode == "human":
            # Explicitly requested human-like typing
            if self._type_text_humanlike(text, interval):
                return f"Typed: {text[:80]}{'...' if len(text) > 80 else ''} ({len(text)} chars, human-like)"
            # Fall through to clipboard paste

        # Default path: clipboard paste (most reliable)
        if self._paste_text_via_clipboard(text):
            return f"Typed: {text[:80]}{'...' if len(text) > 80 else ''} ({len(text)} chars, clipboard)"

        # Fallback: human-like typing (if clipboard failed)
        if self._type_text_humanlike(text, interval):
            return f"Typed: {text[:80]}{'...' if len(text) > 80 else ''} ({len(text)} chars, humanlike-fallback)"

        # Last resort: character-by-character via Win32 SendInput
        logger.warning(f"type_text: clipboard + humanlike both failed, last-resort char-by-char")
        attach_info = _attach_to_foreground()
        try:
            for ch in text:
                win32_type_unicode(ch)
                time.sleep(0.02)
        finally:
            _detach_from_foreground(attach_info)
        
        return f"Typed: {text[:80]}{'...' if len(text) > 80 else ''} ({len(text)} chars, win32-lastresort)"

    def _type_text_fast(self, params: dict) -> str:
        """Explicit clipboard-paste mode for speed-critical bulk text input."""
        text = params.get("text", "")
        if not self.enabled:
            return f"[headless] fast-type: {text[:50]}"
        if not text:
            return "Nothing to type (empty text)"
        if self._paste_text_via_clipboard(text):
            return f"Fast-typed: {text[:80]}{'...' if len(text) > 80 else ''} ({len(text)} chars, clipboard)"
        # Fallback to human-like if clipboard fails
        return self._type_text(params)

    def _press_key(self, params: dict) -> str:
        key = params.get("key", "")
        presses = params.get("presses", 1)
        
        if not self.enabled:
            return f"[headless] press: {key}"
        
        fg_title = _get_foreground_window_title()
        logger.info(f"press_key({key}) x{presses} → foreground='{fg_title}'")
        success = win32_press_key(key, presses=presses)
        if not success:
            logger.error(f"press_key({key}) FAILED — SendInput returned 0")
        return f"Pressed: {key} ({presses}x)"

    def _hotkey(self, params: dict) -> str:
        keys = params.get("keys", [])
        
        if not self.enabled:
            return f"[headless] hotkey: {'+'.join(keys)}"
        
        lowered = [str(k).lower() for k in keys] if isinstance(keys, list) else []
        # Hangul/English IME toggle (Korean keyboard) — fall back to Alt+Shift
        if lowered == ["hangul"] or lowered == ["han_eng"] or lowered == ["ko_en"]:
            try:
                win32_press_key('hangul')
                return "Hotkey: hangul"
            except Exception:
                win32_hotkey('alt', 'shift')
                return "Hotkey: alt+shift (hangul fallback)"

        fg_title = _get_foreground_window_title()
        logger.info(f"hotkey({'+'.join([str(k) for k in keys])}) → foreground='{fg_title}'")

        # Re-assert foreground window focus before sending hotkey.
        # Between LLM decision and actual key dispatch (IPC round-trip), another window
        # may have grabbed focus. SetForegroundWindow re-pins the current fg window so
        # keys (especially Ctrl+S) go to the intended target.
        if sys.platform == "win32":
            try:
                import ctypes
                hwnd = ctypes.windll.user32.GetForegroundWindow()
                if hwnd:
                    ctypes.windll.user32.SetForegroundWindow(hwnd)
                    time.sleep(0.05)  # Let focus settle before sendinput
            except Exception as _fe:
                logger.debug(f"hotkey pre-focus failed: {_fe}")

        success = win32_hotkey(*keys)
        if not success:
            logger.error(f"hotkey({'+'.join([str(k) for k in keys])}) FAILED — SendInput returned 0")
        return f"Hotkey: {'+'.join([str(k) for k in keys])}"

    # === App Management ===

    def _open_app(self, params: dict) -> str:
        name = params.get("name", "")
        path = params.get("path", "")
        
        if path:
            # Direct path provided — use it
            if sys.platform == "win32":
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-a", path])
            else:
                subprocess.Popen([path])
            time.sleep(1)
            return f"Opened: {path}"
        
        if sys.platform == "win32":
            # Use smart app intelligence for Windows
            result = _smart_open_app(name)
            time.sleep(1.5)  # Give app time to start
            return result
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-a", name])
        else:
            subprocess.Popen([name])
        
        time.sleep(1)
        return f"Opened: {name}"

    def _close_app(self, params: dict) -> str:
        name = params.get("name", "")
        
        if not HAS_PSUTIL:
            return "psutil not available"
        
        killed = 0
        for proc in psutil.process_iter(['name']):
            try:
                proc_name = proc.info.get('name') or ''
                if proc_name and name.lower() in proc_name.lower():
                    proc.terminate()
                    killed += 1
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        
        return f"Closed {killed} processes matching '{name}'"

    def _screenshot_action(self, params: dict) -> str:
        return "Screenshot captured (use screenshot module)"

    def _wait(self, params: dict) -> str:
        seconds = params.get("seconds", 1)
        time.sleep(min(seconds, 30))  # Cap at 30s
        return f"Waited {seconds}s"

    def _get_window_list(self, params: dict) -> str:
        if not self.enabled:
            return "[]"
        
        try:
            windows = pyautogui.getAllWindows()
            # Filter out empty titles and provide more useful info
            window_info = []
            for w in windows:
                if w.title.strip():
                    window_info.append({
                        "title": w.title,
                        "visible": w.isActive or w.visible if hasattr(w, 'visible') else True,
                    })
            # Return sorted by title, limit to 30
            titles = [w["title"] for w in window_info[:30]]
            return str(titles)
        except Exception:
            return "Window list not available"

    def _focus_window(self, params: dict) -> str:
        title = params.get("title", "")
        
        if not self.enabled:
            return f"[headless] focus window: {title}"
        
        # Use smart window focusing with fuzzy matching
        return _smart_focus_window(title)

    def _run_command(self, params: dict) -> str:
        command = params.get("command", "")
        timeout = min(params.get("timeout", 30), 60)  # Increased default to 30s
        
        if not command:
            return "No command provided"
        
        # Safety: block dangerous commands
        dangerous = [
            "rm -rf /", "format c:", "del /s /q c:\\", "mkfs",
            ":(){" , "shutdown", "reboot", "rd /s /q c:\\",
        ]
        cmd_lower = command.lower()
        if any(d in cmd_lower for d in dangerous):
            return "Blocked: potentially dangerous command"
        
        # Sanitize: block shell metacharacters to prevent injection
        try:
            command = sanitize_command(command)
        except ValueError as e:
            return f"Blocked: {e}"
        
        try:
            if sys.platform == 'win32':
                # On Windows use cmd /c with split args (no shell=True)
                cmd_args = ['cmd', '/c'] + command.split()
            else:
                cmd_args = shlex.split(command)
            
            result = subprocess.run(
                cmd_args, capture_output=True, text=True,
                timeout=timeout, encoding="utf-8", errors="replace",
            )
            stdout = result.stdout.strip() if result.stdout else ""
            stderr = result.stderr.strip() if result.stderr else ""
            
            # Return more output (2000 chars instead of 500)
            output_parts = []
            if stdout:
                output_parts.append(f"STDOUT:\n{stdout[:2000]}")
            if stderr:
                output_parts.append(f"STDERR:\n{stderr[:1000]}")
            
            output = "\n".join(output_parts) if output_parts else "(no output)"
            
            return {
                "returncode": result.returncode,
                "stdout": stdout[:2000],
                "stderr": stderr[:1000],
                "output": output,
            }
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Command failed: {e}"

    # === Clipboard ===

    def _clipboard_copy(self, params: dict) -> str:
        text = params.get("text", "")
        
        if not self.enabled:
            return f"[headless] clipboard copy: {text[:50]}"
        
        try:
            import pyperclip
            pyperclip.copy(text)
            return "Copied to clipboard"
        except ImportError:
            return "pyperclip not installed – clipboard unavailable"

    def _clipboard_paste(self, params: dict) -> str:
        if not self.enabled:
            return "[headless] clipboard paste"
        
        fg_title = _get_foreground_window_title()
        logger.info(f"clipboard_paste: Ctrl+V → foreground='{fg_title}'")
        win32_hotkey("ctrl", "v")
        return "Pasted from clipboard"

    def _clipboard_get(self, params: dict) -> str:
        try:
            import pyperclip
            text = pyperclip.paste()
            return f"Clipboard: {text[:200]}"
        except Exception:
            return "Clipboard not available"

    # === Utilities ===

    def get_mouse_position(self) -> tuple[int, int]:
        if not self.enabled:
            return (0, 0)
        pos = pyautogui.position()
        return (pos[0], pos[1])

    def get_screen_size(self) -> tuple[int, int]:
        return (self.screen_width, self.screen_height)
