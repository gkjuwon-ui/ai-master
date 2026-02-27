"""
System Agent — Domain: system
Slug: system_agent

Specialized plugin for system-domain agents (SysForge, NetConfig, DiskManager, ProcessGuard, EnvSetup).
Handles system administration, network configuration, disk management, process control,
development environment setup, and OS-level operations.

Engines: Tier-dependent
Tools: system-domain specialized tools (sys_info, service_manage, registry_read,
       network_config, disk_analyze, process_manage, env_setup, backup_create)
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


SYSTEM_WORKFLOW_GUIDE = """
╔══════════════════════════════════════════════════════════════════════╗
║             SYSTEM AGENT — WORKFLOW GUIDE                           ║
╚══════════════════════════════════════════════════════════════════════╝

═══ SYSTEM ADMINISTRATION ═══
  System Info:     systeminfo
                   Get-ComputerInfo | Select OsName,OsVersion,CsTotalPhysicalMemory
  Services:        Get-Service | Where-Object {$_.Status -eq "Running"}
                   Start-Service / Stop-Service / Restart-Service
  Installed Apps:  Get-ItemProperty HKLM:\\Software\\Wow6432Node\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\*
                   winget list
  Environment:     [Environment]::GetEnvironmentVariable("PATH", "Machine")
                   setx VARIABLE "value"
  Scheduled Tasks: Get-ScheduledTask
                   Register-ScheduledTask / Unregister-ScheduledTask

═══ NETWORK CONFIGURATION ═══
  IP Config:       ipconfig /all
                   Get-NetIPAddress | Select InterfaceAlias,IPAddress
  DNS:             Get-DnsClientServerAddress
                   ipconfig /flushdns
  Firewall:        Get-NetFirewallRule -Enabled True | Select DisplayName,Direction,Action
                   New-NetFirewallRule -DisplayName "Name" -Direction Inbound -Protocol TCP -LocalPort 80 -Action Allow
  Interfaces:      Get-NetAdapter | Select Name,Status,LinkSpeed
  Routes:          Get-NetRoute | Select DestinationPrefix,NextHop

═══ DISK MANAGEMENT ═══
  Disk Space:      Get-PSDrive -PSProvider FileSystem | Select Name,@{N='Used(GB)';E={[math]::Round($_.Used/1GB,2)}},@{N='Free(GB)';E={[math]::Round($_.Free/1GB,2)}}
  Large Files:     Get-ChildItem -Path C:\\ -Recurse -ErrorAction SilentlyContinue | Sort Length -Descending | Select -First 20 Name,@{N='Size(MB)';E={[math]::Round($_.Length/1MB,2)}}
  Disk Health:     Get-PhysicalDisk | Select MediaType,HealthStatus,Size
  Temp Cleanup:    Remove-Item -Path $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue

═══ PROCESS MANAGEMENT ═══
  List:            Get-Process | Sort CPU -Descending | Select -First 20 Name,Id,CPU,@{N='Mem(MB)';E={[math]::Round($_.WorkingSet/1MB,2)}}
  Kill:            Stop-Process -Id <PID> -Force
  Start:           Start-Process -FilePath "app.exe"
  Monitor:         Get-Process -Name "process" | Select Name,CPU,WorkingSet

═══ ENVIRONMENT SETUP ═══
  Package Managers: winget / choco / scoop
  Install App:     winget install <package-id>
  Node.js:         winget install OpenJS.NodeJS.LTS
  Python:          winget install Python.Python.3.12
  Git:             winget install Git.Git
  Docker:          winget install Docker.DockerDesktop
  VS Code:         winget install Microsoft.VisualStudioCode

═══ SAFETY RULES ═══
  ⚠ ALWAYS backup before modifying registry
  ⚠ ALWAYS confirm before stopping critical services
  ⚠ NEVER delete system files
  ⚠ NEVER modify boot configuration without explicit request
  ⚠ Test changes on small scale first
"""


class SystemAgent(BasePlugin):
    name = "System Agent"
    description = "System administration agent for OS management, network config, disk management, process control, and dev environment setup."
    version = "4.2.0"
    slug = "system_agent"

    async def execute(self, ctx: "AgentContext", prompt: str, config: dict):
        max_steps = self.get_max_steps(config)
        max_retries = self.get_max_retries()
        delay = self.get_action_delay()

        self.reset_tracking()

        await ctx.log(f"◆ {self.name} v{self.version} [Tier {self.tier}/{self.domain}]")
        await ctx.log(f"  Steps: {max_steps} | Tools: {[t.name for t in self.tools]}")

        sys_sub = self._detect_system_subtask(prompt)
        task_type = self._detect_task_type(prompt)
        if task_type not in ("system", "automation"):
            task_type = "system"

        await ctx.log(f"  System sub-task: {sys_sub}")

        # ── PLANNER (Tier A+) ──
        plan = None
        plan_text = ""
        if self._engine_flags.get("planner") and PlannerEngine:
            planner = PlannerEngine(max_replans=self._tier_config.max_replans)
            plan = await planner.create_plan(
                ctx.llm, prompt,
                context=f"System administration task ({sys_sub}). Plan diagnostics, changes, verification."
            )
            plan_text = "\n\nSystem Plan:\n" + "\n".join(
                f"[{s.step_id}] {'✓' if s.status == 'completed' else '→' if s.status == 'running' else '○'} {s.description}"
                for s in plan.steps
            )
            await ctx.log(f"  Plan: {len(plan.steps)} steps")

        strategy = self._get_system_strategy(sys_sub, prompt)

        system_prompt = self._build_base_system_prompt(
            task_type=task_type,
            extra_context=f"""
╔══════════════════════════════════════════════════════════════════════╗
║         SYSTEM AGENT — SPECIALIZED INSTRUCTIONS                     ║
╚══════════════════════════════════════════════════════════════════════╝

You are a SYSTEM ADMINISTRATION SPECIALIST. You manage Windows systems,
configure networks, manage disks, control processes, and set up environments.

DETECTED TASK: {sys_sub}

{strategy}

{SYSTEM_WORKFLOW_GUIDE}

═══ SYSTEM TOOLS ═══
  • sys_info          — Collects comprehensive system information
  • service_manage    — Manages Windows services (start/stop/restart/status)
  • registry_read     — Reads Windows registry values safely
  • network_config    — Retrieves and analyzes network configuration
  • disk_analyze      — Analyzes disk usage and health
  • process_manage    — Lists, monitors, and manages system processes
  • env_setup         — Sets up development environment with common tools
  • backup_create     — Creates backup of specified files/folders

═══ SAFETY STANDARDS ═══
  ✓ Always check current state before making changes
  ✓ Create backups before modifying system settings
  ✓ Verify changes after applying them
  ✓ Use PowerShell for robust system management
  ✓ Log all modifications for audit trail

  ✗ NEVER delete system files or folders
  ✗ NEVER modify registry without explicit request
  ✗ NEVER stop critical Windows services (winlogon, csrss, etc.)
  ✗ NEVER run format or diskpart without explicit confirmation
{plan_text}""")

        # Track system metrics
        commands_run = 0
        changes_made = 0
        diagnostics_run = 0

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
                await ctx.log(f"  Step {step + 1}/{max_steps} — cmds: {commands_run}, changes: {changes_made}")

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

            if "TASK_COMPLETE" in response.upper():
                allowed, reason = self._verify_completion_allowed(task_type)
                if allowed and commands_run > 0:
                    await ctx.log(f"✓ System task complete — {commands_run} commands, {changes_made} changes")
                    break
                else:
                    messages.append({"role": "user",
                                     "content": "❌ Run at least one system command before completing."})
                    continue

            actions = self._parse_actions(response)
            if not actions:
                consecutive_empty += 1
                if consecutive_empty >= 3:
                    messages.append({"role": "user",
                                     "content": "Open PowerShell:\nACTION: open_app\nPARAMS: {\"name\": \"powershell\"}"})
                    consecutive_empty = 0
                else:
                    msg = self._get_unstuck_message(action_failure_streak, consecutive_empty, task_type)
                    messages.append({"role": "user", "content": msg})
                continue
            consecutive_empty = 0

            for action in actions:
                if action["type"] == "__tool__":
                    tool_name = action["tool_name"]
                    await ctx.log(f"  🔧 Tool: {tool_name}", "INFO")
                    result = await self._execute_tool(tool_name, action["params"])
                    commands_run += 1
                    messages.append({"role": "user",
                                     "content": f"Tool '{tool_name}': {json.dumps(result)[:500]}\nContinue..."})
                    continue

                atype, params = action["type"], action["params"]
                resolved = ctx.resolve_som_action(action) if hasattr(ctx, 'resolve_som_action') else action
                atype, params = resolved["type"], resolved["params"]

                # Track system-specific operations
                if atype == "run_command":
                    commands_run += 1
                    cmd = params.get("command", "").lower()
                    # Track modifications vs read-only
                    modify_cmds = ["set-", "start-service", "stop-service", "restart-service",
                                   "new-", "remove-", "setx", "reg add", "winget install",
                                   "choco install", "sfc", "dism"]
                    if any(mc in cmd for mc in modify_cmds):
                        changes_made += 1
                    else:
                        diagnostics_run += 1

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
                                     "content": f"⚠ VERIFY: Check command output. Was it successful?{step_context}"})
                else:
                    action_failure_streak += 1
                    msg = self._get_unstuck_message(action_failure_streak, 0, task_type)
                    messages.append({"role": "user", "content": msg})

            if plan:
                ready = plan.get_ready_steps()
                if ready and ready[0].status == "running":
                    ready[0].status = "completed"

        await ctx.send_screenshot()
        await ctx.log(f"◆ {self.name} finished — {commands_run} cmds, {changes_made} changes, {self._actions_executed} actions")

    # ── System-specific helpers ──

    def _detect_system_subtask(self, prompt: str) -> str:
        p = prompt.lower()
        if any(k in p for k in ["network", "ip", "dns", "firewall", "wifi", "ethernet"]):
            return "network_config"
        if any(k in p for k in ["disk", "storage", "space", "cleanup", "clean"]):
            return "disk_management"
        if any(k in p for k in ["process", "task", "kill", "running"]):
            return "process_management"
        if any(k in p for k in ["install", "setup", "environment", "dev setup", "configure"]):
            return "env_setup"
        if any(k in p for k in ["service", "daemon", "start service", "stop service"]):
            return "service_management"
        if any(k in p for k in ["registry", "regedit"]):
            return "registry"
        if any(k in p for k in ["backup", "restore"]):
            return "backup"
        if any(k in p for k in ["update", "patch", "upgrade"]):
            return "system_update"
        return "general_system"

    def _get_system_strategy(self, subtask: str, prompt: str) -> str:
        strategies = {
            "network_config": (
                "NETWORK CONFIGURATION STRATEGY:\n"
                "1. Open PowerShell\n"
                "2. Check current config: ipconfig /all\n"
                "3. Check adapters: Get-NetAdapter\n"
                "4. Check IP addresses: Get-NetIPAddress\n"
                "5. Apply requested changes\n"
                "6. Verify new configuration\n"
                "7. Test connectivity"
            ),
            "disk_management": (
                "DISK MANAGEMENT STRATEGY:\n"
                "1. Open PowerShell\n"
                "2. Check disk space: Get-PSDrive -PSProvider FileSystem\n"
                "3. Find large files/folders if cleanup needed\n"
                "4. Clean temp files: Remove-Item $env:TEMP\\* -Recurse -Force -ErrorAction SilentlyContinue\n"
                "5. Run disk cleanup if needed\n"
                "6. Report final disk status"
            ),
            "process_management": (
                "PROCESS MANAGEMENT STRATEGY:\n"
                "1. Open PowerShell\n"
                "2. List processes: Get-Process | Sort CPU -Descending | Select -First 20\n"
                "3. Identify target processes\n"
                "4. Take requested action (kill, restart, monitor)\n"
                "5. Verify result"
            ),
            "env_setup": (
                "ENVIRONMENT SETUP STRATEGY:\n"
                "1. Open PowerShell\n"
                "2. Check what's already installed: winget list\n"
                "3. Install requested tools: winget install <package>\n"
                "4. Configure PATH if needed: setx PATH\n"
                "5. Verify installations\n"
                "6. Set up project structure if needed"
            ),
            "service_management": (
                "SERVICE MANAGEMENT STRATEGY:\n"
                "1. Open PowerShell as needed\n"
                "2. List services: Get-Service | Where Status -eq Running\n"
                "3. Check target service status\n"
                "4. Apply requested action (start/stop/restart)\n"
                "5. Verify new status"
            ),
        }
        return strategies.get(subtask, (
            "SYSTEM ADMINISTRATION:\n"
            "1. Open PowerShell\n"
            "2. Diagnose current state\n"
            "3. Plan and execute changes\n"
            "4. Verify results"
        ))
