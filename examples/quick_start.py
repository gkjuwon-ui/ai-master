"""
quick_start.py — Minimal example of the Ogenti training pipeline.

This script demonstrates the training loop without actually loading
a real LLM model. It exercises the environment, reward, curriculum,
and channel components.

Usage:
  python examples/quick_start.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from ogenti_core.protocol import ProtocolConfig, ProtocolMessage, MessageType
from ogenti_core.channel import CommunicationChannel
from ogenti_train.environment import OgentiEnvironment, TaskGenerator
from ogenti_train.rewards import RewardFunction, RewardConfig
from ogenti_train.curriculum import CurriculumScheduler


def main():
    print("═══ Ogenti Quick Start Demo ═══\n")

    # 1. Protocol config
    proto_cfg = ProtocolConfig(
        max_message_tokens=30,
        min_message_tokens=5,
        enable_budget_decay=True,
        decay_rate=0.97,  # Aggressive decay for demo
        budget_floor=5,
    )
    print(f"Protocol config: max={proto_cfg.max_message_tokens}, min={proto_cfg.min_message_tokens}")
    print(f"Budget at ep 0:   {proto_cfg.effective_budget(0)}")
    print(f"Budget at ep 50:  {proto_cfg.effective_budget(50)}")
    print(f"Budget at ep 100: {proto_cfg.effective_budget(100)}")

    # 2. Channel
    channel = CommunicationChannel(proto_cfg)
    received_messages = []
    channel.register("decoder_0", lambda m: received_messages.append(m))
    print(f"\nChannel: {channel}")

    # 3. Environment
    env = OgentiEnvironment(phase=0)
    print(f"Environment: {env}")

    # 4. Reward function
    reward_fn = RewardFunction(RewardConfig())

    # 5. Curriculum
    scheduler = CurriculumScheduler()
    print(f"Curriculum: {scheduler}")

    # 6. Simulate some episodes
    print("\n─── Simulating 20 episodes ───\n")

    for ep in range(20):
        task = env.reset()
        budget = proto_cfg.effective_budget(ep)

        # Simulate encoding (fake protocol tokens)
        import random
        num_tokens = random.randint(3, min(15, budget))
        token_ids = [random.randint(100, 50000) for _ in range(num_tokens)]
        original_tokens = len(task.instruction.split()) * 2  # rough estimate

        msg = ProtocolMessage(
            token_ids=token_ids,
            sender_id="encoder_0",
            receiver_id="decoder_0",
        )

        # Send through channel
        channel.set_episode(ep)
        delivered = channel.send(msg, original_nl_tokens=original_tokens)

        if delivered:
            # Simulate decoding (just echo some of the reference)
            decoded = task.reference[:50]

            # Compute reward
            reward_info = reward_fn.compute(
                decoded_text=decoded,
                reference=task.reference,
                protocol_tokens=num_tokens,
                original_tokens=original_tokens,
                budget=budget,
            )

            # Update curriculum
            scheduler.update(
                accuracy=reward_info["accuracy"],
                compression=reward_info["compression_ratio"],
                reward=reward_info["total"],
            )

            if ep % 5 == 0:
                print(
                    f"  Ep {ep:3d} | "
                    f"budget={budget:2d} | "
                    f"tokens={num_tokens:2d} | "
                    f"acc={reward_info['accuracy']:.3f} | "
                    f"comp={reward_info['compression_ratio']:.1f}x | "
                    f"R={reward_info['total']:.3f} | "
                    f"task={task.category.value}"
                )

    # 7. Summary
    print(f"\n─── Results ───")
    print(f"Channel stats: {channel.stats.summary()}")
    print(f"Curriculum: {scheduler}")
    print(f"Phase metrics: {scheduler.metrics.summary()}")
    print(f"\n═══ Demo complete ═══")


if __name__ == "__main__":
    main()
