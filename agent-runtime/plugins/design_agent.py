"""
Design Agent v2 — Tier B (Mid-range, $17.99)
Slug: design_studio

Domain: design
Engines: Vision + SoM (NO planner, NO memory)
Tools: color_pick, measure_spacing, generate_palette, snap_to_grid, export_asset, font_suggest (6 tools)
Actions: Design domain (includes drag, NO run_command)

v2 — DESIGN WORKFLOW INTELLIGENCE:
- Knows how to use common Windows design tools (Paint, Paint 3D, PowerPoint)
- Understands design workflow: create canvas → add elements → style → align → export
- SoM-aware element precision targeting
- Completion verification: must have actually created/modified design
- Design concept guidance (typography, color theory, layout)
"""

import asyncio
import json
from plugins.base_plugin import BasePlugin

try:
    from core.engine import AgentContext
except ImportError:
    AgentContext = None


# ── WINDOWS DESIGN APP KNOWLEDGE ──

DESIGN_APP_GUIDE = """
WINDOWS DESIGN APP GUIDE — How to actually design on Windows:

PAINT (mspaint):
  Open: ACTION open_app {"name": "mspaint"}
  Draw rectangle: Click 'Shapes' in toolbar → select Rectangle → drag on canvas
  Draw line: Click 'Shapes' → select Line → drag
  Add text: Click 'A' (text tool) → click on canvas → type text
  Fill color: Click paint bucket → click area to fill
  Pick color: Click eyedropper → click on canvas
  Change color: Click color swatches in toolbar, or click 'Edit Colors'
  Select area: Click 'Select' → drag rectangle → can move, copy, delete
  Resize canvas: Drag the small squares at canvas edge
  Save: Ctrl+S → choose format (PNG recommended)
  Undo: Ctrl+Z
  
PAINT 3D (new Windows):
  Open: ACTION open_app {"name": "ms-paint:"}  (or search for Paint 3D)
  2D shapes: Click '2D Shapes' tab → pick shape → drag on canvas
  3D objects: Click '3D Objects' → pick → drag on canvas
  Text: Click 'Text' → click canvas → type
  Stickers: Click 'Stickers' → pick stickers, emojis, textures
  Canvas: Click 'Canvas' tab → set size, toggle transparent background
  Effects: Click 'Effects' tab → apply color/light filters
  
POWERPOINT (pptx design):
  Open: ACTION open_app {"name": "powerpnt"}
  New slide: Right-click left panel → New Slide
  Add shape: Insert tab → Shapes → click desired shape → drag on slide
  Add text box: Insert → Text Box → drag → type text
  Change colors: Select shape → Format tab → Shape Fill / Shape Outline
  Add image: Insert → Pictures → select file
  Align: Select multiple → Format → Align → Align Center/Left/Right
  Group: Select multiple → right-click → Group
  
SNIPPING TOOL (screenshots for reference):
  Open: ACTION open_app {"name": "snippingtool"}
  or: ACTION hotkey {"keys": ["win", "shift", "s"]}
  
GENERAL DESIGN TOOLBAR NAVIGATION:
  - Most design apps have toolbars at the TOP or LEFT
  - Tools are usually: Select, Draw, Text, Shape, Fill, Eraser
  - Color picker is usually at bottom or right
  - Layer panel (if exists) is usually on the right
  - File menu → Save/Export is the standard save method
"""

DESIGN_PRINCIPLES = """
DESIGN PRINCIPLES TO FOLLOW:
1. COLOR: Use max 3-4 colors. Ensure sufficient contrast (dark text on light bg or vice versa).
2. TYPOGRAPHY: Use max 2 fonts. Headers bigger than body text. Minimum 12pt for readability.
3. ALIGNMENT: Align elements to a grid. Use consistent spacing between elements.
4. HIERARCHY: Most important element = largest/boldest. Guide the eye with size.
5. WHITESPACE: Don't crowd elements. Leave breathing room between sections.
6. CONSISTENCY: Same style for similar elements. Same button shapes, same icon style.

COMMON MISTAKES TO AVOID:
- Using too many colors (keep it simple)
- Tiny text that's hard to read  
- Elements randomly scattered (use alignment)
- No visual hierarchy (everything same size)
- Clashing colors (use complementary/analogous schemes)
"""

DESIGN_COMPLETION_RULES = """
DESIGN TASK COMPLETION RULES:
1. You MUST have actually created visual content (not just opened an app)
2. You MUST have used at least one shape, text, or drawing tool
3. You MUST have saved your work (Ctrl+S or File → Save)
4. Do NOT say TASK_COMPLETE if:
   - You only opened paint/powerpoint without drawing anything
   - The canvas is still blank/default
   - You haven't saved the file
   - You were asked for specific elements that aren't placed yet
"""


class DesignAgent(BasePlugin):
    name = "Design Studio"
    description = "Mid-tier design agent with visual tools, design workflow intelligence, and SoM precision."
    version = "4.2.0"
    slug = "design_studio"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        # Reset tracking
        self.reset_tracking()
        
        # Detect task type
        task_type = self._detect_task_type(prompt)
        
        # Detect specific design sub-task
        design_sub = self._detect_design_subtask(prompt)

        await ctx.log(f"◇ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Task type: {task_type} | Design sub: {design_sub} | Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
DESIGN STUDIO — TIER B DESIGN AGENT 🎨
You are a design specialist working on a Windows computer.
You use design applications (Paint, PowerPoint, etc.) to create visual content.

DETECTED DESIGN TASK: {design_sub}

{DESIGN_APP_GUIDE}

{DESIGN_PRINCIPLES}

{self._get_design_strategy(design_sub, prompt)}

{DESIGN_COMPLETION_RULES}

DESIGN-SPECIFIC TOOLS:
- color_pick: Sample exact colors from the canvas
- measure_spacing: Verify alignment/spacing between elements  
- generate_palette: Create harmonious color schemes
- snap_to_grid: Align elements to pixel grid
- export_asset: Export design elements
- font_suggest: Get typography recommendations

PRECISION TARGETING:
- Look for SoM element IDs (numbered labels on UI elements)
- Use element IDs for precise clicks: ACTION click {{"element_id": 5}}
- This is better than guessing coordinates in complex toolbars

ANTI-FAILURE:
- NEVER leave canvas blank. Draw/type SOMETHING.
- NEVER say TASK_COMPLETE without having created visual content.
- If a tool/button doesn't work, try right-clicking for context menu.
- If you can't find a feature, look in menu bar (File, Edit, View, Insert, Format).
- Use SoM element IDs for toolbar buttons — they're more reliable than coordinates.
""")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_design_initial_message(prompt, design_sub)},
        ]

        # ═══ Minimize Ogenti so LLM sees the desktop ═══
        await self._minimize_ogenti_window(ctx)

        # Tracking state
        action_failure_streak = 0
        consecutive_empty = 0
        has_drawn = False
        has_typed_text = False
        has_saved = False
        app_opened = False
        tools_used_design = set()

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            if step == 0:
                await ctx.log(f"  Analyzing screen & calling LLM (step {step+1}/{max_steps})...")
            elif step % 5 == 0:
                await ctx.log(f"  Step {step+1}/{max_steps} — drawn: {has_drawn}, saved: {has_saved}")

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                messages = [messages[0]] + messages[-(self._tier_config.max_message_history - 1):]

            # Completion verification
            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_design_completion(has_drawn, has_typed_text, has_saved, app_opened)
                if allowed:
                    await ctx.log(f"✓ Design completed. Tools: {tools_used_design}")
                    break
                else:
                    messages.append({"role": "user", "content": f"❌ Cannot complete: {reason}\nYou have {max_steps - step - 1} steps left."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    msg = self._get_design_unstuck(app_opened, has_drawn, design_sub)
                    messages.append({"role": "user", "content": msg})
                    consecutive_empty = 0
                else:
                    messages.append({"role": "user", "content": "Look at the canvas/screen. Describe what you see, then provide your next ACTION or TOOL."})
                continue
            consecutive_empty = 0

            for action in actions:
                # Specialized design tool
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    tools_used_design.add(tool_name)
                    await ctx.log(f"  🎨 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    
                    # Format tool result for design context
                    msg = self._format_design_tool_result(tool_name, result)
                    messages.append({"role": "user", "content": msg + "\nApply this to your design..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                await ctx.log(f"  Step {step+1}: {atype}", "INFO")
                self._track_action(atype, params)

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ {result['error']}\nYou are a DESIGNER. Only use design actions (no run_command)."})
                        break
                    if result.get("success", True):
                        success = True
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(1)

                await ctx.send_screenshot()
                if success:
                    action_failure_streak = 0
                    
                    # Track design progress
                    if atype == "open_app":
                        app_opened = True
                        app_name = params.get("name", "")
                        feedback = self._get_design_app_opened_feedback(app_name, design_sub)
                    elif atype == "drag":
                        has_drawn = True
                        feedback = "Shape/element drawn. Check size and position. Use color tools if needed."
                    elif atype == "type_text":
                        has_typed_text = True
                        text = params.get("text", "")
                        feedback = (
                            f"\u26a0 VERIFY: Look at the screenshot. Is the text '{text[:30]}' visible on the canvas?\n"
                            "\u2022 If YES \u2192 adjust font/color as needed.\n"
                            "\u2022 If NO \u2192 click the text area first, then retry type_text."
                        )
                    elif atype == "click":
                        feedback = self._get_design_click_feedback(params)
                    elif atype == "hotkey":
                        keys = params.get("keys", [])
                        if keys == ["ctrl", "s"]:
                            has_saved = True
                            feedback = "File saved! Verify the design meets requirements."
                        elif keys == ["ctrl", "z"]:
                            feedback = "Undone. Try a different approach."
                        elif keys == ["ctrl", "a"]:
                            feedback = "All selected. You can now move, resize, or modify."
                        else:
                            feedback = f"Shortcut {'+'.join(keys)} applied. Check result."
                    else:
                        feedback = f"'{atype}' done. Check canvas — what changed?"
                    
                    messages.append({"role": "user", "content": feedback})
                else:
                    action_failure_streak += 1
                    if action_failure_streak >= 3:
                        msg = self._get_design_unstuck(app_opened, has_drawn, design_sub)
                        action_failure_streak = 0
                    else:
                        msg = f"FAILED (streak: {action_failure_streak}). Try a different tool or click target."
                    messages.append({"role": "user", "content": msg})

        await ctx.send_screenshot()
        await ctx.log(f"◇ {self.name} finished — Drawn:{has_drawn} Typed:{has_typed_text} Saved:{has_saved}")

    def _detect_design_subtask(self, prompt: str) -> str:
        """Detect specific type of design task."""
        p = prompt.lower()
        
        patterns = {
            "logo": ["logo", "로고", "brand", "브랜드", "icon", "아이콘", "emblem"],
            "poster": ["poster", "포스터", "flyer", "전단지", "banner", "배너", "advertisement", "광고"],
            "ui_mockup": ["ui", "ux", "mockup", "wireframe", "prototype", "프로토타입", "layout", "interface", "인터페이스"],
            "illustration": ["draw", "그림", "그리", "illustration", "일러스트", "picture", "painting", "색칠"],
            "infographic": ["infographic", "인포그래픽", "chart", "차트", "diagram", "다이어그램", "graph", "그래프"],
            "presentation": ["presentation", "발표", "slide", "슬라이드", "ppt", "powerpoint", "프레젠테이션"],
            "social_media": ["social", "소셜", "instagram", "인스타", "thumbnail", "썸네일", "cover", "커버"],
            "document_design": ["card", "명함", "certificate", "인증서", "letter", "letterhead", "envelope"],
            "photo_edit": ["photo", "사진", "edit", "편집", "crop", "resize", "filter", "필터", "retouch"],
            "color_scheme": ["color", "색상", "palette", "팔레트", "theme", "테마", "scheme", "배색"],
        }
        
        for subtype, keywords in patterns.items():
            if any(kw in p for kw in keywords):
                return subtype
        return "general_design"

    def _get_design_strategy(self, subtask: str, prompt: str) -> str:
        """Get concrete step-by-step design strategy."""
        strategies = {
            "logo": """
LOGO DESIGN STRATEGY:
1. Open Paint: ACTION open_app {"name": "mspaint"}
2. Set canvas size (small, e.g. 500x500): Image → Attributes or drag canvas edge
3. Choose 2-3 brand colors using the color palette
4. Draw the main shape/icon:
   - Click 'Shapes' in toolbar → select basic shape (circle, rectangle, etc.)
   - Drag to create the shape on canvas
5. Add company/brand text:
   - Click 'A' (text tool) → click where text should go → type text
   - Choose a clean, readable font
6. Adjust spacing and alignment
7. Save as PNG: Ctrl+S → set filename → Save as type: PNG
""",
            "poster": """
POSTER DESIGN STRATEGY:
1. Open Paint or PowerPoint
2. For Paint: Set large canvas (e.g., 1920x1080 or A4 size)
   For PowerPoint: Use landscape slide
3. Start with background color: Select fill tool → pick color → fill canvas
4. Add main title text (large, bold) at the top
5. Add subtitle and body text below
6. Add shapes/lines to create visual structure
7. Use max 3 colors throughout
8. Save the file
""",
            "illustration": """
ILLUSTRATION STRATEGY:
1. Open Paint: ACTION open_app {"name": "mspaint"}
2. Select drawing tool (pencil, brush)
3. Pick your first color
4. Start drawing the main subject (outline first)
5. Fill in colors using paint bucket or brush
6. Add details and shading
7. Add background elements
8. Save as PNG
""",
            "presentation": """
PRESENTATION STRATEGY:
1. Open PowerPoint: ACTION open_app {"name": "powerpnt"}
2. Create title slide:
   - Click title placeholder → type title
   - Click subtitle → type subtitle
3. Add content slides:
   - Right-click slide panel → New Slide
   - Choose appropriate layout
4. For each slide:
   - Add title, bullet points, or images
   - Keep text concise (6-8 words per bullet)
5. Apply consistent colors/fonts throughout
6. Save: Ctrl+S
""",
            "photo_edit": """
PHOTO EDITING STRATEGY:
1. Open Paint: ACTION open_app {"name": "mspaint"}
2. Open the photo: File → Open → navigate to image
3. Edit:
   - Crop: Select tool → drag to select area → Crop
   - Resize: Resize button → set dimensions
   - Add text overlay: Text tool → click → type
4. Save (Ctrl+S) or Save As for different format
""",
            "color_scheme": """
COLOR SCHEME STRATEGY:
1. Use the generate_palette TOOL to create harmonious colors
   TOOL generate_palette {"base_color": "#3498db", "scheme": "complementary"}
2. Open Paint to visualize:
   - Draw color swatches (rectangles) with each color
   - Label each color with its hex code
3. Test contrast between colors using contrast_check TOOL
4. Save the palette reference image
""",
        }
        
        return strategies.get(subtask, """
GENERAL DESIGN STRATEGY:
1. Open Paint: ACTION open_app {"name": "mspaint"}
2. Plan your layout mentally (what goes where)
3. Start with the background/canvas setup
4. Add the main element first (biggest/most important)
5. Add secondary elements around it
6. Add text labels if needed
7. Check alignment and spacing
8. Save your work: Ctrl+S
""")

    def _build_design_initial_message(self, prompt: str, subtask: str) -> str:
        """Build smart initial message for design task."""
        app_hint = {
            "presentation": "powerpnt",
            "logo": "mspaint",
            "poster": "mspaint",
            "illustration": "mspaint",
            "ui_mockup": "mspaint",
            "infographic": "mspaint",
            "social_media": "mspaint",
            "photo_edit": "mspaint",
            "color_scheme": "mspaint",
        }
        
        app = app_hint.get(subtask, "mspaint")
        
        return f"""Design task: {prompt}

This is a {subtask.replace('_', ' ')} task.

YOUR FIRST ACTION should be to open the design app:
ACTION open_app {{"name": "{app}"}}

Then start creating the design step by step. Do NOT create empty/blank files.
Actually draw, type, and design something visually meaningful."""

    def _format_design_tool_result(self, tool_name: str, result: dict) -> str:
        """Format tool result with design context."""
        if tool_name == "color_pick" and result.get("success"):
            return f"🎨 Color sampled: {result.get('hex', '?')} (RGB: {result.get('rgb', '?')}). Use this color in your design."
        elif tool_name == "measure_spacing" and result.get("success"):
            h = result.get('horizontal_px', '?')
            v = result.get('vertical_px', '?')
            return f"📏 Spacing: {h}px horizontal, {v}px vertical. {'Good spacing!' if 8 <= (h if isinstance(h, int) else 0) <= 32 else 'Consider adjusting for better balance.'}"
        elif tool_name == "generate_palette" and result.get("success"):
            colors = result.get('palette', [])
            return f"🎨 Palette ({result.get('scheme', '?')}): {', '.join(colors)}. Apply these colors to your design elements."
        elif tool_name == "font_suggest" and result.get("success"):
            fonts = result.get('fonts', [])
            return f"🔤 Recommended fonts: {', '.join(fonts[:3])}. Use the first for headings, second for body text."
        elif tool_name == "contrast_check" and result.get("success"):
            ratio = result.get('ratio', '?')
            aa = result.get('AA_normal', False)
            return f"{'✅' if aa else '❌'} Contrast ratio: {ratio}:1 — {'Passes' if aa else 'FAILS'} WCAG AA. {'Good for readability!' if aa else 'Choose more contrasting colors.'}"
        elif tool_name == "snap_to_grid" and result.get("success"):
            return f"📐 Element snapped to grid. Alignment improved."
        elif tool_name == "export_asset" and result.get("success"):
            return f"📁 Asset exported: {result.get('path', 'saved')}."
        else:
            return f"Tool [{tool_name}]: {json.dumps(result)[:300]}"

    def _get_design_app_opened_feedback(self, app_name: str, subtask: str) -> str:
        """Feedback after opening a design app."""
        if app_name in ("mspaint", "paint"):
            return """Paint opened! You should see a white canvas with toolbar at top.
TOOLBAR (top): Home tab has tools: Select, Crop, Resize, Shapes, Text(A), Brushes, Colors
Now start creating your design:
- For shapes: Click 'Shapes' dropdown → pick shape → drag on canvas
- For text: Click 'A' → click on canvas → start typing
- For drawing: Click a brush → pick color → draw on canvas"""
        elif app_name in ("powerpnt", "powerpoint"):
            return """PowerPoint opened! You should see a blank slide.
Click on 'Click to add title' placeholder → type your title
Or: Insert tab → Shapes/Text Box/Pictures to add elements
Use Design tab to change slide theme/colors."""
        else:
            return f"'{app_name}' opened. Look at the toolbar and canvas. Start designing."

    def _get_design_click_feedback(self, params: dict) -> str:
        """Smart feedback after a click in design context."""
        x, y = params.get("x", 0), params.get("y", 0)
        # Top area (likely toolbar)
        if y < 120:
            return "Clicked toolbar area. A tool or option may be selected. Check if the cursor/mode changed."
        # Very top (likely menu)
        if y < 50:
            return "Clicked menu area. Check if a dropdown opened."
        # Main canvas area
        return "Clicked on canvas. If drawing, a mark should appear. If selecting, an element may be highlighted."

    def _verify_design_completion(self, has_drawn: bool, has_typed: bool, 
                                   has_saved: bool, app_opened: bool) -> tuple:
        """Verify design task completion."""
        if not app_opened:
            return False, "You haven't even opened a design app yet. Open Paint or PowerPoint first."
        if not has_drawn and not has_typed:
            return False, "You haven't created any visual content yet. Draw shapes or type text."
        if not has_saved:
            return False, "You haven't saved your design. Press Ctrl+S to save."
        return True, "OK"

    def _get_design_unstuck(self, app_opened: bool, has_drawn: bool, subtask: str) -> str:
        """Help agent get unstuck in design workflow."""
        if not app_opened:
            return """You're stuck. Do this NOW:
ACTION open_app {"name": "mspaint"}
This opens Paint. Then you can draw, add shapes, and add text."""
        
        if not has_drawn:
            return """Paint is open but you haven't drawn anything yet. Start NOW:
1. Click on 'Shapes' in the toolbar (top of screen)
2. Select Rectangle or Oval
3. Drag on the white canvas to create a shape
OR click 'A' (text tool) → click canvas → type text."""
        
        return f"""Design seems stuck. Try:
1. Click on a different tool in the toolbar
2. Try using a SoM element ID for precise clicking
3. If canvas looks cluttered, Ctrl+Z to undo last actions
4. For {subtask}: Make sure you've addressed the user's specific design request."""
