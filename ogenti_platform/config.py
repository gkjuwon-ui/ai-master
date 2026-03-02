"""Ogenti Platform Configuration"""
import os
import secrets

# ── Server ──
HOST = os.getenv("OGENTI_HOST", "0.0.0.0")
PORT = int(os.getenv("OGENTI_PORT", "8080"))
SECRET_KEY = os.getenv("OGENTI_SECRET", secrets.token_hex(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

# ── Database ──
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ogenti_platform/ogenti.db")

# ── Resend (email) ──
RESEND_API_KEY = os.getenv("RESEND_API_KEY", "re_test_xxxxxxxxxxxx")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@ogenti.com")

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

# ── OGT Storage ──
OGT_STORAGE_DIR = os.getenv("OGT_STORAGE_DIR", "./ogt_adapters")

