"""
Tier Configuration v2 — Defines strict performance boundaries per pricing tier.

Business Principle: Performance MUST be proportional to price.
Free agents get bare minimum. S+ agents get maximum capability.
This is NOT a dark pattern — it's fair to paying customers.

Tier Hierarchy:
  F   (Free $0)       → Bare minimum, single-purpose utilities
  B-  (Budget $0.49-1.99) → Basic single-domain, very limited
  C   (Standard $2-3.99) → Decent single-domain, moderate limits
  B   (Enhanced $4-7.99) → Good single-domain, standard features
  A   (Premium $8-12.99) → Strong domain specialist, planning
  S   (Pro $13-19.99)  → Expert domain specialist, all engines
  S+  (Ultra $20-29.99) → Godmode, cross-domain, unlimited

v2 Changes:
  - Increased system_prompt_budget for ALL tiers (intelligence injection needs space)
  - Increased max_message_history for lower tiers (context retention)
  - Added intelligence_level field for progressive feature unlocking
  - Added max_tool_calls_per_step for execution governance
  - Added retry_escalation for smarter retry behavior
"""

from dataclasses import dataclass, field
from typing import Optional


from loguru import logger


@dataclass(frozen=True)
class TierConfig:
    """Immutable tier configuration. Engine enforces these limits."""
    
    # Core execution limits
    max_steps: int
    max_retries: int
    action_delay: float  # seconds between actions (slower = cheaper)
    
    # Engine access
    vision_enabled: bool
    vision_quality: int  # 0-100, affects screenshot resolution
    som_enabled: bool  # Set-of-Mark element detection
    planning_enabled: bool
    memory_enabled: bool
    max_replans: int
    verification_enabled: bool  # Post-action screenshot verification
    
    # Tool access
    specialized_tools_enabled: bool
    specialized_tools_limit: int  # Max number of domain tools (-1 = all)
    cross_domain_tools: bool  # S+ only: can use tools from other domains
    
    # Context limits
    max_message_history: int  # Max conversation messages kept
    system_prompt_budget: int  # Max chars for system prompt
    
    # Feature flags
    smart_wait_enabled: bool  # Visual diff-based wait
    macro_recording: bool  # Record/replay action sequences
    action_chaining: bool  # Execute multi-step tool chains
    
    # v2: Intelligence scaling
    intelligence_level: int = 1          # 1-5, controls depth of strategy injection
    max_tool_calls_per_step: int = 1     # Max tool calls allowed per step
    retry_escalation: bool = False       # Whether retries escalate (screenshot, SoM, replan)
    completion_verification: bool = False # Whether completion requires verification checks
    error_analysis: bool = False          # Whether errors are analyzed for patterns
    unstuck_detection: bool = False       # Whether agent detects when it's stuck and self-corrects
    context_aware_feedback: bool = False  # Whether feedback adapts to action type and context
    

# ═══════════════════════════════════════════════════════
# TIER DEFINITIONS — Strict Performance Scaling
# ═══════════════════════════════════════════════════════

TIERS: dict[str, TierConfig] = {
    "F": TierConfig(
        max_steps=8,
        max_retries=0,
        action_delay=1.5,
        vision_enabled=False,
        vision_quality=0,
        som_enabled=False,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=False,
        specialized_tools_enabled=False,
        specialized_tools_limit=0,
        cross_domain_tools=False,
        max_message_history=8,
        system_prompt_budget=1500,
        smart_wait_enabled=False,
        macro_recording=False,
        action_chaining=False,
        # v2
        intelligence_level=1,
        max_tool_calls_per_step=1,
        retry_escalation=False,
        completion_verification=False,
        error_analysis=False,
        unstuck_detection=False,
        context_aware_feedback=False,
    ),
    "E": TierConfig(
        max_steps=10,
        max_retries=1,
        action_delay=1.3,
        vision_enabled=False,
        vision_quality=0,
        som_enabled=False,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=False,
        specialized_tools_enabled=True,
        specialized_tools_limit=2,
        cross_domain_tools=False,
        max_message_history=9,
        system_prompt_budget=1800,
        smart_wait_enabled=False,
        macro_recording=False,
        action_chaining=False,
        # v2
        intelligence_level=1,
        max_tool_calls_per_step=1,
        retry_escalation=False,
        completion_verification=False,
        error_analysis=False,
        unstuck_detection=False,
        context_aware_feedback=False,
    ),
    "B-": TierConfig(
        max_steps=12,
        max_retries=1,
        action_delay=1.2,
        vision_enabled=False,
        vision_quality=0,
        som_enabled=False,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=False,
        specialized_tools_enabled=True,
        specialized_tools_limit=2,
        cross_domain_tools=False,
        max_message_history=10,
        system_prompt_budget=2000,
        smart_wait_enabled=False,
        macro_recording=False,
        action_chaining=False,
        # v2
        intelligence_level=1,
        max_tool_calls_per_step=1,
        retry_escalation=False,
        completion_verification=False,
        error_analysis=False,
        unstuck_detection=False,
        context_aware_feedback=False,
    ),
    "D": TierConfig(
        max_steps=16,
        max_retries=1,
        action_delay=1.0,
        vision_enabled=True,
        vision_quality=40,
        som_enabled=False,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=False,
        specialized_tools_enabled=True,
        specialized_tools_limit=3,
        cross_domain_tools=False,
        max_message_history=14,
        system_prompt_budget=3200,
        smart_wait_enabled=False,
        macro_recording=False,
        action_chaining=False,
        # v2
        intelligence_level=2,
        max_tool_calls_per_step=1,
        retry_escalation=False,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "C": TierConfig(
        max_steps=20,
        max_retries=1,
        action_delay=0.9,
        vision_enabled=True,
        vision_quality=50,
        som_enabled=False,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=False,
        specialized_tools_enabled=True,
        specialized_tools_limit=4,
        cross_domain_tools=False,
        max_message_history=16,
        system_prompt_budget=4000,
        smart_wait_enabled=False,
        macro_recording=False,
        action_chaining=False,
        # v2 — C tier gets basic intelligence
        intelligence_level=2,
        max_tool_calls_per_step=1,
        retry_escalation=False,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "C+": TierConfig(
        max_steps=26,
        max_retries=2,
        action_delay=0.8,
        vision_enabled=True,
        vision_quality=60,
        som_enabled=True,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=5,
        cross_domain_tools=False,
        max_message_history=20,
        system_prompt_budget=4500,
        smart_wait_enabled=True,
        macro_recording=False,
        action_chaining=False,
        # v2
        intelligence_level=3,
        max_tool_calls_per_step=2,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "B": TierConfig(
        max_steps=30,
        max_retries=2,
        action_delay=0.7,
        vision_enabled=True,
        vision_quality=70,
        som_enabled=True,
        planning_enabled=False,
        memory_enabled=False,
        max_replans=0,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=6,
        cross_domain_tools=False,
        max_message_history=24,
        system_prompt_budget=5000,
        smart_wait_enabled=True,
        macro_recording=False,
        action_chaining=False,
        # v2 — B tier gets moderate intelligence
        intelligence_level=3,
        max_tool_calls_per_step=2,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "B+": TierConfig(
        max_steps=35,
        max_retries=2,
        action_delay=0.6,
        vision_enabled=True,
        vision_quality=75,
        som_enabled=True,
        planning_enabled=True,
        memory_enabled=False,
        max_replans=1,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=7,
        cross_domain_tools=False,
        max_message_history=30,
        system_prompt_budget=6000,
        smart_wait_enabled=True,
        macro_recording=False,
        action_chaining=True,
        # v2
        intelligence_level=4,
        max_tool_calls_per_step=3,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "A": TierConfig(
        max_steps=40,
        max_retries=2,
        action_delay=0.5,
        vision_enabled=True,
        vision_quality=80,
        som_enabled=True,
        planning_enabled=True,
        memory_enabled=False,
        max_replans=1,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=8,
        cross_domain_tools=False,
        max_message_history=35,
        system_prompt_budget=7000,
        smart_wait_enabled=True,
        macro_recording=False,
        action_chaining=True,
        # v2 — A tier gets strong intelligence
        intelligence_level=4,
        max_tool_calls_per_step=3,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "A+": TierConfig(
        max_steps=45,
        max_retries=3,
        action_delay=0.45,
        vision_enabled=True,
        vision_quality=85,
        som_enabled=True,
        planning_enabled=True,
        memory_enabled=True,
        max_replans=2,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=10,
        cross_domain_tools=False,
        max_message_history=40,
        system_prompt_budget=8000,
        smart_wait_enabled=True,
        macro_recording=True,
        action_chaining=True,
        # v2
        intelligence_level=5,
        max_tool_calls_per_step=4,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "S": TierConfig(
        max_steps=50,
        max_retries=3,
        action_delay=0.4,
        vision_enabled=True,
        vision_quality=90,
        som_enabled=True,
        planning_enabled=True,
        memory_enabled=True,
        max_replans=2,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=-1,  # All domain tools
        cross_domain_tools=False,
        max_message_history=50,
        system_prompt_budget=9000,
        smart_wait_enabled=True,
        macro_recording=True,
        action_chaining=True,
        # v2 — S tier gets advanced intelligence
        intelligence_level=5,
        max_tool_calls_per_step=5,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
    "S+": TierConfig(
        max_steps=80,
        max_retries=5,
        action_delay=0.3,
        vision_enabled=True,
        vision_quality=95,
        som_enabled=True,
        planning_enabled=True,
        memory_enabled=True,
        max_replans=5,
        verification_enabled=True,
        specialized_tools_enabled=True,
        specialized_tools_limit=-1,  # All tools
        cross_domain_tools=True,  # Can use tools from adjacent domains
        max_message_history=80,
        system_prompt_budget=15000,
        smart_wait_enabled=True,
        macro_recording=True,
        action_chaining=True,
        # v2 — S+ gets maximum intelligence
        intelligence_level=5,
        max_tool_calls_per_step=10,
        retry_escalation=True,
        completion_verification=True,
        error_analysis=True,
        unstuck_detection=True,
        context_aware_feedback=True,
    ),
}


# ═══════════════════════════════════════════════════════
# INTELLIGENCE LEVEL DESCRIPTIONS
# Controls what intelligence features are injected
# ═══════════════════════════════════════════════════════

INTELLIGENCE_FEATURES = {
    1: {
        "name": "Basic",
        "description": "Minimal intelligence — basic action parsing only",
        "features": ["action_parsing"],
    },
    2: {
        "name": "Smart",
        "description": "Task detection + basic strategies + completion verification",
        "features": ["action_parsing", "task_detection", "basic_strategy", "completion_check", "error_analysis"],
    },
    3: {
        "name": "Advanced",
        "description": "Full strategies + browser/Windows guides + SoM precision + unstuck detection",
        "features": ["action_parsing", "task_detection", "full_strategy", "completion_check", 
                     "error_analysis", "browser_guide", "windows_guide", "som_targeting", "unstuck_detection"],
    },
    4: {
        "name": "Expert",
        "description": "All features + multi-action planning + tool chaining + context-aware feedback",
        "features": ["action_parsing", "task_detection", "full_strategy", "completion_check",
                     "error_analysis", "browser_guide", "windows_guide", "som_targeting", "unstuck_detection",
                     "action_chaining", "multi_action_planning", "context_feedback"],
    },
    5: {
        "name": "Supreme",
        "description": "Maximum intelligence — all features + memory-enhanced + cross-domain reasoning",
        "features": ["action_parsing", "task_detection", "full_strategy", "completion_check",
                     "error_analysis", "browser_guide", "windows_guide", "som_targeting", "unstuck_detection",
                     "action_chaining", "multi_action_planning", "context_feedback",
                     "memory_integration", "cross_domain_reasoning", "adaptive_strategy"],
    },
}


def get_intelligence_features(tier: str) -> dict:
    """Get intelligence features for a tier."""
    config = get_tier_config(tier)
    return INTELLIGENCE_FEATURES.get(config.intelligence_level, INTELLIGENCE_FEATURES[1])


# ═══════════════════════════════════════════════════════
# TIER CAPABILITY SUMMARY (for logging/UI)
# ═══════════════════════════════════════════════════════

TIER_SUMMARIES = {
    "F": "Free tier — 8 steps, no vision, basic clicks only. Proof of concept.",
    "E": "Entry tier — 10 steps, no vision, limited tools. Basic utilities.",
    "B-": "Budget tier — 12 steps, 1 retry, 2 tools. Good for simple one-shot tasks.",
    "D": "Starter tier — 16 steps, basic vision, 3 tools. Handles simple UI tasks.",
    "C": "Affordable tier — 20 steps, vision, 4 tools, smart error analysis. Reliable for standard tasks.",
    "C+": "Enhanced tier — 26 steps, vision+SoM, 5 tools. Better precision for UI tasks.",
    "B": "Mid tier — 30 steps, SoM targeting, 6 tools, smart retries. Handles moderate complexity.",
    "B+": "Expert tier — 35 steps, planning, 7 tools. Stronger strategy and chaining.",
    "A": "Premium tier — 40 steps, planning engine, 8 tools, action chaining. Expert domain performance.",
    "A+": "Premium+ tier — 45 steps, memory, 10 tools. High reliability for complex tasks.",
    "S": "Pro tier — 50 steps, all engines, memory, unlimited tools. Professional-grade agent.",
    "S+": "Ultra tier — 80 steps, cross-domain tools, 5 replans, supreme intelligence. Maximum capability.",
}


def get_tier_summary(tier: str) -> str:
    """Get human-readable tier summary."""
    return TIER_SUMMARIES.get(tier, f"Unknown tier: {tier}")


# ═══════════════════════════════════════════════════════
# DOMAIN ACTION RESTRICTIONS
# Each domain has a WHITELIST of allowed OS actions.
# Agents CANNOT use actions outside their domain whitelist.
# ═══════════════════════════════════════════════════════

# Tier-level base action whitelist (restricts even domain actions)
TIER_ACTION_WHITELIST: dict[str, set[str]] = {
    "F": {
        "click", "type_text", "press_key", "open_app", "wait",
    },
    "E": {
        "click", "type_text", "press_key", "hotkey", "scroll",
        "open_app", "close_app", "wait", "clipboard_get",
    },
    "B-": {
        "click", "type_text", "press_key", "hotkey", "scroll",
        "open_app", "close_app", "wait", "clipboard_get",
    },
    "D": {
        "click", "double_click", "type_text", "type_text_fast",
        "press_key", "hotkey", "scroll", "open_app", "close_app",
        "wait", "clipboard_copy", "clipboard_paste", "clipboard_get",
    },
    "C": {
        "click", "double_click", "type_text", "type_text_fast",
        "press_key", "hotkey", "scroll", "open_app", "close_app",
        "wait", "clipboard_copy", "clipboard_paste", "clipboard_get",
    },
    "C+": {
        "click", "double_click", "right_click", "type_text", "type_text_fast",
        "press_key", "hotkey", "scroll", "move_mouse",
        "open_app", "close_app", "focus_window", "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get",
    },
    "B": {
        "click", "double_click", "right_click", "type_text", "type_text_fast",
        "press_key", "hotkey", "scroll", "move_mouse",
        "open_app", "close_app", "focus_window", "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get",
    },
    "B+": None,
    "A": None,   # All domain-allowed actions
    "A+": None,
    "S": None,   # All domain-allowed actions
    "S+": None,  # All domain-allowed actions + cross-domain
}

# Domain-specific action whitelist — HARD boundary
DOMAIN_ACTION_WHITELIST: dict[str, set[str]] = {
    "coding": {
        "click", "double_click", "right_click",
        "click_element", "double_click_element", "right_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll", "move_mouse",
        "open_app", "close_app", "focus_window",
        "run_command",  # Terminal is CORE to coding
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get", "clipboard_set",
    },
    "design": {
        "click", "double_click", "right_click",
        "click_element", "double_click_element", "right_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll", "move_mouse", "drag",  # Drag is CORE to design
        "open_app", "close_app", "focus_window",
        # NO run_command — designers don't use terminals
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get", "clipboard_set",
    },
    "research": {
        "click", "double_click",
        "click_element", "double_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll",
        "open_app", "close_app", "focus_window",
        # NO run_command — researchers don't need terminals
        # NO drag, move_mouse — not relevant to research
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get",
        "write_file",  # Direct file write for saving research notes/reports
    },
    "writing": {
        "click", "double_click",
        "click_element", "double_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll",
        "open_app", "close_app", "focus_window",
        # NO run_command, drag, move_mouse — writers type, they don't code or draw
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get", "clipboard_set",
        "write_file",  # Direct file write for instant document creation
    },
    "data_analysis": {
        "click", "double_click", "right_click",
        "click_element", "double_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll", "move_mouse",
        "open_app", "close_app", "focus_window",
        "run_command",  # Data analysts use Python/R/Jupyter
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get", "clipboard_set",
    },
    "automation": {
        "click", "double_click", "right_click",
        "click_element", "double_click_element", "right_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll", "move_mouse", "drag",
        "open_app", "close_app", "focus_window",
        "run_command",  # Automation needs full OS control
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get", "clipboard_set",
    },
    "productivity": {
        "click", "double_click",
        "click_element", "double_click_element",
        "type_text", "type_text_fast", "press_key", "hotkey",
        "scroll",
        "open_app", "close_app", "focus_window",
        # NO run_command, drag — productivity tools are simple
        "wait",
        "clipboard_copy", "clipboard_paste", "clipboard_get",
    },
    "general": {
        # Bare minimum — for undefined/generic agents
        "click", "type_text", "press_key", "scroll", "open_app", "wait", "write_file",
    },
}


def get_tier_config(tier: str) -> TierConfig:
    """Get tier config, defaulting to F (free) for unknown tiers."""
    if tier not in TIERS:
        logger.warning(
            f"Unknown tier '{tier}' requested — falling back to 'F'. "
            f"Valid tiers: {list(TIERS.keys())}. "
            "Add this tier to TIERS in tier_config.py or fix the caller."
        )
    return TIERS.get(tier, TIERS["F"])


def get_allowed_actions(tier: str, domain: str) -> set[str]:
    """
    Compute the FINAL set of allowed actions for an agent.
    Result = intersection(tier_whitelist, domain_whitelist)
    """
    domain_actions = DOMAIN_ACTION_WHITELIST.get(domain, DOMAIN_ACTION_WHITELIST["general"])
    tier_whitelist = TIER_ACTION_WHITELIST.get(tier)
    
    if tier_whitelist is None:
        # A, S, S+ tiers: domain whitelist is the only restriction
        return domain_actions
    
    # Lower tiers: intersection of tier and domain whitelists
    return domain_actions & tier_whitelist


def price_to_tier(price: float) -> str:
    """Infer tier from price point.
    
    Must match shared/src/types/agent.ts AgentTier enum:
      F ($0), B- ($0.49-1.99), C ($2-3.99), B ($4-7.99), A ($8-12.99), S ($13-19.99), S+ ($20-29.99)
    """
    if price <= 0:
        return "F"
    elif price <= 1.99:
        return "B-"
    elif price <= 3.99:
        return "C"
    elif price <= 7.99:
        return "B"
    elif price <= 12.99:
        return "A"
    elif price <= 19.99:
        return "S"
    else:
        return "S+"
