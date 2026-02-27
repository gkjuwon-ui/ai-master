"""
Specialized Tools Registry v2 — Domain-exclusive tools that make each agent UNIQUE.

Architecture:
  Each domain has a set of specialized tools that ONLY agents in that domain can use.
  A coding agent CANNOT use design tools. A design agent CANNOT use coding tools.
  
  Tools are further gated by tier:
    F   → 0 specialized tools (no access)
    B-  → 2 most basic domain tools
    C   → 4 domain tools
    B   → 6 domain tools  
    A   → 8 domain tools
    S   → ALL domain tools (unlimited)
    S+  → ALL domain tools + can borrow from adjacent domains

  Tool priority order is defined per domain — lower index = more basic tool,
  unlocked first at lower tiers.

v2 additions:
  - Browser interaction tools (navigate, search, extract)
  - Windows app management tools
  - Document creation and formatting tools
  - Smart file tools with content awareness
  - Enhanced research tools with web intelligence
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import re
import os
import hashlib
import time
import tempfile
from dataclasses import dataclass, field
from typing import Optional, Any
from loguru import logger

from core.tier_config import get_tier_config, get_allowed_actions


# ═══════════════════════════════════════════════════════
# SAFE COMMAND EXECUTION HELPER
# ═══════════════════════════════════════════════════════

import sys
import shlex

# Shell metacharacters that enable command injection
_SHELL_META = ['&&', '||', ';', '`', '$(', '${', '|', '\n', '\r']

def _sanitize_shell_arg(arg: str) -> str:
    """Sanitize a single argument for use in a command list.
    Strips null bytes, control characters, and blocks shell metacharacters."""
    # Remove null bytes and control characters
    cleaned = re.sub(r'[\x00-\x08\x0e-\x1f]', '', arg)
    # Also reject if any shell metacharacter is present
    for meta in _SHELL_META:
        if meta in cleaned:
            raise ValueError(f"Blocked: dangerous metacharacter '{meta}' in argument")
    return cleaned

def _safe_run(cmd_str: str, *, timeout: int = 30, cwd: str = None) -> subprocess.CompletedProcess:
    """
    Run a command safely WITHOUT shell=True.
    Blocks shell metacharacters to prevent injection.
    """
    if not cmd_str or not cmd_str.strip():
        raise ValueError("Empty command")
    # Strip control characters before checking metacharacters
    cmd_str = re.sub(r'[\x00-\x08\x0e-\x1f]', '', cmd_str)
    if any(m in cmd_str for m in _SHELL_META):
        raise ValueError(f"Blocked: shell metacharacters detected in command")
    
    if sys.platform == 'win32':
        cmd_args = ['cmd', '/c'] + cmd_str.split()
    else:
        cmd_args = shlex.split(cmd_str)
    
    return subprocess.run(
        cmd_args, capture_output=True, text=True,
        timeout=timeout, cwd=cwd,
    )

def _safe_run_list(cmd_list: list, *, timeout: int = 30, cwd: str = None) -> subprocess.CompletedProcess:
    """Run a command from an argument list (already split). No shell."""
    return subprocess.run(
        cmd_list, capture_output=True, text=True,
        timeout=timeout, cwd=cwd,
    )


# ═══════════════════════════════════════════════════════
# TOOL DEFINITION
# ═══════════════════════════════════════════════════════

@dataclass
class SpecializedTool:
    """A domain-exclusive tool with execution logic."""
    name: str
    domain: str
    description: str
    params_schema: dict  # JSON Schema for params
    tier_priority: int   # Lower = more basic, unlocked first (0-based)
    
    async def execute(self, params: dict, context: Any = None) -> dict:
        """Execute tool. Override in subclasses or use factory."""
        return {"success": False, "error": "Not implemented"}


# ═══════════════════════════════════════════════════════
# CODING DOMAIN TOOLS
# ═══════════════════════════════════════════════════════

class RunTestsTool(SpecializedTool):
    """Execute test suite and return results."""
    def __init__(self):
        super().__init__(
            name="run_tests",
            domain="coding",
            description="Run test suite (pytest/jest/go test) and return pass/fail results with failure details.",
            params_schema={"command": "str (test command, e.g. 'pytest tests/')", "timeout": "int (seconds, default 60)"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        cmd = params.get("command", "pytest")
        timeout = min(params.get("timeout", 60), 120)
        try:
            result = _safe_run(cmd, timeout=timeout, cwd=params.get("cwd"))
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-1000:] if result.stderr else "",
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Test timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class CodeLintTool(SpecializedTool):
    """Run linter on file/directory."""
    def __init__(self):
        super().__init__(
            name="code_lint",
            domain="coding",
            description="Run linter (eslint/pylint/rustfmt --check) on a file and return issues.",
            params_schema={"command": "str (lint command)", "file": "str (file path)"},
            tier_priority=1,
        )
    async def execute(self, params: dict, context=None) -> dict:
        cmd = params.get("command", f"pylint {params.get('file', '.')}")
        try:
            result = _safe_run(cmd, timeout=30)
            return {
                "success": True,
                "issues": result.stdout[-2000:] if result.stdout else "No issues found",
                "returncode": result.returncode,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class GitOperationTool(SpecializedTool):
    """Execute git operations."""
    def __init__(self):
        super().__init__(
            name="git_operation",
            domain="coding",
            description="Execute git commands (status, add, commit, diff, log, branch, checkout). Safe subset only.",
            params_schema={"operation": "str (status|add|commit|diff|log|branch|checkout|push|pull)", "args": "str (additional args)"},
            tier_priority=2,
        )
    ALLOWED_OPS = {"status", "add", "commit", "diff", "log", "branch", "checkout", "push", "pull", "stash"}
    
    async def execute(self, params: dict, context=None) -> dict:
        op = params.get("operation", "status")
        if op not in self.ALLOWED_OPS:
            return {"success": False, "error": f"Git operation '{op}' not allowed. Use: {self.ALLOWED_OPS}"}
        args = params.get("args", "")
        # Sanitize args to prevent injection
        args = _sanitize_shell_arg(args)
        try:
            cmd_list = ['git', op] + (args.split() if args else [])
            result = _safe_run_list(cmd_list, timeout=30)
            return {"success": result.returncode == 0, "output": (result.stdout + result.stderr)[-2000:]}
        except Exception as e:
            return {"success": False, "error": str(e)}


class DependencyInstallTool(SpecializedTool):
    """Install project dependencies."""
    def __init__(self):
        super().__init__(
            name="dependency_install",
            domain="coding",
            description="Install packages (npm install, pip install, cargo add). Detects package manager from project.",
            params_schema={"command": "str (install command)", "packages": "str (package names)"},
            tier_priority=3,
        )
    async def execute(self, params: dict, context=None) -> dict:
        cmd = params.get("command", "")
        if not cmd:
            return {"success": False, "error": "No install command provided"}
        # Safety: only allow install-type commands
        safe_prefixes = ("npm install", "npm i ", "pip install", "cargo add", "yarn add", "pnpm add", "pip3 install")
        if not any(cmd.strip().startswith(p) for p in safe_prefixes):
            return {"success": False, "error": f"Only package install commands allowed"}
        try:
            result = _safe_run(cmd, timeout=120)
            return {"success": result.returncode == 0, "output": (result.stdout + result.stderr)[-1500:]}
        except Exception as e:
            return {"success": False, "error": str(e)}


class CodeSearchTool(SpecializedTool):
    """Regex search across codebase."""
    def __init__(self):
        super().__init__(
            name="code_search",
            domain="coding",
            description="Search codebase with regex pattern. Returns matching file paths and line numbers.",
            params_schema={"pattern": "str (regex)", "directory": "str (search dir, default '.')", "file_pattern": "str (glob, e.g. '*.py')"},
            tier_priority=4,
        )
    async def execute(self, params: dict, context=None) -> dict:
        pattern = params.get("pattern", "")
        directory = params.get("directory", ".")
        file_pat = params.get("file_pattern", "")
        if not pattern:
            return {"success": False, "error": "No search pattern"}
        # Build command as argument list to avoid shell injection
        cmd_list = ['grep', '-rn', pattern, directory]
        if file_pat:
            cmd_list += [f'--include={file_pat}']
        try:
            result = _safe_run_list(cmd_list, timeout=15)
            matches = result.stdout.strip().split("\n")[:30]  # limit results
            return {"success": True, "matches": matches, "count": len(matches)}
        except Exception as e:
            return {"success": False, "error": str(e)}


class CodeFormatTool(SpecializedTool):
    """Auto-format code file."""
    def __init__(self):
        super().__init__(
            name="code_format",
            domain="coding",
            description="Auto-format a code file (prettier, black, rustfmt, gofmt).",
            params_schema={"command": "str (format command)", "file": "str (file path)"},
            tier_priority=5,
        )
    async def execute(self, params: dict, context=None) -> dict:
        cmd = params.get("command", "")
        if not cmd:
            return {"success": False, "error": "No format command"}
        try:
            result = _safe_run(cmd, timeout=15)
            return {"success": result.returncode == 0, "output": result.stdout[-500:] or "Formatted"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class DebugInspectTool(SpecializedTool):
    """Inspect variable values, stack trace, breakpoints."""
    def __init__(self):
        super().__init__(
            name="debug_inspect",
            domain="coding",
            description="Parse error output / stack trace and identify root cause file + line number.",
            params_schema={"error_text": "str (error/stack trace text)"},
            tier_priority=6,
        )
    async def execute(self, params: dict, context=None) -> dict:
        error_text = params.get("error_text", "")
        if not error_text:
            return {"success": False, "error": "No error text provided"}
        # Parse common stack trace patterns
        file_lines = []
        patterns = [
            r'File "([^"]+)", line (\d+)',  # Python
            r'at (.+):(\d+):\d+',            # Node.js/TypeScript
            r'(\S+\.(?:rs|go|java|c|cpp)):(\d+)',  # Rust/Go/Java/C
        ]
        for pat in patterns:
            matches = re.findall(pat, error_text)
            file_lines.extend([{"file": m[0], "line": int(m[1])} for m in matches])
        return {"success": True, "locations": file_lines[:10], "summary": error_text[:500]}


class ProjectScaffoldTool(SpecializedTool):
    """Generate project boilerplate."""
    def __init__(self):
        super().__init__(
            name="project_scaffold",
            domain="coding",
            description="Generate project structure based on template (nextjs, fastapi, express, etc).",
            params_schema={"template": "str (project type)", "name": "str (project name)", "directory": "str"},
            tier_priority=7,
        )
    async def execute(self, params: dict, context=None) -> dict:
        template = params.get("template", "")
        name = params.get("name", "my-project")
        # Sanitize project name to prevent injection
        name = re.sub(r'[^a-zA-Z0-9_\-]', '', name)
        # Build scaffold command based on template
        TEMPLATE_COMMANDS = {
            "nextjs": ['npx', 'create-next-app@latest', name, '--yes'],
            "react": ['npx', 'create-react-app', name],
            "vite": ['npm', 'create', 'vite@latest', name, '--', '--template', 'react-ts'],
            "fastapi": None,  # Handled separately
            "express": None,  # Handled separately
        }
        cmd_list = TEMPLATE_COMMANDS.get(template)
        if cmd_list is None and template in ("fastapi", "express"):
            # These need directory creation + install — run sequentially
            os.makedirs(name, exist_ok=True)
            if template == "fastapi":
                cmd_list = ['pip', 'install', 'fastapi', 'uvicorn']
            else:
                cmd_list = ['npm', 'init', '-y']
        if not cmd_list:
            return {"success": False, "error": f"Unknown template: {template}. Available: {list(TEMPLATE_COMMANDS.keys())}"}
        try:
            result = _safe_run_list(cmd_list, timeout=120)
            return {"success": result.returncode == 0, "output": result.stdout[-1000:]}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# DESIGN DOMAIN TOOLS
# ═══════════════════════════════════════════════════════

class ColorPickTool(SpecializedTool):
    """Sample color from a screen coordinate."""
    def __init__(self):
        super().__init__(
            name="color_pick",
            domain="design",
            description="Sample the pixel color at (x, y) screen coordinates. Returns hex, RGB, HSL values.",
            params_schema={"x": "int", "y": "int"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        try:
            from PIL import ImageGrab
            x, y = params.get("x", 0), params.get("y", 0)
            img = ImageGrab.grab(bbox=(x, y, x+1, y+1))
            r, g, b = img.getpixel((0, 0))[:3]
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            return {
                "success": True,
                "hex": hex_color,
                "rgb": f"rgb({r},{g},{b})",
                "r": r, "g": g, "b": b,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class MeasureSpacingTool(SpecializedTool):
    """Measure pixel distance between two points."""
    def __init__(self):
        super().__init__(
            name="measure_spacing",
            domain="design",
            description="Measure pixel distance between two screen points. Returns horizontal, vertical, and diagonal distance.",
            params_schema={"x1": "int", "y1": "int", "x2": "int", "y2": "int"},
            tier_priority=1,
        )
    async def execute(self, params: dict, context=None) -> dict:
        import math
        x1, y1 = params.get("x1", 0), params.get("y1", 0)
        x2, y2 = params.get("x2", 0), params.get("y2", 0)
        dx = abs(x2 - x1)
        dy = abs(y2 - y1)
        diagonal = math.sqrt(dx**2 + dy**2)
        return {
            "success": True,
            "horizontal_px": dx,
            "vertical_px": dy,
            "diagonal_px": round(diagonal, 1),
        }


class GeneratePaletteTool(SpecializedTool):
    """Generate a color palette from a base color."""
    def __init__(self):
        super().__init__(
            name="generate_palette",
            domain="design",
            description="Generate a harmonious color palette (complementary, analogous, triadic) from a base hex color.",
            params_schema={"base_color": "str (hex, e.g. '#3b82f6')", "scheme": "str (complementary|analogous|triadic|monochromatic)"},
            tier_priority=2,
        )
    async def execute(self, params: dict, context=None) -> dict:
        base_hex = params.get("base_color", "#3b82f6").lstrip("#")
        scheme = params.get("scheme", "complementary")
        try:
            r, g, b = int(base_hex[0:2], 16), int(base_hex[2:4], 16), int(base_hex[4:6], 16)
            # Convert to HSL for manipulation
            r_, g_, b_ = r/255, g/255, b/255
            mx, mn = max(r_, g_, b_), min(r_, g_, b_)
            l = (mx + mn) / 2
            if mx == mn:
                h = s = 0
            else:
                d = mx - mn
                s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
                if mx == r_: h = (g_ - b_) / d + (6 if g_ < b_ else 0)
                elif mx == g_: h = (b_ - r_) / d + 2
                else: h = (r_ - g_) / d + 4
                h /= 6
            
            def hsl_to_hex(h, s, l):
                def hue2rgb(p, q, t):
                    if t < 0: t += 1
                    if t > 1: t -= 1
                    if t < 1/6: return p + (q - p) * 6 * t
                    if t < 1/2: return q
                    if t < 2/3: return p + (q - p) * (2/3 - t) * 6
                    return p
                if s == 0:
                    r = g = b = l
                else:
                    q = l * (1 + s) if l < 0.5 else l + s - l * s
                    p = 2 * l - q
                    r = hue2rgb(p, q, h + 1/3)
                    g = hue2rgb(p, q, h)
                    b = hue2rgb(p, q, h - 1/3)
                return f"#{int(r*255):02x}{int(g*255):02x}{int(b*255):02x}"
            
            palette = [f"#{base_hex}"]
            if scheme == "complementary":
                palette.append(hsl_to_hex((h + 0.5) % 1, s, l))
                palette.append(hsl_to_hex(h, s, max(0, l - 0.2)))
                palette.append(hsl_to_hex(h, s, min(1, l + 0.2)))
                palette.append(hsl_to_hex((h + 0.5) % 1, s, max(0, l - 0.15)))
            elif scheme == "analogous":
                for offset in [-0.083, -0.042, 0.042, 0.083]:
                    palette.append(hsl_to_hex((h + offset) % 1, s, l))
            elif scheme == "triadic":
                palette.append(hsl_to_hex((h + 1/3) % 1, s, l))
                palette.append(hsl_to_hex((h + 2/3) % 1, s, l))
                palette.append(hsl_to_hex(h, s, max(0, l - 0.2)))
                palette.append(hsl_to_hex(h, s, min(1, l + 0.2)))
            elif scheme == "monochromatic":
                for l_offset in [-0.3, -0.15, 0.15, 0.3]:
                    palette.append(hsl_to_hex(h, s, max(0, min(1, l + l_offset))))
            
            return {"success": True, "palette": palette, "scheme": scheme}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SnapToGridTool(SpecializedTool):
    """Snap coordinates to nearest grid point."""
    def __init__(self):
        super().__init__(
            name="snap_to_grid",
            domain="design",
            description="Snap (x,y) coordinates to nearest grid point. Ensures pixel-perfect alignment.",
            params_schema={"x": "int", "y": "int", "grid_size": "int (default 8)"},
            tier_priority=3,
        )
    async def execute(self, params: dict, context=None) -> dict:
        x, y = params.get("x", 0), params.get("y", 0)
        grid = params.get("grid_size", 8)
        snapped_x = round(x / grid) * grid
        snapped_y = round(y / grid) * grid
        return {
            "success": True,
            "original": {"x": x, "y": y},
            "snapped": {"x": snapped_x, "y": snapped_y},
            "grid_size": grid,
        }


class ExportAssetTool(SpecializedTool):
    """Export screen region as asset in multiple formats/sizes."""
    def __init__(self):
        super().__init__(
            name="export_asset",
            domain="design",
            description="Capture a screen region and export as PNG/JPEG/WebP at specified sizes.",
            params_schema={"x": "int", "y": "int", "width": "int", "height": "int", "format": "str (png|jpeg|webp)", "output_path": "str"},
            tier_priority=4,
        )
    async def execute(self, params: dict, context=None) -> dict:
        try:
            from PIL import ImageGrab, Image
            x, y = params.get("x", 0), params.get("y", 0)
            w, h = params.get("width", 100), params.get("height", 100)
            fmt = params.get("format", "png")
            output = params.get("output_path", f"export_{int(time.time())}.{fmt}")
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img.save(output, fmt.upper())
            return {"success": True, "path": output, "size": f"{w}x{h}", "format": fmt}
        except Exception as e:
            return {"success": False, "error": str(e)}


class FontMatchTool(SpecializedTool):
    """Suggest fonts matching a style description."""
    def __init__(self):
        super().__init__(
            name="font_suggest",
            domain="design",
            description="Suggest font pairings for heading+body based on style (modern, classic, playful, minimal).",
            params_schema={"style": "str (modern|classic|playful|minimal|technical|elegant)"},
            tier_priority=5,
        )
    FONT_DB = {
        "modern": {"heading": ["Inter", "SF Pro Display", "Manrope"], "body": ["Inter", "SF Pro Text", "Roboto"]},
        "classic": {"heading": ["Georgia", "Playfair Display", "Merriweather"], "body": ["Source Serif Pro", "Lora", "Crimson Text"]},
        "playful": {"heading": ["Poppins", "Fredoka One", "Comfortaa"], "body": ["Nunito", "Quicksand", "Patrick Hand"]},
        "minimal": {"heading": ["Helvetica Neue", "Arial", "DM Sans"], "body": ["System UI", "Segoe UI", "Roboto"]},
        "technical": {"heading": ["JetBrains Mono", "Fira Code", "IBM Plex Mono"], "body": ["IBM Plex Sans", "Source Sans Pro", "Fira Sans"]},
        "elegant": {"heading": ["Cormorant Garamond", "Didot", "Bodoni Moda"], "body": ["EB Garamond", "Libre Baskerville", "Spectral"]},
    }
    async def execute(self, params: dict, context=None) -> dict:
        style = params.get("style", "modern")
        fonts = self.FONT_DB.get(style, self.FONT_DB["modern"])
        return {"success": True, "style": style, "heading_fonts": fonts["heading"], "body_fonts": fonts["body"]}


class ContrastCheckTool(SpecializedTool):
    """Check WCAG color contrast ratio."""
    def __init__(self):
        super().__init__(
            name="contrast_check",
            domain="design",
            description="Check WCAG contrast ratio between foreground and background colors. Reports AA/AAA compliance.",
            params_schema={"foreground": "str (hex color)", "background": "str (hex color)"},
            tier_priority=6,
        )
    async def execute(self, params: dict, context=None) -> dict:
        def hex_to_lum(hex_color):
            hex_color = hex_color.lstrip("#")
            r, g, b = int(hex_color[0:2], 16)/255, int(hex_color[2:4], 16)/255, int(hex_color[4:6], 16)/255
            def linearize(c):
                return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
            return 0.2126 * linearize(r) + 0.7152 * linearize(g) + 0.0722 * linearize(b)
        try:
            fg_lum = hex_to_lum(params.get("foreground", "#000000"))
            bg_lum = hex_to_lum(params.get("background", "#ffffff"))
            lighter = max(fg_lum, bg_lum)
            darker = min(fg_lum, bg_lum)
            ratio = (lighter + 0.05) / (darker + 0.05)
            return {
                "success": True,
                "ratio": round(ratio, 2),
                "AA_normal": ratio >= 4.5,
                "AA_large": ratio >= 3.0,
                "AAA_normal": ratio >= 7.0,
                "AAA_large": ratio >= 4.5,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class LayoutGridTool(SpecializedTool):
    """Calculate responsive layout grid values."""
    def __init__(self):
        super().__init__(
            name="layout_grid",
            domain="design",
            description="Calculate responsive grid column widths, gutters, and margins for a given viewport width.",
            params_schema={"viewport_width": "int", "columns": "int (default 12)", "gutter": "int (default 16)", "margin": "int (default 24)"},
            tier_priority=7,
        )
    async def execute(self, params: dict, context=None) -> dict:
        vw = params.get("viewport_width", 1440)
        cols = params.get("columns", 12)
        gutter = params.get("gutter", 16)
        margin = params.get("margin", 24)
        content_width = vw - (margin * 2)
        total_gutters = (cols - 1) * gutter
        col_width = (content_width - total_gutters) / cols
        return {
            "success": True,
            "viewport": vw,
            "content_width": content_width,
            "column_width": round(col_width, 1),
            "columns": cols,
            "gutter": gutter,
            "margin": margin,
        }


# ═══════════════════════════════════════════════════════
# RESEARCH DOMAIN TOOLS  
# ═══════════════════════════════════════════════════════

class WebExtractTool(SpecializedTool):
    """Extract structured data from current page (reads clipboard-pasted content)."""
    def __init__(self):
        super().__init__(
            name="web_extract",
            domain="research",
            description="Extract and structure text/data from clipboard content (copy page text first, then call this).",
            params_schema={"raw_text": "str (text to structure)", "extract_type": "str (summary|key_points|table|quotes)"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        raw = params.get("raw_text", "")
        if not raw:
            return {"success": False, "error": "No text provided. Copy page content to clipboard first."}
        extract_type = params.get("extract_type", "key_points")
        # Basic extraction — in production this would call LLM
        lines = [l.strip() for l in raw.split("\n") if l.strip()]
        if extract_type == "summary":
            return {"success": True, "summary": " ".join(lines[:5]), "word_count": len(raw.split())}
        elif extract_type == "key_points":
            points = [l for l in lines if len(l) > 20][:10]
            return {"success": True, "key_points": points}
        elif extract_type == "quotes":
            quotes = [l for l in lines if '"' in l or "'" in l][:10]
            return {"success": True, "quotes": quotes}
        return {"success": True, "lines": lines[:20], "total_lines": len(lines)}


class SourceCredibilityTool(SpecializedTool):
    """Score source credibility."""
    def __init__(self):
        super().__init__(
            name="source_credibility",
            domain="research",
            description="Score a source URL's credibility (1-10) based on domain authority, type, and indicators.",
            params_schema={"url": "str", "domain_type": "str (academic|government|news|blog|social|corporate)"},
            tier_priority=1,
        )
    DOMAIN_SCORES = {
        "academic": 9, "government": 8, "news": 6, "corporate": 5, "blog": 3, "social": 2,
    }
    HIGH_CRED_DOMAINS = {".edu", ".gov", ".org", "nature.com", "science.org", "pubmed", "arxiv.org", "ieee.org"}
    
    async def execute(self, params: dict, context=None) -> dict:
        url = params.get("url", "")
        dtype = params.get("domain_type", "blog")
        base_score = self.DOMAIN_SCORES.get(dtype, 4)
        # Boost for known high-credibility domains
        for domain in self.HIGH_CRED_DOMAINS:
            if domain in url.lower():
                base_score = min(10, base_score + 2)
                break
        return {
            "success": True,
            "url": url,
            "credibility_score": base_score,
            "domain_type": dtype,
            "label": "High" if base_score >= 7 else "Medium" if base_score >= 4 else "Low",
        }


class CitationFormatTool(SpecializedTool):
    """Format a citation in APA/MLA/Chicago style."""
    def __init__(self):
        super().__init__(
            name="citation_format",
            domain="research",
            description="Format a source citation in APA, MLA, or Chicago style.",
            params_schema={"title": "str", "authors": "str", "year": "str", "url": "str", "style": "str (APA|MLA|Chicago)"},
            tier_priority=2,
        )
    async def execute(self, params: dict, context=None) -> dict:
        title = params.get("title", "Untitled")
        authors = params.get("authors", "Unknown")
        year = params.get("year", "n.d.")
        url = params.get("url", "")
        style = params.get("style", "APA").upper()
        
        if style == "APA":
            citation = f"{authors} ({year}). {title}." + (f" Retrieved from {url}" if url else "")
        elif style == "MLA":
            citation = f'{authors}. "{title}." {year}.' + (f" Web. <{url}>." if url else "")
        elif style == "CHICAGO":
            citation = f'{authors}. "{title}." {year}.' + (f" {url}." if url else "")
        else:
            citation = f"{authors}. {title}. ({year})."
        
        return {"success": True, "citation": citation, "style": style}


class SaveSourceTool(SpecializedTool):
    """Save a research source with metadata to a local file."""
    def __init__(self):
        super().__init__(
            name="save_source",
            domain="research",
            description="Save a research source (URL, title, notes, credibility) to a local research log file.",
            params_schema={"url": "str", "title": "str", "notes": "str", "credibility": "int (1-10)"},
            tier_priority=3,
        )
    async def execute(self, params: dict, context=None) -> dict:
        try:
            entry = {
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
                "url": params.get("url", ""),
                "title": params.get("title", ""),
                "notes": params.get("notes", ""),
                "credibility": params.get("credibility", 5),
            }
            log_file = params.get("output_file", "research_sources.json")
            existing = []
            if os.path.exists(log_file):
                with open(log_file, "r") as f:
                    existing = json.load(f)
            existing.append(entry)
            with open(log_file, "w") as f:
                json.dump(existing, f, indent=2)
            return {"success": True, "saved": entry, "total_sources": len(existing)}
        except Exception as e:
            return {"success": False, "error": str(e)}


class FactCheckTool(SpecializedTool):
    """Cross-reference a claim against saved sources."""
    def __init__(self):
        super().__init__(
            name="fact_cross_reference",
            domain="research",
            description="Check if a claim is supported by multiple saved sources. Returns source agreement count.",
            params_schema={"claim": "str", "sources_file": "str (default 'research_sources.json')"},
            tier_priority=4,
        )
    async def execute(self, params: dict, context=None) -> dict:
        claim = params.get("claim", "")
        log_file = params.get("sources_file", "research_sources.json")
        if not os.path.exists(log_file):
            return {"success": False, "error": "No sources file found. Save sources first."}
        with open(log_file, "r") as f:
            sources = json.load(f)
        # Simple keyword matching (in production this would use LLM)
        claim_words = set(claim.lower().split())
        related = []
        for src in sources:
            note_words = set(src.get("notes", "").lower().split())
            overlap = len(claim_words & note_words)
            if overlap >= 2:
                related.append({"title": src["title"], "url": src["url"], "relevance": overlap})
        related.sort(key=lambda x: x["relevance"], reverse=True)
        return {
            "success": True,
            "claim": claim,
            "supporting_sources": len(related),
            "sources": related[:5],
            "confidence": "high" if len(related) >= 3 else "medium" if len(related) >= 1 else "unverified",
        }


class CompareSourcesTool(SpecializedTool):
    """Build a comparison matrix from saved sources."""
    def __init__(self):
        super().__init__(
            name="compare_sources",
            domain="research",
            description="Generate a comparison matrix from saved research sources, grouped by credibility.",
            params_schema={"sources_file": "str (default 'research_sources.json')"},
            tier_priority=5,
        )
    async def execute(self, params: dict, context=None) -> dict:
        log_file = params.get("sources_file", "research_sources.json")
        if not os.path.exists(log_file):
            return {"success": False, "error": "No sources file"}
        with open(log_file, "r") as f:
            sources = json.load(f)
        by_credibility = {"high": [], "medium": [], "low": []}
        for s in sources:
            cred = s.get("credibility", 5)
            bucket = "high" if cred >= 7 else "medium" if cred >= 4 else "low"
            by_credibility[bucket].append({"title": s["title"], "url": s["url"], "score": cred})
        return {"success": True, "matrix": by_credibility, "total": len(sources)}


class ResearchTimelineTool(SpecializedTool):
    """Build timeline of events from research notes."""
    def __init__(self):
        super().__init__(
            name="research_timeline",
            domain="research",
            description="Build chronological timeline from research notes containing dates/years.",
            params_schema={"sources_file": "str"},
            tier_priority=6,
        )
    async def execute(self, params: dict, context=None) -> dict:
        log_file = params.get("sources_file", "research_sources.json")
        if not os.path.exists(log_file):
            return {"success": False, "error": "No sources file"}
        with open(log_file, "r") as f:
            sources = json.load(f)
        events = []
        for s in sources:
            years = re.findall(r'\b(19|20)\d{2}\b', s.get("notes", ""))
            for y in years:
                events.append({"year": y, "source": s["title"], "note": s["notes"][:100]})
        events.sort(key=lambda x: x["year"])
        return {"success": True, "timeline": events}


class GapAnalysisTool(SpecializedTool):
    """Identify gaps in research coverage."""
    def __init__(self):
        super().__init__(
            name="gap_analysis",
            domain="research",
            description="Analyze saved sources to identify under-researched aspects/topics.",
            params_schema={"topics": "list[str] (expected topics to cover)", "sources_file": "str"},
            tier_priority=7,
        )
    async def execute(self, params: dict, context=None) -> dict:
        expected = params.get("topics", [])
        log_file = params.get("sources_file", "research_sources.json")
        if not os.path.exists(log_file):
            return {"success": False, "error": "No sources file"}
        with open(log_file, "r") as f:
            sources = json.load(f)
        all_notes = " ".join(s.get("notes", "") for s in sources).lower()
        covered = [t for t in expected if t.lower() in all_notes]
        gaps = [t for t in expected if t.lower() not in all_notes]
        return {
            "success": True,
            "covered_topics": covered,
            "gap_topics": gaps,
            "coverage_pct": round(len(covered) / max(len(expected), 1) * 100),
        }


# ═══════════════════════════════════════════════════════
# WRITING DOMAIN TOOLS
# ═══════════════════════════════════════════════════════

class WordCountTool(SpecializedTool):
    """Count words, characters, sentences, paragraphs."""
    def __init__(self):
        super().__init__(
            name="word_count",
            domain="writing",
            description="Count words, characters, sentences, and paragraphs in text.",
            params_schema={"text": "str"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        text = params.get("text", "")
        words = len(text.split())
        chars = len(text)
        sentences = len(re.split(r'[.!?]+', text))
        paragraphs = len([p for p in text.split("\n\n") if p.strip()])
        return {"success": True, "words": words, "characters": chars, "sentences": sentences, "paragraphs": paragraphs}


class ReadabilityScoreTool(SpecializedTool):
    """Calculate Flesch-Kincaid readability score."""
    def __init__(self):
        super().__init__(
            name="readability_score",
            domain="writing",
            description="Calculate Flesch-Kincaid readability score. Higher = easier to read.",
            params_schema={"text": "str"},
            tier_priority=1,
        )
    async def execute(self, params: dict, context=None) -> dict:
        text = params.get("text", "")
        words = text.split()
        word_count = max(len(words), 1)
        sentences = max(len(re.split(r'[.!?]+', text)), 1)
        syllables = sum(max(1, len(re.findall(r'[aeiouy]+', w.lower()))) for w in words)
        fk_reading_ease = 206.835 - 1.015 * (word_count / sentences) - 84.6 * (syllables / word_count)
        grade_level = 0.39 * (word_count / sentences) + 11.8 * (syllables / word_count) - 15.59
        level = (
            "Very Easy (5th grade)" if fk_reading_ease >= 80 else
            "Easy (6th grade)" if fk_reading_ease >= 70 else
            "Standard (7-8th grade)" if fk_reading_ease >= 60 else
            "Moderate (9-10th grade)" if fk_reading_ease >= 50 else
            "Difficult (College)" if fk_reading_ease >= 30 else
            "Very Difficult (Graduate)"
        )
        return {
            "success": True,
            "flesch_reading_ease": round(fk_reading_ease, 1),
            "grade_level": round(grade_level, 1),
            "level": level,
        }


class OutlineGenerateTool(SpecializedTool):
    """Generate document outline structure."""
    def __init__(self):
        super().__init__(
            name="outline_generate",
            domain="writing",
            description="Generate a structured outline (H1/H2/H3) for a topic. Returns heading hierarchy.",
            params_schema={"topic": "str", "depth": "int (1-3, default 2)", "sections": "int (default 5)"},
            tier_priority=2,
        )
    async def execute(self, params: dict, context=None) -> dict:
        # In production, this would use LLM — here we return a template structure
        topic = params.get("topic", "Untitled")
        depth = min(params.get("depth", 2), 3)
        sections = min(params.get("sections", 5), 8)
        outline = {"title": topic, "sections": []}
        section_names = ["Introduction", "Background", "Core Analysis", "Key Findings", "Discussion", "Methodology", "Results", "Conclusion"]
        for i in range(min(sections, len(section_names))):
            section = {"heading": section_names[i], "level": 2, "subsections": []}
            if depth >= 3:
                section["subsections"] = [
                    {"heading": f"Detail {j+1}", "level": 3} for j in range(2)
                ]
            outline["sections"].append(section)
        return {"success": True, "outline": outline}


class SEOAnalyzeTool(SpecializedTool):
    """Analyze text for SEO optimization.""" 
    def __init__(self):
        super().__init__(
            name="seo_analyze",
            domain="writing",
            description="Analyze content for SEO: keyword density, heading structure, meta description length, readability.",
            params_schema={"text": "str", "target_keyword": "str"},
            tier_priority=3,
        )
    async def execute(self, params: dict, context=None) -> dict:
        text = params.get("text", "")
        keyword = params.get("target_keyword", "").lower()
        words = text.lower().split()
        word_count = len(words)
        keyword_count = words.count(keyword) + text.lower().count(keyword) - words.count(keyword)
        density = round(keyword_count / max(word_count, 1) * 100, 2)
        headings = re.findall(r'^#{1,6}\s+.+', text, re.MULTILINE)
        issues = []
        if density < 0.5: issues.append("Keyword density too low (< 0.5%)")
        if density > 3.0: issues.append("Keyword density too high (> 3.0%) — may be flagged as spam")
        if not headings: issues.append("No headings found — add H1/H2/H3 structure")
        if word_count < 300: issues.append("Content too short for SEO (< 300 words)")
        return {
            "success": True,
            "keyword": keyword,
            "density_pct": density,
            "word_count": word_count,
            "headings": len(headings),
            "issues": issues,
            "score": max(0, 100 - len(issues) * 20),
        }


class ToneAnalyzeTool(SpecializedTool):
    """Analyze writing tone and formality level."""
    def __init__(self):
        super().__init__(
            name="tone_analyze",
            domain="writing",
            description="Analyze the tone of text: formality level, sentiment indicators, and style markers.",
            params_schema={"text": "str"},
            tier_priority=4,
        )
    FORMAL_MARKERS = {"furthermore", "consequently", "nevertheless", "therefore", "hereby", "whereas", "thus", "accordingly"}
    CASUAL_MARKERS = {"gonna", "wanna", "kinda", "pretty much", "cool", "awesome", "hey", "lol", "btw", "tbh"}
    
    async def execute(self, params: dict, context=None) -> dict:
        text = params.get("text", "")
        words = set(text.lower().split())
        formal_count = len(words & self.FORMAL_MARKERS)
        casual_count = len(words & self.CASUAL_MARKERS)
        avg_sentence_len = len(text.split()) / max(len(re.split(r'[.!?]+', text)), 1)
        formality = "formal" if formal_count > casual_count or avg_sentence_len > 20 else "casual" if casual_count > formal_count else "neutral"
        return {
            "success": True,
            "formality": formality,
            "avg_sentence_length": round(avg_sentence_len, 1),
            "formal_markers_found": formal_count,
            "casual_markers_found": casual_count,
        }


class TemplateExpandTool(SpecializedTool):
    """Expand a writing template with variables."""
    def __init__(self):
        super().__init__(
            name="template_expand",
            domain="writing",
            description="Expand a template string by replacing {{variable}} placeholders with provided values.",
            params_schema={"template": "str (with {{var}} placeholders)", "variables": "dict (key-value pairs)"},
            tier_priority=5,
        )
    async def execute(self, params: dict, context=None) -> dict:
        template = params.get("template", "")
        variables = params.get("variables", {})
        result = template
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        unfilled = re.findall(r'\{\{(\w+)\}\}', result)
        return {"success": True, "expanded": result, "unfilled_vars": unfilled}


# ═══════════════════════════════════════════════════════
# DATA ANALYSIS DOMAIN TOOLS
# ═══════════════════════════════════════════════════════

class DataProfileTool(SpecializedTool):
    """Generate statistical profile of a CSV file."""
    def __init__(self):
        super().__init__(
            name="data_profile",
            domain="data_analysis",
            description="Generate statistical profile (mean, median, std, nulls, types) of a CSV file.",
            params_schema={"file_path": "str (CSV file path)", "max_rows": "int (default 10000)"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        import csv
        file_path = params.get("file_path", "")
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = []
                for i, row in enumerate(reader):
                    if i >= params.get("max_rows", 10000):
                        break
                    rows.append(row)
            if not rows:
                return {"success": False, "error": "Empty file"}
            columns = list(rows[0].keys())
            profile = {}
            for col in columns:
                values = [r[col] for r in rows if r[col]]
                num_values = []
                for v in values:
                    try: num_values.append(float(v))
                    except: pass
                profile[col] = {
                    "total": len(rows),
                    "non_null": len(values),
                    "null_pct": round((1 - len(values)/len(rows)) * 100, 1),
                    "unique": len(set(values)),
                }
                if num_values:
                    num_values.sort()
                    profile[col]["mean"] = round(sum(num_values)/len(num_values), 2)
                    profile[col]["min"] = num_values[0]
                    profile[col]["max"] = num_values[-1]
                    profile[col]["median"] = num_values[len(num_values)//2]
                    profile[col]["type"] = "numeric"
                else:
                    profile[col]["type"] = "text"
                    profile[col]["sample"] = values[:3]
            return {"success": True, "rows": len(rows), "columns": columns, "profile": profile}
        except Exception as e:
            return {"success": False, "error": str(e)}


class SQLQueryTool(SpecializedTool):
    """Run SQL against a SQLite database."""
    def __init__(self):
        super().__init__(
            name="sql_query",
            domain="data_analysis",
            description="Execute a SQL query against a SQLite database file. Returns results as list of dicts.",
            params_schema={"db_path": "str", "query": "str (SQL query)", "limit": "int (default 100)"},
            tier_priority=1,
        )
    async def execute(self, params: dict, context=None) -> dict:
        import sqlite3
        db_path = params.get("db_path", "")
        query = params.get("query", "")
        limit = params.get("limit", 100)
        if not query:
            return {"success": False, "error": "No SQL query provided"}
        # Safety: only allow SELECT queries (read-only)
        upper = query.strip().upper()
        if not upper.startswith("SELECT"):
            return {"success": False, "error": "Only SELECT queries are allowed via this tool"}
        # Block multi-statement injection (semicolon-separated queries)
        if ';' in query.strip().rstrip(';'):
            return {"success": False, "error": "Multi-statement queries not allowed"}
        # Block UNION-based injection, subquery writes, and stacked DDL/DML
        _BLOCKED_KEYWORDS = [
            "UNION", "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE",
            "EXEC", "EXECUTE", "ATTACH", "DETACH", "PRAGMA", "LOAD_EXTENSION",
            "INTO OUTFILE", "INTO DUMPFILE", "REPLACE",
        ]
        for kw in _BLOCKED_KEYWORDS:
            if kw in upper:
                return {"success": False, "error": f"Blocked keyword '{kw}' detected in query"}
        try:
            conn = sqlite3.connect(db_path, uri=False)
            conn.row_factory = sqlite3.Row
            # Execute as read-only by disabling writes at connection level
            conn.execute("PRAGMA query_only = ON")
            # Use parameter binding when possible — the query itself is validated above
            cursor = conn.execute(query)
            rows = [dict(r) for r in cursor.fetchmany(limit)]
            conn.close()
            return {"success": True, "rows": rows, "count": len(rows)}
        except Exception as e:
            return {"success": False, "error": str(e)}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ChartSpecTool(SpecializedTool):
    """Generate chart specification (Vega-Lite/matplotlib)."""
    def __init__(self):
        super().__init__(
            name="chart_spec",
            domain="data_analysis",
            description="Generate a chart/plot command for matplotlib from data description.",
            params_schema={"chart_type": "str (bar|line|scatter|pie|hist|heatmap)", "x_column": "str", "y_column": "str", "title": "str"},
            tier_priority=2,
        )
    async def execute(self, params: dict, context=None) -> dict:
        chart_type = params.get("chart_type", "bar")
        x = params.get("x_column", "x")
        y = params.get("y_column", "y")
        title = params.get("title", "Chart")
        TEMPLATES = {
            "bar": f"plt.bar(df['{x}'], df['{y}'])\nplt.title('{title}')\nplt.xlabel('{x}')\nplt.ylabel('{y}')\nplt.xticks(rotation=45)",
            "line": f"plt.plot(df['{x}'], df['{y}'], marker='o')\nplt.title('{title}')\nplt.xlabel('{x}')\nplt.ylabel('{y}')",
            "scatter": f"plt.scatter(df['{x}'], df['{y}'], alpha=0.6)\nplt.title('{title}')\nplt.xlabel('{x}')\nplt.ylabel('{y}')",
            "pie": f"plt.pie(df['{y}'], labels=df['{x}'], autopct='%1.1f%%')\nplt.title('{title}')",
            "hist": f"plt.hist(df['{x}'], bins=20, edgecolor='black')\nplt.title('{title}')\nplt.xlabel('{x}')",
            "heatmap": f"import seaborn as sns\nsns.heatmap(df.corr(), annot=True, cmap='coolwarm')\nplt.title('{title}')",
        }
        code = TEMPLATES.get(chart_type, TEMPLATES["bar"])
        full_code = f"import matplotlib.pyplot as plt\nimport pandas as pd\n\n# df = pd.read_csv('data.csv')\n{code}\nplt.tight_layout()\nplt.savefig('chart.png', dpi=150)\nplt.show()"
        return {"success": True, "python_code": full_code, "chart_type": chart_type}


class OutlierDetectTool(SpecializedTool):
    """Detect outliers in numeric data using IQR method."""
    def __init__(self):
        super().__init__(
            name="outlier_detect",
            domain="data_analysis",
            description="Detect outliers in a list of numeric values using IQR (interquartile range) method.",
            params_schema={"values": "list[float]", "multiplier": "float (default 1.5)"},
            tier_priority=3,
        )
    async def execute(self, params: dict, context=None) -> dict:
        values = sorted(params.get("values", []))
        if len(values) < 4:
            return {"success": False, "error": "Need at least 4 values"}
        mult = params.get("multiplier", 1.5)
        q1 = values[len(values)//4]
        q3 = values[3*len(values)//4]
        iqr = q3 - q1
        lower = q1 - mult * iqr
        upper = q3 + mult * iqr
        outliers = [v for v in values if v < lower or v > upper]
        return {
            "success": True,
            "Q1": q1, "Q3": q3, "IQR": iqr,
            "lower_bound": round(lower, 2),
            "upper_bound": round(upper, 2),
            "outliers": outliers,
            "outlier_count": len(outliers),
        }


class CorrelationTool(SpecializedTool):
    """Compute correlation between two numeric arrays."""
    def __init__(self):
        super().__init__(
            name="correlation",
            domain="data_analysis",
            description="Compute Pearson correlation coefficient between two numeric arrays.",
            params_schema={"x": "list[float]", "y": "list[float]"},
            tier_priority=4,
        )
    async def execute(self, params: dict, context=None) -> dict:
        x = params.get("x", [])
        y = params.get("y", [])
        n = min(len(x), len(y))
        if n < 3:
            return {"success": False, "error": "Need at least 3 values"}
        x, y = x[:n], y[:n]
        mean_x, mean_y = sum(x)/n, sum(y)/n
        cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / n
        std_x = (sum((xi - mean_x)**2 for xi in x) / n) ** 0.5
        std_y = (sum((yi - mean_y)**2 for yi in y) / n) ** 0.5
        if std_x == 0 or std_y == 0:
            return {"success": True, "correlation": 0, "interpretation": "No variance"}
        r = cov / (std_x * std_y)
        interp = (
            "Strong positive" if r > 0.7 else
            "Moderate positive" if r > 0.3 else
            "Weak positive" if r > 0 else
            "No correlation" if r == 0 else
            "Weak negative" if r > -0.3 else
            "Moderate negative" if r > -0.7 else
            "Strong negative"
        )
        return {"success": True, "correlation": round(r, 4), "interpretation": interp}


class PivotTableTool(SpecializedTool):
    """Generate pivot table summary from CSV data."""
    def __init__(self):
        super().__init__(
            name="pivot_table",
            domain="data_analysis",
            description="Generate pandas pivot_table code for summarizing CSV data by groups.",
            params_schema={"index": "str (groupby column)", "values": "str (aggregate column)", "aggfunc": "str (sum|mean|count|max|min)"},
            tier_priority=5,
        )
    async def execute(self, params: dict, context=None) -> dict:
        idx = params.get("index", "category")
        val = params.get("values", "amount")
        agg = params.get("aggfunc", "sum")
        code = (
            f"import pandas as pd\n"
            f"df = pd.read_csv('data.csv')\n"
            f"pivot = df.pivot_table(index='{idx}', values='{val}', aggfunc='{agg}')\n"
            f"pivot = pivot.sort_values('{val}', ascending=False)\n"
            f"print(pivot)\n"
            f"pivot.to_csv('pivot_result.csv')"
        )
        return {"success": True, "python_code": code}


# ═══════════════════════════════════════════════════════
# AUTOMATION DOMAIN TOOLS
# ═══════════════════════════════════════════════════════

class FileBatchTool(SpecializedTool):
    """Batch file operations: rename, move, copy with patterns."""
    def __init__(self):
        super().__init__(
            name="file_batch",
            domain="automation",
            description="Batch file operations: list, rename, move, copy files matching a glob pattern.",
            params_schema={"operation": "str (list|rename|move|copy)", "source_dir": "str", "pattern": "str (glob)", "destination": "str"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        import glob as glob_module
        op = params.get("operation", "list")
        src = params.get("source_dir", ".")
        pattern = params.get("pattern", "*")
        dest = params.get("destination", "")
        files = glob_module.glob(os.path.join(src, pattern))
        if op == "list":
            return {"success": True, "files": files[:50], "count": len(files)}
        elif op == "move" and dest:
            os.makedirs(dest, exist_ok=True)
            moved = 0
            for f in files:
                try:
                    os.rename(f, os.path.join(dest, os.path.basename(f)))
                    moved += 1
                except: pass
            return {"success": True, "moved": moved}
        return {"success": False, "error": f"Operation '{op}' not fully implemented or missing params"}


class ScheduleTaskTool(SpecializedTool):
    """Create a scheduled task."""
    def __init__(self):
        super().__init__(
            name="schedule_task",
            domain="automation",
            description="Create a scheduled task (cron-like) to run a command at intervals.",
            params_schema={"name": "str", "command": "str", "interval_minutes": "int"},
            tier_priority=1,
        )
    async def execute(self, params: dict, context=None) -> dict:
        name = _sanitize_shell_arg(params.get("name", "task"))
        cmd = _sanitize_shell_arg(params.get("command", ""))
        interval = params.get("interval_minutes", 60)
        # Windows Task Scheduler — use argument list
        cmd_list = [
            'schtasks', '/create', '/tn', name, '/tr', cmd,
            '/sc', 'minute', '/mo', str(interval), '/f'
        ]
        try:
            result = _safe_run_list(cmd_list, timeout=10)
            return {"success": result.returncode == 0, "output": result.stdout + result.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ProcessListTool(SpecializedTool):
    """List running processes with memory/CPU usage."""
    def __init__(self):
        super().__init__(
            name="process_list",
            domain="automation",
            description="List running processes sorted by memory or CPU usage.",
            params_schema={"sort_by": "str (memory|cpu)", "limit": "int (default 20)"},
            tier_priority=2,
        )
    async def execute(self, params: dict, context=None) -> dict:
        sort_by = params.get("sort_by", "memory")
        limit = params.get("limit", 20)
        sort_prop = "WorkingSet" if sort_by == "memory" else "CPU"
        cmd_list = [
            'powershell', '-NoProfile', '-Command',
            f'Get-Process | Sort-Object {sort_prop} -Descending | Select-Object -First {int(limit)} Name, Id, CPU, @{{N="Memory(MB)";E={{[math]::Round($_.WorkingSet64/1MB,1)}}}}'
        ]
        try:
            result = _safe_run_list(cmd_list, timeout=10)
            return {"success": True, "processes": result.stdout}
        except Exception as e:
            return {"success": False, "error": str(e)}


class EnvVariableTool(SpecializedTool):
    """Get/set environment variables."""
    def __init__(self):
        super().__init__(
            name="env_variable",
            domain="automation",
            description="Get or set environment variables. Use 'get' to read, 'set' to write (session only).",
            params_schema={"operation": "str (get|set|list)", "name": "str", "value": "str"},
            tier_priority=3,
        )
    async def execute(self, params: dict, context=None) -> dict:
        op = params.get("operation", "get")
        name = params.get("name", "")
        if op == "get":
            val = os.environ.get(name, None)
            return {"success": val is not None, "value": val or f"'{name}' not set"}
        elif op == "set":
            os.environ[name] = params.get("value", "")
            return {"success": True, "set": f"{name}={params.get('value', '')}"}
        elif op == "list":
            return {"success": True, "variables": dict(list(os.environ.items())[:30])}
        return {"success": False, "error": f"Unknown operation: {op}"}


class SystemInfoTool(SpecializedTool):
    """Get system information."""
    def __init__(self):
        super().__init__(
            name="system_info",
            domain="automation",
            description="Get system info: OS, CPU, RAM, disk usage, hostname.",
            params_schema={},
            tier_priority=4,
        )
    async def execute(self, params: dict, context=None) -> dict:
        import platform
        import shutil
        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "architecture": platform.machine(),
            "hostname": platform.node(),
            "python_version": platform.python_version(),
        }
        try:
            disk = shutil.disk_usage("/")
            info["disk_total_gb"] = round(disk.total / (1024**3), 1)
            info["disk_free_gb"] = round(disk.free / (1024**3), 1)
        except: pass
        return {"success": True, **info}


class ServiceManageTool(SpecializedTool):
    """Start/stop/restart Windows services."""
    def __init__(self):
        super().__init__(
            name="service_manage",
            domain="automation",
            description="Start, stop, or query status of a Windows service.",
            params_schema={"operation": "str (start|stop|status|list)", "service_name": "str"},
            tier_priority=5,
        )
    async def execute(self, params: dict, context=None) -> dict:
        op = params.get("operation", "status")
        svc = _sanitize_shell_arg(params.get("service_name", ""))
        if op == "list":
            cmd_list = ['powershell', '-NoProfile', '-Command',
                        'Get-Service | Select-Object -First 30 Name, Status | Format-Table']
        elif op == "status":
            cmd_list = ['powershell', '-NoProfile', '-Command',
                        f"Get-Service -Name '{svc}' | Select-Object Name, Status"]
        elif op in ("start", "stop"):
            cmd_list = ['powershell', '-NoProfile', '-Command',
                        f"{op.capitalize()}-Service -Name '{svc}' -Force"]
        else:
            return {"success": False, "error": f"Unknown operation: {op}"}
        try:
            result = _safe_run_list(cmd_list, timeout=15)
            return {"success": result.returncode == 0, "output": result.stdout + result.stderr}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# PRODUCTIVITY DOMAIN TOOLS
# ═══════════════════════════════════════════════════════

class FileHashTool(SpecializedTool):
    """Compute file hashes."""
    def __init__(self):
        super().__init__(
            name="file_hash",
            domain="productivity",
            description="Compute MD5/SHA256 hash of a file for integrity verification.",
            params_schema={"file_path": "str", "algorithm": "str (md5|sha256)"},
            tier_priority=0,
        )
    async def execute(self, params: dict, context=None) -> dict:
        file_path = params.get("file_path", "")
        algo = params.get("algorithm", "sha256")
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found"}
        h = hashlib.new(algo)
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return {"success": True, "hash": h.hexdigest(), "algorithm": algo, "file": file_path}


class TextSearchReplaceTool(SpecializedTool):
    """Search and replace text in files."""
    def __init__(self):
        super().__init__(
            name="text_search_replace",
            domain="productivity",
            description="Find and replace text in a file. Supports regex.",
            params_schema={"file_path": "str", "search": "str", "replace": "str", "is_regex": "bool"},
            tier_priority=1,
        )
    async def execute(self, params: dict, context=None) -> dict:
        file_path = params.get("file_path", "")
        search = params.get("search", "")
        replace_with = params.get("replace", "")
        if not os.path.exists(file_path):
            return {"success": False, "error": "File not found"}
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        if params.get("is_regex"):
            new_content, count = re.subn(search, replace_with, content)
        else:
            count = content.count(search)
            new_content = content.replace(search, replace_with)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        return {"success": True, "replacements": count}


class TimerTool(SpecializedTool):
    """Simple timer/stopwatch."""
    def __init__(self):
        super().__init__(
            name="timer",
            domain="productivity",
            description="Start a countdown timer or measure elapsed time.",
            params_schema={"duration_seconds": "int (0 for stopwatch mode)"},
            tier_priority=2,
        )
    async def execute(self, params: dict, context=None) -> dict:
        duration = params.get("duration_seconds", 0)
        if duration > 0:
            return {"success": True, "action": "timer_started", "duration": duration, "ends_at": time.strftime("%H:%M:%S", time.localtime(time.time() + duration))}
        return {"success": True, "action": "timestamp", "current_time": time.strftime("%Y-%m-%d %H:%M:%S")}


# ═══════════════════════════════════════════════════════
# BROWSER INTERACTION TOOLS
# Concrete browser automation for agents that need web access.
# ═══════════════════════════════════════════════════════

class BrowserNavigateTool(SpecializedTool):
    """Navigate browser to a specific URL using keyboard shortcuts."""
    def __init__(self):
        super().__init__(
            name="browser_navigate",
            domain="research",
            description="Navigate the active browser to a URL. Uses Ctrl+L to focus address bar, types URL, presses Enter. Waits for page load.",
            params_schema={"url": "str (full URL to navigate to)"},
            tier_priority=8,
        )
    async def execute(self, params: dict, context=None) -> dict:
        url = params.get("url", "")
        if not url:
            return {"success": False, "error": "No URL provided"}
        # Return as instruction sequence for the agent to execute
        steps = [
            {"action": "hotkey", "params": {"keys": ["ctrl", "l"]}, "description": "Focus address bar"},
            {"action": "wait", "params": {"seconds": 0.3}},
            {"action": "type_text_fast", "params": {"text": url}, "description": f"Type URL: {url}"},
            {"action": "press_key", "params": {"key": "enter"}, "description": "Navigate"},
            {"action": "wait", "params": {"seconds": 2}, "description": "Wait for page load"},
        ]
        return {
            "success": True,
            "instruction": f"Navigate to: {url}",
            "steps": steps,
            "tip": "After executing these steps, take a screenshot to verify the page loaded.",
        }


class GoogleSearchTool(SpecializedTool):
    """Perform a Google search through the browser."""
    def __init__(self):
        super().__init__(
            name="google_search",
            domain="research",
            description="Perform a Google search by navigating to google.com and entering search query. Returns step instructions.",
            params_schema={"query": "str (search query)"},
            tier_priority=9,
        )
    async def execute(self, params: dict, context=None) -> dict:
        query = params.get("query", "")
        if not query:
            return {"success": False, "error": "No search query provided"}
        search_url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
        steps = [
            {"action": "hotkey", "params": {"keys": ["ctrl", "l"]}, "description": "Focus address bar"},
            {"action": "wait", "params": {"seconds": 0.3}},
            {"action": "type_text_fast", "params": {"text": search_url}, "description": f"Type Google search URL"},
            {"action": "press_key", "params": {"key": "enter"}, "description": "Search"},
            {"action": "wait", "params": {"seconds": 2}, "description": "Wait for results"},
        ]
        return {
            "success": True,
            "instruction": f"Google search: {query}",
            "search_url": search_url,
            "steps": steps,
            "tip": "After search results load, scroll down and click on relevant results. Read content, then search again with refined query if needed.",
        }


class ExtractPageTextTool(SpecializedTool):
    """Extract text content from current browser page via Ctrl+A, Ctrl+C."""
    def __init__(self):
        super().__init__(
            name="extract_page_text",
            domain="research",
            description="Extract all text from current browser page using Select All + Copy. Returns clipboard content.",
            params_schema={},
            tier_priority=10,
        )
    async def execute(self, params: dict, context=None) -> dict:
        steps = [
            {"action": "hotkey", "params": {"keys": ["ctrl", "a"]}, "description": "Select all text"},
            {"action": "wait", "params": {"seconds": 0.2}},
            {"action": "hotkey", "params": {"keys": ["ctrl", "c"]}, "description": "Copy to clipboard"},
            {"action": "wait", "params": {"seconds": 0.3}},
        ]
        return {
            "success": True,
            "instruction": "Select all page text and copy to clipboard",
            "steps": steps,
            "tip": "After copying, use clipboard_get to read the content. Then use web_extract tool to structure it.",
        }


class OpenNewTabTool(SpecializedTool):
    """Open new browser tab and optionally navigate to URL."""
    def __init__(self):
        super().__init__(
            name="open_new_tab",
            domain="research",
            description="Open a new browser tab. Optionally navigate to a URL.",
            params_schema={"url": "str (optional URL to open)"},
            tier_priority=11,
        )
    async def execute(self, params: dict, context=None) -> dict:
        url = params.get("url", "")
        steps = [
            {"action": "hotkey", "params": {"keys": ["ctrl", "t"]}, "description": "Open new tab"},
            {"action": "wait", "params": {"seconds": 0.5}},
        ]
        if url:
            steps.extend([
                {"action": "type_text_fast", "params": {"text": url}, "description": f"Type URL: {url}"},
                {"action": "press_key", "params": {"key": "enter"}, "description": "Navigate"},
                {"action": "wait", "params": {"seconds": 2}, "description": "Wait for page load"},
            ])
        return {"success": True, "instruction": f"Open new tab{' → ' + url if url else ''}", "steps": steps}


class SummarizeContentTool(SpecializedTool):
    """Summarize text content into key points with word counts."""
    def __init__(self):
        super().__init__(
            name="summarize_content",
            domain="research",
            description="Summarize clipboard/input text into structured key points. Returns summary, key facts, word count.",
            params_schema={"text": "str (text to summarize)", "max_points": "int (default 5)"},
            tier_priority=12,
        )
    async def execute(self, params: dict, context=None) -> dict:
        text = params.get("text", "")
        max_points = params.get("max_points", 5)
        if not text or len(text) < 20:
            return {"success": False, "error": "Text too short to summarize. Need at least 20 characters."}
        
        # Split into sentences and extract key ones
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if len(s.strip()) > 15]
        
        # Score sentences by keyword density and position
        scored = []
        important_words = set()
        all_words = text.lower().split()
        word_freq = {}
        for w in all_words:
            w = re.sub(r'[^a-z]', '', w)
            if len(w) > 3:
                word_freq[w] = word_freq.get(w, 0) + 1
        
        # Top frequent words are important
        sorted_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:20]
        important_words = {w for w, _ in sorted_words}
        
        for i, sent in enumerate(sentences):
            score = 0
            sent_words = set(re.sub(r'[^a-z\s]', '', sent.lower()).split())
            score += len(sent_words & important_words) * 2
            if i < 3:
                score += 3  # Boost first sentences
            if any(kw in sent.lower() for kw in ["important", "key", "main", "significant", "result", "conclusion", "therefore"]):
                score += 5
            scored.append((score, sent))
        
        scored.sort(reverse=True)
        key_points = [s for _, s in scored[:max_points]]
        
        return {
            "success": True,
            "key_points": key_points,
            "word_count": len(all_words),
            "sentence_count": len(sentences),
            "top_keywords": [w for w, _ in sorted_words[:10]],
        }


# ═══════════════════════════════════════════════════════
# WINDOWS APP MANAGEMENT TOOLS
# Smart Windows application control for automation/productivity.
# ═══════════════════════════════════════════════════════

class WindowManagerTool(SpecializedTool):
    """List and manage open windows."""
    def __init__(self):
        super().__init__(
            name="window_manager",
            domain="automation",
            description="List all open windows with titles, or focus/minimize/maximize a specific window by title.",
            params_schema={"operation": "str (list|focus|minimize|maximize|close)", "title": "str (window title substring)"},
            tier_priority=6,
        )
    async def execute(self, params: dict, context=None) -> dict:
        op = params.get("operation", "list")
        title = params.get("title", "")
        
        if op == "list":
            cmd_list = ['powershell', '-NoProfile', '-Command',
                        "Get-Process | Where-Object {$_.MainWindowTitle -ne ''} | Select-Object -First 25 Id, MainWindowTitle | Format-Table -AutoSize"]
            try:
                result = _safe_run_list(cmd_list, timeout=10)
                return {"success": True, "windows": result.stdout}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        elif op == "focus" and title:
            # Use pyautogui-compatible approach
            try:
                import pyautogui
                import pygetwindow as gw
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    win = windows[0]
                    if win.isMinimized:
                        win.restore()
                    win.activate()
                    return {"success": True, "focused": win.title}
                return {"success": False, "error": f"No window found with title containing '{title}'"}
            except Exception as e:
                # Fallback to alt-tab approach
                return {"success": False, "error": str(e), "tip": "Use focus_window action or Alt+Tab manually"}
        
        elif op in ("minimize", "maximize", "close") and title:
            try:
                import pygetwindow as gw
                windows = gw.getWindowsWithTitle(title)
                if windows:
                    win = windows[0]
                    if op == "minimize":
                        win.minimize()
                    elif op == "maximize":
                        win.maximize()
                    elif op == "close":
                        win.close()
                    return {"success": True, "action": op, "window": win.title}
                return {"success": False, "error": f"Window '{title}' not found"}
            except Exception as e:
                return {"success": False, "error": str(e)}
        
        return {"success": False, "error": f"Invalid operation or missing title"}


class AppLauncherTool(SpecializedTool):
    """Smart app launcher with fallback strategies."""
    def __init__(self):
        super().__init__(
            name="smart_launch",
            domain="automation",
            description="Launch a Windows app by name with smart resolution. Knows common apps like Chrome, Notepad, VS Code, Word, Excel.",
            params_schema={"app_name": "str (app name, e.g. 'chrome', 'notepad', 'word')", "wait_seconds": "int (default 2)"},
            tier_priority=7,
        )
    
    APP_COMMANDS = {
        "chrome": "start chrome", "google chrome": "start chrome",
        "edge": "start msedge", "microsoft edge": "start msedge",
        "firefox": "start firefox",
        "notepad": "notepad", "notepad++": "start notepad++",
        "vscode": "code", "vs code": "code", "visual studio code": "code",
        "word": "start winword", "microsoft word": "start winword",
        "excel": "start excel", "microsoft excel": "start excel",
        "powerpoint": "start powerpnt", "ppt": "start powerpnt",
        "explorer": "explorer", "file explorer": "explorer",
        "cmd": "start cmd", "command prompt": "start cmd",
        "powershell": "start powershell",
        "terminal": "start wt", "windows terminal": "start wt",
        "paint": "mspaint", "calculator": "calc",
        "task manager": "taskmgr",
        "settings": "start ms-settings:",
        "snipping tool": "snippingtool",
        "outlook": "start outlook",
        "teams": "start msteams:",
        "slack": "start slack",
        "discord": "start discord",
    }
    
    async def execute(self, params: dict, context=None) -> dict:
        app_name = params.get("app_name", "").lower().strip()
        wait = params.get("wait_seconds", 2)
        
        cmd = self.APP_COMMANDS.get(app_name)
        if not cmd:
            # Try fuzzy match
            for key, val in self.APP_COMMANDS.items():
                if app_name in key or key in app_name:
                    cmd = val
                    break
        
        if not cmd:
            # Last resort: try 'start' command — sanitize app_name to prevent injection
            # Only allow alphanumeric, spaces, hyphens, dots, and underscores
            safe_name = re.sub(r'[^a-zA-Z0-9 _.\-]', '', app_name)
            if not safe_name:
                return {"success": False, "error": f"Invalid app name: '{app_name}'"}
            cmd = f"start {safe_name}"
        
        try:
            # Use argument list instead of shell=True
            # For 'start' commands on Windows, route through cmd /c
            cmd_parts = cmd.split()
            if cmd_parts and cmd_parts[0].lower() == 'start':
                # 'start' is a shell built-in; use cmd /c with explicit arg list
                cmd_parts = ['cmd', '/c'] + cmd_parts
            subprocess.Popen(cmd_parts)
            await asyncio.sleep(min(wait, 5))
            return {"success": True, "launched": app_name, "command": cmd}
        except Exception as e:
            return {"success": False, "error": str(e), "tip": f"Try using open_app action with name='{app_name}'"}


class ClipboardManagerTool(SpecializedTool):
    """Advanced clipboard operations."""
    def __init__(self):
        super().__init__(
            name="clipboard_manager",
            domain="automation",
            description="Advanced clipboard: get, set, append to clipboard. Supports text manipulation before paste.",
            params_schema={"operation": "str (get|set|append|clear)", "text": "str (for set/append)"},
            tier_priority=8,
        )
    async def execute(self, params: dict, context=None) -> dict:
        op = params.get("operation", "get")
        try:
            import pyperclip
            if op == "get":
                content = pyperclip.paste()
                return {"success": True, "content": content[:2000], "length": len(content)}
            elif op == "set":
                pyperclip.copy(params.get("text", ""))
                return {"success": True, "copied": True}
            elif op == "append":
                existing = pyperclip.paste()
                new_text = existing + "\n" + params.get("text", "")
                pyperclip.copy(new_text)
                return {"success": True, "total_length": len(new_text)}
            elif op == "clear":
                pyperclip.copy("")
                return {"success": True, "cleared": True}
            return {"success": False, "error": f"Unknown operation: {op}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# DOCUMENT CREATION TOOLS
# For agents that need to create/edit documents.
# ═══════════════════════════════════════════════════════

class CreateTextFileTool(SpecializedTool):
    """Create a text file with content."""
    def __init__(self):
        super().__init__(
            name="create_text_file",
            domain="writing",
            description="Create a text file (.txt, .md, .html) with specified content on the Desktop or given path.",
            params_schema={"filename": "str", "content": "str", "directory": "str (default Desktop)"},
            tier_priority=6,
        )
    async def execute(self, params: dict, context=None) -> dict:
        filename = params.get("filename", f"document_{int(time.time())}.txt")
        content = params.get("content", "")
        directory = params.get("directory", "")
        
        if not directory:
            directory = os.path.join(os.path.expanduser("~"), "Desktop")
        
        os.makedirs(directory, exist_ok=True)
        filepath = os.path.join(directory, filename)
        
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "path": filepath,
                "filename": filename,
                "size_bytes": len(content.encode("utf-8")),
                "tip": f"File created at {filepath}. Open it with: notepad \"{filepath}\"",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class AppendToFileTool(SpecializedTool):
    """Append content to an existing file."""
    def __init__(self):
        super().__init__(
            name="append_to_file",
            domain="writing",
            description="Append text content to an existing file. Creates file if it doesn't exist.",
            params_schema={"filepath": "str", "content": "str", "separator": "str (default newline)"},
            tier_priority=7,
        )
    async def execute(self, params: dict, context=None) -> dict:
        filepath = params.get("filepath", "")
        content = params.get("content", "")
        separator = params.get("separator", "\n")
        
        if not filepath:
            return {"success": False, "error": "No filepath provided"}
        
        try:
            mode = "a" if os.path.exists(filepath) else "w"
            with open(filepath, mode, encoding="utf-8") as f:
                if mode == "a":
                    f.write(separator)
                f.write(content)
            return {"success": True, "path": filepath, "appended_bytes": len(content.encode("utf-8"))}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ReadFileTool(SpecializedTool):
    """Read content of a file."""
    def __init__(self):
        super().__init__(
            name="read_file_content",
            domain="writing",
            description="Read the text content of a file. Returns first N characters.",
            params_schema={"filepath": "str", "max_chars": "int (default 3000)"},
            tier_priority=8,
        )
    async def execute(self, params: dict, context=None) -> dict:
        filepath = params.get("filepath", "")
        max_chars = params.get("max_chars", 3000)
        
        if not os.path.exists(filepath):
            return {"success": False, "error": f"File not found: {filepath}"}
        
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(max_chars)
            return {
                "success": True,
                "content": content,
                "total_size": os.path.getsize(filepath),
                "truncated": os.path.getsize(filepath) > max_chars,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class FormatMarkdownTool(SpecializedTool):
    """Generate markdown-formatted document structure."""
    def __init__(self):
        super().__init__(
            name="format_markdown",
            domain="writing",
            description="Generate a well-formatted Markdown document from raw text with automatic heading, list, and paragraph detection.",
            params_schema={"raw_text": "str", "title": "str", "include_toc": "bool (default false)"},
            tier_priority=9,
        )
    async def execute(self, params: dict, context=None) -> dict:
        raw = params.get("raw_text", "")
        title = params.get("title", "Document")
        include_toc = params.get("include_toc", False)
        
        lines = raw.split("\n")
        formatted_lines = [f"# {title}", ""]
        headings = []
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted_lines.append("")
                continue
            
            # Detect potential headings (short, title-case or all-caps lines)
            if len(stripped) < 60 and (stripped.istitle() or stripped.isupper()) and not stripped.endswith(('.', ',', ';')):
                heading = f"## {stripped.title()}"
                formatted_lines.append(heading)
                headings.append(stripped.title())
            elif stripped.startswith(('-', '*', '•')):
                formatted_lines.append(f"- {stripped.lstrip('-*• ')}")
            elif re.match(r'^\d+[.)]\s', stripped):
                formatted_lines.append(stripped)
            else:
                formatted_lines.append(stripped)
        
        if include_toc and headings:
            toc = ["## Table of Contents", ""]
            for h in headings:
                anchor = h.lower().replace(" ", "-")
                toc.append(f"- [{h}](#{anchor})")
            toc.append("")
            formatted_lines = formatted_lines[:2] + toc + formatted_lines[2:]
        
        markdown = "\n".join(formatted_lines)
        return {"success": True, "markdown": markdown, "headings": headings, "word_count": len(raw.split())}


# ═══════════════════════════════════════════════════════
# ENHANCED CODING TOOLS
# Advanced tools for S/S+ tier coding agents.
# ═══════════════════════════════════════════════════════

class RunScriptTool(SpecializedTool):
    """Run Python/Node script and capture output."""
    def __init__(self):
        super().__init__(
            name="run_script",
            domain="coding",
            description="Run a Python or Node.js script file. Returns stdout, stderr, exit code.",
            params_schema={"file_path": "str", "language": "str (python|node)", "args": "str (command line args)", "timeout": "int (default 30)"},
            tier_priority=8,
        )
    async def execute(self, params: dict, context=None) -> dict:
        fpath = params.get("file_path", "")
        lang = params.get("language", "python")
        args = params.get("args", "")
        timeout = min(params.get("timeout", 30), 60)
        
        if not os.path.exists(fpath):
            return {"success": False, "error": f"File not found: {fpath}"}
        
        interpreter = "python" if lang == "python" else "node"
        cmd_list = [interpreter, fpath] + (args.split() if args else [])
        
        try:
            result = _safe_run_list(cmd_list, timeout=timeout)
            return {
                "success": result.returncode == 0,
                "stdout": result.stdout[-2000:] if result.stdout else "",
                "stderr": result.stderr[-1000:] if result.stderr else "",
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Script timed out after {timeout}s"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class FileTreeTool(SpecializedTool):
    """Generate directory tree structure."""
    def __init__(self):
        super().__init__(
            name="file_tree",
            domain="coding",
            description="Generate a directory tree structure showing files and folders. Helps understand project layout.",
            params_schema={"directory": "str (default '.')", "max_depth": "int (default 3)", "show_hidden": "bool (default false)"},
            tier_priority=9,
        )
    async def execute(self, params: dict, context=None) -> dict:
        directory = params.get("directory", ".")
        max_depth = min(params.get("max_depth", 3), 5)
        show_hidden = params.get("show_hidden", False)
        
        if not os.path.isdir(directory):
            return {"success": False, "error": f"Not a directory: {directory}"}
        
        tree_lines = []
        file_count = 0
        dir_count = 0
        
        def walk(path, prefix="", depth=0):
            nonlocal file_count, dir_count
            if depth > max_depth:
                return
            try:
                entries = sorted(os.listdir(path))
            except PermissionError:
                return
            
            dirs = []
            files = []
            for e in entries:
                if not show_hidden and e.startswith('.'):
                    continue
                if e in ('node_modules', '__pycache__', '.git', 'dist', 'build', '.next', 'venv'):
                    continue
                full = os.path.join(path, e)
                if os.path.isdir(full):
                    dirs.append(e)
                else:
                    files.append(e)
            
            items = dirs + files
            for i, name in enumerate(items):
                is_last = (i == len(items) - 1)
                connector = "└── " if is_last else "├── "
                full = os.path.join(path, name)
                
                if os.path.isdir(full):
                    tree_lines.append(f"{prefix}{connector}{name}/")
                    dir_count += 1
                    new_prefix = prefix + ("    " if is_last else "│   ")
                    walk(full, new_prefix, depth + 1)
                else:
                    size = os.path.getsize(full)
                    size_str = f" ({size:,}B)" if size < 10000 else f" ({size//1024}KB)"
                    tree_lines.append(f"{prefix}{connector}{name}{size_str}")
                    file_count += 1
        
        tree_lines.append(f"{os.path.basename(directory)}/")
        walk(directory)
        
        return {
            "success": True,
            "tree": "\n".join(tree_lines[:100]),
            "total_files": file_count,
            "total_dirs": dir_count,
            "truncated": len(tree_lines) > 100,
        }


class CreateFileTool(SpecializedTool):
    """Create a code file with content."""
    def __init__(self):
        super().__init__(
            name="create_code_file",
            domain="coding",
            description="Create a code file with content. Automatically creates parent directories.",
            params_schema={"file_path": "str", "content": "str", "overwrite": "bool (default false)"},
            tier_priority=10,
        )
    async def execute(self, params: dict, context=None) -> dict:
        fpath = params.get("file_path", "")
        content = params.get("content", "")
        overwrite = params.get("overwrite", False)
        
        if not fpath:
            return {"success": False, "error": "No file path provided"}
        
        if os.path.exists(fpath) and not overwrite:
            return {"success": False, "error": f"File exists: {fpath}. Set overwrite=true to overwrite."}
        
        try:
            os.makedirs(os.path.dirname(fpath), exist_ok=True) if os.path.dirname(fpath) else None
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            return {
                "success": True,
                "path": fpath,
                "size_bytes": len(content.encode("utf-8")),
                "lines": content.count("\n") + 1,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


class DiffTool(SpecializedTool):
    """Show differences between two files."""
    def __init__(self):
        super().__init__(
            name="diff_files",
            domain="coding",
            description="Show line-by-line differences between two files. Useful for code review.",
            params_schema={"file_a": "str (first file path)", "file_b": "str (second file path)"},
            tier_priority=11,
        )
    async def execute(self, params: dict, context=None) -> dict:
        file_a = params.get("file_a", "")
        file_b = params.get("file_b", "")
        
        for f in [file_a, file_b]:
            if not os.path.exists(f):
                return {"success": False, "error": f"File not found: {f}"}
        
        try:
            import difflib
            with open(file_a, "r", encoding="utf-8", errors="replace") as fa:
                lines_a = fa.readlines()
            with open(file_b, "r", encoding="utf-8", errors="replace") as fb:
                lines_b = fb.readlines()
            
            diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=file_a, tofile=file_b, lineterm=""))
            return {
                "success": True,
                "diff": "\n".join(diff[:100]),
                "added_lines": sum(1 for l in diff if l.startswith("+")),
                "removed_lines": sum(1 for l in diff if l.startswith("-")),
                "truncated": len(diff) > 100,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# ENHANCED DATA ANALYSIS TOOLS
# Advanced analysis capabilities.
# ═══════════════════════════════════════════════════════

class DataCleanTool(SpecializedTool):
    """Clean and preprocesss data."""
    def __init__(self):
        super().__init__(
            name="data_clean",
            domain="data_analysis",
            description="Generate Python code to clean a CSV: remove nulls, fix types, deduplicate, normalize columns.",
            params_schema={"file_path": "str (CSV path)", "operations": "list[str] (remove_nulls|fix_types|deduplicate|normalize)"},
            tier_priority=6,
        )
    async def execute(self, params: dict, context=None) -> dict:
        fpath = params.get("file_path", "data.csv")
        ops = params.get("operations", ["remove_nulls", "fix_types"])
        
        code_parts = [
            "import pandas as pd\n",
            f"df = pd.read_csv('{fpath}')",
            f"print(f'Original shape: {{df.shape}}')\n",
        ]
        
        if "remove_nulls" in ops:
            code_parts.append("# Remove rows with null values")
            code_parts.append("df = df.dropna()")
        if "fix_types" in ops:
            code_parts.append("# Auto-convert columns to correct types")
            code_parts.append("for col in df.columns:")
            code_parts.append("    try: df[col] = pd.to_numeric(df[col])")
            code_parts.append("    except: pass")
        if "deduplicate" in ops:
            code_parts.append("# Remove duplicate rows")
            code_parts.append("df = df.drop_duplicates()")
        if "normalize" in ops:
            code_parts.append("# Normalize column names")
            code_parts.append("df.columns = [c.strip().lower().replace(' ', '_') for c in df.columns]")
        
        code_parts.append(f"\nprint(f'Cleaned shape: {{df.shape}}')")
        code_parts.append(f"df.to_csv('{fpath.replace('.csv', '_cleaned.csv')}', index=False)")
        
        return {"success": True, "python_code": "\n".join(code_parts)}


class StatisticalTestTool(SpecializedTool):
    """Generate code for statistical tests."""
    def __init__(self):
        super().__init__(
            name="statistical_test",
            domain="data_analysis",
            description="Generate Python code for common statistical tests: t-test, chi-square, ANOVA, correlation.",
            params_schema={"test_type": "str (ttest|chi_square|anova|correlation|regression)", "columns": "list[str]"},
            tier_priority=7,
        )
    async def execute(self, params: dict, context=None) -> dict:
        test_type = params.get("test_type", "ttest")
        columns = params.get("columns", ["col_a", "col_b"])
        
        TEMPLATES = {
            "ttest": f"""from scipy import stats
import pandas as pd
df = pd.read_csv('data.csv')
t_stat, p_value = stats.ttest_ind(df['{columns[0]}'].dropna(), df['{columns[1] if len(columns)>1 else columns[0]}'].dropna())
print(f't-statistic: {{t_stat:.4f}}')
print(f'p-value: {{p_value:.4f}}')
print(f'Significant (p<0.05): {{p_value < 0.05}}')""",
            
            "chi_square": f"""from scipy import stats
import pandas as pd
df = pd.read_csv('data.csv')
contingency = pd.crosstab(df['{columns[0]}'], df['{columns[1] if len(columns)>1 else columns[0]}'])
chi2, p_value, dof, expected = stats.chi2_contingency(contingency)
print(f'Chi-square: {{chi2:.4f}}, p-value: {{p_value:.4f}}, dof: {{dof}}')""",
            
            "anova": f"""from scipy import stats
import pandas as pd
df = pd.read_csv('data.csv')
groups = [group['{columns[0]}'].values for name, group in df.groupby('{columns[1] if len(columns)>1 else columns[0]}')]
f_stat, p_value = stats.f_oneway(*groups)
print(f'F-statistic: {{f_stat:.4f}}, p-value: {{p_value:.4f}}')""",
            
            "regression": f"""from sklearn.linear_model import LinearRegression
import pandas as pd
import numpy as np
df = pd.read_csv('data.csv')
X = df[['{columns[0]}']].values
y = df['{columns[1] if len(columns)>1 else columns[0]}'].values
model = LinearRegression().fit(X, y)
print(f'R² score: {{model.score(X, y):.4f}}')
print(f'Coefficient: {{model.coef_[0]:.4f}}, Intercept: {{model.intercept_:.4f}}')""",
        }
        
        code = TEMPLATES.get(test_type, TEMPLATES["ttest"])
        return {"success": True, "python_code": code, "test_type": test_type}


# ═══════════════════════════════════════════════════════
# ENHANCED DESIGN TOOLS
# Additional design capabilities.
# ═══════════════════════════════════════════════════════

class ScreenshotRegionTool(SpecializedTool):
    """Capture a specific region of the screen."""
    def __init__(self):
        super().__init__(
            name="screenshot_region",
            domain="design",
            description="Capture a rectangular region of screen. Save as PNG for reference.",
            params_schema={"x": "int", "y": "int", "width": "int", "height": "int", "save_path": "str"},
            tier_priority=8,
        )
    async def execute(self, params: dict, context=None) -> dict:
        try:
            from PIL import ImageGrab
            x, y = params.get("x", 0), params.get("y", 0)
            w, h = params.get("width", 300), params.get("height", 200)
            save_path = params.get("save_path", f"screenshot_{int(time.time())}.png")
            
            img = ImageGrab.grab(bbox=(x, y, x + w, y + h))
            img.save(save_path, "PNG")
            return {"success": True, "path": save_path, "size": f"{w}x{h}"}
        except Exception as e:
            return {"success": False, "error": str(e)}


class ImageResizeTool(SpecializedTool):
    """Resize an image file."""
    def __init__(self):
        super().__init__(
            name="image_resize",
            domain="design",
            description="Resize an image to specified dimensions or scale percentage.",
            params_schema={"input_path": "str", "output_path": "str", "width": "int", "height": "int", "scale_pct": "int (alternative to w/h)"},
            tier_priority=9,
        )
    async def execute(self, params: dict, context=None) -> dict:
        try:
            from PIL import Image
            input_path = params.get("input_path", "")
            output_path = params.get("output_path", input_path)
            
            if not os.path.exists(input_path):
                return {"success": False, "error": f"Image not found: {input_path}"}
            
            img = Image.open(input_path)
            orig_w, orig_h = img.size
            
            scale = params.get("scale_pct")
            if scale:
                new_w = int(orig_w * scale / 100)
                new_h = int(orig_h * scale / 100)
            else:
                new_w = params.get("width", orig_w)
                new_h = params.get("height", orig_h)
            
            resized = img.resize((new_w, new_h), Image.LANCZOS)
            resized.save(output_path)
            
            return {
                "success": True,
                "original_size": f"{orig_w}x{orig_h}",
                "new_size": f"{new_w}x{new_h}",
                "output_path": output_path,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════
# TOOL REGISTRY — Central lookup for all domain tools
# ═══════════════════════════════════════════════════════

# Each domain's tools, ordered by tier_priority (lower = unlocked first)
DOMAIN_TOOLS: dict[str, list[SpecializedTool]] = {
    "coding": sorted([
        RunTestsTool(), CodeLintTool(), GitOperationTool(), DependencyInstallTool(),
        CodeSearchTool(), CodeFormatTool(), DebugInspectTool(), ProjectScaffoldTool(),
        RunScriptTool(), FileTreeTool(), CreateFileTool(), DiffTool(),
    ], key=lambda t: t.tier_priority),
    
    "design": sorted([
        ColorPickTool(), MeasureSpacingTool(), GeneratePaletteTool(), SnapToGridTool(),
        ExportAssetTool(), FontMatchTool(), ContrastCheckTool(), LayoutGridTool(),
        ScreenshotRegionTool(), ImageResizeTool(),
    ], key=lambda t: t.tier_priority),
    
    "research": sorted([
        WebExtractTool(), SourceCredibilityTool(), CitationFormatTool(), SaveSourceTool(),
        FactCheckTool(), CompareSourcesTool(), ResearchTimelineTool(), GapAnalysisTool(),
        BrowserNavigateTool(), GoogleSearchTool(), ExtractPageTextTool(), OpenNewTabTool(),
        SummarizeContentTool(),
    ], key=lambda t: t.tier_priority),
    
    "writing": sorted([
        WordCountTool(), ReadabilityScoreTool(), OutlineGenerateTool(), SEOAnalyzeTool(),
        ToneAnalyzeTool(), TemplateExpandTool(),
        CreateTextFileTool(), AppendToFileTool(), ReadFileTool(), FormatMarkdownTool(),
    ], key=lambda t: t.tier_priority),
    
    "data_analysis": sorted([
        DataProfileTool(), SQLQueryTool(), ChartSpecTool(), OutlierDetectTool(),
        CorrelationTool(), PivotTableTool(),
        DataCleanTool(), StatisticalTestTool(),
    ], key=lambda t: t.tier_priority),
    
    "automation": sorted([
        FileBatchTool(), ScheduleTaskTool(), ProcessListTool(), EnvVariableTool(),
        SystemInfoTool(), ServiceManageTool(),
        WindowManagerTool(), AppLauncherTool(), ClipboardManagerTool(),
    ], key=lambda t: t.tier_priority),
    
    "productivity": sorted([
        FileHashTool(), TextSearchReplaceTool(), TimerTool(),
    ], key=lambda t: t.tier_priority),
}


def get_tools_for_agent(domain: str, tier: str) -> list[SpecializedTool]:
    """
    Get the specialized tools an agent is allowed to use.
    
    - Looks up domain tools
    - Applies tier limit (only first N tools by priority)
    - Returns empty list if tier doesn't allow specialized tools
    """
    config = get_tier_config(tier)
    
    if not config.specialized_tools_enabled:
        return []
    
    domain_tools = DOMAIN_TOOLS.get(domain, [])
    
    if config.specialized_tools_limit == -1:
        # S/S+ tier: all domain tools
        return list(domain_tools)
    
    # Lower tiers: only first N tools by priority
    return domain_tools[:config.specialized_tools_limit]


def get_cross_domain_tools(primary_domain: str, tier: str) -> list[SpecializedTool]:
    """
    S+ only: get tools from adjacent/related domains.
    Returns first 3 tools from each non-primary domain.
    """
    config = get_tier_config(tier)
    if not config.cross_domain_tools:
        return []
    
    tools = []
    for domain, domain_tools in DOMAIN_TOOLS.items():
        if domain != primary_domain:
            tools.extend(domain_tools[:3])  # First 3 from each other domain
    return tools


def build_tools_prompt(tools: list[SpecializedTool]) -> str:
    """Build the specialized tools section for a system prompt."""
    if not tools:
        return ""
    lines = ["\n━━━ SPECIALIZED TOOLS ━━━"]
    lines.append("Use TOOL: / TOOL_PARAMS: format to invoke these domain-specific tools.\n")
    for tool in tools:
        params_desc = ", ".join(f"{k}: {v}" for k, v in tool.params_schema.items())
        lines.append(f"  TOOL: {tool.name}")
        lines.append(f"    {tool.description}")
        lines.append(f"    TOOL_PARAMS: {{{params_desc}}}")
        lines.append("")
    return "\n".join(lines)


async def execute_tool(tool_name: str, params: dict, available_tools: list[SpecializedTool]) -> dict:
    """Execute a specialized tool by name, if it's in the agent's allowed tools."""
    for tool in available_tools:
        if tool.name == tool_name:
            try:
                return await tool.execute(params)
            except Exception as e:
                logger.error(f"Tool '{tool_name}' execution error: {e}")
                return {"success": False, "error": str(e)}
    return {"success": False, "error": f"Tool '{tool_name}' not available for this agent"}
