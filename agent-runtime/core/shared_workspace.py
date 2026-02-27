"""
Shared Workspace — Inter-agent knowledge and communication layer.
==================================================================

This is the REAL collaboration infrastructure. Each agent (potentially
running on a DIFFERENT LLM) can:

1. **Post findings** — discoveries, research results, partial outputs
2. **Read findings** — see what other agents have contributed
3. **Post requests** — ask other agents for help
4. **Claim tasks** — prevent duplicate work
5. **Vote/critique** — evaluate other agents' contributions

The workspace persists across the session so agents in later phases
inherit the accumulated knowledge of earlier phases.

This makes multi-brain collaboration meaningful:
- GPT-4 might find 3 sources; Claude might find 2 different ones
- Gemini might write a draft; GPT-4 might critique and improve it
- Each brain contributes its unique perspective and knowledge
"""

import asyncio
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Optional, Any
from collections import defaultdict
from loguru import logger


@dataclass
class Finding:
    """A piece of knowledge/discovery from an agent."""
    id: str
    agent_id: str
    agent_name: str
    llm_provider: str  # Which LLM produced this (e.g., "OPENAI/gpt-4o")
    category: str      # "research", "code", "design", "analysis", "observation"
    title: str
    content: str
    confidence: float = 0.8
    sources: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    upvotes: int = 0
    downvotes: int = 0
    critiques: list[dict] = field(default_factory=list)  # [{agent_id, comment, agree}]


@dataclass
class TaskClaim:
    """An agent's claim on a specific subtask."""
    task_description: str
    agent_id: str
    agent_name: str
    claimed_at: float = field(default_factory=time.time)
    status: str = "in_progress"  # in_progress, completed, abandoned
    result: str = ""


@dataclass
class AgentRequest:
    """A request from one agent to another."""
    id: str
    from_agent_id: str
    from_agent_name: str
    to_agent_id: str | None  # None = broadcast to all
    request_type: str  # "help", "review", "data", "clarification"
    content: str
    response: str = ""
    responded_by: str = ""
    status: str = "pending"  # pending, answered, expired
    timestamp: float = field(default_factory=time.time)


class SharedWorkspace:
    """
    Centralized shared workspace for multi-brain agent collaboration.

    Thread-safe via asyncio locks. Each session gets its own workspace.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._lock = asyncio.Lock()

        # Core data stores
        self.findings: list[Finding] = []
        self.task_claims: dict[str, TaskClaim] = {}  # task_hash → claim
        self.requests: list[AgentRequest] = []
        self.agent_contributions: dict[str, int] = defaultdict(int)  # agent_id → count
        self.agent_llm_labels: dict[str, str] = {}  # agent_id → "PROVIDER/model"

        # Shared scratchpad for freeform notes
        self.scratchpad: list[dict] = []  # [{agent_id, agent_name, note, timestamp}]

        # Phase handoff data
        self.phase_summaries: dict[int, str] = {}  # phase_number → summary

    # ─── Findings ───

    async def post_finding(
        self,
        agent_id: str,
        agent_name: str,
        category: str,
        title: str,
        content: str,
        confidence: float = 0.8,
        sources: list[str] | None = None,
        tags: list[str] | None = None,
    ) -> Finding:
        """Post a finding to the shared workspace."""
        finding = Finding(
            id=f"f_{len(self.findings)}_{int(time.time()*1000)}",
            agent_id=agent_id,
            agent_name=agent_name,
            llm_provider=self.agent_llm_labels.get(agent_id, "unknown"),
            category=category,
            title=title,
            content=content,
            confidence=confidence,
            sources=sources or [],
            tags=tags or [],
        )
        async with self._lock:
            self.findings.append(finding)
            self.agent_contributions[agent_id] += 1
        logger.info(f"[SharedWorkspace] {agent_name} posted finding: {title}")
        return finding

    async def get_findings(
        self,
        category: str | None = None,
        exclude_agent: str | None = None,
        min_confidence: float = 0.0,
    ) -> list[Finding]:
        """Get findings, optionally filtered."""
        async with self._lock:
            results = list(self.findings)
        if category:
            results = [f for f in results if f.category == category]
        if exclude_agent:
            results = [f for f in results if f.agent_id != exclude_agent]
        if min_confidence > 0:
            results = [f for f in results if f.confidence >= min_confidence]
        return results

    async def get_all_findings_summary(self) -> str:
        """Get a formatted summary of all findings for injection into agent prompts."""
        async with self._lock:
            if not self.findings:
                return ""
            lines = ["═══ SHARED WORKSPACE — Findings from other agents ═══"]
            for f in self.findings:
                src_info = f" (sources: {', '.join(f.sources[:3])})" if f.sources else ""
                lines.append(
                    f"[{f.agent_name} via {f.llm_provider}] ({f.category}) "
                    f"{f.title}: {f.content[:300]}{src_info}"
                )
            return "\n".join(lines)

    async def critique_finding(
        self, finding_id: str, agent_id: str, agree: bool, comment: str = ""
    ):
        """An agent critiques/votes on another agent's finding."""
        async with self._lock:
            for f in self.findings:
                if f.id == finding_id:
                    if agree:
                        f.upvotes += 1
                    else:
                        f.downvotes += 1
                    f.critiques.append({
                        "agent_id": agent_id,
                        "agree": agree,
                        "comment": comment,
                        "llm": self.agent_llm_labels.get(agent_id, "unknown"),
                    })
                    break

    # ─── Task Claims ───

    async def claim_task(self, task_desc: str, agent_id: str, agent_name: str) -> bool:
        """Claim a subtask. Returns False if already claimed by another agent."""
        task_hash = task_desc.strip().lower()[:100]
        async with self._lock:
            existing = self.task_claims.get(task_hash)
            if existing and existing.agent_id != agent_id and existing.status == "in_progress":
                return False  # Already claimed
            self.task_claims[task_hash] = TaskClaim(
                task_description=task_desc,
                agent_id=agent_id,
                agent_name=agent_name,
            )
        return True

    async def complete_task(self, task_desc: str, result: str):
        """Mark a claimed task as completed."""
        task_hash = task_desc.strip().lower()[:100]
        async with self._lock:
            claim = self.task_claims.get(task_hash)
            if claim:
                claim.status = "completed"
                claim.result = result

    async def get_claimed_tasks(self) -> list[dict]:
        """Get all task claims."""
        async with self._lock:
            return [
                {
                    "task": c.task_description,
                    "agent": c.agent_name,
                    "status": c.status,
                    "result": c.result[:200] if c.result else "",
                }
                for c in self.task_claims.values()
            ]

    # ─── Requests ───

    async def post_request(
        self,
        from_agent_id: str,
        from_agent_name: str,
        request_type: str,
        content: str,
        to_agent_id: str | None = None,
    ) -> AgentRequest:
        """Post a request for help/review/data."""
        req = AgentRequest(
            id=f"r_{len(self.requests)}",
            from_agent_id=from_agent_id,
            from_agent_name=from_agent_name,
            to_agent_id=to_agent_id,
            request_type=request_type,
            content=content,
        )
        async with self._lock:
            self.requests.append(req)
        return req

    async def get_pending_requests(self, for_agent_id: str | None = None) -> list[AgentRequest]:
        """Get pending requests, optionally for a specific agent."""
        async with self._lock:
            results = [r for r in self.requests if r.status == "pending"]
        if for_agent_id:
            results = [
                r for r in results
                if r.to_agent_id is None or r.to_agent_id == for_agent_id
            ]
        return results

    async def respond_to_request(self, request_id: str, responder_id: str, response: str):
        """Respond to a request."""
        async with self._lock:
            for r in self.requests:
                if r.id == request_id:
                    r.response = response
                    r.responded_by = responder_id
                    r.status = "answered"
                    break

    # ─── Scratchpad ───

    async def add_note(self, agent_id: str, agent_name: str, note: str):
        """Add a freeform note to the shared scratchpad."""
        async with self._lock:
            self.scratchpad.append({
                "agent_id": agent_id,
                "agent_name": agent_name,
                "llm": self.agent_llm_labels.get(agent_id, "unknown"),
                "note": note,
                "timestamp": time.time(),
            })

    # ─── Phase Management ───

    async def set_phase_summary(self, phase: int, summary: str):
        """Set the summary for a completed phase."""
        async with self._lock:
            self.phase_summaries[phase] = summary

    async def get_phase_summary(self, phase: int) -> str:
        """Get the summary for a phase."""
        async with self._lock:
            return self.phase_summaries.get(phase, "")

    # ─── Agent Registration ───

    def register_agent_llm(self, agent_id: str, provider: str, model: str):
        """Record which LLM an agent is using."""
        self.agent_llm_labels[agent_id] = f"{provider}/{model}"

    # ─── Context Injection ───

    async def get_context_for_agent(self, agent_id: str) -> str:
        """
        Build a comprehensive context string for an agent, including:
        - Findings from OTHER agents (multi-brain perspective)
        - Pending requests directed at this agent
        - Claimed tasks and their status
        - Scratchpad notes
        """
        parts = []

        # Findings from other agents
        other_findings = await self.get_findings(exclude_agent=agent_id)
        if other_findings:
            parts.append("═══ FINDINGS FROM OTHER AGENTS (different LLM brains) ═══")
            for f in other_findings[-10:]:  # Last 10
                votes = f"↑{f.upvotes} ↓{f.downvotes}" if (f.upvotes or f.downvotes) else ""
                parts.append(
                    f"• [{f.agent_name} via {f.llm_provider}] {f.title}: "
                    f"{f.content[:200]} {votes}"
                )

        # Pending requests for this agent
        pending = await self.get_pending_requests(for_agent_id=agent_id)
        if pending:
            parts.append("\n═══ PENDING REQUESTS FOR YOU ═══")
            for r in pending:
                parts.append(f"• [{r.from_agent_name}] ({r.request_type}): {r.content}")

        # Recent scratchpad notes
        async with self._lock:
            recent_notes = [
                n for n in self.scratchpad[-5:]
                if n["agent_id"] != agent_id
            ]
        if recent_notes:
            parts.append("\n═══ TEAM NOTES ═══")
            for n in recent_notes:
                parts.append(f"• [{n['agent_name']}] {n['note'][:200]}")

        return "\n".join(parts) if parts else ""

    # ─── Stats ───

    def get_stats(self) -> dict:
        return {
            "total_findings": len(self.findings),
            "total_claims": len(self.task_claims),
            "total_requests": len(self.requests),
            "agent_contributions": dict(self.agent_contributions),
            "agent_llms": dict(self.agent_llm_labels),
            "scratchpad_notes": len(self.scratchpad),
        }
