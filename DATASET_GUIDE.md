# Ogenti Training Dataset Guide

> *To teach AI how to talk to each other, you first gotta give them something to talk about.*

---

## Table of Contents

- [What is this?](#-what-is-this)
- [Why do we need it?](#-why-do-we-need-it)
- [Under the hood](#-under-the-hood)
- [Full Category Map](#-full-category-map)
- [Curriculum & Difficulty Design](#-curriculum--difficulty-design)
- [Anatomy of a Single Data Point](#-anatomy-of-a-single-data-point)
- [How to Run](#-how-to-run)
- [Adding Custom Tasks](#-adding-custom-tasks)
- [How It Connects to Training](#-how-it-connects-to-training)
- [Dataset Stats](#-dataset-stats)

---

## ◆ What is this?

**`generate_dataset.py`** auto-generates the **task dataset** used to train the Ogenti protocol.

Here's Ogenti in one sentence:

> **Encoder AI compresses natural language into ultra-compact protocol tokens → sends through channel → Decoder AI reconstructs the meaning**

To train this, you need to give the AI "assignments" — "compress THIS sentence." Those **assignments (tasks)** are what this script creates.

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   generate_dataset.py                                   │
│                                                         │
│   "Summarize: Docker is a platform for..."              │
│        ↓                                                │
│   instruction (encoder input)                           │
│        +                                                │
│   reference  (answer — decoder must reconstruct this)   │
│        +                                                │
│   category   (summarize? translate? QA? code review?)   │
│        +                                                │
│   difficulty (0.0 easy ~ 1.0 nightmare)                 │
│        ↓                                                │
│   data/train.jsonl  (93 tasks)                          │
│   data/eval.jsonl   (17 tasks)                          │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

Think of it as **the textbook for AI school**. This tool writes the exam questions.

---

## ◆ Why do we need it?

Ogenti training runs a **5-phase curriculum**:

| Phase | Name | What's happening |
|-------|------|-----------------|
| 0 | **Warmup** | Tutorial level — basic summarize/translate/QA |
| 1 | **Simple** | Intermediate — code review, data analysis, real tasks |
| 2 | **Complex** | Multi-hop relay! 3 agents playing telephone! |
| 3 | **Generalize** | All categories + noise. The final exam |
| 4 | **Universalize** | Knowledge Distillation → universal adapter extraction |

Each phase unlocks different **categories**. Phase 0 only allows summarize/translate/QA. Multi-hop tasks don't appear until Phase 2. The dataset is structured to match this curriculum.

**Could you train without it?** Technically yes — `environment.py` has 14 built-in synthetic tasks. But running 50K episodes on 14 tasks? The AI would just memorize them. That's why this script generates **110 diverse tasks** — enough variety for the protocol to genuinely emerge rather than be memorized.

---

## ◆ Under the hood

### File Layout

```
ai_master/
├── scripts/
│   └── generate_dataset.py    ← this script
├── data/
│   ├── train.jsonl            ← generated training data (93 tasks)
│   └── eval.jsonl             ← generated eval data (17 tasks)
├── configs/
│   └── production.json        ← "dataset_path": "data/train.jsonl"
└── ogenti_train/
    └── environment.py         ← TaskGenerator loads the JSONL here
```

### What's JSONL?

**JSON Lines** — one JSON object per line. Not one big JSON array, but independent objects, one per line. Why this format rocks:

- Streamable (no need to load entire file into memory)
- Easy to append (new task = add one line at the end)
- Clean git diffs

```jsonl
{"task_id": "qa_0042", "category": "qa", "instruction": "What is the capital of France?", "reference": "Paris", "difficulty": 0.2, "num_agents": 2}
{"task_id": "code_review_0050", "category": "code_review", "instruction": "Review this code:\ndef divide(a, b):\n    return a / b", "reference": "Missing division by zero check.", "difficulty": 0.5, "num_agents": 2}
```

---

## ◆ Full Category Map

12 categories, each serving a different purpose:

### Phase 0 — The Starter Pack

| Category | What it does | Example | Difficulty |
|----------|-------------|---------|------------|
| `summarize` | Long text → key points | "Docker is a platform for..." → "Docker packages apps in containers" | 0.3 |
| `translate` | Style/language conversion | Casual → formal, technical → simple | 0.4 |
| `qa` | Question → answer | "What port does HTTPS use?" → "443" | 0.2 |

> These 3 come first because **protocol = information compression** at its core. Summarization IS compression. QA IS key extraction. Translation IS form transformation. Perfect warmup for protocol learning.

### Phase 1 — Real-World Tasks

| Category | What it does | Example | Difficulty |
|----------|-------------|---------|------------|
| `code_review` | Code → bugs/improvements | SQL injection found, O(n³) → O(n) optimization | 0.5 |
| `data_analysis` | Data → insights | "Q1=$100K, Q2=$150K..." → trend analysis | 0.6 |
| `instruction_following` | Instruction → precise execution | "List exactly 3 benefits" → exactly 3, no more | 0.3 |

> This is where **RL kicks in**. PPO starts optimizing the protocol for real.

### Phase 2 — Multi-Hop (Compound Reasoning)

| Category | What it does | Example | Difficulty |
|----------|-------------|---------|------------|
| `chain_summarize` | Read → summarize → refine | Error log analysis → pattern extraction → solution proposal | 0.7 |
| `relay_translate` | A→B→C relay translation | Technical English → simple English → Korean | 0.7 |
| `multi_step_qa` | Multi-step reasoning | Combine 3 facts → derive conclusion | 0.8 |
| `reasoning` | Logic/math reasoning | Train speed problems, server availability calculations | 0.8 |

> **3 agents enter the chat!** Tasks with `num_agents=3` require AI to relay messages A→B→C. This is when a real "protocol" becomes necessary — not just compression, but structured communication.

### Phase 3 — All Categories + Creative/Math

| Category | What it does | Example | Difficulty |
|----------|-------------|---------|------------|
| `creative_writing` | Generate creative text | Product descriptions, haiku, git commit messages | 0.6 |
| `math` | Math/calculations | LoRA parameter counting, FLOPs computation | 0.7 |

> Phase 3 **unlocks all 12 categories**. Noise cranks to 15%. The protocol either proves it's robust or it doesn't. Sink or swim.

---

## ◆ Curriculum & Difficulty Design

```
difficulty
1.0 ┤
    │                              ■ reasoning (0.8)
0.8 ┤                              ■ multi_step_qa (0.8)
    │                      ■ chain_summarize (0.7)
0.7 ┤                      ■ relay_translate (0.7)
    │                                          ■ math (0.7)
0.6 ┤              ■ data_analysis (0.6)       ■ creative (0.6)
    │
0.5 ┤              ■ code_review (0.5)
    │
0.4 ┤      ■ translate (0.4)
    │
0.3 ┤      ■ summarize (0.3)
    │      ■ instruction (0.3)
0.2 ┤      ■ qa (0.2)
    │
0.0 ┼──────┬──────────────┬────────────────┬───────────
    Phase 0   Phase 1       Phase 2          Phase 3/4
    (basics)  (practical)   (compound)       (everything)
```

**Design principles:**

1. **Start easy** — Phase 0 difficulty is 0.2-0.4. "The sky is blue" level stuff
2. **Gradual expansion** — Categories grow per phase (3 → 6 → 10 → 12)
3. **Multi-hop comes late** — 3-agent relay doesn't show up until Phase 2
4. **Phase 4 is everything** — No restrictions (but by then it's Knowledge Distillation, so the teacher model matters more than the data)

---

## ◆ Anatomy of a Single Data Point

```json
{
  "task_id": "code_review_0050",
  "category": "code_review",
  "instruction": "Review for security:\nquery = f\"SELECT * FROM users WHERE name = '{user_input}'\"",
  "reference": "SQL injection vulnerability. Use parameterized queries: cursor.execute('SELECT * FROM users WHERE name = ?', (user_input,)).",
  "difficulty": 0.5,
  "num_agents": 2,
  "metadata": {}
}
```

| Field | What it is |
|-------|-----------|
| `task_id` | Unique ID — `{category}_{index}` |
| `category` | One of the 12 categories |
| `instruction` | **Encoder input** — this natural language gets compressed into protocol tokens |
| `reference` | **Ground truth** — what the decoder should reconstruct. Used for reward calculation |
| `difficulty` | 0.0-1.0 — drives curriculum scheduling |
| `num_agents` | Agents needed (2 = direct, 3 = relay) |
| `metadata` | Extra metadata (extensible, currently empty) |

### How this data flows through training

```
One line from train.jsonl
     │
     ▼
TaskGenerator.load_dataset("data/train.jsonl")
     │
     ▼
Environment (OgentiEnvironment) samples phase-appropriate tasks
     │
     ▼
┌─────────── 1 Episode ───────────┐
│                                 │
│  Encoder receives: instruction  │
│     ↓                           │
│  "SELECT * FROM users..."       │
│     ↓  encode()                 │
│  ξ·REVIEW·SQL·INJECT·◊          │  ← protocol message (5 tokens!)
│     ↓  channel.send()           │
│  [probabilistic noise injection]│
│     ↓  decode()                 │
│  Decoder: "SQL injection..."    │
│     ↓                           │
│  reward = similarity(output, reference)
│  = similarity("SQL injection...", "SQL injection vulnerability...")
│  = 0.87  ← nailed it                │
│                                 │
│  PPO update → protocol improves │
└─────────────────────────────────┘
```

The whole game is: **how few tokens can the instruction be compressed into while the decoder still nails the reference?** That's Ogenti in a nutshell.

---

## ◆ How to Run

### 1. Basic — Generate Dataset

```bash
python scripts/generate_dataset.py
```

Done. This creates:
- `data/train.jsonl` — 93 training tasks
- `data/eval.jsonl` — 17 eval tasks

### 2. Inspect the Output

```bash
# Peek at first task
head -1 data/train.jsonl | python -m json.tool

# Count by category
python -c "
import json
from collections import Counter
tasks = [json.loads(l) for l in open('data/train.jsonl')]
for cat, n in Counter(t['category'] for t in tasks).most_common():
    print(f'  {cat}: {n}')
"

# Total task count
wc -l data/train.jsonl data/eval.jsonl
```

### 3. Connect to Production Training

```bash
# Option 1: Auto-detect (run_production.py finds data/train.jsonl automatically)
python run_production.py

# Option 2: Explicit path
python run_production.py --dataset data/train.jsonl

# Option 3: Set in config (configs/production.json)
{
  "dataset_path": "data/train.jsonl",
  "eval_dataset_path": "data/eval.jsonl"
}
```

### 4. Quick Test (100 episodes, fast sanity check)

```bash
python run_production.py --quick
```

Runs 100 episodes to verify the whole pipeline works. Tasks load automatically.

### 5. On RunPod / GPU Server

```bash
# 1) Server setup (one command)
bash scripts/setup_runpod.sh

# 2) Start training (with dashboard)
python run_production.py

# 3) Open http://<server-IP>:8000 in browser
#    → real-time training dashboard
```

---

## ◆ Adding Custom Tasks

Dead simple. One line per task.

### The pattern

```python
add("category", "instruction text", "reference answer", difficulty=0.5)
```

### Real examples

```python
# Korean summarization task
add("summarize",
    "Summarize: The Transformer architecture uses self-attention to process sequence data in parallel.",
    "Transformers use self-attention for parallel sequence processing.",
    difficulty=0.3)

# Multi-hop relay task
add("relay_translate",
    "3-step relay: Python code → pseudocode → plain English: 'sorted(data, key=lambda x: x[1])'",
    "Sorts data by the second element of each item. Compares values at index [1] and arranges in ascending order.",
    difficulty=0.7,
    num_agents=3)
```

### Direct JSONL append also works

Just add a line to the end of `data/train.jsonl`:

```bash
echo '{"task_id":"custom_001","category":"qa","instruction":"What is Ogenti?","reference":"An ultra-compressed AI-to-AI communication protocol","difficulty":0.3,"num_agents":2,"metadata":{}}' >> data/train.jsonl
```

### Supported Categories

```
summarize              Text compression
translate              Style/language conversion
qa                     Question answering
code_review            Code review & bug detection
data_analysis          Data → insights
instruction_following  Precise instruction execution
creative_writing       Creative text generation
math                   Math & calculations
reasoning              Logical reasoning
chain_summarize        Chained summarization (multi-hop)
relay_translate        Relay translation (multi-hop)
multi_step_qa          Multi-step QA (multi-hop)
```

---

## ◆ How It Connects to Training

The full data flow, visualized:

```
generate_dataset.py
        │
        ▼
  data/train.jsonl  (93 tasks)
  data/eval.jsonl   (17 tasks)
        │
        ▼
  ┌── run_production.py ──────────────────────────────┐
  │                                                   │
  │  TrainConfig.load("configs/production.json")      │
  │    └─ dataset_path = "data/train.jsonl"           │
  │                                                   │
  │  OgentiTrainer(config, bridge)                    │
  │    ├─ TaskGenerator.load_dataset(train.jsonl)     │
  │    ├─ OgentiEnvironment(task_generator)           │
  │    │                                              │
  │    ├─ Phase 0: warmup (5K episodes)               │
  │    │   └─ samples: summarize, translate, qa only  │
  │    │                                              │
  │    ├─ Phase 1: simple (15K episodes)              │
  │    │   └─ adds: code_review, data_analysis        │
  │    │                                              │
  │    ├─ Phase 2: complex (20K episodes)             │
  │    │   └─ adds: chain, relay, multi_step          │
  │    │   └─ activates: num_agents=3 tasks           │
  │    │                                              │
  │    ├─ Phase 3: generalize (10K episodes)          │
  │    │   └─ all 12 categories + 15% noise           │
  │    │                                              │
  │    └─ Phase 4: universalize (8K episodes)         │
  │        └─ Knowledge Distillation                  │
  │        └─ Qwen LoRA → Universal Adapter export    │
  │                                                   │
  │  TrainerBridge → WebSocket → Dashboard (live)     │
  │                                                   │
  └───────────────────────────────────────────────────┘
        │
        ▼
  checkpoints/universal_adapter/
    ├── adapter_config.json
    ├── protocol_vocab.json
    ├── pph_weights.safetensors    (Protocol Projection Head)
    └── prh_weights.safetensors    (Protocol Reconstruction Head)
        │
        ▼
  Attach to ANY LLM via .attach(model, tokenizer) → instant AI-to-AI comms
```

---

## ◆ Dataset Stats

```
╔══════════════════════════════════════════╗
║       Ogenti Dataset v1.0               ║
╠══════════════════════════════════════════╣
║                                         ║
║  Total Tasks:    110                    ║
║  Train Split:    93  (85%)              ║
║  Eval Split:     17  (15%)              ║
║                                         ║
║  Categories:     12                     ║
║  Difficulty:     0.2 ~ 0.8             ║
║  Avg Difficulty: 0.45                  ║
║                                         ║
║  2-Agent Tasks:  101                   ║
║  3-Agent Tasks:  9   (multi-hop only)  ║
║                                         ║
╠══════════════════════════════════════════╣
║  Category Breakdown:                    ║
║                                         ║
║  qa                    25  ████████████ ║
║  summarize             18  █████████    ║
║  instruction_following 10  █████        ║
║  code_review           10  █████        ║
║  translate             10  █████        ║
║  math                   6  ███          ║
║  reasoning              6  ███          ║
║  creative_writing       6  ███          ║
║  data_analysis          5  ██           ║
║  chain_summarize        5  ██           ║
║  multi_step_qa          5  ██           ║
║  relay_translate        4  ██           ║
║                                         ║
╚══════════════════════════════════════════╝
```

### Why is QA the biggest category?

On purpose. QA has **short, unambiguous answers** ("Paris", "8", "O(log n)"). When the protocol is first forming, QA is the perfect training ground for learning "how do I compress this long question into few tokens while keeping the answer recoverable?" It's the **kindling that lights the protocol fire**.

### Isn't 110 tasks kinda small?

Yes. But also no.

1. **Ogenti training is pairing-based** — same tasks get repeated thousands of times while the protocol optimizes. This isn't language understanding training, it's **protocol optimization**. Repetition matters more than variety
2. **58K episodes ÷ 110 tasks = ~450 repeats each** — intentional. Same problem, different protocol attempts each time, converging on the optimal compression
3. **Scaling up is trivial** — one `add()` call = one new task. Or pipe in Alpaca dataset for 50K+ tasks:

```python
from datasets import load_dataset
ds = load_dataset("tatsu-lab/alpaca", split="train")

for row in ds:
    add("instruction_following",
        row["instruction"],
        row["output"],
        difficulty=0.5)
```

But 110 is plenty for protocol discovery. You can always scale later.

---

## ◆ TL;DR

| What | Details |
|------|---------|
| **What is it?** | Task dataset generator for Ogenti protocol training |
| **Script** | `scripts/generate_dataset.py` |
| **Output** | `data/train.jsonl` + `data/eval.jsonl` |
| **Task count** | 110 (93 train + 17 eval) |
| **Categories** | 12 (QA, summarize, translate, code review, reasoning, ...) |
| **Difficulty** | 0.2 - 0.8, mapped to 5-phase curriculum |
| **Run** | `python scripts/generate_dataset.py` |
| **Training** | `python run_production.py` → auto-loads |

```bash
# The whole thing in one line:
python scripts/generate_dataset.py && python run_production.py
# Generate data → start training. Dashboard at http://localhost:8000
```

---

*Built for Ogenti — where AI talks to AI, and we just watch the compression ratio go brrr*
