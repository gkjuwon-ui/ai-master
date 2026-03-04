"""Generate Colab v3 notebook — real token, verbose output, REST-polled dashboard."""
import nbformat as nbf
import os

nb = nbf.v4.new_notebook()
nb.metadata = {
    "colab": {"provenance": [], "gpuType": "A100", "machine_shape": "hm"},
    "kernelspec": {"name": "python3", "display_name": "Python 3"},
    "language_info": {"name": "python"},
    "accelerator": "GPU",
}

cells = []

cells.append(nbf.v4.new_markdown_cell(
    "# 🚀 OGENTI A100 Scout Training v3\n"
    "**pre-quantized 4bit + inline training + REST-polled dashboard**\n\n"
    "| Spec | Value |\n"
    "|------|-------|\n"
    "| Model | unsloth/Llama-4-Scout-17B-16E-Instruct-unsloth-bnb-4bit (~60GB) |\n"
    "| GPU | A100 80GB |\n"
    "| Training | MAPPO 1200 episodes, 5 phases |\n"
    "| Dashboard | iframe + REST polling 2s |\n"
))

# ═══════════════════════════════════════════
# MAIN TRAINING CELL
# ═══════════════════════════════════════════
cells.append(nbf.v4.new_code_cell(r'''# ╔══════════════════════════════════════════════════════════════╗
# ║  OGENTI A100 Scout — All-in-One Training Cell v3           ║
# ╚══════════════════════════════════════════════════════════════╝

HF_TOKEN = "hf_여기에_토큰_붙여넣기"

import os, sys, time, shutil, subprocess, glob, json
os.environ["PYTHONUNBUFFERED"] = "1"

def fp(*a, **kw):
    print(*a, **kw, flush=True)

def banner(step, title):
    fp(f"\n{'='*60}\n  {step}: {title}\n{'='*60}")

# ══════════════════════════════════════════
# 1. DISK CLEANUP
# ══════════════════════════════════════════
banner("STEP 1", "🧹 Disk Cleanup")
for p in [os.path.expanduser("~/.cache/huggingface"), "/root/.cache/huggingface", "/content/.cache", "/content/ai-master"]:
    if os.path.exists(p):
        try: shutil.rmtree(p); fp(f"  🗑️ {p}")
        except: pass
t, u, f_ = shutil.disk_usage("/content")
fp(f"  💾 {f_/1e9:.0f} GB free / {t/1e9:.0f} GB total")

# ══════════════════════════════════════════
# 2. GPU CHECK
# ══════════════════════════════════════════
banner("STEP 2", "🔍 GPU Check")
import torch
assert torch.cuda.is_available(), "❌ No GPU!"
gpu_name = torch.cuda.get_device_name(0)
gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
fp(f"  ✅ {gpu_name} ({gpu_mem:.0f} GB)")

# ══════════════════════════════════════════
# 3. INSTALL
# ══════════════════════════════════════════
banner("STEP 3", "📦 Packages")
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
    "transformers>=4.45.0", "accelerate", "peft>=0.7.0",
    "bitsandbytes>=0.41.0", "datasets", "sentencepiece",
    "protobuf", "tqdm", "uvicorn", "fastapi", "websockets"],
    check=True, capture_output=True)
import transformers, peft, bitsandbytes
fp(f"  ✅ transformers={transformers.__version__}, peft={peft.__version__}, bnb={bitsandbytes.__version__}")

# ══════════════════════════════════════════
# 4. HF LOGIN
# ══════════════════════════════════════════
banner("STEP 4", "🔑 HuggingFace Login")
os.environ["HF_TOKEN"] = HF_TOKEN
os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN
from huggingface_hub import login
login(token=HF_TOKEN)
fp("  ✅ Logged in")

# ══════════════════════════════════════════
# 5. CLONE
# ══════════════════════════════════════════
banner("STEP 5", "📥 Clone Repo")
repo = "/content/ai-master"
subprocess.run(["git", "clone", "https://github.com/gkjuwon-ui/ai-master.git", repo], check=True, capture_output=True)
sys.path.insert(0, repo)
os.chdir(repo)
import ogenti_core, ogenti_train
fp("  ✅ Cloned + imported")

# ══════════════════════════════════════════
# 6. LOGGING
# ══════════════════════════════════════════
import logging
for h in logging.root.handlers[:]:
    logging.root.removeHandler(h)

class _Flush(logging.StreamHandler):
    def emit(self, record):
        try:
            self.stream.write(self.format(record) + "\n")
            self.stream.flush()
        except: pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[_Flush(sys.stdout), logging.FileHandler("training.log", mode="w", encoding="utf-8")],
    force=True,
)
for n in ["ogenti", "ogenti_core", "ogenti_train", "ogenti.production"]:
    logging.getLogger(n).setLevel(logging.INFO)

# ══════════════════════════════════════════
# 7. DASHBOARD SERVER
# ══════════════════════════════════════════
banner("STEP 6", "🖥️ Dashboard Server")

from ogenti_train.config import TrainConfig
from ogenti_train.train import OgentiTrainer
from ogenti_train.server import TrainerBridge, start_server_background

config = TrainConfig.load("configs/a100_scout.json")
config.infra.log_every = 1  # 매 에피소드 출력

bridge = TrainerBridge()
try:
    server_thread = start_server_background(bridge, host="0.0.0.0", port=8000)
    time.sleep(2)
    fp("  ✅ Dashboard server on port 8000")
except Exception as e:
    fp(f"  ⚠️ Dashboard failed: {e}")

# Colab iframe
try:
    from google.colab import output
    output.serve_kernel_port_as_iframe(8000, height=600)
    fp("  📊 Dashboard iframe opened above ↑↑↑")
except Exception as e:
    fp(f"  ⚠️ Iframe: {e}")
    try:
        from google.colab import output as _o
        proxy = _o.eval_js('"https://"+google.colab.kernel.proxyPort(8000, {"cache": false})')
        fp(f"  📊 Dashboard URL: {proxy}")
    except:
        fp("  📊 Dashboard: http://localhost:8000")

# ══════════════════════════════════════════
# 8. TRAINING
# ══════════════════════════════════════════
banner("STEP 7", "🚀 TRAINING")
fp(f"  Model:    {config.encoder.model_name}")
fp(f"  Episodes: {config.total_episodes}")
fp(f"  Phases:   {len(config.phases)}")
fp(f"  Decode tokens: {config.decoder.max_decode_tokens}")
fp(f"  log_every: {config.infra.log_every}")
fp()
fp("  ⏳ 7a: Creating trainer...")
trainer = OgentiTrainer(config, bridge=bridge)

fp("  ⏳ 7b: Loading model (~60GB, 13 shards)...")
fp("       👇 Progress bars below 👇")
fp()
trainer.setup()
fp()
fp(f"  ✅ Model loaded! GPU: {torch.cuda.memory_allocated()/1e9:.1f} GB used")
fp()

# Monkey-patch _log_metrics for forced flush
_orig = trainer._log_metrics
def _patched(metrics):
    _orig(metrics)
    sys.stdout.flush()
    sys.stderr.flush()
trainer._log_metrics = _patched

fp("  🏁 Training loop START!")
fp("  ⚡ 매 에피소드 로그가 아래에 찍힙니다...")
fp()

start = time.time()
try:
    trainer.train()
except KeyboardInterrupt:
    fp("\n⚠️ Interrupted by user")
except Exception as e:
    fp(f"\n❌ Error: {e}")
    import traceback; traceback.print_exc()
    try: trainer._save_checkpoint(tag="error")
    except: pass
    raise

elapsed = time.time() - start
fp()
fp("=" * 60)
fp(f"  🎉 DONE! {trainer.global_episode} episodes in {elapsed/60:.1f}m")
fp(f"  Best Reward: {trainer.best_reward:.4f}")
if elapsed > 0: fp(f"  Speed: {trainer.global_episode/elapsed:.2f} ep/s")
fp("=" * 60)

# ══════════════════════════════════════════
# 9. SAVE RESULTS
# ══════════════════════════════════════════
banner("STEP 8", "💾 Save Results")
results = {"model": config.encoder.model_name, "episodes": trainer.global_episode,
           "elapsed_min": round(elapsed/60,2), "best_reward": round(trainer.best_reward,4),
           "gpu": gpu_name, "vram_gb": round(gpu_mem,1)}
with open("training_results.json", "w") as f:
    json.dump(results, f, indent=2)
fp(f"  📊 Results: {json.dumps(results, indent=2)}")

if os.path.exists("training.log"):
    with open("training.log") as f: lines = f.readlines()
    fp(f"  📋 Log: {len(lines)} lines")
    fp("\n  --- Last 30 lines ---")
    for l in lines[-30:]: fp(f"  {l.rstrip()}")

fp("\n🎉 ALL DONE!")
'''))

# Download cell
cells.append(nbf.v4.new_markdown_cell("## 📦 결과 다운로드"))
cells.append(nbf.v4.new_code_cell('''import shutil, os
os.chdir("/content/ai-master")
if os.path.exists("checkpoints/a100_scout"):
    shutil.make_archive("/content/ogenti_results", "zip", "checkpoints/a100_scout")
    print("✅ Zipped checkpoints", flush=True)
for f in ["training.log", "training_results.json"]:
    if os.path.exists(f): shutil.copy(f, f"/content/{f}")
try:
    from google.colab import files
    for f in ["/content/ogenti_results.zip", "/content/training_results.json", "/content/training.log"]:
        if os.path.exists(f): files.download(f)
except: print("📁 File browser에서 다운로드하세요", flush=True)
'''))

# Monitor cell
cells.append(nbf.v4.new_markdown_cell("## 🔍 모니터링 (학습 중 다른 셀에서 실행)"))
cells.append(nbf.v4.new_code_cell('''import os, torch, json
os.chdir("/content/ai-master")
if torch.cuda.is_available():
    alloc = torch.cuda.memory_allocated()/1e9
    total = torch.cuda.get_device_properties(0).total_memory/1e9
    print(f"🖥️ GPU: {alloc:.1f}/{total:.0f}GB ({alloc/total*100:.0f}%)", flush=True)
if os.path.exists("training.log"):
    with open("training.log") as f: lines = f.readlines()
    print(f"📋 Log: {len(lines)} lines", flush=True)
    print("--- Last 30 ---", flush=True)
    for l in lines[-30:]: print(f"  {l.rstrip()}", flush=True)
if os.path.exists("training_results.json"):
    with open("training_results.json") as f: print(f"📊 Results: {f.read()}", flush=True)
'''))

nb.cells = cells
output_path = "notebooks/ogenti_a100_scout_v3.ipynb"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
nbf.write(nb, output_path)
print(f"✅ Generated: {output_path} ({len(cells)} cells)")
