"""
environment.py — MARL Task Environment

Generates tasks for agent pairs/groups to communicate about.
Each task consists of:
  - A natural-language instruction (input to encoder)
  - A reference answer / expected action (ground truth for reward)
  - A task category (for curriculum learning)

The environment tracks episodes and interacts with the channel
to simulate multi-agent communication rounds.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Task Categories (aligned with OGENTI_SYSTEM_DESIGN.md)
# ─────────────────────────────────────────────────────────────────

class TaskCategory(str, Enum):
    """Categories of tasks that agents communicate about."""

    SUMMARIZE = "summarize"
    TRANSLATE = "translate"
    QA = "qa"
    CODE_REVIEW = "code_review"
    DATA_ANALYSIS = "data_analysis"
    CREATIVE_WRITING = "creative_writing"
    REASONING = "reasoning"
    MATH = "math"
    INSTRUCTION_FOLLOWING = "instruction_following"

    # Multi-hop (Phase 2+)
    CHAIN_SUMMARIZE = "chain_summarize"
    RELAY_TRANSLATE = "relay_translate"
    MULTI_STEP_QA = "multi_step_qa"


# Phase → allowed categories
PHASE_CATEGORIES = {
    0: [TaskCategory.SUMMARIZE, TaskCategory.TRANSLATE, TaskCategory.QA],
    1: [
        TaskCategory.SUMMARIZE,
        TaskCategory.TRANSLATE,
        TaskCategory.QA,
        TaskCategory.CODE_REVIEW,
        TaskCategory.DATA_ANALYSIS,
        TaskCategory.INSTRUCTION_FOLLOWING,
    ],
    2: [
        TaskCategory.CHAIN_SUMMARIZE,
        TaskCategory.RELAY_TRANSLATE,
        TaskCategory.MULTI_STEP_QA,
        TaskCategory.REASONING,
    ],
    3: [c for c in TaskCategory],  # All categories
}


# ─────────────────────────────────────────────────────────────────
#  Task Definition
# ─────────────────────────────────────────────────────────────────

@dataclass
class Task:
    """A single communication task."""

    task_id: str
    category: TaskCategory
    instruction: str          # NL instruction (encoder input)
    reference: str            # Expected output / ground truth
    context: str = ""         # Optional additional context
    difficulty: float = 0.5   # 0.0 (trivial) → 1.0 (hard)
    num_agents: int = 2       # How many agents involved
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "category": self.category.value,
            "instruction": self.instruction,
            "reference": self.reference,
            "context": self.context,
            "difficulty": self.difficulty,
            "num_agents": self.num_agents,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Task:
        return cls(
            task_id=d["task_id"],
            category=TaskCategory(d["category"]),
            instruction=d["instruction"],
            reference=d["reference"],
            context=d.get("context", ""),
            difficulty=d.get("difficulty", 0.5),
            num_agents=d.get("num_agents", 2),
            metadata=d.get("metadata", {}),
        )


# ─────────────────────────────────────────────────────────────────
#  Episode Result
# ─────────────────────────────────────────────────────────────────

@dataclass
class EpisodeResult:
    """Result of one complete communication episode."""

    task: Task
    encoded_tokens: int          # Protocol tokens used
    original_tokens: int         # NL tokens (pre-compression)
    decoded_text: str            # What the decoder reconstructed
    accuracy: float = 0.0        # Semantic accuracy (0-1)
    compression_ratio: float = 0.0
    reward: float = 0.0
    success: bool = False
    episode_num: int = 0


# ─────────────────────────────────────────────────────────────────
#  Task Generator
# ─────────────────────────────────────────────────────────────────

class TaskGenerator:
    """
    Generates tasks for MARL training episodes.

    Can load from a dataset file or generate synthetic tasks.
    Supports curriculum-based filtering by phase.
    """

    def __init__(
        self,
        dataset_path: Optional[str] = None,
        phase: int = 0,
        seed: int = 42,
    ):
        self.phase = phase
        self.rng = random.Random(seed)
        self._tasks: list[Task] = []
        self._task_counter = 0

        if dataset_path:
            self.load_dataset(dataset_path)
        else:
            self._tasks = self._generate_synthetic_tasks()

    def load_dataset(self, path: str) -> None:
        """Load tasks from a JSONL file."""
        with open(path) as f:
            for line in f:
                if line.strip():
                    self._tasks.append(Task.from_dict(json.loads(line)))
        logger.info("Loaded %d tasks from %s", len(self._tasks), path)

    def sample(self, n: int = 1) -> list[Task]:
        """Sample n tasks appropriate for the current phase."""
        allowed = set(PHASE_CATEGORIES.get(self.phase, list(TaskCategory)))
        eligible = [t for t in self._tasks if t.category in allowed]

        if not eligible:
            logger.warning("No eligible tasks for phase %d, using all", self.phase)
            eligible = self._tasks

        if len(eligible) < n:
            return self.rng.choices(eligible, k=n)
        return self.rng.sample(eligible, k=n)

    def sample_one(self) -> Task:
        """Sample a single task."""
        return self.sample(1)[0]

    def set_phase(self, phase: int) -> None:
        """Update the curriculum phase."""
        self.phase = phase

    def __len__(self) -> int:
        return len(self._tasks)

    # ── Synthetic Task Generation ──

    def _generate_synthetic_tasks(self) -> list[Task]:
        """
        Generate a basic set of synthetic tasks for bootstrapping
        training before real datasets are available.
        """
        tasks = []

        # --- Summarize tasks ---
        summarize_items = [
            (
                "Summarize the following: Machine learning is a subset of AI "
                "that enables systems to learn from data. It includes supervised, "
                "unsupervised, and reinforcement learning approaches.",
                "ML is a subset of AI with supervised, unsupervised, and RL approaches.",
            ),
            (
                "Summarize: The Python programming language was created by "
                "Guido van Rossum and released in 1991. It emphasizes code "
                "readability and supports multiple programming paradigms.",
                "Python, created by van Rossum in 1991, emphasizes readability "
                "and supports multiple paradigms.",
            ),
            (
                "Summarize: Neural networks are computing systems inspired by "
                "biological neural networks. They consist of interconnected nodes "
                "organized in layers that process information using connectionist approaches.",
                "Neural networks are bio-inspired computing systems with layered, "
                "interconnected nodes for information processing.",
            ),
        ]
        for i, (instr, ref) in enumerate(summarize_items):
            tasks.append(Task(
                task_id=f"syn_sum_{i}",
                category=TaskCategory.SUMMARIZE,
                instruction=instr,
                reference=ref,
                difficulty=0.3,
            ))

        # --- Translate tasks ---
        translate_items = [
            (
                "Translate to formal English: hey can u help me fix this bug its "
                "driving me crazy lol",
                "Could you assist me in resolving this defect? "
                "It has been quite frustrating.",
            ),
            (
                "Translate this technical description to simple terms: "
                "The system uses a B+ tree index with a fanout of 256 for "
                "logarithmic query complexity.",
                "The system organizes data in a tree structure that makes "
                "searching very fast.",
            ),
        ]
        for i, (instr, ref) in enumerate(translate_items):
            tasks.append(Task(
                task_id=f"syn_trans_{i}",
                category=TaskCategory.TRANSLATE,
                instruction=instr,
                reference=ref,
                difficulty=0.4,
            ))

        # --- QA tasks ---
        qa_items = [
            (
                "What is the capital of France?",
                "Paris",
            ),
            (
                "What programming language is PyTorch primarily written in?",
                "Python and C++",
            ),
            (
                "How many bits are in a byte?",
                "8",
            ),
        ]
        for i, (instr, ref) in enumerate(qa_items):
            tasks.append(Task(
                task_id=f"syn_qa_{i}",
                category=TaskCategory.QA,
                instruction=instr,
                reference=ref,
                difficulty=0.2,
            ))

        # --- Code review tasks ---
        code_review_items = [
            (
                "Review this code for bugs:\n"
                "def divide(a, b):\n    return a / b",
                "Missing division by zero check. Add: if b == 0: raise ValueError.",
            ),
        ]
        for i, (instr, ref) in enumerate(code_review_items):
            tasks.append(Task(
                task_id=f"syn_cr_{i}",
                category=TaskCategory.CODE_REVIEW,
                instruction=instr,
                reference=ref,
                difficulty=0.5,
            ))

        # --- Instruction following ---
        instruct_items = [
            (
                "List exactly 3 benefits of version control systems.",
                "1. Track changes history. 2. Enable collaboration. 3. Provide backup.",
            ),
            (
                "Write a one-sentence definition of an API.",
                "An API is a set of protocols that allows different software "
                "applications to communicate with each other.",
            ),
        ]
        for i, (instr, ref) in enumerate(instruct_items):
            tasks.append(Task(
                task_id=f"syn_inst_{i}",
                category=TaskCategory.INSTRUCTION_FOLLOWING,
                instruction=instr,
                reference=ref,
                difficulty=0.3,
            ))

        # --- Multi-hop tasks (Phase 2+) ---
        chain_items = [
            (
                "Read the document, summarize it, then translate the summary "
                "to simple English.",
                "Simple summary of the document in plain language.",
            ),
        ]
        for i, (instr, ref) in enumerate(chain_items):
            tasks.append(Task(
                task_id=f"syn_chain_{i}",
                category=TaskCategory.CHAIN_SUMMARIZE,
                instruction=instr,
                reference=ref,
                difficulty=0.7,
                num_agents=3,
            ))

        # --- Reasoning ---
        reasoning_items = [
            (
                "If all roses are flowers and some flowers fade quickly, "
                "can we conclude that some roses fade quickly?",
                "No, we cannot conclude that. Some flowers fade quickly, "
                "but those might not be roses.",
            ),
        ]
        for i, (instr, ref) in enumerate(reasoning_items):
            tasks.append(Task(
                task_id=f"syn_reason_{i}",
                category=TaskCategory.REASONING,
                instruction=instr,
                reference=ref,
                difficulty=0.8,
            ))

        logger.info("Generated %d synthetic tasks", len(tasks))
        return tasks


# ─────────────────────────────────────────────────────────────────
#  MARL Environment
# ─────────────────────────────────────────────────────────────────

class OgentiEnvironment:
    """
    The MARL training environment.

    Each step:
    1. Sample a task from the task generator
    2. Give the instruction to the encoder agent
    3. Encoder produces a protocol message
    4. Message passes through the channel
    5. Decoder agent receives and reconstructs
    6. Compare reconstruction to reference → reward

    The environment wraps this loop and provides a gym-like interface.
    """

    def __init__(
        self,
        task_generator: Optional[TaskGenerator] = None,
        phase: int = 0,
        seed: int = 42,
    ):
        self.task_gen = task_generator or TaskGenerator(phase=phase, seed=seed)
        self.phase = phase
        self.episode = 0
        self._current_task: Optional[Task] = None

    def reset(self) -> Task:
        """
        Reset the environment and sample a new task.

        Returns the task for the current episode.
        """
        self._current_task = self.task_gen.sample_one()
        return self._current_task

    @property
    def current_task(self) -> Optional[Task]:
        return self._current_task

    def step(self, decoded_text: str) -> EpisodeResult:
        """
        Evaluate the agent's decoded output against the reference.

        Parameters
        ----------
        decoded_text : str
            The decoder agent's reconstruction / output.

        Returns
        -------
        EpisodeResult
            With accuracy and compression_ratio filled in.
            Reward is computed externally by the reward module.
        """
        assert self._current_task is not None, "Call reset() first"

        result = EpisodeResult(
            task=self._current_task,
            encoded_tokens=0,   # filled by trainer
            original_tokens=0,  # filled by trainer
            decoded_text=decoded_text,
            episode_num=self.episode,
        )
        self.episode += 1
        return result

    def set_phase(self, phase: int) -> None:
        """Update phase for curriculum."""
        self.phase = phase
        self.task_gen.set_phase(phase)

    def __repr__(self) -> str:
        return (
            f"OgentiEnvironment(phase={self.phase}, "
            f"episode={self.episode}, "
            f"tasks={len(self.task_gen)})"
        )
