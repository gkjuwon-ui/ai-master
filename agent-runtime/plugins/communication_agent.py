"""
Communication Agent — Domain: communication
Slug: communication_agent

Specialized plugin for communication-domain agents (Nexus Chat, MailForge, MeetBot, SlackOps, QuickReply).
Handles email composition, message formatting, multi-platform communication workflows,
meeting scheduling, and professional correspondence.

Engines: Tier-dependent
Tools: communication-domain specialized tools (email_compose, tone_adjust, template_fill,
       schedule_meeting, format_message, contact_lookup, thread_summarize, priority_classify)
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


COMMUNICATION_WORKFLOW_GUIDE = """
╔══════════════════════════════════════════════════════════════════════╗
║           COMMUNICATION AGENT — WORKFLOW GUIDE                      ║
╚══════════════════════════════════════════════════════════════════════╝

═══ EMAIL WORKFLOW ═══
  1. Open browser → navigate to email service (Gmail, Outlook)
  2. Click Compose/New
  3. Fill To, Subject fields
  4. Write email body with proper structure
  5. Review and send

═══ MESSAGING WORKFLOW ═══
  1. Open messaging app (Slack, Discord, Teams) in browser
  2. Navigate to target channel/DM
  3. Type and format message
  4. Review and send

═══ MEETING WORKFLOW ═══
  1. Open calendar app in browser
  2. Create new event
  3. Fill title, time, attendees, description
  4. Add meeting link/location
  5. Send invitations

═══ PROFESSIONAL COMMUNICATION RULES ═══
  • Always use appropriate greeting/sign-off
  • Match tone to context (formal/casual/urgent)
  • Keep messages concise and actionable
  • Include clear subject lines for emails
  • Proofread before sending
  • Use bullet points for multiple items
"""


class CommunicationAgent(BasePlugin):
    name = "Communication Agent"
    description = "Professional communication agent for email composition, messaging, meeting scheduling, and multi-platform communication."
    version = "4.2.0"
    slug = "communication_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        comm_sub = self._detect_comm_subtask(prompt)
        task_type = self._detect_task_type(prompt)
        if task_type not in ("communication", "writing", "browsing"):
            task_type = "communication"

        await ctx.log(f"  Communication sub-task: {comm_sub}")

        # ── PLANNER (Tier A+) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Communication task ({comm_sub}). Plan message composition, review, send."
            )
            plan_text = "\n\nCommunication Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status == 'completed' else '→' if s.status == 'running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        strategy = self._get_comm_strategy(comm_sub, prompt)

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║      COMMUNICATION AGENT — SPECIALIZED INSTRUCTIONS                 ║
╚══════════════════════════════════════════════════════════════════════╝

You are a COMMUNICATION SPECIALIST. You compose, format, and manage 
professional communications across email, messaging, and scheduling platforms.

DETECTED TASK: {comm_sub}

{strategy}

{COMMUNICATION_WORKFLOW_GUIDE}

═══ COMMUNICATION TOOLS ═══
  • email_compose      — Generates professional email from parameters
  • tone_adjust        — Adjusts message tone (formal/casual/urgent/friendly)
  • template_fill      — Fills communication templates with context
  • schedule_meeting   — Creates meeting invitation details
  • format_message     — Formats message for platform (Slack/Email/Teams)
  • contact_lookup     — Suggests contact info from context
  • thread_summarize   — Summarizes long message threads
  • priority_classify  — Classifies message urgency and priority

═══ QUALITY STANDARDS ═══
  ✓ Messages must be clear, concise, and professional
  ✓ Emails must have proper subject, greeting, body, sign-off
  ✓ Match tone to audience and context
  ✓ Include action items and deadlines where applicable
  ✓ Proofread before completion

  ✗ NEVER send without reviewing content
  ✗ NEVER use overly casual tone in professional context
  ✗ NEVER create empty messages
{plan_text}""")

        # Track communication metrics
        message_composed = False
        has_sent = False
        platform_opened = False

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
                await ctx.log(f"  Step {step + 1}/{max_steps} — composed: {message_composed}, sent: {has_sent}")

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
                        messages.append({"role": "user",
                                         "content": "🧠 " + "\n".join(
                                             [f"• {a['recommendation']}" for a in adaptations[:3]])})
                except Exception:
                    pass

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                max_h = self._tier_config.max_message_history
                messages = [messages[0]] + messages[-(max_h - 1):]

            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and self._has_typed_content:
                    await ctx.log(f"✓ Communication task complete")
                    break
                else:
                    messages.append({"role": "user",
                                     "content": f"❌ Cannot complete: compose and review your message first."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    if not platform_opened:
                        messages.append({"role": "user",
                                         "content": "Open the communication platform first.\nACTION: open_app\nPARAMS: {\"name\": \"browser\"}"})
                    else:
                        messages.append({"role": "user",
                                         "content": "Compose your message now. Type the content."})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  💬 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    messages.append({"role": "user",
                                     "content": f"Tool '{tool_name}': {json.dumps(result)[:500]}\nContinue..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                if atype == "open_app":
                    app = params.get("name", "").lower()
                    if app in ("chrome", "msedge", "firefox", "edge", "browser", "outlook", "thunderbird"):
                        platform_opened = True

                if atype in ("type_text", "type_text_fast"):
                    text = params.get("text", "")
                    if len(text) > 30:
                        message_composed = True

                await ctx.log(f"  Step {step + 1}: {atype}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ {result['error']}"})
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
                            action=atype, result={"success": True}, confidence=0.7)
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
        await ctx.log(f"◆ {self.name} finished — {self._actions_executed} actions")

    # ── Communication-specific helpers ──

    def _detect_comm_subtask(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ["email", "mail", "letter"]):
            return "email"
        if any(k in p for k in ["slack", "discord", "teams", "message", "chat"]):
            return "messaging"
        if any(k in p for k in ["meeting", "schedule", "calendar", "invite", "appointment"]):
            return "meeting"
        if any(k in p for k in ["reply", "respond", "answer"]):
            return "reply"
        if any(k in p for k in ["announce", "broadcast", "newsletter"]):
            return "announcement"
        return "general_communication"

    def _get_comm_strategy(self, subtask: str, prompt: str) -> str:
        strategies = {
            "email": (
                "EMAIL COMPOSITION STRATEGY:\n"
                "1. Determine recipient and context\n"
                "2. Craft clear subject line\n"
                "3. Write greeting appropriate to relationship\n"
                "4. State purpose in first sentence\n"
                "5. Provide details in 2-3 concise paragraphs\n"
                "6. Include action items / next steps\n"
                "7. Professional sign-off"
            ),
            "messaging": (
                "MESSAGING STRATEGY:\n"
                "1. Open target platform in browser\n"
                "2. Navigate to correct channel/DM\n"
                "3. Write concise, contextual message\n"
                "4. Use formatting (bold, code blocks) as needed\n"
                "5. @mention relevant people\n"
                "6. Review and send"
            ),
            "meeting": (
                "MEETING SCHEDULING STRATEGY:\n"
                "1. Open calendar application\n"
                "2. Check availability for proposed time\n"
                "3. Create event with clear title\n"
                "4. Add description with agenda\n"
                "5. Set duration and recurrence if needed\n"
                "6. Add attendees and meeting link\n"
                "7. Send invitations"
            ),
            "reply": (
                "REPLY STRATEGY:\n"
                "1. Read original message carefully\n"
                "2. Identify all questions/requests\n"
                "3. Address each point systematically\n"
                "4. Keep response proportional to query\n"
                "5. Proofread and send"
            ),
            "announcement": (
                "ANNOUNCEMENT STRATEGY:\n"
                "1. Craft attention-grabbing headline\n"
                "2. Lead with most important information\n"
                "3. Provide context and details\n"
                "4. Include action items if any\n"
                "5. Format for target platform"
            ),
        }
        return strategies.get(subtask, (
            "COMMUNICATION STRATEGY:\n"
            "1. Identify platform and audience\n"
            "2. Determine appropriate tone\n"
            "3. Compose clear, structured message\n"
            "4. Review and finalize"
        ))
