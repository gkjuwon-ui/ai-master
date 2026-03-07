"""
telepathy_train.py — Telepathy v2 Training Pipeline

5-Phase Curriculum:
  Phase 0: SES Alignment      (contrastive learning, 2K episodes)
  Phase 1: Simple 1:1 Telepathy (sender→receiver task completion, 5K episodes)
  Phase 2: Multi-Agent Relay   (A→B→C chains, 8K episodes)
  Phase 3: Cross-Model         (Qwen→Llama, Llama→Qwen, 5K episodes)
  Phase 4: Emergent Composition (SES arithmetic, 3K episodes)

v1 difference:
  Old: autoregressive token generation + token budget + MAPPO
  New: projection + SES + contrastive/RL hybrid

Usage:
  trainer = TelepathyTrainer(config)
  trainer.setup()
  trainer.train()
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, TYPE_CHECKING

import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingWarmRestarts

from ogenti_core.telepathy import (
    TelepathyConfig,
    TELEPATHY_CONFIG,
    TextProjector,
    VisionProjector,
    InjectionHead,
    TelepathyMessage,
    TelepathyChannel,
    Intent,
    Modality,
    vicreg_loss,
    uniformity_loss,
    contrastive_loss,
    compute_effective_dimensionality,
)
from ogenti_core.telepathy_adapter import (
    TelepathyAdapter,
    TelepathyAdapterConfig,
    SESCalibration,
)
from ogenti_train.telepathy_rewards import (
    TelepathyRewardConfig,
    TelepathyRewardFunction,
    reward_task_success,
)
from ogenti_train.environment import OgentiEnvironment, TaskGenerator
from ogenti_train.curriculum import PhaseConfig, PhaseMetrics, CurriculumScheduler

if TYPE_CHECKING:
    from ogenti_train.server import TrainerBridge

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
#                  TRAINING CONFIGURATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class TelepathyPhase:
    """Configuration for a single training phase."""
    phase_id: int
    name: str
    episodes: int
    lr: float = 1e-4
    batch_size: int = 32
    description: str = ""
    use_contrastive: bool = False  # Phase 0 only
    use_rl: bool = False          # Phase 1+
    multi_agent: bool = False     # Phase 2+
    cross_model: bool = False     # Phase 3+
    composability: bool = False   # Phase 4+
    noise_std: float = 0.0       # Noise injection during training


TELEPATHY_PHASES = [
    TelepathyPhase(
        phase_id=0,
        name="SES Alignment",
        episodes=2000,
        lr=3e-4,
        batch_size=64,
        use_contrastive=True,
        description="Align SES space with contrastive learning (InfoNCE). "
                    "Pair same-meaning texts, push different meanings apart.",
    ),
    TelepathyPhase(
        phase_id=1,
        name="Simple 1:1 Telepathy",
        episodes=5000,
        lr=1e-4,
        batch_size=32,
        use_rl=True,
        noise_std=0.005,
        description="Train sender→receiver pairs on task completion. "
                    "Sender projects, receiver injects and generates.",
    ),
    TelepathyPhase(
        phase_id=2,
        name="Multi-Agent Relay",
        episodes=8000,
        lr=5e-5,
        batch_size=16,
        use_rl=True,
        multi_agent=True,
        noise_std=0.01,
        description="A→B→C relay chains. Tests SES stability over hops. "
                    "Each agent re-projects from their own hidden space.",
    ),
    TelepathyPhase(
        phase_id=3,
        name="Cross-Model Transfer",
        episodes=5000,
        lr=3e-5,
        batch_size=16,
        use_rl=True,
        cross_model=True,
        noise_std=0.01,
        description="Qwen sends, Llama receives (and vice versa). "
                    "Tests SES universality across model families.",
    ),
    TelepathyPhase(
        phase_id=4,
        name="Emergent Composition",
        episodes=3000,
        lr=1e-5,
        batch_size=16,
        use_rl=True,
        composability=True,
        noise_std=0.01,
        description="Test SES arithmetic: vec(A) + vec(B) ≈ vec(A∧B). "
                    "Freeform composition and interpolation.",
    ),
]


@dataclass
class TelepathyTrainConfig:
    """Top-level config for telepathy training."""
    # Core
    telepathy: TelepathyConfig = field(default_factory=TelepathyConfig)
    reward: TelepathyRewardConfig = field(default_factory=TelepathyRewardConfig)
    adapter: TelepathyAdapterConfig = field(default_factory=TelepathyAdapterConfig)
    phases: list = field(default_factory=lambda: TELEPATHY_PHASES)

    # Model
    model_name: str = "Qwen/Qwen2.5-3B-Instruct"
    cross_model_name: str = ""  # For Phase 3 (e.g. "meta-llama/Llama-3.2-3B-Instruct")

    # Infrastructure
    seed: int = 42
    checkpoint_dir: str = "./checkpoints/telepathy_v2"
    log_every: int = 10
    checkpoint_every: int = 500
    eval_every: int = 100

    # Dataset
    dataset_path: str = ""
    dataset_tasks: int = 1000

    @property
    def total_episodes(self) -> int:
        return sum(p.episodes for p in self.phases)


# ═══════════════════════════════════════════════════════════════
#                  TELEPATHY TRAINER
# ═══════════════════════════════════════════════════════════════

class TelepathyTrainer:
    """Main training loop for Telepathy v2.

    v1 OgentiTrainer flow:
      encode(text → tokens) → channel → decode(tokens → text) → reward → PPO

    v2 TelepathyTrainer flow:
      Phase 0: project(text → SES) ↔ project(text' → SES) → InfoNCE loss
      Phase 1+: project(text → SES) → inject(SES → virtual_tokens) → generate → reward
    """

    def __init__(
        self,
        config: Optional[TelepathyTrainConfig] = None,
        bridge: Optional["TrainerBridge"] = None,
    ):
        self.config = config or TelepathyTrainConfig()
        self.bridge = bridge
        self.device = self._resolve_device()

        # Components (initialized in setup())
        self.adapter: Optional[TelepathyAdapter] = None
        self.environment: Optional[OgentiEnvironment] = None
        self.channel: Optional[TelepathyChannel] = None
        self.reward_fn: Optional[TelepathyRewardFunction] = None
        self.optimizer: Optional[AdamW] = None
        self.lr_scheduler = None

        # Models (loaded in setup())
        self._sender_model = None
        self._sender_tokenizer = None
        self._receiver_model = None
        self._receiver_tokenizer = None

        # Cross-model (Phase 3)
        self._cross_model = None
        self._cross_tokenizer = None

        # State
        self.global_episode = 0
        self.current_phase_idx = 0
        self.best_reward = float("-inf")
        self._all_ses_vectors: list[torch.Tensor] = []

    def _resolve_device(self) -> str:
        if torch.cuda.is_available():
            return "cuda"
        return "cpu"

    # ── Setup ──────────────────────────────────────────────────

    def setup(self) -> None:
        """Initialize all training components."""
        cfg = self.config
        self._set_seed(cfg.seed)

        logger.info("═══ Telepathy v2 Training Setup ═══")
        logger.info("Device: %s", self.device)
        logger.info("Total episodes: %d across %d phases", cfg.total_episodes, len(cfg.phases))

        if self.bridge:
            self.bridge.on_training_start({
                "version": "telepathy_v2",
                "total_episodes": cfg.total_episodes,
                "phases": [{"id": p.phase_id, "name": p.name, "episodes": p.episodes} for p in cfg.phases],
            })

        # 1. Load models
        logger.info("Loading sender/receiver model: %s", cfg.model_name)
        self._sender_model, self._sender_tokenizer = self._load_model(cfg.model_name)
        # For Phase 0-2, sender and receiver share the same base model
        self._receiver_model = self._sender_model
        self._receiver_tokenizer = self._sender_tokenizer

        # Detect hidden size
        hidden_size = self._sender_model.config.hidden_size
        logger.info("Model hidden size: %d", hidden_size)

        # 2. Build adapter
        self.adapter = TelepathyAdapter(
            config=TelepathyAdapterConfig(
                ses_dim=cfg.telepathy.ses_dim,
                n_virtual_tokens=cfg.telepathy.n_virtual_tokens,
                num_intents=cfg.telepathy.num_intents,
                trained_on=cfg.model_name,
                has_vision=True,
            ),
            use_adaptive=True,
        )
        self.adapter = self.adapter.to(self.device)
        logger.info("Adapter: %s", self.adapter)
        logger.info("Adapter params: %s", self.adapter.param_count())

        # 3. Environment + reward
        self.environment = OgentiEnvironment(
            generator=TaskGenerator(dataset_path=cfg.dataset_path or None),
        )
        self.reward_fn = TelepathyRewardFunction(cfg.reward)
        self.channel = TelepathyChannel(
            config=cfg.telepathy,
            noise_std=0.0,  # Set per-phase
        )

        # 4. Optimizer (for adapter parameters only — base model is frozen)
        self.optimizer = AdamW(
            self.adapter.parameters(),
            lr=cfg.phases[0].lr,
            weight_decay=0.01,
        )
        self.lr_scheduler = CosineAnnealingWarmRestarts(
            self.optimizer, T_0=cfg.phases[0].episodes, T_mult=2,
        )

        logger.info("═══ Setup complete ═══")

    def _load_model(self, model_name: str):
        """Load a HuggingFace model (frozen) for training."""
        from transformers import AutoModelForCausalLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            trust_remote_code=True,
        ).to(self.device)

        # Freeze base model — only adapter weights are trainable
        for param in model.parameters():
            param.requires_grad = False

        return model, tokenizer

    def _set_seed(self, seed: int):
        import random
        import numpy as np
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)

    # ── Main Training Loop ─────────────────────────────────────

    def train(self) -> None:
        """Run the full 5-phase training loop."""
        cfg = self.config
        logger.info("═══ Telepathy v2 Training started ═══")
        start_time = time.time()

        for phase_idx, phase in enumerate(cfg.phases):
            self.current_phase_idx = phase_idx
            logger.info(
                "\n╔══ Phase %d: %s (%d episodes) ══╗\n%s",
                phase.phase_id, phase.name, phase.episodes, phase.description,
            )

            # Update optimizer LR for this phase
            for pg in self.optimizer.param_groups:
                pg["lr"] = phase.lr

            # Update channel noise
            self.channel.noise_std = phase.noise_std

            # Phase 3: load cross-model if configured
            if phase.cross_model and cfg.cross_model_name and self._cross_model is None:
                logger.info("Loading cross-model: %s", cfg.cross_model_name)
                self._cross_model, self._cross_tokenizer = self._load_model(cfg.cross_model_name)

            phase_start = self.global_episode
            phase_rewards = []

            for ep in range(phase.episodes):
                if phase.use_contrastive:
                    metrics = self._run_contrastive_episode(phase)
                elif phase.multi_agent:
                    metrics = self._run_relay_episode(phase)
                elif phase.cross_model and self._cross_model is not None:
                    metrics = self._run_cross_model_episode(phase)
                elif phase.composability:
                    metrics = self._run_composition_episode(phase)
                else:
                    metrics = self._run_telepathy_episode(phase)

                phase_rewards.append(metrics.get("total_reward", 0.0))

                # Dashboard
                if self.bridge:
                    metrics["phase"] = phase.phase_id
                    metrics["phase_name"] = phase.name
                    self.bridge.on_episode(metrics)

                    while self.bridge.status == "paused":
                        time.sleep(0.5)

                # Logging
                if self.global_episode % cfg.log_every == 0:
                    self._log_metrics(metrics)

                # Checkpoint
                if self.global_episode % cfg.checkpoint_every == 0 and self.global_episode > 0:
                    self._save_checkpoint()

                self.global_episode += 1

            # Phase summary
            avg_reward = sum(phase_rewards) / max(len(phase_rewards), 1)
            logger.info(
                "╚══ Phase %d complete: avg_reward=%.4f, episodes=%d ══╝",
                phase.phase_id, avg_reward, len(phase_rewards),
            )

        # ── Final ──
        elapsed = time.time() - start_time
        logger.info(
            "═══ Telepathy v2 Training complete ═══\n"
            "Episodes: %d | Time: %.1f min | Best reward: %.4f",
            self.global_episode, elapsed / 60, self.best_reward,
        )

        # Compute calibration from collected SES vectors
        if self._all_ses_vectors:
            all_vecs = torch.cat(self._all_ses_vectors[-1000:], dim=0)
            self.adapter.calibration = SESCalibration.from_vectors(all_vecs)
            eff_dim = compute_effective_dimensionality(all_vecs)
            self.adapter.calibration.effective_dim = eff_dim
            logger.info("SES calibration: effective_dim=%.3f, n_samples=%d", eff_dim, all_vecs.size(0))

        # Save final adapter
        self.adapter.config.training_episodes = self.global_episode
        self._save_checkpoint(tag="final")
        self._export_adapter()

        if self.bridge:
            self.bridge.on_training_end({
                "total_episodes": self.global_episode,
                "elapsed_min": round(elapsed / 60, 2),
                "best_reward": round(self.best_reward, 4),
                "final_phase": self.current_phase_idx,
            })

    # ── Phase 0: Contrastive Alignment ─────────────────────────

    def _run_contrastive_episode(self, phase: TelepathyPhase) -> dict:
        """Phase 0: Train SES alignment via InfoNCE contrastive loss.

        Pair strategy: same task → two different phrasings → should map close in SES.
        Different tasks → should map far apart.
        """
        self.adapter.train()
        task_a = self.environment.reset()
        # Generate a paired view (paraphrase via rephrasing)
        task_b = self.environment.reset()

        # Get hidden states from the model
        hidden_a = self._get_hidden_states(task_a.instruction)
        hidden_b = self._get_hidden_states(task_b.instruction if task_b != task_a else task_a.reference)

        # Project to SES
        ses_a, intent_a = self.adapter.project_for_training(hidden_a)
        ses_b, intent_b = self.adapter.project_for_training(hidden_b)

        # Contrastive loss (InfoNCE)
        # In a batch: diagonal = matching pairs, off-diagonal = negatives
        loss = contrastive_loss(ses_a, ses_b, tau=self.config.telepathy.contrastive_tau)

        # Add VICReg regularization to prevent collapse
        vic_loss = vicreg_loss(ses_a, ses_b, self.config.telepathy)
        total_loss = loss + 0.1 * vic_loss

        # Backward
        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.adapter.parameters(), 1.0)
        self.optimizer.step()
        self.lr_scheduler.step()

        # Track
        self._all_ses_vectors.append(ses_a.detach())

        cos_sim = F.cosine_similarity(ses_a, ses_b).mean().item()

        return {
            "total_reward": -total_loss.item(),
            "contrastive_loss": loss.item(),
            "vicreg_loss": vic_loss.item(),
            "cosine_similarity": cos_sim,
            "episode": self.global_episode,
            "phase": 0,
        }

    # ── Phase 1: Simple Telepathy ──────────────────────────────

    def _run_telepathy_episode(self, phase: TelepathyPhase) -> dict:
        """Phase 1: Sender projects → SES → Receiver injects and generates.

        This is the core telepathy episode:
        1. Sample task
        2. Sender: text → hidden → TextProjector → SES vector
        3. Channel: transmit SES (with noise)
        4. Receiver: SES → InjectionHead → virtual tokens → generate
        5. Reward: compare receiver output to reference
        """
        self.adapter.train()
        task = self.environment.reset()

        # ── Sender side ──
        hidden = self._get_hidden_states(task.instruction)
        ses_vector, intent_logits = self.adapter.project_for_training(hidden)
        predicted_intent = intent_logits.argmax(dim=-1).item()

        # Add noise for robustness
        if phase.noise_std > 0:
            noise = torch.randn_like(ses_vector) * phase.noise_std
            ses_noisy = F.normalize(ses_vector + noise, dim=-1)
        else:
            ses_noisy = ses_vector

        # ── Receiver side ──
        virtual_tokens = self.adapter.inject_for_training(ses_noisy)

        # Generate from virtual tokens
        with torch.no_grad():
            output_ids = self._receiver_model.generate(
                inputs_embeds=virtual_tokens.half(),
                max_new_tokens=128,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self._receiver_tokenizer.eos_token_id,
            )
        receiver_output = self._receiver_tokenizer.decode(output_ids[0], skip_special_tokens=True)

        # ── Intent label (heuristic) ──
        true_intent = self._classify_task_intent(task.instruction)

        # ── Create message for size calculation ──
        msg = TelepathyMessage.from_tensor(ses_vector.squeeze(0))

        # ── Reward ──
        reward_info = self.reward_fn.compute(
            receiver_output=receiver_output,
            reference=task.reference,
            predicted_intent=predicted_intent,
            true_intent=true_intent,
            message_bytes=msg.size_bytes,
            baseline_tokens=len(self._sender_tokenizer.encode(task.instruction)),
            ses_vectors_a=ses_vector,
            ses_vectors_b=ses_noisy,
        )

        # ── Training loss ──
        # Combine:
        # 1. Intent classification loss (supervised)
        intent_target = torch.tensor([true_intent], device=self.device)
        intent_loss = F.cross_entropy(intent_logits, intent_target)

        # 2. Reconstruction loss via reward signal (REINFORCE-style)
        # We treat the total reward as the signal for the projector
        reward_val = reward_info["total_reward"]
        reinforce_loss = -reward_val * ses_vector.mean()  # Scale gradient by reward

        # 3. Anti-collapse regularization
        vic_loss = vicreg_loss(ses_vector, ses_noisy, self.config.telepathy)

        total_loss = intent_loss + 0.5 * reinforce_loss + 0.1 * vic_loss

        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.adapter.parameters(), 1.0)
        self.optimizer.step()
        self.lr_scheduler.step()

        # Track
        self._all_ses_vectors.append(ses_vector.detach())
        if reward_val > self.best_reward:
            self.best_reward = reward_val

        return {
            "total_reward": reward_val,
            "task_success": reward_info["components"]["task_success"],
            "intent_match": reward_info["components"]["intent_match"],
            "intent_loss": intent_loss.item(),
            "receiver_output_len": len(receiver_output),
            "ses_norm": ses_vector.norm().item(),
            "episode": self.global_episode,
            "phase": phase.phase_id,
            "task_category": task.category.value,
        }

    # ── Phase 2: Multi-Agent Relay ─────────────────────────────

    def _run_relay_episode(self, phase: TelepathyPhase) -> dict:
        """Phase 2: A→B→C relay. Tests SES stability over multiple hops.

        Flow:
        1. Agent A encodes task → SES_a
        2. Agent B receives SES_a, re-encodes → SES_b
        3. Agent C receives SES_b, generates final output
        4. Reward based on how well C's output matches A's reference
        """
        self.adapter.train()
        task = self.environment.reset()

        # Hop 1: A → SES
        hidden_a = self._get_hidden_states(task.instruction)
        ses_a, _ = self.adapter.project_for_training(hidden_a)

        # Hop 2: B receives SES_a, re-encodes via inject→hidden→project
        virtual_b = self.adapter.inject_for_training(ses_a)
        # Simulate B processing: use virtual tokens as hidden states, re-project
        ses_b, _ = self.adapter.project_for_training(virtual_b.mean(dim=1, keepdim=True).expand_as(hidden_a))

        # Add channel noise between hops
        if phase.noise_std > 0:
            noise = torch.randn_like(ses_b) * phase.noise_std
            ses_b = F.normalize(ses_b + noise, dim=-1)

        # Hop 3: C receives SES_b, generates
        virtual_c = self.adapter.inject_for_training(ses_b)
        with torch.no_grad():
            output_ids = self._receiver_model.generate(
                inputs_embeds=virtual_c.half(),
                max_new_tokens=128,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self._receiver_tokenizer.eos_token_id,
            )
        final_output = self._receiver_tokenizer.decode(output_ids[0], skip_special_tokens=True)

        # Fidelity: how close is ses_b to ses_a? (should be nearly identical)
        hop_fidelity = F.cosine_similarity(ses_a, ses_b).mean().item()

        # Reward
        task_success = reward_task_success(final_output, task.reference)
        total_reward = task_success * 0.7 + hop_fidelity * 0.3

        # Loss: maximize fidelity + task success
        fidelity_loss = 1.0 - F.cosine_similarity(ses_a, ses_b).mean()
        vic_loss = vicreg_loss(ses_a, ses_b, self.config.telepathy)
        total_loss = fidelity_loss + 0.1 * vic_loss

        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.adapter.parameters(), 1.0)
        self.optimizer.step()

        self._all_ses_vectors.append(ses_a.detach())

        return {
            "total_reward": total_reward,
            "task_success": task_success,
            "hop_fidelity": hop_fidelity,
            "episode": self.global_episode,
            "phase": 2,
        }

    # ── Phase 3: Cross-Model ──────────────────────────────────

    def _run_cross_model_episode(self, phase: TelepathyPhase) -> dict:
        """Phase 3: Qwen sends, other model receives (and vice versa).

        Tests that SES is truly model-independent. The projector for
        hidden_size=2048 and hidden_size=3072 should produce compatible SES vectors.
        """
        self.adapter.train()
        task = self.environment.reset()

        # Sender: primary model
        hidden_sender = self._get_hidden_states(task.instruction)
        ses_sender, intent_logits = self.adapter.project_for_training(hidden_sender)

        # Receiver: cross-model
        # The adapter's AdaptiveProjector handles the different hidden size
        cross_hidden = self._get_hidden_states(
            task.instruction,
            model=self._cross_model,
            tokenizer=self._cross_tokenizer,
        )
        cross_hidden_size = self._cross_model.config.hidden_size

        # Inject SES into cross-model's hidden space
        old_hidden_size = self.adapter._model_hidden_size
        self.adapter._model_hidden_size = cross_hidden_size
        virtual_cross = self.adapter.inject_for_training(ses_sender)
        self.adapter._model_hidden_size = old_hidden_size

        # Generate with cross-model
        with torch.no_grad():
            output_ids = self._cross_model.generate(
                inputs_embeds=virtual_cross.half(),
                max_new_tokens=128,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self._cross_tokenizer.eos_token_id,
            )
        receiver_output = self._cross_tokenizer.decode(output_ids[0], skip_special_tokens=True)

        # Also project from cross-model to SES (should be near ses_sender)
        ses_cross, _ = self.adapter.project_for_training(cross_hidden)
        cross_fidelity = F.cosine_similarity(ses_sender, ses_cross).mean().item()

        # Reward
        task_success = reward_task_success(receiver_output, task.reference)
        total_reward = task_success + 0.3 * cross_fidelity
        if task_success > 0.5:
            total_reward += self.config.reward.cross_model_bonus

        # Loss
        cross_alignment_loss = 1.0 - F.cosine_similarity(ses_sender, ses_cross).mean()
        total_loss = cross_alignment_loss

        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.adapter.parameters(), 1.0)
        self.optimizer.step()

        return {
            "total_reward": total_reward,
            "task_success": task_success,
            "cross_fidelity": cross_fidelity,
            "is_cross_model": True,
            "episode": self.global_episode,
            "phase": 3,
        }

    # ── Phase 4: Emergent Composition ─────────────────────────

    def _run_composition_episode(self, phase: TelepathyPhase) -> dict:
        """Phase 4: Test SES vector arithmetic.

        Test: vec("translate to Korean") + vec("summarize") ≈ vec("translate and summarize to Korean")
        This tests whether SES has learned composable semantics.
        """
        self.adapter.train()

        # Sample two tasks
        task_a = self.environment.reset()
        task_b = self.environment.reset()

        # Individual SES vectors
        hidden_a = self._get_hidden_states(task_a.instruction)
        hidden_b = self._get_hidden_states(task_b.instruction)
        ses_a, _ = self.adapter.project_for_training(hidden_a)
        ses_b, _ = self.adapter.project_for_training(hidden_b)

        # Compose: (a + b) / 2, normalized
        ses_composed = F.normalize(ses_a + ses_b, dim=-1)

        # Generate from composed vector
        virtual_composed = self.adapter.inject_for_training(ses_composed)
        with torch.no_grad():
            output_ids = self._receiver_model.generate(
                inputs_embeds=virtual_composed.half(),
                max_new_tokens=128,
                do_sample=True,
                temperature=0.7,
                pad_token_id=self._receiver_tokenizer.eos_token_id,
            )
        composed_output = self._receiver_tokenizer.decode(output_ids[0], skip_special_tokens=True)

        # Check if composed output relates to BOTH tasks
        sim_a = reward_task_success(composed_output, task_a.reference)
        sim_b = reward_task_success(composed_output, task_b.reference)
        composability_score = (sim_a + sim_b) / 2

        # Also check uniformity of the SES space
        all_ses = torch.cat([ses_a, ses_b, ses_composed], dim=0)
        uni = uniformity_loss(all_ses).item()

        total_reward = composability_score

        # Loss: encourage composed vector to be equidistant from both
        dist_a = 1.0 - F.cosine_similarity(ses_composed, ses_a).mean()
        dist_b = 1.0 - F.cosine_similarity(ses_composed, ses_b).mean()
        balance_loss = (dist_a - dist_b).abs()
        vic_loss = vicreg_loss(ses_a, ses_b, self.config.telepathy)

        total_loss = balance_loss + 0.1 * vic_loss

        self.optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.adapter.parameters(), 1.0)
        self.optimizer.step()

        return {
            "total_reward": total_reward,
            "composability": composability_score,
            "sim_a": sim_a,
            "sim_b": sim_b,
            "uniformity": uni,
            "episode": self.global_episode,
            "phase": 4,
        }

    # ── Helpers ────────────────────────────────────────────────

    def _get_hidden_states(
        self,
        text: str,
        model=None,
        tokenizer=None,
    ) -> torch.Tensor:
        """Extract last-layer hidden states from a model."""
        model = model or self._sender_model
        tokenizer = tokenizer or self._sender_tokenizer

        inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        inputs = {k: v.to(self.device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = model(**inputs, output_hidden_states=True)

        # Return last layer hidden states, detached but requiring grad for adapter
        hidden = outputs.hidden_states[-1].float()
        return hidden.detach().requires_grad_(True)

    def _classify_task_intent(self, instruction: str) -> int:
        """Heuristic intent classification for training labels."""
        lower = instruction.lower()
        if any(w in lower for w in ["what", "how", "why", "when", "where", "explain", "describe"]):
            return Intent.QUERY
        if any(w in lower for w in ["summarize", "translate", "write", "generate", "create"]):
            return Intent.INSTRUCT
        if any(w in lower for w in ["result", "output", "report", "analysis"]):
            return Intent.REPORT
        return Intent.INSTRUCT  # default

    def _log_metrics(self, metrics: dict):
        phase = metrics.get("phase", "?")
        reward = metrics.get("total_reward", 0)
        extra = {k: v for k, v in metrics.items()
                 if k not in ("total_reward", "phase", "episode", "phase_name")}
        logger.info(
            "[Ep %d|P%s] reward=%.4f %s",
            self.global_episode, phase, reward,
            " ".join(f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}" for k, v in extra.items()),
        )

    # ── Checkpoint / Export ────────────────────────────────────

    def _save_checkpoint(self, tag: str = ""):
        """Save adapter checkpoint."""
        ckpt_dir = Path(self.config.checkpoint_dir)
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        save_name = f"checkpoint_ep{self.global_episode}"
        if tag:
            save_name = f"checkpoint_{tag}"
        save_path = ckpt_dir / save_name

        self.adapter.save(save_path)
        logger.info("Checkpoint saved: %s", save_path)

    def _export_adapter(self):
        """Export the final .ogt v2 adapter."""
        export_path = Path(self.config.checkpoint_dir) / "adapter_v2_final"
        self.adapter.save(export_path)
        logger.info("═══ Telepathy v2 Adapter exported to %s ═══", export_path)
        logger.info("Adapter size: %.2f MB", self.adapter.size_mb())
        logger.info("Param counts: %s", self.adapter.param_count())


# ═══════════════════════════════════════════════════════════════
#                  CLI ENTRYPOINT
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Telepathy v2 Training")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct")
    parser.add_argument("--cross-model", default="")
    parser.add_argument("--dataset", default="")
    parser.add_argument("--checkpoint-dir", default="./checkpoints/telepathy_v2")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    config = TelepathyTrainConfig(
        model_name=args.model,
        cross_model_name=args.cross_model,
        dataset_path=args.dataset,
        checkpoint_dir=args.checkpoint_dir,
        seed=args.seed,
    )

    trainer = TelepathyTrainer(config)
    trainer.setup()
    trainer.train()


if __name__ == "__main__":
    main()
