"""
Research Agent v2 — Tier A (Premium mid, $19.99)
Slug: research_agent

Domain: research
Engines: Vision + SoM + Planner (NO memory)
Tools: web_extract, source_credibility, citation_format, save_source, fact_cross_reference,
       compare_sources, research_timeline, gap_analysis, browser_navigate, google_search,
       extract_page_text, open_new_tab, summarize_content (13 tools)
Actions: Research domain (browser, typing, scrolling. NO run_command, NO drag)

v2 — NOW WITH REAL BROWSER INTELLIGENCE:
- Knows to open Chrome FIRST before anything else
- Knows Ctrl+L → type URL → Enter workflow
- Forces minimum 2 website visits before allowing completion
- Compiles research into Notepad report
- Prevents premature TASK_COMPLETE
"""

import asyncio
import json
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


class ResearchAgent(BasePlugin):
    name = "Research Agent"
    description = "Premium research agent with browser intelligence, planning, source credibility scoring, and citation tools."
    version = "4.2.0"
    slug = "research_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()
        
        # Reset tracking
        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        # Detect task type
        task_type = self._detect_task_type(prompt)
        if task_type not in ("research", "browsing"):
            task_type = "research"  # Force research strategy

        # ── PLANNER: Create research strategy (Tier A has planner) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context="Research task. Browser-based. No terminal. Plan search queries, sources, compilation."
            )
            plan_text = "\n\nResearch Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status=='completed' else '→' if s.status=='running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        # Extract search query from prompt
        search_query = prompt
        for prefix in ["research", "find information about", "search for", "look up", "investigate"]:
            if prompt.lower().startswith(prefix):
                search_query = prompt[len(prefix):].strip()
                break

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║         RESEARCH AGENT — SPECIALIZED INSTRUCTIONS                   ║
╚══════════════════════════════════════════════════════════════════════╝

You are a RESEARCH SPECIALIST. Your job is to find REAL information from the 
internet and compile a comprehensive, factual research report.

██████████████████████████████████████████████████████████████████████
██  CRITICAL RULES — VIOLATING THESE WASTES YOUR LIMITED STEPS     ██
██████████████████████████████████████████████████████████████████████

  1. COOKIE BANNERS / CONSENT POPUPS:
     → Click "Accept All" or "Accept" ONCE. If it doesn't dismiss, IGNORE IT.
     → NEVER click "Deny" or "Reject" — these often don't work.
     → NEVER retry a cookie banner click more than once. Just scroll past it.
     → Cookie banners do NOT stop you from reading the page text.

  2. DO NOT USE Ctrl+A or Ctrl+C on web pages:
     → Copying the entire page is USELESS — it grabs menus, ads, footers.
     → Instead: READ the screen with your eyes and write FINDING: lines.
     → Your job is to UNDERSTAND and EXTRACT key facts, not copy HTML.

  3. DO NOT click "Cite", "Download PDF", "Export" or bibliographic buttons:
     → You can see title, authors, journal, year, DOI on the page already.
     → Just READ them and write FINDING: lines.
     → Citation buttons open popups that waste 3-5 clicks.

  4. STEP BUDGET: ~30 steps total. Every wasted click steals from research.

═══ YOUR EXACT WORKFLOW (follow this PRECISE order) ═══

PHASE 1 — OPEN BROWSER (Steps 1-3):
  Step 1: ACTION: open_app    PARAMS: {{"name": "browser"}}
  Step 2: ACTION: wait        PARAMS: {{"seconds": 3}}
  Step 3: VERIFY — you should see Chrome/Edge window with address bar.
          ⚠ If you see File Explorer → WRONG! Do: ACTION: open_app PARAMS: {{"name": "msedge"}}
          ⚠ If you see Ogenti dark chat window → IGNORE! Use open_app.

PHASE 2 — SEARCH GOOGLE (Steps 4-7):
  Step 4: ACTION: hotkey      PARAMS: {{"keys": ["ctrl", "l"]}}
  Step 5: ACTION: type_text   PARAMS: {{"text": "https://www.google.com/search?q={search_query.replace(' ', '+')}"}}
  Step 6: ACTION: press_key   PARAMS: {{"key": "enter"}}
  Step 7: ACTION: wait        PARAMS: {{"seconds": 3}}

PHASE 3 — VISIT SOURCES & READ CONTENT (Steps 8-22):

  ═══ Source 1 (steps 8-13) ═══

  Step 8:  Click FIRST relevant blue link (NON-AD):
           ACTION: click_element PARAMS: {{"id": <the number>}}
  Step 9:  ACTION: wait       PARAMS: {{"seconds": 3}}
           If cookie banner → click "Accept" ONCE. If no effect → ignore it.
  Step 10-12: ★★★ MANDATORY SCROLL-AND-READ (minimum 5 scrolls):
           REPEAT at least 5 times:
             a) Look at screen. READ all visible text.
             b) Write findings NOW:
                FINDING: [exact fact / stat / name / date from screen]
             c) ACTION: scroll  PARAMS: {{"clicks": -5}}
           ★ MUST write 3+ FINDING: lines before leaving this page.
  Step 13: Go back:
           ACTION: hotkey     PARAMS: {{"keys": ["alt", "left"]}}
           ACTION: wait       PARAMS: {{"seconds": 2}}

  ═══ Source 2 (steps 14-18) ═══

  Step 14: Click SECOND relevant result.
  Step 15-17: Same scroll-and-read: 5+ scrolls, 3+ FINDING: lines.
  Step 18: Go back.

  ═══ Source 3 (steps 19-22) ═══

  Step 19: Click THIRD result.
  Step 20-21: Same scroll-and-read: 5+ scrolls, 3+ FINDING: lines.
  Step 22: Done gathering. You should have 9+ FINDING: lines total.

PHASE 4 — COMPILE REPORT (Steps 23-28):
  Step 23: ACTION: open_app   PARAMS: {{"name": "notepad"}}
  Step 24: ACTION: wait       PARAMS: {{"seconds": 2}}
  Step 25: ACTION: click      PARAMS: {{"x": 400, "y": 400}}
  Step 26: ACTION: type_text_fast  PARAMS: {{"text": "YOUR COMPLETE RESEARCH REPORT"}}
           
           ★★★ Report MUST synthesize your FINDING: lines into:
           • Title of the research topic
           • Introduction / overview
           • Key findings organized by theme
           • Specific facts, numbers, dates, names from sources
           • Source URLs
           • Conclusion / summary
           • Minimum 500 characters of REAL content
           
  Step 27: ACTION: hotkey     PARAMS: {{"keys": ["ctrl", "s"]}}
  Step 28: If Save As dialog → type filename → press Enter

═══ RESEARCH QUALITY STANDARDS ═══

  ✓ Visit at least 2 different websites (preferably 3+)
  ✓ Tag at least 6 findings with FINDING: prefix
  ✓ Write a report with REAL factual content (not placeholder text)
  ✓ Include source URLs in the report

  ✗ NEVER fabricate information you didn't actually read
  ✗ NEVER say TASK_COMPLETE before compiling a report
  ✗ NEVER open File Explorer for research — use BROWSER only
  ✗ NEVER use Ctrl+A/Ctrl+C on web pages
  ✗ NEVER click cookie banners more than once

═══ DOMAIN BOUNDARIES ═══

  You are a RESEARCHER. You browse the web and compile findings.
  You CANNOT run terminal commands (run_command is not in your allowed actions).
  You CANNOT write code or do file management.
  You CAN: open_app, click, type_text, scroll, hotkey, press_key, wait, focus_window.
{plan_text}""")

        # Track research metrics
        findings = []
        sources_count = 0
        urls_visited = []
        browser_opened = False
        report_started = False

        # ═══ LEARNING ENGINE ═══
        learning_engine = None
        if HAS_LEARNING:
            learning_engine = LearningEngine()

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_initial_user_message(prompt, task_type)},
        ]

        action_failure_streak = 0
        consecutive_empty = 0

        # ═══ AUTO-START: Minimize Ogenti so LLM sees the desktop ═══
        await self._minimize_ogenti_window(ctx)

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            # Progress log so user sees what's happening
            if step == 0:
                await ctx.log(f"  Analyzing search results (step {step+1}/{max_steps})...")
            elif step % 3 == 0:
                await ctx.log(f"  Step {step+1}/{max_steps} — {len(findings)} findings, {sources_count} sources")

            # Update plan step context
            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan step: {ready[0].description}]"

            # ═══ LEARNING ADAPTATIONS ═══
            if HAS_LEARNING and learning_engine:
                try:
                    adaptations = learning_engine.get_adaptations(task_type, {})
                    if adaptations:
                        adaptation_msg = "🧠 LEARNING ADAPTATIONS:\n" + "\n".join([f"• {a['recommendation']}" for a in adaptations[:3]])
                        messages.append({"role": "user", "content": adaptation_msg})
                except Exception as e:
                    await ctx.log(f"Learning engine error: {e}", "WARN")

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            # Log LLM response preview so user can see what's happening
            response_preview = response[:150].replace('\n', ' ').strip()
            await ctx.log(f"  LLM: {response_preview}...", "DEBUG")

            if len(messages) > self._tier_config.max_message_history:
                # Intelligent context trimming with learning preservation
                max_h = self._tier_config.max_message_history
                if HAS_LEARNING and learning_engine:
                    dropped_count = len(messages) - max_h + 2
                    dropped = messages[1:dropped_count + 1]
                    
                    # Build summary
                    summary_parts = [
                        f"╔══ CONTEXT SUMMARY ══╗",
                        f"Task: {prompt}",
                    ]
                    
                    # Add learning insights
                    metrics = learning_engine.get_performance_metrics(task_type)
                    if task_type in metrics:
                        summary_parts.append(f"Success Rate: {metrics[task_type]['success_rate']:.1%}")
                    
                    summary_parts.append("╚═════════════════════╝")
                    
                    summary_msg = {"role": "user", "content": "\n".join(summary_parts)}
                    messages = [messages[0], summary_msg] + messages[dropped_count + 1:]
                else:
                    messages = [messages[0]] + messages[-(max_h - 1):]

            # Extract findings and update learning
            if "FINDING:" in response:
                for line in response.split("\n"):
                    if line.strip().startswith("FINDING:"):
                        finding = line.split("FINDING:", 1)[1].strip()
                        findings.append(finding)
                        
                        # Update learning engine with finding
                        if HAS_LEARNING and learning_engine:
                            learning_engine.add_experience(
                                task_type=task_type,
                                command=prompt,
                                context={},
                                action="extract_finding",
                                result={"success": True, "finding": finding},
                                confidence=0.8
                            )

            # Check for completion — WITH VERIFICATION
            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and sources_count >= 2 and self._has_typed_content:
                    await ctx.log(f"✓ Research complete — {len(findings)} findings, {sources_count} sources")
                    break
                else:
                    # Not enough work done
                    if sources_count < 2:
                        msg = f"❌ Cannot complete yet. Only {sources_count} sources visited. Need at least 2. Go back to Chrome and visit more sources."
                    elif not self._has_typed_content:
                        msg = "❌ Cannot complete yet. You haven't compiled your findings. Open Notepad and write a research report."
                    else:
                        msg = f"❌ Cannot complete: {reason}"
                    messages.append({"role": "user", "content": msg})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                await ctx.log(f"  ⚠ No actions parsed (attempt {consecutive_empty}/3) — nudging LLM", "WARN")
                if consecutive_empty >= 3:
                    if not browser_opened:
                        messages.append({"role": "user", "content": "You MUST start by opening a browser!\nACTION: open_app\nPARAMS: {\"name\": \"chrome\"}\nDo this NOW."})
                    elif sources_count < 2:
                        messages.append({"role": "user", "content": "Search Google and visit sources. Use Ctrl+L to type in the address bar."})
                    else:
                        messages.append({"role": "user", "content": "Compile your findings now. Open Notepad and write the research report."})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  🔍 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])

                    if tool_name == "source_credibility" and result.get("success"):
                        sources_count += 1
                        msg = f"Source scored: {result['credibility_score']}/10 ({result['label']}) — {result.get('url', '')[:60]}"
                    elif tool_name == "save_source" and result.get("success"):
                        msg = f"Source saved. Total: {result['total_sources']}"
                    elif tool_name == "fact_cross_reference" and result.get("success"):
                        msg = f"Fact check: {result['confidence']} confidence — {result['supporting_sources']} supporting sources"
                    elif tool_name == "citation_format" and result.get("success"):
                        msg = f"Citation: {result['citation']}"
                    elif tool_name == "google_search" and result.get("success"):
                        msg = f"Search URL ready: {result.get('search_url', '')}. Now execute the steps to navigate there."
                    elif tool_name == "summarize_content" and result.get("success"):
                        msg = f"Summary: {'; '.join(result.get('key_points', [])[:3])}"
                    else:
                        msg = f"Tool result: {json.dumps(result)[:400]}"

                    messages.append({"role": "user", "content": msg + "\nContinue research..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                # Track research-specific actions
                if atype == "open_app":
                    app_name = params.get("name", "").lower()
                    if app_name in ("chrome", "msedge", "firefox", "edge", "browser"):
                        browser_opened = True
                    if app_name in ("notepad", "code", "notepad++"):
                        report_started = True

                await ctx.log(f"  Step {step+1}: {atype}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ {result['error']}\nYou are a RESEARCHER. Browse and type only."})
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
                    
                    # Update learning engine with successful action
                    if HAS_LEARNING and learning_engine:
                        learning_engine.add_experience(
                            task_type=task_type,
                            command=prompt,
                            context={},
                            action=f"{atype}_{str(params)[:100]}",
                            result={"success": True, "duration": 0.5},
                            confidence=0.7
                        )
                    
                    # Track URLs in learning context
                    if HAS_LEARNING and learning_engine:
                        if atype in ("type_text", "type_text_fast"):
                            typed = params.get("text", "")
                            if typed.startswith("http") or "google.com" in typed:
                                learning_engine.add_experience(
                                    task_type=task_type,
                                    command="url_navigation",
                                    context={},
                                    action="navigate_to_url",
                                    result={"success": True, "url": typed[:200]},
                                    confidence=0.9
                                )
                    
                    # Smart context-aware feedback — ALWAYS require visual verification
                    if atype == "open_app":
                        app_name = params.get("name", "")
                        if app_name in ("chrome", "msedge", "edge", "firefox"):
                            messages.append({"role": "user", "content": (
                                f"\u26a0 VERIFY: Look at the screenshot. Do you see a BROWSER window?\n"
                                "\u2022 If YES (address bar visible) \u2192 press Ctrl+L, then type your search URL.\n"
                                "\u2022 If you see File Explorer or Ogenti \u2192 WRONG window. Try: open_app with 'msedge' or Alt+Tab.\n"
                                "\u2605 Describe what you see BEFORE taking the next action."
                            )})
                        elif app_name in ("notepad", "code"):
                            messages.append({"role": "user", "content": (
                                f"\u26a0 VERIFY: Look at the screenshot. Do you see a text editor?\n"
                                f"\u2022 If YES \u2192 click inside the text area, then type your report ({sources_count} sources).\n"
                                "\u2022 If NO \u2192 the editor may not have opened. Retry open_app.\n"
                                "\u2605 Describe what you see BEFORE typing."
                            )})
                        else:
                            messages.append({"role": "user", "content": f"\u26a0 VERIFY: Look at the screenshot. Did '{app_name}' open? Describe what you see.{step_context}"})
                    elif atype in ("type_text", "type_text_fast"):
                        text = params.get("text", "")
                        if "google.com" in text or text.startswith("http") or "://" in text:
                            messages.append({"role": "user", "content": (
                                "\u26a0\u26a0\u26a0 MANDATORY VERIFICATION \u2014 DO NOT SKIP \u26a0\u26a0\u26a0\n"
                                "A URL was typed. BEFORE pressing Enter:\n"
                                "1. Look at the ADDRESS BAR in the screenshot RIGHT NOW.\n"
                                "2. Is the URL visible there? Describe EXACTLY what the address bar shows.\n"
                                "3. If you can see the URL \u2192 press Enter.\n"
                                "4. If the address bar is EMPTY or shows something else \u2192 typing FAILED.\n"
                                "   Recovery: press Ctrl+L, then type_text again.\n"
                                "\u2605 NEVER press Enter unless you can SEE the URL in the address bar."
                            )})
                        else:
                            messages.append({"role": "user", "content": (
                                f"\u26a0 VERIFY: Look at the screenshot. Can you see the typed text in the target field?\n"
                                f"\u2022 If YES \u2192 continue with next action.\n"
                                f"\u2022 If NO \u2192 typing failed. Click the field first, then retry.{step_context}"
                            )})
                    elif atype == "press_key" and params.get("key") == "enter":
                        messages.append({"role": "user", "content": (
                            "\u26a0 VERIFY: Enter was pressed. Look at the screenshot:\n"
                            "\u2022 Did the page change / start loading?\n"
                            "\u2022 If a new page loaded \u2192 wait 2-3 seconds, then read results.\n"
                            "\u2022 If NOTHING changed \u2192 Enter may not have worked. Check focus and retry."
                        )})
                    elif atype == "click" or atype == "click_element":
                        messages.append({"role": "user", "content": (
                            "\u26a0 VERIFY: Look at the screenshot. Did the click work?\n"
                            "\u2022 Did the page change? Describe what you see now.\n"
                            "\u2022 If a new page loaded \u2192 read content, note FINDING: for discoveries.\n"
                            "\u2022 If NOTHING changed \u2192 click missed. Re-examine and pick a different element."
                        )})
                    elif atype == "scroll":
                        messages.append({"role": "user", "content": (
                            "\u26a0 VERIFY: Look at the screenshot after scrolling.\n"
                            "\u2022 Read the new content visible on screen.\n"
                            "\u2022 Note key findings with FINDING: prefix.\n"
                            "\u2022 If you need more \u2192 scroll again. If done \u2192 next phase."
                        )})
                    else:
                        messages.append({"role": "user", "content": f"\u26a0 VERIFY: Look at the screenshot. Did '{atype}' work? Describe what you see.{step_context}"})
                else:
                    action_failure_streak += 1
                    
                    # Update learning engine with failed action
                    if HAS_LEARNING and learning_engine:
                        learning_engine.add_experience(
                            task_type=task_type,
                            command=prompt,
                            context={},
                            action=f"{atype}_{str(params)[:100]}",
                            result={"success": False, "error": "Action failed"},
                            confidence=0.3
                        )
                    
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

            # Mark plan step complete
            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        await ctx.send_screenshot()
        
        # Final learning summary
        if HAS_LEARNING and learning_engine:
            learning_summary = learning_engine.get_learning_summary()
            await ctx.log(f"◆ LEARNING SUMMARY: {learning_summary['total_experiences']} experiences, {learning_summary['total_patterns']} patterns learned")
        
        await ctx.log(f"◆ {self.name} finished — {len(findings)} findings, {sources_count} sources scored, {self._actions_executed} actions")
