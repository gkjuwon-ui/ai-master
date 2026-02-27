"""
Writing Agent — Domain: writing
Slug: writing_agent

Specialized plugin for all writing-domain agents (Scribe, DocuMaster, CopyAce, TransLingo, GrammarFix).
Provides real content creation workflows: outlining, drafting, SEO, tone control,
grammar checking, and structured document output.

Engines: Tier-dependent (F=none, B-=keyboard, C=vision, B=+SoM, A=+planner, S+=all)
Tools: writing-domain specialized tools (outline_generator, seo_optimizer, tone_analyzer,
       grammar_check, readability_score, word_count, content_structure, keyword_density)
"""

import asyncio
import json
import re
from plugins.base_plugin import BasePlugin

try:
    from core.engine import AgentContext
    from core.planner_engine import PlannerEngine
except ImportError:
    AgentContext = None
    PlannerEngine = None

try:
    from core.learning_engine import LearningEngine
    HAS_LEARNING = True
except ImportError:
    HAS_LEARNING = False


# ── WRITING WORKFLOW INTELLIGENCE ──

WRITING_WORKFLOW_GUIDE = """
╔══════════════════════════════════════════════════════════════════════╗
║              WRITING AGENT — WORKFLOW GUIDE                         ║
╚══════════════════════════════════════════════════════════════════════╝

═══ CONTENT CREATION WORKFLOW ═══

PHASE 1 — OPEN TEXT EDITOR:
  ACTION: open_app  PARAMS: {"name": "notepad"}
  ACTION: wait      PARAMS: {"seconds": 2}
  ACTION: click     PARAMS: {"x": 400, "y": 400}   ← click text area

PHASE 2 — PLAN CONTENT STRUCTURE:
  Before typing, determine:
  • Content type: blog post, documentation, email, marketing copy, report
  • Target audience: technical, general, executive, academic
  • Tone: professional, casual, persuasive, informative
  • Required sections: title, introduction, body, conclusion
  • SEO keywords (if applicable)

PHASE 3 — WRITE CONTENT:
  ACTION: type_text  PARAMS: {"text": "<your full content>"}
  
  ★★★ Content MUST include:
  • A clear title/heading
  • Structured sections (use # for headings)
  • At least 500 characters of substantive content
  • Proper grammar and formatting
  • Bullet points/lists where appropriate
  
PHASE 4 — SAVE:
  ACTION: hotkey     PARAMS: {"keys": ["ctrl", "s"]}
  (Save As dialog → click filename input → hotkey end → hotkey shift+home → type filename → Enter)
  ⚠ In Save As: NEVER ctrl+a — it selects file list, not filename text.

═══ CONTENT TYPES & STRATEGIES ═══

BLOG POST:
  Title → Hook intro (1 paragraph) → 3-5 sections with H2 headings → 
  Bullet points for key takeaways → Conclusion → CTA

TECHNICAL DOCUMENTATION:
  Title → Overview → Prerequisites → Step-by-step instructions →
  Code examples → Troubleshooting → FAQ → References

MARKETING COPY:
  Headline → Pain point → Solution → Features/Benefits →
  Social proof → CTA → Urgency element

EMAIL:
  Subject line → Greeting → Purpose (first sentence) →
  Details → Action items → Sign-off

REPORT:
  Title → Executive Summary → Methodology → Findings →
  Analysis → Recommendations → Appendix

═══ SEO OPTIMIZATION ═══
  • Place primary keyword in title and first paragraph
  • Use H2/H3 subheadings with keywords
  • Aim for 1-2% keyword density
  • Include meta description (150-160 chars)
  • Use internal/external link placeholders
  • Optimize readability: short paragraphs, bullet points
"""

WRITING_COMPLETION_RULES = """
WRITING TASK COMPLETION RULES:
1. You MUST have actually typed substantial content (500+ characters minimum)
2. Content must have proper structure (title, sections, conclusion)
3. You MUST have saved the file
4. Grammar and spelling should be reasonable
5. Do NOT say TASK_COMPLETE if:
   - You only opened Notepad
   - Content is placeholder text ("Lorem ipsum" etc.)
   - File was not saved
   - Content is shorter than 2 paragraphs
"""


class WritingAgent(BasePlugin):
    name = "Writing Agent"
    description = "Professional writing agent with content planning, SEO optimization, tone control, and structured document creation."
    version = "4.2.0"
    slug = "writing_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        # Detect writing sub-task
        writing_sub = self._detect_writing_subtask(prompt)
        task_type = self._detect_task_type(prompt)
        if task_type not in ("writing", "research"):
            task_type = "writing"

        await ctx.log(f"  Writing sub-task: {writing_sub}")

        # ── PLANNER (Tier A+) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Writing task ({writing_sub}). Plan outline, draft sections, review, finalize."
            )
            plan_text = "\n\nWriting Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status == 'completed' else '→' if s.status == 'running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        strategy = self._get_writing_strategy(writing_sub, prompt)

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║         WRITING AGENT — SPECIALIZED INSTRUCTIONS                    ║
╚══════════════════════════════════════════════════════════════════════╝

You are a WRITING SPECIALIST. Your job is to create high-quality written content.

DETECTED WRITING TASK: {writing_sub}

{strategy}

{WRITING_WORKFLOW_GUIDE}

{WRITING_COMPLETION_RULES}

═══ WRITING TOOL USAGE ═══
  • outline_generator   — Creates structured outline from topic
  • seo_optimizer       — Suggests SEO improvements for content
  • tone_analyzer       — Analyzes and adjusts writing tone
  • grammar_check       — Checks grammar and suggests corrections
  • readability_score   — Calculates readability metrics (Flesch-Kincaid)
  • word_count          — Counts words, sentences, paragraphs
  • content_structure   — Analyzes document structure quality
  • keyword_density     — Checks keyword frequency and distribution

Usage:
  TOOL: outline_generator
  TOOL_PARAMS: {{"topic": "your topic", "type": "{writing_sub}"}}

═══ QUALITY STANDARDS ═══
  ✓ Content must be original and substantive
  ✓ Proper heading hierarchy (H1 → H2 → H3)
  ✓ Short paragraphs (3-5 sentences max)
  ✓ Active voice preferred over passive
  ✓ Include concrete examples where applicable
  ✓ End with clear conclusion or call-to-action

  ✗ NEVER produce placeholder/lorem ipsum text
  ✗ NEVER say TASK_COMPLETE without saving the file
  ✗ NEVER create content shorter than 300 words
{plan_text}""")

        # Track writing metrics
        word_count = 0
        has_saved = False
        editor_opened = False
        content_typed = False

        learning_engine = None
        if HAS_LEARNING:
            learning_engine = LearningEngine()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_initial_user_message(prompt, task_type)},
        ]

        action_failure_streak = 0
        consecutive_empty = 0

        await self._minimize_ogenti_window(ctx)

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            if step % 5 == 0:
                await ctx.log(f"  Step {step + 1}/{max_steps} — words: ~{word_count}, saved: {has_saved}")

            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan: {ready[0].description}]"

            if HAS_LEARNING and learning_engine:
                try:
                    adaptations = learning_engine.get_adaptations(task_type, {})
                    if adaptations:
                        adaptation_msg = "🧠 LEARNING:\n" + "\n".join(
                            [f"• {a['recommendation']}" for a in adaptations[:3]])
                        messages.append({"role": "user", "content": adaptation_msg})
                except Exception:
                    pass

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                max_h = self._tier_config.max_message_history
                messages = [messages[0]] + messages[-(max_h - 1):]

            # Check completion
            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and self._has_typed_content and has_saved:
                    await ctx.log(f"✓ Writing complete — ~{word_count} words")
                    break
                elif not self._has_typed_content:
                    messages.append({"role": "user",
                                     "content": "❌ You haven't typed any content yet. Open Notepad and write the content."})
                    continue
                elif not has_saved:
                    messages.append({"role": "user",
                                     "content": "❌ File not saved. Press Ctrl+S to save your work."})
                    continue
                else:
                    messages.append({"role": "user", "content": f"❌ Cannot complete: {reason}"})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    if not editor_opened:
                        messages.append({"role": "user",
                                         "content": "Open Notepad NOW:\nACTION: open_app\nPARAMS: {\"name\": \"notepad\"}"})
                    elif not content_typed:
                        messages.append({"role": "user",
                                         "content": "Start writing! Click in Notepad and type your content."})
                    else:
                        messages.append({"role": "user",
                                         "content": "Save your work with Ctrl+S, then say TASK_COMPLETE."})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  📝 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    messages.append({"role": "user",
                                     "content": f"Tool '{tool_name}' result: {json.dumps(result)[:500]}\nContinue writing..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                # Track writing-specific actions
                if atype == "open_app":
                    app = params.get("name", "").lower()
                    if app in ("notepad", "code", "notepad++", "wordpad"):
                        editor_opened = True

                if atype in ("type_text", "type_text_fast"):
                    text = params.get("text", "")
                    word_count += len(text.split())
                    if len(text) > 50:
                        content_typed = True

                if atype == "hotkey":
                    keys = params.get("keys", [])
                    if "ctrl" in keys and "s" in keys:
                        has_saved = True

                await ctx.log(f"  Step {step + 1}: {atype}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user",
                                         "content": f"⚠ {result['error']}\nYou are a WRITER. Type content only."})
                        break
                    if result.get("success", True):
                        success = True
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(1)

                await asyncio.sleep(0.5)
                await ctx.send_screenshot()

                if success:
                    action_failure_streak = 0
                    if HAS_LEARNING and learning_engine:
                        learning_engine.add_experience(
                            task_type=task_type, command=prompt, context={},
                            action=f"{atype}", result={"success": True}, confidence=0.7)

                    if atype == "open_app":
                        messages.append({"role": "user",
                                         "content": f"⚠ VERIFY: Did the editor open? If yes, click inside and start typing.{step_context}"})
                    elif atype in ("type_text", "type_text_fast"):
                        messages.append({"role": "user",
                                         "content": f"⚠ VERIFY: Can you see the typed text? Continue writing or save if done.{step_context}"})
                    elif atype == "hotkey" and has_saved:
                        messages.append({"role": "user",
                                         "content": f"⚠ VERIFY: File saved? If Save As dialog appeared: (1) click the filename input field at the bottom, (2) hotkey end, (3) hotkey shift+home to select all text in field, (4) type_text your filename.txt, (5) press_key enter. Do NOT use ctrl+a in Save As — it selects the file list, not the text.{step_context}"})
                    else:
                        messages.append({"role": "user",
                                         "content": f"⚠ VERIFY: Did '{atype}' work? Describe what you see.{step_context}"})
                else:
                    action_failure_streak += 1
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        await ctx.send_screenshot()
        if HAS_LEARNING and learning_engine:
            summary = learning_engine.get_learning_summary()
            await ctx.log(f"◆ LEARNING: {summary['total_experiences']} experiences")
        await ctx.log(f"◆ {self.name} finished — ~{word_count} words, {self._actions_executed} actions")

    # ── Writing-specific helpers ──

    def _detect_writing_subtask(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ["blog", "article", "post"]):
            return "blog_post"
        if any(k in p for k in ["document", "documentation", "docs", "readme", "guide"]):
            return "documentation"
        if any(k in p for k in ["email", "mail", "letter"]):
            return "email"
        if any(k in p for k in ["marketing", "ad", "copy", "landing", "sales"]):
            return "marketing_copy"
        if any(k in p for k in ["report", "analysis", "summary"]):
            return "report"
        if any(k in p for k in ["translate", "translation", "localize"]):
            return "translation"
        if any(k in p for k in ["grammar", "proofread", "edit", "fix"]):
            return "editing"
        if any(k in p for k in ["essay", "paper", "thesis", "academic"]):
            return "academic"
        return "general_writing"

    def _get_writing_strategy(self, subtask: str, prompt: str) -> str:
        strategies = {
            "blog_post": (
                "BLOG POST STRATEGY:\n"
                "1. Create a catchy, SEO-friendly title\n"
                "2. Write a hook introduction (2-3 sentences that grab attention)\n"
                "3. Organize body into 3-5 H2 sections\n"
                "4. Include bullet points and examples in each section\n"
                "5. Add a conclusion with key takeaways\n"
                "6. End with a call-to-action\n"
                "Target: 800-1500 words"
            ),
            "documentation": (
                "DOCUMENTATION STRATEGY:\n"
                "1. Title and brief overview\n"
                "2. Prerequisites / Requirements section\n"
                "3. Step-by-step instructions with numbered lists\n"
                "4. Code examples in code blocks\n"
                "5. Troubleshooting / FAQ section\n"
                "6. References and links\n"
                "Be precise, use imperative mood, include exact commands"
            ),
            "email": (
                "EMAIL STRATEGY:\n"
                "1. Clear, concise subject line\n"
                "2. Appropriate greeting\n"
                "3. State purpose in first sentence\n"
                "4. Supporting details (2-3 short paragraphs max)\n"
                "5. Clear action items or next steps\n"
                "6. Professional sign-off\n"
                "Keep it under 200 words"
            ),
            "marketing_copy": (
                "MARKETING COPY STRATEGY:\n"
                "1. Attention-grabbing headline\n"
                "2. Identify the pain point\n"
                "3. Present the solution\n"
                "4. List features → transform into benefits\n"
                "5. Add social proof / testimonials\n"
                "6. Strong CTA with urgency\n"
                "Use power words, short sentences, active voice"
            ),
            "report": (
                "REPORT STRATEGY:\n"
                "1. Executive Summary (key findings in 3-5 sentences)\n"
                "2. Introduction (context and objectives)\n"
                "3. Methodology (how data was gathered)\n"
                "4. Findings (organized by theme with data points)\n"
                "5. Analysis and discussion\n"
                "6. Recommendations\n"
                "7. Conclusion\n"
                "Use data, numbers, and specific examples"
            ),
            "translation": (
                "TRANSLATION STRATEGY:\n"
                "1. Identify source and target language\n"
                "2. Read source text completely first\n"
                "3. Translate paragraph by paragraph\n"
                "4. Preserve formatting and structure\n"
                "5. Adapt idioms/expressions naturally\n"
                "6. Review for accuracy and fluency\n"
                "Prioritize natural target language over word-for-word"
            ),
            "editing": (
                "EDITING STRATEGY:\n"
                "1. Read the entire text first\n"
                "2. Check grammar and spelling\n"
                "3. Improve sentence structure and flow\n"
                "4. Check consistency of tone and style\n"
                "5. Verify punctuation and formatting\n"
                "6. Suggest vocabulary improvements\n"
                "Preserve the author's voice while improving clarity"
            ),
            "academic": (
                "ACADEMIC WRITING STRATEGY:\n"
                "1. Clear thesis statement\n"
                "2. Literature context / background\n"
                "3. Well-structured arguments with evidence\n"
                "4. Proper citations (APA/MLA format)\n"
                "5. Critical analysis, not just description\n"
                "6. Strong conclusion linking back to thesis\n"
                "Formal tone, third person, evidence-based"
            ),
        }
        return strategies.get(subtask, (
            "GENERAL WRITING:\n"
            "1. Determine the purpose and audience\n"
            "2. Create a clear structure\n"
            "3. Write substantive content\n"
            "4. Review and polish\n"
            "5. Save the file"
        ))
