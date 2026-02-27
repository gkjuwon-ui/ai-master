"""
Pricing Model — Dynamic credit pricing with intelligence tiers.

Agents are priced in Ogenti Credits. The actual credit cost is NOT fixed —
it is calculated dynamically as: base_price × exchange_rate.
The exchange rate fluctuates (5–30 cr/$1) based on demand pressure, supply
inflation, and issuance velocity (see exchangeService.ts).

base_price is a reference value per tier. The backend's creditService.getCreditCost()
multiplies it by the current exchange rate to determine the real credit cost.
"""

from dataclasses import dataclass
from typing import Dict, List
from enum import Enum


class IntelligenceTier(Enum):
    BASIC = "basic"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"
    GENIUS = "genius"
    MASTER = "master"


@dataclass
class PricingTier:
    tier: str
    intelligence_level: IntelligenceTier
    base_price: float          # Reference price — actual credit cost = base_price × exchange rate
    performance_multiplier: float
    capabilities: List[str]
    max_concurrent_tasks: int
    learning_rate: float
    reasoning_depth: int
    creativity_score: float
    problem_solving_score: float


PRICING_TIERS = {
    # ── Dynamic credit pricing — credit cost = base_price × exchange rate ──
    # Exchange rate fluctuates 5–30 cr/$1 based on market conditions

    "F": PricingTier(
        tier="F",
        intelligence_level=IntelligenceTier.BASIC,
        base_price=0.0,
        performance_multiplier=1.0,
        capabilities=["basic_commands", "simple_automation", "text_processing"],
        max_concurrent_tasks=1,
        learning_rate=0.1,
        reasoning_depth=1,
        creativity_score=0.2,
        problem_solving_score=0.3
    ),

    "B-": PricingTier(
        tier="B-",
        intelligence_level=IntelligenceTier.BASIC,
        base_price=0.49,
        performance_multiplier=1.1,
        capabilities=["basic_commands", "simple_automation", "text_processing"],
        max_concurrent_tasks=1,
        learning_rate=0.1,
        reasoning_depth=1,
        creativity_score=0.2,
        problem_solving_score=0.3
    ),

    "E": PricingTier(
        tier="E",
        intelligence_level=IntelligenceTier.BASIC,
        base_price=0.99,
        performance_multiplier=1.2,
        capabilities=["basic_commands", "simple_automation", "text_processing", "pattern_recognition"],
        max_concurrent_tasks=2,
        learning_rate=0.15,
        reasoning_depth=2,
        creativity_score=0.3,
        problem_solving_score=0.4
    ),

    "D": PricingTier(
        tier="D",
        intelligence_level=IntelligenceTier.INTERMEDIATE,
        base_price=2.49,
        performance_multiplier=1.5,
        capabilities=["automation", "data_processing", "basic_learning", "context_awareness"],
        max_concurrent_tasks=3,
        learning_rate=0.25,
        reasoning_depth=3,
        creativity_score=0.4,
        problem_solving_score=0.5
    ),

    "C": PricingTier(
        tier="C",
        intelligence_level=IntelligenceTier.ADVANCED,
        base_price=3.99,
        performance_multiplier=2.0,
        capabilities=["advanced_automation", "learning", "adaptation", "complex_reasoning"],
        max_concurrent_tasks=5,
        learning_rate=0.4,
        reasoning_depth=4,
        creativity_score=0.6,
        problem_solving_score=0.7
    ),

    "C+": PricingTier(
        tier="C+",
        intelligence_level=IntelligenceTier.ADVANCED,
        base_price=4.99,
        performance_multiplier=2.5,
        capabilities=["advanced_automation", "learning", "adaptation", "complex_reasoning", "pattern_analysis"],
        max_concurrent_tasks=6,
        learning_rate=0.5,
        reasoning_depth=5,
        creativity_score=0.7,
        problem_solving_score=0.75
    ),

    "B": PricingTier(
        tier="B",
        intelligence_level=IntelligenceTier.EXPERT,
        base_price=5.99,
        performance_multiplier=3.0,
        capabilities=["expert_reasoning", "strategic_planning", "creative_problem_solving", "deep_learning"],
        max_concurrent_tasks=8,
        learning_rate=0.6,
        reasoning_depth=6,
        creativity_score=0.8,
        problem_solving_score=0.85
    ),

    "B+": PricingTier(
        tier="B+",
        intelligence_level=IntelligenceTier.EXPERT,
        base_price=7.99,
        performance_multiplier=4.0,
        capabilities=["expert_reasoning", "strategic_planning", "creative_problem_solving", "deep_learning", "advanced_adaptation"],
        max_concurrent_tasks=10,
        learning_rate=0.7,
        reasoning_depth=7,
        creativity_score=0.85,
        problem_solving_score=0.9
    ),

    "A": PricingTier(
        tier="A",
        intelligence_level=IntelligenceTier.GENIUS,
        base_price=9.99,
        performance_multiplier=5.0,
        capabilities=["genius_reasoning", "creative_synthesis", "systems_thinking", "metacognition"],
        max_concurrent_tasks=12,
        learning_rate=0.8,
        reasoning_depth=8,
        creativity_score=0.9,
        problem_solving_score=0.95
    ),

    "A+": PricingTier(
        tier="A+",
        intelligence_level=IntelligenceTier.GENIUS,
        base_price=12.99,
        performance_multiplier=7.5,
        capabilities=["genius_reasoning", "creative_synthesis", "systems_thinking", "metacognition", "multi_domain_reasoning"],
        max_concurrent_tasks=15,
        learning_rate=0.9,
        reasoning_depth=9,
        creativity_score=0.95,
        problem_solving_score=0.98
    ),

    "S": PricingTier(
        tier="S",
        intelligence_level=IntelligenceTier.MASTER,
        base_price=14.99,
        performance_multiplier=10.0,
        capabilities=["advanced_reasoning", "multi_domain_mastery", "strategic_planning", "autonomous_execution"],
        max_concurrent_tasks=20,
        learning_rate=1.0,
        reasoning_depth=10,
        creativity_score=1.0,
        problem_solving_score=1.0
    ),

    "S+": PricingTier(
        tier="S+",
        intelligence_level=IntelligenceTier.MASTER,
        base_price=19.99,
        performance_multiplier=20.0,
        capabilities=["full_autonomy", "cross_domain_expertise", "advanced_planning", "enterprise_automation"],
        max_concurrent_tasks=50,
        learning_rate=1.2,
        reasoning_depth=12,
        creativity_score=1.0,
        problem_solving_score=1.0
    )
}


def get_base_price(tier: str) -> float:
    """Get base reference price for a tier (multiply by exchange rate for credit cost)."""
    tier_config = PRICING_TIERS.get(tier, PRICING_TIERS["F"])
    return tier_config.base_price


def get_intelligence_requirements(tier: str) -> Dict:
    """Get intelligence requirements for a tier"""
    tier_config = PRICING_TIERS.get(tier, PRICING_TIERS["F"])

    return {
        "min_reasoning_depth": tier_config.reasoning_depth,
        "required_capabilities": tier_config.capabilities,
        "max_learning_rate": tier_config.learning_rate,
        "creativity_threshold": tier_config.creativity_score,
        "problem_solving_threshold": tier_config.problem_solving_score,
        "concurrent_task_limit": tier_config.max_concurrent_tasks
    }


def recommend_tier(task_complexity: float, required_intelligence: float, budget: float) -> str:
    """Recommend appropriate tier based on requirements and budget"""

    if task_complexity <= 0.2:
        recommended = "F"
    elif task_complexity <= 0.35:
        recommended = "E"
    elif task_complexity <= 0.5:
        recommended = "D"
    elif task_complexity <= 0.65:
        recommended = "C"
    elif task_complexity <= 0.8:
        recommended = "C+"
    elif task_complexity <= 1.0:
        recommended = "B"
    elif task_complexity <= 1.2:
        recommended = "B+"
    elif task_complexity <= 1.5:
        recommended = "A"
    elif task_complexity <= 1.8:
        recommended = "A+"
    elif task_complexity <= 2.2:
        recommended = "S"
    else:
        recommended = "S+"

    if budget > 0:
        all_tiers = ["F", "E", "D", "C", "C+", "B", "B+", "A", "A+", "S", "S+"]
        for tier in all_tiers:
            if PRICING_TIERS[tier].base_price <= budget:
                recommended = tier
            else:
                break

    return recommended


def get_performance_metrics(tier: str) -> Dict:
    """Get performance metrics for a tier"""
    tier_config = PRICING_TIERS.get(tier, PRICING_TIERS["F"])

    return {
        "intelligence_level": tier_config.intelligence_level.value,
        "base_performance": tier_config.performance_multiplier,
        "learning_capability": tier_config.learning_rate,
        "reasoning_capability": tier_config.reasoning_depth,
        "creativity_capability": tier_config.creativity_score,
        "problem_solving_capability": tier_config.problem_solving_score,
        "task_capacity": tier_config.max_concurrent_tasks
    }
