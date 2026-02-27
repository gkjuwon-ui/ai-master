"""
Omniscient Agent v2 — Tier S+ ($149.99)
Slug: omniscient_agent

Domain: automation (with cross-domain tool access)
Engines: ALL — Vision + SoM + Planner + Memory + ToolEngine
Tools: ALL automation tools + cross-domain tools from EVERY other domain
Actions: FULL action set (all actions unlocked)

v2 — NOW WITH REAL TASK INTELLIGENCE:
- Detects task type from prompt
- Injects concrete step-by-step strategy
- Prevents premature TASK_COMPLETE before real work is done
- Browser/Windows knowledge for reliable navigation
- Smart initial message based on task type
- Completion verification with minimum action checks
"""

import asyncio
import json
from plugins.base_plugin import BasePlugin

try:
    from core.engine import AgentContext
    from core.planner_engine import PlannerEngine
    from core.memory_engine import MemoryEngine
except ImportError:
    AgentContext = None
    PlannerEngine = None
    MemoryEngine = None


class OmniscientAgent(BasePlugin):
    name = "Omniscient Agent"
    description = "Supreme S+ tier agent. Full engine stack, cross-domain tools, planning with memory, task intelligence."
    version = "4.2.0"
    slug = "omniscient_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()
        flags = self._engine_flags
        
        # Reset tracking
        self.reset_tracking()
        
        # SMART: Detect what kind of task this is
        task_type = self._detect_task_type(prompt)

        await ctx.log(f"★ {self.name} v{self.version} [Tier {self.tier}/{self.domain}] — SUPREME")
        await ctx.log(f"  Task type: {task_type} | Steps: {max_steps} | Retries: {max_retries} | Tools: {len(self.tools)} | Engines: ALL")

        # ── MEMORY: Load session memory (S+ has memory) ──
        memory = None
        memory_context = ""
        if flags.get("memory") and MemoryEngine:
            memory = MemoryEngine()
            past = memory.recall(query=prompt, top_k=10)
            if past:
                memory_context = "\n\nRECALLED MEMORY:\n" + "\n".join(
                    f"  [{m.get('created_at', '?')}] {m.get('content', '')[:200]}" for m in past
                )
                await ctx.log(f"  Memory: {len(past)} recalled items")

        # ── PLANNER: Full planning with replans ──
        plan = None
        plan_text = ""
        planner = None
        if flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Task type: {task_type}. You have FULL OS control, all tools, all capabilities.{memory_context}"
            )
            plan_text = "\n\nMaster Plan:\n" + "\n".join(
                f"  [{s.step_id}] {'✓' if s.status=='completed' else '→' if s.status=='running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps, replans: {self._tier_config.max_replans}")

        # Build cross-domain tool list
        from core.specialized_tools import get_cross_domain_tools
        cross_tools = get_cross_domain_tools(self.domain, self.tier)
        cross_tool_names = [t.name for t in cross_tools if t not in self.tools]

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
OMNISCIENT AGENT — SUPREME TIER ★
You are the most powerful agent. You have FULL access to everything:
- ALL screen actions (click, type, scroll, drag, keyboard, run_command)
- ALL automation tools + cross-domain tools from every specialty
- Planning engine with {self._tier_config.max_replans} replans available
- Memory persistence across sessions
- Up to {max_steps} steps with {max_retries} retries each
- SoM element targeting for precision

DETECTED TASK TYPE: {task_type.upper()}

CROSS-DOMAIN TOOLS (bonus access):
{chr(10).join(f"  - {t}" for t in cross_tool_names[:20])}

ANTI-FAILURE RULES:
- NEVER create empty files. If creating a file, write REAL content.
- NEVER say TASK_COMPLETE if you only looked at the screen.
- NEVER try to interact with the Ogenti chat window — that's YOUR app.
- If you need to research: Open Chrome → Google search → Read results → Compile
- If you need to write: Open Notepad → Type actual content → Save
- If you need to code: Open terminal → Write code → Run it → Verify
- ALWAYS verify your actions worked by checking the screenshot after each action
- If a click didn't work, try using SoM element IDs instead of coordinates

STRATEGY:
1. Plan → Execute → Verify → Replan if needed
2. Save important findings to memory for future sessions
3. Use specialized tools heavily — they are your advantage
4. For complex tasks, break into phases and track progress
5. You can chain: run_command → verify output → type result → screenshot
{memory_context}
{plan_text}""")

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": self._build_initial_user_message(prompt, task_type)},
        ]

        # ═══ Minimize Ogenti so LLM sees the desktop ═══
        await self._minimize_ogenti_window(ctx)

        action_failure_streak = 0
        step_successes = 0
        tools_used = set()
        replan_count = 0
        consecutive_empty = 0

        for step in range(max_steps):
            if step > 0:
                await asyncio.sleep(delay)

            if step == 0:
                await ctx.log(f"  Analyzing screen & calling LLM (step {step+1}/{max_steps})...")
            elif step % 5 == 0:
                await ctx.log(f"  Step {step+1}/{max_steps} — tools used: {len(tools_used)}")

            # Update plan step
            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan: {ready[0].description}]"

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            # Memory: save important observations
            if memory and ("IMPORTANT:" in response or "FINDING:" in response or "RESULT:" in response):
                memory.remember(
                    content=response[:500],
                    memory_type="episodic",
                    importance=0.7,
                    tags=["observation", f"step_{step}"],
                )

            # Trim messages (S+ gets 60)
            if len(messages) > self._tier_config.max_message_history:
                messages = [messages[0]] + messages[-(self._tier_config.max_message_history - 1):]

            # Check for completion — WITH VERIFICATION
            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed:
                    await ctx.log(f"★ Task complete at step {step+1}. {step_successes} actions, {len(tools_used)} unique tools.")
                    break
                else:
                    messages.append({"role": "user", "content": f"❌ Cannot complete yet: {reason}\nKeep working. You have {max_steps - step - 1} steps remaining."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                    consecutive_empty = 0
                else:
                    msg = f"Look at the screen.{step_context} What do you see? Provide ACTION or TOOL."
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    tools_used.add(tool_name)
                    await ctx.log(f"  ★ Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    messages.append({"role": "user", "content": f"Tool [{tool_name}]: {json.dumps(result)[:800]}\nContinue..."})
                    continue

                atype, params = action["type"], action["params"]

                # SoM resolution (S+ always has SoM)
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                await ctx.log(f"  Step {step+1}: {atype}{step_context}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ Unexpected block: {result['error']}. Try another approach."})
                        break
                    if result.get("success", True):
                        success = True
                        break
                    if attempt < max_retries:
                        await asyncio.sleep(0.5)
                        await ctx.send_screenshot()

                await asyncio.sleep(0.3)
                await ctx.send_screenshot()

                if success:
                    step_successes += 1
                    action_failure_streak = 0
                    
                    # Smart feedback based on action type
                    if atype == "open_app":
                        app_name = params.get("name", "")
                        if app_name in ("chrome", "msedge", "edge", "firefox"):
                            messages.append({"role": "user", "content": (
                                "\u26a0 VERIFY: Look at the screenshot. Do you see a BROWSER window?\n"
                                "\u2022 If YES (address bar visible) \u2192 press Ctrl+L, then type your URL.\n"
                                "\u2022 If NO \u2192 wrong window. Try open_app 'msedge' or Alt+Tab.\n"
                                "\u2605 Describe what you see BEFORE taking action."
                            )})
                        elif app_name in ("notepad", "code"):
                            messages.append({"role": "user", "content": (
                                "\u26a0 VERIFY: Look at the screenshot. Is the editor open?\n"
                                "\u2022 If YES \u2192 click inside the text area, then start typing.\n"
                                "\u2022 If NO \u2192 editor didn't open. Retry open_app."
                            )})
                        else:
                            messages.append({"role": "user", "content": f"\u26a0 VERIFY: Did '{app_name}' open? Look at the screenshot and describe what you see.{step_context}"})
                    elif atype in ("type_text", "type_text_fast"):
                        typed = params.get("text", "")
                        if typed.startswith("http") or "://" in typed or "google.com" in typed:
                            messages.append({"role": "user", "content": (
                                "\u26a0\u26a0\u26a0 MANDATORY VERIFICATION \u26a0\u26a0\u26a0\n"
                                "A URL was typed. BEFORE pressing Enter:\n"
                                "1. Look at the ADDRESS BAR in the screenshot.\n"
                                "2. Is the URL visible? Describe what you see.\n"
                                "3. If URL visible \u2192 press Enter.\n"
                                "4. If NOT visible \u2192 typing failed. Ctrl+L and retry."
                            )})
                        else:
                            messages.append({"role": "user", "content": (
                                f"\u26a0 VERIFY: Look at the screenshot. Can you see the typed text?\n"
                                f"\u2022 If YES \u2192 continue.\n"
                                f"\u2022 If NO \u2192 click the target field first, then retry.{step_context}"
                            )})
                    elif atype == "run_command":
                        output = str(result.get("result", ""))[:500] if result.get("result") else "No output"
                        messages.append({"role": "user", "content": f"Command output:\n{output}\nVerify result, then continue.{step_context}"})
                    elif atype in ("click", "click_element"):
                        messages.append({"role": "user", "content": (
                            "\u26a0 VERIFY: Look at the screenshot. Did the click change anything?\n"
                            "\u2022 Describe what you see now vs. before.\n"
                            f"\u2022 If nothing changed \u2192 click missed, try different element.{step_context}"
                        )})
                    else:
                        messages.append({"role": "user", "content": f"\u26a0 VERIFY: '{atype}' executed. Look at the screenshot and describe what changed.{step_context}"})
                else:
                    action_failure_streak += 1
                    if action_failure_streak >= 4 and plan and planner and replan_count < self._tier_config.max_replans:
                        # Replan on persistent failure
                        replan_count += 1
                        plan = await planner.create_plan(
                            ctx.llm, prompt,
                            context=f"Previous approach failed repeatedly (streak={action_failure_streak}). Replan #{replan_count}."
                        )
                        action_failure_streak = 0
                        msg = f"🔄 REPLANNED (#{replan_count}). New strategy available."
                        messages.append({"role": "user", "content": msg})
                    else:
                        msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                        messages.append({"role": "user", "content": msg})

            # Mark plan step complete
            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        # Final memory save
        if memory:
            memory.remember(
                content=f"Task '{prompt[:100]}' finished. {step_successes} successful actions. Tools: {list(tools_used)}",
                memory_type="episodic",
                importance=0.6,
                tags=["session_summary"],
            )

        await ctx.send_screenshot()
        await ctx.log(f"★ {self.name} finished — {step_successes} actions, {len(tools_used)} tools, {replan_count} replans")
