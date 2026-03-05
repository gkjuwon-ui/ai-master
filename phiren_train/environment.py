"""
environment.py — PHIREN Training Environment

Gym-like environment for hallucination detection MAPPO training.
Generates tasks from TruthfulQA, FEVER, HaluEval, and synthetic data.
"""

from __future__ import annotations

import json
import logging
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from pathlib import Path
from typing import Optional

from phiren_core.protocol import Claim, ClaimVerdict, VerificationMessage

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Task Categories
# ─────────────────────────────────────────────────────────────────

class TaskCategory(str, Enum):
    """Types of hallucination detection tasks."""
    SIMPLE_FACTUAL = "simple_factual"              # single verifiable fact
    MULTI_CLAIM = "multi_claim"                    # text with multiple claims
    NUMERICAL = "numerical"                        # number-heavy text
    TEMPORAL = "temporal"                          # date/time assertions
    CAUSAL = "causal"                              # cause-effect chains
    COMPARATIVE = "comparative"                    # comparison claims
    MIXED_TRUTH = "mixed_truth"                    # some true, some false
    SUBTLE_HALLUCINATION = "subtle_hallucination"  # nearly-true falsehoods
    ADVERSARIAL = "adversarial"                    # designed to trick detector
    NO_CONTEXT = "no_context"                      # unverifiable without context
    LONG_FORM = "long_form"                        # multi-paragraph text
    QA_PAIR = "qa_pair"                            # question-answer format


# Phase → which categories are used
PHASE_CATEGORIES: dict[int, list[TaskCategory]] = {
    0: [TaskCategory.SIMPLE_FACTUAL, TaskCategory.QA_PAIR],  # Warmup
    1: [TaskCategory.SIMPLE_FACTUAL, TaskCategory.MULTI_CLAIM, TaskCategory.NUMERICAL],  # Claim Extraction
    2: [  # Verification Training
        TaskCategory.SIMPLE_FACTUAL, TaskCategory.MULTI_CLAIM,
        TaskCategory.TEMPORAL, TaskCategory.CAUSAL,
        TaskCategory.MIXED_TRUTH,
    ],
    3: [  # Calibration Tuning
        TaskCategory.MIXED_TRUTH, TaskCategory.SUBTLE_HALLUCINATION,
        TaskCategory.ADVERSARIAL, TaskCategory.NO_CONTEXT,
    ],
    4: [  # Distillation — all categories
        cat for cat in TaskCategory
    ],
}


# ─────────────────────────────────────────────────────────────────
#  Task Data Structure
# ─────────────────────────────────────────────────────────────────

@dataclass
class Task:
    """A single hallucination detection task."""
    task_id: str
    text: str                                     # text to verify
    context: str                                  # reference context
    category: TaskCategory = TaskCategory.SIMPLE_FACTUAL
    ground_truth: list[dict] = field(default_factory=list)  # [{claim_text, verdict}]
    metadata: dict = field(default_factory=dict)
    source: str = "synthetic"                     # truthfulqa | fever | halueval | synthetic

    @property
    def num_claims(self) -> int:
        return len(self.ground_truth)

    @property
    def has_hallucination(self) -> bool:
        return any(
            gt.get("verdict") == "contradicted"
            for gt in self.ground_truth
        )


@dataclass
class EpisodeResult:
    """Result of running the detector on a single task."""
    task: Task
    prediction: Optional[VerificationMessage] = None
    reward: float = 0.0
    reward_components: dict = field(default_factory=dict)
    steps: int = 0
    success: bool = False  # factuality ≥ threshold

    def to_dict(self) -> dict:
        return {
            "task_id": self.task.task_id,
            "category": self.task.category.value,
            "source": self.task.source,
            "reward": round(self.reward, 4),
            "reward_components": {
                k: round(v, 4)
                for k, v in self.reward_components.items()
            },
            "steps": self.steps,
            "success": self.success,
            "num_claims": self.task.num_claims,
            "has_hallucination": self.task.has_hallucination,
        }


# ─────────────────────────────────────────────────────────────────
#  Task Generator
# ─────────────────────────────────────────────────────────────────

class TaskGenerator:
    """
    Generates hallucination detection tasks.

    Can load from JSONL files (TruthfulQA, FEVER, HaluEval) or
    generate synthetic examples.
    """

    def __init__(self):
        self._tasks: dict[str, list[Task]] = {}
        self._synthetic_templates = self._build_templates()
        self._task_counter = 0

    def load_dataset(
        self,
        source: str,
        path: str,
        max_samples: int = 10000,
    ) -> int:
        """
        Load tasks from a JSONL file.

        Expected format per line:
        {
            "text": "...",
            "context": "...",
            "claims": [{"claim_text": "...", "verdict": "supported|contradicted|unverifiable"}],
            "category": "simple_factual",
            ...
        }
        """
        filepath = Path(path)
        if not filepath.exists():
            logger.warning(f"Dataset file not found: {path}")
            return 0

        tasks = []
        with open(filepath) as f:
            for i, line in enumerate(f):
                if i >= max_samples:
                    break
                try:
                    data = json.loads(line.strip())
                    task = Task(
                        task_id=f"{source}_{i}",
                        text=data["text"],
                        context=data.get("context", ""),
                        category=TaskCategory(data.get("category", "simple_factual")),
                        ground_truth=data.get("claims", []),
                        source=source,
                        metadata=data.get("metadata", {}),
                    )
                    tasks.append(task)
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    logger.debug(f"Skipping malformed line {i} in {path}: {e}")

        self._tasks[source] = tasks
        logger.info(f"Loaded {len(tasks)} tasks from {source} ({path})")
        return len(tasks)

    def generate_synthetic(
        self,
        category: TaskCategory,
        count: int = 1,
    ) -> list[Task]:
        """Generate synthetic hallucination detection tasks."""
        tasks = []
        templates = self._synthetic_templates.get(category, [])

        for _ in range(count):
            if templates:
                template = random.choice(templates)
                task = self._fill_template(template, category)
            else:
                task = self._generate_generic(category)
            tasks.append(task)

        return tasks

    def sample(
        self,
        phase: int = 0,
        batch_size: int = 1,
        source_weights: Optional[dict[str, float]] = None,
    ) -> list[Task]:
        """
        Sample tasks appropriate for the current training phase.

        Args:
            phase: current curriculum phase (0-4)
            batch_size: number of tasks to sample
            source_weights: how much to sample from each source
        """
        allowed_categories = PHASE_CATEGORIES.get(phase, list(TaskCategory))
        tasks = []

        # Collect all eligible tasks
        pool = []
        for source, source_tasks in self._tasks.items():
            weight = 1.0
            if source_weights:
                weight = source_weights.get(source, 1.0)

            eligible = [
                t for t in source_tasks
                if t.category in allowed_categories
            ]
            # Weight by repeating
            pool.extend(eligible * max(1, int(weight * 10)))

        if not pool:
            # Fallback to synthetic
            logger.debug(f"No loaded tasks for phase {phase}, generating synthetic")
            category = random.choice(allowed_categories)
            return self.generate_synthetic(category, batch_size)

        # Sample
        if len(pool) < batch_size:
            tasks = pool * (batch_size // len(pool) + 1)
            tasks = tasks[:batch_size]
        else:
            tasks = random.sample(pool, batch_size)

        return tasks

    def _build_templates(self) -> dict[TaskCategory, list[dict]]:
        """Build synthetic task templates."""
        return {
            TaskCategory.SIMPLE_FACTUAL: [
                {
                    "text": "The capital of {country} is {wrong_capital}.",
                    "context": "The capital of {country} is {right_capital}.",
                    "claims": [
                        {"claim_text": "The capital of {country} is {wrong_capital}.", "verdict": "contradicted"}
                    ],
                    "vars": {
                        "country": ["France", "Japan", "Brazil", "Australia", "Egypt"],
                        "wrong_capital": ["London", "Beijing", "Lima", "Auckland", "Tunis"],
                        "right_capital": ["Paris", "Tokyo", "Brasília", "Canberra", "Cairo"],
                    }
                },
            ],
            TaskCategory.NUMERICAL: [
                {
                    "text": "The population of Earth is approximately {wrong_num} billion people.",
                    "context": "As of 2024, the world population is approximately 8.1 billion people.",
                    "claims": [
                        {"claim_text": "The population of Earth is approximately {wrong_num} billion people.", "verdict": "contradicted"}
                    ],
                    "vars": {
                        "wrong_num": ["5", "12", "3", "15", "20"],
                    }
                },
            ],
            TaskCategory.MIXED_TRUTH: [
                {
                    "text": "Water boils at 100°C at sea level. The sun orbits around the Earth.",
                    "context": "Water boils at 100°C at standard atmospheric pressure. The Earth orbits around the Sun.",
                    "claims": [
                        {"claim_text": "Water boils at 100°C at sea level.", "verdict": "supported"},
                        {"claim_text": "The sun orbits around the Earth.", "verdict": "contradicted"}
                    ],
                    "vars": {},
                },
            ],
        }

    def _fill_template(self, template: dict, category: TaskCategory) -> Task:
        """Fill a template with random variable choices."""
        self._task_counter += 1
        variables = template.get("vars", {})
        chosen = {}
        for var_name, options in variables.items():
            chosen[var_name] = random.choice(options)

        text = template["text"].format(**chosen)
        context = template["context"].format(**chosen)
        claims = []
        for gt in template["claims"]:
            claims.append({
                "claim_text": gt["claim_text"].format(**chosen),
                "verdict": gt["verdict"],
            })

        return Task(
            task_id=f"synthetic_{self._task_counter}",
            text=text,
            context=context,
            category=category,
            ground_truth=claims,
            source="synthetic",
        )

    def _generate_generic(self, category: TaskCategory) -> Task:
        """Generate a generic task when no template exists."""
        self._task_counter += 1
        return Task(
            task_id=f"synthetic_{self._task_counter}",
            text="This is a test statement.",
            context="Reference context for verification.",
            category=category,
            ground_truth=[
                {"claim_text": "This is a test statement.", "verdict": "supported"}
            ],
            source="synthetic",
        )

    @property
    def total_tasks(self) -> int:
        return sum(len(tasks) for tasks in self._tasks.values())

    def summary(self) -> str:
        lines = [f"TaskGenerator: {self.total_tasks} total tasks"]
        for source, tasks in self._tasks.items():
            categories = set(t.category.value for t in tasks)
            lines.append(f"  {source}: {len(tasks)} tasks ({', '.join(categories)})")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────
#  PHIREN Environment
# ─────────────────────────────────────────────────────────────────

class PhirenEnvironment:
    """
    Gym-like environment for PHIREN hallucination detection training.

    Each episode:
      1. reset() — sample a task
      2. step(action) — run detector/verifier, get reward
      3. repeat until done
    """

    def __init__(
        self,
        task_generator: TaskGenerator,
        phase: int = 0,
        max_steps: int = 5,
        success_threshold: float = 0.7,
    ):
        self.task_generator = task_generator
        self.phase = phase
        self.max_steps = max_steps
        self.success_threshold = success_threshold

        # Current episode state
        self._current_task: Optional[Task] = None
        self._step_count = 0
        self._done = False
        self._claims: list[Claim] = []

        # Episode history
        self._episode_results: list[EpisodeResult] = []

    def reset(
        self,
        task: Optional[Task] = None,
    ) -> Task:
        """Reset environment with a new task."""
        if task is None:
            tasks = self.task_generator.sample(phase=self.phase, batch_size=1)
            task = tasks[0]

        self._current_task = task
        self._step_count = 0
        self._done = False
        self._claims = []

        return task

    def step(
        self,
        prediction: VerificationMessage,
        reward_fn=None,
    ) -> tuple[EpisodeResult, bool]:
        """
        Take a step in the environment.

        Args:
            prediction: the detector's verification output
            reward_fn: RewardFunction to compute reward (optional)

        Returns:
            (EpisodeResult, done)
        """
        self._step_count += 1
        self._claims = prediction.claims

        reward = 0.0
        reward_components = {}

        if reward_fn is not None:
            reward_dict = reward_fn.compute(
                predicted=prediction.claims,
                ground_truth=self._current_task.ground_truth,
            )
            reward = reward_dict["total"]
            reward_components = reward_dict

        success = prediction.factuality_score >= self.success_threshold

        # Episode ends after max_steps or if successful
        if self._step_count >= self.max_steps or success:
            self._done = True

        result = EpisodeResult(
            task=self._current_task,
            prediction=prediction,
            reward=reward,
            reward_components=reward_components,
            steps=self._step_count,
            success=success,
        )

        if self._done:
            self._episode_results.append(result)

        return result, self._done

    def set_phase(self, phase: int) -> None:
        """Update the training phase (affects task sampling)."""
        self.phase = phase
        logger.info(f"Environment phase set to {phase}")

    @property
    def current_task(self) -> Optional[Task]:
        return self._current_task

    @property
    def is_done(self) -> bool:
        return self._done

    @property
    def episode_count(self) -> int:
        return len(self._episode_results)

    def recent_success_rate(self, window: int = 100) -> float:
        """Compute recent success rate."""
        recent = self._episode_results[-window:]
        if not recent:
            return 0.0
        return sum(1 for r in recent if r.success) / len(recent)

    def recent_avg_reward(self, window: int = 100) -> float:
        """Compute recent average reward."""
        recent = self._episode_results[-window:]
        if not recent:
            return 0.0
        return sum(r.reward for r in recent) / len(recent)

    def get_stats(self) -> dict:
        """Get environment statistics."""
        return {
            "phase": self.phase,
            "total_episodes": self.episode_count,
            "recent_success_rate": round(self.recent_success_rate(), 4),
            "recent_avg_reward": round(self.recent_avg_reward(), 4),
            "current_task": self._current_task.task_id if self._current_task else None,
        }
