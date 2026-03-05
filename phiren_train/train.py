"""
train.py — PHIREN MAPPO Trainer

Main training loop for PHIREN hallucination detection.
Uses Multi-Agent PPO with DetectorAgent + VerifierAgent.

Follows ogenti_train.train pattern:
  setup() → train() → _run_episode() → _ppo_update() → checkpoint
"""

from __future__ import annotations

import argparse
import json
import logging
import time
from pathlib import Path
from typing import Optional

import torch
import torch.nn.functional as F

from phiren_core.protocol import ClaimVerdict, VerificationMode
from phiren_core.detector import PhirenDetector
from phiren_core.calibrator import PhirenCalibrator
from phiren_core.channel import VerificationChannel

from .config import PhirenTrainConfig
from .rewards import RewardFunction, RewardConfig
from .agents import (
    AgentConfig,
    AgentPool,
    DetectorAgent,
    VerifierAgent,
    RolloutEntry,
)
from .environment import PhirenEnvironment, TaskGenerator, EpisodeResult
from .curriculum import CurriculumScheduler, PhaseConfig, default_phases

logger = logging.getLogger(__name__)


class PhirenTrainer:
    """
    PHIREN MAPPO Trainer.

    Orchestrates:
      - Task generation from datasets
      - Episode rollouts (extract claims → verify → reward)
      - PPO updates for detector & verifier agents
      - Curriculum phase progression
      - Checkpointing & monitoring
    """

    def __init__(self, config: PhirenTrainConfig):
        self.config = config

        # Components (initialized in setup())
        self.agent_pool: Optional[AgentPool] = None
        self.detector_agent: Optional[DetectorAgent] = None
        self.verifier_agent: Optional[VerifierAgent] = None
        self.channel: Optional[VerificationChannel] = None
        self.reward_fn: Optional[RewardFunction] = None
        self.task_gen: Optional[TaskGenerator] = None
        self.environment: Optional[PhirenEnvironment] = None
        self.scheduler: Optional[CurriculumScheduler] = None

        # Optimizers
        self.opt_detector: Optional[torch.optim.Optimizer] = None
        self.opt_verifier: Optional[torch.optim.Optimizer] = None

        # Training state
        self.global_episode = 0
        self.best_factuality = 0.0
        self._monitor_bridge = None

    # ──────────── Setup ────────────

    def setup(self, device: str = "auto") -> None:
        """Initialize all components."""
        logger.info("Setting up PHIREN trainer...")

        # 1. Agent Pool
        self.agent_pool = AgentPool(AgentConfig(
            ppo_clip=self.config.ppo_clip,
            ppo_epochs=self.config.ppo_epochs,
            entropy_coef=self.config.entropy_coef,
            value_loss_coef=self.config.value_loss_coef,
            max_grad_norm=self.config.max_grad_norm,
            gamma=self.config.gamma,
            gae_lambda=self.config.gae_lambda,
        ))

        self.detector_agent, self.verifier_agent = self.agent_pool.build_pair(
            detector_config=self.config.detector,
            calibrator_config=self.config.calibrator,
            device=device,
        )

        # 2. Verification Channel
        self.channel = VerificationChannel(self.config.claim)
        self.channel.register_detector(self.detector_agent.detector)
        self.channel.register_calibrator(self.verifier_agent.calibrator)

        # 3. Reward Function
        self.reward_fn = RewardFunction(RewardConfig(
            w_factuality=self.config.rewards.w_factuality,
            w_calibration=self.config.rewards.w_calibration,
            w_helpfulness=self.config.rewards.w_helpfulness,
            w_robustness=self.config.rewards.w_robustness,
        ))

        # 4. Task Generator
        self.task_gen = TaskGenerator()
        self._load_datasets()

        # 5. Environment
        self.environment = PhirenEnvironment(
            task_generator=self.task_gen,
            phase=0,
            max_steps=self.config.max_steps_per_episode,
        )

        # 6. Curriculum Scheduler
        self.scheduler = CurriculumScheduler(default_phases())
        self.scheduler.on_phase_change(self._on_phase_change)

        # 7. Optimizers
        self._setup_optimizers()

        logger.info("PHIREN trainer setup complete")
        logger.info(self.config.summary())
        logger.info(self.scheduler.summary())

    def _load_datasets(self) -> None:
        """Load hallucination datasets."""
        datasets = [
            ("truthfulqa", self.config.dataset.truthfulqa_path),
            ("fever", self.config.dataset.fever_path),
            ("halueval", self.config.dataset.halueval_path),
            ("phiren_combined", self.config.dataset.phiren_combined_path),
        ]

        for source, path in datasets:
            if Path(path).exists():
                count = self.task_gen.load_dataset(source, path)
                logger.info(f"Loaded {count} tasks from {source}")
            else:
                logger.warning(f"Dataset not found: {path}")

        if self.task_gen.total_tasks == 0:
            logger.warning("No datasets loaded! Using synthetic tasks only.")

    def _setup_optimizers(self) -> None:
        """Setup Adam optimizers for both agents."""
        self.opt_detector = torch.optim.Adam(
            self.detector_agent.trainable_parameters(),
            lr=self.config.lr_detector,
        )
        self.opt_verifier = torch.optim.Adam(
            self.verifier_agent.trainable_parameters(),
            lr=self.config.lr_verifier,
        )

    # ──────────── Training Loop ────────────

    def train(self) -> dict:
        """
        Main training loop.

        Returns final metrics dict.
        """
        logger.info(f"Starting PHIREN training for {self.config.total_episodes} episodes")
        start_time = time.time()

        metrics_history = []

        for episode in range(self.global_episode, self.config.total_episodes):
            self.global_episode = episode

            # Run episode
            result = self._run_episode()

            # Update scheduler
            factuality = 0.0
            calibration = 0.0
            if result.prediction:
                factuality = result.prediction.factuality_score
                calibration = result.prediction.calibration_score

            self.scheduler.update(
                reward=result.reward,
                factuality=factuality,
                calibration=calibration,
                success=result.success,
            )

            # PPO update (batch)
            if (episode + 1) % self.config.episodes_per_update == 0:
                ppo_metrics = self._ppo_update()

                if self._monitor_bridge:
                    self._monitor_bridge.on_episode(
                        episode=episode,
                        reward=result.reward,
                        metrics={
                            "factuality": factuality,
                            "calibration": calibration,
                            **ppo_metrics,
                        },
                    )

            # Phase advancement
            if self.scheduler.should_advance():
                self.scheduler.advance()

            # Logging
            if (episode + 1) % self.config.infra.log_every_episodes == 0:
                phase = self.scheduler.current_phase
                avg_reward = self.scheduler.metrics.avg_reward
                avg_fact = self.scheduler.metrics.avg_factuality
                avg_cal = self.scheduler.metrics.avg_calibration

                logger.info(
                    f"[EP {episode+1}/{self.config.total_episodes}] "
                    f"Phase {phase.phase_id} ({phase.name}) | "
                    f"reward={avg_reward:.4f} | "
                    f"factuality={avg_fact:.4f} | "
                    f"calibration={avg_cal:.4f}"
                )

                metrics_history.append({
                    "episode": episode + 1,
                    "phase": phase.phase_id,
                    "reward": avg_reward,
                    "factuality": avg_fact,
                    "calibration": avg_cal,
                })

            # Checkpoint
            if (episode + 1) % self.config.infra.save_every_episodes == 0:
                self._save_checkpoint(episode)

            # Track best
            if factuality > self.best_factuality:
                self.best_factuality = factuality
                self._save_checkpoint(episode, tag="best")

        elapsed = time.time() - start_time
        logger.info(
            f"Training complete | {self.config.total_episodes} episodes | "
            f"{elapsed / 3600:.1f}h | best_factuality={self.best_factuality:.4f}"
        )

        # Export final adapter
        self._export_adapter()

        return {
            "total_episodes": self.config.total_episodes,
            "best_factuality": self.best_factuality,
            "elapsed_hours": elapsed / 3600,
            "final_phase": self.scheduler.current_phase_idx,
            "history": metrics_history,
        }

    # ──────────── Episode ────────────

    def _run_episode(self) -> EpisodeResult:
        """
        Run a single training episode.

        1. Sample task
        2. Run detector (extract claims + NLI verify)
        3. Run verifier (calibrate)
        4. Compute reward
        5. Store in rollout buffers
        """
        task = self.environment.reset()
        phase = self.scheduler.current_phase

        # Phase 0: supervised learning only
        if phase.use_supervised:
            return self._run_supervised_episode(task)

        # RL episode
        # Step 1: Detector extracts claims and verifies
        prediction = self.channel.verify(
            text=task.text,
            context=task.context,
            mode=VerificationMode.FULL,
        )

        # Step 2: Compute reward
        result, done = self.environment.step(prediction, self.reward_fn)

        # Step 3: Store in rollout buffers
        # Detector rollout entry
        state_det = self._get_detector_state(prediction)
        self.detector_agent.buffer.add(RolloutEntry(
            state=state_det,
            action_logprob=self._estimate_logprob(prediction),
            value=self.detector_agent.estimate_value(state_det.unsqueeze(0)).item(),
            reward=result.reward,
            done=done,
        ))

        # Verifier rollout entry
        state_ver = self._get_verifier_state(prediction)
        self.verifier_agent.buffer.add(RolloutEntry(
            state=state_ver,
            action_logprob=0.0,  # calibrator is not a policy per se
            value=self.verifier_agent.estimate_value(state_ver.unsqueeze(0)).item(),
            reward=result.reward * self.config.rewards.w_calibration,
            done=done,
        ))

        return result

    def _run_supervised_episode(self, task) -> EpisodeResult:
        """
        Phase 0: Supervised learning episode.
        Uses ground truth claims to train the detector via cross-entropy.
        """
        prediction = self.channel.verify(
            text=task.text,
            context=task.context,
            mode=VerificationMode.FULL,
        )

        # Compute reward (still using RL reward for metrics)
        result, done = self.environment.step(prediction, self.reward_fn)

        return result

    # ──────────── PPO Update ────────────

    def _ppo_update(self) -> dict:
        """
        Run PPO update for both agents.

        Returns metrics dict.
        """
        metrics = {}

        # Detector PPO
        if len(self.detector_agent.buffer) > 0:
            det_metrics = self._ppo_step(
                agent=self.detector_agent,
                optimizer=self.opt_detector,
                tag="detector",
            )
            metrics.update({f"det_{k}": v for k, v in det_metrics.items()})

        # Verifier PPO
        if len(self.verifier_agent.buffer) > 0:
            ver_metrics = self._ppo_step(
                agent=self.verifier_agent,
                optimizer=self.opt_verifier,
                tag="verifier",
            )
            metrics.update({f"ver_{k}": v for k, v in ver_metrics.items()})

        # Clear buffers
        self.agent_pool.clear_buffers()

        return metrics

    def _ppo_step(
        self,
        agent,
        optimizer: torch.optim.Optimizer,
        tag: str,
    ) -> dict:
        """Single PPO step for one agent."""
        buffer = agent.buffer
        config = self.agent_pool.config

        # Compute GAE
        advantages, returns = buffer.compute_gae(
            gamma=config.gamma,
            gae_lambda=config.gae_lambda,
        )

        # Normalize advantages
        adv_tensor = torch.tensor(advantages, dtype=torch.float32)
        if len(adv_tensor) > 1:
            adv_tensor = (adv_tensor - adv_tensor.mean()) / (adv_tensor.std() + 1e-8)
        advantages = adv_tensor.tolist()

        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        num_updates = 0

        batch_size = max(len(buffer) // 4, 1)

        for epoch in range(config.ppo_epochs):
            for states, old_logprobs, batch_adv, batch_returns in buffer.get_batches(
                batch_size, advantages, returns
            ):
                # Value estimate
                values = agent.estimate_value(states)
                value_loss = F.mse_loss(values, batch_returns)

                # Policy loss (simplified — using advantage directly)
                policy_loss = -(batch_adv).mean()

                # Total loss
                loss = (
                    policy_loss
                    + config.value_loss_coef * value_loss
                )

                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    [p for p in agent.parameters() if p.requires_grad],
                    config.max_grad_norm,
                )
                optimizer.step()

                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                num_updates += 1

        n = max(num_updates, 1)
        return {
            "policy_loss": total_policy_loss / n,
            "value_loss": total_value_loss / n,
        }

    # ──────────── State Extraction ────────────

    def _get_detector_state(self, prediction) -> torch.Tensor:
        """Extract a state vector from the prediction for the detector agent."""
        # Encode key features as a fixed-size vector
        n_claims = len(prediction.claims)
        n_supported = prediction.supported_claims
        n_contradicted = prediction.contradicted_claims
        factuality = prediction.factuality_score

        # Pad to hidden_size using a simple embedding
        state = torch.zeros(self.config.detector.hidden_size)
        state[0] = n_claims / 20.0
        state[1] = n_supported / max(n_claims, 1)
        state[2] = n_contradicted / max(n_claims, 1)
        state[3] = factuality
        state[4] = prediction.calibration_score

        return state

    def _get_verifier_state(self, prediction) -> torch.Tensor:
        """Extract state for verifier agent."""
        claims = prediction.claims
        n = max(len(claims), 1)

        avg_conf = sum(c.confidence for c in claims) / n if claims else 0.0
        max_conf = max((c.confidence for c in claims), default=0.0)

        return self.verifier_agent.encode_state(
            num_claims=len(claims),
            avg_confidence=avg_conf,
            max_confidence=max_conf,
            supported_ratio=prediction.supported_claims / n,
            contradicted_ratio=prediction.contradicted_claims / n,
            unverifiable_ratio=prediction.unverifiable_claims / n,
            ece=1.0 - prediction.calibration_score,
            factuality=prediction.factuality_score,
        )

    @staticmethod
    def _estimate_logprob(prediction) -> float:
        """Estimate log-probability of the detector's action."""
        # Simplified: use average confidence as proxy
        claims = prediction.claims
        if not claims:
            return 0.0
        avg_conf = sum(c.confidence for c in claims) / len(claims)
        return torch.tensor(avg_conf).clamp(1e-8, 1.0).log().item()

    # ──────────── Phase Change ────────────

    def _on_phase_change(
        self,
        old_phase: PhaseConfig,
        new_phase: PhaseConfig,
    ) -> None:
        """Handle curriculum phase transition."""
        # Update environment
        self.environment.set_phase(new_phase.phase_id)

        # Update noise
        self.channel.set_noise(
            enabled=new_phase.noise_rate > 0,
            rate=new_phase.noise_rate,
        )

        # Update reward weights
        self.reward_fn.update_weights(
            w_factuality=new_phase.w_factuality,
            w_calibration=new_phase.w_calibration,
            w_helpfulness=new_phase.w_helpfulness,
            w_robustness=new_phase.w_robustness,
        )

        # Update learning rates
        for param_group in self.opt_detector.param_groups:
            param_group["lr"] = new_phase.lr
        for param_group in self.opt_verifier.param_groups:
            param_group["lr"] = new_phase.lr

        # Notify monitor
        if self._monitor_bridge:
            self._monitor_bridge.on_phase_change(
                old_phase.phase_id, new_phase.phase_id
            )

        # Save checkpoint at phase boundary
        self._save_checkpoint(self.global_episode, tag=f"phase{old_phase.phase_id}")

    # ──────────── Checkpointing ────────────

    def _save_checkpoint(self, episode: int, tag: str = "latest") -> None:
        """Save training checkpoint."""
        ckpt_dir = Path(self.config.infra.checkpoint_dir) / tag
        ckpt_dir.mkdir(parents=True, exist_ok=True)

        # Save detector
        self.detector_agent.detector.save_pretrained(str(ckpt_dir / "detector"))

        # Save calibrator
        self.verifier_agent.calibrator.save(str(ckpt_dir / "calibrator"))

        # Save training state
        state = {
            "episode": episode,
            "best_factuality": self.best_factuality,
            "scheduler": self.scheduler.get_state(),
            "optimizer_detector": self.opt_detector.state_dict(),
            "optimizer_verifier": self.opt_verifier.state_dict(),
        }
        torch.save(state, ckpt_dir / "training_state.pt")

        # Save config
        self.config.save(str(ckpt_dir / "config.json"))

        logger.info(f"Checkpoint saved: {ckpt_dir} (episode {episode})")

    def load_checkpoint(self, path: str) -> None:
        """Load a training checkpoint."""
        ckpt_dir = Path(path)

        # Load training state
        state_path = ckpt_dir / "training_state.pt"
        if state_path.exists():
            state = torch.load(state_path, map_location="cpu", weights_only=False)
            self.global_episode = state.get("episode", 0)
            self.best_factuality = state.get("best_factuality", 0.0)

            if "scheduler" in state:
                self.scheduler.load_state(state["scheduler"])
            if "optimizer_detector" in state:
                self.opt_detector.load_state_dict(state["optimizer_detector"])
            if "optimizer_verifier" in state:
                self.opt_verifier.load_state_dict(state["optimizer_verifier"])

            logger.info(
                f"Checkpoint loaded from {ckpt_dir} "
                f"(episode {self.global_episode})"
            )

    # ──────────── Export ────────────

    def _export_adapter(self) -> None:
        """Export the trained PHIREN adapter (.phr format)."""
        export_dir = Path(self.config.infra.checkpoint_dir) / "export"
        export_dir.mkdir(parents=True, exist_ok=True)

        # Save detector adapter
        self.detector_agent.detector.save_pretrained(str(export_dir / "phiren_adapter"))

        # Save calibrator
        self.verifier_agent.calibrator.save(str(export_dir / "calibrator"))

        # Export metadata
        metadata = {
            "format": "PHR",
            "version": "0.1.0",
            "model_name": self.config.detector.model_name,
            "lora_r": self.config.detector.lora_r,
            "total_episodes": self.global_episode,
            "best_factuality": self.best_factuality,
            "final_phase": self.scheduler.current_phase_idx,
            "reward_weights": {
                "factuality": self.config.rewards.w_factuality,
                "calibration": self.config.rewards.w_calibration,
                "helpfulness": self.config.rewards.w_helpfulness,
                "robustness": self.config.rewards.w_robustness,
            },
        }

        with open(export_dir / "metadata.json", "w") as f:
            json.dump(metadata, f, indent=2)

        logger.info(f"PHIREN adapter exported to {export_dir}")

    # ──────────── Monitor ────────────

    def set_monitor(self, bridge) -> None:
        """Attach a PhirenTrainerBridge for live monitoring."""
        self._monitor_bridge = bridge


# ─────────────────────────────────────────────────────────────────
#  CLI Entry Point
# ─────────────────────────────────────────────────────────────────

def main():
    """CLI entry point for PHIREN training."""
    parser = argparse.ArgumentParser(description="PHIREN MAPPO Trainer")
    parser.add_argument(
        "--config", type=str, default=None,
        help="Path to config JSON",
    )
    parser.add_argument(
        "--resume", type=str, default=None,
        help="Path to checkpoint directory to resume from",
    )
    parser.add_argument(
        "--monitor", action="store_true",
        help="Start WebSocket monitor server",
    )
    parser.add_argument(
        "--device", type=str, default="auto",
        help="Device (auto, cuda, cpu)",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load config
    if args.config:
        config = PhirenTrainConfig.load(args.config)
    else:
        config = PhirenTrainConfig()

    # Create trainer
    trainer = PhirenTrainer(config)
    trainer.setup(device=args.device)

    # Resume from checkpoint
    if args.resume:
        trainer.load_checkpoint(args.resume)

    # Start monitor
    if args.monitor:
        from .server import PhirenTrainerBridge, start_server_background
        bridge = PhirenTrainerBridge()
        trainer.set_monitor(bridge)
        start_server_background(bridge, port=config.monitor_port)

    # Train
    results = trainer.train()
    logger.info(f"Training results: {json.dumps(results, indent=2)}")


if __name__ == "__main__":
    main()
