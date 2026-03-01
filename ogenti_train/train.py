"""
train.py — Main MAPPO Training Loop

Orchestrates the full Ogenti training pipeline:
  1. Initialize agents (encoder + decoder with LoRA)
  2. Run curriculum phases (warmup → simple → complex → generalize)
  3. Per episode: encode → channel → decode → reward → PPO update
  4. Log metrics, save checkpoints, manage phase transitions

Usage
-----
  python -m ogenti_train.train --config config.json
  python -m ogenti_train.train  # uses defaults
"""

from __future__ import annotations

import argparse
import logging
import math
import os
import sys
import time
from pathlib import Path
from typing import Optional

import torch
import torch.nn.functional as F
from torch.optim import AdamW
from torch.optim.lr_scheduler import CosineAnnealingLR, LinearLR

from ogenti_core.protocol import ProtocolConfig, ProtocolMessage
from ogenti_core.encoder import OgentiEncoder, EncoderConfig
from ogenti_core.decoder import OgentiDecoder, DecoderConfig
from ogenti_core.channel import CommunicationChannel

from ogenti_train.config import TrainConfig, InfraConfig
from ogenti_train.environment import OgentiEnvironment, TaskGenerator, EpisodeResult
from ogenti_train.agents import (
    AgentPool, EncoderAgent, DecoderAgent, ValueHead,
    AgentConfig, RolloutEntry,
)
from ogenti_train.rewards import RewardFunction, RewardConfig
from ogenti_train.curriculum import CurriculumScheduler, PhaseConfig
from ogenti_core.adapter import (
    OgentiAdapter, AdapterConfig,
    ProtocolVocab, ProtocolVocabEntry,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Trainer
# ─────────────────────────────────────────────────────────────────

class OgentiTrainer:
    """
    Main MAPPO training loop for the Ogenti protocol.

    Lifecycle:
      trainer = OgentiTrainer(config)
      trainer.setup()
      trainer.train()
      trainer.save()
    """

    def __init__(self, config: Optional[TrainConfig] = None):
        self.config = config or TrainConfig()
        self.device = self._resolve_device()

        # Components (initialized in setup())
        self.agent_pool: Optional[AgentPool] = None
        self.environment: Optional[OgentiEnvironment] = None
        self.channel: Optional[CommunicationChannel] = None
        self.reward_fn: Optional[RewardFunction] = None
        self.scheduler: Optional[CurriculumScheduler] = None
        self.optimizer: Optional[AdamW] = None
        self.lr_scheduler = None

        # Phase 4 universal adapter (initialized on phase transition)
        self.adapter: Optional[OgentiAdapter] = None
        self.adapter_optimizer: Optional[AdamW] = None

        # State
        self.global_episode = 0
        self.best_reward = float("-inf")
        self._metrics_log: list[dict] = []

    # ── Setup ──

    def setup(self) -> None:
        """Initialize all components."""
        cfg = self.config
        logger.info("\n%s", cfg.summary())

        self._set_seed(cfg.infra.seed)

        # 1. Agent pool
        logger.info("Building agent pool...")
        self.agent_pool = AgentPool.build_pair(protocol_config=cfg.protocol)
        trainable = self.agent_pool.trainable_parameter_count()
        logger.info("Trainable parameters: %s", f"{trainable:,}")

        # 2. Environment
        logger.info("Setting up environment...")
        self.environment = OgentiEnvironment(
            task_generator=TaskGenerator(
                dataset_path=cfg.dataset_path,
                phase=0,
                seed=cfg.infra.seed,
            ),
        )

        # 3. Channel
        self.channel = CommunicationChannel(
            protocol_config=cfg.protocol,
            inject_noise_prob=0.0,
            episode=0,
        )

        # 4. Reward
        self.reward_fn = RewardFunction(config=cfg.reward)

        # 5. Curriculum
        self.scheduler = CurriculumScheduler(
            phases=cfg.phases,
            on_phase_change=self._on_phase_change,
        )

        # 6. Optimizer
        self._setup_optimizer()

        # 7. W&B
        if cfg.infra.use_wandb:
            self._setup_wandb()

        logger.info("Setup complete. Ready to train.")

    def train(self) -> None:
        """Run the full training loop."""
        cfg = self.config
        logger.info("═══ Training started ═══")
        start_time = time.time()

        while not self.scheduler.is_training_complete:
            phase = self.scheduler.current_phase

            # Run one episode — Phase 4 uses distillation, others use RL/supervised
            if phase.phase_id == 4 and self.adapter is not None:
                metrics = self._run_distillation_episode(phase)
            else:
                metrics = self._run_episode(phase)

            # Update curriculum
            self.scheduler.update(
                accuracy=metrics["accuracy"],
                compression=metrics["compression_ratio"],
                reward=metrics["total_reward"],
            )

            # Phase transition
            if self.scheduler.should_advance():
                self.scheduler.advance()

            # Logging
            if self.global_episode % cfg.infra.log_every == 0:
                self._log_metrics(metrics)

            # Evaluation
            if self.global_episode % cfg.eval_every == 0 and self.global_episode > 0:
                self._evaluate()

            # Checkpoint
            if self.global_episode % cfg.infra.checkpoint_every == 0 and self.global_episode > 0:
                self._save_checkpoint()

            self.global_episode += 1

            # Safety: max episodes
            if self.global_episode >= cfg.total_episodes:
                logger.info("Hit total_episodes cap (%d), stopping", cfg.total_episodes)
                break

        elapsed = time.time() - start_time
        logger.info(
            "═══ Training complete ═══\n"
            "Episodes: %d | Time: %.1f min | Best reward: %.4f",
            self.global_episode, elapsed / 60, self.best_reward,
        )

        # Final save
        self._save_checkpoint(tag="final")

        # Export universal adapter if Phase 4 was reached
        if self.adapter is not None:
            self._export_adapter()

    # ── Episode ──

    def _run_episode(self, phase: PhaseConfig) -> dict:
        """
        Run a single training episode.

        1. Sample task
        2. Encoder produces protocol message
        3. Channel transmits (with noise if applicable)
        4. Decoder reconstructs
        5. Compute reward
        6. PPO update (if RL is on)
        """
        cfg = self.config
        env = self.environment
        channel = self.channel
        enc_agent = self.agent_pool.get_encoder()
        dec_agent = self.agent_pool.get_decoder()

        # Update channel state
        channel.set_episode(self.global_episode)
        channel.inject_noise_prob = phase.noise_prob

        # 1. Sample task
        task = env.reset()

        # Count original NL tokens
        original_tokens = len(
            enc_agent.encoder.tokenizer.encode(task.instruction)
        )

        # 2. Encode
        if phase.use_rl:
            message, enc_log_probs = enc_agent.act(
                task.instruction,
                max_tokens=cfg.protocol.effective_budget(self.global_episode),
            )
        else:
            # Supervised: use greedy encoding
            message = enc_agent.encoder.encode(
                task.instruction,
                sender_id=enc_agent.config.agent_id,
                max_tokens=cfg.protocol.effective_budget(self.global_episode),
            )
            enc_log_probs = []

        protocol_tokens = message.token_count

        # 3. Channel (simulated — direct pass with noise)
        delivered = channel.send(
            message, original_nl_tokens=original_tokens
        )

        if not delivered:
            # Budget violation → negative reward, skip decode
            return {
                "accuracy": 0.0,
                "compression_ratio": 0.0,
                "total_reward": cfg.reward.budget_violation_penalty,
                "protocol_tokens": protocol_tokens,
                "original_tokens": original_tokens,
                "phase": phase.phase_id,
                "episode": self.global_episode,
            }

        # 4. Decode
        if phase.use_rl:
            decoded_text, dec_log_probs = dec_agent.act(message)
        else:
            # Supervised: greedy decoding
            action = dec_agent.decoder.decode(message)
            decoded_text = action.text
            dec_log_probs = []

        # 5. Reward
        budget = cfg.protocol.effective_budget(self.global_episode)
        reward_info = self.reward_fn.compute(
            decoded_text=decoded_text,
            reference=task.reference,
            protocol_tokens=protocol_tokens,
            original_tokens=original_tokens,
            budget=budget,
        )
        total_reward = reward_info["total"]

        # 6. Update rollout buffers
        if phase.use_rl and enc_log_probs:
            enc_agent.rollout.add(RolloutEntry(
                observation=task.instruction,
                action_token_ids=message.token_ids,
                log_probs=enc_log_probs,
                reward=total_reward,
            ))

        if phase.use_rl and dec_log_probs:
            dec_agent.rollout.add(RolloutEntry(
                observation=str(message.token_ids),
                action_token_ids=[],
                log_probs=dec_log_probs,
                reward=total_reward,
            ))

        # 7. Supervised auxiliary loss (mixed in during early phases)
        if phase.supervised_ratio > 0 and not phase.use_rl:
            self._supervised_step(enc_agent, dec_agent, task, message)
        elif phase.supervised_ratio > 0 and phase.use_rl:
            # Mix supervised + RL
            sup_loss = dec_agent.decoder.compute_reconstruction_loss(
                message, task.reference
            )
            # Scale by supervised_ratio and add to RL update
            if sup_loss is not None:
                scaled_loss = phase.supervised_ratio * sup_loss
                scaled_loss.backward()

        # 8. PPO update (periodically, when buffer is full enough)
        if (
            phase.use_rl
            and len(enc_agent.rollout) >= phase.batch_size
        ):
            self._ppo_update(enc_agent, dec_agent, phase)

        # Track best
        if total_reward > self.best_reward:
            self.best_reward = total_reward

        return {
            "accuracy": reward_info["accuracy"],
            "efficiency": reward_info["efficiency"],
            "compression_ratio": reward_info["compression_ratio"],
            "total_reward": total_reward,
            "protocol_tokens": protocol_tokens,
            "original_tokens": original_tokens,
            "phase": phase.phase_id,
            "episode": self.global_episode,
            "task_category": task.category.value,
        }

    # ── PPO Update ──

    def _ppo_update(
        self,
        enc_agent: EncoderAgent,
        dec_agent: DecoderAgent,
        phase: PhaseConfig,
    ) -> None:
        """
        Proximal Policy Optimization update.

        Simplified PPO for the protocol learning setting:
        - Each "step" is a full encode→decode episode
        - Advantage = R - V(s)
        - Clip the importance-weighted advantage
        """
        # Compute advantages
        enc_agent.rollout.compute_gae()
        dec_agent.rollout.compute_gae()

        for ppo_epoch in range(phase.ppo_epochs):
            # Encoder PPO
            for batch in enc_agent.rollout.get_batches(phase.batch_size):
                self._ppo_step_encoder(enc_agent, batch, phase)

            # Decoder PPO
            for batch in dec_agent.rollout.get_batches(phase.batch_size):
                self._ppo_step_decoder(dec_agent, batch, phase)

        enc_agent.rollout.clear()
        dec_agent.rollout.clear()

    def _ppo_step_encoder(
        self,
        agent: EncoderAgent,
        batch: list[RolloutEntry],
        phase: PhaseConfig,
    ) -> None:
        """Single PPO gradient step for encoder."""
        self.optimizer.zero_grad()

        total_loss = torch.tensor(0.0, device=self.device, requires_grad=True)

        for entry in batch:
            if not entry.log_probs:
                continue

            # Old log prob (from rollout)
            old_log_prob = sum(entry.log_probs)

            # New log prob (current policy)
            _, new_scores = agent.encoder.encode_for_training(
                entry.observation,
                max_tokens=len(entry.action_token_ids) + 5,
            )

            new_log_prob = torch.tensor(0.0, device=self.device)
            for i, score in enumerate(new_scores):
                if i >= len(entry.action_token_ids):
                    break
                probs = F.softmax(score[0], dim=-1)
                token_id = entry.action_token_ids[i]
                new_log_prob = new_log_prob + torch.log(probs[token_id] + 1e-8)

            # Importance ratio
            ratio = torch.exp(new_log_prob - old_log_prob)
            advantage = torch.tensor(entry.advantage, device=self.device)

            # Clipped surrogate
            clip_eps = agent.config.clip_eps
            surr1 = ratio * advantage
            surr2 = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * advantage
            policy_loss = -torch.min(surr1, surr2)

            # Entropy bonus (encourage exploration)
            entropy = torch.tensor(0.0, device=self.device)
            for score in new_scores[:len(entry.action_token_ids)]:
                probs = F.softmax(score[0], dim=-1)
                log_probs = F.log_softmax(score[0], dim=-1)
                entropy = entropy - (probs * log_probs).sum()
            entropy_loss = -agent.config.entropy_coef * entropy

            total_loss = total_loss + policy_loss + entropy_loss

        if len(batch) > 0:
            total_loss = total_loss / len(batch)
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(
                agent.encoder.parameters(),
                agent.config.max_grad_norm,
            )
            self.optimizer.step()

    def _ppo_step_decoder(
        self,
        agent: DecoderAgent,
        batch: list[RolloutEntry],
        phase: PhaseConfig,
    ) -> None:
        """Single PPO gradient step for decoder."""
        self.optimizer.zero_grad()

        total_loss = torch.tensor(0.0, device=self.device, requires_grad=True)

        for entry in batch:
            if not entry.log_probs:
                continue

            old_log_prob = sum(entry.log_probs)
            advantage = torch.tensor(entry.advantage, device=self.device)

            # For decoder we use the reconstruction loss as a proxy
            # since recomputing full decode log probs is expensive
            policy_loss = -old_log_prob * advantage

            total_loss = total_loss + policy_loss

        if len(batch) > 0:
            total_loss = total_loss / len(batch)
            total_loss.backward()
            torch.nn.utils.clip_grad_norm_(
                agent.decoder.parameters(),
                agent.config.max_grad_norm,
            )
            self.optimizer.step()

    # ── Phase 4: Distillation Episode ──

    def _run_distillation_episode(self, phase: PhaseConfig) -> dict:
        """
        Phase 4 distillation episode.

        Uses the trained Qwen LoRA as a teacher to train the
        universal adapter's PPH/PRH heads.

        Flow:
          1. Sample task
          2. Teacher (Qwen LoRA) produces hidden states + protocol tokens
          3. Student (PPH) tries to produce the same protocol tokens
             from the same hidden states
          4. KD loss aligns student ↔ teacher distributions
          5. PRH learns to reconstruct model hidden states from
             protocol tokens (inverse of PPH)
        """
        cfg = self.config
        env = self.environment
        enc_agent = self.agent_pool.get_encoder()
        dec_agent = self.agent_pool.get_decoder()
        adapter = self.adapter

        # 1. Sample task
        task = env.reset()
        original_tokens = len(
            enc_agent.encoder.tokenizer.encode(task.instruction)
        )

        # 2. Teacher forward — get encoder hidden states + protocol output
        with torch.no_grad():
            teacher_msg, teacher_scores = enc_agent.encoder.encode_for_training(
                task.instruction,
                max_tokens=cfg.protocol.effective_budget(self.global_episode),
            )

            # Teacher hidden states (last layer of Qwen)
            inputs = enc_agent.encoder.tokenizer(
                task.instruction,
                return_tensors="pt",
                truncation=True,
                max_length=512,
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
            teacher_out = enc_agent.encoder.model(**inputs, output_hidden_states=True)
            teacher_hidden = teacher_out.hidden_states[-1]  # (1, S, H)

            # Teacher protocol token IDs
            teacher_token_ids = torch.tensor(
                [teacher_msg.token_ids], device=self.device
            )

            # Build teacher logits from score list
            if teacher_scores:
                teacher_logits = torch.stack(
                    [s.squeeze(0) for s in teacher_scores[:len(teacher_msg.token_ids)]],
                    dim=0,
                ).unsqueeze(0)  # (1, T, V_lm)
            else:
                teacher_logits = None

        # 3. Student forward — PPH produces protocol logits from same hidden states
        student_logits = adapter.encoder_head(
            teacher_hidden, protocol_tokens=teacher_token_ids
        )  # (1, T, V_proto)

        # 4. Compute distillation loss (PPH)
        #    Project teacher logits to protocol vocab size if dimensions differ
        if teacher_logits is not None and teacher_logits.shape[-1] != student_logits.shape[-1]:
            # Teacher is in LM vocab space → use hard labels instead
            pph_loss = F.cross_entropy(
                student_logits.view(-1, student_logits.shape[-1]),
                teacher_token_ids.view(-1),
            )
        elif teacher_logits is not None:
            pph_loss = adapter.distillation_loss(student_logits, teacher_logits)
        else:
            pph_loss = F.cross_entropy(
                student_logits.view(-1, student_logits.shape[-1]),
                teacher_token_ids.view(-1),
            )

        # 5. PRH loss — reconstruct teacher hidden states from protocol tokens
        reconstructed_hidden = adapter.decoder_head(
            teacher_token_ids, teacher_hidden.shape[-1]
        )  # (1, T_proto, H)

        # Pool teacher hidden for comparison (match temporal dims)
        T_proto = teacher_token_ids.shape[1]
        if teacher_hidden.shape[1] > T_proto:
            # Chunk teacher hidden and mean-pool to match protocol length
            chunks = torch.chunk(
                teacher_hidden[:, :T_proto * (teacher_hidden.shape[1] // T_proto)],
                T_proto, dim=1,
            )
            teacher_pooled = torch.stack([c.mean(dim=1) for c in chunks], dim=1)
        else:
            teacher_pooled = teacher_hidden[:, :T_proto]

        prh_loss = F.mse_loss(reconstructed_hidden, teacher_pooled.detach())

        # 6. Combined loss
        alpha = adapter.config.distill_alpha
        total_loss = alpha * pph_loss + (1 - alpha) * prh_loss

        # 7. Backward + optimize adapter only
        self.adapter_optimizer.zero_grad()
        total_loss.backward()
        torch.nn.utils.clip_grad_norm_(adapter.parameters(), 1.0)
        self.adapter_optimizer.step()

        # 8. Compute metrics for logging
        with torch.no_grad():
            student_tokens = student_logits.argmax(dim=-1)  # (1, T)
            match = (student_tokens == teacher_token_ids).float().mean().item()
            protocol_tokens = teacher_msg.token_count
            compression = original_tokens / protocol_tokens if protocol_tokens > 0 else 0

        return {
            "accuracy": match,
            "efficiency": 1.0 - (prh_loss.item() / (prh_loss.item() + 1)),
            "compression_ratio": compression,
            "total_reward": 1.0 - total_loss.item(),
            "protocol_tokens": protocol_tokens,
            "original_tokens": original_tokens,
            "phase": phase.phase_id,
            "episode": self.global_episode,
            "task_category": task.category.value,
            "pph_loss": round(pph_loss.item(), 4),
            "prh_loss": round(prh_loss.item(), 4),
            "distill_match": round(match, 4),
        }

    # ── Supervised Step ──

    def _supervised_step(
        self,
        enc_agent: EncoderAgent,
        dec_agent: DecoderAgent,
        task,
        message: ProtocolMessage,
    ) -> None:
        """Pure supervised step (Phase 0)."""
        self.optimizer.zero_grad()

        loss = dec_agent.decoder.compute_reconstruction_loss(
            message, task.reference
        )
        if loss is not None:
            loss.backward()
            torch.nn.utils.clip_grad_norm_(
                list(enc_agent.encoder.parameters())
                + list(dec_agent.decoder.parameters()),
                1.0,
            )
            self.optimizer.step()

    # ── Evaluation ──

    def _evaluate(self) -> dict:
        """Run evaluation on held-out tasks."""
        logger.info("Running evaluation (%d episodes)...", self.config.eval_episodes)

        enc_agent = self.agent_pool.get_encoder()
        dec_agent = self.agent_pool.get_decoder()

        accuracies = []
        compressions = []

        for _ in range(self.config.eval_episodes):
            task = self.environment.reset()
            original_tokens = len(
                enc_agent.encoder.tokenizer.encode(task.instruction)
            )

            message = enc_agent.encoder.encode(
                task.instruction,
                sender_id=enc_agent.config.agent_id,
            )

            action = dec_agent.decoder.decode(message)

            from ogenti_train.rewards import reward_accuracy
            acc = reward_accuracy(action.text, task.reference)
            comp = (
                original_tokens / message.token_count
                if message.token_count > 0 else 0.0
            )

            accuracies.append(acc)
            compressions.append(comp)

        avg_acc = sum(accuracies) / len(accuracies) if accuracies else 0.0
        avg_comp = sum(compressions) / len(compressions) if compressions else 0.0

        logger.info(
            "Eval: accuracy=%.4f, compression=%.1fx",
            avg_acc, avg_comp,
        )

        return {"eval_accuracy": avg_acc, "eval_compression": avg_comp}

    # ── Phase Transition Callback ──

    def _on_phase_change(self, phase_id: int, phase: PhaseConfig) -> None:
        """Called when curriculum scheduler advances to a new phase."""
        logger.info(
            "Phase transition → %d (%s): lr=%s, batch=%d, agents=%d",
            phase_id, phase.name, phase.learning_rate,
            phase.batch_size, phase.num_agents,
        )

        # Update learning rate
        for pg in self.optimizer.param_groups:
            pg["lr"] = phase.learning_rate

        # Update environment phase
        self.environment.set_phase(phase_id)

        # Update channel noise
        self.channel.inject_noise_prob = phase.noise_prob

        # Update reward weights
        if phase.reward_weights:
            rw = phase.reward_weights
            self.reward_fn.config.w_accuracy = rw.get(
                "w_accuracy", self.reward_fn.config.w_accuracy
            )
            self.reward_fn.config.w_efficiency = rw.get(
                "w_efficiency", self.reward_fn.config.w_efficiency
            )
            self.reward_fn.config.w_clarity = rw.get(
                "w_clarity", self.reward_fn.config.w_clarity
            )
            self.reward_fn.config.w_generalization = rw.get(
                "w_generalization", self.reward_fn.config.w_generalization
            )

        # ── Phase 4: Initialize universal adapter for distillation ──
        if phase_id == 4:
            self._init_adapter_for_distillation()

        # Save phase transition checkpoint
        self._save_checkpoint(tag=f"phase_{phase_id}")

    # ── Phase 4: Adapter Initialization ──

    def _init_adapter_for_distillation(self) -> None:
        """
        Initialize the universal adapter and its optimizer for Phase 4.

        Freezes all Qwen LoRA weights (teacher), creates the adapter
        (PPH + PRH), and sets up a separate optimizer for adapter params only.
        """
        logger.info("═══ Phase 4: Initializing Universal Adapter ═══")

        # Freeze teacher (Qwen LoRA) — no more RL updates
        enc_agent = self.agent_pool.get_encoder()
        dec_agent = self.agent_pool.get_decoder()
        for p in enc_agent.encoder.parameters():
            p.requires_grad = False
        for p in dec_agent.decoder.parameters():
            p.requires_grad = False
        logger.info("Teacher (Qwen LoRA) frozen.")

        # Detect source model hidden size
        hidden_size = enc_agent.encoder.model.config.hidden_size
        logger.info(f"Source model hidden size: {hidden_size}")

        # Create adapter
        adapter_cfg = AdapterConfig(
            hidden_dim=256,
            num_layers=3,
            protocol_vocab_size=256,
            distill_temperature=2.0,
            distill_alpha=0.7,
            trained_on=self.config.model_name or "Qwen/Qwen2.5-3B-Instruct",
        )
        self.adapter = OgentiAdapter(config=adapter_cfg).to(self.device)

        # Separate optimizer for adapter only (teacher is frozen)
        self.adapter_optimizer = AdamW(
            self.adapter.parameters(),
            lr=self.scheduler.current_phase.learning_rate,
            weight_decay=self.config.weight_decay,
        )

        n_params = sum(p.numel() for p in self.adapter.parameters())
        logger.info(
            f"Universal adapter created: {n_params:,} params "
            f"(PPH + PRH, hidden_dim={adapter_cfg.hidden_dim})"
        )

    def _export_adapter(self) -> None:
        """
        Export the trained universal adapter after Phase 4 completes.

        Saves:
          checkpoints/universal_adapter/
            adapter_config.json
            protocol_vocab.json
            pph_weights.safetensors
            prh_weights.safetensors
        """
        if self.adapter is None:
            logger.warning("No adapter to export (Phase 4 not complete)")
            return

        export_dir = Path(self.config.infra.checkpoint_dir) / "universal_adapter"

        # Build vocab from discovered tokens
        enc_agent = self.agent_pool.get_encoder()
        self.adapter.vocab = ProtocolVocab(
            version="1.0",
            trained_episodes=self.global_episode,
            source_model=self.config.model_name or "Qwen/Qwen2.5-3B-Instruct",
        )

        # Save
        self.adapter.save(export_dir)
        logger.info(
            f"═══ Universal Adapter exported to {export_dir} ═══\n"
            f"  PPH + PRH weights + protocol vocab\n"
            f"  Attach to any model: adapter.attach(model, tokenizer)"
        )

    # ── Optimizer Setup ──

    def _setup_optimizer(self) -> None:
        """Initialize optimizer and LR scheduler."""
        cfg = self.config
        phase0 = self.scheduler.current_phase

        params = list(self.agent_pool.all_parameters())
        trainable_params = [p for p in params if p.requires_grad]

        self.optimizer = AdamW(
            trainable_params,
            lr=phase0.learning_rate,
            weight_decay=cfg.weight_decay,
            betas=(0.9, 0.999),
        )

        if cfg.lr_scheduler == "cosine":
            self.lr_scheduler = CosineAnnealingLR(
                self.optimizer,
                T_max=cfg.total_episodes,
                eta_min=1e-6,
            )
        elif cfg.lr_scheduler == "linear":
            self.lr_scheduler = LinearLR(
                self.optimizer,
                start_factor=1.0,
                end_factor=0.01,
                total_iters=cfg.total_episodes,
            )

    # ── Checkpointing ──

    def _save_checkpoint(self, tag: str = "") -> None:
        """Save encoder/decoder LoRA + training state."""
        cfg = self.config
        ckpt_dir = Path(cfg.infra.checkpoint_dir)

        suffix = f"_ep{self.global_episode}"
        if tag:
            suffix = f"_{tag}"

        enc_path = ckpt_dir / f"encoder{suffix}"
        dec_path = ckpt_dir / f"decoder{suffix}"

        enc_agent = self.agent_pool.get_encoder()
        dec_agent = self.agent_pool.get_decoder()

        enc_agent.encoder.save_pretrained(str(enc_path))
        dec_agent.decoder.save_pretrained(str(dec_path))

        # Save training state
        state = {
            "global_episode": self.global_episode,
            "best_reward": self.best_reward,
            "phase": self.scheduler.current_phase_idx,
            "phase_metrics": self.scheduler.metrics.summary(),
            "phase_history": self.scheduler.get_history(),
        }

        import json
        with open(ckpt_dir / f"state{suffix}.json", "w") as f:
            json.dump(state, f, indent=2)

        # Save config
        cfg.save(str(ckpt_dir / "config.json"))

        logger.info("Checkpoint saved: %s", suffix)

        # Cleanup old checkpoints
        self._cleanup_checkpoints()

    def _cleanup_checkpoints(self) -> None:
        """Keep only the last N checkpoints."""
        ckpt_dir = Path(self.config.infra.checkpoint_dir)
        if not ckpt_dir.exists():
            return

        keep = self.config.infra.keep_last_n
        # Find encoder checkpoint dirs
        enc_dirs = sorted(
            [d for d in ckpt_dir.iterdir() if d.is_dir() and d.name.startswith("encoder_ep")],
            key=lambda d: d.stat().st_mtime,
        )

        if len(enc_dirs) > keep:
            for d in enc_dirs[:-keep]:
                import shutil
                shutil.rmtree(d, ignore_errors=True)
                # Also remove corresponding decoder and state
                dec_d = d.parent / d.name.replace("encoder", "decoder")
                if dec_d.exists():
                    shutil.rmtree(dec_d, ignore_errors=True)
                state_f = d.parent / d.name.replace("encoder", "state") + ".json"

    # ── Logging ──

    def _log_metrics(self, metrics: dict) -> None:
        """Log metrics to console and W&B."""
        phase = self.scheduler.current_phase
        pm = self.scheduler.metrics

        logger.info(
            "[Ep %5d | Phase %d/%s] "
            "R=%.3f  acc=%.3f  comp=%.1fx  tokens=%d→%d  "
            "(avg: R=%.3f  acc=%.3f  comp=%.1fx)",
            self.global_episode,
            phase.phase_id,
            phase.name,
            metrics.get("total_reward", 0),
            metrics.get("accuracy", 0),
            metrics.get("compression_ratio", 0),
            metrics.get("original_tokens", 0),
            metrics.get("protocol_tokens", 0),
            pm.avg_reward,
            pm.avg_accuracy,
            pm.avg_compression,
        )

        self._metrics_log.append(metrics)

        # W&B
        if self.config.infra.use_wandb:
            try:
                import wandb
                wandb.log(metrics, step=self.global_episode)
            except Exception:
                pass

    def _setup_wandb(self) -> None:
        """Initialize Weights & Biases."""
        try:
            import wandb
            wandb.init(
                project=self.config.infra.wandb_project,
                entity=self.config.infra.wandb_entity,
                config=self.config._to_serializable(),
                name=f"ogenti-{time.strftime('%Y%m%d-%H%M%S')}",
            )
            logger.info("W&B initialized")
        except ImportError:
            logger.warning("wandb not installed, skipping")
            self.config.infra.use_wandb = False

    # ── Utilities ──

    def _resolve_device(self) -> torch.device:
        if torch.cuda.is_available():
            return torch.device("cuda")
        elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")

    @staticmethod
    def _set_seed(seed: int) -> None:
        import random
        import numpy as np
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)


# ─────────────────────────────────────────────────────────────────
#  CLI Entry Point
# ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Ogenti MARL Training")
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to training config JSON",
    )
    parser.add_argument(
        "--resume", type=str, default=None,
        help="Path to checkpoint dir to resume from",
    )
    parser.add_argument(
        "--episodes", type=int, default=None,
        help="Override total episodes",
    )
    parser.add_argument(
        "--no-wandb", action="store_true",
        help="Disable W&B logging",
    )
    args = parser.parse_args()

    # Logging setup
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    if args.config:
        config = TrainConfig.load(args.config)
    else:
        config = TrainConfig()

    if args.episodes:
        config.total_episodes = args.episodes
    if args.no_wandb:
        config.infra.use_wandb = False

    # Train
    trainer = OgentiTrainer(config)
    trainer.setup()
    trainer.train()


if __name__ == "__main__":
    main()
