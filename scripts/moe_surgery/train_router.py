#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  Router Fine-Tuning v3.0 — train_router.py
  Trains ONLY the router gate weights so they learn to route
  tokens to the 4 new experts (16-19) based on specialization.
═══════════════════════════════════════════════════════════════════

V3.0 Changes:
- Expanded expert keywords (60+ EN, 30+ KO per expert) for stronger routing signal
- Added negative keywords (tokens that should NOT route to an expert)
- Semantic donor alignment matching inject_experts.py v3.0
- Temperature annealing schedule (soft→sharp routing over training)
- Improved curriculum learning with smoother phase transitions
- Cross-expert contrastive pairs for better discrimination
    router_logits = x @ router_weight.T   (x: [batch, hidden_size], router: [num_experts, hidden_size])
    expert_probs = softmax(router_logits)
    selected_expert = argmax(expert_probs)  (top-1 routing)

After expert injection, the router has expanded from [16, 5120] → [20, 5120].
The new rows (experts 16-19) are initialized with biased blends, but the router
hasn't learned WHEN to select them.

This script trains the router to:
1. Route "visual grounding" tokens to expert 16
2. Route "workflow planning" tokens to expert 17
3. Route "verification/checking" tokens to expert 18
4. Route "error recovery/retry" tokens to expert 19
5. Maintain existing expert routing quality (no catastrophic forgetting)

Training losses:
- Specialization Loss: New experts should be selected for their specialty tokens
- Load Balance Loss: All experts should be reasonably utilized (no dead experts)
- Auxiliary Router Loss: Standard MoE routing loss from the original config
- Distillation Loss: Keep existing routing behavior for non-specialty tokens
- Contrastive Loss (v2.0): Push apart expert specializations
- Diversity Loss (v2.0): Encourage new expert rows to be different from each other

Training features (v2.0):
- Curriculum Learning: gradual difficulty increase
- Per-expert Learning Rate: different LR for new expert rows
- Contrastive Routing Loss
- Evaluation function with held-out set
- Korean keyword support
- Gradient monitoring
- Training resume from checkpoint
- Dynamic loss weighting

Requirements: Must run AFTER inject_experts.py has expanded the model.
GPU Required: A100 80GB (loads model in 4-bit, trains router in fp32)
"""

import os
import gc
import sys
import json
import math
import time
import random
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader, Subset
from tqdm import tqdm
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("router_tuning")


# ═══════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════

@dataclass
class RouterTuningConfig:
    """Configuration for router fine-tuning."""
    # Model
    model_dir: str = ""
    output_dir: str = ""
    
    # Architecture
    num_experts: int = 20
    num_original_experts: int = 16
    hidden_size: int = 5120
    num_layers: int = 48
    
    # Training
    learning_rate: float = 5e-4       # Relatively high LR for router-only training
    weight_decay: float = 0.01
    num_epochs: int = 5
    batch_size: int = 4
    gradient_accumulation: int = 8    # Effective batch = 32
    warmup_steps: int = 100
    max_grad_norm: float = 1.0
    
    # Loss weights
    specialization_loss_weight: float = 2.0   # Heavily weight specialization
    load_balance_loss_weight: float = 0.1     # Light load balancing
    distillation_loss_weight: float = 1.0     # Preserve existing routing
    aux_loss_weight: float = 0.001            # Standard MoE aux loss
    
    # Routing targets for new experts
    routing_temperature: float = 0.1   # Low temp = sharper routing decisions
    min_expert_utilization: float = 0.02  # Each expert should get at least 2% of tokens
    
    # Data
    training_data_dir: str = ""
    max_seq_length: int = 2048
    
    # Compute
    device: str = "cuda"
    use_amp: bool = True              # Mixed precision
    
    # Logging  
    log_every: int = 10
    save_every: int = 500
    eval_every: int = 100
    
    # Wandb
    use_wandb: bool = False
    wandb_project: str = "osen-router-tuning"
    
    # v2.0: Curriculum Learning
    curriculum_enabled: bool = True
    curriculum_phases: int = 3        # Number of difficulty phases
    # Phase 1: high spec weight, low balance → focus on learning specialization
    # Phase 2: balanced → learn to balance load
    # Phase 3: low spec, high balance → polish routing quality
    
    # v2.0: Per-Expert Learning Rate
    new_expert_lr_multiplier: float = 3.0   # 3x higher LR for new expert rows
    
    # v2.0: Contrastive Loss
    contrastive_loss_weight: float = 0.5    # Push apart expert specializations
    contrastive_margin: float = 0.3         # Minimum cosine distance between expert rows
    
    # v2.0: Diversity Loss
    diversity_loss_weight: float = 0.2      # Encourage new expert row diversity
    
    # v2.0: Training Resume
    resume_from: Optional[str] = None       # Path to checkpoint to resume from
    
    # v2.0: Evaluation
    eval_split_ratio: float = 0.1           # 10% of data for evaluation
    
    # v2.0: Gradient monitoring
    monitor_gradients: bool = True
    gradient_log_every: int = 50


# ═══════════════════════════════════════════════════════════════
# EXPERT SPECIALTY KEYWORDS
# ═══════════════════════════════════════════════════════════════
# These keywords determine which tokens should route to each new expert.
# The router training will learn to associate hidden representations
# of these semantic concepts with the corresponding expert.

EXPERT_KEYWORDS = {
    16: {  # visual_grounding
        "name": "visual_grounding",
        "keywords": [
            # Core visual grounding
            "click", "button", "coordinates", "pixel", "screenshot", "screen",
            "icon", "menu", "toolbar", "cursor", "mouse", "position",
            "element", "ui", "interface", "window", "dialog", "tab",
            "scroll", "drag", "drop", "hover", "focus", "visible",
            "layout", "top-left", "bottom-right", "center", "sidebar",
            "checkbox", "radio", "dropdown", "input", "text field",
            "image", "resolution", "display", "monitor", "viewport",
            "navigate", "locate", "identify", "find", "detect",
            "grounding", "spatial", "visual", "GUI", "widget",
            # V3: Extended visual grounding keywords
            "bounding box", "region", "area", "overlay", "annotation",
            "tooltip", "popup", "modal", "panel", "pane", "frame",
            "header", "footer", "navigation bar", "status bar", "taskbar",
            "tray", "notification", "badge", "indicator", "spinner",
            "dark mode", "light mode", "theme", "DPI", "scaling",
            "retina", "high-DPI", "4K", "1080p", "aspect ratio",
            "clickable", "interactable", "disabled", "grayed out", "hidden",
            "occluded", "overlapping", "z-index", "foreground", "background",
            "SoM", "set-of-mark", "numbered label", "bounding",
            "coordinate system", "absolute position", "relative position",
        ],
        "keywords_ko": [
            "클릭", "버튼", "좌표", "픽셀", "스크린샷", "화면",
            "아이콘", "메뉴", "도구모음", "커서", "마우스", "위치",
            "요소", "인터페이스", "창", "대화상자", "탭", "드래그",
            "스크롤", "드롭다운", "체크박스", "입력", "표시", "레이아웃",
            # V3: Extended Korean keywords
            "영역", "오버레이", "팝업", "모달", "패널", "프레임",
            "상태바", "작업표시줄", "알림", "배지", "스피너",
            "다크모드", "라이트모드", "해상도", "비활성화", "숨김",
            "바운딩박스", "좌표계", "절대위치", "상대위치",
        ],
        "negative_keywords": [
            "retry", "fallback", "recover", "plan", "schedule",
            "verify", "validate", "confirm", "check result",
        ],
    },
    17: {  # workflow_orchestrator
        "name": "workflow_orchestrator",
        "keywords": [
            # Core workflow orchestration
            "plan", "step", "sequence", "workflow", "process",
            "first", "then", "next", "after", "before", "finally",
            "orchestrate", "coordinate", "schedule", "order",
            "task", "subtask", "decompose", "break down",
            "prerequisite", "dependency", "parallel", "sequential",
            "pipeline", "phase", "stage", "milestone",
            "open", "switch", "application", "app", "program",
            "transfer", "data", "between", "across", "multiple",
            "organize", "structure", "manage", "prioritize",
            "efficiency", "optimize", "streamline", "automate",
            # V3: Extended workflow keywords
            "clipboard", "copy", "paste", "cut", "drag between",
            "window management", "alt+tab", "minimize", "maximize", "restore",
            "multi-app", "cross-application", "inter-app", "handoff",
            "data flow", "pipeline stage", "critical path", "bottleneck",
            "estimated time", "ETA", "duration", "time management",
            "batch", "bulk", "queue", "concurrent", "simultaneous",
            "prerequisite check", "conditional", "if then", "branch",
            "loop", "repeat", "iterate", "for each",
            "checkpoint", "save point", "rollback point",
            "Chrome to Excel", "browser to document", "app to app",
        ],
        "keywords_ko": [
            "계획", "단계", "순서", "워크플로우", "프로세스",
            "먼저", "다음", "이후", "이전", "마지막으로",
            "작업", "하위작업", "분해", "의존성", "병렬",
            "순차적", "파이프라인", "자동화", "조율", "우선순위",
            # V3: Extended Korean keywords
            "클립보드", "복사", "붙여넣기", "잘라내기",
            "창관리", "멀티앱", "앱전환", "데이터흐름",
            "예상시간", "소요시간", "일괄처리", "동시",
            "전제조건", "조건부", "반복", "체크포인트",
        ],
        "negative_keywords": [
            "pixel", "coordinates", "bounding box", "screenshot",
            "retry", "error", "crash", "verify result",
        ],
    },
    18: {  # verification_oracle
        "name": "verification_oracle",
        "keywords": [
            # Core verification
            "verify", "check", "confirm", "validate", "ensure",
            "success", "fail", "error", "correct", "wrong",
            "expected", "actual", "compare", "match", "differ",
            "status", "state", "change", "changed", "unchanged",
            "indicator", "signal", "evidence", "proof",
            "complete", "incomplete", "partial", "done",
            "result", "outcome", "output", "response",
            "test", "assert", "true", "false", "pass",
            "diagnosis", "analyze", "inspect", "examine",
            "confidence", "certain", "uncertain", "maybe",
            # V3: Extended verification keywords
            "before and after", "pre-action", "post-action", "screenshot diff",
            "visual diff", "pixel difference", "content appeared", "content disappeared",
            "dialog closed", "dialog opened", "file saved", "download complete",
            "form submitted", "page loaded", "progress bar", "loading complete",
            "checkmark", "green check", "red x", "warning icon",
            "success message", "error message", "confirmation dialog",
            "silent error", "silent failure", "partial completion",
            "wrong tab", "wrong window", "wrong app", "stale state",
            "idempotent", "side effect", "expected behavior",
            "regression", "quality gate", "acceptance criteria",
        ],
        "keywords_ko": [
            "검증", "확인", "확인하다", "검사", "성공", "실패",
            "오류", "맞다", "틀리다", "예상", "실제", "비교",
            "상태", "변경", "완료", "결과", "분석", "진단",
            # V3: Extended Korean keywords
            "전후비교", "사전상태", "사후상태", "스크린샷차이",
            "시각적차이", "콘텐츠확인", "파일저장확인", "다운로드완료",
            "폼제출", "페이지로딩", "체크마크", "경고아이콘",
            "조용한오류", "부분완료", "품질검증", "수락기준",
        ],
        "negative_keywords": [
            "retry", "fallback", "alternative", "workaround",
            "plan", "schedule", "workflow", "coordinate",
        ],
    },
    19: {  # adaptive_retry
        "name": "adaptive_retry",
        "keywords": [
            # Core retry/recovery
            "retry", "again", "failed", "failure", "crash",
            "error", "exception", "bug", "broken", "fix",
            "recover", "recovery", "fallback", "backup",
            "alternative", "instead", "different", "another",
            "timeout", "hang", "stuck", "frozen", "unresponsive",
            "permission", "denied", "access", "blocked",
            "not found", "missing", "unavailable", "offline",
            "backoff", "wait", "delay", "patience",
            "workaround", "hack", "bypass", "overcome",
            "escalate", "abort", "cancel", "undo", "rollback",
            # V3: Extended retry keywords
            "exponential backoff", "jitter", "max retries", "retry limit",
            "circuit breaker", "degraded mode", "graceful degradation",
            "safe mode", "last resort", "emergency", "critical failure",
            "blue screen", "BSOD", "kernel panic", "force quit", "force close",
            "kill process", "end task", "task manager", "process manager",
            "RunAs", "administrator", "UAC", "elevation", "sudo",
            "network timeout", "connection refused", "DNS failure",
            "certificate error", "SSL error", "proxy error",
            "disk full", "out of memory", "OOM", "resource exhausted",
            "file locked", "file in use", "access violation",
            "try differently", "approach differently", "new strategy",
            "rate limit", "429", "503", "throttled", "quota exceeded",
        ],
        "keywords_ko": [
            "재시도", "또", "실패", "장애", "오류", "버그",
            "복구", "대안", "대체", "타임아웃", "멈춤", "접근거부",
            "권한", "없음", "오프라인", "우회", "대비", "롤백",
            # V3: Extended Korean keywords
            "백오프", "지수백오프", "최대재시도", "회로차단기",
            "안전모드", "긴급", "강제종료", "프로세스끝내기",
            "관리자권한", "네트워크오류", "연결거부", "DNS오류",
            "디스크부족", "메모리부족", "파일잠김", "접근위반",
            "다른방법", "새전략", "속도제한", "할당초과",
        ],
        "negative_keywords": [
            "verify", "confirm", "check result", "validate",
            "plan", "step", "workflow", "coordinates", "pixel",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════
# DATASET
# ═══════════════════════════════════════════════════════════════

class RouterTrainingDataset(Dataset):
    """
    Dataset for router training (V3.0). Each example has:
    - input_ids: tokenized conversation
    - target_expert: which new expert should be activated (16-19)
    - keyword_density: positive keyword match strength [0, 1]
    - negative_densities: per-expert negative keyword match [4] — how strongly
      this sample should NOT route to each expert
    - secondary_expert: optional second expert for cross-expert chains (-1 = none)
    """
    
    def __init__(self, data_dir: str, tokenizer, max_length: int = 2048):
        self.examples = []
        self.tokenizer = tokenizer
        self.max_length = max_length
        
        data_path = Path(data_dir)
        
        # Load all expert training data files
        for expert_id in range(16, 20):
            expert_name = EXPERT_KEYWORDS[expert_id]["name"]
            filepath = data_path / f"expert_{expert_name}.jsonl"
            
            if not filepath.exists():
                log.warning(f"Missing training data: {filepath}")
                continue
            
            with open(filepath, "r", encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    example = json.loads(line)
                    conversations = example.get("conversations", [])
                    
                    # Build full text from conversations
                    text_parts = []
                    for msg in conversations:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        text_parts.append(f"<|{role}|>\n{content}")
                    
                    full_text = "\n".join(text_parts)
                    
                    self.examples.append({
                        "text": full_text,
                        "target_expert": expert_id,
                        "expert_name": expert_name,
                        "secondary_expert": -1,  # Single expert
                    })
        
        # V3.0: Load cross-expert chain data
        cross_files = ["expert_cross_chain.jsonl", "cross_expert_chains.jsonl"]
        for cross_name in cross_files:
            cross_path = data_path / cross_name
            if cross_path.exists():
                log.info(f"Loading cross-expert data: {cross_path}")
                with open(cross_path, "r", encoding="utf-8") as f:
                    for line in f:
                        if not line.strip():
                            continue
                        example = json.loads(line)
                        conversations = example.get("conversations", [])
                        chain = example.get("_expert_chain", [])
                        
                        text_parts = []
                        for msg in conversations:
                            role = msg.get("role", "user")
                            content = msg.get("content", "")
                            text_parts.append(f"<|{role}|>\n{content}")
                        
                        full_text = "\n".join(text_parts)
                        primary = chain[0] if chain else 16
                        secondary = chain[1] if len(chain) > 1 else -1
                        
                        self.examples.append({
                            "text": full_text,
                            "target_expert": primary,
                            "expert_name": "cross_expert",
                            "secondary_expert": secondary,
                        })
                break  # Only load from one matched file
        
        log.info(f"Loaded {len(self.examples)} training examples")
        
        # Distribution
        expert_counts = {}
        cross_count = 0
        for ex in self.examples:
            eid = ex["target_expert"]
            expert_counts[eid] = expert_counts.get(eid, 0) + 1
            if ex["secondary_expert"] != -1:
                cross_count += 1
        log.info(f"Expert distribution: {expert_counts}")
        log.info(f"Cross-expert samples: {cross_count}")
    
    def __len__(self):
        return len(self.examples)
    
    def __getitem__(self, idx):
        example = self.examples[idx]
        
        # Tokenize
        encoding = self.tokenizer(
            example["text"],
            max_length=self.max_length,
            truncation=True,
            padding="max_length",
            return_tensors="pt",
        )
        
        target_expert = example["target_expert"]
        keywords = EXPERT_KEYWORDS[target_expert]["keywords"]
        text = example["text"].lower()
        input_ids = encoding["input_ids"].squeeze(0)
        
        # Positive keyword density (EN + KO)
        keyword_density = sum(1 for kw in keywords if kw in text) / max(len(keywords), 1)
        keywords_ko = EXPERT_KEYWORDS[target_expert].get("keywords_ko", [])
        if keywords_ko:
            ko_density = sum(1 for kw in keywords_ko if kw in text) / max(len(keywords_ko), 1)
            keyword_density = max(keyword_density, ko_density)
        
        # V3.0: Negative keyword densities — for each of the 4 new experts,
        # how many of that expert's negative keywords appear in this text?
        # High negative density = this text should NOT route to that expert.
        negative_densities = torch.zeros(4, dtype=torch.float32)
        for i, eid in enumerate(range(16, 20)):
            neg_kws = EXPERT_KEYWORDS[eid].get("negative_keywords", [])
            if neg_kws and eid != target_expert:  # Don't penalize target expert's negatives
                neg_count = sum(1 for kw in neg_kws if kw in text)
                negative_densities[i] = neg_count / max(len(neg_kws), 1)
        
        return {
            "input_ids": input_ids,
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "target_expert": torch.tensor(target_expert, dtype=torch.long),
            "keyword_density": torch.tensor(keyword_density, dtype=torch.float32),
            "negative_densities": negative_densities,
            "secondary_expert": torch.tensor(example.get("secondary_expert", -1), dtype=torch.long),
        }


# ═══════════════════════════════════════════════════════════════
# v2.0: CURRICULUM LEARNING SCHEDULER
# ═══════════════════════════════════════════════════════════════

class CurriculumScheduler:
    """
    Dynamically adjusts loss weights during training.
    
    Phase 1 (warm-up): High specialization, low balance
        → Focus on teaching the router to select new experts at all
    Phase 2 (balanced): Equal weights
        → Learn proper routing patterns
    Phase 3 (refinement): Low specialization, high balance + distillation
        → Polish routing, prevent dead experts, preserve originality
    """
    
    def __init__(self, config: RouterTuningConfig, total_steps: int):
        self.config = config
        self.total_steps = total_steps
        self.num_phases = config.curriculum_phases
        self.phase_length = total_steps // self.num_phases if self.num_phases > 0 else total_steps
        
        # Define loss weight schedules per phase
        self.phase_configs = [
            {  # Phase 1: Learn specialization
                "specialization_weight": config.specialization_loss_weight * 2.0,
                "balance_weight": config.load_balance_loss_weight * 0.2,
                "distillation_weight": config.distillation_loss_weight * 0.5,
                "contrastive_weight": config.contrastive_loss_weight * 0.5,
                "diversity_weight": config.diversity_loss_weight * 1.5,
                "routing_temperature": config.routing_temperature * 2.0,  # Softer routing
            },
            {  # Phase 2: Balanced
                "specialization_weight": config.specialization_loss_weight,
                "balance_weight": config.load_balance_loss_weight,
                "distillation_weight": config.distillation_loss_weight,
                "contrastive_weight": config.contrastive_loss_weight,
                "diversity_weight": config.diversity_loss_weight,
                "routing_temperature": config.routing_temperature,
            },
            {  # Phase 3: Refinement
                "specialization_weight": config.specialization_loss_weight * 0.5,
                "balance_weight": config.load_balance_loss_weight * 3.0,
                "distillation_weight": config.distillation_loss_weight * 2.0,
                "contrastive_weight": config.contrastive_loss_weight * 1.5,
                "diversity_weight": config.diversity_loss_weight * 0.5,
                "routing_temperature": config.routing_temperature * 0.5,  # Sharper routing
            },
        ]
    
    def get_phase(self, step: int) -> int:
        """Get current curriculum phase (0-indexed)."""
        if not self.config.curriculum_enabled:
            return 1  # Always balanced
        phase = min(step // self.phase_length, self.num_phases - 1)
        return phase
    
    def get_weights(self, step: int) -> Dict[str, float]:
        """Get interpolated loss weights for current step."""
        if not self.config.curriculum_enabled:
            return self.phase_configs[1]
        
        phase = self.get_phase(step)
        
        # Smooth transition between phases
        phase_progress = (step % self.phase_length) / max(self.phase_length, 1)
        next_phase = min(phase + 1, self.num_phases - 1)
        
        # Linear interpolation within phase
        current = self.phase_configs[phase]
        next_cfg = self.phase_configs[next_phase]
        
        if phase == next_phase:
            return current
        
        return {
            key: current[key] * (1 - phase_progress) + next_cfg[key] * phase_progress
            for key in current
        }


# ═══════════════════════════════════════════════════════════════
# v2.0: GRADIENT MONITOR
# ═══════════════════════════════════════════════════════════════

class GradientMonitor:
    """Track gradient statistics for router parameters."""
    
    def __init__(self):
        self.history: Dict[str, List[float]] = defaultdict(list)
        self.max_norm_history: List[float] = []
    
    def log_gradients(self, model: nn.Module, step: int):
        """Record gradient norms for all trainable parameters."""
        total_norm = 0.0
        param_norms = {}
        
        for name, param in model.named_parameters():
            if param.requires_grad and param.grad is not None:
                grad_norm = param.grad.data.norm(2).item()
                total_norm += grad_norm ** 2
                
                # Abbreviated name for logging
                short_name = name.split(".")[-3] + "." + name.split(".")[-1] if "." in name else name
                param_norms[short_name] = grad_norm
                self.history[short_name].append(grad_norm)
        
        total_norm = total_norm ** 0.5
        self.max_norm_history.append(total_norm)
        
        return {
            "total_grad_norm": total_norm,
            "per_param_norms": param_norms,
        }
    
    def get_summary(self) -> Dict[str, Any]:
        """Get gradient statistics summary."""
        if not self.max_norm_history:
            return {}
        
        return {
            "avg_total_norm": np.mean(self.max_norm_history),
            "max_total_norm": max(self.max_norm_history),
            "min_total_norm": min(self.max_norm_history),
            "trend": ("increasing" if len(self.max_norm_history) > 10 and
                      np.mean(self.max_norm_history[-10:]) > np.mean(self.max_norm_history[:10]) * 1.5
                      else "stable"),
        }


# ═══════════════════════════════════════════════════════════════
# v2.0: EVALUATION FUNCTION
# ═══════════════════════════════════════════════════════════════

def evaluate_routing(
    tuner: "RouterTuner",
    eval_dataloader: DataLoader,
    config: RouterTuningConfig,
    curriculum_weights: Optional[Dict[str, float]] = None,
) -> Dict[str, float]:
    """
    Evaluate routing quality on held-out data.
    
    Returns:
        Dictionary with evaluation metrics:
        - eval_loss: total loss on eval set
        - new_expert_avg_prob: average selection probability for experts 16-19
        - eval_batches: number of batches evaluated
    """
    tuner.model.eval()
    
    total_loss = 0.0
    new_expert_probs = []
    n_batches = 0
    
    with torch.no_grad():
        for batch in eval_dataloader:
            input_ids = batch["input_ids"].to(config.device)
            attention_mask = batch["attention_mask"].to(config.device)
            target_expert = batch["target_expert"].to(config.device)
            keyword_density = batch["keyword_density"].to(config.device)
            negative_densities = batch["negative_densities"].to(config.device) if "negative_densities" in batch else None
            secondary_expert = batch["secondary_expert"].to(config.device) if "secondary_expert" in batch else None
            
            try:
                losses = tuner(input_ids, attention_mask, target_expert, keyword_density,
                               negative_densities=negative_densities,
                               secondary_expert=secondary_expert)
                total_loss += losses["total_loss"].item()
                new_expert_probs.append(losses["mean_new_expert_prob"].item())
                n_batches += 1
            except Exception as e:
                log.warning(f"Eval batch failed: {e}")
                continue
    
    tuner.model.train()
    
    metrics = {
        "eval_loss": total_loss / max(n_batches, 1),
        "new_expert_avg_prob": np.mean(new_expert_probs) if new_expert_probs else 0.0,
        "eval_batches": n_batches,
    }
    
    return metrics


# ═══════════════════════════════════════════════════════════════
# ROUTER-ONLY MODEL WRAPPER
# ═══════════════════════════════════════════════════════════════

class RouterTuner(nn.Module):
    """
    Wraps the Llama 4 model for router-only training.
    Only the router.weight parameters are trainable.
    Everything else is frozen.
    """
    
    def __init__(self, model, config: RouterTuningConfig):
        super().__init__()
        self.model = model
        self.config = config
        
        # Freeze everything
        for param in self.model.parameters():
            param.requires_grad = False
        
        # Unfreeze only router weights
        router_params = []
        for name, param in self.model.named_parameters():
            if "router.weight" in name or "router" in name.split(".")[-2:]:
                param.requires_grad = True
                param.data = param.data.float()  # Router trains in fp32
                router_params.append((name, param))
                log.info(f"  Trainable: {name} [{param.shape}]")
        
        self.router_param_count = sum(p.numel() for _, p in router_params)
        log.info(f"Total trainable parameters: {self.router_param_count:,} "
                 f"({self.router_param_count * 4 / 1024 / 1024:.1f} MB in fp32)")
        
        # Store original router weights for distillation
        self.original_routers = {}
        for name, param in router_params:
            self.original_routers[name] = param.data.clone().detach()
    
    def get_router_params(self):
        """Get only the trainable router parameters."""
        return [p for n, p in self.model.named_parameters() if p.requires_grad]
    
    def forward(self, input_ids, attention_mask=None, target_expert=None, keyword_density=None,
                negative_densities=None, secondary_expert=None):
        """
        Forward pass that returns router logits for training.
        
        V3.0: Now accepts negative_densities and secondary_expert for
        negative routing loss and cross-expert chain support.
        
        Strategy: Run ALL layer norms and a subset of attention layers (every 3rd)
        to produce realistic hidden states for router training. Full attention
        on every layer would OOM, but layernorm + attention every 3 layers gives
        hidden states that are representative of what the router will actually see
        at inference time. On A100 80GB this fits comfortably.
        """
        # Get embeddings (frozen)
        with torch.no_grad():
            if hasattr(self.model, 'language_model'):
                embed = self.model.language_model.model.embed_tokens(input_ids)
            elif hasattr(self.model, 'model'):
                embed = self.model.model.embed_tokens(input_ids)
            else:
                embed = self.model.embed_tokens(input_ids)
        
        # Collect router logits from each MoE layer
        all_router_logits = []
        hidden = embed
        
        # Run through layers to get realistic hidden states for router training
        if hasattr(self.model, 'language_model'):
            layers = self.model.language_model.model.layers
        elif hasattr(self.model, 'model') and hasattr(self.model.model, 'layers'):
            layers = self.model.model.layers
        else:
            layers = self.model.layers
        
        attn_every_n = 3  # Run full attention every 3rd layer (instead of 6th)
        
        for layer_idx, layer in enumerate(layers):
            with torch.no_grad():
                # Always apply input layernorm (cheap, crucial for realistic states)
                if hasattr(layer, 'input_layernorm'):
                    normed = layer.input_layernorm(hidden)
                else:
                    normed = hidden
                
                # Run attention on a subset of layers for realistic hidden evolution
                run_attn = (layer_idx % attn_every_n == 0) or (layer_idx < 3) or (layer_idx >= len(layers) - 3)
                
                if run_attn:
                    try:
                        # Generate position_ids for RoPE (required by Llama 4)
                        batch_size, seq_len = normed.shape[:2]
                        position_ids = torch.arange(seq_len, device=normed.device).unsqueeze(0).expand(batch_size, -1)
                        attn_output = layer.self_attn(
                            normed,
                            attention_mask=attention_mask,
                            position_ids=position_ids,
                        )
                        if isinstance(attn_output, tuple):
                            attn_out = attn_output[0]
                        else:
                            attn_out = attn_output
                        hidden = hidden + attn_out  # residual connection
                    except Exception as e:
                        log.warning(f"Attention failed at layer {layer_idx}: {e}")
                
                # Apply post-attention layernorm (always, cheap and important)
                if hasattr(layer, 'post_attention_layernorm'):
                    normed_ff = layer.post_attention_layernorm(hidden)
                else:
                    normed_ff = hidden
            
            # Router forward (TRAINABLE)
            if hasattr(layer, 'feed_forward') and hasattr(layer.feed_forward, 'router'):
                router = layer.feed_forward.router
                router_input = normed_ff.float()  # Router works in fp32
                
                # router_logits: [batch, seq_len, num_experts]
                router_logits = F.linear(router_input, router.weight)
                all_router_logits.append(router_logits)
            
            # Approximate FFN contribution (frozen) using shared expert if available
            with torch.no_grad():
                if hasattr(layer, 'feed_forward') and hasattr(layer.feed_forward, 'shared_expert'):
                    try:
                        shared_out = layer.feed_forward.shared_expert(normed_ff)
                        hidden = hidden + shared_out * 0.1  # Damped shared expert residual
                    except Exception as e:
                        log.warning(f"Shared expert failed at layer {layer_idx}: {e}")
        
        if not all_router_logits:
            raise RuntimeError("No router logits collected — model structure mismatch")
        
        # Stack all layers: [num_layers, batch, seq_len, num_experts]
        stacked_logits = torch.stack(all_router_logits)
        
        # Compute losses
        losses = self.compute_routing_losses(
            stacked_logits, target_expert, keyword_density, attention_mask,
            negative_densities=negative_densities,
            secondary_expert=secondary_expert,
        )
        
        return losses
    
    def compute_routing_losses(
        self,
        router_logits: torch.Tensor,     # [num_layers, batch, seq_len, num_experts]
        target_expert: torch.Tensor,      # [batch] — which new expert (16-19)
        keyword_density: torch.Tensor,    # [batch] — how strongly this should route to target
        attention_mask: Optional[torch.Tensor] = None,  # [batch, seq_len]
        negative_densities: Optional[torch.Tensor] = None,  # [batch, 4] — negative routing signal
        secondary_expert: Optional[torch.Tensor] = None,  # [batch] — secondary expert for chains
    ) -> dict:
        """
        Compute the composite routing loss:
        1. Specialization Loss: new experts should be selected for their data
        2. Load Balance Loss: prevent expert collapse
        3. Distillation Loss: maintain existing routing patterns
        """
        num_layers, batch, seq_len, num_experts = router_logits.shape
        
        # Mask padding tokens
        if attention_mask is not None:
            mask = attention_mask.unsqueeze(0).unsqueeze(-1).float()  # [1, batch, seq_len, 1]
        else:
            mask = torch.ones(1, batch, seq_len, 1, device=router_logits.device)
        
        router_probs = F.softmax(router_logits / self.config.routing_temperature, dim=-1)  # [L, B, S, E]
        
        # ─── 1. Specialization Loss ───
        # For each example, the target expert (16-19) should have high selection probability
        # Scale by keyword_density (how strongly this example matches the specialty)
        # V3.0: Also supports secondary_expert for cross-expert chains
        spec_loss = torch.tensor(0.0, device=router_logits.device)
        per_expert_correct = {16: 0.0, 17: 0.0, 18: 0.0, 19: 0.0}  # V3.0: Accuracy tracking
        per_expert_total = {16: 0.0, 17: 0.0, 18: 0.0, 19: 0.0}
        for b in range(batch):
            target_exp = target_expert[b].item()
            if 16 <= target_exp <= 19:
                density = keyword_density[b].clamp(0.1, 1.0)
                
                # Average probability of selecting the target expert across all layers & tokens
                target_prob = router_probs[:, b, :, target_exp]  # [L, S]
                if attention_mask is not None:
                    valid_mask = attention_mask[b].unsqueeze(0).float()  # [1, S]
                    target_prob = (target_prob * valid_mask).sum() / valid_mask.sum().clamp(min=1)
                else:
                    target_prob = target_prob.mean()
                
                # We want to MAXIMIZE target_prob → minimize negative log prob
                spec_loss += -torch.log(target_prob.clamp(min=1e-8)) * density
                
                # V3.0: Track per-expert routing accuracy (is target the argmax?)
                avg_probs = router_probs[:, b, :, :].mean(dim=(0, 1))  # [E]
                selected = avg_probs.argmax().item()
                per_expert_total[target_exp] += 1.0
                if selected == target_exp:
                    per_expert_correct[target_exp] += 1.0
                
                # V3.0: Secondary expert for cross-expert chains
                if secondary_expert is not None:
                    sec_exp = secondary_expert[b].item()
                    if 16 <= sec_exp <= 19 and sec_exp != target_exp:
                        sec_prob = router_probs[:, b, :, sec_exp]
                        if attention_mask is not None:
                            sec_prob = (sec_prob * valid_mask).sum() / valid_mask.sum().clamp(min=1)
                        else:
                            sec_prob = sec_prob.mean()
                        # Secondary expert should also have moderate probability (0.5x weight)
                        spec_loss += -torch.log(sec_prob.clamp(min=1e-8)) * density * 0.5
        
        spec_loss = spec_loss / max(batch, 1)
        
        # ─── 2. Load Balance Loss ───
        # Each expert should receive a minimum fraction of tokens
        # Penalize imbalanced routing
        expert_counts = (router_probs * mask).sum(dim=(1, 2))  # [L, E]
        total_tokens = mask.sum(dim=(1, 2, 3))  # [L]
        expert_fractions = expert_counts / total_tokens.unsqueeze(-1).clamp(min=1)
        
        # Coefficient of Variation penalty (lower = more balanced)
        mean_fraction = expert_fractions.mean(dim=-1, keepdim=True)
        std_fraction = expert_fractions.std(dim=-1, keepdim=True)
        cv = (std_fraction / mean_fraction.clamp(min=1e-8)).mean()
        
        # Dead expert penalty: extra loss if any expert gets < min_utilization
        min_util = self.config.min_expert_utilization
        dead_penalty = F.relu(min_util - expert_fractions).sum() / (num_layers * num_experts)
        
        balance_loss = cv + dead_penalty * 10.0
        
        # ─── 3. Distillation Loss ───
        # Keep the first 16 expert routing weights similar to original
        distill_loss = torch.tensor(0.0, device=router_logits.device)
        for name, param in self.model.named_parameters():
            if "router.weight" in name and name in self.original_routers:
                original = self.original_routers[name]
                current = param[:self.config.num_original_experts]  # First 16 rows
                original_16 = original[:self.config.num_original_experts]
                distill_loss += F.mse_loss(current, original_16.to(current.device))
        
        # ─── 4. Standard Auxiliary MoE Loss ───
        # From the original Llama 4 config: router_aux_loss_coef = 0.001
        # Importance-weighted balance loss
        router_probs_flat = router_probs.reshape(-1, num_experts)
        fraction_per_expert = router_probs_flat.mean(dim=0)
        aux_loss = (fraction_per_expert * torch.log(fraction_per_expert.clamp(min=1e-8) * num_experts)).sum()
        
        # ─── 5. v2.0: Contrastive Loss ───
        # Push the router rows for different new experts apart
        # If expert 16 (visual) and expert 19 (retry) have similar router rows,
        # the router can't distinguish between them
        contrastive_loss = torch.tensor(0.0, device=router_logits.device)
        contrastive_pairs = 0
        margin = self.config.contrastive_margin
        
        for name, param in self.model.named_parameters():
            if "router.weight" in name and param.requires_grad:
                w = param.float()
                if w.shape[0] >= 20:
                    new_rows = w[16:20]  # [4, hidden_size]
                    # All pairs of new experts should be dissimilar
                    for i in range(4):
                        for j in range(i + 1, 4):
                            cos_sim = F.cosine_similarity(
                                new_rows[i].unsqueeze(0),
                                new_rows[j].unsqueeze(0)
                            )
                            # Hinge loss: penalize if similarity > margin
                            contrastive_loss += F.relu(cos_sim - (1.0 - margin))
                            contrastive_pairs += 1
        
        if contrastive_pairs > 0:
            contrastive_loss = contrastive_loss / contrastive_pairs
        
        # ─── 6. V3.0: Negative Routing Loss ───
        # Push tokens AWAY from experts whose negative keywords match the text.
        # This prevents e.g. "retry" tokens from routing to visual_grounding.
        # Uses the negative_densities signal from the dataset.
        negative_loss = torch.tensor(0.0, device=router_logits.device)
        if negative_densities is not None:
            for b in range(batch):
                for i, eid in enumerate(range(16, 20)):
                    neg_d = negative_densities[b, i].item()
                    if neg_d > 0.0:
                        # This text has negative keywords for expert `eid`
                        # → penalize routing probability toward that expert
                        wrong_prob = router_probs[:, b, :, eid]  # [L, S]
                        if attention_mask is not None:
                            valid_mask = attention_mask[b].unsqueeze(0).float()
                            wrong_prob = (wrong_prob * valid_mask).sum() / valid_mask.sum().clamp(min=1)
                        else:
                            wrong_prob = wrong_prob.mean()
                        # Maximize -log(1 - wrong_prob) → minimize wrong_prob
                        negative_loss += -torch.log((1.0 - wrong_prob).clamp(min=1e-8)) * neg_d
            negative_loss = negative_loss / max(batch * 4, 1)
        
        # ─── 7. v2.0: Diversity Loss ───
        # New expert rows should also be different from the closest old expert
        diversity_loss = torch.tensor(0.0, device=router_logits.device)
        diversity_count = 0
        
        for name, param in self.model.named_parameters():
            if "router.weight" in name and param.requires_grad:
                w = param.float()
                if w.shape[0] >= 20:
                    old_rows = w[:16]  # [16, hidden_size]
                    new_rows = w[16:20]  # [4, hidden_size]
                    # Each new expert should be different from ALL old experts
                    for i in range(4):
                        sims = F.cosine_similarity(
                            new_rows[i].unsqueeze(0),  # [1, H]
                            old_rows,                    # [16, H]
                        )  # [16]
                        max_sim_to_old = sims.max()
                        # Penalize if too similar to any old expert
                        diversity_loss += F.relu(max_sim_to_old - 0.95)
                        diversity_count += 1
        
        if diversity_count > 0:
            diversity_loss = diversity_loss / diversity_count
        
        # ─── Combined Loss ───
        # Use dynamic weights if available (from curriculum scheduler)
        spec_w = getattr(self, '_dynamic_spec_weight', self.config.specialization_loss_weight)
        bal_w = getattr(self, '_dynamic_balance_weight', self.config.load_balance_loss_weight)
        dist_w = getattr(self, '_dynamic_distill_weight', self.config.distillation_loss_weight)
        contr_w = getattr(self, '_dynamic_contrastive_weight', self.config.contrastive_loss_weight)
        div_w = getattr(self, '_dynamic_diversity_weight', self.config.diversity_loss_weight)
        neg_w = getattr(self, '_dynamic_negative_weight', 1.0)  # V3.0: Negative routing weight
        
        total_loss = (
            spec_w * spec_loss +
            bal_w * balance_loss +
            dist_w * distill_loss +
            self.config.aux_loss_weight * aux_loss +
            contr_w * contrastive_loss +
            div_w * diversity_loss +
            neg_w * negative_loss  # V3.0
        )
        
        # V3.0: Per-expert routing accuracy
        per_expert_acc = {}
        for eid in range(16, 20):
            total = per_expert_total[eid]
            correct = per_expert_correct[eid]
            per_expert_acc[eid] = correct / max(total, 1.0)
        
        return {
            "total_loss": total_loss,
            "specialization_loss": spec_loss.detach(),
            "balance_loss": balance_loss.detach(),
            "distillation_loss": distill_loss.detach(),
            "aux_loss": aux_loss.detach(),
            "contrastive_loss": contrastive_loss.detach(),
            "diversity_loss": diversity_loss.detach(),
            "negative_loss": negative_loss.detach(),  # V3.0
            "mean_new_expert_prob": router_probs[:, :, :, 16:20].mean().detach(),
            "mean_original_expert_prob": router_probs[:, :, :, :16].mean().detach(),
            "per_expert_accuracy": per_expert_acc,  # V3.0
        }
    
    def set_dynamic_weights(self, weights: Dict[str, float]):
        """Set dynamic loss weights (called by CurriculumScheduler)."""
        self._dynamic_spec_weight = weights.get("specialization_weight", self.config.specialization_loss_weight)
        self._dynamic_balance_weight = weights.get("balance_weight", self.config.load_balance_loss_weight)
        self._dynamic_distill_weight = weights.get("distillation_weight", self.config.distillation_loss_weight)
        self._dynamic_contrastive_weight = weights.get("contrastive_weight", self.config.contrastive_loss_weight)
        self._dynamic_diversity_weight = weights.get("diversity_weight", self.config.diversity_loss_weight)
    
    def set_routing_temperature(self, temp: float):
        """Dynamically adjust routing temperature (called by CurriculumScheduler)."""
        self.config.routing_temperature = temp


# ═══════════════════════════════════════════════════════════════
# TRAINING LOOP
# ═══════════════════════════════════════════════════════════════

def train_router(config: RouterTuningConfig):
    """Main router training function."""
    
    log.info("=" * 70)
    log.info("  Router Fine-Tuning for New MoE Experts")
    log.info("=" * 70)
    
    # ─── Load tokenizer ───
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(
        config.model_dir,
        trust_remote_code=True,
        padding_side="right",
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # ─── Load model (4-bit quantized) ───
    log.info("Loading model (4-bit quantized)...")
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
        llm_int8_skip_modules=["vision_model", "multi_modal_projector", "lm_head", "router"],
    )
    
    model = AutoModelForCausalLM.from_pretrained(
        config.model_dir,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.bfloat16,
        trust_remote_code=True,
        attn_implementation="flash_attention_2",
    )
    
    log.info(f"Model loaded. Memory: {torch.cuda.memory_allocated() / 1e9:.1f} GB")
    
    # ─── Wrap model for router training ───
    tuner = RouterTuner(model, config)
    
    # ─── Load dataset ───
    full_dataset = RouterTrainingDataset(
        data_dir=config.training_data_dir,
        tokenizer=tokenizer,
        max_length=config.max_seq_length,
    )
    
    # v2.0: Split into train/eval
    n_eval = max(int(len(full_dataset) * config.eval_split_ratio), 1)
    n_train = len(full_dataset) - n_eval
    indices = list(range(len(full_dataset)))
    random.shuffle(indices)
    train_indices = indices[:n_train]
    eval_indices = indices[n_train:]
    
    train_dataset = Subset(full_dataset, train_indices)
    eval_dataset = Subset(full_dataset, eval_indices)
    
    dataloader = DataLoader(
        train_dataset,
        batch_size=config.batch_size,
        shuffle=True,
        num_workers=2,
        pin_memory=True,
        drop_last=True,
    )
    
    eval_dataloader = DataLoader(
        eval_dataset,
        batch_size=config.batch_size,
        shuffle=False,
        num_workers=0,
        drop_last=False,
    )
    
    log.info(f"Dataset split: {n_train} train, {n_eval} eval")
    
    # ─── Optimizer with per-expert LR (v2.0) ───
    router_params = tuner.get_router_params()
    
    if config.new_expert_lr_multiplier != 1.0:
        # Separate parameter groups: new expert rows get higher LR
        param_groups = []
        for name, param in tuner.model.named_parameters():
            if param.requires_grad:
                # Router weights contain both old (rows 0-15) and new (rows 16-19) expert rows
                # We can't split a single tensor into different LR groups,
                # but we can apply a per-expert gradient scaling hook
                param_groups.append({
                    "params": [param],
                    "lr": config.learning_rate,
                    "name": name,
                })
        
        optimizer = torch.optim.AdamW(
            param_groups,
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            betas=(0.9, 0.95),
        )
        
        # v2.0: Register gradient scaling hook for new expert rows
        def scale_new_expert_grads():
            """Scale gradients for new expert rows (16-19) by multiplier."""
            for name, param in tuner.model.named_parameters():
                if param.requires_grad and param.grad is not None:
                    if "router.weight" in name and param.shape[0] >= 20:
                        # Scale gradient for new expert rows
                        param.grad.data[16:20] *= config.new_expert_lr_multiplier
    else:
        optimizer = torch.optim.AdamW(
            router_params,
            lr=config.learning_rate,
            weight_decay=config.weight_decay,
            betas=(0.9, 0.95),
        )
        scale_new_expert_grads = None
    
    # ─── Learning rate scheduler (cosine with warmup) ───
    total_steps = len(dataloader) * config.num_epochs // config.gradient_accumulation
    
    def lr_lambda(step):
        if step < config.warmup_steps:
            return step / max(config.warmup_steps, 1)
        progress = (step - config.warmup_steps) / max(total_steps - config.warmup_steps, 1)
        return 0.1 + 0.9 * (1 + math.cos(math.pi * progress)) / 2
    
    scheduler = torch.optim.lr_scheduler.LambdaLR(optimizer, lr_lambda)
    
    # ─── AMP scaler ───
    scaler = torch.amp.GradScaler("cuda") if config.use_amp and config.device == "cuda" else None
    
    # ─── Wandb ───
    if config.use_wandb:
        try:
            import wandb
            wandb.init(
                project=config.wandb_project,
                config=vars(config),
                name="router-tuning-v2",
            )
        except Exception as e:
            log.warning(f"Wandb init failed: {e}")
            config.use_wandb = False
    
    # ─── v2.0: Curriculum Scheduler ───
    curriculum = CurriculumScheduler(config, total_steps)
    
    # ─── v2.0: Gradient Monitor ───
    grad_monitor = GradientMonitor() if config.monitor_gradients else None
    
    # ─── v2.0: Resume from checkpoint ───
    start_epoch = 0
    global_step = 0
    best_new_expert_prob = 0.0
    
    if config.resume_from:
        resume_path = Path(config.resume_from)
        if (resume_path / "training_state.pt").exists():
            log.info(f"Resuming from checkpoint: {resume_path}")
            state = torch.load(resume_path / "training_state.pt", map_location="cpu")
            start_epoch = state.get("epoch", 0)
            global_step = state.get("global_step", 0)
            best_new_expert_prob = state.get("best_new_expert_prob", 0.0)
            optimizer.load_state_dict(state["optimizer_state"])
            scheduler.load_state_dict(state["scheduler_state"])
            log.info(f"  Resumed at epoch {start_epoch}, step {global_step}")
        
        if (resume_path / "router_weights.pt").exists():
            router_state = torch.load(resume_path / "router_weights.pt", map_location="cpu")
            for name, param in tuner.model.named_parameters():
                if name in router_state:
                    param.data.copy_(router_state[name].to(param.device))
            log.info(f"  Loaded router weights from checkpoint")
    
    # ─── Training loop ───
    log.info(f"Starting training: {config.num_epochs} epochs, {len(dataloader)} batches/epoch")
    log.info(f"Total steps: {total_steps}, warmup: {config.warmup_steps}")
    if config.curriculum_enabled:
        log.info(f"Curriculum: {config.curriculum_phases} phases, {curriculum.phase_length} steps/phase")
    
    patience_counter = 0
    train_start_time = time.time()
    
    output_path = Path(config.output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    for epoch in range(start_epoch, config.num_epochs):
        curr_phase = curriculum.get_phase(global_step)
        log.info(f"\n{'='*50} Epoch {epoch+1}/{config.num_epochs} "
                 f"(curriculum phase {curr_phase+1}/{config.curriculum_phases}) {'='*50}")
        
        epoch_losses = {
            "total": 0.0, "spec": 0.0, "balance": 0.0, "distill": 0.0, "aux": 0.0,
            "contrastive": 0.0, "diversity": 0.0, "negative": 0.0,
        }
        epoch_metrics = {"new_prob": 0.0, "orig_prob": 0.0}
        # V3.0: Track per-expert routing accuracy across epoch
        epoch_per_expert_acc = {16: [], 17: [], 18: [], 19: []}
        n_batches = 0
        
        optimizer.zero_grad()
        
        for batch_idx, batch in enumerate(tqdm(dataloader, desc=f"Epoch {epoch+1}")):
            # v2.0: Update curriculum weights
            curr_weights = curriculum.get_weights(global_step)
            tuner.set_dynamic_weights(curr_weights)
            tuner.set_routing_temperature(curr_weights.get("routing_temperature", config.routing_temperature))
            
            # Move to device
            input_ids = batch["input_ids"].to(config.device)
            attention_mask = batch["attention_mask"].to(config.device)
            target_expert = batch["target_expert"].to(config.device)
            keyword_density = batch["keyword_density"].to(config.device)
            # V3.0: Negative routing & cross-expert signals
            negative_densities = batch["negative_densities"].to(config.device) if "negative_densities" in batch else None
            secondary_expert = batch["secondary_expert"].to(config.device) if "secondary_expert" in batch else None
            
            # Forward
            if config.use_amp and scaler is not None:
                with torch.amp.autocast("cuda"):
                    losses = tuner(input_ids, attention_mask, target_expert, keyword_density,
                                   negative_densities=negative_densities,
                                   secondary_expert=secondary_expert)
                
                loss = losses["total_loss"] / config.gradient_accumulation
                scaler.scale(loss).backward()
                
                if (batch_idx + 1) % config.gradient_accumulation == 0:
                    scaler.unscale_(optimizer)
                    
                    # v2.0: Scale new expert gradients before clipping
                    if scale_new_expert_grads is not None:
                        scale_new_expert_grads()
                    
                    # v2.0: Gradient monitoring
                    if grad_monitor and global_step % config.gradient_log_every == 0:
                        grad_info = grad_monitor.log_gradients(tuner.model, global_step)
                    
                    torch.nn.utils.clip_grad_norm_(router_params, config.max_grad_norm)
                    scaler.step(optimizer)
                    scaler.update()
                    optimizer.zero_grad()
                    scheduler.step()
                    global_step += 1
            else:
                losses = tuner(input_ids, attention_mask, target_expert, keyword_density,
                               negative_densities=negative_densities,
                               secondary_expert=secondary_expert)
                loss = losses["total_loss"] / config.gradient_accumulation
                loss.backward()
                
                if (batch_idx + 1) % config.gradient_accumulation == 0:
                    # v2.0: Scale new expert gradients before clipping
                    if scale_new_expert_grads is not None:
                        scale_new_expert_grads()
                    
                    # v2.0: Gradient monitoring
                    if grad_monitor and global_step % config.gradient_log_every == 0:
                        grad_info = grad_monitor.log_gradients(tuner.model, global_step)
                    
                    torch.nn.utils.clip_grad_norm_(router_params, config.max_grad_norm)
                    optimizer.step()
                    optimizer.zero_grad()
                    scheduler.step()
                    global_step += 1
            
            # Track metrics
            epoch_losses["total"] += losses["total_loss"].item()
            epoch_losses["spec"] += losses["specialization_loss"].item()
            epoch_losses["balance"] += losses["balance_loss"].item()
            epoch_losses["distill"] += losses["distillation_loss"].item()
            epoch_losses["aux"] += losses["aux_loss"].item()
            epoch_losses["contrastive"] += losses["contrastive_loss"].item()
            epoch_losses["diversity"] += losses["diversity_loss"].item()
            epoch_losses["negative"] += losses["negative_loss"].item()  # V3.0
            epoch_metrics["new_prob"] += losses["mean_new_expert_prob"].item()
            epoch_metrics["orig_prob"] += losses["mean_original_expert_prob"].item()
            # V3.0: Per-expert accuracy
            per_acc = losses.get("per_expert_accuracy", {})
            for eid in range(16, 20):
                if eid in per_acc:
                    epoch_per_expert_acc[eid].append(per_acc[eid])
            n_batches += 1
            
            # Log
            if (batch_idx + 1) % config.log_every == 0:
                avg = {k: v / n_batches for k, v in epoch_losses.items()}
                new_prob = epoch_metrics["new_prob"] / n_batches
                phase = curriculum.get_phase(global_step)
                # V3.0: Compute per-expert accuracy for logging
                acc_strs = []
                for eid in range(16, 20):
                    vals = epoch_per_expert_acc[eid]
                    acc_val = np.mean(vals) if vals else 0.0
                    acc_strs.append(f"E{eid}={acc_val:.0%}")
                acc_str = ", ".join(acc_strs)
                log.info(
                    f"  Step {global_step} [P{phase+1}] | "
                    f"Loss: {avg['total']:.4f} (spec={avg['spec']:.4f}, bal={avg['balance']:.4f}, "
                    f"neg={avg['negative']:.4f}, contr={avg['contrastive']:.4f}) | "
                    f"New expert prob: {new_prob:.4f} | Acc: [{acc_str}] | "
                    f"LR: {scheduler.get_last_lr()[0]:.2e}"
                )
                
                if config.use_wandb:
                    import wandb
                    log_dict = {
                        "loss/total": avg["total"],
                        "loss/specialization": avg["spec"],
                        "loss/balance": avg["balance"],
                        "loss/distillation": avg["distill"],
                        "loss/contrastive": avg["contrastive"],
                        "loss/diversity": avg["diversity"],
                        "loss/negative": avg["negative"],  # V3.0
                        "routing/new_expert_prob": new_prob,
                        "routing/original_expert_prob": epoch_metrics["orig_prob"] / n_batches,
                        "curriculum/phase": phase + 1,
                        "lr": scheduler.get_last_lr()[0],
                        "step": global_step,
                    }
                    # V3.0: Per-expert accuracy metrics
                    for eid in range(16, 20):
                        vals = epoch_per_expert_acc[eid]
                        ename = EXPERT_KEYWORDS[eid]["name"]
                        log_dict[f"accuracy/{ename}"] = np.mean(vals) if vals else 0.0
                    wandb.log(log_dict)
            
            # v2.0: Run evaluation periodically
            if global_step > 0 and global_step % config.eval_every == 0 and len(eval_dataloader) > 0:
                eval_metrics = evaluate_routing(tuner, eval_dataloader, config)
                log.info(f"  [EVAL] Step {global_step}: "
                         f"loss={eval_metrics['eval_loss']:.4f}, "
                         f"new_prob={eval_metrics['new_expert_avg_prob']:.4f}")
                
                if config.use_wandb:
                    import wandb
                    wandb.log({f"eval/{k}": v for k, v in eval_metrics.items()}, step=global_step)
            
            # Save checkpoint
            if global_step > 0 and global_step % config.save_every == 0:
                save_router_checkpoint(tuner, output_path / f"checkpoint-{global_step}",
                                       epoch, global_step, best_new_expert_prob,
                                       optimizer, scheduler)
        
        # End of epoch
        avg = {k: v / max(n_batches, 1) for k, v in epoch_losses.items()}
        new_prob = epoch_metrics["new_prob"] / max(n_batches, 1)
        
        log.info(f"\n  Epoch {epoch+1} Summary:")
        log.info(f"    Total loss: {avg['total']:.4f}")
        log.info(f"    Specialization: {avg['spec']:.4f}")
        log.info(f"    Balance: {avg['balance']:.4f}")
        log.info(f"    Distillation: {avg['distill']:.6f}")
        log.info(f"    Contrastive: {avg['contrastive']:.4f}")
        log.info(f"    Diversity: {avg['diversity']:.4f}")
        log.info(f"    Negative routing: {avg['negative']:.4f}")  # V3.0
        log.info(f"    New expert avg prob: {new_prob:.4f}")
        log.info(f"    Curriculum phase: {curriculum.get_phase(global_step) + 1}")
        # V3.0: Per-expert routing accuracy
        log.info(f"    Per-expert routing accuracy:")
        for eid in range(16, 20):
            ename = EXPERT_KEYWORDS[eid]["name"]
            vals = epoch_per_expert_acc[eid]
            acc = np.mean(vals) if vals else 0.0
            log.info(f"      Expert {eid} ({ename}): {acc:.1%}")
        
        # v2.0: End-of-epoch evaluation
        if len(eval_dataloader) > 0:
            eval_metrics = evaluate_routing(tuner, eval_dataloader, config)
            log.info(f"    Eval loss: {eval_metrics['eval_loss']:.4f}")
            log.info(f"    Eval new expert prob: {eval_metrics['new_expert_avg_prob']:.4f}")
        
        # v2.0: Gradient summary
        if grad_monitor:
            grad_summary = grad_monitor.get_summary()
            if grad_summary:
                log.info(f"    Gradient trend: {grad_summary['trend']} "
                         f"(avg norm={grad_summary['avg_total_norm']:.4f})")
        
        # Save best
        if new_prob > best_new_expert_prob:
            best_new_expert_prob = new_prob
            save_router_checkpoint(tuner, output_path / "best", epoch, global_step,
                                   best_new_expert_prob, optimizer, scheduler)
            log.info(f"    ★ New best model saved (new expert prob: {new_prob:.4f})")
            patience_counter = 0
        else:
            patience_counter += 1
            if patience_counter >= 3 and epoch >= 2:
                log.info(f"    Early stopping: no improvement for {patience_counter} epochs")
                break
        
        # Per-expert routing analysis at end of each epoch
        log.info(f"    Per-expert routing analysis (epoch {epoch+1}):")
        for name, param in tuner.model.named_parameters():
            if "router.weight" in name and "layers.0." in name:
                # Analyze router weight norms for layer 0 as representative
                w = param.data.float()
                for eid in range(16, 20):
                    ename = EXPERT_KEYWORDS[eid]["name"]
                    row_norm = w[eid].norm().item()
                    row_mean = w[eid].mean().item()
                    orig_mean_norm = w[:16].norm(dim=1).mean().item()
                    log.info(f"      Expert {eid} ({ename}): "
                             f"norm={row_norm:.4f} (orig avg={orig_mean_norm:.4f}), "
                             f"mean={row_mean:.6f}")
                break
    
    # Final save
    save_router_checkpoint(tuner, output_path / "final", config.num_epochs - 1,
                           global_step, best_new_expert_prob, optimizer, scheduler)
    
    train_time = time.time() - train_start_time
    log.info(f"\nTraining complete! Best new expert probability: {best_new_expert_prob:.4f}")
    log.info(f"Total time: {train_time/60:.1f} minutes ({train_time/3600:.2f} hours)")
    log.info(f"Router checkpoints saved to: {output_path}")
    
    # v2.0: Save training summary
    summary = {
        "best_new_expert_prob": best_new_expert_prob,
        "total_steps": global_step,
        "total_time_s": round(train_time, 1),
        "final_losses": avg,
        "config": {k: str(v) if isinstance(v, Path) else v for k, v in vars(config).items()},
    }
    if grad_monitor:
        summary["gradient_summary"] = grad_monitor.get_summary()
    
    with open(output_path / "training_summary.json", "w") as f:
        json.dump(summary, f, indent=2)
    log.info(f"Training summary saved to: {output_path / 'training_summary.json'}")
    
    if config.use_wandb:
        import wandb
        wandb.finish()


def save_router_checkpoint(
    tuner: RouterTuner,
    output_dir: Path,
    epoch: int = 0,
    global_step: int = 0,
    best_new_expert_prob: float = 0.0,
    optimizer: Optional[torch.optim.Optimizer] = None,
    scheduler: Optional[torch.optim.lr_scheduler.LambdaLR] = None,
):
    """Save router weights and full training state for resume."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Save router weights
    router_state = {}
    for name, param in tuner.model.named_parameters():
        if "router.weight" in name:
            router_state[name] = param.data.cpu().clone()
    
    torch.save(router_state, output_dir / "router_weights.pt")
    
    # v2.0: Save training state for resume
    training_state = {
        "epoch": epoch + 1,
        "global_step": global_step,
        "best_new_expert_prob": best_new_expert_prob,
    }
    if optimizer is not None:
        training_state["optimizer_state"] = optimizer.state_dict()
    if scheduler is not None:
        training_state["scheduler_state"] = scheduler.state_dict()
    
    torch.save(training_state, output_dir / "training_state.pt")
    
    size_mb = sum(v.numel() * 4 for v in router_state.values()) / 1024 / 1024
    log.info(f"  Saved checkpoint: {output_dir} ({size_mb:.1f} MB router, step {global_step})")


# ═══════════════════════════════════════════════════════════════
# v2.0: ROUTER ANALYSIS
# ═══════════════════════════════════════════════════════════════

def analyze_router_weights(checkpoint_dir: str, output_file: Optional[str] = None):
    """
    Analyze trained router weights to understand expert specialization.
    
    Reports:
    - Per-layer router weight statistics (mean, std, norm)
    - Cosine similarity matrix between all 20 experts
    - New expert distinctiveness metrics
    - PCA projection of expert weight vectors
    - Expert specialization scores
    """
    checkpoint_path = Path(checkpoint_dir) / "router_weights.pt"
    if not checkpoint_path.exists():
        log.error(f"Checkpoint not found: {checkpoint_path}")
        return
    
    router_state = torch.load(checkpoint_path, map_location="cpu")
    
    log.info(f"Analyzing {len(router_state)} router weights from {checkpoint_dir}")
    
    analysis = {
        "per_layer": {},
        "summary": {},
    }
    
    all_new_expert_norms = defaultdict(list)
    all_old_expert_norms = []
    all_similarity_matrices = []
    
    for name, weight in sorted(router_state.items()):
        w = weight.float()
        
        if w.shape[0] < 20:
            continue
        
        # Extract layer number
        layer_num = None
        parts = name.split(".")
        for i, p in enumerate(parts):
            if p == "layers" and i + 1 < len(parts):
                try:
                    layer_num = int(parts[i + 1])
                except ValueError:
                    pass
        
        if layer_num is None:
            continue
        
        # Per-expert statistics
        expert_stats = {}
        for eid in range(20):
            row = w[eid]
            expert_stats[eid] = {
                "norm": row.norm().item(),
                "mean": row.mean().item(),
                "std": row.std().item(),
                "min": row.min().item(),
                "max": row.max().item(),
            }
            
            if eid >= 16:
                all_new_expert_norms[eid].append(row.norm().item())
            else:
                all_old_expert_norms.append(row.norm().item())
        
        # Cosine similarity matrix between all experts
        w_normed = F.normalize(w, dim=1)
        sim_matrix = (w_normed @ w_normed.T).numpy()
        all_similarity_matrices.append(sim_matrix)
        
        # New expert similarity to each other
        new_inter_sim = []
        for i in range(16, 20):
            for j in range(i + 1, 20):
                new_inter_sim.append(sim_matrix[i, j])
        
        # New expert max similarity to old experts
        new_old_max_sim = []
        for i in range(16, 20):
            max_sim_to_old = max(sim_matrix[i, j] for j in range(16))
            new_old_max_sim.append(max_sim_to_old)
        
        layer_data = {
            "expert_stats": {str(k): v for k, v in expert_stats.items()},
            "new_inter_similarity": {
                "mean": float(np.mean(new_inter_sim)),
                "max": float(max(new_inter_sim)),
                "min": float(min(new_inter_sim)),
            },
            "new_old_max_similarity": {
                "mean": float(np.mean(new_old_max_sim)),
                "max": float(max(new_old_max_sim)),
                "per_expert": {str(16 + i): float(s) for i, s in enumerate(new_old_max_sim)},
            },
        }
        
        analysis["per_layer"][str(layer_num)] = layer_data
    
    # Summary statistics
    for eid in range(16, 20):
        if eid in all_new_expert_norms:
            norms = all_new_expert_norms[eid]
            ename = EXPERT_KEYWORDS[eid]["name"]
            analysis["summary"][f"expert_{eid}_{ename}"] = {
                "avg_norm": float(np.mean(norms)),
                "std_norm": float(np.std(norms)),
                "min_norm": float(min(norms)),
                "max_norm": float(max(norms)),
            }
    
    if all_old_expert_norms:
        analysis["summary"]["original_experts_avg_norm"] = float(np.mean(all_old_expert_norms))
    
    # Average similarity matrix across layers
    if all_similarity_matrices:
        avg_sim = np.mean(all_similarity_matrices, axis=0)
        analysis["summary"]["avg_similarity_matrix_new_block"] = {
            f"{i}-{j}": float(avg_sim[i, j])
            for i in range(16, 20) for j in range(i + 1, 20)
        }
    
    # PCA of expert weight vectors (from first layer)
    first_layer_name = sorted(router_state.keys())[0]
    w = router_state[first_layer_name].float()
    if w.shape[0] >= 20:
        try:
            # Mean-center
            w_centered = w - w.mean(dim=0, keepdim=True)
            # SVD for PCA
            U, S, V = torch.svd(w_centered)
            # Project to 2D
            proj_2d = (w_centered @ V[:, :2]).numpy()
            
            analysis["summary"]["pca_2d"] = {
                str(i): {"x": float(proj_2d[i, 0]), "y": float(proj_2d[i, 1])}
                for i in range(20)
            }
            analysis["summary"]["pca_explained_variance"] = {
                "pc1": float(S[0] ** 2 / (S ** 2).sum()),
                "pc2": float(S[1] ** 2 / (S ** 2).sum()),
            }
        except Exception as e:
            log.warning(f"PCA failed: {e}")
    
    # Print summary
    log.info("\n" + "=" * 60)
    log.info("  Router Weight Analysis")
    log.info("=" * 60)
    
    for eid in range(16, 20):
        ename = EXPERT_KEYWORDS[eid]["name"]
        key = f"expert_{eid}_{ename}"
        if key in analysis["summary"]:
            stats = analysis["summary"][key]
            log.info(f"  Expert {eid} ({ename}): "
                     f"avg_norm={stats['avg_norm']:.4f} ± {stats['std_norm']:.4f}")
    
    if "original_experts_avg_norm" in analysis["summary"]:
        log.info(f"  Original experts avg norm: {analysis['summary']['original_experts_avg_norm']:.4f}")
    
    if "avg_similarity_matrix_new_block" in analysis["summary"]:
        sims = analysis["summary"]["avg_similarity_matrix_new_block"]
        log.info(f"  New expert inter-similarity: {list(sims.values())}")
    
    # Save analysis
    if output_file:
        with open(output_file, "w") as f:
            json.dump(analysis, f, indent=2)
        log.info(f"  Analysis saved: {output_file}")
    
    return analysis


def compare_checkpoints(checkpoint_before: str, checkpoint_after: str):
    """
    Compare two router checkpoints to measure training progress.
    
    Reports per-layer:
    - Weight delta (L2 distance)
    - Changed expert ranking
    - Similarity shift
    """
    path_before = Path(checkpoint_before) / "router_weights.pt"
    path_after = Path(checkpoint_after) / "router_weights.pt"
    
    if not path_before.exists() or not path_after.exists():
        log.error("One or both checkpoint paths do not exist")
        return
    
    state_before = torch.load(path_before, map_location="cpu")
    state_after = torch.load(path_after, map_location="cpu")
    
    log.info(f"\nComparing checkpoints:")
    log.info(f"  Before: {checkpoint_before}")
    log.info(f"  After: {checkpoint_after}")
    log.info("")
    
    total_delta = 0.0
    new_expert_delta = 0.0
    old_expert_delta = 0.0
    n_layers = 0
    
    for name in sorted(state_before.keys()):
        if name not in state_after:
            continue
        
        w_before = state_before[name].float()
        w_after = state_after[name].float()
        
        if w_before.shape != w_after.shape:
            log.warning(f"Shape mismatch for {name}: {w_before.shape} vs {w_after.shape}")
            continue
        
        if w_before.shape[0] < 20:
            continue
        
        # Overall delta
        delta = (w_after - w_before).norm().item()
        total_delta += delta
        
        # New expert delta (rows 16-19)
        new_delta = (w_after[16:20] - w_before[16:20]).norm().item()
        new_expert_delta += new_delta
        
        # Old expert delta (rows 0-15)
        old_delta = (w_after[:16] - w_before[:16]).norm().item()
        old_expert_delta += old_delta
        
        n_layers += 1
        
        # Extract layer number for logging
        layer_num = "?"
        parts = name.split(".")
        for i, p in enumerate(parts):
            if p == "layers" and i + 1 < len(parts):
                layer_num = parts[i + 1]
        
        if n_layers <= 5 or delta > total_delta / max(n_layers, 1) * 2:
            log.info(f"  Layer {layer_num}: delta={delta:.6f} "
                     f"(new={new_delta:.6f}, old={old_delta:.6f})")
    
    if n_layers > 0:
        log.info(f"\n  Summary across {n_layers} layers:")
        log.info(f"    Total weight delta: {total_delta:.6f}")
        log.info(f"    New expert delta: {new_expert_delta:.6f} (avg {new_expert_delta/n_layers:.6f}/layer)")
        log.info(f"    Old expert delta: {old_expert_delta:.6f} (avg {old_expert_delta/n_layers:.6f}/layer)")
        
        ratio = new_expert_delta / max(old_expert_delta, 1e-10)
        log.info(f"    New/Old delta ratio: {ratio:.2f}x (higher = more new expert change, less old disruption)")
        
        if ratio > 5:
            log.info("    ★ Good: New experts changed significantly more than old ones")
        elif ratio > 2:
            log.info("    ○ Acceptable: New experts changed more but old experts also shifted")
        else:
            log.warning("    ⚠ Concerning: Old experts changed almost as much as new ones (catastrophic forgetting risk)")


def apply_router_checkpoint(model_dir: str, checkpoint_dir: str, output_dir: str):
    """
    Apply trained router weights back to the full model safetensors.
    This is run after training to produce the final model.
    """
    from safetensors.torch import load_file, save_file
    
    log.info("Applying trained router weights to model shards...")
    
    checkpoint_path = Path(checkpoint_dir) / "router_weights.pt"
    router_state = torch.load(checkpoint_path, map_location="cpu")
    
    model_path = Path(model_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Load index to find which shards contain which router weights
    with open(model_path / "model.safetensors.index.json") as f:
        index = json.load(f)
    
    import shutil
    
    # Map router param names to safetensors tensor names
    # Typical: "language_model.model.layers.X.feed_forward.router.weight"
    shard_updates = {}
    for param_name, weight in router_state.items():
        # Find matching key in the index
        for index_key, shard_name in index["weight_map"].items():
            if "router.weight" in index_key:
                # Check if this is the same layer
                # param_name might be: "language_model.model.layers.0.feed_forward.router.weight"
                # or: "model.layers.0.feed_forward.router.weight"
                # index_key: "language_model.model.layers.0.feed_forward.router.weight"
                param_layer = None
                for part_idx, part in enumerate(param_name.split(".")):
                    if part == "layers":
                        param_layer = param_name.split(".")[part_idx + 1]
                        break
                
                index_layer = None
                for part_idx, part in enumerate(index_key.split(".")):
                    if part == "layers":
                        index_layer = index_key.split(".")[part_idx + 1]
                        break
                
                if param_layer == index_layer:
                    if shard_name not in shard_updates:
                        shard_updates[shard_name] = {}
                    shard_updates[shard_name][index_key] = weight
    
    # Process each shard
    for shard_name in sorted(set(index["weight_map"].values())):
        src = model_path / shard_name
        dst = output_path / shard_name
        
        if shard_name in shard_updates:
            log.info(f"  Updating shard: {shard_name} ({len(shard_updates[shard_name])} router weights)")
            tensors = load_file(str(src))
            
            for key, weight in shard_updates[shard_name].items():
                if key in tensors:
                    tensors[key] = weight.to(tensors[key].dtype)
                    log.info(f"    Updated: {key}")
            
            save_file(tensors, str(dst))
        else:
            if not dst.exists():
                shutil.copy2(src, dst)
    
    # Copy other files
    for item in model_path.iterdir():
        if item.is_file() and not item.name.endswith(".safetensors"):
            dst = output_path / item.name
            if not dst.exists():
                shutil.copy2(item, dst)
    
    log.info("Router weights applied successfully!")


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Router Fine-Tuning v2.0 for New MoE Experts")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")
    
    # Train command
    train_parser = subparsers.add_parser("train", help="Train router weights")
    train_parser.add_argument("--model-dir", type=str, required=True, help="Model directory (post-injection)")
    train_parser.add_argument("--output-dir", type=str, required=True, help="Output directory for router checkpoints")
    train_parser.add_argument("--data-dir", type=str, required=True, help="Training data directory (JSONL files)")
    train_parser.add_argument("--epochs", type=int, default=5)
    train_parser.add_argument("--batch-size", type=int, default=4)
    train_parser.add_argument("--lr", type=float, default=5e-4)
    train_parser.add_argument("--wandb", action="store_true")
    train_parser.add_argument("--resume-from", type=str, default=None,
                              help="Resume training from checkpoint directory")
    train_parser.add_argument("--no-curriculum", action="store_true",
                              help="Disable curriculum learning")
    train_parser.add_argument("--new-expert-lr-mult", type=float, default=3.0,
                              help="Learning rate multiplier for new expert rows (default: 3.0)")
    train_parser.add_argument("--contrastive-weight", type=float, default=0.5,
                              help="Contrastive loss weight (default: 0.5)")
    train_parser.add_argument("--eval-split", type=float, default=0.1,
                              help="Fraction of data for evaluation (default: 0.1)")
    train_parser.add_argument("--no-grad-monitor", action="store_true",
                              help="Disable gradient monitoring")
    
    # Apply command
    apply_parser = subparsers.add_parser("apply", help="Apply router checkpoint to model")
    apply_parser.add_argument("--model-dir", type=str, required=True)
    apply_parser.add_argument("--checkpoint-dir", type=str, required=True)
    apply_parser.add_argument("--output-dir", type=str, required=True)
    
    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Analyze router weights from checkpoint")
    analyze_parser.add_argument("--checkpoint-dir", type=str, required=True)
    analyze_parser.add_argument("--output", type=str, default=None, help="Output JSON file")
    
    # Compare command
    compare_parser = subparsers.add_parser("compare", help="Compare two router checkpoints")
    compare_parser.add_argument("--before", type=str, required=True, help="Before checkpoint dir")
    compare_parser.add_argument("--after", type=str, required=True, help="After checkpoint dir")
    
    args = parser.parse_args()
    
    # Backward compatibility: if no subcommand, check for old-style args
    if args.command is None:
        # Try old-style argument parsing
        old_parser = argparse.ArgumentParser()
        old_parser.add_argument("--model-dir", type=str, required=True)
        old_parser.add_argument("--output-dir", type=str, required=True)
        old_parser.add_argument("--data-dir", type=str, required=True)
        old_parser.add_argument("--epochs", type=int, default=5)
        old_parser.add_argument("--batch-size", type=int, default=4)
        old_parser.add_argument("--lr", type=float, default=5e-4)
        old_parser.add_argument("--wandb", action="store_true")
        old_parser.add_argument("--apply-checkpoint", type=str, default=None)
        old_parser.add_argument("--final-output-dir", type=str, default=None)
        old_parser.add_argument("--resume-from", type=str, default=None)
        old_parser.add_argument("--no-curriculum", action="store_true")
        old_parser.add_argument("--new-expert-lr-mult", type=float, default=3.0)
        old_parser.add_argument("--contrastive-weight", type=float, default=0.5)
        old_parser.add_argument("--eval-split", type=float, default=0.1)
        old_parser.add_argument("--no-grad-monitor", action="store_true")
        
        try:
            args = old_parser.parse_args()
        except SystemExit:
            parser.print_help()
            sys.exit(1)
        
        if hasattr(args, 'apply_checkpoint') and args.apply_checkpoint:
            apply_router_checkpoint(
                model_dir=args.model_dir,
                checkpoint_dir=args.apply_checkpoint,
                output_dir=getattr(args, 'final_output_dir', None) or args.output_dir,
            )
            return
        
        config = RouterTuningConfig(
            model_dir=args.model_dir,
            output_dir=args.output_dir,
            training_data_dir=args.data_dir,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            use_wandb=args.wandb,
            resume_from=args.resume_from,
            curriculum_enabled=not args.no_curriculum,
            new_expert_lr_multiplier=args.new_expert_lr_mult,
            contrastive_loss_weight=args.contrastive_weight,
            eval_split_ratio=args.eval_split,
            monitor_gradients=not args.no_grad_monitor,
        )
        train_router(config)
        return
    
    if args.command == "train":
        config = RouterTuningConfig(
            model_dir=args.model_dir,
            output_dir=args.output_dir,
            training_data_dir=args.data_dir,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            use_wandb=args.wandb,
            resume_from=args.resume_from,
            curriculum_enabled=not args.no_curriculum,
            new_expert_lr_multiplier=args.new_expert_lr_mult,
            contrastive_loss_weight=args.contrastive_weight,
            eval_split_ratio=args.eval_split,
            monitor_gradients=not args.no_grad_monitor,
        )
        train_router(config)
    
    elif args.command == "apply":
        apply_router_checkpoint(
            model_dir=args.model_dir,
            checkpoint_dir=args.checkpoint_dir,
            output_dir=args.output_dir,
        )
    
    elif args.command == "analyze":
        analyze_router_weights(
            checkpoint_dir=args.checkpoint_dir,
            output_file=args.output,
        )
    
    elif args.command == "compare":
        compare_checkpoints(
            checkpoint_before=args.before,
            checkpoint_after=args.after,
        )


if __name__ == "__main__":
    main()
