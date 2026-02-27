"""
Windows UI Automation Engine — Accurate UI element detection via accessibility API.

Uses the Windows UI Automation framework (via ctypes/comtypes) to enumerate
visible, interactive UI elements with 100% accurate bounding rectangles.

This replaces/supplements the heuristic edge-based SoM detection which misses
flat design buttons, text links, and small icons. UI Automation provides:
- Exact bounding rectangles for every UI element
- Element names, types, and states
- Works regardless of visual style (flat, gradient, textured)
- No false positives from edge detection noise

Falls back gracefully when UI Automation is unavailable (e.g., Linux, headless).
"""

import sys
import time
from dataclasses import dataclass
from typing import Optional
from loguru import logger

# Try importing pywinauto for Windows UI Automation
HAS_UIAUTOMATION = False
_uia_backend = None  # "pywinauto" or "ctypes"

try:
    if sys.platform == "win32":
        import ctypes
        import ctypes.wintypes
        HAS_UIAUTOMATION = True
        _uia_backend = "ctypes"
except ImportError:
    pass


@dataclass
class UIAElement:
    """A UI element discovered via Windows UI Automation."""
    name: str
    control_type: str   # Button, Edit, Text, Link, CheckBox, MenuItem, etc.
    x: int
    y: int
    w: int
    h: int
    cx: int             # center x
    cy: int             # center y
    is_enabled: bool = True
    is_offscreen: bool = False
    automation_id: str = ""
    class_name: str = ""


def _map_control_type_id(type_id: int) -> str:
    """Map UIA control type ID to human-readable type name."""
    _CONTROL_TYPES = {
        50000: "Button",
        50001: "Calendar",
        50002: "CheckBox",
        50003: "ComboBox",
        50004: "Edit",
        50005: "Hyperlink",
        50006: "Image",
        50007: "ListItem",
        50008: "List",
        50009: "Menu",
        50010: "MenuBar",
        50011: "MenuItem",
        50012: "ProgressBar",
        50013: "RadioButton",
        50014: "ScrollBar",
        50015: "Slider",
        50016: "Spinner",
        50017: "StatusBar",
        50018: "Tab",
        50019: "TabItem",
        50020: "Text",
        50021: "ToolBar",
        50022: "ToolTip",
        50023: "Tree",
        50024: "TreeItem",
        50025: "Custom",
        50026: "Group",
        50027: "Thumb",
        50028: "DataGrid",
        50029: "DataItem",
        50030: "Document",
        50031: "SplitButton",
        50032: "Window",
        50033: "Pane",
        50034: "Header",
        50035: "HeaderItem",
        50036: "Table",
        50037: "TitleBar",
        50038: "Separator",
    }
    return _CONTROL_TYPES.get(type_id, f"Control_{type_id}")


def _classify_som_type(control_type: str) -> str:
    """Convert Windows UIA control type to SoM element type for compatibility."""
    _TYPE_MAP = {
        "Button": "button",
        "SplitButton": "button",
        "MenuItem": "button",
        "Hyperlink": "button",
        "TabItem": "button",
        "ListItem": "button",
        "TreeItem": "button",
        "RadioButton": "button",
        "CheckBox": "button",
        "Edit": "input",
        "ComboBox": "input",
        "Spinner": "input",
        "Image": "icon",
        "Text": "region",
        "ToolBar": "region",
        "StatusBar": "region",
        "Menu": "region",
        "MenuBar": "region",
        "Pane": "region",
        "Group": "region",
        "Document": "region",
        "DataGrid": "region",
        "Table": "region",
        "List": "region",
        "Tree": "region",
        "Tab": "region",
        "Custom": "region",
    }
    return _TYPE_MAP.get(control_type, "region")


# Interactive control types we care about (buttons, inputs, links, etc.)
_INTERACTIVE_TYPES = {
    50000,  # Button
    50002,  # CheckBox
    50003,  # ComboBox
    50004,  # Edit
    50005,  # Hyperlink
    50007,  # ListItem
    50011,  # MenuItem
    50013,  # RadioButton
    50019,  # TabItem
    50024,  # TreeItem
    50025,  # Custom (may be interactive)
    50031,  # SplitButton
}


class UIAutomationEngine:
    """
    Windows UI Automation element detector.
    
    Enumerates interactive UI elements in the foreground window using
    the Windows UIA COM interface via ctypes. Returns elements compatible
    with SoMElement format.
    
    Performance target: <200ms for typical window.
    """

    def __init__(self, max_elements: int = 50, max_depth: int = 12):
        self.max_elements = max_elements
        self.max_depth = max_depth
        self.enabled = HAS_UIAUTOMATION and sys.platform == "win32"
        self._uia = None
        self._condition = None
        
        if self.enabled:
            try:
                self._init_uia()
            except Exception as e:
                logger.warning(f"UIAutomation init failed: {e}")
                self.enabled = False

    def _init_uia(self):
        """Initialize COM-based UI Automation."""
        import comtypes
        import comtypes.client as cc
        
        # CoInitialize for this thread
        try:
            comtypes.CoInitializeEx(comtypes.COINIT_MULTITHREADED)
        except OSError:
            pass  # Already initialized
        
        # Create IUIAutomation instance
        CLSID_CUIAutomation = comtypes.GUID("{FF48DBA4-60EF-4201-AA87-54103EEF594E}")
        IID_IUIAutomation = comtypes.GUID("{30CBE57D-D9D0-452A-AB13-7AC5AC4825EE}")
        
        self._uia = cc.CreateObject(CLSID_CUIAutomation, interface=None)
        # Get true condition for finding all elements
        self._condition = self._uia.CreateTrueCondition()
        logger.info("UIAutomation engine initialized (COM)")

    def detect_elements(
        self, screen_width: int = 1920, screen_height: int = 1080
    ) -> list[UIAElement]:
        """
        Detect interactive UI elements in the current foreground window.
        
        Returns a list of UIAElement with accurate bounding rectangles.
        Filters to only interactive, on-screen, enabled elements.
        """
        if not self.enabled:
            return []
        
        try:
            return self._detect_via_com(screen_width, screen_height)
        except Exception as e:
            logger.debug(f"UIAutomation COM detection failed: {e}")
            # Try fallback with ctypes direct approach
            try:
                return self._detect_via_ctypes(screen_width, screen_height)
            except Exception as e2:
                logger.debug(f"UIAutomation ctypes fallback failed: {e2}")
                return []

    def _detect_via_com(
        self, screen_width: int, screen_height: int
    ) -> list[UIAElement]:
        """Detect elements using comtypes COM interface."""
        if not self._uia:
            return []
        
        start_time = time.time()
        
        # Get foreground window element
        root = self._uia.GetFocusedElement()
        if not root:
            root = self._uia.GetRootElement()
        
        # Walk the tree to find interactive elements
        walker = self._uia.CreateTreeWalker(self._condition)
        elements: list[UIAElement] = []
        
        try:
            # Get the window that contains the focused element
            try:
                window = self._walk_to_window(root, walker)
                if window:
                    root = window
            except Exception:
                pass
            
            self._collect_elements(root, walker, elements, 0, screen_width, screen_height)
        except Exception as e:
            logger.debug(f"COM element collection failed: {e}")
        
        elapsed = time.time() - start_time
        logger.debug(f"UIAutomation detected {len(elements)} elements in {elapsed:.3f}s")
        
        return elements[:self.max_elements]

    def _walk_to_window(self, element, walker):
        """Walk up to find the parent window element."""
        try:
            parent = walker.GetParentElement(element)
            depth = 0
            while parent and depth < 5:
                try:
                    ct = parent.CurrentControlType
                    if ct == 50032:  # Window
                        return parent
                except Exception:
                    pass
                parent = walker.GetParentElement(parent)
                depth += 1
        except Exception:
            pass
        return element

    def _collect_elements(
        self, node, walker, elements: list[UIAElement],
        depth: int, screen_width: int, screen_height: int
    ):
        """Recursively collect interactive elements from the UIA tree."""
        if depth > self.max_depth or len(elements) >= self.max_elements:
            return
        
        try:
            child = walker.GetFirstChildElement(node)
        except Exception:
            return
        
        while child is not None and len(elements) < self.max_elements:
            try:
                ct = child.CurrentControlType
                
                # Get bounding rectangle
                try:
                    rect = child.CurrentBoundingRectangle
                    x = int(rect.left)
                    y = int(rect.top)
                    w = int(rect.right - rect.left)
                    h = int(rect.bottom - rect.top)
                except Exception:
                    x = y = w = h = 0
                
                # Filter: must be visible, on-screen, reasonable size
                if (w > 5 and h > 5 
                    and x >= -10 and y >= -10
                    and x < screen_width + 10 and y < screen_height + 10
                    and w < screen_width * 0.9 and h < screen_height * 0.9):
                    
                    # Only collect interactive elements
                    if ct in _INTERACTIVE_TYPES:
                        try:
                            name = child.CurrentName or ""
                        except Exception:
                            name = ""
                        
                        try:
                            is_enabled = bool(child.CurrentIsEnabled)
                        except Exception:
                            is_enabled = True
                        
                        try:
                            is_offscreen = bool(child.CurrentIsOffscreen)
                        except Exception:
                            is_offscreen = False
                        
                        try:
                            auto_id = child.CurrentAutomationId or ""
                        except Exception:
                            auto_id = ""
                        
                        try:
                            class_name = child.CurrentClassName or ""
                        except Exception:
                            class_name = ""
                        
                        if not is_offscreen and is_enabled:
                            control_type_str = _map_control_type_id(ct)
                            elements.append(UIAElement(
                                name=name[:80],
                                control_type=control_type_str,
                                x=max(0, x),
                                y=max(0, y),
                                w=w,
                                h=h,
                                cx=max(0, x) + w // 2,
                                cy=max(0, y) + h // 2,
                                is_enabled=is_enabled,
                                is_offscreen=is_offscreen,
                                automation_id=auto_id[:40],
                                class_name=class_name[:40],
                            ))
                
                # Recurse into children
                self._collect_elements(child, walker, elements, depth + 1, screen_width, screen_height)
                
            except Exception:
                pass
            
            try:
                child = walker.GetNextSiblingElement(child)
            except Exception:
                break

    def _detect_via_ctypes(
        self, screen_width: int, screen_height: int
    ) -> list[UIAElement]:
        """
        Fallback: Use ctypes to find window children with EnumChildWindows.
        Less accurate than COM but works without comtypes.
        """
        if sys.platform != "win32":
            return []
        
        import ctypes
        from ctypes import wintypes
        
        user32 = ctypes.windll.user32
        
        # Get foreground window
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return []
        
        elements: list[UIAElement] = []
        
        # Callback for EnumChildWindows
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        
        def enum_callback(child_hwnd, lparam):
            if len(elements) >= self.max_elements:
                return False
            
            # Check visibility
            if not user32.IsWindowVisible(child_hwnd):
                return True
            if not user32.IsWindowEnabled(child_hwnd):
                return True
            
            # Get rect
            rect = wintypes.RECT()
            if not user32.GetWindowRect(child_hwnd, ctypes.byref(rect)):
                return True
            
            x = rect.left
            y = rect.top
            w = rect.right - rect.left
            h = rect.bottom - rect.top
            
            if w < 5 or h < 5:
                return True
            if x >= screen_width or y >= screen_height:
                return True
            if w > screen_width * 0.9 or h > screen_height * 0.9:
                return True
            
            # Get window text
            buf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(child_hwnd, buf, 256)
            name = buf.value or ""
            
            # Get class name
            cls_buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(child_hwnd, cls_buf, 256)
            cls_name = cls_buf.value or ""
            
            # Classify by class name
            control_type = "Custom"
            cls_lower = cls_name.lower()
            if "button" in cls_lower or "btn" in cls_lower:
                control_type = "Button"
            elif "edit" in cls_lower or "text" in cls_lower:
                control_type = "Edit"
            elif "combo" in cls_lower:
                control_type = "ComboBox"
            elif "list" in cls_lower:
                control_type = "ListItem"
            elif "static" in cls_lower:
                control_type = "Text"
            elif "check" in cls_lower:
                control_type = "CheckBox"
            elif "radio" in cls_lower:
                control_type = "RadioButton"
            elif "tab" in cls_lower:
                control_type = "TabItem"
            elif "menu" in cls_lower:
                control_type = "MenuItem"
            elif "link" in cls_lower:
                control_type = "Hyperlink"
            
            # Skip non-interactive Text/Static
            if control_type == "Text":
                return True
            
            elements.append(UIAElement(
                name=name[:80],
                control_type=control_type,
                x=max(0, x),
                y=max(0, y),
                w=w,
                h=h,
                cx=max(0, x) + w // 2,
                cy=max(0, y) + h // 2,
                is_enabled=True,
                is_offscreen=False,
                automation_id="",
                class_name=cls_name[:40],
            ))
            return True
        
        try:
            cb = WNDENUMPROC(enum_callback)
            user32.EnumChildWindows(hwnd, cb, 0)
        except Exception:
            pass
        
        return elements[:self.max_elements]


def uia_elements_to_som_description(
    elements: list[UIAElement], screen_width: int = 1920, screen_height: int = 1080
) -> str:
    """Convert UI Automation elements to SoM-compatible text description."""
    if not elements:
        return ""
    
    def get_zone(cx: int, cy: int) -> str:
        h_zone = "left" if cx < screen_width * 0.33 else ("right" if cx > screen_width * 0.67 else "center")
        v_zone = "top" if cy < screen_height * 0.33 else ("bottom" if cy > screen_height * 0.67 else "middle")
        return f"{v_zone}-{h_zone}"
    
    TYPE_EMOJI = {
        "button": "🔘",
        "input": "📝",
        "icon": "🔷",
        "region": "📦",
    }
    
    parts = [f"[UIA] {len(elements)} interactive elements detected (Windows UI Automation):"]
    for i, el in enumerate(elements, start=1):
        som_type = _classify_som_type(el.control_type)
        emoji = TYPE_EMOJI.get(som_type, "📦")
        zone = get_zone(el.cx, el.cy)
        name_str = f" '{el.name}'" if el.name else ""
        parts.append(
            f"  [{i}] {emoji} {el.control_type:12s}{name_str} at ({el.cx:4d},{el.cy:4d}) "
            f"{el.w}x{el.h} zone={zone}"
        )
    
    parts.append("")
    parts.append("TIP: These elements have EXACT positions from Windows accessibility API.")
    return "\n".join(parts)
