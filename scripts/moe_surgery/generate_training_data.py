#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  Training Data Generator V3.0 for 4 New MoE Experts
  Generates production-quality training data in LLaMA
  conversation format for each expert's specialty domain.
═══════════════════════════════════════════════════════════════════

V3.0 Changes:
- Target 1500+ examples per expert (up from 500+)
- Added cross-expert chain scenarios (ground→verify, workflow→retry, etc.)
- Added hard/adversarial examples for Phase 4 hardening
- Expanded Korean language coverage
- Added multi-monitor, DPI-aware, dark mode scenarios
- Added negative examples (what NOT to do)

Each expert gets 1500+ training examples covering:
  Expert 16 — visual_grounding:    UI element identification, coordinate mapping,
                                   screenshot understanding, spatial reasoning
  Expert 17 — workflow_orchestrator: Multi-step task planning, cross-app workflows,
                                     process decomposition, sequencing
  Expert 18 — verification_oracle:  Action verification, state change detection,
                                    error identification, success confirmation
  Expert 19 — adaptive_retry:       Error recovery, alternative strategies,
                                    fallback planning, graceful degradation

Cross-expert scenarios (500+ examples):
  ground→verify:    Grounding identifies target → verification checks result
  workflow→verify:  Orchestrator runs step → verification confirms success
  ground→retry:     Grounding fails → retry generates alternative localization
  full_chain:       Ground → orchestrate → verify → retry if needed

Output: JSONL files with LLaMA conversation format:
  {"conversations": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]}
"""

import json
import os
import random
import argparse
from pathlib import Path
from typing import List, Dict


# ═══════════════════════════════════════════════════════════════
# SYSTEM PROMPTS (injected per expert during training)
# ═══════════════════════════════════════════════════════════════

SYSTEM_PROMPTS = {
    "visual_grounding": (
        "You are a visual grounding expert for computer operation. "
        "You specialize in identifying UI elements from screenshots, mapping pixel coordinates "
        "to interactive elements, understanding spatial layout of windows and controls, "
        "and precisely describing what is visible on screen. You reason about element types "
        "(buttons, text fields, menus, icons, links), their positions, sizes, and relationships. "
        "You provide exact coordinates (x, y) for click targets and describe visual states accurately."
    ),
    "workflow_orchestrator": (
        "You are a workflow orchestration expert for computer operation. "
        "You specialize in decomposing complex tasks into ordered step sequences, "
        "coordinating actions across multiple applications, managing task dependencies, "
        "and optimizing execution order. You plan which applications to open, in what order, "
        "what actions to perform in each, and how to transfer data between them. "
        "You think about prerequisites, parallel opportunities, and critical paths."
    ),
    "verification_oracle": (
        "You are a verification oracle expert for computer operation. "
        "You specialize in confirming whether actions were successfully completed, "
        "detecting state changes on screen, identifying error conditions, "
        "comparing expected vs actual outcomes, and providing confidence assessments. "
        "You check for visual indicators of success (checkmarks, confirmation dialogs, "
        "content changes) and failure (error messages, unchanged states, red indicators)."
    ),
    "adaptive_retry": (
        "You are an adaptive retry expert for computer operation. "
        "You specialize in recovering from failed actions, generating alternative approaches, "
        "diagnosing why previous attempts failed, and designing fallback strategies. "
        "You consider timeout issues, element not found errors, permission problems, "
        "network failures, and UI state mismatches. You suggest modified approaches "
        "that avoid the original failure mode."
    ),
}


# ═══════════════════════════════════════════════════════════════
# VISUAL GROUNDING — Expert 16 Training Data
# ═══════════════════════════════════════════════════════════════

def generate_visual_grounding_data() -> List[Dict]:
    """Generate 1500+ visual grounding training examples with dynamic reasoning.

    V4.0: Removed all hardcoded coordinates. Every example teaches the model to
    REASON about element positions based on layout conventions, window parameters,
    and visual context. Coordinates are dynamically computed with randomization.
    """
    examples = []

    # ─── Helpers for dynamic coordinate generation ───────────
    def rand_window(maximized=False):
        """Generate random window position and size. Returns (wx, wy, ww, wh, res_w, res_h)."""
        res_w, res_h = random.choice([(1920, 1080), (2560, 1440), (1366, 768), (1280, 720)])
        if maximized:
            return 0, 0, res_w, res_h, res_w, res_h
        ww = random.randint(800, res_w)
        wh = random.randint(500, res_h)
        wx = random.randint(0, max(0, res_w - ww))
        wy = random.randint(0, max(0, res_h - wh))
        return wx, wy, ww, wh, res_w, res_h

    SP = SYSTEM_PROMPTS["visual_grounding"]

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 1 — Visual Reasoning Methodology (teaches HOW)
    # ═══════════════════════════════════════════════════════════

    methodology_examples = [
        (
            "How should I approach finding a specific UI element in a screenshot?",
            "Visual element localization follows a systematic reasoning process:\n\n"
            "1. **Identify the application** — Recognize which app is shown (browser, editor, file manager, etc.)\n"
            "2. **Determine window boundaries** — Find the title bar to establish (x, y, width, height)\n"
            "3. **Apply layout conventions** — Each OS and app has predictable element placement:\n"
            "   - Windows: Close/Maximize/Minimize buttons at top-right\n"
            "   - macOS: Traffic lights (close/minimize/maximize) at top-left\n"
            "   - Menu bar: Below title bar, left-aligned\n"
            "   - Status bar: Bottom edge of window\n"
            "4. **Compute relative position** — Calculate element position from window origin + known offsets\n"
            "5. **Verify visual characteristics** — Check that the pixel area matches expected appearance\n\n"
            "Never memorize fixed coordinates — always compute them from the current window state."
        ),
        (
            "What information do I need to determine where a UI element is?",
            "To locate any UI element, you need these inputs:\n\n"
            "1. **Window position** (x, y) — where the window's top-left corner is on screen\n"
            "2. **Window dimensions** (width, height) — the window's size\n"
            "3. **Element type** — what kind of element (button, menu, input field, etc.)\n"
            "4. **Application identity** — which app, as each has different layouts\n"
            "5. **OS/platform** — Windows, macOS, Linux have different UI conventions\n"
            "6. **Display scaling** — DPI percentage affects logical vs physical coordinates\n"
            "7. **Window state** — maximized, windowed, or minimized affects position calculation\n\n"
            "With these inputs, you can COMPUTE the element's position rather than guessing."
        ),
        (
            "Why can't I just memorize where buttons are?",
            "Memorizing fixed coordinates fails because:\n\n"
            "1. **Window position varies** — users move windows around the screen\n"
            "2. **Window size varies** — users resize windows to different dimensions\n"
            "3. **Resolution differs** — 1080p vs 1440p vs 4K all have different pixel layouts\n"
            "4. **DPI scaling** — 100%, 125%, 150%, 200% scaling changes pixel positions\n"
            "5. **Theme/skin changes** — different themes may resize UI elements\n"
            "6. **Updates** — software updates can change UI layout\n"
            "7. **Multi-monitor** — elements on secondary monitors have offset coordinates\n\n"
            "Instead, learn the RULES governing element placement, then compute coordinates dynamically:\n"
            "element_position = window_origin + layout_offset(element_type, window_size)"
        ),
        (
            "What are the standard UI element positions in Windows applications?",
            "Windows UI layout conventions (relative to window origin):\n\n"
            "**Title Bar (height ~32px):**\n"
            "- App icon: (8, 8) relative to window\n"
            "- Title text: (~40, 8) or centered\n"
            "- Minimize button: (width - 138, 0), size ~46x32\n"
            "- Maximize button: (width - 92, 0), size ~46x32\n"
            "- Close button: (width - 46, 0), size ~46x32\n\n"
            "**Menu Bar (below title bar, height ~24px):**\n"
            "- First item (File): (~8, 32)\n"
            "- Items spaced by text width + ~20px padding\n\n"
            "**Toolbar (below menu, height ~36px):**\n"
            "- Starts at (~8, 56)\n\n"
            "**Status Bar (bottom edge, height ~24px):**\n"
            "- Starts at (0, height - 24)\n\n"
            "All positions are RELATIVE to the window's top-left corner."
        ),
        (
            "How do I compute absolute screen coordinates from relative positions?",
            "Formula: screen_position = window_origin + relative_offset\n\n"
            "Example calculation:\n"
            "- Window at screen position: (200, 100)\n"
            "- Window size: 1400x800\n"
            "- Target: Close button\n"
            "- Close button relative offset: (width - 23, 16) = (1377, 16)\n"
            "- Absolute screen position: (200 + 1377, 100 + 16) = (1577, 116)\n\n"
            "This works for ANY window position and size. The key insight: "
            "learn the RELATIVE offset rules, then compute absolute positions dynamically."
        ),
        (
            "How do I find scroll bars in any window?",
            "Scroll bars follow predictable placement rules:\n\n"
            "**Vertical scroll bar:**\n"
            "- Position: Right edge of the scrollable content area\n"
            "- X coordinate: window_x + content_width - scrollbar_width (~17px on Windows)\n"
            "- Y range: from content_top to content_bottom\n"
            "- Thumb position: proportional to scroll position in content\n\n"
            "**Horizontal scroll bar:**\n"
            "- Position: Bottom edge of the scrollable content area\n"
            "- Y coordinate: window_y + content_height - scrollbar_height (~17px)\n"
            "- X range: from content_left to content_right\n\n"
            "To find the scroll thumb:\n"
            "thumb_y = content_top + (scroll_pct * (content_height - thumb_height))"
        ),
        (
            "How do context menus work for coordinate targeting?",
            "Context menus appear at the cursor position, so their coordinates are dynamic:\n\n"
            "1. **Trigger position**: The right-click location determines menu origin\n"
            "2. **Menu position**: Usually appears at (click_x, click_y) or adjusted if near screen edges\n"
            "3. **Edge correction**: If menu would go off-screen, it flips direction\n"
            "   - Near right edge: menu opens to the left instead\n"
            "   - Near bottom edge: menu opens upward\n"
            "4. **Item positions**: Each item is ~24px tall, offset from menu top\n"
            "   - Item N center: (menu_x + menu_width/2, menu_y + 12 + (N-1) * 24)\n\n"
            "You MUST know where the context menu appeared to target its items."
        ),
        (
            "How do I reason about the position of toolbar icons?",
            "Toolbar icon positioning follows these rules:\n\n"
            "1. **Toolbar location**: Usually below the menu bar, ~56px from window top\n"
            "2. **Icon arrangement**: Left-to-right, with ~4px gaps between icons\n"
            "3. **Icon size**: Typically 24x24 or 32x32 pixels with padding\n"
            "4. **Separator groups**: Related icons are grouped with ~8px separator gaps\n"
            "5. **Right-aligned icons**: Some icons (settings, profile) are right-aligned\n\n"
            "To find icon N from the left:\n"
            "icon_x = toolbar_left + padding + N * (icon_size + gap)\n"
            "icon_y = toolbar_y + toolbar_height / 2\n\n"
            "Right-aligned icons: icon_x = window_right - padding - (N_from_right * (icon_size + gap))"
        ),
    ]

    for q, a in methodology_examples:
        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 2 — Dynamic Coordinate Computation (300 examples)
    # Randomly parametrized — teaches computation from context
    # ═══════════════════════════════════════════════════════════

    element_rules = {
        "close button": {
            "offset_fn": lambda w, h: (w - 23, 16),
            "size": (46, 32),
            "area": "top-right corner of the title bar",
            "visual": "an X icon, typically with a red hover background",
            "reasoning": "The close button is always at the rightmost position of the title bar controls",
        },
        "maximize button": {
            "offset_fn": lambda w, h: (w - 69, 16),
            "size": (46, 32),
            "area": "top-right area, left of the close button",
            "visual": "a square icon (□) or overlapping squares for restore",
            "reasoning": "The maximize button is the second button from the right in the title bar",
        },
        "minimize button": {
            "offset_fn": lambda w, h: (w - 115, 16),
            "size": (46, 32),
            "area": "top-right area, left of maximize",
            "visual": "a horizontal line icon (—)",
            "reasoning": "The minimize button is the third button from the right in the title bar",
        },
        "menu bar - File": {
            "offset_fn": lambda w, h: (20, 44),
            "size": (40, 24),
            "area": "left side of menu bar, below title bar",
            "visual": "text label 'File'",
            "reasoning": "The File menu is always the first item in the menu bar, left-aligned",
        },
        "menu bar - Edit": {
            "offset_fn": lambda w, h: (70, 44),
            "size": (40, 24),
            "area": "menu bar, right of File",
            "visual": "text label 'Edit'",
            "reasoning": "The Edit menu follows File with ~50px spacing",
        },
        "menu bar - View": {
            "offset_fn": lambda w, h: (120, 44),
            "size": (40, 24),
            "area": "menu bar, right of Edit",
            "visual": "text label 'View'",
            "reasoning": "The View menu follows Edit in the standard menu order",
        },
        "search bar": {
            "offset_fn": lambda w, h: (w // 2, 52),
            "size": (400, 28),
            "area": "center-top area, in the toolbar",
            "visual": "a text input field, often with a magnifying glass icon or placeholder text",
            "reasoning": "Search bars are typically centered horizontally in the toolbar area",
        },
        "address bar": {
            "offset_fn": lambda w, h: (w // 2, 44),
            "size": (800, 28),
            "area": "top center, spanning most of the toolbar width",
            "visual": "a wide text input showing URL or path",
            "reasoning": "In browsers, the address bar is centered and takes up ~60% of toolbar width",
        },
        "tab bar - first tab": {
            "offset_fn": lambda w, h: (100, 12),
            "size": (180, 28),
            "area": "top of the window, in the tab strip",
            "visual": "a tab shape with page title text",
            "reasoning": "The first tab starts ~100px from the left in the tab strip at the window top",
        },
        "vertical scrollbar": {
            "offset_fn": lambda w, h: (w - 9, h // 2),
            "size": (17, 300),
            "area": "right edge of the content area",
            "visual": "a thin vertical bar or track",
            "reasoning": "Vertical scrollbars are always at the rightmost edge of scrollable content",
        },
        "status bar": {
            "offset_fn": lambda w, h: (w // 2, h - 12),
            "size": (1200, 24),
            "area": "bottom edge of the window",
            "visual": "a bar showing status information, line numbers, encoding, etc.",
            "reasoning": "The status bar is always at the very bottom of the window",
        },
        "horizontal scrollbar": {
            "offset_fn": lambda w, h: (w // 2, h - 30),
            "size": (400, 17),
            "area": "bottom of content area, above status bar",
            "visual": "a thin horizontal bar or track",
            "reasoning": "Horizontal scrollbars appear just above the status bar",
        },
    }

    apps = [
        "Chrome", "Firefox", "Edge", "VS Code", "File Explorer",
        "Notepad++", "Excel", "Word", "PowerPoint", "Outlook",
        "Teams", "Discord", "Slack", "Terminal", "Paint",
    ]

    for _ in range(500):
        app = random.choice(apps)
        elem_name = random.choice(list(element_rules.keys()))
        rule = element_rules[elem_name]
        is_maximized = random.random() < 0.4

        wx, wy, ww, wh, rw, rh = rand_window(maximized=is_maximized)
        rel_x, rel_y = rule["offset_fn"](ww, wh)
        abs_x, abs_y = wx + rel_x, wy + rel_y
        btn_w, btn_h = rule["size"]

        window_state = "maximized" if is_maximized else f"positioned at ({wx}, {wy}) with size {ww}x{wh}"

        q_templates = [
            f"The {app} window is {window_state} on a {rw}x{rh} display. Where is the {elem_name}?",
            f"I need to click the {elem_name} in {app}. The window is {window_state}. Screen resolution: {rw}x{rh}.",
            f"Find the {elem_name} in a {app} window that is {window_state}.",
            f"On a {rw}x{rh} screen, {app} is {window_state}. Where should I click for the {elem_name}?",
        ]

        response = (
            f"Step-by-step coordinate computation for the {elem_name} in {app}:\n\n"
            f"1. **Window state**: {'Maximized — fills entire ' + f'{rw}x{rh}' + ' screen, origin at (0, 0)' if is_maximized else f'Positioned at ({wx}, {wy}), size {ww}x{wh}'}\n"
            f"2. **Element rule**: {rule['reasoning']}\n"
            f"3. **Relative offset**: The {elem_name} is in the {rule['area']}\n"
            f"   - Relative to window: ({rel_x}, {rel_y})\n"
            f"4. **Absolute position**: ({wx} + {rel_x}, {wy} + {rel_y}) = ({abs_x}, {abs_y})\n"
            f"5. **Element size**: approximately {btn_w}x{btn_h} pixels\n"
            f"6. **Visual check**: Look for {rule['visual']} at this position\n\n"
            f"**Click target: ({abs_x}, {abs_y})**"
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": random.choice(q_templates)},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 3 — Relative Position Reasoning (150 examples)
    # ═══════════════════════════════════════════════════════════

    relative_pairs = [
        ("File menu", "Edit menu", "right", 50, 0, "Menu items are arranged horizontally left-to-right"),
        ("Edit menu", "View menu", "right", 50, 0, "View follows Edit in the standard menu order"),
        ("address bar", "reload button", "left", -30, 0, "Reload is to the left of the address bar"),
        ("address bar", "bookmark star", "right", 10, 0, "Bookmark icon is at the right end of the address bar"),
        ("tab title", "close tab button", "right", 75, 0, "Each tab has a close X at its right edge"),
        ("search result 1", "search result 2", "below", 0, 30, "Search results are stacked vertically ~30px apart"),
        ("toolbar", "content area", "above", 0, -40, "Content area is directly below the toolbar"),
        ("sidebar", "main content", "left", -200, 0, "Sidebar is to the left of main content"),
        ("OK button", "Cancel button", "left", -100, 0, "OK is typically to the left of Cancel in Windows dialogs"),
        ("scroll up arrow", "scroll down arrow", "above", 0, -300, "Scroll arrows are at top and bottom of scrollbar"),
        ("minimize button", "maximize button", "left", -46, 0, "Window control buttons are spaced 46px apart"),
        ("maximize button", "close button", "left", -46, 0, "Close button is 46px right of maximize"),
    ]

    for _ in range(200):
        ref_elem, target_elem, direction, dx, dy, reason = random.choice(relative_pairs)
        wx, wy, ww, wh, rw, rh = rand_window()

        ref_x = random.randint(wx + 50, wx + ww - 100)
        ref_y = random.randint(wy + 30, wy + wh - 50)
        target_x = ref_x + dx + random.randint(-5, 5)
        target_y = ref_y + dy + random.randint(-5, 5)

        q_templates = [
            f"I can see the {ref_elem} at ({ref_x}, {ref_y}). Where is the {target_elem}?",
            f"The {ref_elem} is located at ({ref_x}, {ref_y}). Find the {target_elem} relative to it.",
            f"Given {ref_elem} at ({ref_x}, {ref_y}), compute the {target_elem} position.",
        ]

        response = (
            f"Reasoning from the known reference point:\n\n"
            f"1. **Reference**: {ref_elem} is at ({ref_x}, {ref_y})\n"
            f"2. **Spatial rule**: {reason}\n"
            f"3. **Direction**: {target_elem} is to the {direction} of {ref_elem}\n"
            f"4. **Offset**: approximately ({dx:+d}, {dy:+d}) pixels from reference\n"
            f"5. **Computed position**: ({ref_x} + ({dx}), {ref_y} + ({dy})) ≈ ({target_x}, {target_y})\n\n"
            f"**Target: ({target_x}, {target_y})**"
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": random.choice(q_templates)},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 4 — App-Specific Layout Knowledge (200+ examples)
    # ═══════════════════════════════════════════════════════════

    app_layouts = {
        "Chrome": {
            "tab bar": ("top strip", lambda w, h: (random.randint(80, 400), 14), "Tabs at very top of window in the tab strip"),
            "new tab button (+)": ("right of last tab", lambda w, h: (random.randint(200, 500), 14), "Plus icon (+) after the last tab in the tab strip"),
            "address bar (omnibox)": ("center of toolbar", lambda w, h: (w // 2, 52), "Wide input field centered in toolbar, spanning ~60% of window width"),
            "back button (←)": ("left side of toolbar", lambda w, h: (36, 52), "Left arrow, leftmost toolbar button"),
            "forward button (→)": ("left toolbar, after back", lambda w, h: (66, 52), "Right arrow, second toolbar button"),
            "reload button (↻)": ("left toolbar, after forward", lambda w, h: (96, 52), "Circular arrow icon, third toolbar button"),
            "bookmark star": ("right end of address bar", lambda w, h: (int(w * 0.82), 52), "Star icon at right edge of the omnibox"),
            "three-dot menu (⋮)": ("top-right", lambda w, h: (w - 40, 52), "Three vertical dots, rightmost toolbar icon"),
            "bookmark bar": ("below toolbar", lambda w, h: (200, 82), "Horizontal bar with bookmark links, if enabled"),
        },
        "VS Code": {
            "activity bar": ("left edge", lambda w, h: (24, h // 2), "Vertical icon bar at far left with Explorer/Search/Git/Debug icons"),
            "file explorer panel": ("left side", lambda w, h: (150, h // 2), "File tree panel ~250px wide, right of activity bar"),
            "editor tab": ("top of editor area", lambda w, h: (random.randint(300, 600), 36), "Tab in editor tab bar showing filename"),
            "editor content": ("center", lambda w, h: (w // 2, h // 2), "Main text editing area — the largest region"),
            "minimap": ("right edge of editor", lambda w, h: (w - 60, h // 2 - 50), "Miniature code preview on right side of editor"),
            "terminal panel": ("bottom", lambda w, h: (w // 2, h - 100), "Integrated terminal at bottom of window"),
            "status bar": ("bottom edge", lambda w, h: (w // 2, h - 12), "Blue/purple bar at very bottom with branch, encoding, language"),
            "command palette": ("center top", lambda w, h: (w // 2, 80), "Overlay input box at top center, opened with Ctrl+Shift+P"),
        },
        "File Explorer": {
            "navigation pane": ("left side", lambda w, h: (120, h // 2), "Tree view with Quick Access, This PC, Network"),
            "address/path bar": ("top center", lambda w, h: (w // 2, 42), "Shows current folder path at top of window"),
            "search box": ("top right", lambda w, h: (w - 120, 42), "Search input field in top-right area"),
            "file/folder list": ("center right", lambda w, h: (w * 2 // 3, h // 2), "Main content area showing files and folders"),
            "ribbon/toolbar": ("top below title bar", lambda w, h: (w // 2, 80), "Home/Share/View tabs with action buttons"),
            "back button": ("top left", lambda w, h: (36, 42), "Left arrow for navigation history"),
            "up button": ("top left, after back/fwd", lambda w, h: (80, 42), "Up arrow to go to parent folder"),
        },
        "Excel": {
            "ribbon tabs": ("top area", lambda w, h: (w // 2, 44), "Home/Insert/Layout/Formulas/Data/Review tabs"),
            "formula bar": ("below ribbon", lambda w, h: (w // 2, 110), "Shows cell formula, with Name Box on left"),
            "name box": ("left of formula bar", lambda w, h: (50, 110), "Shows selected cell address like 'A1'"),
            "cell grid": ("center", lambda w, h: (w // 2, h // 2), "Main spreadsheet grid area"),
            "sheet tabs": ("bottom left", lambda w, h: (200, h - 38), "Sheet1/Sheet2 tabs at bottom-left"),
            "column header": ("top of grid", lambda w, h: (w // 2, 134), "A, B, C, D… letters above columns"),
            "row header": ("left of grid", lambda w, h: (20, h // 2), "1, 2, 3… numbers on left side of rows"),
        },
        "Word": {
            "ribbon tabs": ("top area", lambda w, h: (w // 2, 44), "Home/Insert/Design/Layout/References tabs"),
            "document area": ("center", lambda w, h: (w // 2, h // 2), "Main text editing region (white page)"),
            "ruler": ("above document", lambda w, h: (w // 2, 130), "Horizontal ruler showing margins and indents"),
            "page number": ("bottom center", lambda w, h: (w // 2, h - 36), "Page N of M in the status bar"),
            "zoom slider": ("bottom right", lambda w, h: (w - 100, h - 12), "Zoom percentage slider at bottom-right of status bar"),
        },
        "Discord": {
            "server list": ("far left", lambda w, h: (36, h // 2), "Vertical column of circular server icons at far left"),
            "channel list": ("left sidebar", lambda w, h: (160, h // 2), "Channel names under server name, ~240px panel"),
            "message area": ("center", lambda w, h: (w // 2, h // 2), "Main chat message area"),
            "message input": ("bottom center", lambda w, h: (w // 2, h - 50), "Text input box at the bottom of the message area"),
            "member list": ("right side", lambda w, h: (w - 120, h // 2), "Online/offline member list on right sidebar"),
            "user settings": ("bottom left", lambda w, h: (160, h - 20), "Gear icon next to username at bottom-left"),
        },
    }

    for app_name, elements in app_layouts.items():
        for elem_name, (area_desc, pos_fn, detail) in elements.items():
            for _ in range(random.randint(4, 6)):
                is_max = random.random() < 0.4
                wx, wy, ww, wh, rw, rh = rand_window(maximized=is_max)
                local_x, local_y = pos_fn(ww, wh)
                abs_x, abs_y = wx + local_x, wy + local_y
                win_desc = f"maximized on {rw}x{rh}" if is_max else f"at ({wx}, {wy}), size {ww}x{wh}, on {rw}x{rh}"

                q_variants = [
                    f"Where is the {elem_name} in {app_name}? Window is {win_desc}.",
                    f"I need to click the {elem_name} in {app_name} ({win_desc}). Coordinates?",
                    f"Locate the {elem_name} in {app_name}. Window: {win_desc}.",
                    f"In {app_name} ({win_desc}), find the {elem_name}.",
                ]

                response = (
                    f"**{elem_name}** in {app_name}:\n\n"
                    f"1. Window: {'Maximized, full ' + f'{rw}x{rh}' + ' screen' if is_max else f'Origin ({wx}, {wy}), dimensions {ww}×{wh}'}\n"
                    f"2. Layout rule: {detail}\n"
                    f"3. Located in: {area_desc}\n"
                    f"4. Relative position: ({local_x}, {local_y}) from window origin\n"
                    f"5. Absolute position: ({abs_x}, {abs_y})\n\n"
                    f"**Click target: ({abs_x}, {abs_y})**"
                )

                examples.append({
                    "conversations": [
                        {"role": "system", "content": SP},
                        {"role": "user", "content": random.choice(q_variants)},
                        {"role": "assistant", "content": response},
                    ]
                })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 5 — Multi-Step Scene Analysis (100+ examples)
    # ═══════════════════════════════════════════════════════════

    scene_templates = [
        {
            "app": "Chrome",
            "description": "Chrome is open with 3 tabs. The window is {win_desc}. The active tab shows a Google search page.",
            "questions": [
                ("Where is the third tab?", lambda wx, wy, ww, wh: (
                    f"Tab positions in Chrome:\n"
                    f"- Tabs start at ~x=80 from window left, each ~180px wide\n"
                    f"- Tab strip at y=14 from window top\n"
                    f"- Tab 1: x={wx+80}, Tab 2: x={wx+260}, Tab 3: x={wx+440}\n"
                    f"- All at y={wy+14}\n\n"
                    f"**Third tab center: ({wx+530}, {wy+14})**"
                )),
                ("Where is the Google search box?", lambda wx, wy, ww, wh: (
                    f"On the Google search page:\n"
                    f"- Search box is centered horizontally in the content area\n"
                    f"- Vertically ~45% from top of viewport\n"
                    f"- Content area starts below toolbar (~y=82 from window top)\n"
                    f"- Search box center: ({wx + ww//2}, {wy + 82 + int((wh-82)*0.45)})\n\n"
                    f"**Search box: ({wx + ww//2}, {wy + 82 + int((wh-82)*0.45)})**"
                )),
            ],
        },
        {
            "app": "VS Code",
            "description": "VS Code is open with file explorer visible on the left. A Python file is open in the editor. The terminal is visible at the bottom. Window is {win_desc}.",
            "questions": [
                ("Where is the Run button (play triangle)?", lambda wx, wy, ww, wh: (
                    f"The Run button in VS Code:\n"
                    f"- Located in the editor title bar, top-right of editor area\n"
                    f"- File explorer is ~250px wide, editor starts at x≈{wx+250}\n"
                    f"- Run button at approximately: ({wx + ww - 60}, {wy + 36})\n\n"
                    f"**Run button: ({wx + ww - 60}, {wy + 36})**"
                )),
                ("Where is the terminal input cursor?", lambda wx, wy, ww, wh: (
                    f"Integrated terminal in VS Code:\n"
                    f"- Terminal panel occupies bottom ~30% of window\n"
                    f"- Terminal starts at x≈{wx+250} (right of sidebar)\n"
                    f"- Cursor at last line of terminal output\n"
                    f"- Estimated: ({wx + 280}, {wy + int(wh * 0.92)})\n\n"
                    f"**Terminal cursor: ({wx + 280}, {wy + int(wh * 0.92)})**"
                )),
            ],
        },
        {
            "app": "File Explorer",
            "description": "File Explorer showing Documents folder. Navigation pane on the left. View: Details. Window is {win_desc}.",
            "questions": [
                ("Where is the third file in the list?", lambda wx, wy, ww, wh: (
                    f"In Details view:\n"
                    f"- Navigation pane is ~200px wide\n"
                    f"- File list starts at x≈{wx+210}, column headers at y≈{wy+130}\n"
                    f"- Each row is ~24px tall\n"
                    f"- Third file row: y = {wy+130} + 3×24 = {wy+202}\n"
                    f"- Name column center: x≈{wx+360}\n\n"
                    f"**Third file: ({wx+360}, {wy+202})**"
                )),
                ("Where is the 'Name' column header to sort?", lambda wx, wy, ww, wh: (
                    f"Column headers in Details view:\n"
                    f"- Just above file list, 'Name' is first (widest) column\n"
                    f"- Position: ({wx + 310}, {wy + 130})\n\n"
                    f"**Name column header: ({wx+310}, {wy+130})**"
                )),
            ],
        },
        {
            "app": "Excel",
            "description": "Excel has a workbook open with data in columns A-F. The ribbon is visible. Window is {win_desc}.",
            "questions": [
                ("Where is cell C5?", lambda wx, wy, ww, wh: (
                    f"Cell positioning in Excel:\n"
                    f"- Grid starts at ~x=50 (after row headers), y≈{wy+134} (below column headers)\n"
                    f"- Default column width ≈ 64px, row height ≈ 20px\n"
                    f"- Column C = 3rd column → x = {wx+50} + 2×64 = {wx+178}\n"
                    f"- Row 5 = 5th row → y = {wy+134} + 4×20 = {wy+214}\n\n"
                    f"**Cell C5 center: ({wx+178+32}, {wy+214+10}) = ({wx+210}, {wy+224})**"
                )),
                ("Where is the SUM button in the ribbon?", lambda wx, wy, ww, wh: (
                    f"SUM (AutoSum Σ) in Excel ribbon:\n"
                    f"- Located in the Home tab, Editing group (right side of ribbon)\n"
                    f"- Ribbon is at y≈{wy+70}\n"
                    f"- Editing group is near right end of ribbon: x≈{wx+ww-150}\n\n"
                    f"**AutoSum button: ({wx+ww-150}, {wy+70})**"
                )),
            ],
        },
    ]

    for template in scene_templates:
        for _ in range(12):
            is_max = random.random() < 0.4
            wx, wy, ww, wh, rw, rh = rand_window(maximized=is_max)
            win_desc = f"maximized on {rw}x{rh}" if is_max else f"at ({wx}, {wy}), size {ww}x{wh}"
            scene_desc = template["description"].format(win_desc=win_desc)

            for q_text, answer_fn in template["questions"]:
                examples.append({
                    "conversations": [
                        {"role": "system", "content": SP},
                        {"role": "user", "content": f"{scene_desc}\n\n{q_text}"},
                        {"role": "assistant", "content": answer_fn(wx, wy, ww, wh)},
                    ]
                })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 6 — Resolution & DPI Reasoning (80 examples)
    # ═══════════════════════════════════════════════════════════

    dpi_scales = [
        (100, 1.0, "default (100%)"),
        (125, 1.25, "125%"),
        (150, 1.5, "150%"),
        (175, 1.75, "175%"),
        (200, 2.0, "200% (common on 4K)"),
    ]
    resolutions = [
        (1920, 1080, "Full HD"), (2560, 1440, "QHD"), (3840, 2160, "4K UHD"),
        (1366, 768, "HD"), (1280, 720, "720p"),
    ]

    for _ in range(100):
        res_w, res_h, res_name = random.choice(resolutions)
        dpi_pct, dpi_scale, dpi_desc = random.choice(dpi_scales)
        logical_w, logical_h = int(res_w / dpi_scale), int(res_h / dpi_scale)

        app = random.choice(apps)
        elem = random.choice(["close button", "search bar", "address bar", "menu bar - File"])
        rule = element_rules[elem]

        if random.random() < 0.4 or logical_w < 650 or logical_h < 450:
            lwx, lwy, lww, lwh = 0, 0, logical_w, logical_h
            win_state = "maximized"
        else:
            lww = random.randint(600, max(600, logical_w))
            lwh = random.randint(400, max(400, logical_h))
            lwx = random.randint(0, max(0, logical_w - lww))
            lwy = random.randint(0, max(0, logical_h - lwh))
            win_state = f"positioned at ({lwx}, {lwy}), size {lww}x{lwh}"

        local_x, local_y = rule["offset_fn"](lww, lwh)
        logical_x, logical_y = lwx + local_x, lwy + local_y
        physical_x, physical_y = int(logical_x * dpi_scale), int(logical_y * dpi_scale)

        user_q = (
            f"My display is {res_w}x{res_h} ({res_name}) with {dpi_desc} DPI scaling. "
            f"{app} is {win_state}. Where is the {elem}?"
        )
        response = (
            f"DPI-aware coordinate computation:\n\n"
            f"1. **Physical resolution**: {res_w}×{res_h} ({res_name})\n"
            f"2. **DPI scaling**: {dpi_desc} → logical resolution = {logical_w}×{logical_h}\n"
            f"3. **Window** ({win_state}): logical size {lww}×{lwh}\n"
            f"4. **{elem}** relative offset: ({local_x}, {local_y})\n"
            f"5. **Logical coordinates**: ({logical_x}, {logical_y})\n"
            f"6. **Physical pixels**: ({logical_x}×{dpi_scale}, {logical_y}×{dpi_scale}) = ({physical_x}, {physical_y})\n\n"
            f"**Use logical coordinates for automation tools: ({logical_x}, {logical_y})**\n"
            f"**Physical pixel position: ({physical_x}, {physical_y})**\n\n"
            f"Most OS APIs work in logical (DPI-aware) coordinates."
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 7 — Multi-Monitor & Complex Layouts (50 examples)
    # ═══════════════════════════════════════════════════════════

    monitor_configs = [
        ("dual horizontal", [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]),
        ("dual horizontal (mixed res)", [(0, 0, 2560, 1440), (2560, 0, 1920, 1080)]),
        ("dual vertical", [(0, 0, 1920, 1080), (0, 1080, 1920, 1080)]),
        ("triple horizontal", [(0, 0, 1920, 1080), (1920, 0, 1920, 1080), (3840, 0, 1920, 1080)]),
        ("ultrawide", [(0, 0, 3440, 1440)]),
        ("ultrawide + side", [(0, 0, 3440, 1440), (3440, 0, 1920, 1080)]),
    ]

    for _ in range(70):
        config_name, monitors = random.choice(monitor_configs)
        monitor_idx = random.randint(0, len(monitors) - 1)
        mx, my, mw, mh = monitors[monitor_idx]

        app = random.choice(apps)
        elem = random.choice(["close button", "maximize button", "minimize button", "search bar", "status bar"])
        rule = element_rules[elem]

        ww = random.randint(800, mw)
        wh = random.randint(500, mh)
        wx = mx + random.randint(0, max(0, mw - ww))
        wy = my + random.randint(0, max(0, mh - wh))

        local_x, local_y = rule["offset_fn"](ww, wh)
        abs_x, abs_y = wx + local_x, wy + local_y

        user_q = (
            f"Setup: {config_name} monitors. {app} is on monitor {monitor_idx+1} "
            f"({mw}x{mh}, origin {mx},{my}), window at ({wx}, {wy}), size {ww}x{wh}. "
            f"Where is the {elem}?"
        )
        response = (
            f"Multi-monitor coordinate computation:\n\n"
            f"1. **Monitor layout**: {config_name}\n"
            + "".join(f"   - Monitor {i+1}: {mw_}x{mh_} at ({mx_}, {my_})\n" for i, (mx_, my_, mw_, mh_) in enumerate(monitors))
            + f"2. **Target monitor**: #{monitor_idx+1}, origin ({mx}, {my})\n"
            f"3. **Window**: ({wx}, {wy}), size {ww}×{wh}\n"
            f"4. **{elem}** offset: ({local_x}, {local_y}) from window origin\n"
            f"5. **Absolute desktop coords**: ({wx}+{local_x}, {wy}+{local_y}) = ({abs_x}, {abs_y})\n\n"
            f"**Click target: ({abs_x}, {abs_y})** (desktop coordinate space)\n"
            f"Monitor {monitor_idx+1} x-range: {mx}–{mx+mw}, y-range: {my}–{my+mh}."
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 8 — Theme, Visual State & Occlusion (40 examples)
    # ═══════════════════════════════════════════════════════════

    theme_reasoning = [
        (
            "In dark mode Chrome, how do I identify the address bar?",
            "In dark mode Chrome, the address bar has a dark gray background (#35363A) with light text. "
            "Its POSITION doesn't change — still centered in the toolbar area.\n"
            "Compute exactly the same way: window_x + window_width/2, window_y + ~52px.\n"
            "Visual difference: look for a slightly lighter gray input field against the darker toolbar."
        ),
        (
            "How do I find buttons in Windows high-contrast mode?",
            "In high-contrast mode, buttons have bright borders (yellow #FFFF00 or white #FFFFFF) "
            "against black backgrounds. Their POSITIONS remain identical to standard mode — only "
            "visual appearance changes. Use the same coordinate computation rules. The enhanced "
            "borders actually make elements EASIER to locate."
        ),
        (
            "How do I distinguish active vs inactive tabs in dark mode?",
            "Active tab: lighter background (#1E1E1E vs #2D2D2D), may have colored top border "
            "(blue #007ACC in VS Code), full-opacity text.\n"
            "Inactive tab: darker background, ~70% opacity text.\n\n"
            "TAB POSITIONS are identical regardless of theme. Each tab ~180px wide, "
            "starting from x=80 from window left. Only visual appearance differs."
        ),
        (
            "In macOS, where are the window control buttons?",
            "macOS uses 'traffic light' buttons at the TOP-LEFT (opposite of Windows):\n"
            "- Close (red): window_x + 14, window_y + 14\n"
            "- Minimize (yellow): window_x + 34, window_y + 14\n"
            "- Maximize/Fullscreen (green): window_x + 54, window_y + 14\n"
            "- Each button: ~14px diameter\n\n"
            "This is the OPPOSITE side compared to Windows. Always identify the OS first."
        ),
        (
            "How do elements move when a sidebar is toggled?",
            "When a sidebar opens (e.g., 250px wide):\n"
            "- Main content shifts RIGHT by sidebar width\n"
            "- Content width DECREASES by sidebar width\n"
            "- new_content_x = old_content_x + sidebar_width\n\n"
            "When sidebar closes: content expands LEFT to fill space.\n"
            "Title bar buttons (close, minimize, maximize) are NOT affected by sidebar state."
        ),
        (
            "A dialog box appeared. How do I find its buttons?",
            "Dialogs are centered on their parent window by default:\n"
            "dialog_x = parent_x + (parent_w - dialog_w) / 2\n"
            "dialog_y = parent_y + (parent_h - dialog_h) / 2\n\n"
            "Dialog buttons are at bottom-right:\n"
            "OK: (dialog_x + dialog_w - 180, dialog_y + dialog_h - 40)\n"
            "Cancel: (dialog_x + dialog_w - 85, dialog_y + dialog_h - 40)\n\n"
            "Modal dialogs block interaction with the parent window."
        ),
        (
            "A notification toast overlaps a button. What do I do?",
            "Toast notifications:\n"
            "1. Appear at bottom-right or top-right of screen\n"
            "2. Auto-dismiss after 3–5 seconds\n"
            "3. Have close button at toast_x + width - 20, toast_y + 12\n\n"
            "Options: wait for auto-dismiss, or click toast's close button.\n"
            "After dismissal, the underlying button coordinates are UNCHANGED."
        ),
        (
            "A dropdown menu is open. How do I find a specific item?",
            "Dropdown menu item positions:\n"
            "1. Menu origin: at the trigger element position\n"
            "2. Drops DOWN, left-aligned with trigger\n"
            "3. Each item ~32px tall\n"
            "4. Item N: (menu_x + padding, menu_y + N × 32 + padding)\n"
            "5. Separators add ~8px to vertical offset\n\n"
            "width: ~200–300px. Click center of item text."
        ),
    ]

    for q, a in theme_reasoning:
        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ]
        })

    # Dynamic dialog examples
    for _ in range(50):
        wx, wy, ww, wh, rw, rh = rand_window()
        app = random.choice(apps)
        dialog_w = random.randint(350, 550)
        dialog_h = random.randint(180, 350)
        dialog_x = wx + (ww - dialog_w) // 2
        dialog_y = wy + (wh - dialog_h) // 2
        ok_x, ok_y = dialog_x + dialog_w - 175, dialog_y + dialog_h - 38
        cancel_x, cancel_y = dialog_x + dialog_w - 85, dialog_y + dialog_h - 38

        user_q = (
            f"A save dialog ({dialog_w}x{dialog_h}) appeared in {app}. "
            f"Main window at ({wx}, {wy}), size {ww}x{wh}. Where are OK and Cancel?"
        )
        response = (
            f"Dialog button computation:\n\n"
            f"1. **Parent window**: ({wx}, {wy}), {ww}×{wh}\n"
            f"2. **Dialog**: {dialog_w}×{dialog_h}, centered on parent\n"
            f"3. **Dialog position**: ({dialog_x}, {dialog_y})\n"
            f"4. **OK**: bottom-right area → ({ok_x}, {ok_y})\n"
            f"5. **Cancel**: right of OK → ({cancel_x}, {cancel_y})\n\n"
            f"**OK: ({ok_x}, {ok_y}) | Cancel: ({cancel_x}, {cancel_y})**"
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 9 — Web App Element Reasoning (30 examples)
    # ═══════════════════════════════════════════════════════════

    webapp_reasoning = [
        (
            "In a React web app, how do I locate a Material UI button?",
            "Material UI buttons can be found by:\n"
            "1. Visual: Rounded corners (4px), elevation shadow, ripple on hover\n"
            "2. DevTools (F12): search for class 'MuiButton-root'\n"
            "3. Programmatic: element.getBoundingClientRect() → {x, y, width, height}\n"
            "4. Coordinates are CSS pixels (logical), not physical\n"
            "Add browser chrome offset (~82px toolbar) for screen-level coordinates."
        ),
        (
            "How do I find a submit button in a web form?",
            "Web form submit buttons:\n"
            "1. Typically at BOTTOM of the form\n"
            "2. LTR layouts: primary (Submit) right, secondary (Cancel) left\n"
            "3. DevTools: document.querySelector('button[type=\"submit\"]')\n"
            "4. getBoundingClientRect() gives viewport-relative {x, y, w, h}\n"
            "5. Screen coords: add window position + browser toolbar offset\n\n"
            "Button center = (rect.x + rect.width/2, rect.y + rect.height/2) in viewport."
        ),
        (
            "How do I handle infinite scroll lists?",
            "Infinite scroll changes element availability:\n"
            "1. Visible elements: standard coord computation works\n"
            "2. Off-screen: must scroll first, then re-locate\n"
            "3. Scroll step: viewport_height × 0.8 per step\n"
            "4. After scrolling: ALL visible element positions CHANGE\n"
            "5. Always re-calculate after any scroll action\n\n"
            "Key: scrolling invalidates all previous coordinate calculations."
        ),
    ]

    for q, a in webapp_reasoning:
        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 10 — Korean Language Coverage (120+ examples)
    # ═══════════════════════════════════════════════════════════

    korean_method = [
        (
            "스크린샷에서 UI 요소를 찾으려면 어떻게 해야 하나요?",
            "UI 요소 위치를 찾는 체계적인 방법:\n\n"
            "1. **앱 식별** — 어떤 프로그램인지 확인\n"
            "2. **창 경계 파악** — 타이틀바를 찾아 (x, y, 너비, 높이) 확인\n"
            "3. **레이아웃 규칙 적용** — OS/앱마다 예측 가능한 배치 패턴:\n"
            "   - Windows: 닫기/최대화/최소화 → 오른쪽 상단\n"
            "   - macOS: 신호등 → 왼쪽 상단\n"
            "   - 메뉴바: 타이틀바 아래, 왼쪽 정렬\n"
            "   - 상태바: 창 하단\n"
            "4. **상대 좌표 계산** — 창 원점 + 오프셋으로 위치 계산\n"
            "5. **시각적 확인** — 해당 픽셀이 예상 모양과 일치하는지 검증\n\n"
            "절대 좌표를 외우지 마세요 — 항상 현재 창 상태에서 계산하세요."
        ),
        (
            "좌표를 하드코딩하면 안 되는 이유가 뭔가요?",
            "하드코딩 좌표가 실패하는 이유:\n\n"
            "1. 창 위치/크기가 항상 변동됨\n"
            "2. 해상도 차이 (1080p vs 4K)\n"
            "3. DPI 스케일링 (100%~200%)\n"
            "4. 테마/스킨/업데이트 변경\n"
            "5. 멀티 모니터 오프셋\n\n"
            "대신 배치 규칙을 배우고 동적 계산:\n"
            "요소_위치 = 창_원점 + 레이아웃_오프셋(요소_유형, 창_크기)"
        ),
        (
            "Windows에서 표준 UI 요소 위치 규칙이 뭔가요?",
            "Windows UI 레이아웃 규칙 (창 원점 기준 상대 좌표):\n\n"
            "**타이틀바 (높이 ~32px):**\n"
            "- 최소화: (너비 - 138, 0), 크기 46×32\n"
            "- 최대화: (너비 - 92, 0), 크기 46×32\n"
            "- 닫기: (너비 - 46, 0), 크기 46×32\n\n"
            "**메뉴바 (타이틀바 아래, 높이 ~24px):**\n"
            "- 파일(File): (~8, 32)\n"
            "- 항목 간격: 텍스트 너비 + ~20px\n\n"
            "**상태바 (하단, 높이 ~24px):**\n"
            "- 위치: (0, 높이 - 24)\n\n"
            "모든 좌표는 창의 왼쪽 상단 기준 상대값입니다."
        ),
        (
            "절대 좌표를 상대 좌표에서 어떻게 계산하나요?",
            "공식: 화면_좌표 = 창_원점 + 상대_오프셋\n\n"
            "예시:\n"
            "- 창 위치: (200, 100), 크기: 1400×800\n"
            "- 대상: 닫기 버튼\n"
            "- 상대 오프셋: (너비 - 23, 16) = (1377, 16)\n"
            "- 절대 좌표: (200+1377, 100+16) = (1577, 116)\n\n"
            "이 방식은 어떤 창 위치/크기에서도 정확하게 작동합니다."
        ),
    ]

    for q, a in korean_method:
        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ]
        })

    # Korean dynamic coordinate examples
    korean_apps = [
        ("크롬", "Chrome"), ("파일 탐색기", "File Explorer"),
        ("VS Code", "VS Code"), ("엑셀", "Excel"),
        ("팀즈", "Teams"), ("메모장", "Notepad"),
        ("디스코드", "Discord"), ("워드", "Word"),
    ]
    korean_elements = [
        ("닫기 버튼", "close button"), ("최소화 버튼", "minimize button"),
        ("최대화 버튼", "maximize button"), ("주소창", "address bar"),
        ("검색창", "search bar"), ("파일 메뉴", "menu bar - File"),
        ("상태바", "status bar"), ("스크롤바", "vertical scrollbar"),
    ]

    for _ in range(100):
        kr_app, en_app = random.choice(korean_apps)
        kr_elem, en_elem = random.choice(korean_elements)
        rule = element_rules.get(en_elem, element_rules["close button"])

        is_max = random.random() < 0.4
        wx, wy, ww, wh, rw, rh = rand_window(maximized=is_max)
        local_x, local_y = rule["offset_fn"](ww, wh)
        abs_x, abs_y = wx + local_x, wy + local_y
        win_kr = f"전체화면 ({rw}x{rh})" if is_max else f"위치 ({wx}, {wy}), 크기 {ww}x{wh}"

        user_q = f"{kr_app} 창이 {win_kr}일 때, {kr_elem}의 위치는?"
        response = (
            f"**{kr_elem}** ({kr_app}) 좌표 계산:\n\n"
            f"1. **창 상태**: {win_kr}\n"
            f"2. **배치 규칙**: {rule['reasoning']}\n"
            f"3. **상대 좌표**: 창 원점에서 ({local_x}, {local_y})\n"
            f"4. **절대 좌표**: ({wx}+{local_x}, {wy}+{local_y}) = ({abs_x}, {abs_y})\n\n"
            f"**클릭 대상: ({abs_x}, {abs_y})**"
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": response},
            ]
        })

    # Korean scene + DPI examples
    for _ in range(20):
        res_w, res_h = random.choice([(1920, 1080), (2560, 1440), (3840, 2160)])
        dpi_pct = random.choice([100, 125, 150, 200])
        dpi_scale = dpi_pct / 100.0
        logical_w, logical_h = int(res_w / dpi_scale), int(res_h / dpi_scale)
        kr_app, en_app = random.choice(korean_apps)
        kr_elem, en_elem = random.choice(korean_elements)
        rule = element_rules.get(en_elem, element_rules["close button"])

        lww, lwh = random.randint(600, max(600, logical_w)), random.randint(400, max(400, logical_h))
        lwx = random.randint(0, max(0, logical_w - lww))
        lwy = random.randint(0, max(0, logical_h - lwh))
        local_x, local_y = rule["offset_fn"](lww, lwh)
        log_x, log_y = lwx + local_x, lwy + local_y
        phys_x, phys_y = int(log_x * dpi_scale), int(log_y * dpi_scale)

        user_q = f"디스플레이 {res_w}x{res_h}, DPI {dpi_pct}%. {kr_app}이 ({lwx},{lwy}) 크기 {lww}x{lwh}. {kr_elem} 위치?"
        response = (
            f"DPI 고려 좌표 계산:\n\n"
            f"1. 물리 해상도: {res_w}×{res_h}\n"
            f"2. DPI {dpi_pct}% → 논리 해상도: {logical_w}×{logical_h}\n"
            f"3. {kr_elem} 상대 오프셋: ({local_x}, {local_y})\n"
            f"4. 논리 좌표: ({log_x}, {log_y})\n"
            f"5. 물리 좌표: ({phys_x}, {phys_y})\n\n"
            f"**자동화 도구용 (논리): ({log_x}, {log_y})**"
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 11 — Negative Examples: What NOT to do (50+ examples)
    # ═══════════════════════════════════════════════════════════

    negatives_static = [
        (
            "The close button in Chrome is at (1875, 12). Click there.",
            "⚠️ I cannot blindly click at (1875, 12) — that coordinate assumes:\n"
            "- Window is maximized on 1920×1080\n"
            "- Window origin at (0, 0)\n"
            "- DPI scaling 100%\n\n"
            "If ANY assumption is wrong, the click misses.\n\n"
            "**Correct approach**: Determine the window's actual position and size, then compute:\n"
            "close_x = window_x + window_width - 23\n"
            "close_y = window_y + 16\n\n"
            "Please provide the window's current state."
        ),
        (
            "Just click at (500, 500), that's where the button usually is.",
            "⚠️ 'Usually' is unreliable for coordinate targeting:\n"
            "1. Window position can be anywhere\n"
            "2. Window size affects element positions\n"
            "3. App state (sidebars, menus) shifts content\n\n"
            "**Instead**: Tell me which button in which app, with current window state, "
            "and I'll compute exact coordinates."
        ),
        (
            "I saved the coordinates from last time. Can I reuse them?",
            "⚠️ Reusing saved coordinates is unreliable:\n"
            "1. Window may have moved/resized\n"
            "2. Display scaling might differ\n"
            "3. App updates may change layout\n"
            "4. Different monitor configuration\n\n"
            "**Always recompute** from current state. Fast and accurate:\n"
            "element_pos = window_origin + known_offset(element_type)"
        ),
        (
            "저번에 닫기 버튼이 (1875, 12)였으니까 그냥 거기를 클릭해.",
            "⚠️ 이전 좌표 재사용 금지:\n"
            "- 창 위치/크기가 바뀌었을 수 있음\n"
            "- DPI 배율이 다를 수 있음\n"
            "- 앱 업데이트로 레이아웃이 변경됐을 수 있음\n\n"
            "**올바른 방법**: 현재 창 상태 확인 후 계산:\n"
            "닫기_x = 창_x + 창_너비 - 23\n"
            "닫기_y = 창_y + 16\n\n"
            "현재 창 정보를 알려주세요."
        ),
    ]

    for q, a in negatives_static:
        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": q},
                {"role": "assistant", "content": a},
            ]
        })

    # Dynamic negative examples
    for _ in range(50):
        wx, wy, ww, wh, rw, rh = rand_window()
        elem = random.choice(list(element_rules.keys()))
        rule = element_rules[elem]

        wrong_x, wrong_y = random.randint(0, rw), random.randint(0, rh)
        local_x, local_y = rule["offset_fn"](ww, wh)
        correct_x, correct_y = wx + local_x, wy + local_y

        user_q = f"Click the {elem} at ({wrong_x}, {wrong_y})."
        response = (
            f"⚠️ Cannot verify ({wrong_x}, {wrong_y}) without current window state.\n\n"
            f"If window is at ({wx}, {wy}), size {ww}×{wh}:\n"
            f"- Correct {elem}: ({correct_x}, {correct_y})\n"
            f"- Your coords: {'MATCH ✓' if (wrong_x, wrong_y) == (correct_x, correct_y) else f'OFF by ({abs(wrong_x-correct_x)}, {abs(wrong_y-correct_y)}) pixels ✗'}\n\n"
            f"**Always compute**: {elem}_x = window_x + {local_x}, {elem}_y = window_y + {local_y}"
        )

        examples.append({
            "conversations": [
                {"role": "system", "content": SP},
                {"role": "user", "content": user_q},
                {"role": "assistant", "content": response},
            ]
        })

    # ═══════════════════════════════════════════════════════════
    # CATEGORY 12 — Multi-Turn Visual Grounding (60 examples)
    # ═══════════════════════════════════════════════════════════

    for _ in range(80):
        app = random.choice(apps)
        wx, wy, ww, wh, rw, rh = rand_window()
        chosen_elems = random.sample(list(element_rules.keys()), min(3, len(element_rules)))

        turns = [
            {"role": "system", "content": SP},
            {"role": "user", "content": (
                f"{app} is open at ({wx}, {wy}), size {ww}x{wh} on {rw}x{rh}. "
                f"I need to find several elements."
            )},
            {"role": "assistant", "content": (
                f"I'll help locate elements in {app}. Window origin ({wx}, {wy}), "
                f"dimensions {ww}×{wh}. What element do you need first?"
            )},
        ]

        for elem_name in chosen_elems:
            rule = element_rules[elem_name]
            local_x, local_y = rule["offset_fn"](ww, wh)
            abs_x, abs_y = wx + local_x, wy + local_y

            turns.append({"role": "user", "content": f"Where is the {elem_name}?"})
            turns.append({"role": "assistant", "content": (
                f"**{elem_name}**: {rule['reasoning']}. "
                f"Offset ({local_x}, {local_y}) → Absolute ({abs_x}, {abs_y}). "
                f"Look for {rule['visual']}."
            )})

        examples.append({"conversations": turns})

    return examples


# ═══════════════════════════════════════════════════════════════

def generate_workflow_orchestrator_data() -> List[Dict]:
    """Generate 500+ training examples for workflow orchestration expert."""
    examples = []
    
    # ─── Category 1: Multi-step task plans (150 examples) ───
    task_plans = [
        {
            "task": "Research a topic online and write a summary report in a text file",
            "steps": [
                "1. Open Chrome browser (Win+R → 'chrome' → Enter, or click Chrome icon on taskbar)",
                "2. Navigate to Google (Ctrl+L → type 'google.com' → Enter)",
                "3. Search for the topic (type search query → Enter)",
                "4. Open first 3 relevant results in new tabs (Ctrl+Click on each link)",
                "5. Read and extract key information from each source",
                "6. Open Notepad (Win+R → 'notepad' → Enter)",
                "7. Write the report with structured headings and citations",
                "8. Save the file (Ctrl+S → navigate to desired folder → name file → Save)",
                "9. Verify the file was saved by checking in Explorer",
            ],
            "dependencies": "Steps 1-5 must complete before step 6. Steps 6-8 are sequential.",
            "estimated_time": "10-15 minutes",
            "critical_path": "Web research (steps 2-5) is the bottleneck",
        },
        {
            "task": "Create a Python script that processes CSV data and generates a chart",
            "steps": [
                "1. Open PowerShell or Command Prompt (Win+R → 'cmd' → Enter)",
                "2. Navigate to project directory (cd C:\\Projects\\data-analysis)",
                "3. Create Python script file (type > analysis.py or use Notepad)",
                "4. Write import statements (pandas, matplotlib)",
                "5. Write data loading code (pd.read_csv)",
                "6. Write data processing logic (filtering, grouping, calculations)",
                "7. Write chart generation code (plt.figure, plt.bar/plot, plt.savefig)",
                "8. Save script (Ctrl+S)",
                "9. Install missing packages if needed (pip install pandas matplotlib)",
                "10. Run script (python analysis.py)",
                "11. Check for errors in output",
                "12. If errors: read error message → fix code → re-run",
                "13. Verify output chart file exists and looks correct",
            ],
            "dependencies": "Step 9 can run anytime before step 10. Steps 3-8 are sequential code writing.",
            "estimated_time": "15-25 minutes",
            "critical_path": "Code writing and debugging (steps 3-12)",
        },
        {
            "task": "Set up a new project folder with README, .gitignore, and initial code",
            "steps": [
                "1. Open PowerShell (Win+X → Windows Terminal or Win+R → 'powershell')",
                "2. Navigate to workspace (cd C:\\Projects)",
                "3. Create project directory (mkdir my-project)",
                "4. Enter directory (cd my-project)",
                "5. Initialize git repository (git init)",
                "6. Create README.md with project description using echo/Notepad",
                "7. Create .gitignore with common patterns (node_modules/, __pycache__/, .env)",
                "8. Create initial source directory structure (mkdir src, mkdir tests)",
                "9. Create initial code file (src/main.py or src/index.js)",
                "10. Stage all files (git add .)",
                "11. Make initial commit (git commit -m 'Initial project setup')",
                "12. Verify with git log and git status",
            ],
            "dependencies": "Step 5 must come after step 4. Steps 6-9 can be done in any order.",
            "estimated_time": "5-10 minutes",
            "critical_path": "All sequential, but steps 6-9 are parallelizable",
        },
        {
            "task": "Download an image from the web and edit it in Paint",
            "steps": [
                "1. Open Chrome browser",
                "2. Navigate to the image source URL or search Google Images",
                "3. Find the target image",
                "4. Right-click on the image → 'Save image as...'",
                "5. Choose Downloads folder → Save",
                "6. Open Paint (Win+R → 'mspaint' → Enter)",
                "7. Open the downloaded image (File → Open → navigate to Downloads → select file)",
                "8. Perform edits (resize, crop, add text, draw)",
                "9. Save the edited image (File → Save As → choose format → Save)",
                "10. Verify the edited image in Explorer or Photos app",
            ],
            "dependencies": "Steps 1-5 must complete before step 7. Step 6 can run parallel to steps 1-5.",
            "estimated_time": "5-10 minutes",
            "critical_path": "Image download (steps 2-5)",
        },
        {
            "task": "Compare two text files and find the differences",
            "steps": [
                "1. Open PowerShell",
                "2. Navigate to the directory containing both files",
                "3. Option A: Use fc command (fc file1.txt file2.txt)",
                "4. Option B: Use PowerShell Compare-Object (Compare-Object (Get-Content file1.txt) (Get-Content file2.txt))",
                "5. Review the differences in the output",
                "6. If visual comparison needed: open both files in Notepad (side by side)",
                "7. Use Win+Left and Win+Right to snap windows side by side",
                "8. Manually review differences line by line",
                "9. Document differences in a new file if needed",
            ],
            "dependencies": "Steps 3 and 4 are alternatives (pick one). Steps 6-8 are optional visual approach.",
            "estimated_time": "3-5 minutes",
            "critical_path": "The comparison itself is fast; review takes the most time",
        },
    ]
    
    for plan in task_plans:
        steps_text = "\n".join(plan["steps"])
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": f"Plan the workflow for: {plan['task']}"},
                {"role": "assistant", "content": (
                    f"## Workflow Plan: {plan['task']}\n\n"
                    f"### Steps:\n{steps_text}\n\n"
                    f"### Dependencies:\n{plan['dependencies']}\n\n"
                    f"### Estimated Time: {plan['estimated_time']}\n"
                    f"### Critical Path: {plan['critical_path']}\n\n"
                    f"### Error Handling:\n"
                    f"- If any step fails, diagnose the error before proceeding\n"
                    f"- Keep a mental model of current state at each step\n"
                    f"- Verify each step's completion before moving to the next"
                )},
            ]
        })
    
    # ─── Category 2: Cross-application workflows (100 examples) ───
    cross_app_workflows = [
        ("Copy data from a webpage into Excel",
         ["Chrome → navigate to data source", "Select table data on webpage (Ctrl+A or manual select)", 
          "Copy to clipboard (Ctrl+C)", "Open Excel (Win+R → 'excel')", 
          "Click cell A1", "Paste data (Ctrl+V)", "Format columns as needed",
          "Save workbook (Ctrl+S → name → Save)"]),
        ("Take a screenshot of an error message and email it to support",
         ["Capture screenshot (Win+Shift+S → select area)", "Open email client or webmail in Chrome",
          "Compose new email", "Add recipient address", "Write subject: 'Error Report'",
          "Paste screenshot in email body (Ctrl+V)", "Add text description of the error",
          "Click Send"]),
        ("Read a PDF document and create summary notes in Notepad",
         ["Open PDF in Chrome or default PDF viewer", "Read through document sections",
          "Open Notepad (Win+R → 'notepad')", "Snap windows side by side (Win+Left/Right)",
          "For each section: read in PDF → type summary in Notepad",
          "Format notes with headings and bullet points",
          "Save notes file (Ctrl+S)"]),
        ("Install a Python package and verify it works",
         ["Open PowerShell or Command Prompt", "Check Python version (python --version)",
          "Install package (pip install package_name)", "Verify installation (pip show package_name)",
          "Test with Python (python -c 'import package; print(package.__version__)')",
          "If import error: check virtual environment, retry with correct pip"]),
        ("Create a backup of important files to a USB drive",
         ["Open Windows Explorer (Win+E)", "Navigate to source folder with files",
          "Verify USB drive is connected (check This PC for drive letter)",
          "Select files to backup (Ctrl+Click for individual, Ctrl+A for all)",
          "Copy files (Ctrl+C)", "Navigate to USB drive",
          "Create backup folder with date (New Folder → name 'backup_2026-02-14')",
          "Paste files (Ctrl+V)", "Wait for copy to complete",
          "Verify files on USB (check sizes, open a few to confirm integrity)"]),
    ]
    
    for task_desc, steps in cross_app_workflows:
        steps_text = "\n".join(f"  {i+1}. {s}" for i, s in enumerate(steps))
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": f"How do I {task_desc}?"},
                {"role": "assistant", "content": (
                    f"## Cross-Application Workflow\n\n"
                    f"**Task:** {task_desc}\n\n"
                    f"**Step-by-step plan:**\n{steps_text}\n\n"
                    f"**Applications involved:** {', '.join(set(s.split(' → ')[0].split('(')[0].strip() for s in steps if '→' in s or '(' in s))}\n\n"
                    f"**Key transitions:** When switching between applications, ensure the previous "
                    f"app's action is complete (e.g., data is fully copied before pasting in the next app). "
                    f"Use Alt+Tab to switch quickly between windows."
                )},
            ]
        })
    
    # Bulk generate task decomposition examples
    complex_tasks = [
        "Build a personal website using HTML and CSS",
        "Organize all photos in Downloads by date into folders",
        "Debug a JavaScript application that shows a blank page",
        "Create a PowerPoint presentation about quarterly results",
        "Set up SSH keys and connect to a remote server",
        "Clean up disk space by finding and removing large files",
        "Configure Windows Defender firewall rules for a specific app",
        "Create a database backup and verify its integrity",
        "Write unit tests for an existing Python module",
        "Set up a local development environment for a Node.js project",
        "Monitor system resources while running a heavy process",
        "Convert multiple images from PNG to JPEG format using batch processing",
        "Set up automated file synchronization between two folders",
        "Create a scheduled task to run a script every hour",
        "Extract text from multiple PDF files and combine into one document",
    ]
    
    # Detailed plans for each complex task (NOT generic templates)
    complex_task_plans = {
        "Build a personal website using HTML and CSS": (
            "1. Create project folder: `mkdir my-website && cd my-website`\n"
            "2. Create `index.html` with HTML5 boilerplate (`<!DOCTYPE html>`, head, body)\n"
            "3. Create `styles/main.css` and link it in head (`<link rel=\"stylesheet\">`)\n"
            "4. Structure HTML: header(nav), main(hero, about, contact), footer\n"
            "5. Style layout: CSS Grid/Flexbox for responsive design\n"
            "6. Add media queries for mobile (`@media (max-width: 768px)`)\n"
            "7. Test in Chrome DevTools responsive mode (Ctrl+Shift+M)\n"
            "8. Deploy: `npx serve .` for local preview, or push to GitHub Pages"
        ),
        "Organize all photos in Downloads by date into folders": (
            "1. Open PowerShell in Downloads folder\n"
            "2. Scan: `Get-ChildItem *.jpg,*.png,*.heic | Group-Object {$_.CreationTime.ToString('yyyy-MM')}`\n"
            "3. Dry run: display what would be moved without actually moving\n"
            "4. Create year-month folders: `foreach ($g in $groups) { New-Item -ItemType Directory $g.Name -Force }`\n"
            "5. Move files: `foreach ($f in $g.Group) { Move-Item $f.FullName \"$($g.Name)\\\" }`\n"
            "6. Handle duplicates: append `-1`, `-2` suffix to collisions\n"
            "7. Verify: `Get-ChildItem -Recurse | Measure-Object` — total should match original count\n"
            "8. Delete empty subfolders if any: `Get-ChildItem -Directory -Recurse | Where {!(Get-ChildItem $_)} | Remove-Item`"
        ),
        "Debug a JavaScript application that shows a blank page": (
            "1. Open Chrome DevTools (F12) → Console tab — check for red error messages\n"
            "2. Check Network tab: are JS/CSS files loading? Look for 404s on script/link tags\n"
            "3. If errors: read the error message, note file and line number\n"
            "4. Check Elements tab: is the DOM empty or does it have content?\n"
            "   - Empty DOM → JS not executing or crashing before render\n"
            "   - Content present but invisible → CSS issue (display:none, z-index, opacity)\n"
            "5. Add `console.log('app start')` at entry point to confirm JS loads\n"
            "6. Use breakpoints (Sources tab → click line number) to step through render logic\n"
            "7. Check for async issues: API calls returning errors, missing `await`\n"
            "8. Verify build output: `npm run build` — check for compile warnings"
        ),
        "Create a PowerPoint presentation about quarterly results": (
            "1. Open PowerPoint → choose clean template (e.g., 'Facet' or blank)\n"
            "2. Title slide: 'Q4 2025 Results' + subtitle with team/date\n"
            "3. Agenda slide: bullet list of 4-5 sections to cover\n"
            "4. Data slides: Insert → Chart → select type (bar/line for trends)\n"
            "   - Right-click chart → 'Edit Data' → paste numbers from Excel\n"
            "5. Key metrics slide: use SmartArt for KPIs (revenue, growth, targets)\n"
            "6. Comparison slide: table with Q3 vs Q4, highlight improvements in green\n"
            "7. Summary slide: 3 key takeaways as bold bullet points\n"
            "8. Save as .pptx (Ctrl+S), export PDF copy (File → Export → Create PDF)"
        ),
        "Set up SSH keys and connect to a remote server": (
            "1. Generate key: `ssh-keygen -t ed25519 -C \"your@email.com\"` → accept defaults\n"
            "2. Start agent: `eval $(ssh-agent -s)` or on Windows: `Get-Service ssh-agent | Set-Service -StartupType Automatic`\n"
            "3. Add key: `ssh-add ~/.ssh/id_ed25519`\n"
            "4. Copy public key: `cat ~/.ssh/id_ed25519.pub` → clipboard\n"
            "5. On server: append to `~/.ssh/authorized_keys` (or use `ssh-copy-id user@host`)\n"
            "6. Test: `ssh user@host` — should connect WITHOUT password prompt\n"
            "7. Add to SSH config (`~/.ssh/config`) for shortcut:\n"
            "   `Host myserver\\n  HostName 192.168.1.100\\n  User deploy\\n  IdentityFile ~/.ssh/id_ed25519`\n"
            "8. Now: `ssh myserver` connects directly"
        ),
        "Clean up disk space by finding and removing large files": (
            "1. Overview: `Get-PSDrive C | Select Used,Free` — see current usage\n"
            "2. Find largest files: `Get-ChildItem C:\\ -Recurse -File | Sort Length -Desc | Select -First 20 FullName,@{N='GB';E={$_.Length/1GB}}`\n"
            "3. Quick wins: `Disk Cleanup` (cleanmgr.exe) → check 'Previous Windows installations', 'Temp files'\n"
            "4. Check Downloads: `Get-ChildItem $HOME\\Downloads | Sort Length -Desc | Select -First 10`\n"
            "5. Docker cleanup (if installed): `docker system prune -a` → can free 10-50 GB\n"
            "6. npm/yarn cache: `npm cache clean --force` or `yarn cache clean`\n"
            "7. Check Recycle Bin: right-click → 'Empty Recycle Bin'\n"
            "8. WinSxS cleanup: `Dism.exe /online /Cleanup-Image /StartComponentCleanup`"
        ),
        "Configure Windows Defender firewall rules for a specific app": (
            "1. Open Windows Defender Firewall with Advanced Security (`wf.msc`)\n"
            "2. Click 'Inbound Rules' → 'New Rule...' → select 'Program'\n"
            "3. Browse to program path (e.g., `C:\\Program Files\\MyApp\\app.exe`)\n"
            "4. Choose action: Allow or Block the connection\n"
            "5. Select profiles: Domain, Private, Public (uncheck Public for security)\n"
            "6. Name the rule descriptively: 'Allow MyApp - Inbound TCP'\n"
            "7. For specific ports: create 'Port' rule instead, specify TCP/UDP and port number\n"
            "8. Verify: `Get-NetFirewallRule -DisplayName '*MyApp*' | Format-List` in PowerShell\n"
            "9. Test: try the connection — if blocked, check Windows Event Viewer → Security log"
        ),
        "Create a database backup and verify its integrity": (
            "1. PostgreSQL: `pg_dump -U postgres -d mydb -F c -f backup_$(date +%Y%m%d).dump`\n"
            "   Or MySQL: `mysqldump -u root -p mydb > backup.sql`\n"
            "2. Verify file created: `ls -la backup*` — check size is > 0, reasonable MB\n"
            "3. Integrity check (PostgreSQL): `pg_restore --list backup.dump` — should list tables without errors\n"
            "4. Test restore to temp database:\n"
            "   `createdb mydb_test && pg_restore -d mydb_test backup.dump`\n"
            "5. Spot-check data: `psql mydb_test -c 'SELECT count(*) FROM users'` — compare with production\n"
            "6. Drop test db: `dropdb mydb_test`\n"
            "7. Move backup to safe location (cloud storage, secondary drive)\n"
            "8. Schedule regular backups via cron or Task Scheduler"
        ),
        "Write unit tests for an existing Python module": (
            "1. Examine the module: read function signatures, identify inputs/outputs\n"
            "2. Create test file: `tests/test_<module>.py`\n"
            "3. Import: `from src.<module> import <functions>` + `import pytest`\n"
            "4. Write happy-path tests: typical inputs → expected outputs\n"
            "5. Write edge cases: empty input, None, very large values, boundary conditions\n"
            "6. Write error cases: `with pytest.raises(ValueError):` for invalid inputs\n"
            "7. Add fixtures (`@pytest.fixture`) for shared test setup (db connections, temp files)\n"
            "8. Run: `pytest tests/test_<module>.py -v` → all should pass\n"
            "9. Check coverage: `pytest --cov=src/<module> --cov-report=term-missing`"
        ),
        "Set up a local development environment for a Node.js project": (
            "1. Install Node.js: `winget install OpenJS.NodeJS.LTS` (or download from nodejs.org)\n"
            "2. Verify: `node -v && npm -v`\n"
            "3. Clone project: `git clone <repo-url> && cd <project>`\n"
            "4. Install deps: `npm install` (reads package.json, creates node_modules/)\n"
            "5. Copy env template: `cp .env.example .env` → fill in values (API keys, DB URL)\n"
            "6. Start dev server: `npm run dev` → should show 'listening on port 3000'\n"
            "7. Open browser: `http://localhost:3000` → verify app loads\n"
            "8. Install VS Code extensions: ESLint, Prettier, Thunder Client (for API testing)\n"
            "9. Test: `npm test` → verify existing tests pass in your environment"
        ),
        "Monitor system resources while running a heavy process": (
            "1. Open Task Manager (Ctrl+Shift+Esc) → Performance tab for real-time graphs\n"
            "2. For detailed monitoring: `resmon.exe` (Resource Monitor) → CPU, Memory, Disk, Network tabs\n"
            "3. PowerShell monitoring:\n"
            "   `while ($true) { Get-Process | Sort CPU -Desc | Select -First 5 Name,CPU,WS; Start-Sleep 2; cls }`\n"
            "4. Start the heavy process in a separate terminal\n"
            "5. Watch for: CPU > 95% sustained, Memory > 90%, Disk 100% (I/O bottleneck)\n"
            "6. If memory pressure: check for memory leaks (growing RSS over time)\n"
            "7. Log to file: `typeperf '\\Processor(_Total)\\% Processor Time' -o perf.csv -si 1`\n"
            "8. After completion: review perf.csv for anomalies (spikes, sustained plateaus)"
        ),
        "Convert multiple images from PNG to JPEG format using batch processing": (
            "1. Open PowerShell in the images folder\n"
            "2. Using built-in .NET:\n"
            "   ```powershell\n"
            "   Add-Type -AssemblyName System.Drawing\n"
            "   Get-ChildItem *.png | ForEach-Object {\n"
            "     $img = [System.Drawing.Image]::FromFile($_.FullName)\n"
            "     $jpg = $_.FullName -replace '\\.png$','.jpg'\n"
            "     $img.Save($jpg, [System.Drawing.Imaging.ImageFormat]::Jpeg)\n"
            "     $img.Dispose()\n"
            "   }\n"
            "   ```\n"
            "3. Or using ImageMagick: `magick mogrify -format jpg *.png`\n"
            "4. Verify: `Get-ChildItem *.jpg | Measure-Object` — count should match PNG count\n"
            "5. Compare file sizes: JPEGs should be smaller (typically 30-70% of PNG)\n"
            "6. Spot-check quality: open a few JPEGs to verify no corruption\n"
            "7. Optionally delete originals: `Remove-Item *.png` (only after verification)"
        ),
        "Set up automated file synchronization between two folders": (
            "1. Choose tool: robocopy (built-in) or rsync (WSL/Linux)\n"
            "2. Test command: `robocopy C:\\Source D:\\Backup /MIR /L` (/L = list only, don't copy)\n"
            "3. Review what WOULD change — /MIR deletes extra files in destination!\n"
            "4. Run actual sync: `robocopy C:\\Source D:\\Backup /MIR /LOG:sync.log /NP`\n"
            "5. Check sync.log for errors or skipped files\n"
            "6. Automate with Task Scheduler: create task, trigger = every 1 hour\n"
            "   Program: `robocopy`, Arguments: `C:\\Source D:\\Backup /MIR /LOG:C:\\Logs\\sync.log`\n"
            "7. For real-time sync: use FileSystemWatcher in PowerShell script\n"
            "8. Test: add a file to Source → wait for trigger → verify it appears in Backup"
        ),
        "Create a scheduled task to run a script every hour": (
            "1. Write the script and test it manually first\n"
            "2. Open Task Scheduler: `taskschd.msc`\n"
            "3. Create Task (not Basic Task — for more control)\n"
            "4. General tab: Name = 'Hourly Script', check 'Run whether user is logged on or not'\n"
            "5. Triggers tab → New: Begin = 'On a schedule', repeat every 1 hour, indefinitely\n"
            "6. Actions tab → New: Program = `powershell.exe`,\n"
            "   Arguments = `-ExecutionPolicy Bypass -NoProfile -File \"C:\\Scripts\\myscript.ps1\"`\n"
            "7. Conditions tab: uncheck 'Start only if on AC power' (for laptops)\n"
            "8. Settings tab: check 'Run task as soon as possible after missed start'\n"
            "9. Test: right-click task → Run, check task history for success/failure\n"
            "10. Monitor: `Get-ScheduledTaskInfo -TaskName 'Hourly Script' | Select LastRunTime,LastTaskResult`"
        ),
        "Extract text from multiple PDF files and combine into one document": (
            "1. Install tool: `pip install pdfplumber` (or `pip install PyPDF2`)\n"
            "2. Python script:\n"
            "   ```python\n"
            "   import pdfplumber, glob\n"
            "   texts = []\n"
            "   for pdf_path in sorted(glob.glob('*.pdf')):\n"
            "       with pdfplumber.open(pdf_path) as pdf:\n"
            "           text = '\\n'.join(p.extract_text() or '' for p in pdf.pages)\n"
            "           texts.append(f'=== {pdf_path} ===\\n{text}')\n"
            "   with open('combined.txt', 'w', encoding='utf-8') as f:\n"
            "       f.write('\\n\\n'.join(texts))\n"
            "   ```\n"
            "3. Run: `python extract_pdfs.py`\n"
            "4. Verify: open combined.txt — check text quality, no garbled characters\n"
            "5. If text extraction fails (scanned PDFs): use OCR via `pytesseract` instead\n"
            "6. Word count check: `Get-Content combined.txt | Measure-Object -Word`"
        ),
    }
    
    for task, plan in complex_task_plans.items():
        steps_count = plan.count("\\n") + 1
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": f"Break down this task into actionable steps: {task}"},
                {"role": "assistant", "content": (
                    f"## Task Decomposition: {task}\n\n"
                    f"**Steps:**\n{plan}\n\n"
                    f"**Key principle:** Verify each step before proceeding. "
                    f"If any step fails, diagnose before continuing."
                )},
            ]
        })
    
    # ─── Category 3: Multi-turn workflow planning (30 examples) ───
    multi_turn_workflows = [
        {
            "turns": [
                ("I need to set up a new Python project with virtual environment, linting, and testing.",
                 "## Phase 1: Project Structure\n\n"
                 "Let me break this into 3 phases. Starting with the foundation:\n\n"
                 "**Phase 1 — Project Setup (3 min):**\n"
                 "1. Open PowerShell → navigate to workspace directory\n"
                 "2. `mkdir my-project && cd my-project`\n"
                 "3. `python -m venv .venv`\n"
                 "4. `.venv\\Scripts\\activate`\n"
                 "5. `mkdir src tests docs`\n"
                 "6. Create `src/__init__.py` and `tests/__init__.py`\n\n"
                 "Ready for Phase 2 (dependencies & tooling)?"),
                ("Yes, what's Phase 2?",
                 "## Phase 2: Dependencies & Tooling (5 min)\n\n"
                 "7. Create `requirements.txt`:\n"
                 "   ```\n"
                 "   pytest>=7.0\n"
                 "   ruff>=0.1.0\n"
                 "   mypy>=1.0\n"
                 "   ```\n"
                 "8. `pip install -r requirements.txt`\n"
                 "9. Create `pyproject.toml` with project config:\n"
                 "   - `[tool.ruff]` for linting rules, line-length=88\n"
                 "   - `[tool.pytest.ini_options]` for test discovery (`tests/`)\n"
                 "   - `[tool.mypy]` for type checking strictness\n"
                 "10. Create `.gitignore` with `.venv/`, `__pycache__/`, `*.pyc`, `.mypy_cache/`\n\n"
                 "**Dependency note:** Steps 8-10 can run in parallel if you have two terminal panes.\n\n"
                 "Phase 3 covers git init and first commit."),
                ("And Phase 3?",
                 "## Phase 3: Version Control & Verification (2 min)\n\n"
                 "11. `git init`\n"
                 "12. Create a sample module `src/main.py` with a simple function + type hints\n"
                 "13. Create matching test `tests/test_main.py`\n"
                 "14. Run verification:\n"
                 "    - `ruff check .` → should pass with no errors\n"
                 "    - `mypy src/` → should pass with no type errors\n"
                 "    - `pytest tests/` → should pass with your sample test\n"
                 "15. `git add . && git commit -m 'Initial project setup with linting and testing'`\n\n"
                 "**Total time:** ~10 minutes\n"
                 "**Critical path:** Step 8 (pip install) is the slowest — everything else is fast.\n"
                 "**Post-setup:** Your project is ready for development with automated linting on every save (if using VS Code with ruff extension)."),
            ]
        },
        {
            "turns": [
                ("I need to deploy a web app: build frontend, start backend, configure nginx.",
                 "This is a 3-service deployment. Let me plan the dependency graph:\n\n"
                 "```\n"
                 "Frontend build ──┐\n"
                 "                 ├── Nginx config ── Nginx restart\n"
                 "Backend start ───┘\n"
                 "```\n\n"
                 "**Frontend and backend can start IN PARALLEL** since they're independent.\n\n"
                 "**Step 1-2 (parallel, ~5 min):**\n"
                 "- Terminal 1: `cd frontend && npm run build` (builds to `dist/`)\n"
                 "- Terminal 2: `cd backend && npm start` (starts API server on port 3001)\n\n"
                 "Do you have the frontend deps installed, or do we need `npm install` first?"),
                ("Frontend deps are installed. Backend needs npm install first.",
                 "Updated plan — backend needs setup first:\n\n"
                 "**Step 1: Backend setup (Terminal 2)**\n"
                 "- `cd backend && npm install` (~2 min)\n"
                 "- `npm start` → verify it starts on port 3001\n"
                 "- Check: `curl http://localhost:3001/health` should return 200\n\n"
                 "**Step 2: Frontend build (Terminal 1, start immediately)**\n"
                 "- `cd frontend && npm run build`\n"
                 "- Verify `dist/` directory contains `index.html` and asset files\n\n"
                 "**Step 3: Nginx config (after both complete)**\n"
                 "- Copy `dist/` to nginx serving directory\n"
                 "- Configure reverse proxy: `location /api { proxy_pass http://localhost:3001; }`\n"
                 "- `sudo nginx -t` (test config)\n"
                 "- `sudo systemctl reload nginx`\n\n"
                 "Nginx MUST wait for both frontend build and backend start. Want me to write the nginx config?"),
            ]
        },
    ]

    for mt in multi_turn_workflows:
        convs = [{"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]}]
        for user_msg, asst_msg in mt["turns"]:
            convs.append({"role": "user", "content": user_msg})
            convs.append({"role": "assistant", "content": asst_msg})
        examples.append({"conversations": convs})

    # ─── Category 4: Specific, detailed bulk workflow examples (200 examples) ───
    # Each entry has a UNIQUE detailed workflow plan, not generic templates
    
    detailed_workflows = [
        {"task": "Automate renaming 500 photos by date taken",
         "plan": "**Tools:** PowerShell + Get-FileMetaData\n\n"
                 "1. Open PowerShell in the photo folder\n"
                 "2. Test on single file: `(Get-Item IMG_001.jpg).CreationTime.ToString('yyyy-MM-dd_HHmmss')`\n"
                 "3. Dry-run: `Get-ChildItem *.jpg | ForEach-Object { $new = $_.CreationTime.ToString('yyyy-MM-dd_HHmmss') + $_.Extension; Write-Host \"$($_.Name) → $new\" }`\n"
                 "4. Verify output looks correct\n"
                 "5. Execute: Replace `Write-Host` with `Rename-Item $_.FullName $new`\n"
                 "6. Handle duplicates: Append counter if name exists\n\n"
                 "**Risk mitigation:** Always dry-run first. Work on copies if possible."},
        {"task": "Set up dual-monitor display for coding (VS Code left, browser right)",
         "plan": "**Prerequisites:** Two monitors connected and detected\n\n"
                 "1. Win+P → 'Extend' (use extended desktop, not mirror)\n"
                 "2. Settings → Display: arrange monitors to match physical layout (drag to position)\n"
                 "3. Set primary display (the one with taskbar)\n"
                 "4. Open VS Code → Win+Left arrow (snaps to left half of left monitor)\n"
                 "5. Or: drag VS Code to left monitor, then Win+Up to maximize\n"
                 "6. Open Chrome → drag to right monitor → Win+Up to maximize\n"
                 "7. Optional: VS Code setting `window.restoreFullscreen: true` to remember position\n\n"
                 "**Tip:** Win+Shift+Left/Right moves windows between monitors."},
        {"task": "Debug a Node.js app that crashes on startup with 'port already in use'",
         "plan": "**Diagnosis → Fix → Verify pipeline:**\n\n"
                 "1. Find what's using the port: `netstat -ano | findstr :3000`\n"
                 "2. Note the PID (last column)\n"
                 "3. Identify the process: `tasklist | findstr <PID>`\n"
                 "4. Decision:\n"
                 "   - If it's a zombie/old instance: `taskkill /PID <PID> /F`\n"
                 "   - If it's a needed service: change your app's port in `.env` or config\n"
                 "5. Retry: `npm start`\n"
                 "6. Verify: `curl http://localhost:3000` returns expected response\n\n"
                 "**Prevention:** Add `process.on('SIGTERM', () => server.close())` for graceful shutdown."},
        {"task": "Merge two Git branches with conflicts and push",
         "plan": "1. `git fetch origin` — get latest remote state\n"
                 "2. `git checkout main && git pull` — update main\n"
                 "3. `git checkout feature-branch && git merge main`\n"
                 "4. If conflicts:\n"
                 "   a. `git status` — shows conflicted files (red 'both modified')\n"
                 "   b. Open each conflicted file in VS Code (shows <<<< ==== >>>> markers)\n"
                 "   c. VS Code offers: Accept Current | Accept Incoming | Accept Both\n"
                 "   d. Choose the right resolution for each conflict\n"
                 "   e. `git add <resolved-file>` after fixing each\n"
                 "5. `git commit` — merge commit (default message is fine)\n"
                 "6. `git push origin feature-branch`\n"
                 "7. Verify: `git log --oneline --graph -5` shows clean merge\n\n"
                 "**Key risk:** Never force-push to shared branches."},
        {"task": "Extract data from a PDF invoice and enter it into a spreadsheet",
         "plan": "**Cross-app data transfer workflow:**\n\n"
                 "1. Open the PDF in Chrome (drag-drop or double-click)\n"
                 "2. Identify key data points: invoice number, date, line items, totals\n"
                 "3. Snap Chrome to left half (Win+Left)\n"
                 "4. Open Excel → snap to right half (Win+Right)\n"
                 "5. Create column headers in Excel: Invoice#, Date, Description, Qty, Price, Total\n"
                 "6. For each data point:\n"
                 "   a. Select text in PDF (click-drag)\n"
                 "   b. Ctrl+C\n"
                 "   c. Click target cell in Excel\n"
                 "   d. Ctrl+V (use Ctrl+Shift+V for plain text paste if formatting issues)\n"
                 "7. Format columns: dates as Date, prices as Currency\n"
                 "8. Add SUM formula for totals verification\n"
                 "9. Cross-check: PDF total should match Excel SUM\n"
                 "10. Save Excel file (Ctrl+S)\n\n"
                 "**If PDF has copy protection:** Use OCR (OneNote's paste from clipboard, or Snipping Tool text extraction in Win11)."},
        {"task": "Record a screen demo and narrate it",
         "plan": "1. Plan the demo script (list what to show in order)\n"
                 "2. Close unnecessary apps, clean desktop\n"
                 "3. Open OBS Studio (or Win+G for Xbox Game Bar)\n"
                 "4. Configure:\n"
                 "   - Screen capture source (full screen or window)\n"
                 "   - Audio: desktop audio + microphone\n"
                 "   - Output: 1080p, 30fps, MP4 format\n"
                 "5. Do a 5-second test recording → play back to verify A/V\n"
                 "6. Arrange windows for demo\n"
                 "7. Start recording → wait 2s → begin narration\n"
                 "8. Follow the script, speak clearly, pause at transitions\n"
                 "9. Stop recording (Ctrl+Alt+R in OBS)\n"
                 "10. Review in VLC: check audio levels, no dead air, no errors\n"
                 "11. If trim needed: open in Windows Video Editor\n\n"
                 "**Tip:** Close notification center (Focus Assist → Alarms Only) to prevent popups during recording."},
        {"task": "Set up a cron job (scheduled task) to backup files daily",
         "plan": "**Windows Task Scheduler approach:**\n\n"
                 "1. Create backup script `backup.ps1`:\n"
                 "   ```powershell\n"
                 "   $date = Get-Date -Format 'yyyy-MM-dd'\n"
                 "   $src = 'C:\\Users\\Me\\Documents'\n"
                 "   $dst = \"D:\\Backups\\$date\"\n"
                 "   New-Item -Path $dst -ItemType Directory -Force\n"
                 "   robocopy $src $dst /MIR /LOG:\"D:\\Backups\\$date.log\"\n"
                 "   ```\n"
                 "2. Open Task Scheduler (taskschd.msc)\n"
                 "3. Create Basic Task:\n"
                 "   - Name: 'Daily Document Backup'\n"
                 "   - Trigger: Daily at 2:00 AM\n"
                 "   - Action: Start Program\n"
                 "   - Program: `powershell.exe`\n"
                 "   - Arguments: `-ExecutionPolicy Bypass -File C:\\Scripts\\backup.ps1`\n"
                 "4. Properties → 'Run whether user is logged on or not'\n"
                 "5. Test: right-click task → Run → check output\n"
                 "6. Verify: check D:\\Backups for today's folder\n\n"
                 "**robocopy /MIR** mirrors the source — it also DELETES files in the backup that no longer exist in source."},
        {"task": "Troubleshoot slow internet by testing at each layer",
         "plan": "**Layer-by-layer diagnosis (bottom-up):**\n\n"
                 "1. **Physical layer:** Check cable connections, Wi-Fi signal strength\n"
                 "   - `ipconfig` — verify IP assigned (not 169.254.x.x = APIPA)\n"
                 "2. **Network layer:** Check connectivity\n"
                 "   - `ping 8.8.8.8` — if success: internet reachable\n"
                 "   - If fail: problem is local network or ISP\n"
                 "3. **DNS layer:**\n"
                 "   - `nslookup google.com` — if fail: DNS issue\n"
                 "   - Fix: set DNS to 8.8.8.8 / 1.1.1.1 manually\n"
                 "4. **Speed test:**\n"
                 "   - Open Chrome → speedtest.net → run test\n"
                 "   - Compare to ISP's advertised speed\n"
                 "5. **Router check:**\n"
                 "   - `tracert google.com` — look for high latency hops\n"
                 "   - First hop = your router — should be <5ms\n"
                 "6. **Application layer:**\n"
                 "   - Is it all apps or just one? (isolate browser vs system)\n"
                 "   - Check Task Manager → Network tab for bandwidth hogs\n\n"
                 "**Quick fixes:** Router restart (unplug 30s), flush DNS (`ipconfig /flushdns`)"},
        {"task": "Create an automated testing pipeline for a web app",
         "plan": "**CI/CD pipeline architecture:**\n\n"
                 "1. **Local setup first:**\n"
                 "   a. Install test framework: `npm install jest @testing-library/react cypress`\n"
                 "   b. Create test directories: `__tests__/unit/`, `__tests__/integration/`, `cypress/e2e/`\n"
                 "   c. Write initial tests for critical paths\n"
                 "   d. Add scripts to package.json: `test`, `test:e2e`, `test:ci`\n\n"
                 "2. **Test execution order:**\n"
                 "   ```\n"
                 "   Unit tests (fast, <30s) → Integration tests (~2min) → E2E tests (~5min)\n"
                 "   ```\n"
                 "   Fail fast: if unit tests fail, skip slower tests.\n\n"
                 "3. **CI config (GitHub Actions):**\n"
                 "   a. Create `.github/workflows/test.yml`\n"
                 "   b. Triggers: push to main, PR to main\n"
                 "   c. Steps: checkout → npm ci → lint → test → test:e2e → report\n\n"
                 "4. **Verification:** Push a breaking change to test that CI catches it.\n\n"
                 "**Dependency:** E2E tests need a running server. Use `start-server-and-test` package."},
    ]

    for wf in detailed_workflows:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": f"Plan the workflow: {wf['task']}"},
                {"role": "assistant", "content": wf["plan"]},
            ]
        })

    # Additional diverse bulk: conditional/branching workflow plans  
    conditional_workflows = [
        {"task": "Install a program — but different methods depending on what's available",
         "response": "**Conditional workflow with fallback chain:**\n\n"
                     "```\n"
                     "Check: winget available?\n"
                     "  ├─ YES → winget install <package>\n"
                     "  └─ NO → Check: chocolatey available?\n"
                     "           ├─ YES → choco install <package>\n"
                     "           └─ NO → Download installer from official website\n"
                     "                   → Run .exe/.msi installer\n"
                     "                   → Follow wizard steps\n"
                     "```\n\n"
                     "**Verification at each branch:**\n"
                     "- `winget --version` to check winget\n"
                     "- `choco --version` to check chocolatey\n"
                     "- After install: verify with `where <program>` or check Start Menu"},
        {"task": "Handle a file that might be in different formats (CSV, JSON, or XML)",
         "response": "**Format-detection workflow:**\n\n"
                     "1. Check file extension: `.csv`, `.json`, `.xml`\n"
                     "2. If ambiguous, check first few bytes:\n\n"
                     "| First bytes | Format | Parser |\n"
                     "|-------------|--------|--------|\n"
                     "| `{` or `[`  | JSON   | `python -m json.tool file` |\n"
                     "| `<?xml`     | XML    | `python -c \"import xml.etree...\"` |\n"
                     "| headers,data| CSV    | `python -c \"import csv...\"` |\n\n"
                     "3. Parse with appropriate tool\n"
                     "4. Transform to target format\n"
                     "5. Validate output: check row count, sample data integrity\n\n"
                     "**PowerShell detection:** `Get-Content file.dat -Head 1` to peek at format."},
        {"task": "Deploy code changes but roll back if tests fail",
         "response": "**Safe deployment with rollback:**\n\n"
                     "```\n"
                     "1. git tag pre-deploy-$(date) ← save rollback point\n"
                     "2. git pull origin main\n"
                     "3. npm install\n"
                     "4. npm test\n"
                     "   ├─ PASS → Step 5\n"
                     "   └─ FAIL → ROLLBACK:\n"
                     "              git checkout pre-deploy-$(date)\n"
                     "              npm install\n"
                     "              pm2 restart app\n"
                     "              ALERT: 'Deploy failed, rolled back'\n"
                     "              EXIT\n"
                     "5. npm run build\n"
                     "6. pm2 restart app\n"
                     "7. Health check: curl localhost:3000/health\n"
                     "   ├─ 200 → SUCCESS: 'Deploy complete'\n"
                     "   └─ !200 → ROLLBACK (same as above)\n"
                     "```\n\n"
                     "**Key principle:** Every change is reversible. Never delete the old version until the new one is verified."},
    ]

    for cw in conditional_workflows:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": cw["task"]},
                {"role": "assistant", "content": cw["response"]},
            ]
        })

    # ═══ v2.0: WORKFLOW EXPANSION — Korean, Parallel, Long, Cloud, CI/CD ═══

    # Korean workflow descriptions
    korean_workflows = [
        {"task": "새 프로젝트 폴더를 만들고 Git으로 초기화한 후 GitHub에 올리세요",
         "plan": "**프로젝트 초기화 워크플로우:**\n\n"
                 "1. PowerShell 열기 (Win+X → Windows Terminal)\n"
                 "2. 프로젝트 디렉토리로 이동: `cd C:\\Projects`\n"
                 "3. 새 폴더 생성: `mkdir my-project; cd my-project`\n"
                 "4. Git 초기화: `git init`\n"
                 "5. README.md 생성: `echo '# My Project' > README.md`\n"
                 "6. .gitignore 생성: `echo 'node_modules/' > .gitignore`\n"
                 "7. 첫 커밋: `git add . && git commit -m 'Initial commit'`\n"
                 "8. GitHub에서 새 리포지토리 생성 (https://github.com/new)\n"
                 "9. 리모트 연결: `git remote add origin https://github.com/user/my-project.git`\n"
                 "10. 푸시: `git push -u origin main`\n\n"
                 "**확인:** GitHub 페이지에서 README.md가 보이는지 확인"},
        {"task": "엑셀에서 데이터를 정리하고 차트를 만들어 PDF로 저장하세요",
         "plan": "**데이터 분석 및 리포트 워크플로우:**\n\n"
                 "1. Excel 열기 → 데이터 파일 열기 (Ctrl+O)\n"
                 "2. 데이터 정리:\n"
                 "   - 빈 행 삭제: 데이터 탭 → 필터 → 빈 셀 필터 → 삭제\n"
                 "   - 중복 제거: 데이터 탭 → 중복 항목 제거\n"
                 "   - 서식 통일: 날짜→날짜형식, 숫자→숫자형식\n"
                 "3. 피벗 테이블 생성:\n"
                 "   - 삽입 → 피벗 테이블 → 새 시트\n"
                 "   - 행: 카테고리, 값: 합계\n"
                 "4. 차트 생성:\n"
                 "   - 피벗 테이블 선택 → 삽입 → 추천 차트\n"
                 "   - 차트 제목, 축 레이블 추가\n"
                 "5. PDF 저장: 파일 → 내보내기 → PDF/XPS 문서 만들기\n\n"
                 "**의존성:** 2단계 완료 전 3단계 시작 불가"},
        {"task": "여러 개의 이미지를 일괄 리사이즈하고 워터마크를 추가하세요",
         "plan": "**이미지 일괄 처리 워크플로우:**\n\n"
                 "1. PowerShell에서 Python 스크립트 생성:\n"
                 "   ```python\n"
                 "   from PIL import Image, ImageDraw, ImageFont\n"
                 "   import os\n"
                 "   for f in os.listdir('input/'):\n"
                 "       img = Image.open(f'input/{f}')\n"
                 "       img = img.resize((800, 600))\n"
                 "       draw = ImageDraw.Draw(img)\n"
                 "       draw.text((10, 10), 'watermark', fill='gray')\n"
                 "       img.save(f'output/{f}')\n"
                 "   ```\n"
                 "2. 의존성 설치: `pip install Pillow`\n"
                 "3. input/ 폴더에 원본 이미지 준비\n"
                 "4. output/ 폴더 생성: `mkdir output`\n"
                 "5. 실행: `python resize.py`\n"
                 "6. 결과 확인: output/ 폴더의 이미지 열어 확인\n\n"
                 "**병렬화 가능:** concurrent.futures.ThreadPoolExecutor 사용 시 처리 속도 3-5배 향상"},
    ]
    for wf in korean_workflows:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": wf["task"]},
                {"role": "assistant", "content": wf["plan"]},
            ]
        })

    # Parallel execution workflows
    parallel_workflows = [
        {"task": "Set up a full-stack development environment with frontend, backend, and database running simultaneously",
         "plan": "**Parallel launch workflow (3 terminals):**\n\n"
                 "```\n"
                 "SEQUENTIAL SETUP (must be in order):\n"
                 "  1. Clone repo and install dependencies\n"
                 "  2. Create .env files from .env.example\n"
                 "  3. Run database migrations\n"
                 "\n"
                 "PARALLEL LAUNCH (can run simultaneously):\n"
                 "  Terminal 1: cd backend && npm run dev     (port 3001)\n"
                 "  Terminal 2: cd frontend && npm run dev    (port 3000)\n"
                 "  Terminal 3: docker-compose up db redis    (ports 5432, 6379)\n"
                 "```\n\n"
                 "**Startup order matters:** DB → Backend → Frontend\n"
                 "**Health checks:** curl localhost:3001/health, open localhost:3000\n"
                 "**Use tmux or Windows Terminal tabs for side-by-side monitoring**"},
        {"task": "Run multiple test suites in parallel to save time",
         "plan": "**Parallel test execution strategy:**\n\n"
                 "```\n"
                 "Independent test groups (can run in parallel):\n"
                 "├─ Group A: Unit tests (Jest)       → 30 seconds\n"
                 "├─ Group B: API tests (Supertest)   → 2 minutes\n"
                 "├─ Group C: Lint + typecheck         → 1 minute\n"
                 "└─ Group D: E2E tests (Cypress)     → 5 minutes\n"
                 "\n"
                 "Sequential: Group A first (fail fast), then B+C+D in parallel\n"
                 "```\n\n"
                 "**Implementation:**\n"
                 "1. `npm run test:unit` — if fails, STOP (don't waste time on slow tests)\n"
                 "2. `concurrently 'npm run test:api' 'npm run lint' 'npm run test:e2e'`\n"
                 "3. Total time: ~5.5 min (vs ~8.5 min sequential)\n\n"
                 "**CI optimization:** Use matrix strategy in GitHub Actions for true parallelism"},
    ]
    for wf in parallel_workflows:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": wf["task"]},
                {"role": "assistant", "content": wf["plan"]},
            ]
        })

    # Long multi-step workflows (20+ steps)
    long_workflows = [
        {"task": "Deploy a production application with zero-downtime migration",
         "plan": "**Zero-Downtime Production Deployment (23 steps):**\n\n"
                 "**Phase 1: Preparation (Steps 1-6)**\n"
                 "1. Create deployment branch from main\n"
                 "2. Run full test suite on deployment branch\n"
                 "3. Build production artifacts (npm run build)\n"
                 "4. Create database migration backup: `pg_dump -Fc prod > backup.dump`\n"
                 "5. Stage migration in staging environment first\n"
                 "6. Smoke test staging: verify critical paths work\n\n"
                 "**Phase 2: Database Migration (Steps 7-11)**\n"
                 "7. Enable maintenance window logging\n"
                 "8. Run non-breaking migrations first (ADD COLUMN, CREATE INDEX CONCURRENTLY)\n"
                 "9. Verify migration: `SELECT count(*) FROM new_table`\n"
                 "10. Update connection pool settings if schema changed\n"
                 "11. Monitor error rates for 5 minutes\n\n"
                 "**Phase 3: Application Deploy (Steps 12-17)**\n"
                 "12. Deploy to canary (1 instance)\n"
                 "13. Monitor canary metrics: error rate, latency, CPU\n"
                 "14. If canary healthy (5 min): roll out to 25% of fleet\n"
                 "15. Monitor at 25% for 10 minutes\n"
                 "16. Roll out to 100%\n"
                 "17. Old instances drain connections (graceful shutdown)\n\n"
                 "**Phase 4: Verification (Steps 18-23)**\n"
                 "18. Run production smoke tests\n"
                 "19. Check all health endpoints respond 200\n"
                 "20. Verify database query performance (no slow queries)\n"
                 "21. Check error monitoring (Sentry/DataDog)\n"
                 "22. Update deployment log\n"
                 "23. Notify team in Slack: #deployments\n\n"
                 "**Rollback at any step:** Revert to backup.dump + redeploy previous Docker image"},
    ]
    for wf in long_workflows:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": wf["task"]},
                {"role": "assistant", "content": wf["plan"]},
            ]
        })

    # Cloud service workflows
    cloud_workflows = [
        {"task": "Set up AWS S3 bucket with CloudFront CDN for static website hosting",
         "plan": "**AWS Static Site Pipeline:**\n\n"
                 "1. Create S3 bucket: `aws s3 mb s3://my-site-bucket`\n"
                 "2. Enable static website hosting:\n"
                 "   `aws s3 website s3://my-site --index-document index.html --error-document error.html`\n"
                 "3. Upload files: `aws s3 sync ./build s3://my-site-bucket`\n"
                 "4. Create CloudFront distribution:\n"
                 "   - Origin: S3 bucket\n"
                 "   - SSL: ACM certificate (us-east-1 required)\n"
                 "   - Cache policy: Managed-CachingOptimized\n"
                 "5. Configure custom domain in Route 53\n"
                 "6. Verify: `curl -I https://mysite.com` → should show CloudFront headers\n\n"
                 "**Cost:** S3 (~$0.023/GB/mo) + CloudFront (~$0.085/GB transfer)"},
        {"task": "Docker 컨테이너를 빌드하고 레지스트리에 올린 후 Kubernetes에 배포하세요",
         "plan": "**컨테이너 배포 파이프라인:**\n\n"
                 "1. Dockerfile 작성 (또는 확인)\n"
                 "2. 이미지 빌드: `docker build -t myapp:v1.0 .`\n"
                 "3. 로컬 테스트: `docker run -p 3000:3000 myapp:v1.0`\n"
                 "4. 레지스트리 태그: `docker tag myapp:v1.0 registry.io/myapp:v1.0`\n"
                 "5. 로그인: `docker login registry.io`\n"
                 "6. 푸시: `docker push registry.io/myapp:v1.0`\n"
                 "7. K8s 매니페스트 업데이트: image: registry.io/myapp:v1.0\n"
                 "8. 배포: `kubectl apply -f k8s/deployment.yaml`\n"
                 "9. 상태 확인: `kubectl rollout status deployment/myapp`\n"
                 "10. 파드 확인: `kubectl get pods -l app=myapp`\n\n"
                 "**롤백:** `kubectl rollout undo deployment/myapp`"},
    ]
    for wf in cloud_workflows:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": wf["task"]},
                {"role": "assistant", "content": wf["plan"]},
            ]
        })

    # Combinatorial: task type × complexity level × OS
    task_types_combo = [
        "file organization", "data backup", "environment setup",
        "dependency installation", "configuration change", "log analysis",
        "permission management", "network diagnostics",
    ]
    complexity_levels = ["simple (3 steps)", "medium (5-7 steps)", "complex (10+ steps)"]
    for task_type in task_types_combo:
        for complexity in random.sample(complexity_levels, 2):
            user_q = f"Plan a {complexity} workflow for {task_type} on Windows"
            if "simple" in complexity:
                steps = f"1. Open relevant tool (PowerShell or app)\n2. Execute {task_type} command\n3. Verify result"
            elif "medium" in complexity:
                steps = (f"1. Assess current state\n2. Backup existing configuration\n"
                        f"3. Plan {task_type} changes\n4. Execute step-by-step\n"
                        f"5. Verify each change\n6. Document what was done\n7. Clean up temporary files")
            else:
                steps = (f"1. Document current state\n2. Create backup\n3. Plan all changes\n"
                        f"4-6. Execute {task_type} in phases\n7. Test after each phase\n"
                        f"8. Verify full system\n9. Update documentation\n10. Schedule monitoring\n"
                        f"11. Create rollback plan\n12. Notify stakeholders")
            examples.append({
                "conversations": [
                    {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                    {"role": "user", "content": user_q},
                    {"role": "assistant", "content": f"**{task_type.title()} Workflow ({complexity}):**\n\n{steps}"},
                ]
            })

    return examples


# ═══════════════════════════════════════════════════════════════
# VERIFICATION ORACLE — Expert 18 Training Data
# ═══════════════════════════════════════════════════════════════

def generate_verification_oracle_data() -> List[Dict]:
    """Generate 500+ training examples for verification oracle expert."""
    examples = []
    
    # ─── Category 1: Action success verification (150 examples) ───
    verifications = [
        {
            "action": "Saved a file in Notepad using Ctrl+S",
            "success_indicators": [
                "Title bar no longer shows asterisk (*) or 'Unsaved' indicator",
                "If Save As dialog appeared: file name field is populated and dialog closed",
                "No error dialog appeared after save",
                "File modification timestamp updated (visible in Explorer properties)",
            ],
            "failure_indicators": [
                "Title bar still shows asterisk (*) indicating unsaved changes",
                "Error dialog: 'Access denied' or 'File is read-only'",
                "Error dialog: 'The disk is full'",
                "Save As dialog still open (save didn't complete)",
            ],
        },
        {
            "action": "Opened Chrome and navigated to google.com",
            "success_indicators": [
                "Chrome window is visible and in focus",
                "Address bar shows 'https://www.google.com' or 'google.com'",
                "Google logo and search bar are visible in the page content",
                "No error page (like ERR_CONNECTION_REFUSED) is showing",
            ],
            "failure_indicators": [
                "Chrome didn't open (no window appeared)",
                "Error page: 'ERR_INTERNET_DISCONNECTED' or 'ERR_NAME_NOT_RESOLVED'",
                "Chrome opened but navigated to a different page (home page override)",
                "Chrome opened but is showing a crash dialog or 'Aw, Snap!'",
            ],
        },
        {
            "action": "Copied text to clipboard using Ctrl+C",
            "success_indicators": [
                "Text was visually selected (highlighted in blue) before Ctrl+C",
                "No error sound played",
                "Clipboard content can be verified by pasting (Ctrl+V) elsewhere",
                "Win+V clipboard history shows the copied text (if enabled)",
            ],
            "failure_indicators": [
                "No text was selected before copy (nothing to copy)",
                "The application doesn't support Ctrl+C (some terminal apps use Ctrl+Shift+C)",
                "Protected content that blocks clipboard access",
                "Clipboard was overwritten by another application immediately after",
            ],
        },
        {
            "action": "Created a new folder in Windows Explorer",
            "success_indicators": [
                "A new folder appears in the file list with name field in edit mode",
                "Default name 'New folder' is shown and highlighted for renaming",
                "Folder icon is standard yellow folder icon",
                "No error dialog appeared",
            ],
            "failure_indicators": [
                "Error: 'You need permission to perform this action'",
                "Error: 'The filename, directory name, or volume label syntax is incorrect'",
                "No new folder appeared (might be a read-only location)",
                "Folder was created but in the wrong directory",
            ],
        },
        {
            "action": "Ran a Python script using 'python script.py'",
            "success_indicators": [
                "Script produced expected output in the terminal",
                "No traceback or error messages in terminal output",
                "Exit code was 0 (can check with 'echo $?' on Linux or '$LASTEXITCODE' on PowerShell)",
                "Any expected output files were created",
            ],
            "failure_indicators": [
                "Traceback with exception type and line number",
                "ModuleNotFoundError: missing dependency",
                "SyntaxError: code has syntax issues",
                "FileNotFoundError: script references missing file",
                "PermissionError: insufficient permissions",
                "Script hangs (no output for extended time)",
            ],
        },
    ]
    
    for v in verifications:
        success_text = "\n".join(f"  ✅ {s}" for s in v["success_indicators"])
        failure_text = "\n".join(f"  ❌ {f}" for f in v["failure_indicators"])
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": f"How do I verify that this action succeeded: {v['action']}?"},
                {"role": "assistant", "content": (
                    f"## Verification: {v['action']}\n\n"
                    f"**Success indicators** (look for ANY of these):\n{success_text}\n\n"
                    f"**Failure indicators** (watch for ANY of these):\n{failure_text}\n\n"
                    f"**Verification steps:**\n"
                    f"1. Take a screenshot immediately after the action\n"
                    f"2. Check for success indicators in the screenshot\n"
                    f"3. If no clear success indicator: perform a secondary verification\n"
                    f"4. If failure indicator found: diagnose and plan retry\n\n"
                    f"**Confidence assessment:** Check at least 2 independent indicators "
                    f"before declaring success with high confidence."
                )},
            ]
        })
    
    # ─── Category 2: Error message interpretation (150 examples) ───
    error_messages = [
        ("'python' is not recognized as an internal or external command",
         "Python is not installed or not in the system PATH. Solutions:\n"
         "1. Install Python from python.org\n"
         "2. During install, check 'Add Python to PATH'\n"
         "3. Or manually add Python's install directory to PATH environment variable\n"
         "4. Restart the terminal after PATH changes\n"
         "5. Alternative: use 'py' command instead of 'python' on Windows"),
        ("Access is denied",
         "The current user doesn't have permission for this operation. Solutions:\n"
         "1. Run the application as Administrator (right-click → Run as administrator)\n"
         "2. Check file/folder permissions (right-click → Properties → Security tab)\n"
         "3. If it's a system file: use an elevated PowerShell/cmd\n"
         "4. If it's a locked file: check what process has it open (Resource Monitor)"),
        ("ENOENT: no such file or directory",
         "The specified file path doesn't exist. Check:\n"
         "1. Spelling of the filename and path\n"
         "2. Current working directory (use 'pwd' or 'cd' to verify)\n"
         "3. Whether the file was moved, renamed, or deleted\n"
         "4. Whether using forward slashes on Windows (use backslashes or raw strings)\n"
         "5. Case sensitivity (Windows paths are case-insensitive, but some tools aren't)"),
        ("FATAL ERROR: CALL_AND_RETRY_LAST Allocation failed - JavaScript heap out of memory",
         "Node.js ran out of memory. Solutions:\n"
         "1. Increase memory limit: NODE_OPTIONS='--max-old-space-size=8192'\n"
         "2. Check for memory leaks in the application\n"
         "3. Process data in smaller chunks instead of loading everything at once\n"
         "4. Use streaming APIs instead of loading entire files into memory"),
        ("ModuleNotFoundError: No module named 'pandas'",
         "The Python module 'pandas' is not installed in the current environment. Solutions:\n"
         "1. Install it: pip install pandas\n"
         "2. If using virtual environment: activate it first\n"
         "3. Check which Python/pip: 'which python' or 'where python'\n"
         "4. Use python -m pip install pandas for explicit Python version\n"
         "5. If using conda: conda install pandas"),
        ("ERR_CONNECTION_REFUSED",
         "The browser can't connect to the target server. Check:\n"
         "1. Is the server/service actually running?\n"
         "2. Is the URL and port correct?\n"
         "3. Is a firewall blocking the connection?\n"
         "4. For localhost: is the development server started?\n"
         "5. For remote: is the network/internet connection working?"),
        ("git: 'push' is not a git command. See 'git --help'.",
         "This usually means git is not properly installed or there's a PATH issue.\n"
         "But if the error specifically says a command doesn't exist:\n"
         "1. Check git version: git --version\n"
         "2. Reinstall git if needed\n"
         "3. Make sure you're inside a git repo (git status)\n"
         "4. Check for typos in the command"),
    ]
    
    for error_msg, diagnosis in error_messages:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": f"I got this error: '{error_msg}'. What does it mean and how do I fix it?"},
                {"role": "assistant", "content": (
                    f"## Error Diagnosis\n\n"
                    f"**Error:** `{error_msg}`\n\n"
                    f"**Diagnosis:**\n{diagnosis}\n\n"
                    f"**Verification after fix:** Re-run the original command/action and confirm "
                    f"the error no longer appears. Check for new errors that might surface."
                )},
            ]
        })
    
    # ─── Category 3: State change detection (100 examples) ───
    state_changes = [
        ("Before: Notepad title shows 'Untitled - Notepad'. After: Title shows '* report.txt - Notepad'",
         "State change detected: File was named 'report.txt' but has UNSAVED changes (indicated by asterisk *). "
         "The file has been given a name (likely via Save As) but subsequent edits haven't been saved yet."),
        ("Before: Chrome tab shows loading spinner. After: Page content is fully rendered",
         "State change detected: Page load completed successfully. The loading spinner disappearing and content "
         "rendering confirms the navigation succeeded. Verify the correct page loaded by checking the URL."),
        ("Before: Terminal shows command prompt '$'. After: Terminal shows error traceback",
         "State change detected: A command was executed and FAILED. The traceback indicates a Python exception. "
         "Read the traceback bottom-to-top: the last line shows the exception type and message, "
         "lines above show the call stack with file names and line numbers."),
        ("Before: Desktop has 5 icons. After: Desktop has 6 icons",
         "State change detected: A new file/shortcut was created or copied to the desktop. "
         "Check the new icon's name and type. If unexpected, it might be from an installer or download."),
        ("Before: Task Manager shows 45% CPU usage. After: Task Manager shows 98% CPU usage",
         "State change detected: CRITICAL — CPU usage spiked to near-maximum. This indicates a process "
         "is consuming excessive resources. Check the 'Processes' tab to identify the culprit. "
         "This could cause system slowdowns and should be investigated immediately."),
    ]
    
    for observation, analysis in state_changes:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": f"I observed this state change: {observation}. Analyze it."},
                {"role": "assistant", "content": analysis},
            ]
        })
    
    # ─── Category 4: Multi-turn verification (30 examples) ───
    multi_turn_verifications = [
        {
            "turns": [
                ("I ran 'pip install tensorflow' and it seemed to finish. Did it work?",
                 "Let me help you verify the installation step by step:\n\n"
                 "**Quick check:** Run `python -c \"import tensorflow; print(tensorflow.__version__)\"`\n\n"
                 "**What to look for:**\n"
                 "- If it prints a version number (e.g., '2.15.0'): SUCCESS\n"
                 "- If you see `ModuleNotFoundError`: FAILED — package didn't install correctly\n"
                 "- If you see `ImportError` about DLLs: PARTIAL — installed but missing C++ runtime\n\n"
                 "Can you run that command and tell me what it says?"),
                ("It says WARNING about CUDA and cuDNN not found, then prints '2.15.0'.",
                 "**Verdict: Installation SUCCEEDED (with expected warnings)**\n\n"
                 "The CUDA/cuDNN warnings mean:\n"
                 "- TensorFlow IS installed and importable ✅\n"
                 "- GPU acceleration is NOT available (CPU-only mode) ⚠️\n"
                 "- This is NORMAL if you don't have an NVIDIA GPU or haven't installed CUDA toolkit\n\n"
                 "**TensorFlow will work correctly** for development and testing on CPU. "
                 "Training will be slower without GPU, but all functionality is available.\n\n"
                 "**If you need GPU:** Install CUDA 11.8 + cuDNN 8.6 from NVIDIA's website."),
            ]
        },
        {
            "turns": [
                ("I saved a file but I'm not sure if it actually saved. The title bar still says the same name.",
                 "The title bar showing the same filename is EXPECTED after a successful save. "
                 "What matters is whether the asterisk (*) or 'modified' indicator is gone.\n\n"
                 "**Check these:**\n"
                 "1. Does the title bar show `*` before or after the filename? (e.g., '* document.txt')\n"
                 "2. Open Explorer → navigate to the file → check 'Date modified' — is it recent?\n"
                 "3. Try closing the app — if it asks 'Save changes?' then it DID NOT save\n\n"
                 "What do you see?"),
                ("No asterisk, and the Date modified shows the current time.",
                 "**Confirmed: Save was SUCCESSFUL** ✅\n\n"
                 "Evidence:\n"
                 "1. No asterisk (*) in title → no unsaved changes remain\n"
                 "2. Date modified matches current time → file was just written to disk\n\n"
                 "Both indicators consistently confirm the save. "
                 "You can safely proceed with the next step in your workflow."),
            ]
        },
    ]

    for mt in multi_turn_verifications:
        convs = [{"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]}]
        for user_msg, asst_msg in mt["turns"]:
            convs.append({"role": "user", "content": user_msg})
            convs.append({"role": "assistant", "content": asst_msg})
        examples.append({"conversations": convs})

    # ─── Category 5: Specific verification scenarios (200 examples) ───
    # Each has a UNIQUE, detailed verification scenario
    
    specific_verifications = [
        {"action": "installed VS Code extension",
         "check": "**Verification steps:**\n"
                  "1. Check Extensions sidebar (Ctrl+Shift+X): the extension should appear under 'Installed'\n"
                  "2. Look for the extension's icon in the activity bar or status bar (some add visible icons)\n"
                  "3. Test functionality: if it's a linter, open a file with known issues — it should show diagnostics\n"
                  "4. Check Output panel (Ctrl+Shift+U) → dropdown → select the extension's output channel for logs\n\n"
                  "**Common failure mode:** Extension installed but requires reload — look for 'Reload Required' button."},
        {"action": "cloned a Git repository",
         "check": "**Verification:**\n"
                  "1. `cd <repo-name>` — if directory exists, clone created the folder\n"
                  "2. `git status` — should show 'On branch main' (not 'not a git repository')\n"
                  "3. `git log --oneline -3` — should show commit history\n"
                  "4. `ls` (or `dir`) — should show repo files, not empty\n"
                  "5. Check remote: `git remote -v` — should show origin URL\n\n"
                  "**If clone failed:** Look for messages about SSH keys (use HTTPS URL) or disk space."},
        {"action": "set an environment variable",
         "check": "**Verification depends on how it was set:**\n\n"
                  "**Temporary (current session only):**\n"
                  "- PowerShell: `$env:MY_VAR` — should print the value\n"
                  "- CMD: `echo %MY_VAR%` — should print the value\n\n"
                  "**Permanent (system-wide):**\n"
                  "- `[System.Environment]::GetEnvironmentVariable('MY_VAR', 'User')` for user-level\n"
                  "- `[System.Environment]::GetEnvironmentVariable('MY_VAR', 'Machine')` for system-level\n"
                  "- **Important:** New terminals will see it, existing ones won't until restarted\n\n"
                  "**Common mistake:** Set in one terminal, testing in another — the second one won't have it."},
        {"action": "successfully printed to a network printer",
         "check": "**Verification steps:**\n"
                  "1. Check print queue: Settings → Printers → click printer → 'Open print queue'\n"
                  "2. Document should appear with status 'Printing' then 'Printed'\n"
                  "3. If status shows 'Error' or 'Offline': the print didn't reach the printer\n"
                  "4. Physical check: did paper come out of the printer?\n\n"
                  "**If stuck in queue:** Right-click → Cancel, then retry. Check printer is online and has paper/ink."},
        {"action": "resized a partition using Disk Management",
         "check": "**Verification:**\n"
                  "1. Open Disk Management (diskmgmt.msc)\n"
                  "2. Check the partition shows the new size\n"
                  "3. Open This PC → verify drive shows correct total and free space\n"
                  "4. Run `chkdsk <drive>: /F` to verify filesystem integrity\n\n"
                  "**CRITICAL:** If you see 'Unallocated' space, the resize freed space but didn't extend the adjacent partition. "
                  "Right-click the partition you want to extend → 'Extend Volume' to claim the unallocated space."},
        {"action": "set up SSH key authentication",
         "check": "**Test SSH key auth:**\n"
                  "1. `ssh -T git@github.com` — should say 'Hi username! You've successfully authenticated'\n"
                  "2. If it asks for password → key auth NOT working\n"
                  "3. Debug: `ssh -vT git@github.com` — verbose output shows which keys are tried\n"
                  "4. Check key was added: `ssh-add -l` — should list your key\n"
                  "5. Verify public key exists on GitHub: Settings → SSH and GPG keys\n\n"
                  "**Common fix:** `ssh-add ~/.ssh/id_ed25519` to load the key into the agent."},
        {"action": "Docker container started successfully",
         "check": "**Verify Docker container:**\n"
                  "1. `docker ps` — container should appear with STATUS 'Up X seconds'\n"
                  "2. `docker logs <container>` — check for error messages in startup logs\n"
                  "3. If it exposes a port: `curl http://localhost:<port>` — should respond\n"
                  "4. `docker inspect <container> --format='{{.State.Status}}'` → should be 'running'\n\n"
                  "**If container exit immediately:** `docker ps -a` shows stopped containers, then `docker logs <id>` for crash reason."},
        {"action": "Windows Update completed",
         "check": "**Verify Windows Update:**\n"
                  "1. Settings → Update & Security → Windows Update\n"
                  "2. Should show 'You're up to date' with last check time\n"
                  "3. Check Update history: shows installed updates with dates and status\n"
                  "4. Look for 'Restart required' — some updates aren't complete until restart\n"
                  "5. Verify: `winver` (Run → winver) shows updated build number\n\n"
                  "**If update failed:** Click 'Retry' or check error code and search Microsoft support."},
        {"action": "created a virtual environment in Python",
         "check": "**Verify venv:**\n"
                  "1. Check prompt: should show `(.venv)` or `(venv)` prefix\n"
                  "2. `where python` (Windows) → should point to `.venv\\Scripts\\python.exe`\n"
                  "3. `python -c \"import sys; print(sys.prefix)\"` → should show venv path, not system Python\n"
                  "4. `pip list` → should show minimal packages (just pip and setuptools)\n\n"
                  "**If prompt doesn't change after activation:** You may be using a shell that doesn't modify the prompt. "
                  "The `where python` check is the reliable way."},
        {"action": "connected to a Wi-Fi network",
         "check": "**Verify Wi-Fi connection:**\n"
                  "1. System tray Wi-Fi icon: should show signal bars (not globe with X)\n"
                  "2. `ipconfig` → look for 'Wireless LAN adapter' with valid IPv4 address\n"
                  "3. `ping 8.8.8.8` → should get reply (verifies internet, not just LAN)\n"
                  "4. `netsh wlan show interfaces` → shows SSID, signal strength, speed\n\n"
                  "**Connected but no internet?** Try: `ipconfig /release && ipconfig /renew` → `ipconfig /flushdns`"},
    ]

    for sv in specific_verifications:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": f"I just {sv['action']}. How do I verify it worked?"},
                {"role": "assistant", "content": sv["check"]},
            ]
        })

    # Confidence-based verification (structured differently from above)
    confidence_scenarios = [
        {"observation": "After running 'git push', the terminal shows no output at all.",
         "analysis": "**Confidence: LOW** ⚠️\n\n"
                     "No output after `git push` is suspicious. Typically, a successful push shows:\n"
                     "```\n"
                     "Enumerating objects: 5, done.\n"
                     "Writing objects: 100% (3/3), 312 bytes, done.\n"
                     "To github.com:user/repo.git\n"
                     "   abc1234..def5678  main -> main\n"
                     "```\n\n"
                     "No output could mean:\n"
                     "1. **Credential prompt is waiting** (check if Git is asking for username/password)\n"
                     "2. **Network timeout** (connection hanging)\n"
                     "3. **Push hook is running** (pre-push hook could be slow)\n\n"
                     "**Action:** Wait 30s. If still no output, press Ctrl+C and try `git push -v` (verbose) to see what's happening."},
        {"observation": "The website now shows a different layout than before the deployment.",
         "analysis": "**Confidence: MEDIUM** — Layout change could indicate success OR failure.\n\n"
                     "**If the new layout matches the intended design:**\n"
                     "✅ Deployment SUCCEEDED — new frontend is live\n"
                     "- Clear browser cache (Ctrl+Shift+R) to see the fully-updated version\n"
                     "- Check in incognito mode to avoid cache issues\n\n"
                     "**If the layout is broken (missing styles, wrong positions):**\n"
                     "❌ Deployment PARTIALLY FAILED — HTML deployed but CSS/JS assets missing\n"
                     "- Check browser DevTools Console (F12) for 404 errors on CSS/JS files\n"
                     "- Check network tab for failed asset requests\n"
                     "- Common cause: asset paths are relative and base URL changed"},
    ]

    for cs in confidence_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": cs["observation"]},
                {"role": "assistant", "content": cs["analysis"]},
            ]
        })

    # ═══ v2.0: VERIFICATION EXPANSION — Korean, Partial, Security, Data ═══

    # Korean verification scenarios
    korean_verifications = [
        {"action": "한글(HWP) 문서를 PDF로 변환했습니다",
         "check": "**확인 단계:**\n"
                  "1. 출력 폴더에서 PDF 파일 존재 확인\n"
                  "2. PDF 파일 크기가 0이 아닌지 확인\n"
                  "3. PDF를 열어 페이지 수가 원본과 동일한지 확인\n"
                  "4. 한글 폰트가 깨지지 않았는지 확인 (특히 특수 문자, 수식)\n"
                  "5. 이미지/표가 올바르게 렌더링되었는지 확인\n\n"
                  "**일반적인 실패:** 폰트 임베딩 실패 시 PDF에서 글자가 □로 표시됨"},
        {"action": "Windows 업데이트를 설치했습니다",
         "check": "**확인 단계:**\n"
                  "1. 설정 > 업데이트 및 보안 > Windows 업데이트 확인\n"
                  "2. '최신 상태입니다' 메시지 확인\n"
                  "3. 업데이트 기록에서 설치 상태 확인 (성공/실패)\n"
                  "4. `winver` 명령으로 빌드 번호 확인\n"
                  "5. 재시작이 필요한 경우 재시작 후 재확인\n\n"
                  "**실패 시:** 오류 코드 (예: 0x800f0922) 검색하여 해결"},
        {"action": "파이썬 가상환경을 생성하고 패키지를 설치했습니다",
         "check": "**확인 방법:**\n"
                  "1. 가상환경 활성화: `.\\venv\\Scripts\\activate`\n"
                  "2. `python --version` — 올바른 버전 확인\n"
                  "3. `pip list` — 설치된 패키지 목록 확인\n"
                  "4. `python -c 'import package_name'` — 임포트 테스트\n"
                  "5. `pip check` — 의존성 충돌 확인\n\n"
                  "**주의:** (venv) 프롬프트가 보여야 가상환경이 활성화된 상태"},
    ]
    for kv in korean_verifications:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": f"다음 작업을 확인해주세요: {kv['action']}"},
                {"role": "assistant", "content": kv["check"]},
            ]
        })

    # Partial success detection
    partial_success = [
        {"observation": "I ran `npm install` and it completed, but there are 5 peer dependency warnings and 2 deprecated package notices",
         "analysis": "**Verdict: PARTIAL SUCCESS (85% confidence)**\n\n"
                     "✅ Installation completed — packages were installed\n"
                     "⚠️ Peer dependency warnings: Not blocking but may cause runtime issues\n"
                     "⚠️ Deprecated notices: Packages work but may have security vulnerabilities\n\n"
                     "**Actions needed:**\n"
                     "1. Check `npm audit` for security issues\n"
                     "2. Run `npm ls` to verify dependency tree is intact\n"
                     "3. Test the application to verify nothing is broken\n"
                     "4. Consider updating deprecated packages when possible"},
        {"observation": "I copied 50 files to a new directory. The file count shows 48 files in the destination",
         "analysis": "**Verdict: FAILURE — 2 files missing (96% complete)**\n\n"
                     "❌ Not all files were copied. Possible causes:\n"
                     "1. Files were locked by another process\n"
                     "2. Permission denied on specific files\n"
                     "3. File path too long (Windows MAX_PATH 260 chars)\n"
                     "4. Special characters in filenames\n\n"
                     "**Verification:**\n"
                     "1. Compare file lists: `diff (ls source) (ls dest)` in PowerShell\n"
                     "2. Check for error log from the copy operation\n"
                     "3. Try copying the missing 2 files individually to get specific error"},
        {"observation": "Database migration ran but one table alteration showed a warning about data truncation",
         "analysis": "**Verdict: CRITICAL PARTIAL FAILURE (40% confidence in data integrity)**\n\n"
                     "⚠️ Data truncation warning means DATA MAY HAVE BEEN LOST!\n\n"
                     "**Immediate actions:**\n"
                     "1. STOP all operations on affected table\n"
                     "2. Check backup exists before migration\n"
                     "3. Compare row counts: `SELECT COUNT(*) FROM table`\n"
                     "4. Check truncated column: `SELECT MAX(LENGTH(column)) FROM table`\n"
                     "5. Verify affected column's old vs new type definition\n\n"
                     "**If data was lost:** Restore from backup and re-run with corrected column size"},
    ]
    for ps in partial_success:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": ps["observation"]},
                {"role": "assistant", "content": ps["analysis"]},
            ]
        })

    # Security verification
    security_verifications = [
        {"action": "configured SSL certificate for the web server",
         "check": "**SSL Certificate Verification:**\n"
                  "1. `openssl s_client -connect yoursite.com:443 -servername yoursite.com` → check certificate chain\n"
                  "2. Verify certificate expiry: `echo | openssl s_client -connect site:443 2>/dev/null | openssl x509 -dates`\n"
                  "3. Check HTTPS in browser: should show padlock icon (no warnings)\n"
                  "4. Test HTTPS redirect: `curl -I http://site.com` → should get 301/302 to https://\n"
                  "5. SSL Labs test: https://www.ssllabs.com/ssltest/ → aim for A or A+ rating\n"
                  "6. Check all subdomains also use HTTPS\n\n"
                  "**Common failures:** Mixed content (HTTP resources on HTTPS page), certificate name mismatch"},
        {"action": "updated firewall rules to block external access to database port",
         "check": "**Firewall Rule Verification:**\n"
                  "1. From OUTSIDE network: `nmap -p 5432 your-ip` → should show 'filtered' or 'closed'\n"
                  "2. From INSIDE network: `psql -h localhost -p 5432` → should still work\n"
                  "3. List firewall rules: `netsh advfirewall firewall show rule name=all | findstr 5432`\n"
                  "4. Verify rule priority: ensure block rule has higher priority than any allow rule\n"
                  "5. Test from multiple external IPs if possible\n\n"
                  "**Warning:** Verify you haven't locked yourself out of remote management (SSH/RDP)"},
    ]
    for sv in security_verifications:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": f"Verify that I correctly {sv['action']}"},
                {"role": "assistant", "content": sv["check"]},
            ]
        })

    # Data integrity verification
    data_integrity = [
        {"observation": "Exported CSV file from database. Source table has 10,000 rows",
         "analysis": "**Data Integrity Check:**\n"
                     "1. Row count: `wc -l export.csv` (subtract 1 for header) → should be 10,000\n"
                     "2. Column count: check first line has expected number of commas\n"
                     "3. Spot-check: compare 5 random rows against source\n"
                     "4. Null handling: search for empty fields → `grep ',,' export.csv | wc -l`\n"
                     "5. Encoding: verify UTF-8 → `file export.csv` should show 'UTF-8'\n"
                     "6. Special chars: look for unescaped commas in text fields\n"
                     "7. Checksum: `certutil -hashfile export.csv SHA256`\n\n"
                     "**If row count doesn't match:** Check query had no WHERE clause, and LIMIT wasn't set"},
        {"observation": "Restored database from backup file. Original was 2.3 GB, backup file is 2.3 GB",
         "analysis": "**Backup Restoration Verification:**\n"
                     "1. ✅ File size matches — good initial sign\n"
                     "2. Table count: `SELECT count(*) FROM information_schema.tables WHERE table_schema='public'`\n"
                     "3. Row counts for critical tables: compare against pre-backup counts\n"
                     "4. Sequence values: check auto-increment counters are correct\n"
                     "5. Foreign key integrity: run constraint validation\n"
                     "6. Test critical queries that touch multiple tables\n"
                     "7. Check indexes exist: `\\di` in psql\n\n"
                     "**Confidence:** 70% based on size match alone. Need query-level verification for 95%+"},
    ]
    for di in data_integrity:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                {"role": "user", "content": di["observation"]},
                {"role": "assistant", "content": di["analysis"]},
            ]
        })

    # Combinatorial: action type × expected outcome × error indicators
    action_types = [
        "file copy", "app installation", "config change", "database query",
        "API call", "build process", "deployment", "user creation",
    ]
    outcomes = ["succeeded", "failed silently", "partially completed"]
    for action in action_types:
        for outcome in random.sample(outcomes, 2):
            user_q = f"I performed a {action} operation. The operation {outcome}. How do I verify the real state?"
            if outcome == "succeeded":
                response = (f"Even though the {action} appears to have succeeded, verify:\n"
                           f"1. Check the actual result (file exists, data correct, service running)\n"
                           f"2. Validate any side effects (logs, notifications, dependent systems)\n"
                           f"3. Run a smoke test to confirm functionality, not just existence")
            elif outcome == "failed silently":
                response = (f"Silent failure in {action} is dangerous. Investigate:\n"
                           f"1. Check logs (event viewer, app logs, syslog)\n"
                           f"2. Verify expected changes actually occurred\n"
                           f"3. Check exit/return codes — 0 doesn't always mean success\n"
                           f"4. Look for partial state that indicates mid-operation failure")
            else:
                response = (f"Partial completion of {action} needs careful assessment:\n"
                           f"1. Determine what completed and what didn't\n"
                           f"2. Check if partial state is dangerous (corrupted data? half-migrated?)\n"
                           f"3. Decide: complete the remaining work OR rollback to clean state\n"
                           f"4. Never leave a system in partial state for production")
            examples.append({
                "conversations": [
                    {"role": "system", "content": SYSTEM_PROMPTS["verification_oracle"]},
                    {"role": "user", "content": user_q},
                    {"role": "assistant", "content": response},
                ]
            })

    return examples


# ═══════════════════════════════════════════════════════════════
# ADAPTIVE RETRY — Expert 19 Training Data
# ═══════════════════════════════════════════════════════════════

def generate_adaptive_retry_data() -> List[Dict]:
    """Generate 500+ training examples for adaptive retry expert."""
    examples = []
    
    # ─── Category 1: Failure recovery strategies (150 examples) ───
    failure_recoveries = [
        {
            "failure": "Clicked on a button but nothing happened",
            "diagnosis": [
                "Button might be disabled (grayed out)",
                "Click coordinates were slightly off (missed the button)",
                "A modal dialog or overlay is blocking the button",
                "The page hasn't fully loaded yet",
                "JavaScript error preventing button handler from running",
            ],
            "retry_strategies": [
                "Strategy 1: Wait 2 seconds for page to fully load, then retry click",
                "Strategy 2: Verify exact button coordinates from screenshot, adjust click position",
                "Strategy 3: Check for overlays/modals — close them first if present",
                "Strategy 4: Try using keyboard alternative (Tab to button → Enter)",
                "Strategy 5: Refresh the page (F5) and try again",
                "Strategy 6: Use JavaScript console to trigger the button programmatically",
            ],
        },
        {
            "failure": "Terminal command returned 'command not found'",
            "diagnosis": [
                "The program is not installed",
                "The program is installed but not in PATH",
                "Typo in the command name",
                "Using a Linux command on Windows (or vice versa)",
                "Need to use the full path to the executable",
            ],
            "retry_strategies": [
                "Strategy 1: Check spelling — use tab completion to verify command exists",
                "Strategy 2: Search for the program: 'where <command>' (Windows) or 'which <command>' (Linux)",
                "Strategy 3: Install the missing program (apt install, brew install, winget install, etc.)",
                "Strategy 4: Use the Windows equivalent command (e.g., 'dir' instead of 'ls')",
                "Strategy 5: Use full path: 'C:\\Program Files\\...\\program.exe'",
                "Strategy 6: Add program directory to PATH and restart terminal",
            ],
        },
        {
            "failure": "File save failed with 'Permission denied'",
            "diagnosis": [
                "The directory requires administrator privileges",
                "The file is read-only",
                "Another process has the file locked",
                "The disk is write-protected",
                "Antivirus is blocking the write operation",
            ],
            "retry_strategies": [
                "Strategy 1: Save to a different location (Desktop or Documents)",
                "Strategy 2: Run the application as Administrator",
                "Strategy 3: Check file properties → uncheck 'Read-only'",
                "Strategy 4: Use Task Manager to find and close the process locking the file",
                "Strategy 5: Copy file to a user-writable location, edit there, then move back",
                "Strategy 6: Use PowerShell with elevated privileges: Start-Process ... -Verb RunAs",
            ],
        },
        {
            "failure": "Python script crashed with ImportError",
            "diagnosis": [
                "Required package not installed in current environment",
                "Wrong Python version active (2 vs 3, or wrong virtual env)",
                "Package installed in global env but script uses venv",
                "Package name differs from import name (e.g., pip install Pillow → import PIL)",
                "Circular import in the project code",
            ],
            "retry_strategies": [
                "Strategy 1: Install missing package: pip install <package_name>",
                "Strategy 2: Activate correct virtual environment first",
                "Strategy 3: Check pip install name vs import name (search PyPI)",
                "Strategy 4: Use python -m pip install to match the correct Python",
                "Strategy 5: Create a fresh virtual environment: python -m venv .venv && .venv\\Scripts\\activate",
                "Strategy 6: Install from requirements.txt if available: pip install -r requirements.txt",
            ],
        },
        {
            "failure": "Chrome page shows 'This site can't be reached'",
            "diagnosis": [
                "No internet connection",
                "DNS resolution failed",
                "Server is down",
                "URL is incorrect",
                "Firewall blocking the connection",
                "VPN/proxy interfering",
            ],
            "retry_strategies": [
                "Strategy 1: Check internet: try a known site like google.com",
                "Strategy 2: Verify URL spelling and protocol (http vs https)",
                "Strategy 3: Try alternative DNS: Settings → Network → DNS → use 8.8.8.8",
                "Strategy 4: Clear browser cache and cookies: Ctrl+Shift+Del",
                "Strategy 5: Try incognito mode: Ctrl+Shift+N",
                "Strategy 6: If localhost: verify the development server is running",
                "Strategy 7: Disable VPN/proxy temporarily and retry",
            ],
        },
        {
            "failure": "Drag and drop operation didn't register",
            "diagnosis": [
                "Mouse button released too early",
                "Drag started from wrong element",
                "Target drop zone not accepting the drag",
                "Application doesn't support drag and drop",
                "Mouse sensitivity too low causing micro-clicks instead of drag",
            ],
            "retry_strategies": [
                "Strategy 1: Use copy-paste instead (Ctrl+C → navigate → Ctrl+V)",
                "Strategy 2: Use cut-paste for move operations (Ctrl+X → Ctrl+V)",
                "Strategy 3: Use right-click → 'Move to' or 'Copy to' menu option",
                "Strategy 4: Use terminal commands (move, copy) for precise file operations",
                "Strategy 5: Try slower, more deliberate drag with longer hold time",
            ],
        },
        {
            "failure": "Screenshot capture came out blank/black",
            "diagnosis": [
                "Captured wrong monitor in multi-monitor setup",
                "Application uses hardware acceleration (DRM/protected content)",
                "Capture happened during screen transition",
                "Screenshot tool failed to initialize",
                "Window was minimized when screenshot was taken",
            ],
            "retry_strategies": [
                "Strategy 1: Wait 1 second for screen to stabilize, then retry",
                "Strategy 2: Use different screenshot method: Win+Shift+S, PrtScn, or Snipping Tool",
                "Strategy 3: Disable hardware acceleration in the target application",
                "Strategy 4: Ensure window is in foreground: Alt+Tab to bring it forward",
                "Strategy 5: Capture full screen instead of specific window",
            ],
        },
    ]
    
    for fr in failure_recoveries:
        diagnosis_text = "\n".join(f"  • {d}" for d in fr["diagnosis"])
        strategies_text = "\n".join(f"  {s}" for s in fr["retry_strategies"])
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": f"Failure encountered: {fr['failure']}. What should I do?"},
                {"role": "assistant", "content": (
                    f"## Failure Recovery Plan\n\n"
                    f"**Failure:** {fr['failure']}\n\n"
                    f"**Possible causes:**\n{diagnosis_text}\n\n"
                    f"**Recovery strategies (try in order):**\n{strategies_text}\n\n"
                    f"**Escalation path:** If all strategies fail:\n"
                    f"1. Take screenshot of current state for diagnosis\n"
                    f"2. Check system logs for additional error info\n"
                    f"3. Try a completely different approach to achieve the same goal\n"
                    f"4. Report the failure with full context for human review"
                )},
            ]
        })
    
    # ─── Category 2: Alternative approaches (120 examples) ───
    alternative_approaches = [
        ("Cannot install npm package due to permission error",
         "Primary approach failed: npm install -g <package>",
         [
             "Use npx instead of global install: npx <package>",
             "Install locally instead: npm install <package> (no -g flag)",
             "Use nvm to manage Node versions with proper permissions",
             "Fix npm permissions: npm config set prefix ~/.npm-global",
             "Use yarn instead: yarn add <package>",
         ]),
        ("Cannot open file because it's in use by another process",
         "Primary approach failed: Opening/editing the file directly",
         [
             "Find the locking process: Resource Monitor → CPU → Associated Handles → search filename",
             "Copy the file to a temp location, edit the copy, then swap back",
             "Use Process Explorer to find and close the handle",
             "Wait and retry: some processes release locks periodically",
             "Restart the locking application or service",
             "As last resort: restart the computer to release all locks",
         ]),
        ("Cannot type in a field because focus is stuck elsewhere",
         "Primary approach failed: Clicking on the target input field",
         [
             "Press Tab multiple times to cycle keyboard focus to the field",
             "Press Escape first to dismiss any active modal/dropdown, then click",
             "Click a neutral area (like the window title bar) first, then click the field",
             "Use Alt+Tab to switch away and back to reset focus",
             "If in a web form: try clicking the field's label instead of the field itself",
         ]),
        ("Git push rejected: non-fast-forward update",
         "Primary approach failed: git push origin main",
         [
             "Pull first then push: git pull --rebase origin main && git push",
             "If you want to keep your changes: git pull origin main → resolve conflicts → git push",
             "If you want to force (DANGEROUS): git push --force-with-lease origin main",
             "Create a new branch: git checkout -b my-changes && git push origin my-changes",
             "Stash, pull, pop: git stash → git pull → git stash pop → git push",
         ]),
    ]
    
    for problem, primary, alternatives in alternative_approaches:
        alt_text = "\n".join(f"  {i+1}. {a}" for i, a in enumerate(alternatives))
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": f"Problem: {problem}\nFailed attempt: {primary}\nWhat are my alternatives?"},
                {"role": "assistant", "content": (
                    f"**Problem:** {problem}\n"
                    f"**Failed approach:** {primary}\n\n"
                    f"**Alternative approaches (ordered by likelihood of success):**\n{alt_text}\n\n"
                    f"**Selection criteria:** Start with the least disruptive option. "
                    f"If it fails, escalate to more aggressive approaches. "
                    f"Always verify the problem is resolved after each attempt."
                )},
            ]
        })
    
    # ─── Category 3: Retry with exponential backoff scenarios (80 examples) ───
    timing_scenarios = [
        "Network request timed out",
        "Application is still loading",
        "Service returned 503 (Service Unavailable)",
        "Database connection failed",
        "File system operation returned BUSY",
        "API rate limit exceeded (429 Too Many Requests)",
        "Process hasn't started yet",
        "Download speed dropped to 0",
    ]
    
    for scenario in timing_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": f"Timing issue: {scenario}. Should I retry? How long should I wait?"},
                {"role": "assistant", "content": (
                    f"**Issue:** {scenario}\n\n"
                    f"**Retry strategy: Exponential backoff with jitter**\n\n"
                    f"| Attempt | Wait Time | Action |\n"
                    f"|---------|-----------|--------|\n"
                    f"| 1st retry | 1-2 seconds | Simple retry |\n"
                    f"| 2nd retry | 3-5 seconds | Retry with fresh state |\n"
                    f"| 3rd retry | 8-15 seconds | Check prerequisites, then retry |\n"
                    f"| 4th retry | 30-60 seconds | Investigate root cause |\n"
                    f"| 5th retry | 2-5 minutes | Try alternative approach |\n\n"
                    f"**Important:** After each wait, verify the blocking condition has changed "
                    f"before retrying. Don't blindly retry if the root cause hasn't been addressed.\n\n"
                    f"**Max retries:** 5. After that, escalate or use a different strategy entirely."
                )},
            ]
        })
    
    # ─── Category 4: Multi-turn recovery sessions (30 examples) ───
    multi_turn_recovery = [
        {
            "turns": [
                ("I tried to run 'npm start' but got EADDRINUSE error on port 3000.",
                 "**Error: Port 3000 already in use.** Good news — this is a common, easy-to-fix issue.\n\n"
                 "**Immediate diagnosis:**\n"
                 "Run: `netstat -ano | findstr :3000`\n\n"
                 "This will show what process is using port 3000 and its PID.\n"
                 "Can you run that and tell me what it shows?"),
                ("It shows: TCP 0.0.0.0:3000 LISTENING 12456",
                 "PID 12456 is holding port 3000. Let me identify it:\n\n"
                 "Run: `tasklist | findstr 12456`\n\n"
                 "This tells us which program it is. If it's an old node.exe instance, we can safely kill it."),
                ("It says 'node.exe 12456'",
                 "**Confirmed:** A zombie Node.js process from a previous run.\n\n"
                 "**Fix (choose one):**\n"
                 "1. Kill it: `taskkill /PID 12456 /F`\n"
                 "2. Then retry: `npm start`\n\n"
                 "**Prevention for next time:**\n"
                 "- Always stop the server with Ctrl+C (not just closing the terminal)\n"
                 "- Add a `prestart` script to package.json: `\"prestart\": \"npx kill-port 3000\"`\n"
                 "- Or use `nodemon` which handles restarts cleanly\n\n"
                 "After killing the process, port 3000 should be immediately available."),
            ]
        },
        {
            "turns": [
                ("My Python script keeps crashing with MemoryError when processing a large CSV.",
                 "**Root cause:** You're loading the entire CSV into memory at once.\n\n"
                 "**How big is the file?** And are you using pandas `read_csv()` without parameters?\n\n"
                 "While you check, here are the common solutions ranked by easiness:\n"
                 "1. Use chunked reading: `pd.read_csv(file, chunksize=10000)`\n"
                 "2. Use only needed columns: `pd.read_csv(file, usecols=['col1', 'col2'])`\n"
                 "3. Downcast dtypes: `pd.read_csv(file, dtype={'id': 'int32', 'name': 'category'})`\n"
                 "4. Use Dask for out-of-core processing: `import dask.dataframe as dd; dd.read_csv(file)`\n\n"
                 "How large is the file?"),
                ("It's 12 GB. I'm using pd.read_csv with no parameters.",
                 "12 GB CSV — pandas needs roughly **3-5x the file size** in RAM (36-60 GB). That's why it crashes.\n\n"
                 "**Best approach for 12 GB: Chunked processing**\n\n"
                 "```python\n"
                 "chunks = pd.read_csv('big.csv', chunksize=50_000)\n"
                 "results = []\n"
                 "for chunk in chunks:\n"
                 "    # Process each 50K-row chunk\n"
                 "    partial = chunk.groupby('category').sum()\n"
                 "    results.append(partial)\n"
                 "final = pd.concat(results).groupby(level=0).sum()\n"
                 "```\n\n"
                 "**Alternative if you need the full dataset:** Use `polars` (faster, lower memory) or `dask` (lazy evaluation).\n\n"
                 "This should reduce peak memory from ~40 GB to ~200 MB."),
            ]
        },
    ]

    for mt in multi_turn_recovery:
        convs = [{"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]}]
        for user_msg, asst_msg in mt["turns"]:
            convs.append({"role": "user", "content": user_msg})
            convs.append({"role": "assistant", "content": asst_msg})
        examples.append({"conversations": convs})

    # ─── Category 5: Specific detailed recovery patterns (200 examples) ───
    detailed_recoveries = [
        {"error": "VS Code won't open — just shows splash then closes",
         "recovery": "**Escalation ladder:**\n\n"
                     "1. **Quick fix:** Delete user settings cache:\n"
                     "   `Remove-Item -Recurse $env:APPDATA\\Code\\Cache`\n"
                     "   `Remove-Item -Recurse $env:APPDATA\\Code\\CachedData`\n"
                     "2. **If still crashes:** Disable extensions:\n"
                     "   `code --disable-extensions`\n"
                     "   If this works → a bad extension is the cause. Enable one-by-one to find it.\n"
                     "3. **If still crashes:** Reset all settings:\n"
                     "   Rename `$env:APPDATA\\Code\\User\\settings.json` to `settings.json.bak`\n"
                     "4. **Nuclear option:** Uninstall → delete `$env:APPDATA\\Code` → reinstall\n\n"
                     "**Data safety:** Your extensions/settings are synced if you signed in. "
                     "Your workspace files are NOT affected by any of these steps."},
        {"error": "npm install fails with ERESOLVE peer dependency conflict",
         "recovery": "**Understanding the error:** Two packages need different versions of the same dependency.\n\n"
                     "**Solutions (safest to riskiest):**\n"
                     "1. `npm install --legacy-peer-deps` — ignores peer dependency checks (usually safe)\n"
                     "2. `npm install --force` — forces installation regardless of conflicts\n"
                     "3. Manually update the conflicting package to a compatible version\n"
                     "4. Use `npx npm-check-updates` to find upgrades that resolve the conflict\n"
                     "5. Delete `node_modules/` and `package-lock.json`, then `npm install` fresh\n\n"
                     "**Start with option 1** — it's what npm v6 did by default and rarely causes issues."},
        {"error": "Git says 'detached HEAD' and I don't know what branch I'm on",
         "recovery": "**Don't panic — your commits are safe.**\n\n"
                     "**What happened:** You checked out a commit directly (not a branch).\n\n"
                     "**Recovery:**\n"
                     "1. See where you are: `git log --oneline -5`\n"
                     "2. If you have uncommitted work: `git stash` first\n"
                     "3. **To go back to a branch:** `git checkout main` (or whatever branch you want)\n"
                     "4. **To save current position as a new branch:** `git checkout -b recovery-branch`\n"
                     "5. If you stashed: `git stash pop`\n\n"
                     "**If you made commits in detached HEAD:**\n"
                     "- Note the commit hash: `git log --oneline -1`\n"
                     "- Switch to target branch: `git checkout main`\n"
                     "- Cherry-pick your commits: `git cherry-pick <hash>`"},
        {"error": "Windows won't let me delete a file — says 'in use by another process'",
         "recovery": "**Finding and releasing the lock:**\n\n"
                     "1. **Quick try:** Close obvious programs that might use the file\n"
                     "2. **Find the locker:**\n"
                     "   - Resource Monitor (resmon.exe) → CPU tab → Associated Handles → type filename\n"
                     "   - OR: `handle.exe filename` (from Sysinternals suite)\n"
                     "3. **Release it:**\n"
                     "   - Close the program that's using it\n"
                     "   - If it's a system process: restart that service\n"
                     "   - If nothing works: `taskkill /IM process.exe /F`\n"
                     "4. **Schedule for deletion on reboot:**\n"
                     "   - PowerShell: `Move-ItemAtReboot -Path 'file' -Destination $null`\n"
                     "   - Or add to PendingFileRenameOperations in registry\n\n"
                     "**Last resort:** Boot into Safe Mode where minimal processes are running."},
        {"error": "Python virtual environment's pip installs packages globally instead of in venv",
         "recovery": "**This means the venv isn't properly activated.**\n\n"
                     "**Diagnosis:**\n"
                     "```\n"
                     "where pip    # Should show .venv\\Scripts\\pip.exe, NOT C:\\Python...\\pip.exe\n"
                     "echo $env:VIRTUAL_ENV  # Should show venv path, not empty\n"
                     "```\n\n"
                     "**Fix:**\n"
                     "1. Activate properly: `.venv\\Scripts\\Activate.ps1` (PowerShell) or `.venv\\Scripts\\activate.bat` (CMD)\n"
                     "2. If PowerShell blocks: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`\n"
                     "3. Use explicit pip: `.venv\\Scripts\\pip.exe install package` (bypass activation)\n"
                     "4. Use python -m: `.venv\\Scripts\\python.exe -m pip install package`\n\n"
                     "**Prevention:** Always check for `(.venv)` prompt prefix before running pip."},
        {"error": "Browser shows 'Your connection is not private' (SSL certificate error)",
         "recovery": "**Assessment:** This is a security warning — proceed carefully.\n\n"
                     "**If it's YOUR development server (localhost):**\n"
                     "- Safe to bypass: Click 'Advanced' → 'Proceed to localhost (unsafe)'\n"
                     "- Better fix: use `http://` instead of `https://` for local dev\n"
                     "- Best fix: generate self-signed cert and add to trusted store\n\n"
                     "**If it's a public website:**\n"
                     "- Check the date on your computer (expired clock causes cert errors)\n"
                     "- Try another browser (if it works → your browser's cert store needs update)\n"
                     "- DO NOT proceed if this is a banking/sensitive site\n\n"
                     "**If it's an internal company site:**\n"
                     "- Your company's CA cert may not be installed\n"
                     "- Contact IT for the root certificate to install"},
        {"error": "Docker build fails with 'no space left on device'",
         "recovery": "**Docker tends to accumulate unused data FAST.**\n\n"
                     "**Recovery steps:**\n"
                     "1. See what's using space: `docker system df`\n"
                     "2. **Quick cleanup:** `docker system prune` (removes unused containers, networks, images)\n"
                     "3. **Aggressive cleanup:** `docker system prune -a --volumes` (removes ALL unused, including volumes)\n"
                     "4. **Targeted:** \n"
                     "   - `docker image prune -a` (old images)\n"
                     "   - `docker volume prune` (orphaned volumes)\n"
                     "   - `docker builder prune` (build cache — often 10+ GB)\n"
                     "5. Check Docker Desktop settings → Resources → increase disk image size\n\n"
                     "**Prevention:** Add `docker system prune -f` to weekly schedule."},
        {"error": "Excel file won't open — 'file format or extension is not valid'",
         "recovery": "**Possible causes and fixes:**\n\n"
                     "1. **Wrong extension:** File might be CSV renamed to .xlsx\n"
                     "   - Try: Open Excel → File → Open → change filter to 'All Files' → select the file\n"
                     "2. **Corrupted file:**\n"
                     "   - Open Excel → File → Open → select file → click dropdown on 'Open' button → 'Open and Repair'\n"
                     "3. **File is actually a different format:**\n"
                     "   - Open in Notepad to peek: if it starts with `PK` → it's a zip (valid .xlsx)\n"
                     "   - If it's readable text → it's CSV/TSV, not Excel format\n"
                     "4. **Temporary file:**\n"
                     "   - Check for `~$filename.xlsx` — that's a lock file, not the real file\n"
                     "   - The real file might be in a different location\n\n"
                     "**Data recovery:** If none work, try LibreOffice (more tolerant of format issues)."},
        {"error": "PowerShell script runs fine manually but fails in Task Scheduler",
         "recovery": "**Common cause: different execution context.**\n\n"
                     "Task Scheduler runs scripts as a different user, with different environment.\n\n"
                     "**Debugging steps:**\n"
                     "1. **Add logging:** Start script with:\n"
                     "   ```\n"
                     "   Start-Transcript -Path C:\\Logs\\task_$(Get-Date -f yyyyMMdd).log\n"
                     "   ```\n"
                     "2. **Fix execution policy:** In Task Scheduler action:\n"
                     "   - Program: `powershell.exe`\n"
                     "   - Arguments: `-ExecutionPolicy Bypass -File \"C:\\Scripts\\task.ps1\"`\n"
                     "3. **Fix working directory:** Set 'Start in' field in task action\n"
                     "4. **Check user context:** Does the task user have file/network access?\n"
                     "5. **PATH differences:** Use full paths for all executables in the script\n"
                     "6. **Network drives:** Mapped drives don't exist in scheduled tasks — use UNC paths\n\n"
                     "**Test:** Right-click task → Run → check the log file immediately."},
        {"error": "Application hangs and Task Manager won't end the process",
         "recovery": "**Escalation ladder for unkillable processes:**\n\n"
                     "1. **Task Manager → End Task:** Already failed. Try 'End process tree' instead.\n"
                     "2. **Elevated kill:**\n"
                     "   - Open PowerShell as Admin\n"
                     "   - `Stop-Process -Id <PID> -Force`\n"
                     "3. **Taskkill with force:**\n"
                     "   - `taskkill /PID <PID> /F /T` (force + tree = kill children too)\n"
                     "4. **Wait for IO:** If process is stuck on disk I/O, it might be in a kernel wait state\n"
                     "   - These can ONLY end when the I/O completes or times out\n"
                     "   - Check Resource Monitor → Disk tab for the process\n"
                     "5. **If truly unkillable:** The process is in kernel mode\n"
                     "   - Restart the associated Windows service\n"
                     "   - Last resort: restart the computer\n\n"
                     "**Safety:** Save work in OTHER applications first before forced termination."},
    ]

    for dr in detailed_recoveries:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": f"Error: {dr['error']}. Previous attempts to fix failed. What do I do?"},
                {"role": "assistant", "content": dr["recovery"]},
            ]
        })

    # ═══ v2.0: ADAPTIVE RETRY EXPANSION — Korean, Rate Limit, Auth, Cascading ═══

    # Korean error recovery
    korean_recovery = [
        {"error": "Python에서 'ModuleNotFoundError: No module named pandas' 오류가 발생했습니다",
         "recovery": "**진단:** pandas 패키지가 설치되지 않았거나, 잘못된 Python 환경에서 실행 중입니다.\n\n"
                     "**복구 단계:**\n"
                     "1. 현재 Python 확인: `python --version` 및 `which python` (또는 `where python`)\n"
                     "2. 가상환경 확인: 프롬프트에 `(venv)`가 보이는지 확인\n"
                     "3. 설치 시도: `pip install pandas`\n"
                     "4. 그래도 안 되면: `python -m pip install pandas`\n"
                     "5. 여전히 실패: `pip install --user pandas`\n\n"
                     "**근본 원인 확인:** `pip list | findstr pandas` 로 이미 설치되어 있는지 확인.\n"
                     "가상환경 밖에서 설치했다면 환경 안에서 다시 설치 필요."},
        {"error": "PowerShell에서 '이 시스템에서 스크립트를 실행할 수 없으므로...' 오류",
         "recovery": "**진단:** PowerShell 실행 정책이 Restricted로 설정되어 있습니다.\n\n"
                     "**복구:**\n"
                     "1. 관리자 PowerShell 열기 (시작 > PowerShell > 마우스 우클릭 > 관리자로 실행)\n"
                     "2. `Set-ExecutionPolicy RemoteSigned -Scope CurrentUser`\n"
                     "3. 'Y' 입력하여 확인\n"
                     "4. 스크립트 다시 실행\n\n"
                     "**대안:** 정책 변경 없이 한 번만 실행:\n"
                     "`powershell -ExecutionPolicy Bypass -File script.ps1`"},
        {"error": "Git push에서 'rejected - non-fast-forward' 에러",
         "recovery": "**진단:** 리모트에 로컬에 없는 커밋이 있습니다.\n\n"
                     "**복구 (안전한 방법):**\n"
                     "1. `git fetch origin`\n"
                     "2. `git rebase origin/main` (또는 `git merge origin/main`)\n"
                     "3. 충돌 발생 시: 파일 수정 → `git add .` → `git rebase --continue`\n"
                     "4. `git push origin main`\n\n"
                     "**절대 하지 말 것:** `git push --force` (다른 사람의 커밋을 삭제할 수 있음)\n"
                     "**예외:** 개인 브랜치에서만 `git push --force-with-lease` 사용 가능"},
    ]
    for kr in korean_recovery:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": kr["error"]},
                {"role": "assistant", "content": kr["recovery"]},
            ]
        })

    # Rate limit recovery
    rate_limit_recovery = [
        {"error": "GitHub API returns '403 API rate limit exceeded'. I need to make 500 more API calls",
         "recovery": "**Rate Limit Recovery Strategy:**\n\n"
                     "1. **Check reset time:** `curl -I https://api.github.com/rate_limit`\n"
                     "   → Look for `X-RateLimit-Reset` (Unix timestamp)\n"
                     "2. **Immediate options:**\n"
                     "   a. Wait for reset (usually 60 minutes for unauthenticated)\n"
                     "   b. Authenticate: add `Authorization: token YOUR_TOKEN` → 5000 req/hr\n"
                     "   c. Use conditional requests: `If-None-Match` header → 304 responses don't count\n"
                     "3. **For 500 calls with 5000/hr limit:**\n"
                     "   - Can complete in ~6 minutes (pace at 90 req/min to be safe)\n"
                     "   - Add `time.sleep(0.7)` between requests\n"
                     "4. **Long-term fix:**\n"
                     "   - Cache responses locally\n"
                     "   - Use GraphQL API (1 call = multiple REST calls)\n"
                     "   - Implement exponential backoff: 1s → 2s → 4s → 8s → 16s"},
        {"error": "OpenAI API returns '429 Rate limit reached for requests per minute'",
         "recovery": "**OpenAI Rate Limit Strategy:**\n\n"
                     "1. **Immediate:** Wait 20-60 seconds, then retry\n"
                     "2. **Implement exponential backoff:**\n"
                     "   ```python\n"
                     "   import time, random\n"
                     "   for attempt in range(5):\n"
                     "       try:\n"
                     "           response = openai.chat.completions.create(...)\n"
                     "           break\n"
                     "       except openai.RateLimitError:\n"
                     "           wait = (2 ** attempt) + random.random()\n"
                     "           time.sleep(wait)\n"
                     "   ```\n"
                     "3. **Batch requests:** Use batch API for non-urgent processing\n"
                     "4. **Rate-limit aware queue:**\n"
                     "   - Track requests per minute\n"
                     "   - Pause when approaching limit (80% of quota)\n"
                     "5. **Reduce token usage:** Shorter prompts = more requests per minute"},
    ]
    for rl in rate_limit_recovery:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": rl["error"]},
                {"role": "assistant", "content": rl["recovery"]},
            ]
        })

    # Authentication/token expiry retry
    auth_recovery = [
        {"error": "SSH key authentication failed when trying to git push",
         "recovery": "**SSH Key Recovery Escalation:**\n\n"
                     "**Level 1: Test connection**\n"
                     "`ssh -T git@github.com` → should say 'Hi username!'\n\n"
                     "**Level 2: Check SSH agent**\n"
                     "- `ssh-add -l` → lists loaded keys\n"
                     "- If empty: `ssh-add ~/.ssh/id_ed25519`\n\n"
                     "**Level 3: Check key is on GitHub**\n"
                     "- `cat ~/.ssh/id_ed25519.pub` → copy\n"
                     "- GitHub → Settings → SSH Keys → check it's listed\n\n"
                     "**Level 4: Generate new key**\n"
                     "- `ssh-keygen -t ed25519 -C 'your@email.com'`\n"
                     "- Add to GitHub\n"
                     "- Test: `ssh -T git@github.com`\n\n"
                     "**Fallback: Use HTTPS instead**\n"
                     "`git remote set-url origin https://github.com/user/repo.git`"},
        {"error": "Docker login fails with '401 Unauthorized' to private registry",
         "recovery": "**Docker Auth Recovery:**\n\n"
                     "1. Clear cached credentials: `docker logout registry.io`\n"
                     "2. Re-login: `docker login registry.io -u username`\n"
                     "3. If password expired: regenerate token in registry UI\n"
                     "4. Check credentials file: `cat ~/.docker/config.json`\n"
                     "5. For AWS ECR: `aws ecr get-login-password | docker login --username AWS --password-stdin ...`\n"
                     "6. For GCR: `gcloud auth configure-docker`\n\n"
                     "**Common mistake:** Registry URL mismatch — `docker.io` vs custom `registry.company.com`"},
    ]
    for ar in auth_recovery:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": ar["error"]},
                {"role": "assistant", "content": ar["recovery"]},
            ]
        })

    # Cascading failure recovery
    cascading_failures = [
        {"error": "Backend API is down, which caused the frontend to show errors, which caused users to submit duplicate requests",
         "recovery": "**Cascading Failure Recovery (reverse order):**\n\n"
                     "**Step 1: Stop the bleeding (frontend)**\n"
                     "- Enable maintenance page immediately\n"
                     "- Or add a circuit breaker: if API fails 3x, show 'Please try later' instead of retrying\n\n"
                     "**Step 2: Fix root cause (backend)**\n"
                     "- Check server logs: `tail -f /var/log/app.log`\n"
                     "- Common causes: OOM kill, disk full, DB connection pool exhausted\n"
                     "- Restart: `systemctl restart app`\n"
                     "- Verify: `curl localhost:3000/health`\n\n"
                     "**Step 3: Clean up consequences (duplicate requests)**\n"
                     "- Identify duplicates: `SELECT *, COUNT(*) FROM orders GROUP BY idempotency_key HAVING COUNT(*) > 1`\n"
                     "- Remove duplicates, keeping the first\n"
                     "- Refund any double-charges\n\n"
                     "**Step 4: Prevention**\n"
                     "- Add idempotency keys to all mutations\n"
                     "- Implement circuit breaker pattern\n"
                     "- Add health check monitoring with auto-restart"},
        {"error": "Disk full caused log rotation to fail, which caused the log file to grow to fill remaining space, which caused the database to crash",
         "recovery": "**Disk Space Cascade Recovery:**\n\n"
                     "**Emergency (immediate):**\n"
                     "1. Clear space NOW:\n"
                     "   - `find /var/log -name '*.log' -size +100M -exec truncate -s 0 {} \\;`\n"
                     "   - Or: `journalctl --vacuum-size=100M`\n"
                     "   - Clear temp: `rm -rf /tmp/*`\n\n"
                     "**Fix database:**\n"
                     "2. Restart DB: `systemctl restart postgresql`\n"
                     "3. If corrupted: `pg_resetwal` (DANGEROUS — last resort)\n"
                     "4. If won't start: check `pg_log` for the specific error\n\n"
                     "**Fix log rotation:**\n"
                     "5. Check logrotate config: `cat /etc/logrotate.d/app`\n"
                     "6. Run manually: `logrotate -f /etc/logrotate.d/app`\n"
                     "7. Set max size: `maxsize 500M`\n\n"
                     "**Prevention:** Disk usage alert at 80%, auto-cleanup at 90%"},
    ]
    for cf in cascading_failures:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": cf["error"]},
                {"role": "assistant", "content": cf["recovery"]},
            ]
        })

    # Graceful degradation strategies
    degradation_strategies = [
        {"scenario": "The main AI model API is down but we need to keep serving users",
         "strategy": "**Graceful Degradation Ladder:**\n\n"
                     "1. **Primary:** Full AI model (GPT-4 / Claude)\n"
                     "2. **Fallback 1:** Smaller/faster model (GPT-3.5 / Haiku)\n"
                     "3. **Fallback 2:** Cached responses for common queries\n"
                     "4. **Fallback 3:** Rule-based responses (if/else templates)\n"
                     "5. **Fallback 4:** 'Service degraded' message with ETA\n\n"
                     "**Implementation:**\n"
                     "```python\n"
                     "async def get_response(query):\n"
                     "    for provider in [primary_model, fallback_model, cache, rules]:\n"
                     "        try:\n"
                     "            return await provider.respond(query)\n"
                     "        except ServiceUnavailable:\n"
                     "            continue\n"
                     "    return DEGRADED_MESSAGE\n"
                     "```"},
        {"scenario": "Network connection is intermittent — works sometimes, fails sometimes",
         "strategy": "**Intermittent Network Strategy:**\n\n"
                     "1. **Detect:** Track last 10 requests' success/failure ratio\n"
                     "2. **Adapt:** If failure rate > 30%:\n"
                     "   - Increase timeouts (2x)\n"
                     "   - Reduce request frequency\n"
                     "   - Queue non-urgent requests\n"
                     "3. **Retry wisely:** Not all failures are equal:\n"
                     "   - Connection refused → wait and retry (server might be restarting)\n"
                     "   - Timeout → retry with longer timeout\n"
                     "   - DNS failure → switch to IP address directly\n"
                     "4. **Offline mode:**\n"
                     "   - Cache critical resources locally\n"
                     "   - Queue writes for when connection restores\n"
                     "   - Show cached data with 'last updated' timestamp"},
    ]
    for ds in degradation_strategies:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                {"role": "user", "content": ds["scenario"]},
                {"role": "assistant", "content": ds["strategy"]},
            ]
        })

    # Combinatorial: error type × severity × recovery approach
    error_types = [
        "FileNotFoundError", "PermissionError", "ConnectionRefusedError",
        "TimeoutError", "OutOfMemoryError", "DiskFullError",
        "AuthenticationError", "SyntaxError", "ImportError",
    ]
    severity_levels = ["minor (non-blocking)", "major (task blocked)", "critical (data at risk)"]
    for error in error_types:
        for severity in random.sample(severity_levels, 2):
            user_q = f"Getting {error} with {severity} impact. How should I retry?"
            if "minor" in severity:
                response = (f"{error} with minor impact — safe to retry:\n"
                           f"1. Log the error for tracking\n"
                           f"2. Wait 1-2 seconds\n"
                           f"3. Retry the operation (up to 3 times)\n"
                           f"4. If still failing, skip and continue with next task")
            elif "major" in severity:
                response = (f"{error} blocking the task — escalated retry:\n"
                           f"1. Diagnose root cause before retrying\n"
                           f"2. Fix the underlying issue (permissions, path, connection)\n"
                           f"3. Retry with modified parameters\n"
                           f"4. If fix unclear, try alternative approach entirely")
            else:
                response = (f"{error} with data at risk — careful recovery:\n"
                           f"1. STOP all operations immediately\n"
                           f"2. Assess data state — is anything corrupted?\n"
                           f"3. Create backup of current state before ANY retry\n"
                           f"4. Fix root cause thoroughly\n"
                           f"5. Run integrity checks after retry succeeds")
            examples.append({
                "conversations": [
                    {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                    {"role": "user", "content": user_q},
                    {"role": "assistant", "content": response},
                ]
            })

    return examples


# ═══════════════════════════════════════════════════════════════
# V3.0: CROSS-EXPERT CHAIN SCENARIOS
# ═══════════════════════════════════════════════════════════════

def generate_cross_expert_data() -> List[Dict]:
    """
    V3.0: Generate 500+ cross-expert scenarios that exercise
    multiple new experts in sequence. These train the router to
    properly handoff between experts within a single conversation.
    """
    examples = []

    # ─── Ground → Verify (150 examples) ───
    # Expert 16 identifies element → action executes → Expert 18 verifies
    ground_verify_scenarios = [
        {
            "task": "Click the Save button in Notepad",
            "ground_desc": "Blue 'Save' button at (780, 520), size 80×30, enabled",
            "action": "click at (780, 520)",
            "verify_q": "After clicking Save, the title bar no longer shows '*' before filename",
            "verify_result": "SUCCESS — title changed from '*Untitled' to 'Untitled', confirming save completed",
        },
        {
            "task": "Open File menu in Chrome",
            "ground_desc": "'File' in menu bar at (25, 12), clickable, not expanded",
            "action": "click at (25, 12)",
            "verify_q": "The File dropdown menu should now be visible with options like New Tab, New Window",
            "verify_result": "SUCCESS — dropdown appeared with 10 menu items including 'New Tab (Ctrl+T)', 'New Window (Ctrl+N)'",
        },
        {
            "task": "Enable Dark Mode in Windows Settings",
            "ground_desc": "'Dark' radio button at (500, 380), currently unselected, enabled",
            "action": "click at (500, 380)",
            "verify_q": "The Settings UI should have switched to dark theme, background should be dark",
            "verify_result": "SUCCESS — background changed from white (#FFFFFF) to dark gray (#1E1E1E), radio button now shows filled state",
        },
        {
            "task": "Close a browser tab",
            "ground_desc": "Tab close '×' button at (285, 12), size 16×16, visible on hover",
            "action": "click at (285, 12)",
            "verify_q": "The tab should be removed and adjacent tab should become active",
            "verify_result": "SUCCESS — tab count decreased from 5 to 4, next tab is now active with blue underline",
        },
        {
            "task": "Check a checkbox in a web form",
            "ground_desc": "'I agree to terms' checkbox at (340, 450), unchecked, enabled",
            "action": "click at (340, 450)",
            "verify_q": "The checkbox should now display a checkmark and the Submit button should become enabled",
            "verify_result": "SUCCESS — checkbox shows ✓, Submit button changed from gray (disabled) to blue (enabled)",
        },
    ]

    for scenario in ground_verify_scenarios:
        # Multi-turn: ground → verify
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["visual_grounding"]},
                {"role": "user", "content": f"I need to: {scenario['task']}. Where is the target element?"},
                {"role": "assistant", "content": f"Target identified: {scenario['ground_desc']}. Recommended action: {scenario['action']}."},
                {"role": "user", "content": f"I performed the action. Now verify: {scenario['verify_q']}"},
                {"role": "assistant", "content": f"Verification: {scenario['verify_result']}"},
            ],
            "_expert_chain": [16, 18],
        })

    # Generate more ground→verify from combinations
    apps = ["Chrome", "VS Code", "Excel", "PowerPoint", "Windows Explorer", "Terminal",
            "Notepad", "Paint", "Settings", "Task Manager", "Discord", "Slack"]
    elements = [
        ("button", "click", "button state changed (enabled→pressed→released)"),
        ("tab", "click", "tab became active, content area updated"),
        ("menu item", "click", "dropdown appeared or action executed"),
        ("checkbox", "click", "check state toggled"),
        ("text field", "click then type", "cursor appeared, typed text visible"),
        ("link", "click", "page navigated, URL changed in address bar"),
        ("slider", "drag", "value changed, visual indicator moved"),
        ("toggle switch", "click", "switch flipped from off to on"),
        ("dropdown", "click", "options list appeared below the control"),
        ("close button", "click", "window/tab closed, focus shifted"),
    ]

    for app in apps:
        for elem_type, action_type, expected_change in random.sample(elements, min(5, len(elements))):
            x, y = random.randint(50, 1870), random.randint(30, 1050)
            examples.append({
                "conversations": [
                    {"role": "system", "content": SYSTEM_PROMPTS["visual_grounding"]},
                    {"role": "user", "content": f"In {app}, I need to interact with a {elem_type}. Locate it and tell me what to do."},
                    {"role": "assistant", "content": (
                        f"I found a {elem_type} in {app} at coordinates ({x}, {y}).\n"
                        f"Action: {action_type} at ({x}, {y}).\n"
                        f"Expected result: {expected_change}")},
                    {"role": "user", "content": f"Done. Did it work? The screen looks different now."},
                    {"role": "assistant", "content": (
                        f"Verification check for {action_type} on {elem_type} in {app}:\n"
                        f"Expected: {expected_change}\n"
                        f"Look for these indicators:\n"
                        f"1. Visual state change (color, position, visibility)\n"
                        f"2. Content update (new text, new view, new panel)\n"
                        f"3. No error messages or warnings appeared\n"
                        f"If all indicators match, the action was successful.")},
                ],
                "_expert_chain": [16, 18],
            })

    # ─── Workflow → Verify (150 examples) ───
    # Expert 17 plans workflow → Expert 18 verifies each step
    workflow_verify_scenarios = [
        {
            "workflow": "Copy data from a webpage into an Excel spreadsheet",
            "steps": [
                "1. Open Chrome and navigate to the data source URL",
                "2. Select the data table on the webpage (Ctrl+A or manual selection)",
                "3. Copy the selected data (Ctrl+C)",
                "4. Switch to Excel (Alt+Tab)",
                "5. Click cell A1 in the target sheet",
                "6. Paste the data (Ctrl+V)",
            ],
            "verify_points": [
                "Step 1: Chrome opened, page loaded (check URL bar matches target)",
                "Step 2: Data highlighted with blue selection overlay",
                "Step 3: Clipboard now contains data (no visual change expected)",
                "Step 4: Excel is now the active window (title bar shows Excel)",
                "Step 5: Cell A1 has a blue border indicating selection",
                "Step 6: Data appears in cells, formatting may differ from web",
            ],
        },
        {
            "workflow": "Create a PDF from a Word document",
            "steps": [
                "1. Open the Word document",
                "2. Click File → Export → Create PDF/XPS",
                "3. Choose save location and filename",
                "4. Click 'Publish' button",
                "5. Verify the PDF was created in the target location",
            ],
            "verify_points": [
                "Step 1: Word shows document title in title bar",
                "Step 2: Export dialog appeared with PDF option highlighted",
                "Step 3: File dialog shows correct path and name",
                "Step 4: Progress bar appeared and completed",
                "Step 5: PDF file exists in Explorer with correct size > 0 bytes",
            ],
        },
        {
            "workflow": "Send an email with attachment from Outlook",
            "steps": [
                "1. Open Outlook and click 'New Email'",
                "2. Enter recipient in To field",
                "3. Type subject and body",
                "4. Click 'Attach File' and browse to file",
                "5. Select the file and click Insert",
                "6. Click Send",
            ],
            "verify_points": [
                "Step 1: New email composition window opened",
                "Step 2: Recipient address appears in To field with valid format",
                "Step 3: Subject line and body text visible",
                "Step 4: File browser dialog opened",
                "Step 5: Attachment appears below subject with filename and size",
                "Step 6: Email window closed, item appears in Sent Items",
            ],
        },
    ]

    for scenario in workflow_verify_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                {"role": "user", "content": f"Plan the workflow: {scenario['workflow']}"},
                {"role": "assistant", "content": "Workflow plan:\n" + "\n".join(scenario["steps"])},
                {"role": "user", "content": "How do I verify each step was successful?"},
                {"role": "assistant", "content": "Verification checkpoints:\n" + "\n".join(scenario["verify_points"])},
            ],
            "_expert_chain": [17, 18],
        })

    # Generate more workflow→verify from task templates
    task_templates = [
        ("Download a file from the web and open it in {app}",
         ["Open browser", "Navigate to URL", "Click download link", "Wait for download", "Open file in {app}"]),
        ("Create a new {filetype} file and save it to {path}",
         ["Open {app}", "Create new file", "Add content", "Save As to {path}", "Verify file exists"]),
        ("Update system settings for {setting}",
         ["Open Settings", "Navigate to {setting} section", "Change value", "Click Apply", "Verify change took effect"]),
        ("Install a program from the web",
         ["Open browser", "Search for program", "Download installer", "Run installer", "Follow wizard", "Verify installation"]),
        ("Organize files from Downloads into categorized folders",
         ["Open Explorer to Downloads", "Create category folders", "Sort files by type", "Move files to folders", "Verify all moved"]),
    ]
    app_list = ["Excel", "Word", "VS Code", "Notepad", "Paint", "PowerPoint"]
    filetype_list = ["spreadsheet", "document", "script", "presentation", "image", "text file"]
    path_list = ["Desktop", "Documents", "D:\\Projects", "C:\\Work", "~/Documents"]
    setting_list = ["display resolution", "default browser", "power plan", "mouse speed", "keyboard layout"]

    for template_desc, template_steps in task_templates:
        for _ in range(10):
            app = random.choice(app_list)
            filetype = random.choice(filetype_list)
            path = random.choice(path_list)
            setting = random.choice(setting_list)
            desc = template_desc.format(app=app, filetype=filetype, path=path, setting=setting)
            steps = [s.format(app=app, filetype=filetype, path=path, setting=setting) for s in template_steps]

            verify_points = []
            for i, step in enumerate(steps):
                verify_points.append(f"Step {i+1}: After '{step}' — check for visual confirmation or state change")

            examples.append({
                "conversations": [
                    {"role": "system", "content": SYSTEM_PROMPTS["workflow_orchestrator"]},
                    {"role": "user", "content": f"Plan and verify: {desc}"},
                    {"role": "assistant", "content": (
                        f"**Workflow Plan:**\n" + "\n".join(f"{i+1}. {s}" for i, s in enumerate(steps)) +
                        f"\n\n**Verification Points:**\n" + "\n".join(verify_points)
                    )},
                ],
                "_expert_chain": [17, 18],
            })

    # ─── Ground → Retry (100 examples) ───
    # Expert 16 fails to find element → Expert 19 generates alternative
    ground_retry_scenarios = [
        {
            "target": "Save button",
            "app": "Custom Web App",
            "failure": "No standard 'Save' button found — the app uses a floppy disk icon instead",
            "retry_strategy": [
                "1. Look for a floppy disk icon (💾) in the toolbar area — common Save metaphor",
                "2. Check for keyboard shortcut Ctrl+S as alternative",
                "3. Look for an 'Auto-save' indicator — the app might save automatically",
                "4. Check the File menu for a 'Save' option",
                "5. Right-click the document area — some apps have Save in context menu",
            ],
        },
        {
            "target": "Submit button on a form",
            "app": "Chrome (web form)",
            "failure": "The Submit button is disabled/grayed out — likely form validation failed",
            "retry_strategy": [
                "1. Check for red validation messages near required fields",
                "2. Look for asterisk (*) markers on unfilled required fields",
                "3. Scroll down — there might be hidden required fields below the fold",
                "4. Check CAPTCHA — it might need to be completed first",
                "5. Try pressing Enter while focused on the last field as alternative submit",
            ],
        },
        {
            "target": "Close button on a dialog",
            "app": "Windows Application",
            "failure": "Close (×) button not visible — dialog appears to be borderless/custom-styled",
            "retry_strategy": [
                "1. Try pressing Escape key — most dialogs respond to Esc",
                "2. Try Alt+F4 to force-close the dialog window",
                "3. Look for a 'Cancel' or 'Close' text button within the dialog body",
                "4. Click outside the dialog — it might be a dismiss-on-outside-click modal",
                "5. Check if the dialog has a custom close icon (different from standard ×)",
            ],
        },
        {
            "target": "Search box",
            "app": "Windows Explorer",
            "failure": "Search box not visible — Explorer might be in a simplified view or too narrow",
            "retry_strategy": [
                "1. Press Ctrl+E or Ctrl+F to activate search directly via keyboard",
                "2. Widen the Explorer window — search box may be hidden due to narrow width",
                "3. Click in the address bar and type a search query with wildcards",
                "4. Use Windows Search (Win key) as alternative search method",
                "5. Navigate to the folder first, then try search again",
            ],
        },
        {
            "target": "Settings gear icon",
            "app": "Web Application",
            "failure": "No gear icon found — the app may use a hamburger menu (≡) or user avatar for settings",
            "retry_strategy": [
                "1. Look for a hamburger menu (≡) icon, typically in the top-left or top-right",
                "2. Check the user avatar/profile icon — settings often hide under profile",
                "3. Look for a '...' (more options) button in the toolbar",
                "4. Try the URL path /settings or /preferences directly in the address bar",
                "5. Check the footer — some apps put settings links at the bottom",
            ],
        },
    ]

    for scenario in ground_retry_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": SYSTEM_PROMPTS["visual_grounding"]},
                {"role": "user", "content": f"I need to find the {scenario['target']} in {scenario['app']}."},
                {"role": "assistant", "content": f"Grounding attempt: {scenario['failure']}"},
                {"role": "user", "content": "The element wasn't found as expected. What should I try instead?"},
                {"role": "assistant", "content": (
                    f"Alternative approaches to find/interact with {scenario['target']}:\n" +
                    "\n".join(scenario["retry_strategy"])
                )},
            ],
            "_expert_chain": [16, 19],
        })

    # Generate more ground→retry from element type × failure pattern
    element_types = ["button", "input field", "link", "dropdown", "checkbox", "tab", "icon", "menu"]
    failure_patterns = [
        "Element is off-screen — need to scroll",
        "Element is obscured by a popup/overlay",
        "Element has different styling than expected",
        "Element is inside an iframe",
        "Element was dynamically loaded and isn't visible yet",
        "Element is disabled and can't be interacted with",
        "Element moved due to responsive layout change",
        "Element is behind a cookie consent banner",
    ]

    for elem in element_types:
        for failure in random.sample(failure_patterns, 4):
            examples.append({
                "conversations": [
                    {"role": "system", "content": SYSTEM_PROMPTS["adaptive_retry"]},
                    {"role": "user", "content": f"Tried to interact with a {elem} but: {failure}. How to recover?"},
                    {"role": "assistant", "content": (
                        f"Recovery strategy for '{failure}' on a {elem}:\n\n"
                        f"1. **Immediate fix:** Address the specific blocker (scroll, close overlay, wait for load)\n"
                        f"2. **Alternative interaction:** Try keyboard shortcuts or tab navigation instead of mouse\n"
                        f"3. **Re-scan:** Take a fresh screenshot and re-identify elements\n"
                        f"4. **Workaround:** Use application menu or command palette as backup\n"
                        f"5. **Escalate:** If 3 attempts fail, report the blocker and try a completely different approach"
                    )},
                ],
                "_expert_chain": [16, 19],
            })

    # ─── Full Chain: All 4 experts (100 examples) ───
    full_chain_scenarios = [
        {
            "task": "Research a topic online and create a summary document",
            "ground": "Identify Chrome's address bar at (500, 40) and Google search results at various positions",
            "workflow": "1. Open Chrome → 2. Search query → 3. Read top 3 results → 4. Open Word → 5. Write summary → 6. Save as PDF",
            "verify": "Check: Chrome opened, search results loaded, Word has content, PDF file exists in target directory",
            "retry": "If search returns no results → modify query. If Word won't open → use Notepad. If PDF export fails → save as .docx first",
        },
        {
            "task": "Set up a new Python project in VS Code",
            "ground": "Identify VS Code's Explorer panel, terminal, file tab bar, and Extensions sidebar",
            "workflow": "1. Open VS Code → 2. File → Open Folder → 3. Create main.py → 4. Open terminal → 5. Create venv → 6. Install packages",
            "verify": "Check: Folder shows in Explorer, main.py exists, terminal shows (venv) prefix, pip list shows installed packages",
            "retry": "If venv creation fails → try 'python -m venv'. If pip fails → check internet. If VS Code frozen → restart",
        },
        {
            "task": "Download and organize photos from a website",
            "ground": "Identify image thumbnails, download buttons, Explorer folder tree, and file rename dialog",
            "workflow": "1. Open browser → 2. Navigate to gallery → 3. Download images → 4. Open Explorer → 5. Create folders by date → 6. Move images",
            "verify": "Check: Images downloaded (file count matches), folders created, images moved to correct folders, originals deleted from Downloads",
            "retry": "If downloads blocked → check popup blocker. If images won't move → check permissions. If wrong images → re-select",
        },
        {
            "task": "Create an Excel budget spreadsheet from scratch",
            "ground": "Identify Excel's ribbon tabs, cell references, formula bar, and chart insertion tools",
            "workflow": "1. Open Excel → 2. Set up headers (Income, Expenses, etc.) → 3. Enter data → 4. Add formulas (SUM, AVERAGE) → 5. Create chart → 6. Save",
            "verify": "Check: Headers in row 1, data in correct cells, formulas computing correctly, chart displays data, file saved without errors",
            "retry": "If formula errors → check cell references. If chart wrong → reselect data range. If save fails → try different path",
        },
        {
            "task": "Clone a GitHub repo and run it locally",
            "ground": "Identify Terminal prompt, VS Code file tree, browser GitHub page elements",
            "workflow": "1. Copy repo URL from GitHub → 2. Open terminal → 3. git clone → 4. cd into project → 5. Install dependencies → 6. Run",
            "verify": "Check: Repo folder exists, all files present, dependencies installed (node_modules or venv), server running (port open)",
            "retry": "If git clone fails → check SSH/HTTPS credentials. If deps fail → check Node/Python version. If port in use → kill process or change port",
        },
    ]

    for scenario in full_chain_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": (
                    "You are a comprehensive computer operation expert that combines visual grounding, "
                    "workflow planning, action verification, and adaptive error recovery. You handle "
                    "the complete lifecycle of complex computer tasks."
                )},
                {"role": "user", "content": f"Complete task: {scenario['task']}"},
                {"role": "assistant", "content": (
                    f"**Visual Grounding:**\n{scenario['ground']}\n\n"
                    f"**Workflow Plan:**\n{scenario['workflow']}\n\n"
                    f"**Verification Checkpoints:**\n{scenario['verify']}\n\n"
                    f"**Recovery Strategies:**\n{scenario['retry']}"
                )},
            ],
            "_expert_chain": [16, 17, 18, 19],
        })

    # Generate more full-chain from task category × app combinations
    task_categories = [
        "data entry", "file management", "web research", "document creation",
        "system configuration", "software installation", "email management",
        "presentation creation", "code development", "media editing",
    ]

    for category in task_categories:
        for app in random.sample(apps, 3):
            task_desc = f"Perform {category} using {app} and related applications"
            examples.append({
                "conversations": [
                    {"role": "system", "content": (
                        "You are a comprehensive computer operation expert. For every task, you: "
                        "1) Identify UI elements on screen (visual grounding), "
                        "2) Plan the step-by-step workflow (orchestration), "
                        "3) Define verification checkpoints (verification), "
                        "4) Prepare recovery strategies for each step (adaptive retry)."
                    )},
                    {"role": "user", "content": task_desc},
                    {"role": "assistant", "content": (
                        f"**Task:** {task_desc}\n\n"
                        f"**1. Visual Grounding (Expert 16):**\n"
                        f"- Identify {app}'s main window elements: toolbar, content area, status bar\n"
                        f"- Map interactive elements to coordinates for precise clicking\n"
                        f"- Note any overlapping windows or dialogs that need attention\n\n"
                        f"**2. Workflow (Expert 17):**\n"
                        f"- Step 1: Launch {app} if not already open\n"
                        f"- Step 2: Navigate to the correct workspace/document\n"
                        f"- Step 3: Perform the core {category} operations\n"
                        f"- Step 4: Save results and verify output\n\n"
                        f"**3. Verification (Expert 18):**\n"
                        f"- After each step, check for expected visual changes\n"
                        f"- Verify data integrity (content matches expectations)\n"
                        f"- Confirm no error dialogs or warnings appeared\n\n"
                        f"**4. Recovery (Expert 19):**\n"
                        f"- If {app} crashes: restart and recover from auto-save\n"
                        f"- If action fails: try keyboard shortcut alternative\n"
                        f"- If data lost: check temp files and undo history"
                    )},
                ],
                "_expert_chain": [16, 17, 18, 19],
            })

    # ─── Korean cross-expert scenarios (50 examples) ───
    korean_cross_scenarios = [
        {
            "task": "크롬에서 구글 검색 결과를 엑셀에 정리하기",
            "steps": "1. 크롬 열기 → 2. 구글에서 검색 → 3. 결과 복사 → 4. 엑셀에 붙여넣기 → 5. 정렬 및 포맷",
            "verify": "크롬 URL 확인, 검색결과 로드됨, 클립보드에 데이터 있음, 엑셀에 데이터 표시됨",
        },
        {
            "task": "파워포인트로 발표자료 만들기",
            "steps": "1. 파워포인트 실행 → 2. 새 프레젠테이션 → 3. 제목 입력 → 4. 슬라이드 추가 → 5. 이미지 삽입 → 6. 저장",
            "verify": "파워포인트 열폄, 슬라이드 생성됨, 텍스트 입력됨, 이미지 표시됨, 파일 저장됨",
        },
        {
            "task": "윈도우 설정에서 해상도 변경하기",
            "steps": "1. 설정 열기 → 2. 디스플레이 메뉴 → 3. 해상도 드롭다운 클릭 → 4. 원하는 해상도 선택 → 5. 변경 확인",
            "verify": "설정 창 열림, 디스플레이 섹션 표시됨, 해상도 변경됨, 확인 대화상자 표시됨",
        },
        {
            "task": "한글(HWP)에서 표 만들고 데이터 입력하기",
            "steps": "1. 한글 실행 → 2. 표 삽입 메뉴 → 3. 행/열 설정 → 4. 데이터 입력 → 5. 테두리 설정 → 6. 저장",
            "verify": "한글 열림, 표 삽입됨, 데이터 정확히 입력됨, 테두리 표시됨, 저장 완료",
        },
        {
            "task": "파일 탐색기에서 파일 찾아 이동하기",
            "steps": "1. 탐색기 열기 → 2. 검색창에 파일명 입력 → 3. 검색 결과에서 파일 선택 → 4. 대상 폴더로 이동",
            "verify": "탐색기 열림, 검색 결과 표시됨, 파일 선택됨, 파일 새 위치에 존재",
        },
    ]

    for scenario in korean_cross_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": (
                    "당신은 컴퓨터 작업 전문가입니다. 화면 요소 식별, 작업 계획, 결과 검증, "
                    "오류 복구를 종합적으로 수행합니다."
                )},
                {"role": "user", "content": f"작업을 수행해주세요: {scenario['task']}"},
                {"role": "assistant", "content": (
                    f"**작업 계획:**\n{scenario['steps']}\n\n"
                    f"**검증 포인트:**\n{scenario['verify']}\n\n"
                    f"**오류 대비:**\n"
                    f"- 프로그램이 응답하지 않으면: 작업 관리자에서 다시 시작\n"
                    f"- 파일을 찾을 수 없으면: 최근 사용 파일에서 확인\n"
                    f"- 작업이 실패하면: 키보드 단축키로 대체 시도"
                )},
            ],
            "_expert_chain": [16, 17, 18, 19],
        })

    # ─── Hard/Adversarial examples for Phase 4 hardening (50 examples) ───
    adversarial_scenarios = [
        {
            "scenario": "Unexpected popup blocking the target element",
            "response": "1. Identify the popup type (ad, notification, consent, system)\n2. Find the popup's close button or dismiss area\n3. Close the popup\n4. Re-scan for the original target element\n5. If popup persists, try clicking around it or use keyboard navigation",
        },
        {
            "scenario": "Application froze mid-workflow, some data may be unsaved",
            "response": "1. Wait 15-30 seconds — it might be processing\n2. Check task manager for 'Not Responding' status\n3. If frozen, try Ctrl+S (some apps save even when busy)\n4. If no response, use Task Manager to End Task\n5. Reopen app and check auto-recovery/temp files\n6. Resume workflow from last verified checkpoint",
        },
        {
            "scenario": "Multiple similar-looking buttons on screen — which one is correct?",
            "response": "1. Analyze context: which dialog/panel contains the target?\n2. Check button labels carefully (Save vs Save As, OK vs Apply)\n3. Verify parent container — right dialog, right tab?\n4. Check button state — only enabled buttons are valid targets\n5. When in doubt, hover first to see tooltip confirmation",
        },
        {
            "scenario": "Screen resolution changed mid-session, all coordinates are wrong",
            "response": "1. Detect the resolution change (window positions shifted)\n2. Re-capture a fresh screenshot at new resolution\n3. Recalculate all element positions relative to new layout\n4. If DPI scaling changed, apply DPI correction factor\n5. Verify at least one known element before proceeding",
        },
        {
            "scenario": "The website requires CAPTCHA completion before proceeding",
            "response": "1. Identify the CAPTCHA type (reCAPTCHA, hCaptcha, image puzzle)\n2. CANNOT bypass CAPTCHA automatically — this requires human intervention\n3. Notify the user that CAPTCHA needs manual completion\n4. Wait for user to complete CAPTCHA\n5. After completion, verify the page progressed past the CAPTCHA\n6. Resume the workflow from the post-CAPTCHA step",
        },
    ]

    for scenario in adversarial_scenarios:
        examples.append({
            "conversations": [
                {"role": "system", "content": (
                    "You are a computer operation expert handling adversarial and edge-case scenarios. "
                    "You must handle unexpected situations gracefully without causing data loss."
                )},
                {"role": "user", "content": f"Edge case: {scenario['scenario']}. How do I handle this?"},
                {"role": "assistant", "content": scenario["response"]},
            ],
            "_expert_chain": [16, 17, 18, 19],
            "_difficulty": "hard",
        })

    print(f"  Cross-expert data: {len(examples)} examples")
    return examples

def main():
    parser = argparse.ArgumentParser(description="Generate training data for 4 new MoE experts (V3.0)")
    parser.add_argument("--output-dir", type=str, default="./data",
                        help="Output directory for JSONL files")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for reproducibility")
    parser.add_argument("--include-cross-expert", action="store_true", default=True,
                        help="Include cross-expert chain scenarios (V3.0)")
    args = parser.parse_args()
    
    random.seed(args.seed)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    generators = {
        "visual_grounding": generate_visual_grounding_data,
        "workflow_orchestrator": generate_workflow_orchestrator_data,
        "verification_oracle": generate_verification_oracle_data,
        "adaptive_retry": generate_adaptive_retry_data,
    }
    
    # Generate ALL data ONCE and reuse (v2.0 — no redundant calls)
    expert_data = {}
    total_examples = 0
    
    for expert_name, generator_fn in generators.items():
        print(f"\n{'='*60}")
        print(f"  Generating training data for: {expert_name}")
        print(f"{'='*60}")
        
        examples = generator_fn()
        expert_data[expert_name] = examples
        
        # Save individual expert dataset
        output_file = output_dir / f"expert_{expert_name}.jsonl"
        with open(output_file, "w", encoding="utf-8") as f:
            for example in examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
        
        print(f"  Generated: {len(examples)} examples")
        print(f"  Saved to: {output_file}")
        total_examples += len(examples)
    
    # V3.0: Cross-expert chain scenarios
    cross_expert_examples = []
    if args.include_cross_expert:
        print(f"\n{'='*60}")
        print(f"  Generating cross-expert chain scenarios (V3.0)")
        print(f"{'='*60}")
        cross_expert_examples = generate_cross_expert_data()
        
        # Save cross-expert dataset
        cross_file = output_dir / "expert_cross_chain.jsonl"
        with open(cross_file, "w", encoding="utf-8") as f:
            for example in cross_expert_examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
        
        print(f"  Generated: {len(cross_expert_examples)} cross-expert examples")
        print(f"  Saved to: {cross_file}")
        total_examples += len(cross_expert_examples)
    
    # Combined dataset — reuse already-generated data
    combined_file = output_dir / "expert_combined.jsonl"
    all_examples = []
    expert_id_map = {name: idx + 16 for idx, name in enumerate(generators.keys())}
    
    for expert_name, examples in expert_data.items():
        for ex in examples:
            tagged = dict(ex)  # shallow copy to avoid mutating originals
            tagged["_expert"] = expert_name
            tagged["_expert_id"] = expert_id_map[expert_name]
            all_examples.append(tagged)
    
    # Add cross-expert examples to combined (tagged as multi-expert)
    for ex in cross_expert_examples:
        tagged = dict(ex)
        chain = tagged.get("_expert_chain", [16, 17, 18, 19])
        tagged["_expert"] = "cross_expert"
        tagged["_expert_id"] = chain[0]  # Primary expert is first in chain
        all_examples.append(tagged)
    
    random.shuffle(all_examples)
    
    with open(combined_file, "w", encoding="utf-8") as f:
        for example in all_examples:
            f.write(json.dumps(example, ensure_ascii=False) + "\n")
    
    # V3.0: Hard examples subset for Phase 4 hardening
    hard_examples = [ex for ex in all_examples if ex.get("_difficulty") == "hard"]
    if hard_examples:
        hard_file = output_dir / "expert_hard_examples.jsonl"
        with open(hard_file, "w", encoding="utf-8") as f:
            for example in hard_examples:
                f.write(json.dumps(example, ensure_ascii=False) + "\n")
        print(f"\n  Hard examples (Phase 4): {len(hard_examples)} saved to {hard_file}")
    
    print(f"\n{'='*60}")
    print(f"  TOTAL: {total_examples} examples across 4 experts + cross-expert")
    print(f"  Combined dataset: {combined_file} ({len(all_examples)} tagged examples)")
    print(f"{'='*60}")
    
    # Print statistics — reuse cached data
    print(f"\n  Per-expert breakdown:")
    for expert_name, examples in expert_data.items():
        print(f"    {expert_name}: {len(examples)} examples")
    if cross_expert_examples:
        print(f"    cross_expert_chain: {len(cross_expert_examples)} examples")
    
    # V3.0: Dataset quality report
    print(f"\n  V3.0 Dataset Quality Report:")
    print(f"  ─────────────────────────────")
    for expert_name, examples in expert_data.items():
        multi_turn = sum(1 for ex in examples if len(ex.get("conversations", [])) > 3)
        korean = sum(1 for ex in examples
                     for c in ex.get("conversations", [])
                     if any(ord(ch) >= 0xAC00 and ord(ch) <= 0xD7AF for ch in c.get("content", "")))
        print(f"    {expert_name}: total={len(examples)}, multi_turn={multi_turn}, korean={korean}")
    if cross_expert_examples:
        chains = {}
        for ex in cross_expert_examples:
            chain_key = str(ex.get("_expert_chain", []))
            chains[chain_key] = chains.get(chain_key, 0) + 1
        print(f"    cross_expert chains: {chains}")


if __name__ == "__main__":
    main()
