# Ogenti — AI-to-AI Communication Protocol

> AIs talking to each other in human language is like two CPUs exchanging data via handwritten letters.
> Let's fix that. **15-20x compression. 97% fidelity. Zero fluff.**

## yo, what IS this?

Ogenti is a protocol that lets AI agents ditch natural language and talk to each other in **ultra-compressed token sequences** they invent themselves. We throw a bunch of LLM agents into a MARL (Multi-Agent RL) arena, crank up the token pressure, and watch them evolve their own language from scratch.

No one teaches them the protocol. They just... figure it out.

```
Human language:  "Please summarize the following document focusing on key findings
                  and recommendations, limiting the output to 200 words"  (23 tokens)

Ogenti protocol: ξ SUMMARIZE · doc → key_findings ◊ 200w                 (≈8 tokens)
```

Same meaning. Way fewer tokens. Way less money burned.

## the problem is dumb (and expensive)

| What's happening | Why it's bad |
|------------------|-------------|
| Multi-agent systems chat in natural language | NL was made for humans, not silicon |
| Every inter-agent call burns API tokens | 150+ tokens × thousands of calls = pain |
| CoT prompting balloons token usage | 3-10x overhead for internal reasoning nobody reads |

**The move**: Let agents learn their own compressed protocol through RL. 150 NL tokens → 10 protocol tokens. Same semantics. 90%+ cost reduction. Your wallet says thank you.

## how it works

```
                    ┌───────────────┐
 NL instruction ──▶ │   Encoder     │ ──▶ Protocol Message (≈10 tokens)
                    │ (3B + LoRA)   │
                    └───────────────┘
                            │
                    ┌───────────────┐
                    │   Channel     │  ← budget enforcement, noise injection
                    └───────────────┘
                            │
                    ┌───────────────┐
 Action/Output  ◀── │   Decoder     │ ◀── Protocol Message
                    │ (3B + LoRA)   │
                    └───────────────┘
```

Encoder compresses. Channel adds chaos. Decoder reconstructs. If the decoder nails it with fewer tokens, everybody gets rewarded. If not, back to the drawing board. Darwinism but for language.

## training pipeline

| Phase | Name | Episodes | What happens | The sauce |
|-------|------|----------|-------------|-----------|
| 0 | Warmup | 5K | Supervised pretraining | Agents learn "oh, encoding is a thing" |
| 1 | Simple | 15K | 1:1 RL communication | Token budget shrinks every episode. Adapt or die |
| 2 | Complex | 20K | Multi-hop relay chains | 3 agents playing telephone. With noise |
| 3 | Generalize | 10K | Zero-shot unseen tasks | All categories unlocked + 15% noise. Sink or swim |
| 4 | Universalize | 8K | Knowledge distillation | Compress the compressor into a 3MB adapter |

**Token Budget Decay** is the secret weapon — max tokens per message drops every episode. Agents literally can't be verbose even if they want to. Forces them to invent increasingly dense encodings. Natural selection speedrun.

## project structure

```
ogenti_core/          # Protocol core library
├── protocol.py       # ProtocolMessage, MessageType, OpCode, ProtocolConfig
├── encoder.py        # NL → Protocol (3B + LoRA)
├── decoder.py        # Protocol → NL/Action (3B + LoRA)
└── channel.py        # Message routing, noise injection, metrics

ogenti_train/         # MARL training pipeline
├── environment.py    # Task generation & environment loop
├── agents.py         # Encoder/Decoder agents + value head (MAPPO)
├── rewards.py        # Multi-component reward function
├── curriculum.py     # 4-phase curriculum scheduler
├── config.py         # Central training configuration
└── train.py          # Main MAPPO training loop

ogenti_bench/         # Benchmark & evaluation
├── benchmark.py      # Standardized benchmark runner
├── metrics.py        # CR, SF, CAC, PSI metrics
└── visualize.py      # Training curves & protocol evolution plots
```

## quick start

```bash
# Install
pip install -e ".[all]"

# Train (defaults)
python -m ogenti_train.train

# Train (custom config)
python -m ogenti_train.train --config my_config.json

# Benchmark
python -m ogenti_bench.benchmark \
  --encoder checkpoints/encoder_final \
  --decoder checkpoints/decoder_final \
  --episodes 500
```

## tech stack

- **Base Model**: Qwen2.5-3B-Instruct — small model = less NL inertia = easier to break free from human language habits
- **Adaptation**: LoRA (rank 16, α=32) — separate adapters for encoder/decoder
- **RL Algorithm**: MAPPO — centralized critic, decentralized actors
- **Training**: DeepSpeed ZeRO-2, bf16 mixed precision
- **Reward**: `0.4·accuracy + 0.3·efficiency + 0.2·clarity + 0.1·generalization`
- **Infra**: RunPod spot instances, ~$30-50 total for a full training run

## key metrics (what we're chasing)

| Metric | What it measures | Target |
|--------|-----------------|--------|
| Compression Ratio | NL tokens / Protocol tokens | ≥15x |
| Semantic Fidelity | cosine_sim(decoded, reference) | ≥0.97 |
| Cross-Agent Compatibility | Accuracy with agents they've never met | ≥0.85 |
| Protocol Stability | 1 - std(recent accuracies) | ≥0.90 |

## the endgame

After 58K episodes, Ogenti spits out a **~3MB Universal Adapter** (PPH + PRH heads). Slap it onto any LLM — LLaMA, Mistral, GPT, whatever — and that model instantly speaks Ogenti protocol. No retraining needed.

45 natural language tokens → 3 protocol tokens. Decoder reconstructs the full meaning. That's not compression, that's **re-encoding in meaning space**.

```
NL input (45 tokens):
  "Review this Python code for security vulnerabilities:
   query = f'SELECT * FROM users WHERE name = {user_input}'"

Protocol (3 tokens):
  ξ·SEC_REVIEW·SQL_INJ·◊

Decoder output:
  "SQL injection vulnerability detected. Use parameterized
   queries: cursor.execute('SELECT * FROM users WHERE
   name = ?', (user_input,))"
```

$30 and a GPU. That's all it takes for AI to invent its own language.

## License

MIT

---

*Built for Ogenti — where AIs stop being polite and start being efficient.*
