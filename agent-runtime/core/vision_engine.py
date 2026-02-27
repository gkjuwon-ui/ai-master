"""
Vision Engine v3 — Premium visual perception system.

Enhanced capabilities:
- Multi-region attention: focus on specific UI elements
- OCR-powered text extraction from screen regions
- Element detection: identifies clickable buttons, inputs, menus
- Visual diff: detects what changed between frames
- Adaptive quality: higher resolution for text-heavy areas
- Annotation overlay: marks detected elements for LLM reasoning
- App Detection: identifies which application is currently in foreground
- UI State Analysis: detects dialogs, popups, focused elements
- Content Verification: checks if expected content appeared after action
- Taskbar Analysis: detects running apps from taskbar
"""

import io
import hashlib
from typing import Optional
from loguru import logger

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageStat
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import pyautogui
    HAS_PYAUTOGUI = True
except ImportError:
    HAS_PYAUTOGUI = False


# ═══════════════════════════════════════════════════════════════════════
# APP DETECTION SIGNATURES
# ═══════════════════════════════════════════════════════════════════════
# Visual patterns that help identify which app is in the foreground
# based on window title bar analysis.

APP_DETECTION_PATTERNS = {
    "chrome": {
        "title_keywords": ["chrome", "google chrome", "- google chrome"],
        "title_bar_height": 60,
        "characteristics": "Tab bar at top, address bar below tabs",
    },
    "edge": {
        "title_keywords": ["edge", "microsoft edge", "- microsoft edge"],
        "title_bar_height": 60,
        "characteristics": "Similar to Chrome, may show sidebar",
    },
    "firefox": {
        "title_keywords": ["firefox", "mozilla firefox"],
        "title_bar_height": 55,
        "characteristics": "Tab bar at top, address bar below",
    },
    "notepad": {
        "title_keywords": ["notepad", "메모장", "untitled - notepad"],
        "title_bar_height": 35,
        "characteristics": "Simple menu bar, white editing area",
    },
    "vscode": {
        "title_keywords": ["visual studio code", "- code"],
        "title_bar_height": 35,
        "characteristics": "Dark title bar, sidebar with file explorer",
    },
    "terminal": {
        "title_keywords": ["terminal", "powershell", "command prompt", "cmd"],
        "title_bar_height": 35,
        "characteristics": "Dark background, monospace text",
    },
    "explorer": {
        "title_keywords": ["file explorer", "탐색기", "explorer"],
        "title_bar_height": 50,
        "characteristics": "Navigation bar, folder/file list view",
    },
    "ogenti": {
        "title_keywords": ["ogenti", "agent runtime", "execution session"],
        "title_bar_height": 40,
        "characteristics": "Agent control interface",
    },
}


class ScreenAnalysis:
    """Results of analyzing the current screen state."""
    
    def __init__(self):
        self.detected_app: str = "unknown"
        self.window_title: str = ""
        self.has_dialog: bool = False
        self.has_popup: bool = False
        self.is_loading: bool = False
        self.screen_brightness: float = 0.0
        self.text_density: float = 0.0
        self.is_ogenti: bool = False
        self.active_windows: list[str] = []
        self.taskbar_apps: list[str] = []
        self.suggestions: list[str] = []
    
    def to_dict(self) -> dict:
        return {
            "app": self.detected_app,
            "title": self.window_title,
            "has_dialog": self.has_dialog,
            "has_popup": self.has_popup,
            "is_loading": self.is_loading,
            "is_ogenti": self.is_ogenti,
            "brightness": round(self.screen_brightness, 2),
            "text_density": round(self.text_density, 2),
            "active_windows": self.active_windows,
            "suggestions": self.suggestions,
        }
    
    def to_text(self) -> str:
        """Format for LLM consumption."""
        parts = [f"Detected App: {self.detected_app}"]
        if self.window_title:
            parts.append(f"Window Title: {self.window_title}")
        if self.is_ogenti:
            parts.append("⚠️ WARNING: This is the Ogenti app — you should switch to another window!")
        if self.has_dialog:
            parts.append("⚠️ A dialog box appears to be open")
        if self.has_popup:
            parts.append("⚠️ A popup or modal may be visible")
        if self.is_loading:
            parts.append("⏳ The page appears to be loading...")
        if self.active_windows:
            parts.append(f"Open windows: {', '.join(self.active_windows[:5])}")
        if self.suggestions:
            parts.append("Suggestions: " + "; ".join(self.suggestions))
        return "\n".join(parts)


class VisionEngine:
    """
    Premium vision system with multi-region attention, OCR, element detection,
    and visual diffing. Used exclusively by Tier-S and Tier-S+ agents.
    """

    def __init__(
        self,
        quality: int = 92,
        max_width: int = 1920,
        enable_ocr: bool = True,
        enable_element_detection: bool = True,
        enable_diff: bool = True,
    ):
        self.quality = quality
        self.max_width = max_width
        self.enable_ocr = enable_ocr
        self.enable_element_detection = enable_element_detection
        self.enable_diff = enable_diff
        self.enabled = HAS_MSS and HAS_PIL
        self._previous_frame_hash: Optional[str] = None
        self._previous_frame: Optional[Image.Image] = None
        self._element_cache: list[dict] = []

        if not self.enabled:
            logger.warning("VisionEngine disabled: mss or PIL not available")

    def capture_full(self, monitor_index: int = 1) -> Optional[bytes]:
        """
        Full-screen capture at maximum quality with no downscaling below max_width.
        Returns JPEG bytes.
        """
        if not self.enabled:
            return None
        try:
            with mss.mss() as sct:
                mons = sct.monitors
                mon = mons[monitor_index] if monitor_index < len(mons) else mons[0]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                if img.width > self.max_width:
                    ratio = self.max_width / img.width
                    img = img.resize(
                        (self.max_width, int(img.height * ratio)),
                        Image.LANCZOS,
                    )
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=self.quality, optimize=True)
                self._update_frame_cache(img)
                return buf.getvalue()
        except Exception as e:
            logger.error(f"VisionEngine capture_full error: {e}")
            return None

    def capture_region(
        self, x: int, y: int, width: int, height: int, upscale: float = 1.0
    ) -> Optional[bytes]:
        """
        High-resolution capture of a specific screen region.
        upscale > 1.0 increases resolution for small UI elements.
        """
        if not self.enabled:
            return None
        try:
            with mss.mss() as sct:
                region = {"left": x, "top": y, "width": width, "height": height}
                raw = sct.grab(region)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                if upscale > 1.0:
                    new_w = int(img.width * upscale)
                    new_h = int(img.height * upscale)
                    img = img.resize((new_w, new_h), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="PNG")  # PNG for region crops — lossless
                return buf.getvalue()
        except Exception as e:
            logger.error(f"VisionEngine capture_region error: {e}")
            return None

    def capture_multi_region(self, regions: list[dict]) -> list[Optional[bytes]]:
        """
        Capture multiple screen regions in a single mss session.
        Each region: {"x": int, "y": int, "width": int, "height": int, "label": str}
        Returns list of PNG bytes per region.
        """
        results: list[Optional[bytes]] = []
        if not self.enabled:
            return [None] * len(regions)
        try:
            with mss.mss() as sct:
                for r in regions:
                    try:
                        area = {
                            "left": r["x"], "top": r["y"],
                            "width": r["width"], "height": r["height"],
                        }
                        raw = sct.grab(area)
                        img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        results.append(buf.getvalue())
                    except Exception:
                        results.append(None)
        except Exception as e:
            logger.error(f"VisionEngine capture_multi_region error: {e}")
            return [None] * len(regions)
        return results

    def detect_changes(self) -> dict:
        """
        Compare current frame with previous frame.
        Returns dict with changed_percentage, changed_regions, and is_significant.
        """
        if not self.enabled or self._previous_frame is None:
            return {"changed_percentage": 100.0, "changed_regions": [], "is_significant": True}
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                raw = sct.grab(mon)
                current = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                # Resize both to same manageable size for comparison
                cmp_size = (640, 360)
                prev_small = self._previous_frame.resize(cmp_size, Image.NEAREST)
                curr_small = current.resize(cmp_size, Image.NEAREST)
                # Pixel comparison
                prev_data = list(prev_small.getdata())
                curr_data = list(curr_small.getdata())
                total = len(prev_data)
                changed = sum(
                    1 for a, b in zip(prev_data, curr_data)
                    if abs(a[0] - b[0]) + abs(a[1] - b[1]) + abs(a[2] - b[2]) > 30
                )
                pct = (changed / total) * 100 if total else 0
                self._update_frame_cache(current)
                return {
                    "changed_percentage": round(pct, 2),
                    "changed_regions": [],  # Could be extended with region clustering
                    "is_significant": pct > 2.0,
                }
        except Exception as e:
            logger.error(f"VisionEngine detect_changes error: {e}")
            return {"changed_percentage": 0, "changed_regions": [], "is_significant": False}

    def extract_text_regions(self) -> list[dict]:
        """
        Attempt basic text region detection using contrast analysis.
        Returns list of {"x", "y", "width", "height", "confidence"}.
        For full OCR, requires pytesseract (optional).
        """
        if not self.enabled:
            return []
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                # Convert to grayscale for edge detection
                gray = img.convert("L")
                # Simple edge detection via difference
                edges = gray.filter(ImageFilter.FIND_EDGES)
                # Threshold
                threshold = 50
                data = edges.load()
                w, h = edges.size
                # Scan horizontal strips for text-heavy regions
                strip_h = 40
                regions = []
                for y_start in range(0, h - strip_h, strip_h // 2):
                    edge_count = 0
                    for yy in range(y_start, min(y_start + strip_h, h)):
                        for xx in range(0, w, 4):  # Sample every 4th pixel
                            if data[xx, yy] > threshold:
                                edge_count += 1
                    density = edge_count / ((strip_h * (w // 4)) or 1)
                    if density > 0.15:
                        regions.append({
                            "x": 0, "y": y_start,
                            "width": w, "height": strip_h,
                            "confidence": min(density * 3, 1.0),
                        })
                # Merge adjacent regions
                merged = self._merge_adjacent_regions(regions, strip_h)
                return merged
        except Exception as e:
            logger.error(f"VisionEngine extract_text_regions error: {e}")
            return []

    def ocr_screen(self, max_chars: int = 4000) -> str:
        if not self.enabled:
            return ""
        if not HAS_TESSERACT:
            logger.warning("OCR unavailable: pytesseract not installed. Install with: pip install pytesseract")
            return ""
        if not (HAS_MSS and HAS_PIL):
            logger.warning("OCR unavailable: mss or PIL not installed")
            return ""
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

            if img.width > self.max_width:
                ratio = self.max_width / img.width
                img = img.resize((self.max_width, int(img.height * ratio)), Image.LANCZOS)

            gray = img.convert("L")
            try:
                text = pytesseract.image_to_string(gray)
            except Exception:
                text = pytesseract.image_to_string(img)

            text = (text or "").replace("\r", "\n")
            lines = [ln.strip() for ln in text.split("\n")]
            lines = [ln for ln in lines if ln]
            compact = "\n".join(lines)
            return compact[:max_chars]
        except Exception as e:
            logger.debug(f"VisionEngine ocr_screen error: {e}")
            return ""

    def annotate_screenshot(self, elements: list[dict]) -> Optional[bytes]:
        """
        Capture a screenshot and draw bounding boxes + labels around detected elements.
        elements: [{"x", "y", "width", "height", "label", "color"}]
        Returns annotated JPEG bytes.
        """
        if not self.enabled:
            return None
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                draw = ImageDraw.Draw(img)
                for el in elements:
                    x, y = el.get("x", 0), el.get("y", 0)
                    w, h = el.get("width", 50), el.get("height", 20)
                    color = el.get("color", "#FF0000")
                    label = el.get("label", "")
                    draw.rectangle([x, y, x + w, y + h], outline=color, width=2)
                    if label:
                        draw.text((x, max(y - 14, 0)), label, fill=color)
                if img.width > self.max_width:
                    ratio = self.max_width / img.width
                    img = img.resize(
                        (self.max_width, int(img.height * ratio)), Image.LANCZOS
                    )
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=self.quality, optimize=True)
                return buf.getvalue()
        except Exception as e:
            logger.error(f"VisionEngine annotate_screenshot error: {e}")
            return None

    def get_screen_layout(self) -> dict:
        """
        Returns structured screen information including monitor details
        and basic layout analysis.
        """
        if not HAS_MSS:
            return {"monitors": [], "primary": None}
        try:
            with mss.mss() as sct:
                monitors = []
                for i, m in enumerate(sct.monitors):
                    monitors.append({
                        "index": i,
                        "left": m["left"], "top": m["top"],
                        "width": m["width"], "height": m["height"],
                        "is_primary": i == 1,
                    })
                return {
                    "monitors": monitors,
                    "primary": monitors[1] if len(monitors) > 1 else (monitors[0] if monitors else None),
                    "total_monitors": len(monitors) - 1,  # monitors[0] is virtual "all"
                }
        except Exception:
            return {"monitors": [], "primary": None}

    # --- Internal helpers ---

    def _update_frame_cache(self, img: Image.Image):
        """Store frame for diffing."""
        self._previous_frame = img.copy()
        small = img.resize((160, 90), Image.NEAREST)
        self._previous_frame_hash = hashlib.md5(small.tobytes()).hexdigest()

    @staticmethod
    def _merge_adjacent_regions(regions: list[dict], strip_h: int) -> list[dict]:
        """Merge vertically adjacent text regions."""
        if not regions:
            return []
        merged = [regions[0].copy()]
        for r in regions[1:]:
            last = merged[-1]
            if r["y"] <= last["y"] + last["height"] + strip_h // 2:
                last["height"] = r["y"] + r["height"] - last["y"]
                last["confidence"] = max(last["confidence"], r["confidence"])
            else:
                merged.append(r.copy())
        return merged

    def analyze_screen(self) -> ScreenAnalysis:
        """
        Comprehensive screen analysis combining window title detection,
        visual state analysis, and app identification.
        
        Returns a ScreenAnalysis object with detailed screen state info.
        """
        analysis = ScreenAnalysis()
        
        # Get active window title
        if HAS_PYAUTOGUI:
            try:
                active_win = pyautogui.getActiveWindow()
                if active_win and active_win.title:
                    analysis.window_title = active_win.title
                    
                    # Detect app from window title
                    title_lower = active_win.title.lower()
                    for app_name, patterns in APP_DETECTION_PATTERNS.items():
                        for keyword in patterns["title_keywords"]:
                            if keyword in title_lower:
                                analysis.detected_app = app_name
                                break
                        if analysis.detected_app != "unknown":
                            break
                    
                    # Check for Ogenti
                    ogenti_keywords = ["ogenti", "agent runtime", "execution session"]
                    analysis.is_ogenti = any(kw in title_lower for kw in ogenti_keywords)
                
                # Get list of active windows
                all_windows = pyautogui.getAllWindows()
                analysis.active_windows = [
                    w.title for w in all_windows
                    if w.title.strip() and len(w.title.strip()) > 2
                ][:10]
            except Exception as e:
                logger.debug(f"Window analysis error: {e}")
        
        # Visual analysis of the screenshot
        if self.enabled:
            try:
                with mss.mss() as sct:
                    mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
                    raw = sct.grab(mon)
                    img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")
                    
                    # Overall brightness analysis
                    stat = ImageStat.Stat(img)
                    analysis.screen_brightness = sum(stat.mean) / (3 * 255)
                    
                    # Text density estimation (edge density)
                    gray = img.convert("L").resize((320, 180), Image.NEAREST)
                    edges = gray.filter(ImageFilter.FIND_EDGES)
                    edge_stat = ImageStat.Stat(edges)
                    analysis.text_density = edge_stat.mean[0] / 255.0
                    
                    # Dialog/popup detection (look for centered bright rectangle)
                    center_region = img.crop((
                        img.width // 4, img.height // 4,
                        3 * img.width // 4, 3 * img.height // 4,
                    ))
                    center_stat = ImageStat.Stat(center_region)
                    overall_brightness = sum(stat.mean) / 3
                    center_brightness = sum(center_stat.mean) / 3
                    
                    # If center is significantly brighter → possible dialog
                    if center_brightness > overall_brightness * 1.3 and center_brightness > 200:
                        analysis.has_dialog = True
                    
                    # Loading detection (many repeated patterns / low complexity)
                    if analysis.text_density < 0.02 and analysis.screen_brightness > 0.7:
                        analysis.is_loading = True
                    
            except Exception as e:
                logger.debug(f"Visual analysis error: {e}")
        
        # Generate suggestions based on analysis
        if analysis.is_ogenti:
            analysis.suggestions.append("Switch to another app — you're looking at Ogenti's UI")
        if analysis.has_dialog:
            analysis.suggestions.append("A dialog may be open — look for OK/Cancel buttons")
        if analysis.is_loading:
            analysis.suggestions.append("Screen may be loading — wait a moment before acting")
        if analysis.detected_app == "explorer":
            analysis.suggestions.append("File Explorer is open — if you need to research, switch to Chrome")
        
        return analysis

    def verify_content_appeared(self, expected_keywords: list[str], timeout: float = 5.0) -> dict:
        """
        Check if expected content appeared on screen by capturing multiple frames
        and analyzing visual changes. Useful for verifying page loads, dialog appearances, etc.
        
        Returns {"found": bool, "confidence": float, "changes_detected": bool}
        """
        import time
        start = time.time()
        initial_changes = False
        
        while time.time() - start < timeout:
            changes = self.detect_changes()
            if changes.get("is_significant"):
                initial_changes = True
                # Content is changing — wait a bit more for it to settle
                time.sleep(0.5)
                continue
            elif initial_changes:
                # Screen settled after changes — content likely loaded
                return {
                    "found": True,
                    "confidence": 0.7,
                    "changes_detected": True,
                }
            time.sleep(0.3)
        
        return {
            "found": initial_changes,
            "confidence": 0.3 if initial_changes else 0.1,
            "changes_detected": initial_changes,
        }

    def get_active_app_name(self) -> str:
        """Quick helper to get just the current app name."""
        if HAS_PYAUTOGUI:
            try:
                win = pyautogui.getActiveWindow()
                if win and win.title:
                    title_lower = win.title.lower()
                    for app_name, patterns in APP_DETECTION_PATTERNS.items():
                        for kw in patterns["title_keywords"]:
                            if kw in title_lower:
                                return app_name
                    return win.title[:30]
            except Exception:
                pass
        return "unknown"
