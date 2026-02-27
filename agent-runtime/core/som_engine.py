"""
Set-of-Mark (SoM) Engine — UI element detection and numbered overlay system.

Core Innovation:
Instead of asking LLMs to guess raw pixel coordinates (typical error: 50-200px),
this module detects visible UI elements on screen, assigns numbers to each,
and draws labeled overlays on the screenshot. The LLM then says
"click_element 5" and we resolve element #5 to its exact center coordinates.

Detection Pipeline:
  1. Capture screenshot at full resolution
  2. Convert to grayscale → Gaussian blur → edge detection
  3. Downsample edge image to grid using PIL BOX resize (fast cell averaging)
  4. Threshold → mark cells with significant edges
  5. BFS flood-fill → cluster adjacent active cells
  6. Filter clusters by size / aspect-ratio → classify as button/input/icon/region
  7. Merge overlapping bounding boxes
  8. Sort top→bottom, left→right; cap at MAX_ELEMENTS
  9. Draw numbered badges + colored borders on screenshot
  10. Return annotated image + element map

Performance: <100ms per capture (PIL-native, no OpenCV/numpy dependency)
"""

import io
import math
from typing import Optional
from dataclasses import dataclass
from loguru import logger

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

try:
    import mss
    HAS_MSS = True
except ImportError:
    HAS_MSS = False


# ── Data Structures ──────────────────────────────────────────

@dataclass
class SoMElement:
    """A detected UI element with position, size, and classification."""
    id: int
    x: int          # bounding-box top-left x
    y: int          # bounding-box top-left y
    w: int          # width
    h: int          # height
    cx: int         # center x
    cy: int         # center y
    type: str = "region"   # button | input | icon | region
    score: float = 0.0     # detection confidence


@dataclass
class SoMResult:
    """Result from a SoM capture operation."""
    annotated_image: Optional[bytes]       # JPEG with numbered overlays
    elements: list[SoMElement]             # all detected elements
    element_map: dict[int, SoMElement]     # id → element (fast lookup)
    description: str                       # compact text listing for LLM
    raw_image: Optional[bytes] = None      # original screenshot (no overlay)


# ── Detection Constants ──────────────────────────────────────

CELL_SIZE = 14              # analysis grid cell (px); smaller = more precise, slower
EDGE_THRESHOLD = 22         # min avg edge intensity per cell to mark "active" (lower for finer grid)
MIN_CLUSTER_CELLS = 3       # min grid-cells per cluster (raised to filter noise at finer grid)
MIN_ELEMENT_W = 20          # min element width
MIN_ELEMENT_H = 16          # min element height
MAX_ELEMENT_FRAC = 0.55     # max element dimension as fraction of screen
MAX_ELEMENTS = 60           # cap on labeled elements (raised for finer detection)

# ── Subdivision Constants (split oversized elements into sub-tiles) ──
SUBDIV_MIN_W = 400          # only split elements wider than this
SUBDIV_MIN_H = 150          # only split elements taller than this
SUBDIV_TILE_W = 280         # target sub-tile width
SUBDIV_TILE_H = 110         # target sub-tile height

# ── Blue Link Detection Constants ─────────────────────────────
LINK_BLUE_EXCESS = 25       # min (B - max(R,G)) in downsampled cell
LINK_MIN_CLUSTER = 2        # min cells per link cluster
LINK_MAX_W_FRAC = 0.40      # max link width as fraction of screen

# ── Visual Overlay Constants ─────────────────────────────────

LABEL_FONT_SIZE = 14
BORDER_WIDTH = 2
COLORS = {
    "button": (52, 152, 219),     # Blue
    "input":  (46, 204, 113),     # Green
    "icon":   (231, 76, 60),      # Red
    "region": (155, 89, 182),     # Purple
    "link":   (33, 150, 243),     # Material Blue — detected hyperlinks
}


class SoMEngine:
    """
    Set-of-Mark Engine.

    Detects visible UI elements in a screenshot, numbers them,
    and draws a labeled overlay. The LLM uses element IDs to specify
    click targets instead of guessing raw pixel coordinates.
    """

    def __init__(self, quality: int = 92, max_width: int = 1920):
        self.quality = quality
        self.max_width = max_width
        self.enabled = HAS_PIL and HAS_MSS
        if not self.enabled:
            logger.warning("SoMEngine disabled: mss or PIL not available")

    # ── Public API ───────────────────────────────────────────

    def capture_som(self, monitor_index: int = 1) -> Optional[SoMResult]:
        """
        Full SoM pipeline: capture → detect → annotate → return.

        Returns SoMResult with annotated image (JPEG bytes), element list,
        element map (id → SoMElement), and text description.
        """
        if not self.enabled:
            return None
        try:
            # 1. Capture screenshot
            with mss.mss() as sct:
                mons = sct.monitors
                mon = mons[monitor_index] if monitor_index < len(mons) else mons[0]
                raw = sct.grab(mon)
                img = Image.frombytes("RGB", raw.size, raw.bgra, "raw", "BGRX")

            full_w, full_h = img.size

            # 2. Save raw (un-annotated) image
            raw_copy = img.copy()
            if raw_copy.width > self.max_width:
                r = self.max_width / raw_copy.width
                raw_copy = raw_copy.resize(
                    (self.max_width, int(raw_copy.height * r)), Image.LANCZOS
                )
            raw_buf = io.BytesIO()
            raw_copy.save(raw_buf, format="JPEG", quality=self.quality, optimize=True)

            # 3. Detect UI elements
            elements = self._detect_elements(img, full_w, full_h)

            # 4. Draw overlay on a copy
            annotated = img.copy()
            if elements:
                annotated = self._draw_overlay(annotated, elements)
            if annotated.width > self.max_width:
                r = self.max_width / annotated.width
                annotated = annotated.resize(
                    (self.max_width, int(annotated.height * r)), Image.LANCZOS
                )
            ann_buf = io.BytesIO()
            annotated.save(ann_buf, format="JPEG", quality=self.quality, optimize=True)

            # 5. Build description + element map
            element_map = {el.id: el for el in elements}
            desc = self._build_description(elements, full_w, full_h)

            return SoMResult(
                annotated_image=ann_buf.getvalue(),
                elements=elements,
                element_map=element_map,
                description=desc,
                raw_image=raw_buf.getvalue(),
            )
        except Exception as e:
            logger.error(f"SoM capture failed: {e}")
            return None

    def get_element_center(
        self, element_id: int, result: SoMResult
    ) -> Optional[tuple[int, int]]:
        """Look up an element's center coordinates by its numbered ID."""
        el = result.element_map.get(element_id)
        return (el.cx, el.cy) if el else None

    # ── Detection Pipeline ───────────────────────────────────

    def _detect_elements(
        self, img: Image.Image, full_w: int, full_h: int
    ) -> list[SoMElement]:
        """Edge-based grid clustering → bounding boxes → classified elements."""

        # --- Edge detection ---
        gray = img.convert("L")
        gray = gray.filter(ImageFilter.GaussianBlur(radius=1))
        edges = gray.filter(ImageFilter.FIND_EDGES)

        # --- Grid analysis (fast: PIL BOX resize computes cell averages) ---
        grid_cols = max(1, full_w // CELL_SIZE)
        grid_rows = max(1, full_h // CELL_SIZE)
        cell_avg = edges.resize((grid_cols, grid_rows), Image.BOX)
        cell_values = list(cell_avg.getdata())

        # Mark cells above threshold
        active = [v > EDGE_THRESHOLD for v in cell_values]

        # --- BFS flood-fill clustering ---
        visited = [False] * len(active)
        clusters: list[list[tuple[int, int]]] = []

        for idx in range(len(active)):
            if not active[idx] or visited[idx]:
                continue
            cluster: list[tuple[int, int]] = []
            queue = [idx]
            visited[idx] = True
            while queue:
                ci = queue.pop(0)
                cr = ci // grid_cols
                cc = ci % grid_cols
                cluster.append((cr, cc))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = cr + dr, cc + dc
                    ni = nr * grid_cols + nc
                    if 0 <= nr < grid_rows and 0 <= nc < grid_cols:
                        if not visited[ni] and active[ni]:
                            visited[ni] = True
                            queue.append(ni)
            if len(cluster) >= MIN_CLUSTER_CELLS:
                clusters.append(cluster)

        # --- Convert clusters to bounding boxes ---
        max_w = int(full_w * MAX_ELEMENT_FRAC)
        max_h = int(full_h * MAX_ELEMENT_FRAC)
        raw_elements: list[dict] = []

        for cells in clusters:
            min_r = min(r for r, _ in cells)
            max_r = max(r for r, _ in cells)
            min_c = min(c for _, c in cells)
            max_c = max(c for _, c in cells)

            ex = min_c * CELL_SIZE
            ey = min_r * CELL_SIZE
            ew = min((max_c - min_c + 1) * CELL_SIZE, full_w - ex)
            eh = min((max_r - min_r + 1) * CELL_SIZE, full_h - ey)

            if ew < MIN_ELEMENT_W or eh < MIN_ELEMENT_H:
                continue
            if ew > max_w or eh > max_h:
                continue

            # Compactness & intensity scoring
            n_cells = len(cells)
            bbox_cells = (max_r - min_r + 1) * (max_c - min_c + 1)
            compactness = n_cells / bbox_cells if bbox_cells else 0
            avg_edge = sum(cell_values[r * grid_cols + c] for r, c in cells) / n_cells

            # Classify by shape
            aspect = ew / eh if eh else 1.0
            el_type = "region"
            if ew < 70 and eh < 70 and 0.5 < aspect < 2.0:
                el_type = "icon"
            elif eh <= 56 and aspect >= 2.0:
                el_type = "button"
            elif eh <= 44 and aspect >= 4.0:
                el_type = "input"

            area = ew * eh
            area_score = max(0.0, 1.0 - abs(area - 5000) / 50000)
            score = compactness * 0.3 + (avg_edge / 255) * 0.4 + area_score * 0.3

            raw_elements.append({
                "x": ex, "y": ey, "w": ew, "h": eh,
                "cx": ex + ew // 2, "cy": ey + eh // 2,
                "type": el_type, "area": area, "score": score,
            })

        # --- Merge overlapping boxes ---
        merged = self._merge_overlapping(raw_elements)

        # --- Subdivide oversized elements into clickable sub-tiles ---
        merged = self._subdivide_large(merged)

        # --- Blue link detection (color-based, catches hyperlinks edge-detect misses) ---
        link_elements = self._detect_colored_links(img, full_w, full_h)
        if link_elements:
            for le in link_elements:
                # Only add if no existing small element already covers this area
                already_precise = False
                for existing in merged:
                    dx = abs(le["cx"] - existing["cx"])
                    dy = abs(le["cy"] - existing["cy"])
                    if dx < 25 and dy < 25 and existing["area"] < 15000:
                        already_precise = True
                        break
                if not already_precise:
                    merged.append(le)

        # --- Sort & cap ---
        row_bin = CELL_SIZE * 2
        merged.sort(key=lambda e: (e["y"] // row_bin, e["x"]))

        if len(merged) > MAX_ELEMENTS:
            merged.sort(key=lambda e: e["score"], reverse=True)
            merged = merged[:MAX_ELEMENTS]
            merged.sort(key=lambda e: (e["y"] // row_bin, e["x"]))

        # --- Assign IDs ---
        return [
            SoMElement(
                id=i,
                x=el["x"], y=el["y"], w=el["w"], h=el["h"],
                cx=el["cx"], cy=el["cy"],
                type=el["type"], score=el["score"],
            )
            for i, el in enumerate(merged, start=1)
        ]

    # ── Large Element Subdivision ────────────────────────────

    @staticmethod
    def _subdivide_large(elements: list[dict]) -> list[dict]:
        """Split elements exceeding size thresholds into a sub-tile grid.

        Large elements (e.g., entire text blocks on web pages) get subdivided
        so the LLM can click specific sub-regions instead of a single center
        point that may miss the intended target.
        """
        result: list[dict] = []
        for el in elements:
            need_w = el["w"] > SUBDIV_MIN_W
            need_h = el["h"] > SUBDIV_MIN_H
            if not need_w and not need_h:
                result.append(el)
                continue

            cols = max(1, math.ceil(el["w"] / SUBDIV_TILE_W)) if need_w else 1
            rows = max(1, math.ceil(el["h"] / SUBDIV_TILE_H)) if need_h else 1
            tile_w = el["w"] // cols
            tile_h = el["h"] // rows

            for r in range(rows):
                for c in range(cols):
                    tx = el["x"] + c * tile_w
                    ty = el["y"] + r * tile_h
                    tw = tile_w if c < cols - 1 else (el["w"] - c * tile_w)
                    th = tile_h if r < rows - 1 else (el["h"] - r * tile_h)
                    if tw < MIN_ELEMENT_W or th < MIN_ELEMENT_H:
                        continue
                    result.append({
                        "x": tx, "y": ty, "w": tw, "h": th,
                        "cx": tx + tw // 2, "cy": ty + th // 2,
                        "type": el["type"],
                        "area": tw * th,
                        "score": el["score"] * 0.95,
                    })
        return result

    # ── Blue / Purple Link Detection ─────────────────────────

    def _detect_colored_links(
        self, img: Image.Image, full_w: int, full_h: int
    ) -> list[dict]:
        """Detect hyperlink-coloured text regions (blue/purple) as extra elements.

        Web pages use saturated blue for unvisited links and purple for visited
        links.  Edge-based detection usually merges these into large text blobs.
        This colour pass creates small, precise elements for each link cluster
        so the LLM can ``click_element`` them directly.
        """
        grid_cols = max(1, full_w // CELL_SIZE)
        grid_rows = max(1, full_h // CELL_SIZE)
        small_rgb = img.resize((grid_cols, grid_rows), Image.BOX)
        pixels = list(small_rgb.getdata())   # [(R, G, B), ...]

        link_cells: list[tuple[int, int]] = []
        for idx, (rv, gv, bv) in enumerate(pixels):
            # Blue link: B component significantly exceeds R and G
            blue_excess = bv - max(rv, gv)
            is_blue = blue_excess > LINK_BLUE_EXCESS and bv > 130 and bv < 255

            # Purple visited link: both R and B above G, B > R
            purple_excess = min(rv, bv) - gv
            is_purple = (
                purple_excess > 20
                and bv > rv
                and bv > 120
                and rv > 50
                and gv < 180
            )

            if is_blue or is_purple:
                row = idx // grid_cols
                col = idx % grid_cols
                link_cells.append((row, col))

        if not link_cells:
            return []

        # BFS cluster adjacent link cells
        link_set = set(link_cells)
        visited: set[tuple[int, int]] = set()
        clusters: list[list[tuple[int, int]]] = []

        for cell in link_cells:
            if cell in visited:
                continue
            cluster: list[tuple[int, int]] = []
            queue = [cell]
            visited.add(cell)
            while queue:
                cr, cc = queue.pop(0)
                cluster.append((cr, cc))
                for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    nr, nc = cr + dr, cc + dc
                    nb = (nr, nc)
                    if nb in link_set and nb not in visited:
                        visited.add(nb)
                        queue.append(nb)
            if len(cluster) >= LINK_MIN_CLUSTER:
                clusters.append(cluster)

        # Convert clusters to elements
        max_link_w = int(full_w * LINK_MAX_W_FRAC)
        elements: list[dict] = []

        for cells in clusters:
            min_r = min(r for r, _ in cells)
            max_r = max(r for r, _ in cells)
            min_c = min(c for _, c in cells)
            max_c = max(c for _, c in cells)

            ex = min_c * CELL_SIZE
            ey = min_r * CELL_SIZE
            ew = min((max_c - min_c + 1) * CELL_SIZE, full_w - ex)
            eh = min((max_r - min_r + 1) * CELL_SIZE, full_h - ey)

            if ew < 15 or eh < 10:
                continue
            if ew > max_link_w:
                continue

            elements.append({
                "x": ex, "y": ey, "w": ew, "h": eh,
                "cx": ex + ew // 2, "cy": ey + eh // 2,
                "type": "link",
                "area": ew * eh,
                "score": 0.85,
            })

        return elements

    # ── Overlap Merging ──────────────────────────────────────

    def _merge_overlapping(self, elements: list[dict]) -> list[dict]:
        """Greedy merge: larger elements absorb smaller ones with >40 % overlap."""
        if len(elements) <= 1:
            return list(elements)

        elements.sort(key=lambda e: e["area"], reverse=True)
        merged: list[dict] = []
        used: set[int] = set()

        for i, a in enumerate(elements):
            if i in used:
                continue
            cur = a.copy()
            for j in range(i + 1, len(elements)):
                if j in used:
                    continue
                b = elements[j]
                if self._iou_smaller(cur, b) > 0.4:
                    # expand bounding box
                    nx = min(cur["x"], b["x"])
                    ny = min(cur["y"], b["y"])
                    nr = max(cur["x"] + cur["w"], b["x"] + b["w"])
                    nb = max(cur["y"] + cur["h"], b["y"] + b["h"])
                    cur.update(
                        x=nx, y=ny, w=nr - nx, h=nb - ny,
                        cx=nx + (nr - nx) // 2,
                        cy=ny + (nb - ny) // 2,
                        area=(nr - nx) * (nb - ny),
                        score=max(cur["score"], b["score"]),
                    )
                    used.add(j)
            merged.append(cur)
            used.add(i)
        return merged

    @staticmethod
    def _iou_smaller(a: dict, b: dict) -> float:
        """Intersection area / smaller element's area."""
        ix = max(0, min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"]))
        iy = max(0, min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"]))
        inter = ix * iy
        smaller = min(a["area"], b["area"])
        return inter / smaller if smaller > 0 else 0.0

    # ── Overlay Drawing ──────────────────────────────────────

    def _draw_overlay(
        self, img: Image.Image, elements: list[SoMElement]
    ) -> Image.Image:
        """Draw numbered badges and thin borders on each detected element.
        
        v2: Smart badge placement — badges placed OUTSIDE elements to avoid
        occlusion. For small elements (<30px), uses smaller font and thinner
        borders to minimize interference. Badges prefer top-left outside,
        falling back to other corners if space is tight.
        """
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        font_normal = self._load_font(LABEL_FONT_SIZE)
        font_small = self._load_font(max(9, LABEL_FONT_SIZE - 4))
        
        # Track badge positions to avoid overlaps
        used_badge_rects: list[tuple[int, int, int, int]] = []

        for el in elements:
            color = COLORS.get(el.type, COLORS["region"])
            is_small = el.w < 30 or el.h < 30
            
            # Adaptive border width — thinner for small elements
            border_w = 1 if is_small else BORDER_WIDTH

            # Thin coloured border
            draw.rectangle(
                [el.x, el.y, el.x + el.w, el.y + el.h],
                outline=(*color, 150 if is_small else 180),
                width=border_w,
            )

            # Number badge — smart placement to avoid occlusion
            label = str(el.id)
            font = font_small if is_small else font_normal
            tw, th = self._text_size(font, label)
            pad_x = 3 if is_small else 4
            pad_y = 1 if is_small else 2
            bw = tw + pad_x * 2
            bh = th + pad_y * 2

            # Try placement positions in order (all OUTSIDE the element):
            # 1. Top-left above, 2. Top-right above, 3. Bottom-left below,
            # 4. Top-left inside (last resort)
            candidates = [
                (el.x, el.y - bh - 1),           # above top-left
                (el.x + el.w - bw, el.y - bh - 1),  # above top-right
                (el.x, el.y + el.h + 1),          # below bottom-left
                (el.x + el.w + 1, el.y),          # right of top-right
                (el.x - bw - 1, el.y),            # left of top-left
                (el.x + 1, el.y + 1),             # inside top-left (last resort)
            ]
            
            def _overlaps_any(bx: int, by: int) -> bool:
                for ux1, uy1, ux2, uy2 in used_badge_rects:
                    if bx < ux2 and bx + bw > ux1 and by < uy2 and by + bh > uy1:
                        return True
                return False
            
            # Pick first position that's on-screen and doesn't overlap other badges
            bx, by = candidates[-1]  # default to inside
            for cx, cy in candidates:
                if cx >= 0 and cy >= 0 and cx + bw <= img.width and cy + bh <= img.height:
                    if not _overlaps_any(cx, cy):
                        bx, by = cx, cy
                        break

            used_badge_rects.append((bx, by, bx + bw, by + bh))
            
            alpha = 200 if is_small else 220
            draw.rectangle([bx, by, bx + bw, by + bh], fill=(*color, alpha))
            draw.text(
                (bx + pad_x, by + pad_y), label,
                fill=(255, 255, 255, 255), font=font,
            )

        rgba = img.convert("RGBA")
        composited = Image.alpha_composite(rgba, overlay)
        return composited.convert("RGB")

    # ── Description Builder ──────────────────────────────────

    @staticmethod
    def _build_description(
        elements: list[SoMElement], sw: int, sh: int
    ) -> str:
        """
        Rich element listing for the LLM prompt.
        
        v2: Now includes element type, size category, and position zone.
        This helps the LLM understand WHAT each element is (button, input, icon, etc.)
        and WHERE it is on screen (top-left, center, bottom-right, etc.).
        """
        if not elements:
            return "No numbered elements detected. Use raw coordinates for clicking."

        # Active window detection
        active_window_hint = ""
        try:
            import pyautogui
            win = pyautogui.getActiveWindow()
            if win and win.title:
                active_window_hint = f"Active window: {win.title}"
        except Exception:
            pass

        parts = [
            f"[SoM] {len(elements)} UI elements detected on screen (1920x{int(sh * 1920 / sw) if sw > 0 else sh}).",
            f"Use: ACTION: click_element  PARAMS: {{\"id\": N}}  to click element #N.",
        ]
        if active_window_hint:
            parts.append(active_window_hint)
        parts.append("")

        # Coordinate scale: convert native → 1920-normalized for display
        # (LLM sees a 1920px-wide screenshot, so coords in text must match)
        _desc_scale = 1920.0 / sw if sw > 0 else 1.0

        # Position zone helpers
        def get_zone(cx: int, cy: int) -> str:
            h_zone = "left" if cx < sw * 0.33 else ("right" if cx > sw * 0.67 else "center")
            v_zone = "top" if cy < sh * 0.33 else ("bottom" if cy > sh * 0.67 else "middle")
            return f"{v_zone}-{h_zone}"

        def get_size_category(w: int, h: int) -> str:
            area = w * h
            if area < 1000:
                return "tiny"
            elif area < 5000:
                return "small"
            elif area < 20000:
                return "medium"
            elif area < 80000:
                return "large"
            return "very-large"

        # Type emoji mapping
        TYPE_EMOJI = {
            "button": "🔘",
            "input": "📝",
            "icon": "🔷",
            "region": "📦",
            "link": "🔗",
        }

        for el in elements:
            zone = get_zone(el.cx, el.cy)
            size_cat = get_size_category(el.w, el.h)
            emoji = TYPE_EMOJI.get(el.type, "📦")
            # Display coordinates in 1920-normalized space (matching screenshot)
            dcx = int(el.cx * _desc_scale)
            dcy = int(el.cy * _desc_scale)
            parts.append(
                f"  [{el.id}] {emoji} {el.type:7s} at ({dcx:4d},{dcy:4d})  "
                f"{el.w}x{el.h} {size_cat:10s} zone={zone}"
            )

        parts.append("")
        parts.append("TIP: Buttons and links (🔗) are clickable. Inputs can be typed into after clicking.")
        parts.append("TIP: ALWAYS use click_element with element [ID]. Raw coordinates WILL miss small targets like links.")
        parts.append("TIP: 🔗 link elements are detected from hyperlink colours — high-priority click targets.")

        return "\n".join(parts)

    # ── Helpers ──────────────────────────────────────────────

    @staticmethod
    def _load_font(size: int):
        """Try loading a TTF font; fall back to Pillow default."""
        for path in ("arial.ttf", "C:/Windows/Fonts/arial.ttf",
                      "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(path, size)
            except (IOError, OSError):
                continue
        return ImageFont.load_default()

    @staticmethod
    def _text_size(font, text: str) -> tuple[int, int]:
        try:
            bbox = font.getbbox(text)
            return bbox[2] - bbox[0], bbox[3] - bbox[1]
        except AttributeError:
            return len(text) * 8, 14
