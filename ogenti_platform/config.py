"""O Series Platform Configuration — Ogenti (Text) + Ovisen (Image)"""
import os
import secrets

# ── Railway detection ──
_ON_RAILWAY = bool(os.getenv("RAILWAY_ENVIRONMENT"))

# ── Server ──
HOST = os.getenv("OGENTI_HOST", "0.0.0.0")
PORT = int(os.getenv("OGENTI_PORT", "8080"))
SECRET_KEY = os.getenv("OGENTI_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30  # 30 days

# ── Database ──
# Railway: use persistent volume (/data) so DB survives redeploys
_default_db = "sqlite:////data/ogenti.db" if _ON_RAILWAY else "sqlite:///./ogenti_platform/ogenti.db"
DATABASE_URL = os.getenv("DATABASE_URL", _default_db)

# ── Resend (email) ──
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "re_test_xxxxxxxxxxxx")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@oseries.io")

# ── Stripe ──
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_xxxxxxxxxxxx")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "pk_test_xxxxxxxxxxxx")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_test_xxxxxxxxxxxx")

# ── Pricing (credits) ──
CREDIT_PACKAGES = [
    {"id": "starter",    "credits": 1_000,  "price_cents": 500,   "label": "1K Credits",  "price_display": "$5"},
    {"id": "builder",    "credits": 5_000,  "price_cents": 2_000, "label": "5K Credits",  "price_display": "$20"},
    {"id": "pro",        "credits": 20_000, "price_cents": 6_000, "label": "20K Credits", "price_display": "$60"},
    {"id": "enterprise", "credits": 100_000,"price_cents": 25_000,"label": "100K Credits","price_display": "$250"},
]

# ── Model Pricing (credits per episode) ──
MODEL_COSTS = {
    "qwen2.5-3b":   {"credits_per_episode": 1,  "label": "Qwen2.5-3B",   "vram": "8GB",  "speed": "Fast"},
    "qwen2.5-7b":   {"credits_per_episode": 3,  "label": "Qwen2.5-7B",   "vram": "16GB", "speed": "Medium"},
    "qwen2.5-14b":  {"credits_per_episode": 8,  "label": "Qwen2.5-14B",  "vram": "32GB", "speed": "Slow"},
    "llama3.2-3b":  {"credits_per_episode": 1,  "label": "LLaMA-3.2-3B", "vram": "8GB",  "speed": "Fast"},
    "llama3.2-8b":  {"credits_per_episode": 4,  "label": "LLaMA-3.2-8B", "vram": "20GB", "speed": "Medium"},
    "mistral-7b":   {"credits_per_episode": 3,  "label": "Mistral-7B",   "vram": "16GB", "speed": "Medium"},
    "custom":       {"credits_per_episode": 2,  "label": "Custom (User)", "vram": "Varies","speed": "Varies"},
}

# ── Tiers ──
TIERS = {
    "free":       {"label": "Free",       "monthly_credits": 100,   "max_episodes": 500,    "models": ["qwen2.5-3b"]},
    "starter":    {"label": "Starter",    "monthly_credits": 1_000, "max_episodes": 5_000,  "models": ["qwen2.5-3b", "llama3.2-3b"]},
    "pro":        {"label": "Pro",        "monthly_credits": 5_000, "max_episodes": 30_000, "models": "all"},
    "enterprise": {"label": "Enterprise", "monthly_credits": 50_000,"max_episodes": 100_000,"models": "all"},
}

# ── Available Datasets ──
DATASETS = [
    {"id": "ogenti-default",   "label": "Ogenti Default (110 tasks)",     "tasks": 110, "categories": 12},
    {"id": "ogenti-extended",  "label": "Ogenti Extended (500 tasks)",    "tasks": 500, "categories": 12},
    {"id": "alpaca-converted", "label": "Alpaca Converted (10K tasks)",   "tasks": 10_000, "categories": 8},
    {"id": "custom-upload",    "label": "Custom Upload (JSONL)",          "tasks": 0, "categories": 0},
]

# ── Inference / Adapter Usage Pricing (credits per call) ──
# Pricing logic:
#   GPT-4o  ≈ $0.0075/conversation (~1K in + 500 out tokens)
#   1 credit = $0.005 (starter), $0.003 (pro), $0.0025 (enterprise)
#   → 1 credit/call for 3B = $0.005  = 33% cheaper than GPT-4o
#   → 2 credits/call for 7B = $0.01  but FINE-TUNED specialist > generic GPT
#   → 3 credits/call for 14B = $0.015 = enterprise-grade specialist
INFERENCE_COSTS = {
    "qwen2.5-3b":   {"credits_per_call": 1,  "label": "Qwen2.5-3B"},
    "qwen2.5-7b":   {"credits_per_call": 2,  "label": "Qwen2.5-7B"},
    "qwen2.5-14b":  {"credits_per_call": 3,  "label": "Qwen2.5-14B"},
    "llama3.2-3b":  {"credits_per_call": 1,  "label": "LLaMA-3.2-3B"},
    "llama3.2-8b":  {"credits_per_call": 2,  "label": "LLaMA-3.2-8B"},
    "mistral-7b":   {"credits_per_call": 2,  "label": "Mistral-7B"},
    "custom":       {"credits_per_call": 1,  "label": "Custom"},
}

# ── RunPod (GPU Training) ──
RUNPOD_API_KEY = os.getenv("RUNPOD_API_KEY", "")
RUNPOD_ENDPOINT_ID = os.getenv("RUNPOD_ENDPOINT_ID", "")
RUNPOD_WEBHOOK_TOKEN = os.getenv("RUNPOD_WEBHOOK_TOKEN", secrets.token_hex(16))  # verifies callbacks
RUNPOD_API_BASE = "https://api.runpod.ai/v2"

# Model → GPU type mapping for RunPod
MODEL_GPU_MAP = {
    "qwen2.5-3b":   {"gpu": "NVIDIA RTX A4000", "gpu_count": 1},
    "qwen2.5-7b":   {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
    "qwen2.5-14b":  {"gpu": "NVIDIA A100-SXM4-80GB", "gpu_count": 1},
    "llama3.2-3b":  {"gpu": "NVIDIA RTX A4000", "gpu_count": 1},
    "llama3.2-8b":  {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
    "mistral-7b":   {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
    "custom":       {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
}

# Model → HuggingFace repo ID mapping
MODEL_HF_MAP = {
    "qwen2.5-3b":   "Qwen/Qwen2.5-3B-Instruct",
    "qwen2.5-7b":   "Qwen/Qwen2.5-7B-Instruct",
    "qwen2.5-14b":  "Qwen/Qwen2.5-14B-Instruct",
    "llama3.2-3b":  "meta-llama/Llama-3.2-3B-Instruct",
    "llama3.2-8b":  "meta-llama/Llama-3.2-8B-Instruct",
    "mistral-7b":   "mistralai/Mistral-7B-Instruct-v0.3",
}

# Dataset → HuggingFace repo or URL mapping
DATASET_HF_MAP = {
    "ogenti-default":   {"type": "local", "path": "data/ogenti_default.jsonl"},
    "ogenti-extended":  {"type": "local", "path": "data/ogenti_extended.jsonl"},
    "alpaca-converted": {"type": "hf", "path": "tatsu-lab/alpaca"},
    "custom-upload":    {"type": "upload"},
}

# ── OGT Storage ──
_default_ogt = "/data/ogt_adapters" if _ON_RAILWAY else "./ogt_adapters"
OGT_STORAGE_DIR = os.getenv("OGT_STORAGE_DIR", _default_ogt)

# ══════════════════════════════════════════════════════════════════
# OVISEN — Image Embedding Compression (AI-to-AI Visual Protocol)
# ══════════════════════════════════════════════════════════════════

# ── Vision Model Pricing (credits per episode) ──
OVISEN_MODEL_COSTS = {
    "clip-vit-b32":    {"credits_per_episode": 2,  "label": "CLIP ViT-B/32",     "vram": "8GB",  "speed": "Fast"},
    "clip-vit-l14":    {"credits_per_episode": 5,  "label": "CLIP ViT-L/14",     "vram": "16GB", "speed": "Medium"},
    "siglip-so400m":   {"credits_per_episode": 4,  "label": "SigLIP SO-400M",    "vram": "12GB", "speed": "Medium"},
    "dinov2-vit-b14":  {"credits_per_episode": 3,  "label": "DINOv2 ViT-B/14",   "vram": "10GB", "speed": "Fast"},
    "dinov2-vit-l14":  {"credits_per_episode": 6,  "label": "DINOv2 ViT-L/14",   "vram": "20GB", "speed": "Slow"},
    "eva02-vit-l":     {"credits_per_episode": 7,  "label": "EVA-02 ViT-L",      "vram": "24GB", "speed": "Slow"},
    "custom-vision":   {"credits_per_episode": 3,  "label": "Custom (User)",      "vram": "Varies","speed": "Varies"},
}

# ── Ovisen Inference Pricing ──
OVISEN_INFERENCE_COSTS = {
    "clip-vit-b32":    {"credits_per_call": 2,  "label": "CLIP ViT-B/32"},
    "clip-vit-l14":    {"credits_per_call": 3,  "label": "CLIP ViT-L/14"},
    "siglip-so400m":   {"credits_per_call": 3,  "label": "SigLIP SO-400M"},
    "dinov2-vit-b14":  {"credits_per_call": 2,  "label": "DINOv2 ViT-B/14"},
    "dinov2-vit-l14":  {"credits_per_call": 4,  "label": "DINOv2 ViT-L/14"},
    "eva02-vit-l":     {"credits_per_call": 5,  "label": "EVA-02 ViT-L"},
    "custom-vision":   {"credits_per_call": 2,  "label": "Custom"},
}

# ── Ovisen Datasets ──
OVISEN_DATASETS = [
    {"id": "imagenet-1k-sample",  "label": "ImageNet-1K Sample (10K images)",  "images": 10_000, "categories": 100},
    {"id": "coco-2017-val",       "label": "COCO 2017 Validation (5K images)", "images": 5_000,  "categories": 80},
    {"id": "ovisen-synthetic",    "label": "Ovisen Synthetic (20K images)",     "images": 20_000, "categories": 50},
    {"id": "custom-upload",       "label": "Custom Upload (Image Archive)",    "images": 0,      "categories": 0},
]

# ── Ovisen model → HuggingFace mapping ──
OVISEN_MODEL_HF_MAP = {
    "clip-vit-b32":    "openai/clip-vit-base-patch32",
    "clip-vit-l14":    "openai/clip-vit-large-patch14",
    "siglip-so400m":   "google/siglip-so400m-patch14-384",
    "dinov2-vit-b14":  "facebook/dinov2-base",
    "dinov2-vit-l14":  "facebook/dinov2-large",
    "eva02-vit-l":     "Yuxin-CV/EVA-02/eva02_L_pt_m38m_p14to16",
}

# ── Ovisen Dataset → source mapping ──
OVISEN_DATASET_MAP = {
    "imagenet-1k-sample": {"type": "hf",    "path": "imagenet-1k"},
    "coco-2017-val":      {"type": "hf",    "path": "detection-datasets/coco"},
    "ovisen-synthetic":   {"type": "local",  "path": "data/ovisen_synthetic/"},
    "custom-upload":      {"type": "upload"},
}

# ── Ovisen GPU mapping ──
OVISEN_MODEL_GPU_MAP = {
    "clip-vit-b32":    {"gpu": "NVIDIA RTX A4000", "gpu_count": 1},
    "clip-vit-l14":    {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
    "siglip-so400m":   {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
    "dinov2-vit-b14":  {"gpu": "NVIDIA RTX A4000", "gpu_count": 1},
    "dinov2-vit-l14":  {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
    "eva02-vit-l":     {"gpu": "NVIDIA A100-SXM4-80GB", "gpu_count": 1},
    "custom-vision":   {"gpu": "NVIDIA RTX A5000", "gpu_count": 1},
}

# ── OGE Storage ──
_default_oge = "/data/oge_adapters" if _ON_RAILWAY else "./oge_adapters"
OGE_STORAGE_DIR = os.getenv("OGE_STORAGE_DIR", _default_oge)

# ── RunPod OVISEN Endpoint (separate serverless endpoint for vision) ──
RUNPOD_OVISEN_ENDPOINT_ID = os.getenv("RUNPOD_OVISEN_ENDPOINT_ID", "")

