"""Semantic SoM Engine — UI element detection using a vision-capable LLM.

This is a fallback layer for cases where the heuristic edge-based SoM fails,
or when semantic understanding (labels/text) is required.

It asks the configured multimodal LLM to return a JSON list of visible UI
interactive elements with bounding boxes and optional text labels.

Returned result is compatible with SoMResult/SoMElement usage in the engine.
"""

from __future__ import annotations

import json
import time
import hashlib
from dataclasses import dataclass
from typing import Optional

from loguru import logger

from core.llm_client import LLMClient
from core.som_engine import SoMElement, SoMResult


@dataclass
class SemanticSoMConfig:
    enabled: bool = False
    max_elements: int = 40
    cooldown_s: float = 2.0
    cache_ttl_s: float = 15.0


class SemanticSoMEngine:
    def __init__(self):
        self._last_call_ts: float = 0.0
        self._cache: dict[str, tuple[float, SoMResult]] = {}

    @staticmethod
    def _hash_b64(b64: str) -> str:
        return hashlib.md5((b64 or "").encode("utf-8", errors="ignore")).hexdigest()

    def _get_cached(self, key: str, ttl_s: float) -> Optional[SoMResult]:
        if not key:
            return None
        item = self._cache.get(key)
        if not item:
            return None
        ts, result = item
        if time.time() - ts > ttl_s:
            return None
        return result

    def _set_cached(self, key: str, result: SoMResult):
        if not key:
            return
        self._cache[key] = (time.time(), result)

    async def capture_semantic_som(
        self,
        llm: LLMClient,
        screenshot_b64: str,
        config: SemanticSoMConfig,
        native_width: int = 1920,
        native_height: int = 1080,
    ) -> Optional[SoMResult]:
        if not config.enabled:
            return None
        if not screenshot_b64:
            return None

        now = time.time()
        if (now - self._last_call_ts) < config.cooldown_s:
            cached = self._get_cached(self._hash_b64(screenshot_b64), config.cache_ttl_s)
            if cached:
                return cached
            return None

        key = self._hash_b64(screenshot_b64)
        cached = self._get_cached(key, config.cache_ttl_s)
        if cached:
            return cached

        self._last_call_ts = now

        system = (
            "You are a UI element detector. Look at the screenshot and output ONLY valid JSON.\n"
            "Return a JSON object with an 'elements' array.\n\n"
            "Each element must be: {\n"
            "  'x': int, 'y': int, 'w': int, 'h': int,\n"
            "  'type': 'button'|'input'|'link'|'checkbox'|'menu'|'icon'|'region',\n"
            "  'text': string (optional)\n"
            "}\n\n"
            "Rules:\n"
            "- Coordinates are in IMAGE PIXELS of the provided screenshot.\n"
            "- Include only visible interactive targets (things a user would click/type into).\n"
            "- Do not include huge background regions.\n"
            "- Limit to the most relevant items (max 40).\n"
        )

        user = (
            "Detect UI elements and return JSON. "
            "Do not add markdown. Do not add explanations."
        )

        try:
            resp = await llm.chat(
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                screenshot_b64=screenshot_b64,
            )
            raw = (resp.get("content") or "").strip()

            # Strip fenced blocks if present
            if raw.startswith("```"):
                parts = raw.split("```")
                if len(parts) >= 3:
                    raw = parts[1]
                    raw_lines = raw.split("\n")
                    if raw_lines and raw_lines[0].strip().lower() in ("json", "javascript"):
                        raw = "\n".join(raw_lines[1:])
                    raw = raw.strip()

            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start >= 0 and end > start:
                raw = raw[start:end]

            obj = json.loads(raw)
            elems = obj.get("elements") if isinstance(obj, dict) else None
            if not isinstance(elems, list):
                return None

            sx = native_width / 1920.0 if native_width != 1920 else 1.0
            sy = native_height / 1080.0 if native_height != 1080 else 1.0

            elements: list[SoMElement] = []
            raw_coords: list[tuple[int, int, int, int]] = []
            for item in elems[: max(1, int(config.max_elements))]:
                if not isinstance(item, dict):
                    continue
                try:
                    x = int(item.get("x", 0))
                    y = int(item.get("y", 0))
                    w = int(item.get("w", 0))
                    h = int(item.get("h", 0))
                except Exception:
                    continue
                if w <= 0 or h <= 0:
                    continue
                etype = str(item.get("type") or "region").strip().lower()
                if etype == "textbox":
                    etype = "input"
                if etype == "hyperlink":
                    etype = "link"
                if etype not in ("button", "input", "link", "checkbox", "menu", "icon", "region"):
                    etype = "region"

                nx = int(x * sx)
                ny = int(y * sy)
                nw = int(w * sx)
                nh = int(h * sy)
                cx = nx + nw // 2
                cy = ny + nh // 2
                raw_coords.append((x, y, w, h))
                elements.append(
                    SoMElement(
                        id=0,
                        x=nx,
                        y=ny,
                        w=nw,
                        h=nh,
                        cx=cx,
                        cy=cy,
                        type=etype if etype != "link" else "button",
                        score=0.5,
                    )
                )

            # Assign IDs top-to-bottom, left-to-right
            elements.sort(key=lambda e: (e.y, e.x))
            sort_indices = sorted(range(len(elements)), key=lambda i: (elements[i].y, elements[i].x))
            raw_coords = [raw_coords[i] for i in sort_indices] if raw_coords else []
            for i, el in enumerate(elements, start=1):
                el.id = i

            element_map = {el.id: el for el in elements}

            desc_lines = []
            for idx, el in enumerate(elements):
                label = ""
                try:
                    if idx < len(raw_coords):
                        ox, oy, ow, oh = raw_coords[idx]
                        text_val = str(next((it.get("text") for it in elems if isinstance(it, dict) and int(it.get("x", -1)) == ox and int(it.get("y", -1)) == oy and int(it.get("w", -1)) == ow and int(it.get("h", -1)) == oh), "") or "").strip()
                    else:
                        text_val = ""
                    if text_val:
                        label = f" text='{text_val[:40]}'"
                except Exception:
                    pass
                desc_lines.append(f"[{el.id}] {el.type} @({el.cx},{el.cy}){label}")
            desc = "\n".join(desc_lines)

            result = SoMResult(
                annotated_image=None,
                elements=elements,
                element_map=element_map,
                description=desc,
                raw_image=None,
            )
            self._set_cached(key, result)
            return result
        except Exception as e:
            logger.warning(f"SemanticSoM capture failed: {e}")
            return None
