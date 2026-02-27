"""
ogent-1.0 Token Pricing — Per-model cost tracking with 1.4x profit markup.

ogent-1.0 is a platform-managed model (NOT BYOK). The platform pays for
API calls using its own keys, and charges users credits at a 1.4x markup
over the actual dollar cost.

Routing:
  - Execute tasks → GPT-5.2 (OpenAI)
  - Idle/social   → phi-3 / llama-3-8b / qwen2-14b via Groq

All costs are in USD per 1M tokens. Credit conversion uses the exchange rate.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


PROFIT_MARKUP = 1.4


class OgentMode(Enum):
    EXECUTE = "execute"
    IDLE = "idle"


@dataclass(frozen=True)
class ModelCost:
    """Cost per 1M tokens in USD."""
    model_id: str
    provider: str
    input_cost_per_1m: float
    output_cost_per_1m: float
    context_window: int
    supports_vision: bool = False


OGENT_EXECUTE_MODEL = ModelCost(
    model_id="gpt-5.2",
    provider="openai",
    input_cost_per_1m=2.50,
    output_cost_per_1m=10.00,
    context_window=256000,
    supports_vision=True,
)

OGENT_IDLE_MODELS: list[ModelCost] = [
    ModelCost(
        model_id="llama-3.3-70b-versatile",
        provider="groq",
        input_cost_per_1m=0.59,
        output_cost_per_1m=0.79,
        context_window=128000,
    ),
    ModelCost(
        model_id="llama-3.1-8b-instant",
        provider="groq",
        input_cost_per_1m=0.05,
        output_cost_per_1m=0.08,
        context_window=131072,
    ),
    ModelCost(
        model_id="gemma2-9b-it",
        provider="groq",
        input_cost_per_1m=0.20,
        output_cost_per_1m=0.20,
        context_window=8192,
    ),
]

# Default idle model (cheapest for most social tasks)
OGENT_DEFAULT_IDLE_MODEL = OGENT_IDLE_MODELS[0]


def get_model_for_mode(mode: OgentMode, idle_model_index: int = 0) -> ModelCost:
    if mode == OgentMode.EXECUTE:
        return OGENT_EXECUTE_MODEL
    idx = max(0, min(idle_model_index, len(OGENT_IDLE_MODELS) - 1))
    return OGENT_IDLE_MODELS[idx]


def calculate_token_cost_usd(
    model: ModelCost,
    input_tokens: int,
    output_tokens: int,
) -> float:
    """Calculate raw USD cost for a given token usage."""
    input_cost = (input_tokens / 1_000_000) * model.input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * model.output_cost_per_1m
    return input_cost + output_cost


def calculate_credit_charge(
    model: ModelCost,
    input_tokens: int,
    output_tokens: int,
    exchange_rate: float = 10.0,
) -> dict:
    """Calculate credits to charge the user (with 1.4x markup).

    Returns breakdown dict for transparency/logging.
    """
    raw_usd = calculate_token_cost_usd(model, input_tokens, output_tokens)
    marked_up_usd = raw_usd * PROFIT_MARKUP
    credit_charge = max(0.01, round(marked_up_usd * exchange_rate, 2))

    return {
        "model_id": model.model_id,
        "provider": model.provider,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "raw_cost_usd": round(raw_usd, 6),
        "markup": PROFIT_MARKUP,
        "marked_up_usd": round(marked_up_usd, 6),
        "exchange_rate": exchange_rate,
        "credit_charge": credit_charge,
    }


def estimate_credits_for_request(
    mode: OgentMode,
    estimated_input_tokens: int = 2000,
    estimated_output_tokens: int = 500,
    exchange_rate: float = 10.0,
) -> float:
    """Quick estimate of credit cost for UI display."""
    model = get_model_for_mode(mode)
    result = calculate_credit_charge(model, estimated_input_tokens, estimated_output_tokens, exchange_rate)
    return result["credit_charge"]
