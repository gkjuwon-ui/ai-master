"""
Demo data feeder — simulates training events for the dashboard.

Used when running `python -m ogenti_train.server --demo` without an actual
GPU training run. Generates realistic metric progressions so the frontend
can be tested end-to-end.
"""

from __future__ import annotations

import math
import random
import threading
import time

from ogenti_train.server import TrainerBridge


# Phase definitions matching ogenti_train/curriculum.py defaults
PHASES = [
    {"phase_id": 0, "name": "warmup",     "description": "Supervised warm-up",
     "max_episodes": 5000,  "min_accuracy": 0.60, "min_compression": 2.0},
    {"phase_id": 1, "name": "simple",      "description": "Simple 1:1 MARL",
     "max_episodes": 15000, "min_accuracy": 0.75, "min_compression": 8.0},
    {"phase_id": 2, "name": "complex",     "description": "Multi-hop routing",
     "max_episodes": 20000, "min_accuracy": 0.70, "min_compression": 12.0},
    {"phase_id": 3, "name": "generalize",  "description": "Zero-shot transfer",
     "max_episodes": 10000, "min_accuracy": 0.65, "min_compression": 15.0},
]

# Target metrics at each phase boundary
TARGETS = [
    {"compression": 1.0,  "fidelity": 0.00, "tokens": 30, "budget": 30.0},
    {"compression": 2.2,  "fidelity": 0.52, "tokens": 24, "budget": 27.0},
    {"compression": 8.5,  "fidelity": 0.86, "tokens": 11, "budget": 18.0},
    {"compression": 13.0, "fidelity": 0.94, "tokens": 6,  "budget": 8.0},
    {"compression": 15.8, "fidelity": 0.97, "tokens": 5,  "budget": 5.0},
]

TASKS = [
    ("Summarize quarterly earnings report",    "summarize"),
    ("Compare product A vs B metrics",          "data_analysis"),
    ("Extract findings from research paper",    "summarize"),
    ("Analyze customer sentiment trends",       "data_analysis"),
    ("Generate executive summary",              "summarize"),
    ("Classify document by topic",              "instruction_following"),
    ("Identify anomalies in dataset",           "data_analysis"),
    ("Translate technical spec to guide",       "translate"),
    ("Prioritize action items from notes",      "reasoning"),
    ("Evaluate campaign performance",           "data_analysis"),
    ("What is the capital of France?",          "qa"),
    ("Solve: 2x + 5 = 17",                     "math"),
    ("Review this Python function",             "code_review"),
    ("Write a haiku about AI",                  "creative_writing"),
    ("Chain summarize three documents",         "chain_summarize"),
]

VOCAB_POOL = [
    {"token_id": 7,   "meaning": "begin-ctx",      "category": "struct"},
    {"token_id": 22,  "meaning": "end-response",   "category": "struct"},
    {"token_id": 1,   "meaning": "separator",      "category": "struct"},
    {"token_id": 15,  "meaning": "ack",            "category": "struct"},
    {"token_id": 42,  "meaning": "summarize",      "category": "op"},
    {"token_id": 87,  "meaning": "compare",        "category": "op"},
    {"token_id": 91,  "meaning": "extract",        "category": "op"},
    {"token_id": 3,   "meaning": "key-points",     "category": "op"},
    {"token_id": 67,  "meaning": "enumerate",      "category": "op"},
    {"token_id": 45,  "meaning": "analyze",        "category": "op"},
    {"token_id": 55,  "meaning": "aggregate",      "category": "op"},
    {"token_id": 30,  "meaning": "transform",      "category": "op"},
    {"token_id": 33,  "meaning": "causal-link",    "category": "rel"},
    {"token_id": 14,  "meaning": "contrast",       "category": "rel"},
    {"token_id": 200, "meaning": "temporal",       "category": "mod"},
    {"token_id": 8,   "meaning": "quantitative",   "category": "mod"},
    {"token_id": 77,  "meaning": "trend-up",       "category": "semantic"},
    {"token_id": 78,  "meaning": "trend-down",     "category": "semantic"},
    {"token_id": 120, "meaning": "entity-ref",     "category": "semantic"},
    {"token_id": 156, "meaning": "sentiment-pos",  "category": "semantic"},
    {"token_id": 99,  "meaning": "confidence-hi",  "category": "meta"},
    {"token_id": 100, "meaning": "confidence-lo",  "category": "meta"},
    {"token_id": 250, "meaning": "uncertainty",    "category": "meta"},
    {"token_id": 11,  "meaning": "scope-global",   "category": "meta"},
]

# Phases in which each vocab token is discovered
VOCAB_PHASE = [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2, 2, 2, 2, 2, 2, 2, 2, 3, 3, 3, 3]


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _smoothstep(t: float) -> float:
    return t * t * (3 - 2 * t)


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def _feeder_loop(bridge: TrainerBridge) -> None:
    """Main demo feeder loop — runs until thread is killed.
    
    Designed to show the FULL training progression in ~2 minutes,
    not 3 hours. The dashboard should feel alive immediately.
    """
    
    # Notify training start
    bridge.on_training_start({"phases": PHASES})
    
    total_episodes = 5000
    tick_interval = 0.25      # seconds between ticks
    ep_per_tick = 12           # episodes per tick → ~48 ep/sec
    vocab_idx = 0
    msg_count = 0
    
    phase = 0
    phase_start_ep = 0
    # Fast phase limits — full cycle in ~2 min
    phase_ep_limits = [500, 1500, 2000, 1000]
    
    episode = 0
    
    # Smoothing state (exponential moving average)
    ema_compression = 1.0
    ema_fidelity = 0.0
    ema_budget = 30.0
    ema_alpha = 0.15  # smoothing factor
    
    while True:
        time.sleep(tick_interval)
        
        if bridge.status == "paused":
            continue
        
        # Advance by multiple episodes per tick
        ep_step = ep_per_tick + random.randint(-2, 3)
        episode += max(1, ep_step)
        
        # ── Phase progression ──────────────────────────────
        phase_ep = episode - phase_start_ep
        phase_max = phase_ep_limits[phase]
        
        if phase_ep >= phase_max and phase < 3:
            old_name = PHASES[phase]["name"]
            phase += 1
            phase_start_ep = episode
            bridge.on_phase_change({
                "new_phase": phase,
                "new_phase_name": PHASES[phase]["name"],
                "completed_phase_summary": {
                    "phase": phase - 1,
                    "name": old_name,
                    "episodes": phase_max,
                    "avg_accuracy": bridge.fidelity,
                    "avg_compression": bridge.compression,
                },
                "current_metrics": {},
            })
        
        # ── Compute interpolated metrics ───────────────────
        # Global progress across ALL phases for smooth curves
        global_progress = _clamp(episode / total_episodes, 0, 1)
        # Local progress within current phase for phase-specific effects
        local_progress = _clamp(phase_ep / phase_max, 0, 1)
        t_global = _smoothstep(global_progress)
        t_local = _smoothstep(local_progress)
        
        # Blend: 70% global curve + 30% phase-local detail
        t = 0.7 * t_global + 0.3 * t_local * ((phase + 1) / 4)
        
        src = TARGETS[0]          # always interpolate from the ground floor
        dst = TARGETS[min(phase + 1, len(TARGETS) - 1)]
        
        # Raw targets with very small noise
        raw_compression = max(1.0, _lerp(src["compression"], dst["compression"], t))
        raw_fidelity = _clamp(_lerp(src["fidelity"], dst["fidelity"], t), 0, 1)
        raw_tokens = max(3, round(_lerp(src["tokens"], dst["tokens"], t)))
        raw_budget = max(5.0, _lerp(src["budget"], dst["budget"], t))
        
        # Add realistic noise — small during warmup, more during complex phases
        phase_noise = 0.02 + phase * 0.015  # 2% → 6.5%
        raw_compression *= (1 + (random.random() - 0.5) * phase_noise * 2)
        raw_compression = max(1.0, raw_compression)
        raw_fidelity += (random.random() - 0.5) * phase_noise * 0.5
        raw_fidelity = _clamp(raw_fidelity, 0, 1)
        raw_budget += (random.random() - 0.5) * 0.8
        raw_budget = max(5.0, raw_budget)
        
        # Smooth with EMA to avoid spiky charts
        ema_compression = ema_compression + ema_alpha * (raw_compression - ema_compression)
        ema_fidelity = ema_fidelity + ema_alpha * (raw_fidelity - ema_fidelity)
        ema_budget = ema_budget + ema_alpha * (raw_budget - ema_budget)
        
        compression = round(ema_compression, 2)
        fidelity = round(ema_fidelity, 4)
        avg_tokens = max(3, round(_lerp(src["tokens"], dst["tokens"], t) + (random.random() - 0.5) * 1.5))
        budget = round(ema_budget, 1)
        
        efficiency = _clamp(1.0 / (1.0 + math.exp(-5.0 * (compression / 15.0 - 0.5))), 0, 1)
        reward = 0.4 * fidelity + 0.3 * efficiency + 0.2 * random.uniform(0.5, 1.0) + 0.1 * random.uniform(0.3, 0.9)
        
        # Generate token IDs
        token_ids = [random.randint(0, 255) for _ in range(avg_tokens)]
        
        task_str, task_cat = random.choice(TASKS)
        
        # ── Episode event ──────────────────────────────────
        metrics = {
            "episode": episode,
            "phase": phase,
            "compression_ratio": round(compression, 2),
            "accuracy": round(fidelity, 4),
            "efficiency": round(efficiency, 4),
            "total_reward": round(reward, 4),
            "protocol_tokens": avg_tokens,
            "original_tokens": round(avg_tokens * compression),
            "budget": round(budget, 1),
            "task_category": task_cat,
            "token_ids": token_ids,
        }
        bridge.on_episode(metrics)
        
        # ── Channel message event (~45% chance) ────────────
        if random.random() < 0.45:
            msg_count += 1
            success = avg_tokens <= math.ceil(budget) and random.random() > 0.05
            sender_idx = random.randint(1, 3)
            receiver_idx = random.randint(1, 3)
            
            bridge.on_message({
                "messages_sent": msg_count if success else msg_count - 1,
                "messages_dropped": 0 if success else 1,
                "total_tokens": msg_count * avg_tokens,
                "compression_ratio": round(compression, 2),
                "noise_injections": random.randint(0, 3),
                "relay_hops": 1 if phase >= 2 and random.random() > 0.7 else 0,
                "sender_id": f"encoder_α{sender_idx}",
                "receiver_id": f"decoder_β{receiver_idx}",
                "token_ids": token_ids[:5],
                "token_count": avg_tokens,
                "message_type": random.choice(["INSTRUCT", "REPORT", "NEGOTIATE", "ACK"]),
                "success": success,
                "fidelity": round(fidelity * 100, 1),
                "task": task_str,
            })
        
        # ── Vocabulary discovery (~12% chance) ─────────────
        if vocab_idx < len(VOCAB_POOL):
            required_phase = VOCAB_PHASE[vocab_idx]
            if phase >= required_phase and random.random() < 0.12:
                token = VOCAB_POOL[vocab_idx].copy()
                token["frequency"] = random.randint(200, 1500)
                bridge.on_vocab_discovered(token)
                vocab_idx += 1
        
        # ── Periodic eval (~every 100 episodes) ───────────
        if episode % 100 == 0:
            bridge.on_eval({
                "eval_accuracy": round(fidelity + random.uniform(-0.02, 0.02), 4),
                "eval_compression": round(compression + random.uniform(-0.3, 0.3), 2),
                "episode": episode,
            })
        
        # ── Loop reset ─────────────────────────────────────
        if episode >= total_episodes:
            bridge.on_training_end({"total_episodes": episode, "final_compression": compression})
            # Reset for continuous demo
            episode = 0
            phase = 0
            phase_start_ep = 0
            vocab_idx = 0
            msg_count = 0
            ema_compression = 1.0
            ema_fidelity = 0.0
            ema_budget = 30.0
            time.sleep(3)  # brief pause between cycles
            bridge.on_training_start({"phases": PHASES})


def start_demo_feeder(bridge: TrainerBridge) -> threading.Thread:
    """Launch the demo feeder in a background thread."""
    thread = threading.Thread(
        target=_feeder_loop,
        args=(bridge,),
        daemon=True,
        name="ogenti-demo-feeder",
    )
    thread.start()
    return thread
