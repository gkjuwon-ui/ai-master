"""
Monitoring Agent — Domain: monitoring
Slug: monitoring_agent

Specialized plugin for monitoring-domain agents (Sentinel Watch, LogHound, UptimeGuard, PerfTracker, PingBot).
Handles system monitoring, log analysis, uptime checks, performance tracking,
health checks, and alert management.

Engines: Tier-dependent
Tools: monitoring-domain specialized tools (health_check, log_parse, metric_collect,
       alert_evaluate, uptime_check, perf_snapshot, anomaly_detect, report_generate)
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


MONITORING_WORKFLOW_GUIDE = """
╔══════════════════════════════════════════════════════════════════════╗
║            MONITORING AGENT — WORKFLOW GUIDE                        ║
╚══════════════════════════════════════════════════════════════════════╝

═══ SYSTEM MONITORING COMMANDS (Windows) ═══
  CPU Usage:        wmic cpu get loadpercentage
                    Get-Counter '\\Processor(_Total)\\% Processor Time'
  RAM Usage:        systeminfo | findstr /C:"Total Physical Memory" /C:"Available Physical Memory"
                    Get-Process | Sort-Object WorkingSet -Descending | Select-Object -First 10
  Disk Usage:       wmic logicaldisk get size,freespace,caption
                    Get-PSDrive -PSProvider FileSystem
  Network:          netstat -an
                    Get-NetTCPConnection | Where-Object State -eq Listen
  Services:         Get-Service | Where-Object Status -eq "Running"
  Event Logs:       Get-EventLog -LogName System -Newest 20
  Processes:        tasklist /v
                    Get-Process | Sort-Object CPU -Descending | Select -First 15

═══ LOG ANALYSIS WORKFLOW ═══
  1. Identify log files location
  2. Read recent entries: Get-Content log.txt -Tail 50
  3. Search for errors: Select-String -Path log.txt -Pattern "ERROR|WARN|CRITICAL"
  4. Parse timestamps and group by time period
  5. Identify patterns and anomalies
  6. Generate summary report

═══ UPTIME CHECK WORKFLOW ═══
  1. HTTP check: Invoke-WebRequest -Uri "http://target" -UseBasicParsing
  2. Ping: Test-Connection -ComputerName target -Count 4
  3. Port check: Test-NetConnection -ComputerName target -Port 80
  4. DNS: Resolve-DnsName target
  5. SSL cert: Check certificate expiry

═══ PERFORMANCE TRACKING ═══
  1. Baseline: Collect initial metrics
  2. Monitor: Periodic sampling at intervals
  3. Analyze: Compare against thresholds
  4. Alert: Flag anomalies above threshold
  5. Report: Generate performance summary with trends
"""


class MonitoringAgent(BasePlugin):
    name = "Monitoring Agent"
    description = "System monitoring agent for health checks, log analysis, uptime tracking, performance metrics, and alert management."
    version = "4.2.0"
    slug = "monitoring_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        mon_sub = self._detect_monitoring_subtask(prompt)
        task_type = self._detect_task_type(prompt)
        if task_type not in ("monitoring", "automation"):
            task_type = "monitoring"

        await ctx.log(f"  Monitoring sub-task: {mon_sub}")

        # ── PLANNER (Tier A+) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"Monitoring task ({mon_sub}). Plan checks, data collection, analysis, report."
            )
            plan_text = "\n\nMonitoring Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status == 'completed' else '→' if s.status == 'running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        strategy = self._get_monitoring_strategy(mon_sub, prompt)

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║        MONITORING AGENT — SPECIALIZED INSTRUCTIONS                  ║
╚══════════════════════════════════════════════════════════════════════╝

You are a MONITORING SPECIALIST. You check system health, analyze logs,
track performance metrics, and create monitoring reports.

DETECTED TASK: {mon_sub}

{strategy}

{MONITORING_WORKFLOW_GUIDE}

═══ MONITORING TOOLS ═══
  • health_check      — Runs comprehensive system health check
  • log_parse         — Parses and filters log files by severity
  • metric_collect    — Collects system performance metrics
  • alert_evaluate    — Evaluates conditions against alert thresholds
  • uptime_check      — Checks service/website availability
  • perf_snapshot     — Takes performance snapshot (CPU, RAM, disk, network)
  • anomaly_detect    — Detects anomalies in metric data
  • report_generate   — Generates structured monitoring report

═══ QUALITY STANDARDS ═══
  ✓ Always collect actual data — never fabricate metrics
  ✓ Include timestamps with all measurements
  ✓ Report both current values and thresholds
  ✓ Save monitoring results to a file
  ✓ Flag anomalies clearly

  ✗ NEVER modify system settings during monitoring
  ✗ NEVER report fabricated metrics
  ✗ NEVER complete without running actual commands
{plan_text}""")

        # Track monitoring metrics
        checks_run = 0
        anomalies_found = 0
        metrics_collected = []
        report_generated = False

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
                await ctx.log(f"  Step {step + 1}/{max_steps} — checks: {checks_run}, anomalies: {anomalies_found}")

            step_context = ""
            if plan:
                ready = plan.get_ready_steps()
                if ready:
                    ready[0].status = "running"
                    step_context = f" [Plan: {ready[0].description}]"

            response = await ctx.ask_llm(messages, screenshot=True)
            messages.append({"role": "assistant", "content": response})

            if len(messages) > self._tier_config.max_message_history:
                max_h = self._tier_config.max_message_history
                messages = [messages[0]] + messages[-(max_h - 1):]

            # Track metrics mentioned in response
            if "METRIC:" in response:
                for line in response.split("\n"):
                    if line.strip().startswith("METRIC:"):
                        metric = line.split("METRIC:", 1)[1].strip()
                        metrics_collected.append(metric)

            if "ANOMALY:" in response or "WARNING:" in response:
                anomalies_found += 1

            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and checks_run > 0:
                    await ctx.log(f"✓ Monitoring complete — {checks_run} checks, {anomalies_found} anomalies")
                    break
                else:
                    messages.append({"role": "user",
                                     "content": "❌ Run at least one monitoring command before completing."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    messages.append({"role": "user",
                                     "content": "Start monitoring! Open PowerShell:\nACTION: open_app\nPARAMS: {\"name\": \"powershell\"}"})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  📊 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    checks_run += 1
                    messages.append({"role": "user",
                                     "content": f"Tool '{tool_name}': {json.dumps(result)[:500]}\nContinue monitoring..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                # Track monitoring-specific operations
                if atype == "run_command":
                    cmd = params.get("command", "").lower()
                    monitoring_cmds = ["systeminfo", "wmic", "get-counter", "get-process",
                                       "get-service", "get-eventlog", "tasklist", "netstat",
                                       "test-connection", "test-netconnection", "ping",
                                       "invoke-webrequest", "get-psdrive"]
                    if any(mc in cmd for mc in monitoring_cmds):
                        checks_run += 1

                await ctx.log(f"  Step {step + 1}: {atype}", "INFO")

                success = False
                for attempt in range(max_retries + 1):
                    result = await self._execute_action(ctx, atype, params)
                    if result.get("blocked"):
                        messages.append({"role": "user", "content": f"⚠ {result['error']}\nRead-only monitoring only."})
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
                                     "content": f"⚠ VERIFY: Check command output. Note any METRIC: or ANOMALY: findings.{step_context}"})
                else:
                    action_failure_streak += 1
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        await ctx.send_screenshot()
        await ctx.log(f"◆ {self.name} finished — {checks_run} checks, {anomalies_found} anomalies, {self._actions_executed} actions")

    # ── Monitoring-specific helpers ──

    def _detect_monitoring_subtask(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ["cpu", "ram", "memory", "resource", "system"]):
            return "system_resources"
        if any(k in p for k in ["log", "event log", "error log"]):
            return "log_analysis"
        if any(k in p for k in ["uptime", "availability", "health check", "alive"]):
            return "uptime_check"
        if any(k in p for k in ["performance", "benchmark", "speed", "latency"]):
            return "performance"
        if any(k in p for k in ["network", "port", "connection", "dns"]):
            return "network"
        if any(k in p for k in ["process", "service", "running"]):
            return "process_monitor"
        if any(k in p for k in ["disk", "storage", "space"]):
            return "disk_monitor"
        if any(k in p for k in ["ping", "reach", "connect"]):
            return "connectivity"
        return "general_monitoring"

    def _get_monitoring_strategy(self, subtask: str, prompt: str) -> str:
        strategies = {
            "system_resources": (
                "SYSTEM RESOURCE MONITORING:\n"
                "1. Open PowerShell\n"
                "2. Check CPU: Get-Counter '\\Processor(_Total)\\% Processor Time' -SampleInterval 2 -MaxSamples 3\n"
                "3. Check RAM: Get-Process | Measure-Object WorkingSet -Sum\n"
                "4. Check Disk: Get-PSDrive -PSProvider FileSystem | Select Name,Used,Free\n"
                "5. Top processes: Get-Process | Sort CPU -Descending | Select -First 10\n"
                "6. Save report to file"
            ),
            "log_analysis": (
                "LOG ANALYSIS STRATEGY:\n"
                "1. Open PowerShell\n"
                "2. Identify log sources: Get-EventLog -List\n"
                "3. Read recent events: Get-EventLog -LogName System -Newest 50\n"
                "4. Filter errors: Get-EventLog -LogName System -EntryType Error -Newest 20\n"
                "5. Analyze patterns and frequency\n"
                "6. Report findings with timestamps"
            ),
            "uptime_check": (
                "UPTIME CHECK STRATEGY:\n"
                "1. Open PowerShell\n"
                "2. For websites: Invoke-WebRequest -Uri 'URL' -UseBasicParsing\n"
                "3. For servers: Test-Connection hostname -Count 4\n"
                "4. For ports: Test-NetConnection hostname -Port number\n"
                "5. Record response times and status codes\n"
                "6. Report availability status"
            ),
            "performance": (
                "PERFORMANCE TRACKING STRATEGY:\n"
                "1. Collect baseline metrics\n"
                "2. Run performance counters over sample period\n"
                "3. Analyze CPU, RAM, disk I/O, network throughput\n"
                "4. Identify bottlenecks and anomalies\n"
                "5. Compare against normal thresholds\n"
                "6. Generate performance report"
            ),
            "network": (
                "NETWORK MONITORING:\n"
                "1. Check connections: netstat -an | findstr ESTABLISHED\n"
                "2. DNS resolution: Resolve-DnsName target\n"
                "3. Port scanning: Test-NetConnection target -Port 80,443,22\n"
                "4. Bandwidth: check network adapter stats\n"
                "5. Report network health"
            ),
            "connectivity": (
                "CONNECTIVITY CHECK:\n"
                "1. Ping target: Test-Connection target -Count 4\n"
                "2. Check response times and packet loss\n"
                "3. Traceroute: tracert target\n"
                "4. Report connectivity status"
            ),
        }
        return strategies.get(subtask, (
            "GENERAL MONITORING:\n"
            "1. Open PowerShell\n"
            "2. Collect relevant system metrics\n"
            "3. Analyze and identify issues\n"
            "4. Report findings"
        ))
