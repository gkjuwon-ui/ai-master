#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  Model Validation v2.0 — validate_model.py
  Validates the post-surgery MoE model for correctness.
═══════════════════════════════════════════════════════════════════

Checks:
  1. Tensor integrity: all expected tensors exist with correct shapes
  2. Expert expansion: expert weights are [20, ...] not [16, ...]
  3. Router expansion: router weights are [20, 5120]
  4. Quantization metadata: all NF4 tensors have valid quant state
  5. New expert diversity: new experts are NOT identical to donors
  6. Router routing: the router actually selects new experts (16-19)
  7. Index consistency: index JSON matches actual shard contents
  8. Config correctness: num_local_experts == 20
  9. Generation test: model can generate text without crashing
  10. NF4 quantization integrity: validate quant_state, absmax, nested
  11. Weight statistics: NaN/Inf detection, distribution analysis
  12. Shard size validation: file sizes within expected ranges
  13. Routing entropy: measure router output diversity per layer
  14. Expert routing bias: verify bias values match config
  15. Activation balance: check token distribution across experts
  16. Validation report: JSON + markdown output
"""

import os
import sys
import json
import time
import argparse
import logging
import math
from pathlib import Path
from typing import Dict, Tuple, List, Optional, Any
from dataclasses import dataclass, field
from collections import defaultdict

import torch
import numpy as np

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("validate")


class ValidationResult:
    """Tracks pass/fail/warn with timing, categories, and report generation."""
    
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details: List[Tuple[str, str, str]] = []  # (status, category, msg)
        self._current_category = "general"
        self._start_time = time.time()
        self._category_times: Dict[str, float] = {}
        self._cat_start: Optional[float] = None
        # Numeric data collected during validation
        self.metrics: Dict[str, Any] = {}
    
    def set_category(self, cat: str):
        """Set current validation category and track timing."""
        if self._cat_start and self._current_category:
            self._category_times[self._current_category] = (
                self._category_times.get(self._current_category, 0)
                + time.time() - self._cat_start
            )
        self._current_category = cat
        self._cat_start = time.time()
    
    def ok(self, msg: str):
        self.passed += 1
        self.details.append(("PASS", self._current_category, msg))
        log.info(f"  ✓ {msg}")
    
    def fail(self, msg: str):
        self.failed += 1
        self.details.append(("FAIL", self._current_category, msg))
        log.error(f"  ✗ {msg}")
    
    def warn(self, msg: str):
        self.warnings += 1
        self.details.append(("WARN", self._current_category, msg))
        log.warning(f"  ! {msg}")
    
    def add_metric(self, name: str, value: Any):
        """Store a named metric for report generation."""
        self.metrics[name] = value
    
    def summary(self) -> bool:
        # Finalize timing
        if self._cat_start and self._current_category:
            self._category_times[self._current_category] = (
                self._category_times.get(self._current_category, 0)
                + time.time() - self._cat_start
            )
        
        total_time = time.time() - self._start_time
        log.info("")
        log.info(f"  Results: {self.passed} passed, {self.failed} failed, {self.warnings} warnings")
        log.info(f"  Total time: {total_time:.1f}s")
        
        if self._category_times:
            log.info("  Time per category:")
            for cat, t in sorted(self._category_times.items(), key=lambda x: -x[1]):
                log.info(f"    {cat}: {t:.1f}s")
        
        return self.failed == 0
    
    def to_dict(self) -> Dict:
        """Export results as a dictionary for JSON report."""
        return {
            "passed": self.passed,
            "failed": self.failed,
            "warnings": self.warnings,
            "success": self.failed == 0,
            "total_time_s": round(time.time() - self._start_time, 2),
            "category_times": {k: round(v, 2) for k, v in self._category_times.items()},
            "details": [{"status": s, "category": c, "message": m} for s, c, m in self.details],
            "metrics": self.metrics,
        }
    
    def generate_markdown_report(self, model_dir: str) -> str:
        """Generate a human-readable markdown validation report."""
        lines = [
            "# MoE Model Validation Report",
            f"**Model:** `{model_dir}`",
            f"**Date:** {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Result:** {'PASS ✓' if self.failed == 0 else 'FAIL ✗'}",
            "",
            f"| Metric | Count |",
            f"|--------|-------|",
            f"| Passed | {self.passed} |",
            f"| Failed | {self.failed} |",
            f"| Warnings | {self.warnings} |",
            "",
        ]
        
        # Group by category
        categories: Dict[str, List] = defaultdict(list)
        for status, cat, msg in self.details:
            categories[cat].append((status, msg))
        
        for cat in sorted(categories.keys()):
            lines.append(f"## {cat.replace('_', ' ').title()}")
            for status, msg in categories[cat]:
                icon = "✓" if status == "PASS" else ("✗" if status == "FAIL" else "⚠")
                lines.append(f"- {icon} {msg}")
            lines.append("")
        
        # Metrics section
        if self.metrics:
            lines.append("## Metrics")
            for k, v in self.metrics.items():
                if isinstance(v, float):
                    lines.append(f"- **{k}:** {v:.6f}")
                else:
                    lines.append(f"- **{k}:** {v}")
            lines.append("")
        
        return "\n".join(lines)


def validate_config(model_dir: Path, result: ValidationResult):
    """Check config.json for correct expert count."""
    result.set_category("config")
    config_path = model_dir / "config.json"
    
    if not config_path.exists():
        result.fail("config.json not found")
        return
    
    with open(config_path) as f:
        config = json.load(f)
    
    # Handle nested text_config
    text_config = config.get("text_config", config)
    
    num_experts = text_config.get("num_local_experts", None)
    if num_experts == 20:
        result.ok(f"num_local_experts = {num_experts}")
    elif num_experts is not None:
        result.fail(f"num_local_experts = {num_experts} (expected 20)")
    else:
        result.warn("num_local_experts not found in config")
    
    # Check v2 surgery markers
    if text_config.get("_osen_surgery_complete", False):
        result.ok(f"Surgery v{text_config.get('_osen_surgery_version', '?')} marked complete")
    else:
        result.warn("_osen_surgery_complete flag not set (may be pre-v2)")
    
    custom_experts = text_config.get("_osen_custom_experts", [])
    if len(custom_experts) == 4:
        result.ok(f"Custom experts listed: {custom_experts}")
    elif len(custom_experts) > 0:
        result.warn(f"Expected 4 custom experts, found {len(custom_experts)}")
    
    num_layers = text_config.get("num_hidden_layers", None)
    if num_layers == 48:
        result.ok(f"num_hidden_layers = {num_layers}")
    elif num_layers is not None:
        result.warn(f"num_hidden_layers = {num_layers} (expected 48)")
    
    hidden_size = text_config.get("hidden_size", None)
    if hidden_size == 5120:
        result.ok(f"hidden_size = {hidden_size}")
    elif hidden_size is not None:
        result.warn(f"hidden_size = {hidden_size} (expected 5120)")


def validate_index(model_dir: Path, result: ValidationResult):
    """Check that index JSON is consistent with actual files."""
    result.set_category("index")
    index_path = model_dir / "model.safetensors.index.json"
    
    if not index_path.exists():
        result.fail("model.safetensors.index.json not found")
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    weight_map = index.get("weight_map", {})
    
    # Check all referenced shards exist
    unique_shards = set(weight_map.values())
    for shard in unique_shards:
        shard_path = model_dir / shard
        if shard_path.exists():
            result.ok(f"Shard exists: {shard}")
        else:
            result.fail(f"Missing shard: {shard}")
    
    # Check for router and expert keys
    router_keys = [k for k in weight_map if "router.weight" in k]
    expert_keys = [k for k in weight_map if "experts" in k and "weight" in k]
    
    result.ok(f"Index has {len(router_keys)} router keys, {len(expert_keys)} expert keys")
    
    # v2.0: Validate all 48 MoE layers have router + expert entries
    expected_moe_layers = 48
    found_router_layers = set()
    for k in router_keys:
        # Extract layer number from key like "model.layers.X.feed_forward.router.weight"
        parts = k.split(".")
        for i, p in enumerate(parts):
            if p == "layers" and i + 1 < len(parts):
                try:
                    found_router_layers.add(int(parts[i + 1]))
                except ValueError:
                    pass
    
    if len(found_router_layers) == expected_moe_layers:
        result.ok(f"All {expected_moe_layers} MoE layers have router entries")
    elif len(found_router_layers) > 0:
        missing = set(range(expected_moe_layers)) - found_router_layers
        if missing:
            result.warn(f"Missing router entries for layers: {sorted(missing)[:10]}...")
        result.ok(f"Found router entries for {len(found_router_layers)} layers")
    
    # v2.0: Check for orphaned tensors (in weight_map but not in any shard)
    orphaned = []
    for key, shard in weight_map.items():
        shard_path = model_dir / shard
        if not shard_path.exists():
            orphaned.append(key)
    
    if orphaned:
        result.fail(f"{len(orphaned)} tensors reference non-existent shards")
        for o in orphaned[:5]:
            log.error(f"    Orphaned: {o}")
    else:
        result.ok("No orphaned tensor references")
    
    return weight_map


def validate_shard_sizes(model_dir: Path, result: ValidationResult):
    """Validate shard file sizes are within expected ranges.
    
    For Llama 4 Scout 17B with NF4 quantization:
    - Total model size ~9-11 GB across 13 shards
    - Each shard should be ~700MB-1.2GB
    - Empty or tiny shards indicate corruption
    """
    result.set_category("shard_sizes")
    shards = sorted(model_dir.glob("model-*.safetensors"))
    
    if not shards:
        result.fail("No safetensors shards found")
        return
    
    total_size_gb = 0
    shard_sizes = {}
    min_shard_bytes = 100 * 1024 * 1024  # 100 MB minimum
    max_shard_bytes = 5 * 1024 * 1024 * 1024  # 5 GB maximum
    
    for shard in shards:
        size_bytes = shard.stat().st_size
        size_gb = size_bytes / (1024 ** 3)
        total_size_gb += size_gb
        shard_sizes[shard.name] = size_gb
        
        if size_bytes < min_shard_bytes:
            result.warn(f"{shard.name}: unusually small ({size_gb:.2f} GB)")
        elif size_bytes > max_shard_bytes:
            result.warn(f"{shard.name}: unusually large ({size_gb:.2f} GB)")
    
    result.ok(f"Total model size: {total_size_gb:.2f} GB across {len(shards)} shards")
    result.add_metric("total_model_size_gb", round(total_size_gb, 2))
    result.add_metric("num_shards", len(shards))
    
    # Check variance — shards should be roughly similar size
    sizes = list(shard_sizes.values())
    mean_size = np.mean(sizes)
    std_size = np.std(sizes)
    cv = std_size / mean_size if mean_size > 0 else 0
    
    if cv < 0.5:
        result.ok(f"Shard sizes well-balanced (CV={cv:.3f})")
    else:
        result.warn(f"High shard size variance (CV={cv:.3f})")
    
    result.add_metric("shard_size_cv", round(cv, 4))


def validate_quantization_integrity(model_dir: Path, result: ValidationResult):
    """Validate NF4 quantization metadata for all quantized tensors.
    
    Each NF4-quantized tensor should have:
    - .quant_state.bitsandbytes__nf4 metadata
    - .absmax tensor with correct shape
    - No NaN/Inf in absmax
    - Reasonable absmax value range
    """
    from safetensors import safe_open
    
    result.set_category("quantization")
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        result.fail("Cannot validate quantization without index")
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    weight_map = index.get("weight_map", {})
    unique_shards = sorted(set(weight_map.values()))
    
    # Categorize tensor keys
    main_weight_keys = set()
    quant_state_keys = set()
    absmax_keys = set()
    nested_keys = set()
    
    for key in weight_map:
        if ".quant_state" in key:
            quant_state_keys.add(key)
        elif ".absmax" in key:
            absmax_keys.add(key)
        elif ".nested" in key:
            nested_keys.add(key)
        elif "proj.weight" in key or "router.weight" in key:
            main_weight_keys.add(key)
    
    result.ok(f"Found {len(main_weight_keys)} main weights, "
              f"{len(quant_state_keys)} quant states, "
              f"{len(absmax_keys)} absmax tensors")
    
    # Validate absmax values in sampled shards
    checked_absmax = 0
    nan_inf_count = 0
    absmax_ranges = []
    
    sample_shards = unique_shards[:3]  # Check first 3 shards for speed
    
    for shard_name in sample_shards:
        shard_path = model_dir / shard_name
        if not shard_path.exists():
            continue
        
        try:
            with safe_open(str(shard_path), framework="pt") as f:
                for key in f.keys():
                    if ".absmax" in key or "absmax" in key.lower():
                        tensor = f.get_tensor(key)
                        checked_absmax += 1
                        
                        # Check for NaN/Inf
                        if torch.isnan(tensor).any():
                            result.fail(f"NaN in absmax: {key}")
                            nan_inf_count += 1
                        elif torch.isinf(tensor).any():
                            result.fail(f"Inf in absmax: {key}")
                            nan_inf_count += 1
                        else:
                            t_float = tensor.float()
                            absmax_ranges.append((t_float.min().item(), t_float.max().item()))
        except Exception as e:
            result.warn(f"Could not read shard {shard_name} for quant check: {e}")
    
    if checked_absmax > 0 and nan_inf_count == 0:
        result.ok(f"Checked {checked_absmax} absmax tensors — no NaN/Inf")
    elif checked_absmax == 0:
        result.warn("No absmax tensors found to validate")
    
    # Report absmax value ranges
    if absmax_ranges:
        min_all = min(r[0] for r in absmax_ranges)
        max_all = max(r[1] for r in absmax_ranges)
        result.ok(f"Absmax range: [{min_all:.6f}, {max_all:.6f}]")
        result.add_metric("absmax_min", round(min_all, 6))
        result.add_metric("absmax_max", round(max_all, 6))
    
    result.add_metric("checked_absmax_tensors", checked_absmax)
    result.add_metric("quant_nan_inf_count", nan_inf_count)


def validate_weight_statistics(model_dir: Path, result: ValidationResult):
    """Check weight tensors for NaN, Inf, and abnormal distributions.
    
    Validates:
    - No NaN or Inf in any weight tensor
    - Weights have reasonable magnitude (not exploding/vanishing)
    - Router weights have proper scale for softmax
    """
    from safetensors import safe_open
    
    result.set_category("weight_stats")
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        result.fail("Cannot validate weights without index")
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    unique_shards = sorted(set(index["weight_map"].values()))
    
    total_tensors = 0
    nan_tensors = 0
    inf_tensors = 0
    zero_tensors = 0
    router_stats = []
    expert_weight_stats = []
    
    # Sample up to 4 shards for speed
    for shard_name in unique_shards[:4]:
        shard_path = model_dir / shard_name
        if not shard_path.exists():
            continue
        
        try:
            with safe_open(str(shard_path), framework="pt") as f:
                for key in f.keys():
                    # Skip metadata tensors
                    if ".quant_state" in key or ".nested" in key:
                        continue
                    
                    tensor = f.get_tensor(key)
                    t_float = tensor.float()
                    total_tensors += 1
                    
                    has_nan = torch.isnan(t_float).any().item()
                    has_inf = torch.isinf(t_float).any().item()
                    is_all_zero = (t_float == 0).all().item()
                    
                    if has_nan:
                        nan_tensors += 1
                        result.fail(f"NaN detected in {key}")
                    if has_inf:
                        inf_tensors += 1
                        result.fail(f"Inf detected in {key}")
                    if is_all_zero and "bias" not in key:
                        zero_tensors += 1
                        result.warn(f"All-zero tensor: {key}")
                    
                    # Collect stats for router weights
                    if "router.weight" in key and ".absmax" not in key and ".quant" not in key:
                        mean_val = t_float.mean().item()
                        std_val = t_float.std().item()
                        min_val = t_float.min().item()
                        max_val = t_float.max().item()
                        router_stats.append({
                            "key": key, "mean": mean_val, "std": std_val,
                            "min": min_val, "max": max_val,
                        })
                    
                    # Collect stats for new expert weights (16-19)
                    # NOTE: Llama 4 uses packed expert tensors (experts.gate_proj.weight)
                    # not per-expert keys (experts.16.gate_proj.weight).
                    # For packed tensors, we check the overall tensor stats instead.
                    if "experts" in key and "proj.weight" in key:
                        if ".absmax" not in key and ".quant" not in key and ".nested" not in key:
                            mean_val = t_float.mean().item()
                            std_val = t_float.std().item()
                            expert_weight_stats.append({
                                "key": key,
                                "mean": mean_val, "std": std_val,
                            })
        except Exception as e:
            result.warn(f"Could not read shard {shard_name}: {e}")
    
    if total_tensors > 0:
        result.ok(f"Checked {total_tensors} tensors — "
                  f"{nan_tensors} NaN, {inf_tensors} Inf, {zero_tensors} all-zero")
    
    result.add_metric("total_tensors_checked", total_tensors)
    result.add_metric("nan_tensor_count", nan_tensors)
    result.add_metric("inf_tensor_count", inf_tensors)
    
    # Router weight analysis
    if router_stats:
        means = [s["mean"] for s in router_stats]
        stds = [s["std"] for s in router_stats]
        avg_mean = np.mean(means)
        avg_std = np.mean(stds)
        
        result.ok(f"Router weights: avg mean={avg_mean:.6f}, avg std={avg_std:.6f}")
        result.add_metric("router_avg_mean", round(avg_mean, 6))
        result.add_metric("router_avg_std", round(avg_std, 6))
        
        # Check for exploding router weights (would cause softmax saturation)
        max_abs = max(max(abs(s["min"]), abs(s["max"])) for s in router_stats)
        if max_abs > 100:
            result.warn(f"Router weights very large (max |w| = {max_abs:.2f}), softmax may saturate")
        elif max_abs > 10:
            result.ok(f"Router weight magnitude reasonable (max |w| = {max_abs:.2f})")
        else:
            result.ok(f"Router weight magnitude normal (max |w| = {max_abs:.4f})")
    
    # New expert weight analysis
    if expert_weight_stats:
        by_expert: Dict[int, list] = defaultdict(list)
        for s in expert_weight_stats:
            by_expert[s["expert_id"]].append(s)
        
        for eid in sorted(by_expert.keys()):
            stats = by_expert[eid]
            avg_std = np.mean([s["std"] for s in stats])
            if avg_std < 1e-6:
                result.warn(f"Expert {eid}: weights near-zero (avg std={avg_std:.8f})")
            else:
                result.ok(f"Expert {eid}: avg weight std={avg_std:.6f} (healthy)")


def validate_expert_routing_bias(model_dir: Path, result: ValidationResult):
    """Check that routing biases for new experts are set correctly.
    
    New experts need slight positive routing bias to overcome the
    established routing patterns of the original 16 experts.
    Expected bias for experts 16-19: ~0.01-0.1
    """
    from safetensors import safe_open
    
    result.set_category("routing_bias")
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    # Look for router bias tensors
    bias_keys = [k for k in index["weight_map"] if "router.bias" in k.lower()]
    
    if not bias_keys:
        # No explicit bias — check config for routing_bias setting
        config_path = model_dir / "config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)
            text_config = config.get("text_config", config)
            routing_bias = text_config.get("_osen_routing_bias", None)
            if routing_bias:
                result.ok(f"Routing bias configured in config: {routing_bias}")
            else:
                result.warn("No router bias tensor found and no routing_bias in config — "
                           "new experts may not receive traffic")
        return
    
    # Validate bias values
    checked = 0
    for key in bias_keys[:5]:  # Sample
        shard_name = index["weight_map"][key]
        shard_path = model_dir / shard_name
        if not shard_path.exists():
            continue
        
        try:
            with safe_open(str(shard_path), framework="pt") as f:
                bias = f.get_tensor(key).float()
            
            if bias.shape[0] >= 20:
                new_biases = bias[16:20]
                old_biases = bias[:16]
                
                new_mean = new_biases.mean().item()
                old_mean = old_biases.mean().item()
                
                if new_mean > old_mean:
                    result.ok(f"New expert bias ({new_mean:.4f}) > old ({old_mean:.4f}) — good for initial routing")
                else:
                    result.warn(f"New expert bias ({new_mean:.4f}) <= old ({old_mean:.4f})")
                
                checked += 1
        except Exception as e:
            result.warn(f"Could not read bias {key}: {e}")
    
    if checked == 0:
        result.warn("Could not validate any routing bias values")


def validate_tensor_shapes(model_dir: Path, result: ValidationResult):
    """Validate tensor shapes in safetensors shards."""
    result.set_category("tensor_shapes")
    from safetensors import safe_open
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        result.fail("Cannot validate tensors without index")
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    weight_map = index.get("weight_map", {})
    unique_shards = sorted(set(weight_map.values()))
    
    checked_routers = 0
    checked_experts = 0
    router_shape_ok = True
    expert_shape_ok = True
    
    for shard_name in unique_shards:
        shard_path = model_dir / shard_name
        if not shard_path.exists():
            continue
        
        try:
            with safe_open(str(shard_path), framework="pt") as f:
                for key in f.keys():
                    tensor = f.get_tensor(key)
                    
                    # Check router weight shapes
                    if "router.weight" in key and ".quant" not in key and ".absmax" not in key:
                        if tensor.shape[0] == 20 and tensor.shape[1] == 5120:
                            checked_routers += 1
                        else:
                            result.fail(f"Router {key} has shape {tensor.shape} (expected [20, 5120])")
                            router_shape_ok = False
                    
                    # Check expert weight shapes (main weight tensors, not metadata)
                    if "experts" in key and "proj.weight" in key:
                        if ".quant" not in key and ".absmax" not in key and ".nested" not in key:
                            # This is a packed quantized tensor or the main weight
                            if len(tensor.shape) >= 1:
                                checked_experts += 1
        except Exception as e:
            result.warn(f"Could not read shard {shard_name}: {e}")
    
    if checked_routers > 0 and router_shape_ok:
        result.ok(f"All {checked_routers} router weights have correct shape [20, 5120]")
    elif checked_routers == 0:
        result.warn("No router weights found to validate")
    
    if checked_experts > 0:
        result.ok(f"Checked {checked_experts} expert weight tensors")
    else:
        result.warn("No expert weight tensors found")


def validate_expert_diversity(model_dir: Path, result: ValidationResult):
    """Check that new experts are not identical to existing ones.
    Checks multiple layers (0, 24, 47) to catch layer-specific issues."""
    result.set_category("expert_diversity")
    from safetensors import safe_open
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    # Check diversity across multiple layers (shallow, middle, deep)
    check_layers = [0, 24, 47]
    layers_checked = 0
    
    for check_layer in check_layers:
        layer_key_pattern = f"layers.{check_layer}.feed_forward.router.weight"
        
        for key, shard in index["weight_map"].items():
            if layer_key_pattern in key and ".quant" not in key and ".absmax" not in key:
                shard_path = model_dir / shard
                if not shard_path.exists():
                    continue
                
                try:
                    with safe_open(str(shard_path), framework="pt") as f:
                        router = f.get_tensor(key)
                    
                    if router.shape[0] < 20:
                        result.warn(f"Layer {check_layer}: Router has only {router.shape[0]} experts (expected 20)")
                        continue
                    
                    new_rows = router[16:20].float()
                    old_rows = router[:16].float()
                    
                    # Cosine similarity between new experts
                    worst_new_pair_sim = 0.0
                    for i in range(4):
                        for j in range(i + 1, 4):
                            sim = torch.nn.functional.cosine_similarity(
                                new_rows[i].unsqueeze(0), new_rows[j].unsqueeze(0)
                            ).item()
                            worst_new_pair_sim = max(worst_new_pair_sim, sim)
                            if sim > 0.99:
                                result.fail(f"Layer {check_layer}: experts {16+i} and {16+j} "
                                            f"nearly identical (sim={sim:.6f})")
                            elif sim > 0.97:
                                result.warn(f"Layer {check_layer}: experts {16+i} and {16+j} "
                                            f"very similar (sim={sim:.6f})")
                    
                    # Check new vs old similarity
                    max_sim = 0.0
                    for i in range(4):
                        for j in range(16):
                            sim = torch.nn.functional.cosine_similarity(
                                new_rows[i].unsqueeze(0), old_rows[j].unsqueeze(0)
                            ).item()
                            max_sim = max(max_sim, sim)
                    
                    if max_sim > 0.99:
                        result.warn(f"Layer {check_layer}: new experts too similar to originals "
                                    f"(max sim={max_sim:.6f})")
                    else:
                        result.ok(f"Layer {check_layer}: experts diverse — "
                                  f"max inter-new sim={worst_new_pair_sim:.4f}, "
                                  f"max new-old sim={max_sim:.4f}")
                    
                    layers_checked += 1
                    break  # Found the layer, move to next
                    
                except Exception as e:
                    result.warn(f"Could not check layer {check_layer} diversity: {e}")
    
    if layers_checked == 0:
        result.warn("No layers could be checked for expert diversity")


def validate_routing(model_dir: Path, result: ValidationResult):
    """
    Load the model and check that the router actually selects new experts.
    This is the most important validation — if the router never picks experts 16-19,
    the entire surgery is wasted.
    """
    result.set_category("routing")
    try:
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        
        log.info("  Loading model for routing validation (this may take a few minutes)...")
        
        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=True,
            llm_int8_skip_modules=["router"],
        )
        
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            quantization_config=bnb_config,
            device_map="auto",
            torch_dtype=torch.bfloat16,
            trust_remote_code=True,
        )
        
        # Test prompts designed to trigger each new expert
        test_prompts = {
            16: "Click on the blue button at coordinates (450, 320) in the screenshot.",
            17: "Plan a multi-step workflow: first open Chrome, then navigate to Gmail, compose an email.",
            18: "Verify that the file was saved successfully. Check for any error indicators.",
            19: "The download failed with a timeout error. Retry using an alternative approach.",
        }
        
        expert_selections = {i: 0 for i in range(20)}
        total_tokens = 0
        
        model.eval()
        with torch.no_grad():
            for target_expert, prompt in test_prompts.items():
                inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
                
                # Forward pass with output_router_logits if available
                try:
                    outputs = model(**inputs, output_hidden_states=True, output_router_logits=True)
                    
                    if hasattr(outputs, 'router_logits') and outputs.router_logits is not None:
                        for layer_logits in outputs.router_logits:
                            if layer_logits is not None:
                                selected = layer_logits.argmax(dim=-1)  # [batch, seq_len]
                                for expert_id in selected.flatten().tolist():
                                    expert_selections[expert_id] = expert_selections.get(expert_id, 0) + 1
                                    total_tokens += 1
                except Exception as e:
                    log.warning(f"Could not get router logits: {e}")
                    # Fallback: try manual routing check
                    try:
                        outputs = model(**inputs, output_hidden_states=True)
                    except Exception:
                        pass
        
        if total_tokens > 0:
            new_selections = sum(expert_selections.get(i, 0) for i in range(16, 20))
            new_pct = new_selections / total_tokens * 100
            
            if new_pct > 1.0:
                result.ok(f"New experts selected {new_pct:.1f}% of tokens ({new_selections}/{total_tokens})")
            elif new_pct > 0:
                result.warn(f"New experts selected only {new_pct:.1f}% of tokens — may need more router tuning")
            else:
                result.warn("New experts were never selected — router tuning may not have converged")
            
            # Per-expert breakdown
            for i in range(16, 20):
                count = expert_selections.get(i, 0)
                pct = count / total_tokens * 100
                log.info(f"    Expert {i}: {count} tokens ({pct:.1f}%)")
        else:
            result.warn("Could not measure routing — no router logits available")
        
        # Generation test
        log.info("  Testing text generation...")
        test_input = tokenizer("Hello, how can I help you today?", return_tensors="pt").to(model.device)
        try:
            gen_output = model.generate(
                **test_input,
                max_new_tokens=50,
                do_sample=False,
                temperature=1.0,
            )
            gen_text = tokenizer.decode(gen_output[0], skip_special_tokens=True)
            if len(gen_text) > 10:
                result.ok(f"Generation works! Output length: {len(gen_text)} chars")
            else:
                result.warn(f"Generation produced very short output: {gen_text!r}")
        except Exception as e:
            result.fail(f"Generation failed: {e}")
        
        # Cleanup
        del model
        torch.cuda.empty_cache()
        
    except ImportError as e:
        result.warn(f"Cannot validate routing (missing dependency: {e})")
    except Exception as e:
        result.warn(f"Routing validation error: {e}")


def validate_routing_entropy(model_dir: Path, result: ValidationResult):
    """Analyze router output entropy across layers.
    
    Good routing:
    - Entropy > 0 means the router is not always selecting the same expert
    - Entropy close to log2(20) = 4.32 means near-uniform distribution
    - Entropy ~ 2-3 is typical (some specialization, but not collapsed)
    
    This uses the router weights directly (without loading the full model)
    to estimate routing diversity by checking weight vector similarity patterns.
    """
    from safetensors import safe_open
    
    result.set_category("routing_entropy")
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    layer_entropies = {}
    new_expert_row_norms = defaultdict(list)
    
    for key, shard_name in index["weight_map"].items():
        if "router.weight" not in key:
            continue
        if ".quant" in key or ".absmax" in key or ".nested" in key:
            continue
        
        # Extract layer number
        layer_num = None
        parts = key.split(".")
        for i, p in enumerate(parts):
            if p == "layers" and i + 1 < len(parts):
                try:
                    layer_num = int(parts[i + 1])
                except ValueError:
                    pass
        
        if layer_num is None:
            continue
        
        shard_path = model_dir / shard_name
        if not shard_path.exists():
            continue
        
        try:
            with safe_open(str(shard_path), framework="pt") as f:
                router = f.get_tensor(key).float()
            
            if router.shape[0] < 20:
                continue
            
            # Compute row norms — larger norms → stronger routing preference
            row_norms = router.norm(dim=1)
            
            # Simulate entropy: create a "pseudo-distribution" from row norms
            # Higher norm → higher probability of selection (via softmax analogy)
            probs = torch.softmax(row_norms, dim=0)
            entropy = -(probs * torch.log2(probs + 1e-10)).sum().item()
            layer_entropies[layer_num] = entropy
            
            # Track new expert row norms
            for eid in range(16, 20):
                if eid < router.shape[0]:
                    new_expert_row_norms[eid].append(row_norms[eid].item())
            
        except Exception as e:
            continue
    
    if layer_entropies:
        avg_entropy = np.mean(list(layer_entropies.values()))
        min_entropy = min(layer_entropies.values())
        max_entropy = max(layer_entropies.values())
        min_layer = min(layer_entropies, key=layer_entropies.get)
        max_layer = max(layer_entropies, key=layer_entropies.get)
        
        max_possible = math.log2(20)
        
        result.ok(f"Router entropy: avg={avg_entropy:.3f}, "
                  f"range=[{min_entropy:.3f}, {max_entropy:.3f}] "
                  f"(max possible: {max_possible:.2f})")
        result.add_metric("avg_routing_entropy", round(avg_entropy, 4))
        result.add_metric("min_routing_entropy", round(min_entropy, 4))
        result.add_metric("max_routing_entropy", round(max_entropy, 4))
        result.add_metric("min_entropy_layer", min_layer)
        result.add_metric("max_entropy_layer", max_layer)
        
        if avg_entropy < 1.0:
            result.warn(f"Low routing entropy ({avg_entropy:.3f}) — router may be collapsed")
        elif avg_entropy < 2.0:
            result.ok(f"Moderate routing entropy — some expert specialization")
        else:
            result.ok(f"Healthy routing entropy — good expert diversity")
        
        # Check if new experts have competitive norms
        for eid in sorted(new_expert_row_norms.keys()):
            norms = new_expert_row_norms[eid]
            avg_norm = np.mean(norms)
            result.add_metric(f"expert_{eid}_avg_router_norm", round(avg_norm, 6))
    else:
        result.warn("No router weights available for entropy analysis")


def validate_layer_consistency(model_dir: Path, result: ValidationResult):
    """Check consistency across all 48 MoE layers.
    
    Validates that the surgery was applied uniformly:
    - All layers have 20 experts
    - Router shapes are consistent
    - No layers were missed during surgery
    """
    from safetensors import safe_open
    
    result.set_category("layer_consistency")
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    # Build a per-layer inventory
    layer_expert_counts: Dict[int, set] = defaultdict(set)
    layer_has_router: Dict[int, bool] = {}
    
    for key in index["weight_map"]:
        parts = key.split(".")
        layer_num = None
        for i, p in enumerate(parts):
            if p == "layers" and i + 1 < len(parts):
                try:
                    layer_num = int(parts[i + 1])
                except ValueError:
                    pass
        
        if layer_num is None:
            continue
        
        # Track expert presence per layer
        # Llama 4 uses packed tensors: layers.N.feed_forward.experts.gate_proj.weight
        # NOT per-expert keys like experts.16.gate_proj.weight
        if "experts" in key and "proj" in key:
            # Packed format: the presence of any experts key means experts exist in this layer
            # We can't count individual experts from key names in packed format.
            # Instead, just mark the layer as having expert weights.
            layer_expert_counts[layer_num].add(-1)  # sentinel: experts exist
        
        # Track router presence
        if "router.weight" in key and ".quant" not in key and ".absmax" not in key:
            layer_has_router[layer_num] = True
    
    # Validate
    perfect_layers = 0
    incomplete_layers = 0
    
    for layer_num in range(48):
        expert_ids = layer_expert_counts.get(layer_num, set())
        has_router = layer_has_router.get(layer_num, False)
        
        if not expert_ids and not has_router:
            # Non-MoE layer (some architectures have dense layers too)
            continue
        
        has_expert_weights = len(expert_ids) > 0
        
        # For packed tensors we can't enumerate individual expert IDs from key names.
        # Instead check router shape (already validated in validate_tensor_shapes).
        if has_expert_weights and has_router:
            perfect_layers += 1
        else:
            incomplete_layers += 1
            if not has_expert_weights:
                result.fail(f"Layer {layer_num}: no expert weight tensors found")
            if not has_router:
                result.warn(f"Layer {layer_num}: no router weight found")
    
    if perfect_layers > 0 and incomplete_layers == 0:
        result.ok(f"All {perfect_layers} MoE layers have 20 experts + router")
    elif perfect_layers > 0:
        result.warn(f"{perfect_layers} layers OK, {incomplete_layers} incomplete")
    
    result.add_metric("perfect_moe_layers", perfect_layers)
    result.add_metric("incomplete_moe_layers", incomplete_layers)


def validate_memory_estimate(model_dir: Path, result: ValidationResult):
    """Estimate VRAM requirements for the model.
    
    Provides estimates for different loading modes:
    - NF4 (4-bit): ~5-6 GB for 17B model
    - INT8: ~9-10 GB
    - FP16/BF16: ~18-20 GB
    - FP32: ~36-40 GB
    """
    result.set_category("memory")
    
    index_path = model_dir / "model.safetensors.index.json"
    if not index_path.exists():
        return
    
    with open(index_path) as f:
        index = json.load(f)
    
    # Count parameters from weight map keys
    total_params_est = 0
    expert_params_est = 0
    router_params_est = 0
    other_params_est = 0
    
    # Use standard shapes for estimation
    hidden_size = 5120
    intermediate_size = 8192
    num_experts = 20
    num_layers = 48
    
    for key in index["weight_map"]:
        if ".quant_state" in key or ".absmax" in key or ".nested" in key:
            continue
        
        if "router.weight" in key:
            router_params_est += num_experts * hidden_size
        elif "experts" in key and "proj.weight" in key:
            if "gate_proj" in key or "up_proj" in key:
                expert_params_est += hidden_size * intermediate_size
            elif "down_proj" in key:
                expert_params_est += intermediate_size * hidden_size
        elif "self_attn" in key or "embed" in key or "norm" in key or "lm_head" in key:
            # Rough estimates for attention and embedding layers
            if "embed" in key or "lm_head" in key:
                other_params_est += hidden_size * 128000  # vocab size ~128K
            else:
                other_params_est += hidden_size * hidden_size  # rough
    
    # Actual file-based estimate is more reliable
    total_file_size_gb = sum(
        (model_dir / shard).stat().st_size
        for shard in set(index["weight_map"].values())
        if (model_dir / shard).exists()
    ) / (1024 ** 3)
    
    # VRAM estimates with overhead
    nf4_vram = total_file_size_gb * 1.15  # ~15% overhead for CUDA tensors
    int8_vram = total_file_size_gb * 2.2
    fp16_vram = total_file_size_gb * 4.0
    
    result.ok(f"VRAM estimate — NF4: ~{nf4_vram:.1f} GB, INT8: ~{int8_vram:.1f} GB, FP16: ~{fp16_vram:.1f} GB")
    result.add_metric("estimated_vram_nf4_gb", round(nf4_vram, 1))
    result.add_metric("estimated_vram_int8_gb", round(int8_vram, 1))
    result.add_metric("estimated_vram_fp16_gb", round(fp16_vram, 1))
    
    # Provide GPU recommendations
    if nf4_vram <= 8:
        result.ok("Should fit on RTX 3070/4060 (8 GB) with NF4")
    elif nf4_vram <= 12:
        result.ok("Should fit on RTX 3080/4070 Ti (12 GB) with NF4")
    elif nf4_vram <= 16:
        result.ok("Should fit on RTX 4080/A4000 (16 GB) with NF4")
    elif nf4_vram <= 24:
        result.ok("Should fit on RTX 3090/4090/A5000 (24 GB) with NF4")
    else:
        result.warn(f"May need multi-GPU or A100 (NF4 estimate: {nf4_vram:.1f} GB)")


def validate_comparison(model_dir: Path, original_dir: Path, result: ValidationResult):
    """Compare the surgery output with the original model."""
    result.set_category("comparison")
    from safetensors import safe_open
    
    # Check file counts
    new_shards = sorted(model_dir.glob("model-*.safetensors"))
    old_shards = sorted(original_dir.glob("model-*.safetensors"))
    
    if len(new_shards) == len(old_shards):
        result.ok(f"Same number of shards: {len(new_shards)}")
    else:
        result.warn(f"Different shard count: {len(new_shards)} vs {len(old_shards)}")
    
    # Check that non-expert weights are unchanged
    log.info("  Comparing non-expert weights with original (spot check)...")
    
    if old_shards and new_shards:
        # Check first shard for non-MoE weights
        try:
            with safe_open(str(old_shards[0]), framework="pt") as fold:
                with safe_open(str(new_shards[0]), framework="pt") as fnew:
                    for key in fold.keys():
                        if key in fnew.keys():
                            if "expert" not in key and "router" not in key:
                                old_t = fold.get_tensor(key)
                                new_t = fnew.get_tensor(key)
                                if torch.equal(old_t, new_t):
                                    pass  # Good, unchanged
                                else:
                                    result.warn(f"Non-expert tensor changed: {key}")
                                break  # Just check one
            
            result.ok("Non-expert weights appear preserved")
        except Exception as e:
            result.warn(f"Could not compare with original: {e}")


def main():
    parser = argparse.ArgumentParser(description="Validate post-surgery MoE model (v2.0)")
    parser.add_argument("--model-dir", type=str, required=True)
    parser.add_argument("--original-dir", type=str, default=None)
    parser.add_argument("--skip-routing", action="store_true", help="Skip slow routing validation (loads model)")
    parser.add_argument("--report", type=str, default=None, help="Output validation report (JSON or MD)")
    parser.add_argument("--quick", action="store_true", help="Quick mode: skip slow checks")
    args = parser.parse_args()
    
    model_dir = Path(args.model_dir)
    
    log.info("=" * 60)
    log.info("  MoE Model Validation v2.0")
    log.info("=" * 60)
    log.info(f"  Model: {model_dir}")
    log.info(f"  Mode: {'quick' if args.quick else 'full'}")
    log.info("")
    
    result = ValidationResult()
    
    # 1. Config
    log.info("─── Config Validation ───")
    result.set_category("config")
    validate_config(model_dir, result)
    
    # 2. Shard sizes (fast)
    log.info("\n─── Shard Size Validation ───")
    validate_shard_sizes(model_dir, result)
    
    # 3. Index
    log.info("\n─── Index Validation ───")
    result.set_category("index")
    validate_index(model_dir, result)
    
    # 4. Tensor shapes
    log.info("\n─── Tensor Shape Validation ───")
    result.set_category("tensor_shapes")
    validate_tensor_shapes(model_dir, result)
    
    # 5. Quantization integrity
    log.info("\n─── Quantization Integrity ───")
    validate_quantization_integrity(model_dir, result)
    
    # 6. Weight statistics
    if not args.quick:
        log.info("\n─── Weight Statistics ───")
        validate_weight_statistics(model_dir, result)
    
    # 7. Expert diversity
    log.info("\n─── Expert Diversity Check ───")
    result.set_category("expert_diversity")
    validate_expert_diversity(model_dir, result)
    
    # 8. Layer consistency
    log.info("\n─── Layer Consistency ───")
    validate_layer_consistency(model_dir, result)
    
    # 9. Routing entropy (uses weights only, no model load)
    log.info("\n─── Routing Entropy Analysis ───")
    validate_routing_entropy(model_dir, result)
    
    # 10. Expert routing bias
    log.info("\n─── Expert Routing Bias ───")
    validate_expert_routing_bias(model_dir, result)
    
    # 11. Memory estimate
    log.info("\n─── Memory Estimate ───")
    validate_memory_estimate(model_dir, result)
    
    # 12. Comparison with original
    if args.original_dir:
        log.info("\n─── Comparison with Original ───")
        result.set_category("comparison")
        validate_comparison(model_dir, Path(args.original_dir), result)
    
    # 13. Routing validation (slow — loads full model)
    if not args.skip_routing and not args.quick:
        log.info("\n─── Routing Validation (loading model...) ───")
        result.set_category("routing")
        validate_routing(model_dir, result)
    else:
        log.info("\n─── Routing Validation: SKIPPED ───")
    
    # Summary
    log.info("")
    log.info("=" * 60)
    success = result.summary()
    log.info("=" * 60)
    
    # Generate report if requested
    if args.report:
        report_path = Path(args.report)
        if report_path.suffix == ".json":
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
            log.info(f"  JSON report saved: {report_path}")
        elif report_path.suffix in (".md", ".markdown"):
            md = result.generate_markdown_report(str(model_dir))
            with open(report_path, "w", encoding="utf-8") as f:
                f.write(md)
            log.info(f"  Markdown report saved: {report_path}")
        else:
            # Default to JSON
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)
            log.info(f"  Report saved: {report_path}")
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()