#!/bin/bash
# ================================================================
# OSEN-1.0 RunPod Setup Script
# 
# Run this on a fresh RunPod GPU pod to set up the environment.
# Recommended pod: A100 80GB SXM or H100 80GB
# Template: RunPod PyTorch 2.2+ / CUDA 12+
#
# Usage:
#   chmod +x runpod_setup.sh && ./runpod_setup.sh
# ================================================================

set -e

echo "=========================================="
echo "  OSEN-1.0 RunPod Environment Setup"
echo "=========================================="

# 1. System info
echo ""
echo "[1/7] Checking system..."
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader
python3 -c "import torch; print(f'PyTorch: {torch.__version__}, CUDA: {torch.cuda.is_available()}')"

# 2. Install dependencies
echo ""
echo "[2/7] Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements_finetune.txt

# 3. Login to HuggingFace (for gated model access)
echo ""
echo "[3/7] HuggingFace login..."
if [ -z "$HF_TOKEN" ]; then
    echo "WARNING: HF_TOKEN not set. Set it with: export HF_TOKEN=your_token"
    echo "You need access to meta-llama/Llama-4-Scout-17B-16E-Instruct"
else
    huggingface-cli login --token "$HF_TOKEN" 2>/dev/null
    unset HF_TOKEN  # Remove from environment after login to prevent leakage
    echo "Logged in to HuggingFace."
fi

# 4. Setup wandb (optional)
echo ""
echo "[4/7] Weights & Biases setup..."
if [ -z "$WANDB_API_KEY" ]; then
    echo "WANDB_API_KEY not set. Training will log locally only."
    echo "To enable W&B: export WANDB_API_KEY=your_key"
else
    wandb login $WANDB_API_KEY 2>/dev/null || true
    echo "W&B configured."
fi

# 5. Create output directories
echo ""
echo "[5/7] Creating directories..."
mkdir -p osen_checkpoints/phase_1
mkdir -p osen_checkpoints/phase_2
mkdir -p osen_checkpoints/phase_3
mkdir -p osen_checkpoints/osen-1.0-merged
mkdir -p datasets
echo "Directories created."

# 6. Verify dataset
echo ""
echo "[6/7] Checking dataset..."
if [ -f "datasets/training.jsonl" ]; then
    SAMPLE_COUNT=$(wc -l < datasets/training.jsonl)
    echo "Found training.jsonl with $SAMPLE_COUNT samples."
    if [ "$SAMPLE_COUNT" -lt 100 ]; then
        echo "WARNING: Only $SAMPLE_COUNT samples. Recommend 1000+ for quality fine-tuning."
    fi
else
    echo "WARNING: datasets/training.jsonl not found!"
    echo "Upload your dataset or generate it with the Discord bot /gen command."
    echo "Then copy training.jsonl here."
fi

# 7. Dry run test
echo ""
echo "[7/7] Environment validation..."
python3 -c "
import torch
from transformers import AutoTokenizer
print(f'  torch: {torch.__version__}')
print(f'  CUDA available: {torch.cuda.is_available()}')
print(f'  GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else \"N/A\"}')
print(f'  VRAM: {torch.cuda.get_device_properties(0).total_mem / 1024**3:.1f} GB' if torch.cuda.is_available() else '  VRAM: N/A')

try:
    from peft import LoraConfig
    print('  peft: OK')
except: print('  peft: MISSING')

try:
    from trl import SFTTrainer
    print('  trl: OK')
except: print('  trl: MISSING')

try:
    import bitsandbytes
    print('  bitsandbytes: OK')
except: print('  bitsandbytes: MISSING')

try:
    from datasets import Dataset
    print('  datasets: OK')
except: print('  datasets: MISSING')
"

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "To start training:"
echo "  Phase 1 (Expert Warmup):"
echo "    python3 finetune_osen.py --phase 1 --model-path meta-llama/Llama-4-Scout-17B-16E-Instruct"
echo ""
echo "  Phase 2 (Router Calibration):"
echo "    python3 finetune_osen.py --phase 2"
echo ""
echo "  Phase 3 (Full Fine-tune + Merge):"
echo "    python3 finetune_osen.py --phase 3 --merge"
echo ""
echo "Environment variables:"
echo "  HF_TOKEN       — HuggingFace access token (required for Llama 4)"
echo "  WANDB_API_KEY  — Weights & Biases API key (optional, for logging)"
echo ""
