"""Generate clean Colab v2 notebook — inline training, no subprocess."""
import nbformat as nbf

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
# CELL 0: Title
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell(
    "# OGENTI A100 Scout Training v2\n"
    "**Clean start — inline training, no subprocess issues**\n\n"
    "| Spec | Value |\n"
    "|------|-------|\n"
    "| Model | Llama 4 Scout 109B MoE (QLoRA 4-bit) |\n"
    "| GPU | A100 80GB |\n"
    "| Training | MAPPO 1200 episodes, 5 phases |\n"
))

# ═══════════════════════════════════════════════════════════════
# CELL 1: Clean Slate — nuke all old caches
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 1: Clean Slate"))
cells.append(nbf.v4.new_code_cell('''# ============================================================
# STEP 1: 디스크 정리 — 이전 실패한 캐시 전부 삭제
# ============================================================
import os, shutil, subprocess

print("🧹 이전 캐시 정리 중...")

# 삭제 대상 디렉토리
targets = [
    os.path.expanduser("~/.cache/huggingface"),
    "/root/.cache/huggingface",
    "/content/.cache",
    "/tmp/hf_cache",
    "/content/ai-master",      # 이전 클론도 삭제
    "/content/ai_master",
]

total_freed = 0
for path in targets:
    if os.path.exists(path):
        try:
            size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, dn, fns in os.walk(path)
                for f in fns
            ) / (1024**3)
            shutil.rmtree(path)
            total_freed += size
            print(f"  🗑️ {path} ({size:.1f} GB)")
        except Exception as e:
            print(f"  ⚠️ {path}: {e}")

print(f"\\n✅ 총 {total_freed:.1f} GB 확보!")

# 디스크 상태 확인
result = subprocess.run(["df", "-h", "/content"], capture_output=True, text=True)
print(f"\\n📊 디스크 현황:\\n{result.stdout}")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 2: GPU Check
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 2: GPU 확인"))
cells.append(nbf.v4.new_code_cell('''import torch

if not torch.cuda.is_available():
    raise RuntimeError("❌ GPU 없음! Runtime > Change runtime type > A100 선택")

gpu_name = torch.cuda.get_device_name(0)
gpu_mem = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"✅ GPU: {gpu_name}")
print(f"✅ VRAM: {gpu_mem:.1f} GB")

if gpu_mem < 70:
    print("⚠️ A100 80GB가 아님! Runtime 변경 필요")
else:
    print("🎯 A100 80GB 확인!")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 3: Install Dependencies
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 3: 패키지 설치"))
cells.append(nbf.v4.new_code_cell('''%%capture install_output
!pip install -q transformers>=4.45.0 accelerate peft>=0.7.0 bitsandbytes>=0.41.0
!pip install -q datasets sentencepiece protobuf tqdm
!pip install -q torch torchvision --upgrade -q 2>/dev/null || true

import transformers, peft, bitsandbytes
print(f"✅ transformers={transformers.__version__}")
print(f"✅ peft={peft.__version__}")
print(f"✅ bitsandbytes={bitsandbytes.__version__}")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 4: HuggingFace Login
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 4: HuggingFace 로그인"))
cells.append(nbf.v4.new_code_cell('''import os

# ⬇️⬇️⬇️ 여기에 본인 HF 토큰 붙여넣기 ⬇️⬇️⬇️
HF_TOKEN = "hf_여기에_본인_토큰_붙여넣기"
# ⬆️⬆️⬆️ https://huggingface.co/settings/tokens 에서 발급 ⬆️⬆️⬆️

# 모든 방법으로 토큰 설정 (subprocess에서도 쓰일 수 있도록)
os.environ["HF_TOKEN"] = HF_TOKEN
os.environ["HUGGING_FACE_HUB_TOKEN"] = HF_TOKEN

from huggingface_hub import login
login(token=HF_TOKEN)
print("✅ HuggingFace 로그인 완료!")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 5: Clone Repo
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 5: 레포 클론"))
cells.append(nbf.v4.new_code_cell('''import os, subprocess

repo_url = "https://github.com/gkjuwon-ui/ai-master.git"
repo_path = "/content/ai-master"

if os.path.exists(repo_path):
    print("🔄 기존 레포 업데이트...")
    subprocess.run(["git", "pull"], cwd=repo_path, check=True)
else:
    print("📥 레포 클론 중...")
    subprocess.run(["git", "clone", repo_url, repo_path], check=True)

print(f"✅ 레포 준비 완료: {repo_path}")

# Python path에 추가
import sys
if repo_path not in sys.path:
    sys.path.insert(0, repo_path)

# 확인
import ogenti_core
print(f"✅ ogenti_core 임포트 성공!")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 6: Disk Budget Check
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 6: 디스크 용량 체크"))
cells.append(nbf.v4.new_code_cell('''import shutil, subprocess

total, used, free = shutil.disk_usage("/content")
free_gb = free / (1024**3)
total_gb = total / (1024**3)
used_gb = used / (1024**3)

print(f"📊 디스크: {used_gb:.1f} / {total_gb:.1f} GB (잔여 {free_gb:.1f} GB)")
print()

# Llama 4 Scout 109B = 약 55-60GB (4-bit quantized weights)
# 실제 다운로드: safetensor shards ~100GB, but HF caches efficiently
MODEL_NEED_GB = 110

if free_gb >= MODEL_NEED_GB:
    print(f"✅ 충분! 모델 다운로드에 ~{MODEL_NEED_GB}GB 필요, {free_gb:.0f}GB 여유")
else:
    shortage = MODEL_NEED_GB - free_gb
    print(f"⚠️ 부족할 수 있음! ~{shortage:.0f}GB 더 필요")
    print(f"   옵션 1: Colab Pro+ 업그레이드 (더 큰 디스크)")
    print(f"   옵션 2: 아래 Google Drive 캐시 셀 실행")

result = subprocess.run(["df", "-h", "/content"], capture_output=True, text=True)
print(f"\\n{result.stdout}")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 7: (Optional) Google Drive Cache
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell(
    "## Step 6.5: (선택) Google Drive에 캐시 저장\n"
    "디스크 부족 시에만 실행. 충분하면 건너뛰기."
))
cells.append(nbf.v4.new_code_cell('''# ⚠️ 디스크 부족할 때만 실행! 충분하면 이 셀 건너뛰기!
import os

from google.colab import drive
drive.mount("/content/drive")

cache_dir = "/content/drive/MyDrive/hf_cache"
os.makedirs(cache_dir, exist_ok=True)
os.environ["HF_HOME"] = cache_dir
os.environ["TRANSFORMERS_CACHE"] = cache_dir
os.environ["HF_HUB_CACHE"] = os.path.join(cache_dir, "hub")

print(f"✅ HF 캐시 → Google Drive: {cache_dir}")
print(f"   로컬 디스크를 아끼면서 모델을 Google Drive에 저장합니다")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 8: TRAINING — Direct Inline (NO subprocess!)
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell(
    "## Step 7: 🚀 학습 시작 (Direct Inline)\n"
    "**subprocess 없이 직접 실행 — 환경변수 문제 원천 차단!**"
))
cells.append(nbf.v4.new_code_cell('''# ============================================================
# 🚀 OGENTI Training — Direct Inline (No Subprocess!)
# ============================================================
import os, sys, time, logging

# Ensure repo is on path
repo_path = "/content/ai-master"
if repo_path not in sys.path:
    sys.path.insert(0, repo_path)
os.chdir(repo_path)

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("training.log", mode="a", encoding="utf-8"),
    ],
    force=True,
)
logger = logging.getLogger("ogenti.production")

# ── GPU Info ──
import torch
info = {
    "python": sys.version.split()[0],
    "torch": torch.__version__,
    "cuda": torch.cuda.is_available(),
    "gpu_count": torch.cuda.device_count(),
    "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "N/A",
    "gpu_memory_gb": round(torch.cuda.get_device_properties(0).total_memory / 1e9, 1) if torch.cuda.is_available() else 0,
}

print("=" * 60)
print("   OGENTI — A100 Scout Production Training")
print("=" * 60)
print(f"  GPU:     {info['gpu_count']}× {info['gpu_name']} ({info['gpu_memory_gb']}GB)")
print(f"  PyTorch: {info['torch']}")
print(f"  Python:  {info['python']}")
print(f"  CUDA:    {info['cuda']}")
print("=" * 60)

# ── Load Config ──
from ogenti_train.config import TrainConfig

config_path = "configs/a100_scout.json"
logger.info("Loading config: %s", config_path)
config = TrainConfig.load(config_path)

print(f"  Model:     {config.encoder.model_name}")
print(f"  Episodes:  {config.total_episodes}")
print(f"  Phases:    {len(config.phases)}")
print(f"  LoRA:      r={config.encoder.lora_rank}, α={config.encoder.lora_alpha}")
print(f"  Quant:     {config.encoder.quantization}")
print("=" * 60)

# ── Launch Training (Inline!) ──
from ogenti_train.train import OgentiTrainer

trainer = OgentiTrainer(config, bridge=None)
logger.info("Setting up trainer (model download may take 10-20 min)...")
trainer.setup()

logger.info("═══ Starting training loop ═══")
start = time.time()

try:
    trainer.train()
except KeyboardInterrupt:
    logger.info("Training interrupted by user.")
except Exception as e:
    logger.exception("Training failed: %s", e)
    raise

elapsed = time.time() - start
print()
print("=" * 60)
print(f"✅ DONE! {trainer.global_episode} episodes in {elapsed/60:.1f} min")
print(f"   Speed: {trainer.global_episode / elapsed:.1f} ep/s" if elapsed > 0 else "")
print("=" * 60)
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 9: Results
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 8: 결과 확인"))
cells.append(nbf.v4.new_code_cell('''import os, json, glob
repo_path = "/content/ai-master"

# Find latest checkpoint
ckpt_dirs = sorted(glob.glob(os.path.join(repo_path, "checkpoints/a100_scout/episode_*")))
if not ckpt_dirs:
    ckpt_dirs = sorted(glob.glob(os.path.join(repo_path, "checkpoints/**/episode_*"), recursive=True))

if ckpt_dirs:
    latest = ckpt_dirs[-1]
    print(f"📁 Latest checkpoint: {latest}")
    
    # Look for metrics
    metrics_file = os.path.join(latest, "metrics.json")
    if os.path.exists(metrics_file):
        with open(metrics_file) as f:
            metrics = json.load(f)
        print(f"\\n📊 Training Results:")
        for k, v in metrics.items():
            if isinstance(v, float):
                print(f"  {k}: {v:.4f}")
            else:
                print(f"  {k}: {v}")
else:
    print("⏳ No checkpoints yet. Training may still be running or hasn't started.")

# Check training log
log_path = os.path.join(repo_path, "training.log")
if os.path.exists(log_path):
    print(f"\\n📋 Last 20 lines of training.log:")
    with open(log_path) as f:
        lines = f.readlines()
    for line in lines[-20:]:
        print(f"  {line.rstrip()}")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 10: Download Results
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 9: 결과 다운로드"))
cells.append(nbf.v4.new_code_cell('''import shutil, os

repo_path = "/content/ai-master"
ckpt_dir = os.path.join(repo_path, "checkpoints/a100_scout")

if os.path.exists(ckpt_dir):
    # Zip checkpoints
    archive_path = "/content/ogenti_a100_scout_results"
    shutil.make_archive(archive_path, "zip", ckpt_dir)
    print(f"✅ 체크포인트 압축: {archive_path}.zip")
    
    # Auto-download
    try:
        from google.colab import files
        files.download(f"{archive_path}.zip")
        print("📥 다운로드 시작!")
    except:
        print("📁 파일 브라우저에서 직접 다운로드하세요")
else:
    print("❌ 체크포인트 없음")

# Also save training log
log_path = os.path.join(repo_path, "training.log")
if os.path.exists(log_path):
    shutil.copy(log_path, "/content/training.log")
    print("📋 training.log → /content/training.log")
'''))

# ═══════════════════════════════════════════════════════════════
# CELL 11: Google Drive Backup
# ═══════════════════════════════════════════════════════════════
cells.append(nbf.v4.new_markdown_cell("## Step 10: (선택) Google Drive 백업"))
cells.append(nbf.v4.new_code_cell('''# Google Drive가 마운트 되어있다면 백업
import os, shutil

drive_save = "/content/drive/MyDrive/ogenti_results"
ckpt_dir = "/content/ai-master/checkpoints/a100_scout"

if os.path.exists("/content/drive/MyDrive") and os.path.exists(ckpt_dir):
    os.makedirs(drive_save, exist_ok=True)
    shutil.copytree(ckpt_dir, os.path.join(drive_save, "checkpoints"), dirs_exist_ok=True)
    
    log_path = "/content/ai-master/training.log"
    if os.path.exists(log_path):
        shutil.copy(log_path, os.path.join(drive_save, "training.log"))
    
    print(f"✅ Google Drive 백업 완료: {drive_save}")
else:
    print("⚠️ Google Drive 미마운트 또는 체크포인트 없음")
'''))

# ═══════════════════════════════════════════════════════════════
# Build notebook
# ═══════════════════════════════════════════════════════════════
nb.cells = cells

import os
output_path = "notebooks/ogenti_a100_scout_v2.ipynb"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
nbf.write(nb, output_path)

print(f"✅ Generated: {output_path}")
print(f"   Cells: {len(cells)} ({sum(1 for c in cells if c.cell_type == 'code')} code, {sum(1 for c in cells if c.cell_type == 'markdown')} markdown)")
