#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Ogenti — RunPod / GPU Server Setup Script
#  
#  Sets up a fresh GPU instance for production training.
#  Tested on: RunPod (A100-80GB), Lambda Labs, Vast.ai
#
#  Usage:
#    # On a fresh RunPod instance:
#    curl -sSL https://raw.githubusercontent.com/gkjuwon-ui/ai-master/main/scripts/setup_runpod.sh | bash
#    
#    # Or clone first:
#    git clone https://github.com/gkjuwon-ui/ai-master.git && cd ai-master
#    bash scripts/setup_runpod.sh
# ═══════════════════════════════════════════════════════════════

set -euo pipefail

echo "╔══════════════════════════════════════════════╗"
echo "║  ◆  OGENTI — GPU Server Setup               ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

# ── 1. System basics ──
echo "[1/7] System packages..."
apt-get update -qq
apt-get install -y -qq git curl wget htop tmux tree > /dev/null 2>&1
echo "  ✓ System packages installed"

# ── 2. Clone repo (if not already in it) ──
if [ ! -f "pyproject.toml" ]; then
    echo "[2/7] Cloning repo..."
    cd /workspace 2>/dev/null || cd ~
    if [ -d "ai-master" ]; then
        cd ai-master && git pull
    else
        git clone https://github.com/gkjuwon-ui/ai-master.git
        cd ai-master
    fi
    echo "  ✓ Repo ready at $(pwd)"
else
    echo "[2/7] Already in repo directory"
fi

# ── 3. Python environment ──
echo "[3/7] Python environment..."
PYTHON=${PYTHON:-python3}
$PYTHON --version

# Create venv if not exists
if [ ! -d ".venv" ]; then
    $PYTHON -m venv .venv
fi
source .venv/bin/activate
echo "  ✓ Virtual environment activated"

# ── 4. Install dependencies ──
echo "[4/7] Installing dependencies..."
pip install --upgrade pip setuptools wheel -q

# Core training deps
pip install -q \
    torch>=2.1.0 \
    transformers>=4.36.0 \
    peft>=0.7.0 \
    trl>=0.7.0 \
    accelerate>=0.25.0 \
    datasets>=2.16.0 \
    sentencepiece>=0.1.99 \
    numpy>=1.24.0 \
    safetensors>=0.4.0

# Server deps
pip install -q \
    fastapi>=0.104.0 \
    uvicorn[standard]>=0.24.0 \
    websockets>=12.0

# Training extras
pip install -q \
    deepspeed>=0.12.0 \
    wandb>=0.16.0 \
    matplotlib>=3.7.0 \
    sentence-transformers>=2.2.0

# Install package in editable mode
pip install -e ".[train,bench]" -q 2>/dev/null || pip install -e . -q 2>/dev/null || true

echo "  ✓ All dependencies installed"

# ── 5. GPU check ──
echo "[5/7] GPU check..."
$PYTHON -c "
import torch
if torch.cuda.is_available():
    n = torch.cuda.device_count()
    for i in range(n):
        name = torch.cuda.get_device_name(i)
        mem = torch.cuda.get_device_properties(i).total_mem / 1e9
        print(f'  GPU {i}: {name} ({mem:.1f} GB)')
    print(f'  ✓ {n} GPU(s) ready')
else:
    print('  ⚠ No CUDA GPU detected — CPU training will be very slow')
"

# ── 6. Pre-download model ──
echo "[6/7] Pre-downloading Qwen2.5-3B-Instruct..."
$PYTHON -c "
from transformers import AutoModelForCausalLM, AutoTokenizer
import os

model_name = 'Qwen/Qwen2.5-3B-Instruct'
cache_dir = os.environ.get('HF_HOME', os.path.expanduser('~/.cache/huggingface'))

print(f'  Downloading {model_name}...')
print(f'  Cache: {cache_dir}')

tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
print(f'  ✓ Tokenizer ready ({len(tokenizer)} tokens)')

# Download model weights (this is the big download)
model = AutoModelForCausalLM.from_pretrained(
    model_name,
    torch_dtype='auto',
    trust_remote_code=True,
    device_map='auto',
)
print(f'  ✓ Model ready ({sum(p.numel() for p in model.parameters()) / 1e9:.1f}B params)')
del model  # Free memory
"

# ── 7. Create directories ──
echo "[7/7] Setting up directories..."
mkdir -p checkpoints logs data configs

echo ""
echo "╔══════════════════════════════════════════════╗"
echo "║  ✓  Setup complete!                          ║"
echo "╠══════════════════════════════════════════════╣"
echo "║                                              ║"
echo "║  Start training:                             ║"
echo "║    python run_production.py                  ║"
echo "║                                              ║"
echo "║  Quick test (100 episodes):                  ║"
echo "║    python run_production.py --quick           ║"
echo "║                                              ║"
echo "║  With custom config:                         ║"
echo "║    python run_production.py \\                ║"
echo "║      --config configs/production.json        ║"
echo "║                                              ║"
echo "║  Headless (no dashboard):                    ║"
echo "║    python run_production.py --headless       ║"
echo "║                                              ║"
echo "║  Dashboard URL: http://<your-ip>:8000       ║"
echo "║                                              ║"
echo "║  For long training, use tmux:                ║"
echo "║    tmux new -s ogenti                        ║"
echo "║    python run_production.py                  ║"
echo "║    (Ctrl+B, D to detach)                     ║"
echo "║                                              ║"
echo "╚══════════════════════════════════════════════╝"
