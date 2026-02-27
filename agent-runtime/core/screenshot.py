"""
Screenshot Capture - High-performance screen capture using mss.

v2 — Multi-environment support:
- Auto-detects current screen resolution dynamically
- Scales output to consistent size for LLM regardless of native resolution
- Works across Windows, macOS, Linux
- Thread-safe for concurrent sessions
"""

import io
import threading
from typing import Optional
from loguru import logger

try:
    import mss
    import mss.tools
    HAS_MSS = True
except ImportError:
    HAS_MSS = False

try:
    from PIL import Image
    HAS_PIL = True
except ImportError:
    HAS_PIL = False


class ScreenshotCapture:
    """Captures screenshots with consistent output regardless of native resolution."""

    def __init__(self, quality: int = 92, max_width: int = 1920):
        self.quality = quality
        self.max_width = max_width
        self.enabled = HAS_MSS and HAS_PIL
        self._lock = threading.Lock()  # Thread-safe for concurrent sessions
        
        if not self.enabled:
            logger.warning("Screenshot capture disabled (mss or PIL not available)")

    def capture(self, region: Optional[dict] = None) -> Optional[bytes]:
        """
        Capture screenshot and return as JPEG bytes.
        Always scales to max_width for consistent LLM input
        regardless of the host machine's native resolution.
        
        Args:
            region: Optional dict with top, left, width, height
            
        Returns:
            JPEG image bytes or None if capture fails
        """
        if not self.enabled:
            return None

        try:
            with self._lock:  # Thread-safe capture
                with mss.mss() as sct:
                    if region:
                        monitor = {
                            "top": region.get("top", 0),
                            "left": region.get("left", 0),
                            "width": region.get("width", 800),
                            "height": region.get("height", 600),
                        }
                    else:
                        # Capture primary monitor (works on any resolution)
                        monitor = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]

                    sct_img = sct.grab(monitor)
                    img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                    # Always normalize to max_width for consistent LLM interpretation
                    # This ensures coordinates are valid regardless of host resolution
                    if img.width != self.max_width:
                        ratio = self.max_width / img.width
                        new_height = int(img.height * ratio)
                        img = img.resize((self.max_width, new_height), Image.LANCZOS)

                    buffer = io.BytesIO()
                    img.save(buffer, format="JPEG", quality=self.quality, optimize=True)
                    return buffer.getvalue()

        except Exception as e:
            logger.error(f"Screenshot capture failed: {e}")
            return None

    def capture_region(self, x: int, y: int, width: int, height: int) -> Optional[bytes]:
        """Capture a specific screen region."""
        return self.capture({"left": x, "top": y, "width": width, "height": height})

    def get_screen_info(self) -> dict:
        """Get information about available monitors."""
        if not HAS_MSS:
            return {"monitors": [], "primary": None}

        try:
            with mss.mss() as sct:
                monitors = []
                for i, m in enumerate(sct.monitors):
                    monitors.append({
                        "index": i,
                        "left": m["left"],
                        "top": m["top"],
                        "width": m["width"],
                        "height": m["height"],
                    })
                return {
                    "monitors": monitors,
                    "primary": monitors[1] if len(monitors) > 1 else monitors[0] if monitors else None,
                }
        except Exception as e:
            return {"monitors": [], "error": str(e)}
