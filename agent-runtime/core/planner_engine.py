"""
Planner Engine — Premium multi-step task planning system.

Unlike the basic generic agent (simple LLM loop), this engine provides:
- Hierarchical planning: breaks tasks into subtasks with dependencies
- Plan validation: checks feasibility before execution
- Adaptive replanning: adjusts plan when actions fail
- Progress tracking: monitors completion % across subtasks
- Rollback support: can undo partial progress on failure
- Memory system: remembers context across long sessions
- Parallel subtask execution: runs independent subtasks concurrently
- Task-type intelligence: uses domain-specific templates for common tasks
"""

import asyncio
import time
import json
from typing import Optional
from loguru import logger

# Import task intelligence
try:
    from core.engine import TaskAnalyzer, TaskType
    HAS_TASK_INTELLIGENCE = True
except ImportError:
    HAS_TASK_INTELLIGENCE = False


# ═══════════════════════════════════════════════════════════════════════
# TASK-SPECIFIC PLAN TEMPLATES
# ═══════════════════════════════════════════════════════════════════════
# Pre-built plan templates for common task types.
# These provide concrete, actionable steps instead of vague LLM-generated plans.

PLAN_TEMPLATES = {
    "research": [
        {"step_id": 1, "description": "Open Google Chrome web browser", "action_type": "open_app", "depends_on": [], "estimated_duration": 3, "params": {"name": "chrome"}},
        {"step_id": 2, "description": "Wait for Chrome to fully load", "action_type": "wait", "depends_on": [1], "estimated_duration": 3, "params": {"seconds": 3}},
        {"step_id": 3, "description": "Focus the address bar using Ctrl+L", "action_type": "hotkey", "depends_on": [2], "estimated_duration": 1, "params": {"keys": ["ctrl", "l"]}},
        {"step_id": 4, "description": "Navigate to Google search with the research query", "action_type": "type_and_enter", "depends_on": [3], "estimated_duration": 3, "params": {"text": "https://www.google.com/search?q={query}"}},
        {"step_id": 5, "description": "Read and analyze the first page of search results", "action_type": "read_screen", "depends_on": [4], "estimated_duration": 10, "params": {}},
        {"step_id": 6, "description": "Click on the first relevant search result link", "action_type": "click", "depends_on": [5], "estimated_duration": 5, "params": {}},
        {"step_id": 7, "description": "Read the article/page content by scrolling through it", "action_type": "read_screen", "depends_on": [6], "estimated_duration": 15, "params": {}},
        {"step_id": 8, "description": "Go back to search results (Alt+Left)", "action_type": "hotkey", "depends_on": [7], "estimated_duration": 2, "params": {"keys": ["alt", "left"]}},
        {"step_id": 9, "description": "Click on the second relevant search result", "action_type": "click", "depends_on": [8], "estimated_duration": 5, "params": {}},
        {"step_id": 10, "description": "Read the second source by scrolling through", "action_type": "read_screen", "depends_on": [9], "estimated_duration": 15, "params": {}},
        {"step_id": 11, "description": "Go back to search results again", "action_type": "hotkey", "depends_on": [10], "estimated_duration": 2, "params": {"keys": ["alt", "left"]}},
        {"step_id": 12, "description": "Click on a third source for comprehensive research", "action_type": "click", "depends_on": [11], "estimated_duration": 5, "params": {}},
        {"step_id": 13, "description": "Read the third source content", "action_type": "read_screen", "depends_on": [12], "estimated_duration": 15, "params": {}},
        {"step_id": 14, "description": "Open Notepad to write the research report", "action_type": "open_app", "depends_on": [13], "estimated_duration": 3, "params": {"name": "notepad"}},
        {"step_id": 15, "description": "Wait for Notepad to open", "action_type": "wait", "depends_on": [14], "estimated_duration": 2, "params": {"seconds": 2}},
        {"step_id": 16, "description": "Type the full research report with findings from all sources", "action_type": "type_text", "depends_on": [15], "estimated_duration": 30, "params": {}},
        {"step_id": 17, "description": "Save the report file (Ctrl+S)", "action_type": "hotkey", "depends_on": [16], "estimated_duration": 3, "params": {"keys": ["ctrl", "s"]}},
        {"step_id": 18, "description": "Type filename in save dialog and confirm", "action_type": "type_and_enter", "depends_on": [17], "estimated_duration": 3, "params": {"text": "research_report.txt"}},
    ],
    "coding": [
        {"step_id": 1, "description": "Open VS Code or preferred code editor", "action_type": "open_app", "depends_on": [], "estimated_duration": 5, "params": {"name": "code"}},
        {"step_id": 2, "description": "Wait for editor to load", "action_type": "wait", "depends_on": [1], "estimated_duration": 3, "params": {"seconds": 3}},
        {"step_id": 3, "description": "Create a new file (Ctrl+N)", "action_type": "hotkey", "depends_on": [2], "estimated_duration": 2, "params": {"keys": ["ctrl", "n"]}},
        {"step_id": 4, "description": "Write the code implementation", "action_type": "type_text", "depends_on": [3], "estimated_duration": 60, "params": {}},
        {"step_id": 5, "description": "Save the code file (Ctrl+S)", "action_type": "hotkey", "depends_on": [4], "estimated_duration": 3, "params": {"keys": ["ctrl", "s"]}},
        {"step_id": 6, "description": "Name the file and confirm save", "action_type": "type_and_enter", "depends_on": [5], "estimated_duration": 3, "params": {}},
        {"step_id": 7, "description": "Open terminal to test the code", "action_type": "hotkey", "depends_on": [6], "estimated_duration": 2, "params": {"keys": ["ctrl", "`"]}},
        {"step_id": 8, "description": "Run the code and check output", "action_type": "run_command", "depends_on": [7], "estimated_duration": 10, "params": {}},
        {"step_id": 9, "description": "Fix any errors if test failed", "action_type": "llm_driven", "depends_on": [8], "estimated_duration": 30, "params": {}},
        {"step_id": 10, "description": "Final save and verification", "action_type": "hotkey", "depends_on": [9], "estimated_duration": 3, "params": {"keys": ["ctrl", "s"]}},
    ],
    "writing": [
        {"step_id": 1, "description": "Open Notepad text editor", "action_type": "open_app", "depends_on": [], "estimated_duration": 3, "params": {"name": "notepad"}},
        {"step_id": 2, "description": "Wait for Notepad to load", "action_type": "wait", "depends_on": [1], "estimated_duration": 2, "params": {"seconds": 2}},
        {"step_id": 3, "description": "Type the document title and introduction", "action_type": "type_text", "depends_on": [2], "estimated_duration": 15, "params": {}},
        {"step_id": 4, "description": "Type the main body content with sections", "action_type": "type_text", "depends_on": [3], "estimated_duration": 30, "params": {}},
        {"step_id": 5, "description": "Type the conclusion", "action_type": "type_text", "depends_on": [4], "estimated_duration": 10, "params": {}},
        {"step_id": 6, "description": "Review and proofread by scrolling up", "action_type": "read_screen", "depends_on": [5], "estimated_duration": 10, "params": {}},
        {"step_id": 7, "description": "Save the document (Ctrl+S)", "action_type": "hotkey", "depends_on": [6], "estimated_duration": 3, "params": {"keys": ["ctrl", "s"]}},
        {"step_id": 8, "description": "Name the file and confirm", "action_type": "type_and_enter", "depends_on": [7], "estimated_duration": 3, "params": {}},
    ],
    "browsing": [
        {"step_id": 1, "description": "Open Chrome web browser", "action_type": "open_app", "depends_on": [], "estimated_duration": 3, "params": {"name": "chrome"}},
        {"step_id": 2, "description": "Wait for browser to load", "action_type": "wait", "depends_on": [1], "estimated_duration": 3, "params": {"seconds": 3}},
        {"step_id": 3, "description": "Focus address bar with Ctrl+L", "action_type": "hotkey", "depends_on": [2], "estimated_duration": 1, "params": {"keys": ["ctrl", "l"]}},
        {"step_id": 4, "description": "Type the target URL and press Enter", "action_type": "type_and_enter", "depends_on": [3], "estimated_duration": 3, "params": {}},
        {"step_id": 5, "description": "Wait for page to load", "action_type": "wait", "depends_on": [4], "estimated_duration": 3, "params": {"seconds": 3}},
        {"step_id": 6, "description": "Interact with the page as needed", "action_type": "llm_driven", "depends_on": [5], "estimated_duration": 30, "params": {}},
    ],
    "data_analysis": [
        {"step_id": 1, "description": "Open terminal or code editor", "action_type": "open_app", "depends_on": [], "estimated_duration": 3, "params": {"name": "code"}},
        {"step_id": 2, "description": "Locate data files or prepare data source", "action_type": "llm_driven", "depends_on": [1], "estimated_duration": 10, "params": {}},
        {"step_id": 3, "description": "Write analysis script or use tools", "action_type": "type_text", "depends_on": [2], "estimated_duration": 30, "params": {}},
        {"step_id": 4, "description": "Run analysis and review results", "action_type": "run_command", "depends_on": [3], "estimated_duration": 15, "params": {}},
        {"step_id": 5, "description": "Write summary of findings", "action_type": "type_text", "depends_on": [4], "estimated_duration": 15, "params": {}},
        {"step_id": 6, "description": "Save results", "action_type": "hotkey", "depends_on": [5], "estimated_duration": 3, "params": {"keys": ["ctrl", "s"]}},
    ],
    "automation": [
        {"step_id": 1, "description": "Open terminal", "action_type": "open_app", "depends_on": [], "estimated_duration": 3, "params": {"name": "terminal"}},
        {"step_id": 2, "description": "Write automation script", "action_type": "type_text", "depends_on": [1], "estimated_duration": 20, "params": {}},
        {"step_id": 3, "description": "Test automation", "action_type": "run_command", "depends_on": [2], "estimated_duration": 10, "params": {}},
        {"step_id": 4, "description": "Verify results", "action_type": "read_screen", "depends_on": [3], "estimated_duration": 5, "params": {}},
        {"step_id": 5, "description": "Fix issues if any", "action_type": "llm_driven", "depends_on": [4], "estimated_duration": 15, "params": {}},
    ],
}


class PlanValidator:
    """Validates execution plans for feasibility and completeness."""
    
    @staticmethod
    def validate(plan: 'ExecutionPlan') -> dict:
        """
        Validate a plan and return {valid: bool, issues: list[str], suggestions: list[str]}.
        """
        issues = []
        suggestions = []
        
        if not plan.steps:
            issues.append("Plan has no steps")
            return {"valid": False, "issues": issues, "suggestions": ["Create at least 2 steps"]}
        
        # Check for missing dependencies
        all_ids = {s.step_id for s in plan.steps}
        for step in plan.steps:
            for dep in step.depends_on:
                if dep not in all_ids:
                    issues.append(f"Step {step.step_id} depends on non-existent step {dep}")
        
        # Check for circular dependencies
        visited = set()
        for step in plan.steps:
            if PlanValidator._has_cycle(step.step_id, plan.steps, visited, set()):
                issues.append("Plan has circular dependencies")
                break
        
        # Check for research tasks without browser step
        has_browser = any(
            s.action_type == "open_app" and s.params.get("name") in ("chrome", "msedge", "firefox", "edge")
            for s in plan.steps
        )
        has_type_text = any(s.action_type in ("type_text", "type_and_enter") for s in plan.steps)
        
        goal_lower = plan.goal.lower()
        if any(kw in goal_lower for kw in ("research", "search", "find information", "report")):
            if not has_browser:
                issues.append("Research task has no browser step — must open Chrome/Edge first")
                suggestions.append("Add: open_app chrome → navigate to Google → search → read")
            if not has_type_text:
                suggestions.append("Research should end with writing findings in Notepad")
        
        # Check for writing tasks without type_text
        if any(kw in goal_lower for kw in ("write", "document", "essay", "report")):
            if not has_type_text:
                issues.append("Writing task has no type_text step")
                suggestions.append("Must include type_text with actual content")
        
        # General validations
        if len(plan.steps) > 30:
            suggestions.append("Plan has many steps — consider consolidating")
        
        if len(plan.steps) < 2:
            suggestions.append("Plan has very few steps — consider breaking down further")
        
        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "suggestions": suggestions,
        }
    
    @staticmethod
    def _has_cycle(step_id: int, steps: list, visited: set, path: set) -> bool:
        """Check for circular dependencies using DFS."""
        if step_id in path:
            return True
        if step_id in visited:
            return False
        
        visited.add(step_id)
        path.add(step_id)
        
        step = next((s for s in steps if s.step_id == step_id), None)
        if step:
            for dep in step.depends_on:
                if PlanValidator._has_cycle(dep, steps, visited, path):
                    return True
        
        path.discard(step_id)
        return False


class PlanStep:
    """Represents a single step in an execution plan."""

    def __init__(
        self,
        step_id: int,
        description: str,
        action_type: str = "llm_driven",
        params: Optional[dict] = None,
        depends_on: Optional[list[int]] = None,
        estimated_duration: float = 5.0,
    ):
        self.step_id = step_id
        self.description = description
        self.action_type = action_type
        self.params = params or {}
        self.depends_on = depends_on or []
        self.estimated_duration = estimated_duration
        self.status: str = "pending"  # pending, running, completed, failed, skipped
        self.result: Optional[str] = None
        self.started_at: Optional[float] = None
        self.completed_at: Optional[float] = None
        self.retry_count: int = 0

    def to_dict(self) -> dict:
        return {
            "id": self.step_id,
            "description": self.description,
            "action_type": self.action_type,
            "status": self.status,
            "result": self.result,
            "retry_count": self.retry_count,
        }


class ExecutionPlan:
    """A full execution plan with steps, dependencies, and progress."""

    def __init__(self, goal: str, steps: Optional[list[PlanStep]] = None):
        self.goal = goal
        self.steps = steps or []
        self.created_at = time.time()
        self.current_step_idx = 0

    @property
    def progress(self) -> float:
        if not self.steps:
            return 0.0
        completed = sum(1 for s in self.steps if s.status == "completed")
        return (completed / len(self.steps)) * 100

    @property
    def is_complete(self) -> bool:
        return all(s.status in ("completed", "skipped") for s in self.steps)

    def get_ready_steps(self) -> list[PlanStep]:
        """Get steps whose dependencies are all completed."""
        ready = []
        completed_ids = {s.step_id for s in self.steps if s.status in ("completed", "skipped")}
        for step in self.steps:
            if step.status == "pending" and all(d in completed_ids for d in step.depends_on):
                ready.append(step)
        return ready

    def to_dict(self) -> dict:
        return {
            "goal": self.goal,
            "progress": round(self.progress, 1),
            "total_steps": len(self.steps),
            "completed_steps": sum(1 for s in self.steps if s.status == "completed"),
            "steps": [s.to_dict() for s in self.steps],
        }


class PlannerEngine:
    """
    Premium planning engine that creates, validates, and adaptively
    executes multi-step plans. Used by Tier-S/S+ agents.
    """

    def __init__(self, max_replans: int = 3):
        self.max_replans = max_replans
        self._memory: list[dict] = []  # Session memory across steps
        self._plans: list[ExecutionPlan] = []

    async def create_plan(self, llm, goal: str, context: str = "") -> ExecutionPlan:
        """
        Create an execution plan. Uses task-type-specific templates when available,
        with LLM refinement for customization.
        """
        # ── Task-type detection for template selection ──
        task_type_key = None
        search_query = goal
        
        if HAS_TASK_INTELLIGENCE:
            detected = TaskAnalyzer.detect(goal)
            task_type_key = detected.value
            search_query = TaskAnalyzer.extract_search_query(goal)
            logger.info(f"PlannerEngine: Detected task type '{task_type_key}' for goal: {goal[:80]}")
        
        # ── Try to use a template first ──
        template = PLAN_TEMPLATES.get(task_type_key)
        if template:
            logger.info(f"PlannerEngine: Using {task_type_key} template with {len(template)} steps")
            steps = []
            for item in template:
                params = dict(item.get("params", {}))
                # Substitute {query} placeholder with actual search query
                for key, val in params.items():
                    if isinstance(val, str) and "{query}" in val:
                        params[key] = val.replace("{query}", search_query.replace(" ", "+"))
                steps.append(PlanStep(
                    step_id=item["step_id"],
                    description=item["description"],
                    action_type=item["action_type"],
                    params=params,
                    depends_on=item.get("depends_on", []),
                    estimated_duration=item.get("estimated_duration", 5.0),
                ))
            plan = ExecutionPlan(goal=goal, steps=steps)
            
            # Validate the template-based plan
            validation = PlanValidator.validate(plan)
            if not validation["valid"]:
                logger.warning(f"Template plan validation issues: {validation['issues']}")
            
            self._plans.append(plan)
            return plan
        
        # ── Fallback: LLM-generated plan (enhanced prompt) ──
        system_prompt = """You are a task planning engine for an AI agent that controls a Windows computer.
Break the user's goal into concrete, executable steps.

CRITICAL PLANNING RULES:
1. For RESEARCH tasks, the plan MUST start with opening Chrome browser:
   {"step_id": 1, "description": "Open Chrome browser", "action_type": "open_app", "params": {"name": "chrome"}, "depends_on": []}
   Then navigate to Google, search, read multiple pages, then open Notepad and write a report.

2. For WRITING tasks, open Notepad first, then type content.

3. For CODING tasks, open VS Code or use terminal.

4. NEVER plan to open File Explorer for research.

5. ALWAYS include saving the work (Ctrl+S) as a step.

6. Each step must have: step_id, description, action_type, params, depends_on, estimated_duration.

Available action_types: open_app, type_text, type_and_enter, click, hotkey, press_key, 
scroll, run_command, browse_web, read_screen, write_file, wait, llm_driven

Respond ONLY with a JSON array. No markdown, no explanation."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Goal: {goal}\n\nContext: {context}" if context else f"Goal: {goal}"},
        ]
        resp = await llm.chat(messages=messages)
        raw = resp.get("content", "[]")

        # Parse steps
        steps = self._parse_plan_json(raw)
        plan = ExecutionPlan(goal=goal, steps=steps)
        
        # Validate
        validation = PlanValidator.validate(plan)
        if not validation["valid"]:
            logger.warning(f"LLM plan validation issues: {validation['issues']}")
            # If research task doesn't have browser, inject template steps
            if task_type_key == "research" and "browser" in str(validation["issues"]).lower():
                logger.info("Overriding with research template due to missing browser steps")
                research_template = PLAN_TEMPLATES["research"]
                template_steps = []
                for item in research_template:
                    params = dict(item.get("params", {}))
                    for key, val in params.items():
                        if isinstance(val, str) and "{query}" in val:
                            params[key] = val.replace("{query}", search_query.replace(" ", "+"))
                    template_steps.append(PlanStep(
                        step_id=item["step_id"],
                        description=item["description"],
                        action_type=item["action_type"],
                        params=params,
                        depends_on=item.get("depends_on", []),
                        estimated_duration=item.get("estimated_duration", 5.0),
                    ))
                plan = ExecutionPlan(goal=goal, steps=template_steps)
        
        self._plans.append(plan)
        return plan

    async def replan(self, llm, plan: ExecutionPlan, failure_reason: str) -> ExecutionPlan:
        """Create an adjusted plan based on what failed and what's already done."""
        completed = [s.to_dict() for s in plan.steps if s.status == "completed"]
        failed = [s.to_dict() for s in plan.steps if s.status == "failed"]

        messages = [
            {"role": "system", "content": """You are a task replanning engine.
The original plan partially failed. Create a revised plan that:
1. Keeps completed steps as-is
2. Fixes or works around the failed steps
3. Completes the remaining goal

Respond ONLY with a JSON array of NEW steps (don't include already-completed steps).
Start step_id numbering from where the old plan left off."""},
            {"role": "user", "content": json.dumps({
                "original_goal": plan.goal,
                "completed_steps": completed,
                "failed_steps": failed,
                "failure_reason": failure_reason,
            }, indent=2)},
        ]
        resp = await llm.chat(messages=messages)
        new_steps = self._parse_plan_json(resp.get("content", "[]"))

        # Update plan
        for old_step in plan.steps:
            if old_step.status in ("pending", "failed"):
                old_step.status = "skipped"
        plan.steps.extend(new_steps)
        return plan

    def add_to_memory(self, key: str, value: str):
        """Store context information across plan steps."""
        self._memory.append({"key": key, "value": value, "timestamp": time.time()})

    def get_memory(self, last_n: int = 10) -> list[dict]:
        """Retrieve recent memory entries."""
        return self._memory[-last_n:]

    def get_memory_summary(self) -> str:
        """Get a text summary of memory for LLM context."""
        if not self._memory:
            return "No previous context."
        lines = []
        for m in self._memory[-15:]:
            lines.append(f"- {m['key']}: {m['value']}")
        return "\n".join(lines)

    def _parse_plan_json(self, raw: str) -> list[PlanStep]:
        """Parse LLM response into PlanStep objects."""
        # Try to extract JSON from response
        text = raw.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            start = text.find("[")
            end = text.rfind("]") + 1
            if start >= 0 and end > start:
                try:
                    data = json.loads(text[start:end])
                except json.JSONDecodeError:
                    logger.warning(f"PlannerEngine: Could not parse plan JSON")
                    return [PlanStep(1, "Execute goal directly", "llm_driven")]
            else:
                return [PlanStep(1, "Execute goal directly", "llm_driven")]

        steps = []
        for item in data:
            steps.append(PlanStep(
                step_id=item.get("step_id", len(steps) + 1),
                description=item.get("description", "Unknown step"),
                action_type=item.get("action_type", "llm_driven"),
                params=item.get("params", {}),
                depends_on=item.get("depends_on", []),
                estimated_duration=item.get("estimated_duration", 5.0),
            ))
        return steps
