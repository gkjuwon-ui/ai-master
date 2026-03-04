"""Generate ultimate Colab v3 notebook — bulletproof, self-contained."""
import nbformat as nbf
import os

nb = nbf.v4.new_notebook()
nb.metadata = {
    "colab": {
        "provenance": [],
        "gpuType": "A100",
        "machine_shape": "hm",
    },
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
    "language_info": {"name": "python"},
    "accelerator": "GPU",
}

cells = []

# ═══════════════════════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell(
    "# OGENTI A100 Scout Training v3 — Complete Edition\n"
    "**양자화 모델 + 인라인 학습 + 실시간 출력**\n\n"
    "| Spec | Value |\n"
    "|------|-------|\n"
    "| Model | unsloth/Llama-4-Scout-17B-16E-Instruct-unsloth-bnb-4bit (~60GB) |\n"
    "| GPU | A100 80GB |\n"
    "| Training | MAPPO 1200 episodes, 5 phases |\n"
    "| LoRA | r=16, alpha=32, QLoRA on q/k/v/o_proj |\n"
))

# ═══════════════════════════════════════════════════════════════
# CELL 1: EVERYTHING — one giant cell, no confusion
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell(
    "## Run This One Cell — Does Everything\n"
    "1. Cleans disk\n"
    "2. Installs packages\n" 
    "3. Logs into HuggingFace\n"
    "4. Clones repo\n"
    "5. Downloads model (~60GB, 3-5 min)\n"
    "6. Trains 1200 episodes\n"
    "7. Saves results\n\n"
    "**⬇️ HF_TOKEN만 수정하고 실행! ⬇️**"
))

cells.append(nbf.v4.new_code_cell(r'''# ╔══════════════════════════════════════════════════════════════╗
# ║  OGENTI A100 Scout — Complete Training Pipeline v3         ║
# ╚══════════════════════════════════════════════════════════════╝

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ⬇️⬇️⬇️ 여기에 본인 HF 토큰 ⬇️⬇️⬇️
HF_TOKEN = "hf_여기에_토큰_붙여넣기"
# ⬆️⬆️⬆️ https://huggingface.co/settings/tokens ⬆️⬆️⬆️
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

import os, sys, time, shutil, subprocess, glob, json

# Force unbuffered output (Colab 출력 즉시 표시)
os.environ["PYTHONUNBUFFERED"] = "1"

def flush_print(*args, **kwargs):
    """Print that always flushes (Colab-safe)."""
    print(*args, **kwargs, flush=True)

# ═══════════════════════════════════════════════════════════════
# PHASE 1: Clean Slate
# ═══════════════════════════════════════════════════════════════
flush_print("=" * 60)
flush_print("  PHASE 1: Disk Cleanup")
flush_print("=" * 60)

for path in [
    os.path.expanduser("~/.cache/huggingface"),
    "/root/.cache/huggingface",
    "/content/.cache",
    "/content/ai-master",
]:
    if os.path.exists(path):
        try:
            sz = sum(os.path.getsize(os.path.join(d,f)) for d,_,fs in os.walk(path) for f in fs) / 1e9
            shutil.rmtree(path)
            flush_print(f"  🗑️ {path} ({sz:.1f} GB)")
        except Exception as e:
            flush_print(f"  ⚠️ {path}: {e}")

total, used, free = shutil.disk_usage("/content")
flush_print(f"  📊 Disk: {used/1e9:.0f}/{total/1e9:.0f} GB (free: {free/1e9:.0f} GB)")

# ═══════════════════════════════════════════════════════════════
# PHASE 2: GPU Check
# ═══════════════════════════════════════════════════════════════
flush_print()
flush_print("=" * 60)
flush_print("  PHASE 2: GPU Check")
flush_print("=" * 60)

import torch
assert torch.cuda.is_available(), "❌ No GPU! Change runtime to A100"
gpu_name = torch.cuda.get_device_name(0)
gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
flush_print(f"  ✅ {gpu_name} ({gpu_mem:.0f} GB)")

# ═══════════════════════════════════════════════════════════════
# PHASE 3: Install Dependencies
# ═══════════════════════════════════════════════════════════════
flush_print()
flush_print("=" * 60)
flush_print("  PHASE 3: Installing Packages")
flush_print("=" * 60)

subprocess.run(
    [sys.executable, "-m", "pip", "install", "-q",
     "transformers>=4.45.0", "accelerate", "peft>=0.7.0",
     "bitsandbytes>=0.41.0", "datasets", "sentencepiece", "protobuf", "tqdm"],
    check=True, capture_output=True
)
import transformers, peft, bitsandbytes
flush_print(f"  ✅ transformers={transformers.__version__}")
flush_print(f"  ✅ peft={peft.__version__}")
flush_print(f"  ✅ bitsandbytes={bitsandbytes.__version__}")

# ═══════════════════════════════════════════════════════════════
# PHASE 4: HuggingFace Login
# ═══════════════════════════════════════════════════════════════
flush_print()
flush_print("=" * 60)
flush_print("  PHASE 4: HuggingFace Login")
flush_print("=" * 60)

os.environ["HF_TOKEN"] = HF_TOKEN
os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN

from huggingface_hub import login
login(token=HF_TOKEN)
flush_print("  ✅ HuggingFace logged in")

# ═══════════════════════════════════════════════════════════════
# PHASE 5: Clone Repo
# ═══════════════════════════════════════════════════════════════
flush_print()
flush_print("=" * 60)
flush_print("  PHASE 5: Clone Repository")
flush_print("=" * 60)

repo_path = "/content/ai-master"
subprocess.run(
    ["git", "clone", "https://github.com/gkjuwon-ui/ai-master.git", repo_path],
    check=True, capture_output=True
)
flush_print(f"  ✅ Cloned to {repo_path}")

# Add to Python path
sys.path.insert(0, repo_path)
os.chdir(repo_path)

# Verify imports
import ogenti_core
import ogenti_train
flush_print("  ✅ ogenti_core + ogenti_train imported")

# ═══════════════════════════════════════════════════════════════
# PHASE 6: Configure Logging (REAL-TIME output for Colab)
# ═══════════════════════════════════════════════════════════════
import logging

# Clear ALL existing handlers
root_logger = logging.getLogger()
for handler in root_logger.handlers[:]:
    root_logger.removeHandler(handler)

# Custom handler that always flushes
class FlushStreamHandler(logging.StreamHandler):
    def emit(self, record):
        try:
            msg = self.format(record)
            self.stream.write(msg + self.terminator)
            self.stream.flush()
        except Exception:
            self.handleError(record)

# Set up with flush handler
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        FlushStreamHandler(sys.stdout),
        logging.FileHandler("training.log", mode="w", encoding="utf-8"),
    ],
    force=True,
)

# Also make ogenti loggers use our handler
for name in ["ogenti", "ogenti_core", "ogenti_train", "ogenti.production"]:
    lg = logging.getLogger(name)
    lg.setLevel(logging.INFO)
    lg.propagate = True

logger = logging.getLogger("ogenti.colab")

# ═══════════════════════════════════════════════════════════════
# PHASE 7: TRAIN
# ═══════════════════════════════════════════════════════════════
flush_print()
flush_print("=" * 60)
flush_print("  PHASE 7: 🚀 TRAINING START")
flush_print("=" * 60)
flush_print()

from ogenti_train.config import TrainConfig
from ogenti_train.train import OgentiTrainer
from ogenti_train.server import TrainerBridge, start_server_background

config = TrainConfig.load("configs/a100_scout.json")

flush_print(f"  Model:    {config.encoder.model_name}")
flush_print(f"  Episodes: {config.total_episodes}")
flush_print(f"  Phases:   {len(config.phases)}")
flush_print(f"  LoRA:     r={config.encoder.lora_rank}, α={config.encoder.lora_alpha}")
flush_print(f"  Quant:    {config.encoder.quantization or 'pre-quantized (bnb-4bit)'}")
flush_print()

# ── Start Dashboard Server ──
flush_print("  🖥️ Starting live dashboard server...")
bridge = TrainerBridge()
server_thread = start_server_background(bridge, host="0.0.0.0", port=8000)
time.sleep(1)

# Colab proxy URL for dashboard access
try:
    from google.colab.output import serve_kernel_port_as_iframe
    flush_print("  ✅ Dashboard server running on port 8000")
    flush_print("  📊 Dashboard will open below after model loads!")
except ImportError:
    flush_print("  ✅ Dashboard: http://localhost:8000")

flush_print()
flush_print("  ⏳ Loading model (60GB download, ~5 min)...")
flush_print()

trainer = OgentiTrainer(config, bridge=bridge)
trainer.setup()

flush_print()
flush_print("  ✅ Model loaded! Starting training loop...")

# Open dashboard in Colab iframe
try:
    from google.colab.output import serve_kernel_port_as_iframe
    serve_kernel_port_as_iframe(8000, height=600)
    flush_print("  📊 Dashboard opened above ↑↑↑")
except ImportError:
    flush_print("  📊 Dashboard: http://localhost:8000")
flush_print()

start_time = time.time()

try:
    trainer.train()
except KeyboardInterrupt:
    flush_print("\n⚠️ Training interrupted by user")
except Exception as e:
    flush_print(f"\n❌ Training error: {e}")
    import traceback
    traceback.print_exc()
    raise

elapsed = time.time() - start_time

flush_print()
flush_print("=" * 60)
flush_print(f"  ✅ TRAINING COMPLETE!")
flush_print(f"  Episodes:   {trainer.global_episode}")
flush_print(f"  Time:       {elapsed/60:.1f} min")
flush_print(f"  Best Reward: {trainer.best_reward:.4f}")
if elapsed > 0:
    flush_print(f"  Speed:      {trainer.global_episode/elapsed:.2f} ep/s")
flush_print("=" * 60)

# ═══════════════════════════════════════════════════════════════
# PHASE 8: Save Results
# ═══════════════════════════════════════════════════════════════
flush_print()
flush_print("=" * 60)
flush_print("  PHASE 8: Saving Results")
flush_print("=" * 60)

# Summary
results = {
    "model": config.encoder.model_name,
    "total_episodes": trainer.global_episode,
    "elapsed_min": round(elapsed / 60, 2),
    "best_reward": round(trainer.best_reward, 4),
    "gpu": gpu_name,
    "gpu_memory_gb": round(gpu_mem, 1),
}
with open("training_results.json", "w") as f:
    json.dump(results, f, indent=2)
flush_print(f"  📊 Results saved to training_results.json")

# List checkpoints
ckpts = sorted(glob.glob("checkpoints/**/*", recursive=True))
flush_print(f"  📁 Checkpoints: {len(ckpts)} files")

# training.log stats
if os.path.exists("training.log"):
    with open("training.log") as f:
        lines = f.readlines()
    flush_print(f"  📋 Training log: {len(lines)} lines")
    flush_print()
    flush_print("  --- Last 15 lines ---")
    for line in lines[-15:]:
        flush_print(f"  {line.rstrip()}")

flush_print()
flush_print("🎉 ALL DONE! 결과를 다운로드하려면 다음 셀 실행")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 2: Download Results
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## 결과 다운로드 (학습 완료 후 실행)"))
cells.append(nbf.v4.new_code_cell('''import shutil, os

os.chdir("/content/ai-master")

# Zip everything
ckpt_dir = "checkpoints/a100_scout"
if os.path.exists(ckpt_dir):
    shutil.make_archive("/content/ogenti_results", "zip", ckpt_dir)
    print(f"✅ Checkpoints zipped: /content/ogenti_results.zip", flush=True)

# Copy log
if os.path.exists("training.log"):
    shutil.copy("training.log", "/content/training.log")

if os.path.exists("training_results.json"):
    shutil.copy("training_results.json", "/content/training_results.json")

# Auto-download
try:
    from google.colab import files
    if os.path.exists("/content/ogenti_results.zip"):
        files.download("/content/ogenti_results.zip")
    files.download("/content/training_results.json")
    print("📥 Download started!", flush=True)
except:
    print("📁 File browser에서 직접 다운로드하세요", flush=True)
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 3: Monitor (run during training in separate tab)
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## 학습 모니터링 (학습 중 다른 셀에서 실행 가능)"))
cells.append(nbf.v4.new_code_cell('''# 학습 중 상태 확인 — 언제든 실행 가능
import os, torch

os.chdir("/content/ai-master")

# GPU
if torch.cuda.is_available():
    alloc = torch.cuda.memory_allocated() / 1e9
    total = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"🔥 GPU: {alloc:.1f} / {total:.0f} GB", flush=True)

# Log
if os.path.exists("training.log"):
    with open("training.log") as f:
        lines = f.readlines()
    print(f"\\n📋 Log: {len(lines)} lines, last 20:", flush=True)
    for l in lines[-20:]:
        print(f"  {l.rstrip()}", flush=True)
else:
    print("⏳ training.log not yet created", flush=True)

# Checkpoints
import glob
ckpts = glob.glob("checkpoints/**/*.json", recursive=True)
print(f"\\n📁 Checkpoint files: {len(ckpts)}", flush=True)

# Disk
import shutil
_, used, free = shutil.disk_usage("/content")
print(f"💾 Disk: used {used/1e9:.0f} GB, free {free/1e9:.0f} GB", flush=True)
'''))

# Build
nb.cells = cells
output_path = "notebooks/ogenti_a100_scout_v3.ipynb"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
nbf.write(nb, output_path)

print(f"✅ Generated: {output_path}")
print(f"   Cells: {len(cells)} ({sum(1 for c in cells if c.cell_type == 'code')} code, {sum(1 for c in cells if c.cell_type == 'markdown')} markdown)")
