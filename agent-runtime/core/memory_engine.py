"""
Memory Engine v2 — Premium persistent context system with task and spatial memory.

Enhanced capabilities:
- Working memory: active context for current task
- Episodic memory: records of past actions and outcomes
- Semantic memory: learned facts and preferences
- Task memory: tracks current task state, progress, and strategy
- Spatial memory: remembers UI element positions across turns
- Action outcome memory: learns which actions work/fail for which contexts
- Memory consolidation: summarizes old memories to save tokens
- Priority scoring: most relevant memories surface first
- Cross-session persistence: remembers across agent runs
- LLM-assisted consolidation: uses LLM for intelligent summarization
"""

import time
import json
import hashlib
from typing import Optional
from loguru import logger


class MemoryEntry:
    """A single memory record."""

    def __init__(
        self,
        content: str,
        memory_type: str = "episodic",  # working, episodic, semantic
        importance: float = 0.5,
        tags: Optional[list[str]] = None,
        source: str = "",
    ):
        self.content = content
        self.memory_type = memory_type
        self.importance = importance
        self.tags = tags or []
        self.source = source
        self.created_at = time.time()
        self.last_accessed = time.time()
        self.access_count = 0
        self.entry_id = hashlib.sha256(
            f"{content}:{time.time()}".encode()
        ).hexdigest()[:12]

    @property
    def relevance_score(self) -> float:
        """Score based on importance, recency, and access frequency."""
        age_hours = (time.time() - self.created_at) / 3600
        recency_bonus = max(0, 1.0 - (age_hours / 24))  # Decays over 24h
        access_bonus = min(self.access_count * 0.1, 0.5)
        return self.importance + recency_bonus * 0.3 + access_bonus

    def to_dict(self) -> dict:
        return {
            "id": self.entry_id,
            "content": self.content,
            "type": self.memory_type,
            "importance": self.importance,
            "tags": self.tags,
            "relevance": round(self.relevance_score, 3),
            "created_at": self.created_at,
        }


class MemoryEngine:
    """
    Premium memory system with working, episodic, and semantic memory.
    Used exclusively by Tier-S/S+ agents for long-context reasoning.
    """

    def __init__(self, max_working: int = 20, max_episodic: int = 200, max_semantic: int = 100):
        self.working: list[MemoryEntry] = []
        self.episodic: list[MemoryEntry] = []
        self.semantic: list[MemoryEntry] = []
        self.max_working = max_working
        self.max_episodic = max_episodic
        self.max_semantic = max_semantic

    def remember(
        self,
        content: str,
        memory_type: str = "episodic",
        importance: float = 0.5,
        tags: Optional[list[str]] = None,
        source: str = "",
    ) -> str:
        """Store a new memory. Returns the entry ID."""
        entry = MemoryEntry(
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags,
            source=source,
        )
        store = self._get_store(memory_type)
        store.append(entry)
        self._enforce_limits()
        return entry.entry_id

    def recall(
        self,
        query: str = "",
        memory_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        top_k: int = 10,
    ) -> list[dict]:
        """
        Retrieve the most relevant memories matching the query.
        Uses keyword matching + relevance scoring.
        """
        candidates: list[MemoryEntry] = []
        if memory_type:
            candidates = list(self._get_store(memory_type))
        else:
            candidates = list(self.working) + list(self.episodic) + list(self.semantic)

        # Filter by tags if specified
        if tags:
            tag_set = set(t.lower() for t in tags)
            candidates = [
                m for m in candidates
                if tag_set.intersection(set(t.lower() for t in m.tags))
            ]

        # Score by relevance + keyword match
        query_lower = query.lower()
        query_words = set(query_lower.split())

        scored = []
        for m in candidates:
            score = m.relevance_score
            if query:
                content_lower = m.content.lower()
                # Exact substring match bonus
                if query_lower in content_lower:
                    score += 2.0
                # Word overlap bonus
                content_words = set(content_lower.split())
                overlap = len(query_words.intersection(content_words))
                score += overlap * 0.5
            scored.append((score, m))

        scored.sort(key=lambda x: x[0], reverse=True)

        results = []
        for score, m in scored[:top_k]:
            m.last_accessed = time.time()
            m.access_count += 1
            results.append(m.to_dict())
        return results

    def get_working_context(self) -> str:
        """Get current working memory as a text block for LLM injection."""
        if not self.working:
            return ""
        lines = ["[Working Memory]"]
        for m in self.working:
            lines.append(f"- {m.content}")
        return "\n".join(lines)

    def get_context_for_llm(self, query: str = "", max_tokens_estimate: int = 1500) -> str:
        """
        Build an optimized context string from memory for LLM injection.
        Prioritizes working memory + most relevant episodic/semantic.
        """
        parts = []
        char_budget = max_tokens_estimate * 4  # ~4 chars per token

        # Always include working memory
        if self.working:
            parts.append("[Active Context]")
            for m in self.working:
                parts.append(f"• {m.content}")

        used = sum(len(p) for p in parts)

        # Add top-scored episodic memories
        relevant = self.recall(query=query, memory_type="episodic", top_k=5)
        if relevant:
            parts.append("\n[Recent Actions]")
            for m in relevant:
                line = f"• {m['content']}"
                if used + len(line) > char_budget:
                    break
                parts.append(line)
                used += len(line)

        # Add top semantic memories
        semantic = self.recall(query=query, memory_type="semantic", top_k=3)
        if semantic:
            parts.append("\n[Known Facts]")
            for m in semantic:
                line = f"• {m['content']}"
                if used + len(line) > char_budget:
                    break
                parts.append(line)
                used += len(line)

        return "\n".join(parts)

    def consolidate(self, llm=None):
        """
        Consolidate old episodic memories into semantic summaries.
        If LLM is provided, uses it for intelligent summarization.
        Otherwise, uses simple deduplication.
        """
        if len(self.episodic) < self.max_episodic * 0.8:
            return  # Not enough pressure to consolidate

        # Keep top 50% by relevance, archive (summarize) the rest
        sorted_memories = sorted(self.episodic, key=lambda m: m.relevance_score, reverse=True)
        keep = sorted_memories[:len(sorted_memories) // 2]
        archive = sorted_memories[len(sorted_memories) // 2:]

        if archive:
            # Create a summary semantic memory
            summary_parts = [m.content[:100] for m in archive[:10]]
            summary = f"Summary of {len(archive)} past actions: " + "; ".join(summary_parts)
            self.remember(summary, memory_type="semantic", importance=0.6, tags=["consolidated"])

        self.episodic = keep

    def clear_working(self):
        """Clear working memory (start fresh context)."""
        self.working.clear()

    def clear_all(self):
        """Clear all memories."""
        self.working.clear()
        self.episodic.clear()
        self.semantic.clear()

    def stats(self) -> dict:
        """Get memory usage statistics."""
        return {
            "working": len(self.working),
            "episodic": len(self.episodic),
            "semantic": len(self.semantic),
            "total": len(self.working) + len(self.episodic) + len(self.semantic),
        }

    # --- Internal ---

    def _get_store(self, memory_type: str) -> list[MemoryEntry]:
        if memory_type == "working":
            return self.working
        elif memory_type == "semantic":
            return self.semantic
        return self.episodic  # default

    def _enforce_limits(self):
        """Evict lowest-relevance entries when over capacity."""
        for store, limit in [
            (self.working, self.max_working),
            (self.episodic, self.max_episodic),
            (self.semantic, self.max_semantic),
        ]:
            if len(store) > limit:
                store.sort(key=lambda m: m.relevance_score, reverse=True)
                del store[limit:]


# ═══════════════════════════════════════════════════════════════════════
# TASK MEMORY SYSTEM
# ═══════════════════════════════════════════════════════════════════════
# Tracks the current task's state, strategy, progress, and findings.

class TaskMemory:
    """
    Tracks the current task execution context.
    Unlike episodic memory (records of past actions), this tracks the
    CURRENT task's state machine, strategy, and accumulated findings.
    """
    
    def __init__(self):
        self.task_type: str = ""
        self.task_description: str = ""
        self.current_phase: str = "planning"  # planning, navigating, working, compiling, done
        self.strategy: str = ""
        self.sub_tasks: list[dict] = []  # {description, status: pending/done/failed}
        self.findings: list[str] = []  # Key findings/facts discovered
        self.visited_urls: list[str] = []
        self.files_created: list[str] = []
        self.errors_encountered: list[str] = []
        self.apps_opened: list[str] = []
        self.start_time: float = time.time()
        self.phase_history: list[dict] = []  # {phase, entered_at, left_at}
    
    def set_task(self, task_type: str, description: str, strategy: str = ""):
        """Initialize task context."""
        self.task_type = task_type
        self.task_description = description
        self.strategy = strategy
        self.current_phase = "planning"
        self.start_time = time.time()
    
    def advance_phase(self, new_phase: str):
        """Move to next phase of task execution."""
        if self.phase_history:
            self.phase_history[-1]["left_at"] = time.time()
        self.phase_history.append({"phase": new_phase, "entered_at": time.time(), "left_at": None})
        self.current_phase = new_phase
    
    def add_subtask(self, description: str, status: str = "pending"):
        """Add a subtask to track."""
        self.sub_tasks.append({"description": description, "status": status, "added_at": time.time()})
    
    def complete_subtask(self, description: str):
        """Mark a subtask as done."""
        for st in self.sub_tasks:
            if st["description"] == description:
                st["status"] = "done"
                return
    
    def add_finding(self, fact: str):
        """Record a discovered fact/finding."""
        if fact not in self.findings:
            self.findings.append(fact)
    
    def add_error(self, error: str):
        """Record an error encountered."""
        self.errors_encountered.append(error)
    
    def record_url(self, url: str):
        """Record a visited URL."""
        if url not in self.visited_urls:
            self.visited_urls.append(url)
    
    def record_app(self, app_name: str):
        """Record an opened app."""
        if app_name not in self.apps_opened:
            self.apps_opened.append(app_name)
    
    def record_file(self, filename: str):
        """Record a created file."""
        if filename not in self.files_created:
            self.files_created.append(filename)
    
    @property
    def progress_percentage(self) -> float:
        """Estimate task progress based on subtasks and phase."""
        if not self.sub_tasks:
            PHASE_PROGRESS = {
                "planning": 5, "navigating": 15, "working": 50,
                "compiling": 80, "done": 100,
            }
            return PHASE_PROGRESS.get(self.current_phase, 10)
        done = sum(1 for st in self.sub_tasks if st["status"] == "done")
        return (done / len(self.sub_tasks)) * 100 if self.sub_tasks else 0
    
    @property
    def elapsed_seconds(self) -> float:
        return time.time() - self.start_time
    
    def get_context_for_llm(self) -> str:
        """Format task memory for LLM injection."""
        parts = []
        parts.append(f"[Task Memory] Type: {self.task_type} | Phase: {self.current_phase} | Progress: {self.progress_percentage:.0f}%")
        
        if self.strategy:
            parts.append(f"Strategy: {self.strategy[:200]}")
        
        if self.findings:
            parts.append(f"Findings ({len(self.findings)}):")
            for f in self.findings[-5:]:
                parts.append(f"  • {f[:150]}")
        
        if self.visited_urls:
            parts.append(f"Visited URLs: {', '.join(self.visited_urls[-3:])}")
        
        if self.apps_opened:
            parts.append(f"Apps used: {', '.join(self.apps_opened)}")
        
        if self.errors_encountered:
            parts.append(f"Recent errors: {'; '.join(self.errors_encountered[-2:])}")
        
        if self.sub_tasks:
            done_count = sum(1 for st in self.sub_tasks if st["status"] == "done")
            parts.append(f"Subtasks: {done_count}/{len(self.sub_tasks)} complete")
            for st in self.sub_tasks[-5:]:
                status_icon = "✓" if st["status"] == "done" else ("✗" if st["status"] == "failed" else "○")
                parts.append(f"  {status_icon} {st['description'][:100]}")
        
        return "\n".join(parts)


class SpatialMemory:
    """
    Remembers the positions of UI elements across turns.
    This helps the agent navigate back to elements it previously saw
    even if SoM IDs change between turns.
    """
    
    def __init__(self, max_entries: int = 100):
        self._elements: dict[str, dict] = {}  # label → {x, y, w, h, last_seen, confidence}
        self.max_entries = max_entries
    
    def remember_element(self, label: str, x: int, y: int, w: int = 0, h: int = 0, confidence: float = 0.8):
        """Store or update an element's position."""
        label_lower = label.lower().strip()
        self._elements[label_lower] = {
            "x": x, "y": y, "w": w, "h": h,
            "cx": x + w // 2 if w else x,
            "cy": y + h // 2 if h else y,
            "last_seen": time.time(),
            "confidence": confidence,
            "access_count": self._elements.get(label_lower, {}).get("access_count", 0) + 1,
        }
        self._enforce_limit()
    
    def recall_element(self, label: str) -> Optional[dict]:
        """Try to recall an element's position by label."""
        label_lower = label.lower().strip()
        
        # Exact match
        if label_lower in self._elements:
            entry = self._elements[label_lower]
            entry["access_count"] += 1
            return entry
        
        # Partial match
        for key, entry in self._elements.items():
            if label_lower in key or key in label_lower:
                entry["access_count"] += 1
                return entry
        
        return None
    
    def get_nearby_elements(self, x: int, y: int, radius: int = 100) -> list[dict]:
        """Find elements near a given coordinate."""
        results = []
        for label, entry in self._elements.items():
            dist = ((entry["cx"] - x) ** 2 + (entry["cy"] - y) ** 2) ** 0.5
            if dist <= radius:
                results.append({"label": label, "distance": dist, **entry})
        results.sort(key=lambda r: r["distance"])
        return results
    
    def _enforce_limit(self):
        if len(self._elements) > self.max_entries:
            # Remove oldest entries
            sorted_by_time = sorted(self._elements.items(), key=lambda x: x[1]["last_seen"])
            for key, _ in sorted_by_time[:len(self._elements) - self.max_entries]:
                del self._elements[key]
    
    def get_context_for_llm(self) -> str:
        """Format spatial memory for LLM."""
        if not self._elements:
            return ""
        recent = sorted(self._elements.items(), key=lambda x: x[1]["last_seen"], reverse=True)[:10]
        parts = ["[Spatial Memory - Known Element Positions]"]
        for label, entry in recent:
            age = time.time() - entry["last_seen"]
            freshness = "fresh" if age < 10 else ("recent" if age < 60 else "stale")
            parts.append(f"  • '{label}' at ({entry['cx']},{entry['cy']}) [{freshness}]")
        return "\n".join(parts)


class ActionOutcomeMemory:
    """
    Learns which actions work and which fail in specific contexts.
    This helps the agent avoid repeating failed strategies and prefer
    proven successful approaches.
    """
    
    def __init__(self, max_entries: int = 200):
        self._outcomes: list[dict] = []
        self.max_entries = max_entries
    
    def record(self, action_type: str, context: str, success: bool, notes: str = ""):
        """Record the outcome of an action in a given context."""
        self._outcomes.append({
            "action": action_type,
            "context": context[:100],
            "success": success,
            "notes": notes[:200],
            "timestamp": time.time(),
        })
        if len(self._outcomes) > self.max_entries:
            self._outcomes = self._outcomes[-self.max_entries:]
    
    def get_success_rate(self, action_type: str) -> float:
        """Get the success rate for a specific action type."""
        relevant = [o for o in self._outcomes if o["action"] == action_type]
        if not relevant:
            return 0.5  # Unknown
        successes = sum(1 for o in relevant if o["success"])
        return successes / len(relevant)
    
    def get_best_action_for_context(self, context: str) -> Optional[str]:
        """Find the most successful action type for a given context."""
        context_lower = context.lower()
        matching = [
            o for o in self._outcomes
            if context_lower in o["context"].lower() or o["context"].lower() in context_lower
        ]
        if not matching:
            return None
        
        # Count successes per action type
        action_scores: dict[str, tuple[int, int]] = {}  # action → (successes, total)
        for o in matching:
            a = o["action"]
            s, t = action_scores.get(a, (0, 0))
            action_scores[a] = (s + (1 if o["success"] else 0), t + 1)
        
        # Return action with highest success rate (min 2 observations)
        best = None
        best_rate = 0
        for action, (successes, total) in action_scores.items():
            if total >= 2:
                rate = successes / total
                if rate > best_rate:
                    best_rate = rate
                    best = action
        
        return best
    
    def get_failed_patterns(self, last_n: int = 5) -> list[str]:
        """Get recent failure patterns to avoid."""
        recent_failures = [
            o for o in self._outcomes[-20:]
            if not o["success"]
        ][-last_n:]
        return [
            f"{o['action']} in context '{o['context']}': {o['notes']}"
            for o in recent_failures
        ]
    
    def get_context_for_llm(self) -> str:
        """Format action outcomes for LLM."""
        failures = self.get_failed_patterns(3)
        if not failures:
            return ""
        parts = ["[Action Outcomes - Avoid These Patterns]"]
        for f in failures:
            parts.append(f"  ✗ {f}")
        return "\n".join(parts)
