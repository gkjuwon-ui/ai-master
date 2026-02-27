# OSEN-1.0 Training Guide

> **Complete guide to training OSEN-1.0 — from dataset generation to final model export.**
> Version 3.0 | Updated for 4-phase training pipeline

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Hardware Requirements](#2-hardware-requirements)
3. [Best Training Route](#3-best-training-route)
4. [Dataset Guide](#4-dataset-guide)
5. [Environment Setup (RunPod)](#5-environment-setup-runpod)
6. [MoE Surgery Pipeline](#6-moe-surgery-pipeline)
7. [Training Execution](#7-training-execution)
8. [Validation & Export](#8-validation--export)
9. [Hyperparameter Reference](#9-hyperparameter-reference)
10. [Troubleshooting](#10-troubleshooting)
11. [Quick Cheat Sheet](#11-quick-cheat-sheet)

---

## 1. Architecture Overview

OSEN-1.0 is a Mixture-of-Experts (MoE) model for OS-control AI agents, built on top of **Meta Llama 4 Scout 17B-16E-Instruct**.

| Property | Value |
|---|---|
| Base model | `meta-llama/Llama-4-Scout-17B-16E-Instruct` |
| Architecture | MoE with top-1 routing |
| MoE layers | 48 |
| Base experts | 16 (indices 0–15) |
| New experts | 4 (indices 16–19) |
| Total experts | **20** |
| Hidden size | 5120 |
| Intermediate size | 8192 |
| Quantization | NF4 (bitsandbytes, double quant) |
| Context length | 4096 tokens (training) |

### The 4 New Experts

| Expert ID | Name | Specialty |
|---|---|---|
| 16 | `visual_grounding` | UI element detection, coordinate mapping, screenshot understanding |
| 17 | `workflow_orchestrator` | Multi-step task planning, cross-app workflows, process decomposition |
| 18 | `verification_oracle` | Action verification, state change detection, result validation |
| 19 | `adaptive_retry` | Error recovery, fallback strategies, graceful degradation |

### Semantic Donor Alignment

Each new expert is initialized by blending weights from semantically related base experts (not random):

| New Expert | Donors (indices) | Rationale |
|---|---|---|
| 16 visual_grounding | [1, 0, 14, 12] | screen_understanding + action_planner + input_method + memory_context |
| 17 workflow_orchestrator | [13, 0, 15, 5] | planning_strategy + action_planner + app_specific + file_system |
| 18 verification_oracle | [1, 2, 7, 12] | screen_understanding + error_recovery + safety_ethics + memory_context |
| 19 adaptive_retry | [2, 7, 3, 15] | error_recovery + safety_ethics + web_navigation + app_specific |

---

## 2. Hardware Requirements

### Minimum
| Component | Spec |
|---|---|
| GPU | A6000 48GB or A100 40GB |
| VRAM | 40 GB+ |
| RAM | 64 GB |
| Disk | 100 GB SSD |

### Recommended
| Component | Spec |
|---|---|
| GPU | **A100 80GB SXM** or H100 80GB |
| VRAM | 80 GB |
| RAM | 128 GB |
| Disk | 200 GB NVMe SSD |

### RunPod Pod Selection

| GPU | VRAM | Batch Size | Training Speed | Cost (approx) |
|---|---|---|---|---|
| A6000 48GB | 48 GB | 1 | ~8 hr/phase | $0.79/hr |
| A100 80GB SXM | 80 GB | 2–4 | ~3 hr/phase | $1.64/hr |
| H100 80GB | 80 GB | 2–4 | ~2 hr/phase | $3.89/hr |

> **Recommendation**: A100 80GB SXM is the best price-performance ratio.
> Total training time (4 phases): ~12 hours on A100 80GB.

---

## 3. Best Training Route

### Overview: 4-Phase Pipeline

```
Phase 1          Phase 2            Phase 3           Phase 4
Expert Warmup → Router Calibration → Full Fine-tune → Hard Hardening
  (3 epochs)      (2 epochs)         (3 epochs)        (1 epoch)
  LR: 2e-5        LR: 1e-5          LR: 5e-6          LR: 1e-6
```

This is the **optimal training route**, tested for stability and convergence.

### Phase 1: Expert Warmup (Foundation)

| Parameter | Value |
|---|---|
| Learning Rate | 2e-5 |
| Epochs | 3 |
| Batch Size | 2 |
| Gradient Accumulation | 8 |
| Effective Batch | 16 |
| Warmup Ratio | 0.1 |
| LoRA targets | `gate_proj`, `up_proj`, `down_proj` (MoE expert FFN layers only) |
| LoRA rank | 32 |
| LoRA alpha | 64 |

**Purpose**: Teach the 4 new experts their domain knowledge without disturbing the base model.
Only expert FFN layers are trained — the router and attention layers are frozen.

**Dataset**: Full training.jsonl (all expert-specific + cross-expert data)

### Phase 2: Router Calibration (Routing)

| Parameter | Value |
|---|---|
| Learning Rate | 1e-5 |
| Epochs | 2 |
| Batch Size | 4 |
| Gradient Accumulation | 4 |
| Effective Batch | 16 |
| Warmup Ratio | 0.05 |
| LoRA targets | `router` (MoE gate layer only) |
| LoRA rank | 16 |
| LoRA alpha | 32 |

**Purpose**: Calibrate the router to correctly dispatch tokens to the 4 new experts.
Only the router/gate weights are trained — everything else is frozen.

**Dataset**: Same training.jsonl — the router learns which tokens belong to which expert.

### Phase 3: Full Fine-tune (Integration)

| Parameter | Value |
|---|---|
| Learning Rate | 5e-6 |
| Epochs | 3 |
| Batch Size | 1 |
| Gradient Accumulation | 16 |
| Effective Batch | 16 |
| Warmup Ratio | 0.03 |
| LoRA targets | `q_proj`, `k_proj`, `v_proj`, `o_proj`, `gate_proj`, `up_proj`, `down_proj` |
| LoRA rank | 64 |
| LoRA alpha | 128 |

**Purpose**: End-to-end fine-tuning with all projection layers trainable. This integrates the new experts
with the attention mechanism and ensures coherent output across all 20 experts.

**Dataset**: Same training.jsonl — model learns to produce high-quality complete responses.

### Phase 4: Hard Example Hardening (Robustness)

| Parameter | Value |
|---|---|
| Learning Rate | 1e-6 |
| Epochs | 1 |
| Batch Size | 1 |
| Gradient Accumulation | 16 |
| Effective Batch | 16 |
| Warmup Ratio | 0.05 |
| LoRA targets | Same as Phase 3 |
| LoRA rank | 64 |
| LoRA alpha | 128 |

**Purpose**: Harden the model against edge cases, adversarial inputs, and cross-expert confusion.
Uses the hard examples JSONL (ambiguous, multi-expert, adversarial scenarios).

**Dataset**: `hard_examples.jsonl` — generated by `generate_training_data.py --include-cross-expert`

### Why This Order?

```
Phase 1 first  → New experts learn domain knowledge on a stable base
Phase 2 second → Router learns optimal dispatching after experts have skills
Phase 3 third  → Full model aligns attention + experts + router together
Phase 4 last   → Edge cases are addressed after the model is already strong
```

**Do NOT skip phases.** Each phase depends on the previous one.
**Do NOT change the order.** Training router before experts produces garbage routing.

---

## 4. Dataset Guide

### Best Dataset Amount

| Expert | Minimum | Recommended | Optimal |
|---|---|---|---|
| visual_grounding (16) | 500 | **1,500** | 2,500 |
| workflow_orchestrator (17) | 500 | **1,500** | 2,500 |
| verification_oracle (18) | 500 | **1,500** | 2,500 |
| adaptive_retry (19) | 500 | **1,500** | 2,500 |
| Cross-expert chains | 200 | **500** | 1,000 |
| Hard/adversarial examples | 50 | **200** | 500 |
| **Total** | **2,250** | **6,700** | **11,500** |

> **TL;DR**: Aim for **1,500 samples per expert** and **500 cross-expert** minimum.
> Below 500 per expert = undertrained. Above 3,000 per expert = diminishing returns.

### Dataset Format

All training data uses **LLaMA conversation format** in JSONL:

```json
{"conversations": [
  {"role": "system", "content": "You are a visual grounding expert for computer operation..."},
  {"role": "user", "content": "Find the 'Save' button in this dialog window at the bottom right corner."},
  {"role": "assistant", "content": "I can see the 'Save' button at coordinates (845, 612). It's a standard rectangular button with white text on a blue background, located in the bottom-right corner of the dialog, next to the 'Cancel' button at (745, 612)."}
]}
```

### Dataset Quality Rules

1. **Every sample must have 3+ turns**: system + user + assistant (minimum)
2. **Multi-turn is better**: Include 5–7 turn conversations (20–30% of data)
3. **Korean coverage**: Include Korean language samples (at least 15–20%)
4. **Negative examples**: Include "what NOT to do" examples (5–10%)
5. **Diversity**: Cover different apps, OS versions, screen resolutions, themes
6. **Coordinate realism**: Use real pixel coordinates (not round numbers like 100, 200)
7. **Error scenarios**: Include failed attempts, partial results, ambiguous UI states

### Generating Training Data

#### Method 1: Script Generator (recommended for initial data)

```bash
cd scripts/moe_surgery

# Generate expert-specific + cross-expert data
python generate_training_data.py --include-cross-expert

# Output files:
#   expert_16_visual_grounding.jsonl
#   expert_17_workflow_orchestrator.jsonl
#   expert_18_verification_oracle.jsonl
#   expert_19_adaptive_retry.jsonl
#   cross_expert_chains.jsonl
#   hard_examples.jsonl

# Combine into single training file
cat expert_*.jsonl cross_expert_chains.jsonl > ../../datasets/training.jsonl
```

#### Method 2: Discord Bot (recommended for high-quality data)

The ogenti Discord bot uses **OpenAI GPT-4o-mini debate + GPT-4o judge** for quality data:

```
/gen topic:visual_grounding count:500
/gen topic:workflow_orchestrator count:500
/gen topic:verification_oracle count:500
/gen topic:adaptive_retry count:500
```

The bot generates multi-turn, debate-validated conversations that are higher quality
than templated data. **Use this if you have time** — it produces better training signal.

#### Method 3: Hybrid (best results)

1. Generate 500/expert with the script (quick baseline)
2. Generate 500/expert with the Discord bot (high quality)
3. Add 500/expert manually curated edge cases
4. Total: 1,500/expert ✓

### Verifying Your Dataset

```bash
# Count samples per expert
wc -l datasets/training.jsonl

# Check format validity
python -c "
import json
with open('datasets/training.jsonl') as f:
    valid = broken = 0
    for line in f:
        try:
            d = json.loads(line.strip())
            if len(d.get('conversations', [])) >= 3:
                valid += 1
            else:
                broken += 1
        except: broken += 1
print(f'Valid: {valid}, Broken: {broken}')
"

# Check multi-turn ratio
python -c "
import json
multi = total = 0
with open('datasets/training.jsonl') as f:
    for line in f:
        d = json.loads(line.strip())
        total += 1
        if len(d.get('conversations', [])) >= 5:
            multi += 1
print(f'Multi-turn: {multi}/{total} ({100*multi/total:.0f}%)')
print('Target: 20-30%')
"
```

---

## 5. Environment Setup (RunPod)

### Step-by-Step

#### 1. Create RunPod Account
- Go to [runpod.io](https://runpod.io)
- Add credits ($20–50 is enough for full training)

#### 2. Launch a GPU Pod
- Template: **RunPod PyTorch 2.2+ / CUDA 12+**
- GPU: **A100 80GB SXM** (recommended)
- Disk: 100 GB minimum
- Set environment variables:
  ```
  HF_TOKEN=your_huggingface_token
  WANDB_API_KEY=your_wandb_key  (optional)
  ```

#### 3. Upload Files

Upload these files to the pod root (`/workspace/`):

```
finetune_osen.py
requirements_finetune.txt
runpod_setup.sh
datasets/training.jsonl
datasets/hard_examples.jsonl     (for Phase 4)
scripts/moe_surgery/             (entire folder)
osen_expert_config.json          (reference)
config.json                      (model config)
```

#### 4. Run Setup Script

```bash
cd /workspace
chmod +x runpod_setup.sh
./runpod_setup.sh
```

This installs all dependencies and validates the environment.

#### 5. Manual Setup (if script fails)

```bash
pip install --upgrade pip
pip install -r requirements_finetune.txt

# Verify
python -c "import torch; print(torch.cuda.get_device_name(0))"
python -c "from peft import LoraConfig; print('peft OK')"
python -c "from trl import SFTTrainer; print('trl OK')"
```

#### HuggingFace Access

You need access to the gated Llama 4 model:
1. Go to https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E-Instruct
2. Request access (usually instant approval)
3. Create a token at https://huggingface.co/settings/tokens
4. Set `HF_TOKEN` in your environment

---

## 6. MoE Surgery Pipeline

> **This step is only needed if you're building OSEN-1.0 from scratch.**
> If you already have model shards with 20 experts, skip to [Training Execution](#7-training-execution).

### Surgery Steps

```bash
cd scripts/moe_surgery

# Step 1: Inject 4 new experts into each MoE layer
python inject_experts.py \
  --model-dir /workspace/model_shards \
  --output-dir /workspace/osen_model \
  --config /workspace/osen_expert_config.json

# Step 2: Train router gate weights
python train_router.py \
  --model-dir /workspace/osen_model \
  --output-dir /workspace/osen_model_routed

# Step 3: Validate the modified model
python validate_model.py \
  --model-dir /workspace/osen_model_routed
```

### What Surgery Does

1. **inject_experts.py** — For each of the 48 MoE layers:
   - Blends donor expert weights using orthogonal donor blending + SVD rotation
   - Expands router gate from 16→20 outputs
   - Creates new expert FFN weights (gate_proj, up_proj, down_proj)
   - Applies NF4 quantization to match base model format

2. **train_router.py** — Calibrates the expanded router:
   - Uses keyword-based soft labels (60+ keywords per expert, EN + KO)
   - 6-loss training (CE, KL, balance, expert_entropy, load_uniformity, negative)
   - Curriculum learning: easy → medium → hard samples
   - Ensures new experts get adequate token routing

3. **validate_model.py** — 16-point health check:
   - Model loading, expert count, router weight shapes
   - Expert diversity (cosine similarity < 0.95 between experts)
   - Inference test with sample prompts

---

## 7. Training Execution

### Full Training Pipeline

```bash
cd /workspace

# ==========================================
# Phase 1: Expert Warmup (3 epochs, ~3 hrs on A100)
# ==========================================
python finetune_osen.py \
  --phase 1 \
  --model-path meta-llama/Llama-4-Scout-17B-16E-Instruct \
  --dataset datasets/training.jsonl \
  --output-dir osen_checkpoints

# ==========================================
# Phase 2: Router Calibration (2 epochs, ~2 hrs on A100)
# ==========================================
python finetune_osen.py \
  --phase 2 \
  --dataset datasets/training.jsonl \
  --output-dir osen_checkpoints

# ==========================================
# Phase 3: Full Fine-tune (3 epochs, ~4 hrs on A100)
# ==========================================
python finetune_osen.py \
  --phase 3 \
  --dataset datasets/training.jsonl \
  --output-dir osen_checkpoints

# ==========================================
# Phase 4: Hard Hardening (1 epoch, ~1 hr on A100)
# + Merge and Export final model
# ==========================================
python finetune_osen.py \
  --phase 4 \
  --dataset datasets/hard_examples.jsonl \
  --output-dir osen_checkpoints \
  --merge
```

### Key Notes

- **Phase 2+ auto-loads from previous phase**: The script detects `osen_checkpoints/phase_N-1` and loads from there.
- **`--merge` flag**: Only use on the final phase (3 or 4). This merges LoRA weights into the base model and exports the final OSEN-1.0.
- **Resume from crash**: Add `--resume osen_checkpoints/phase_N/checkpoint-XXX` to continue from a checkpoint.
- **Sequence length**: Default 4096. Increase to 8192 with `--max-length 8192` if your data has long conversations (requires more VRAM).

### Monitoring Training

#### With Weights & Biases (recommended)

```bash
export WANDB_API_KEY=your_key
# Training automatically logs to W&B
```

Look for:
- **Phase 1**: Loss should drop from ~2.5 to ~0.8 over 3 epochs
- **Phase 2**: Loss should drop from ~1.5 to ~0.5 over 2 epochs
- **Phase 3**: Loss should drop from ~0.8 to ~0.3 over 3 epochs
- **Phase 4**: Loss should stay ~0.3–0.4 (hardening, not reducing further)

#### Without W&B

Check training logs in terminal. Loss is printed every 10 steps.

### Expected Training Times

| Phase | A6000 48GB | A100 80GB | H100 80GB |
|---|---|---|---|
| Phase 1 (3 epochs) | ~6 hrs | ~3 hrs | ~2 hrs |
| Phase 2 (2 epochs) | ~3 hrs | ~1.5 hrs | ~1 hr |
| Phase 3 (3 epochs) | ~8 hrs | ~4 hrs | ~2.5 hrs |
| Phase 4 (1 epoch) | ~2 hrs | ~1 hr | ~0.5 hrs |
| **Total** | **~19 hrs** | **~9.5 hrs** | **~6 hrs** |

---

## 8. Validation & Export

### After Training

The final model will be at: `osen_checkpoints/osen-1.0-merged/`

Verify it:

```bash
# Quick inference test
python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer
import torch

model = AutoModelForCausalLM.from_pretrained(
    'osen_checkpoints/osen-1.0-merged',
    torch_dtype=torch.bfloat16,
    device_map='auto'
)
tokenizer = AutoTokenizer.from_pretrained('osen_checkpoints/osen-1.0-merged')

messages = [
    {'role': 'system', 'content': 'You are OSEN, an AI agent that controls computers.'},
    {'role': 'user', 'content': 'Click the blue Submit button at the bottom of the form.'}
]

inputs = tokenizer.apply_chat_template(messages, return_tensors='pt').to('cuda')
output = model.generate(inputs, max_new_tokens=256)
print(tokenizer.decode(output[0], skip_special_tokens=True))
"
```

### Export Checklist

After merging, verify these files exist in `osen-1.0-merged/`:

```
config.json                    — Must show num_local_experts=20
model.safetensors.index.json   — Updated tensor map
model-*.safetensors            — Weight shards
tokenizer.json                 — Tokenizer
tokenizer_config.json          — Tokenizer config
osen_metadata.json             — OSEN version metadata
```

### Upload to HuggingFace (optional)

```bash
huggingface-cli upload your-org/osen-1.0 osen_checkpoints/osen-1.0-merged
```

---

## 9. Hyperparameter Reference

### Learning Rate Guidelines

| Scenario | Recommended LR | Why |
|---|---|---|
| Small dataset (<1000) | 1e-5 | Prevent overfitting |
| Medium dataset (1000–5000) | 2e-5 (Phase 1) | Standard warmup |
| Large dataset (5000+) | 3e-5 (Phase 1) | Can afford faster learning |
| Router training | 1e-5 | Router is sensitive to large updates |
| Full fine-tune | 5e-6 | Low LR prevents catastrophic forgetting |
| Hard hardening | 1e-6 | Minimal perturbation on converged model |

### LoRA Rank Guide

| Phase | Rank (r) | Alpha | Trainable % | Purpose |
|---|---|---|---|---|
| Phase 1 | 32 | 64 | ~0.5% | Moderate capacity for expert knowledge |
| Phase 2 | 16 | 32 | ~0.1% | Router is a small linear layer |
| Phase 3 | 64 | 128 | ~2% | Full integration needs more capacity |
| Phase 4 | 64 | 128 | ~2% | Same as Phase 3, lower LR |

### Effective Batch Size

All phases use **effective batch size = 16**:

```
Phase 1: batch_size=2 × grad_accum=8  = 16
Phase 2: batch_size=4 × grad_accum=4  = 16
Phase 3: batch_size=1 × grad_accum=16 = 16
Phase 4: batch_size=1 × grad_accum=16 = 16
```

16 is the sweet spot for MoE training:
- Below 8: Too noisy, especially for router
- Above 32: Diminishing returns, wastes VRAM

### Optimizer

| Parameter | Value | Notes |
|---|---|---|
| Optimizer | `paged_adamw_8bit` | Memory-efficient, near-identical to AdamW |
| Scheduler | `cosine` | Smooth decay, best for LoRA fine-tuning |
| Max grad norm | 0.3 | Prevents gradient explosion in MoE layers |
| Weight decay | 0.01 (Phase 1,3,4), 0.005 (Phase 2) | Lower for router to prevent over-regularization |

---

## 10. Troubleshooting

### Common Issues

#### OOM (Out of Memory)

```
torch.cuda.OutOfMemoryError: CUDA out of memory
```

**Fix**: Reduce batch size and increase gradient accumulation:
```bash
# In finetune_osen.py, change the phase config:
# batch_size: 2 → 1
# gradient_accumulation: 8 → 16
```

Or reduce max sequence length:
```bash
python finetune_osen.py --phase 1 --max-length 2048
```

#### Loss Not Decreasing

- **Phase 1 stuck at >2.0**: Dataset quality issue. Check for empty/broken samples.
- **Phase 2 stuck at >1.0**: Router not learning. Try LR=2e-5 for 1 extra epoch.
- **Phase 3 loss increases**: Learning rate too high. Try 2e-6 instead of 5e-6.

#### Flash Attention Error

```
No module named 'flash_attn'
```

**Fix**:
```bash
pip install flash-attn --no-build-isolation
```

If it still fails (compilation issues), remove `attn_implementation="flash_attention_2"` from `finetune_osen.py`.

#### HuggingFace 401 Unauthorized

```
HTTPError: 401 Client Error
```

**Fix**: Get approved for Llama 4 access and set your token:
```bash
export HF_TOKEN=hf_your_token_here
huggingface-cli login --token $HF_TOKEN
```

#### Checkpoint Corrupted

If a checkpoint is corrupted after a crash:
```bash
# Delete the bad checkpoint
rm -rf osen_checkpoints/phase_N/checkpoint-XXX

# Resume from the previous good checkpoint
python finetune_osen.py --phase N --resume osen_checkpoints/phase_N/checkpoint-YYY
```

#### Router Routing All to One Expert

After Phase 2, if one expert gets >90% of tokens:
1. Check your training data — make sure each expert has roughly equal samples
2. Increase Phase 2 to 3 epochs
3. Add more negative keywords in `train_router.py`
4. Check the balance loss weight in router training

---

## 11. Quick Cheat Sheet

### Fastest Path to OSEN-1.0

```bash
# 1. Setup (5 min)
chmod +x runpod_setup.sh && ./runpod_setup.sh

# 2. Generate data (10 min)
cd scripts/moe_surgery
python generate_training_data.py --include-cross-expert
cat expert_*.jsonl cross_expert_chains.jsonl > ../../datasets/training.jsonl
cp hard_examples.jsonl ../../datasets/
cd /workspace

# 3. Train (10 hrs on A100)
python finetune_osen.py --phase 1 --model-path meta-llama/Llama-4-Scout-17B-16E-Instruct
python finetune_osen.py --phase 2
python finetune_osen.py --phase 3
python finetune_osen.py --phase 4 --dataset datasets/hard_examples.jsonl --merge

# 4. Done! Model at osen_checkpoints/osen-1.0-merged/
```

### Key Numbers to Remember

| What | Best Value |
|---|---|
| Samples per expert | **1,500** |
| Cross-expert samples | **500** |
| Total dataset size | **6,700+** |
| Phase 1 LR | **2e-5** |
| Phase 2 LR | **1e-5** |
| Phase 3 LR | **5e-6** |
| Phase 4 LR | **1e-6** |
| Effective batch | **16** |
| Context length | **4096** |
| LoRA rank (expert) | **32** |
| LoRA rank (router) | **16** |
| LoRA rank (full) | **64** |
| Best GPU | **A100 80GB** |
| Total training time | **~10 hrs (A100)** |

### Dataset Quality Checklist

- [ ] 1,500+ samples per expert
- [ ] 500+ cross-expert chain examples
- [ ] 200+ hard/adversarial examples
- [ ] 20–30% multi-turn (5+ turns)
- [ ] 15–20% Korean language
- [ ] Each sample has system + user + assistant (3+ turns)
- [ ] No duplicate samples
- [ ] Realistic coordinates (not round numbers)
- [ ] Error/failure scenarios included

---

*OSEN-1.0 by ogenti — AI agents that control your computer.*
