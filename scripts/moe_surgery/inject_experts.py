#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════
  MoE Expert Injection — inject_experts.py  (v3.0 — Semantic Donor Alignment)
  Adds 4 NEW experts (16→20) to every MoE layer of Llama 4 Scout
═══════════════════════════════════════════════════════════════════

Architecture (Llama 4 Scout 17B-16E, NF4 quantized via bitsandbytes):
  • 48 MoE layers (all layers are MoE), each with:
      – experts.{gate,up,down}_proj.weight  (NF4-packed uint8 + 5 metadata tensors)
      – router.weight                       (bfloat16, [16, 5120] — NOT quantized)
      – shared_expert.{gate,up,down}_proj   (NF4, separate from MoE experts)
  • hidden_size    = 5120
  • intermediate   = 8192  (per expert)
  • top-k routing  = 1

NF4 tensor structure per projection (6 tensors):
  .weight                                  — packed uint8 (2 x 4-bit values per byte)
  .weight.absmax                           — nested-quantized absmax (uint8)
  .weight.nested_absmax                    — float32 absmax of the absmax blocks
  .weight.nested_quant_map                 — float32[256] mapping table for nested quant
  .weight.quant_map                        — float32[16] NF4 quantization table
  .weight.quant_state.bitsandbytes__nf4    — uint8 JSON metadata (shape, dtype, blocksize)

What this script does:
  1. Loads each safetensors shard sequentially (memory efficient)
  2. For each of the 48 MoE layers:
     a) Dequantizes the NF4-packed expert weight tensors → bfloat16 using bitsandbytes
        (falls back to manual NF4 reimplementation if bnb unavailable)
     b) Creates 4 new experts via ORTHOGONAL DONOR BLENDING (V3 semantic donors):
        - expert_16 (visual_grounding):     blend of experts  1,0,14,12 (see→plan→target→remember)
        - expert_17 (workflow_orchestrator): blend of experts  13,0,15,5 (plan→act→app→data)
        - expert_18 (verification_oracle):  blend of experts  1,2,7,12  (see→error→validate→compare)
        - expert_19 (adaptive_retry):       blend of experts  2,7,3,15  (error→safe→navigate→workaround)
        Each new expert = weighted_mean(donors) + orthogonalized perturbation + noise
     c) Expands router gate from [16, 5120] → [20, 5120] (bfloat16, no quantization needed)
        New router rows initialized via PCA-informed blend + specialty bias
  3. Re-quantizes expert weights to NF4 with bitsandbytes (or manual fallback)
  4. Saves as new safetensors shards with IDENTICAL tensor naming convention
  5. Updates model.safetensors.index.json with new tensor entries

Requirements: RunPod A100 80GB (or any system with ≥ 80GB VRAM or 160GB RAM for CPU)
Runtime: ~1-3 hours depending on hardware
"""

import os
import gc
import sys
import json
import copy
import math
import struct
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any
from collections import defaultdict

import torch
import numpy as np
from tqdm import tqdm

# ═══════════════════════════════════════════════════════════════
# BITSANDBYTES INTEGRATION (preferred path for NF4)
# ═══════════════════════════════════════════════════════════════

try:
    import bitsandbytes as bnb
    from bitsandbytes.functional import dequantize_4bit, quantize_4bit
    import bitsandbytes.functional as bnb_F
    HAS_BNB = True
except ImportError:
    HAS_BNB = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("moe_surgery")

# ═══════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════

ORIGINAL_NUM_EXPERTS = 16
NEW_NUM_EXPERTS = 20
NUM_NEW_EXPERTS = 4
NUM_LAYERS = 48
HIDDEN_SIZE = 5120
INTERMEDIATE_SIZE = 8192

EXPERT_SHAPES = {
    "gate_proj": (ORIGINAL_NUM_EXPERTS, INTERMEDIATE_SIZE, HIDDEN_SIZE),
    "up_proj":   (ORIGINAL_NUM_EXPERTS, INTERMEDIATE_SIZE, HIDDEN_SIZE),
    "down_proj": (ORIGINAL_NUM_EXPERTS, HIDDEN_SIZE, INTERMEDIATE_SIZE),
}

EXPANDED_SHAPES = {
    "gate_proj": (NEW_NUM_EXPERTS, INTERMEDIATE_SIZE, HIDDEN_SIZE),
    "up_proj":   (NEW_NUM_EXPERTS, INTERMEDIATE_SIZE, HIDDEN_SIZE),
    "down_proj": (NEW_NUM_EXPERTS, HIDDEN_SIZE, INTERMEDIATE_SIZE),
}

# V3: Semantic donor alignment — donors chosen by functional relevance, not stride-4 pattern
# Each new expert blends from the base experts most semantically related to its domain.
# See osen_expert_config.json V3 for detailed rationale per donor.
DONOR_MAP = {
    16: {
        "name": "visual_grounding",
        # screen_understanding(1) + action_planner(0) + input_method(14) + memory_context(12)
        # Visual grounding = seeing the screen + knowing what to click + coordinate precision + spatial memory
        "donors": [1, 0, 14, 12],
        "blend_weights": [0.35, 0.25, 0.25, 0.15],
        "routing_bias": 0.15,
    },
    17: {
        "name": "workflow_orchestrator",
        # planning_strategy(13) + action_planner(0) + app_specific(15) + file_system(5)
        # Workflow orchestration = task planning + action sequencing + app knowledge + data transfer
        "donors": [13, 0, 15, 5],
        "blend_weights": [0.30, 0.25, 0.25, 0.20],
        "routing_bias": 0.12,
    },
    18: {
        "name": "verification_oracle",
        # screen_understanding(1) + error_recovery(2) + safety_ethics(7) + memory_context(12)
        # Verification = seeing current state + detecting errors + validation logic + before/after comparison
        "donors": [1, 2, 7, 12],
        "blend_weights": [0.30, 0.30, 0.20, 0.20],
        "routing_bias": 0.13,
    },
    19: {
        "name": "adaptive_retry",
        # error_recovery(2) + safety_ethics(7) + web_navigation(3) + app_specific(15)
        # Adaptive retry = error diagnosis + safe fallbacks + adaptive navigation + app-specific workarounds
        "donors": [2, 7, 3, 15],
        "blend_weights": [0.30, 0.25, 0.25, 0.20],
        "routing_bias": 0.10,
    },
}

# V3: Tuned SVD parameters — higher rank for better expressiveness, 
# adjusted rotation angles to maximize inter-expert diversity while preserving donor knowledge
EXPERT_SPECIALIZATION = {
    16: {
        "svd_rotation_deg": 28.0,      # V3: Slightly reduced from 30 — visual grounding needs more donor fidelity
        "sv_modulation_strength": 0.25,
        "sv_modulation_phase": 0.0,
        "rank_pert_magnitude": 0.20,    # V3: Bumped from 0.18 for stronger specialization
        "rank_r": 48,                   # V3: Increased from 32 for richer perturbation subspace
    },
    17: {
        "svd_rotation_deg": 25.0,
        "sv_modulation_strength": 0.22,  # V3: Slight increase for better workflow separation
        "sv_modulation_phase": math.pi / 4,
        "rank_pert_magnitude": 0.18,    # V3: Bumped from 0.15
        "rank_r": 48,                   # V3: Increased from 32
    },
    18: {
        "svd_rotation_deg": 32.0,      # V3: Reduced from 35 — too much rotation was degrading verification accuracy
        "sv_modulation_strength": 0.28,  # V3: Slight reduction from 0.30 for stability
        "sv_modulation_phase": math.pi / 2,
        "rank_pert_magnitude": 0.22,    # V3: Bumped from 0.20
        "rank_r": 48,                   # V3: Increased from 32
    },
    19: {
        "svd_rotation_deg": 24.0,      # V3: Bumped from 22 — retry needs more differentiation from error_recovery donor
        "sv_modulation_strength": 0.24,  # V3: Bumped from 0.22
        "sv_modulation_phase": 3 * math.pi / 4,
        "rank_pert_magnitude": 0.19,    # V3: Bumped from 0.16
        "rank_r": 48,                   # V3: Increased from 32
    },
}

NF4_QUANT_TABLE = torch.tensor([
    -1.0, -0.6961928009986877, -0.5250730514526367, -0.39491748809814453,
    -0.28444138169288635, -0.18477343022823334, -0.09105003625154495, 0.0,
    0.07958029955625534, 0.16093020141124725, 0.24611230194568634, 0.33791524171829224,
    0.44070982933044434, 0.5626170039176941, 0.7229568362236023, 1.0,
], dtype=torch.float32)


def load_safetensors_shard(filepath: str) -> Dict[str, torch.Tensor]:
    from safetensors.torch import load_file
    return load_file(filepath)


def save_safetensors_shard(tensors: Dict[str, torch.Tensor], filepath: str, metadata: dict = None):
    from safetensors.torch import save_file
    save_file(tensors, filepath, metadata=metadata)


class NF4Handler:
    def __init__(self, device: str = "cpu"):
        self.device = device
        self.use_bnb = HAS_BNB and device != "cpu"
        if self.use_bnb:
            log.info("NF4Handler: Using bitsandbytes native quantization (GPU)")
        else:
            log.info("NF4Handler: Using manual NF4 implementation")

    def dequantize(self, weight_packed, absmax, quant_map, quant_state_bytes,
                   nested_absmax=None, nested_quant_map=None, target_shape=None, blocksize=64):
        if self.use_bnb:
            return self._dequantize_bnb(weight_packed, absmax, quant_map, quant_state_bytes,
                                        nested_absmax, nested_quant_map, target_shape, blocksize)
        else:
            return self._dequantize_manual(weight_packed, absmax, quant_map, quant_state_bytes,
                                           nested_absmax, nested_quant_map, target_shape, blocksize)

    def quantize(self, tensor, blocksize=64, double_quant=True):
        if self.use_bnb:
            return self._quantize_bnb(tensor, blocksize, double_quant)
        else:
            return self._quantize_manual(tensor, blocksize, double_quant)

    def _dequantize_bnb(self, weight_packed, absmax, quant_map, quant_state_bytes,
                         nested_absmax, nested_quant_map, target_shape, blocksize):
        quant_state = bnb.functional.QuantState(
            absmax=absmax.to(self.device), shape=target_shape, blocksize=blocksize,
            code=quant_map.to(self.device) if quant_map is not None else NF4_QUANT_TABLE.to(self.device),
            quant_type="nf4", dtype=torch.bfloat16, nested=nested_absmax is not None,
        )
        if nested_absmax is not None:
            quant_state.state2 = bnb.functional.QuantState(
                absmax=nested_absmax.to(self.device), blocksize=64,
                code=nested_quant_map.to(self.device) if nested_quant_map is not None else None,
                quant_type="nf4", dtype=torch.float32,
            )
            quant_state.offset = torch.zeros(1, device=self.device)
        result = dequantize_4bit(weight_packed.to(self.device), quant_state, quant_type="nf4")
        if target_shape is not None:
            result = result.reshape(target_shape)
        return result.to(torch.bfloat16).cpu()

    def _quantize_bnb(self, tensor, blocksize=64, double_quant=True):
        original_shape = tensor.shape
        original_dtype = tensor.dtype
        flat = tensor.to(self.device).float().contiguous()
        if len(flat.shape) > 1:
            flat = flat.reshape(-1)
        packed, quant_state = quantize_4bit(flat, blocksize=blocksize, quant_type="nf4",
                                             compress_statistics=double_quant)
        result = {
            "_packed": packed.cpu(),
            "_quant_map": quant_state.code.cpu() if quant_state.code is not None else NF4_QUANT_TABLE,
        }
        if double_quant and quant_state.state2 is not None:
            result["_absmax"] = quant_state.absmax.cpu()
            result["_nested_absmax"] = quant_state.state2.absmax.cpu().float()
            result["_nested_quant_map"] = (
                quant_state.state2.code.cpu().float()
                if quant_state.state2.code is not None
                else torch.linspace(-1.0, 1.0, 256)
            )
        else:
            result["_absmax"] = quant_state.absmax.cpu().float()
            result["_nested_absmax"] = torch.zeros(1)
            result["_nested_quant_map"] = torch.linspace(-1.0, 1.0, 256)
        shape_str = json.dumps({
            "shape": list(original_shape),
            "dtype": str(original_dtype).replace("torch.", ""),
            "blocksize": blocksize, "quant_type": "nf4", "double_quant": double_quant,
            "nested_blocksize": 64 if double_quant else 0,
            "nested_offset": float(quant_state.offset.item()) if hasattr(quant_state, 'offset') and quant_state.offset is not None else 0.0,
        })
        result["_quant_state"] = torch.frombuffer(bytearray(shape_str.encode("utf-8")), dtype=torch.uint8).clone()
        return result

    def _dequantize_manual(self, weight_packed, absmax, quant_map, quant_state_bytes,
                            nested_absmax, nested_quant_map, target_shape, blocksize):
        packed = weight_packed.to(torch.uint8).flatten()
        n_values = packed.numel() * 2
        indices_low = (packed & 0x0F).to(torch.long)
        indices_high = ((packed >> 4) & 0x0F).to(torch.long)
        indices = torch.empty(n_values, dtype=torch.long)
        indices[0::2] = indices_low
        indices[1::2] = indices_high
        table = quant_map if (quant_map is not None and quant_map.numel() == 16) else NF4_QUANT_TABLE
        mapped = table[indices]
        if nested_absmax is not None and nested_quant_map is not None:
            absmax_unpacked = absmax.to(torch.uint8).flatten()
            n_abs = absmax_unpacked.numel() * 2
            abs_idx_low = (absmax_unpacked & 0x0F).to(torch.long)
            abs_idx_high = ((absmax_unpacked >> 4) & 0x0F).to(torch.long)
            abs_indices = torch.empty(n_abs, dtype=torch.long)
            abs_indices[0::2] = abs_idx_low
            abs_indices[1::2] = abs_idx_high
            if nested_quant_map.numel() == 256:
                abs_mapped = nested_quant_map[abs_indices[:n_abs]]
            else:
                abs_mapped = nested_quant_map[abs_indices]
            nested_bs = 64
            n_nested = abs_mapped.numel() // nested_bs
            abs_mapped = abs_mapped[:n_nested * nested_bs].reshape(n_nested, nested_bs)
            real_absmax = (abs_mapped * nested_absmax[:n_nested].unsqueeze(1)).reshape(-1)
        else:
            real_absmax = absmax.float()
        if target_shape is not None:
            total_elements = 1
            for s in target_shape:
                total_elements *= s
            mapped = mapped[:total_elements]
        else:
            total_elements = mapped.numel()
        n_blocks = (total_elements + blocksize - 1) // blocksize
        real_absmax = real_absmax[:n_blocks]
        padded_len = n_blocks * blocksize
        if mapped.numel() < padded_len:
            mapped = torch.nn.functional.pad(mapped, (0, padded_len - mapped.numel()))
        mapped = mapped[:padded_len].reshape(n_blocks, blocksize)
        scaled = mapped * real_absmax.unsqueeze(1)
        result = scaled.reshape(-1)[:total_elements]
        if target_shape is not None:
            result = result.reshape(target_shape)
        return result.to(torch.bfloat16)

    def _quantize_manual(self, tensor, blocksize=64, double_quant=True):
        original_shape = tensor.shape
        original_dtype = tensor.dtype
        flat = tensor.float().flatten()
        n = flat.numel()
        padded_n = ((n + blocksize - 1) // blocksize) * blocksize
        if padded_n > n:
            flat = torch.nn.functional.pad(flat, (0, padded_n - n))
        blocks = flat.reshape(-1, blocksize)
        n_blocks = blocks.shape[0]
        absmax = blocks.abs().max(dim=1).values.clamp(min=1e-12)
        normalized = blocks / absmax.unsqueeze(1)
        quant_table = NF4_QUANT_TABLE
        flat_norm = normalized.reshape(-1).unsqueeze(1)
        distances = (flat_norm - quant_table.unsqueeze(0)).abs()
        indices = distances.argmin(dim=1).to(torch.uint8)
        indices_pairs = indices.reshape(-1, 2)
        packed = (indices_pairs[:, 1] << 4) | indices_pairs[:, 0]
        result = {"_packed": packed.to(torch.uint8), "_quant_map": quant_table}
        if double_quant:
            nested_bs = 64
            abs_n = absmax.numel()
            abs_padded = ((abs_n + nested_bs - 1) // nested_bs) * nested_bs
            abs_flat = absmax.clone()
            if abs_padded > abs_n:
                abs_flat = torch.nn.functional.pad(abs_flat, (0, abs_padded - abs_n))
            abs_blocks = abs_flat.reshape(-1, nested_bs)
            nested_absmax = abs_blocks.abs().max(dim=1).values.clamp(min=1e-12)
            abs_normalized = abs_blocks / nested_absmax.unsqueeze(1)
            nested_quant_map = torch.linspace(-1.0, 1.0, 256)
            abs_flat_norm = abs_normalized.reshape(-1).unsqueeze(1)
            abs_distances = (abs_flat_norm - nested_quant_map.unsqueeze(0)).abs()
            abs_indices = abs_distances.argmin(dim=1).to(torch.uint8)
            abs_packed = abs_indices.reshape(-1, 2)
            nested_packed = (abs_packed[:, 1] << 4) | abs_packed[:, 0]
            result["_nested_absmax"] = nested_absmax.to(torch.float32)
            result["_nested_quant_map"] = nested_quant_map.to(torch.float32)
            result["_absmax"] = nested_packed.to(torch.uint8)
        else:
            result["_absmax"] = absmax.to(torch.float32)
            result["_nested_absmax"] = torch.zeros(1, dtype=torch.float32)
            result["_nested_quant_map"] = torch.linspace(-1.0, 1.0, 256)
        shape_str = json.dumps({
            "shape": list(original_shape),
            "dtype": str(original_dtype).replace("torch.", ""),
            "blocksize": blocksize, "quant_type": "nf4", "double_quant": double_quant,
            "nested_blocksize": 64 if double_quant else 0,
        })
        result["_quant_state"] = torch.frombuffer(bytearray(shape_str.encode("utf-8")), dtype=torch.uint8).clone()
        return result


def create_all_new_expert_weights(existing_weights, layer_idx):
    """Create 4 new expert weight matrices with STRUCTURAL DIFFERENTIATION."""
    depth_factor = 1.0 - 0.4 * (layer_idx / max(NUM_LAYERS - 1, 1))
    new_weights = []
    blended_bases = []
    deltas = []

    for new_id in range(ORIGINAL_NUM_EXPERTS, NEW_NUM_EXPERTS):
        donor_info = DONOR_MAP[new_id]
        spec = EXPERT_SPECIALIZATION[new_id]
        donors = donor_info["donors"]
        blend_w = torch.tensor(donor_info["blend_weights"], dtype=torch.float32)
        donor_mats = torch.stack([existing_weights[d].float() for d in donors])
        blended = torch.einsum("i, ijk -> jk", blend_w, donor_mats)
        blended_norm = blended.norm()
        blended_bases.append(blended)

        try:
            U, S, Vh = torch.linalg.svd(blended, full_matrices=False)
            k = min(64, S.numel())
            angle_rad = math.radians(spec["svd_rotation_deg"] * depth_factor)
            cos_a = math.cos(angle_rad)
            sin_a = math.sin(angle_rad)
            U_rot = U.clone()
            for j in range(0, k - 1, 2):
                u_j = U_rot[:, j].clone()
                u_j1 = U_rot[:, j + 1].clone()
                U_rot[:, j] = cos_a * u_j - sin_a * u_j1
                U_rot[:, j + 1] = sin_a * u_j + cos_a * u_j1
            S_mod = S.clone()
            mod_strength = spec["sv_modulation_strength"] * depth_factor
            phase = spec["sv_modulation_phase"]
            for j in range(k):
                modulation = 1.0 + mod_strength * math.sin(2 * math.pi * j / k + phase)
                S_mod[j] = S[j] * max(modulation, 0.3)
            rotated = U_rot @ (S_mod.unsqueeze(1) * Vh)
        except Exception:
            rotated = blended.clone()
            log.warning(f"    SVD failed for expert {new_id} layer {layer_idx}, using unrotated blend")

        rank_r = spec["rank_r"]
        gen = torch.Generator()
        gen.manual_seed(new_id * 10000 + layer_idx * 100 + 7)
        A = torch.randn(blended.shape[0], rank_r, generator=gen)
        B = torch.randn(rank_r, blended.shape[1], generator=gen)
        rank_pert = A @ B
        target_pert_norm = blended_norm * spec["rank_pert_magnitude"] * depth_factor
        rank_pert = rank_pert * (target_pert_norm / (rank_pert.norm() + 1e-8))
        result = rotated + rank_pert
        delta = result - blended
        deltas.append(delta)
        new_weights.append(result)

    ortho_deltas = []
    for i, delta in enumerate(deltas):
        d = delta.clone().flatten()
        for prev_d in ortho_deltas:
            proj = (d @ prev_d) / (prev_d @ prev_d + 1e-12)
            d = d - proj * prev_d
        original_norm = deltas[i].norm()
        d_norm = d.norm()
        if d_norm > 1e-8:
            d = d * (original_norm / d_norm)
        ortho_deltas.append(d)
        new_weights[i] = (blended_bases[i] + d.reshape(blended_bases[i].shape)).to(existing_weights.dtype)

    for i in range(len(new_weights)):
        new_id = ORIGINAL_NUM_EXPERTS + i
        delta_norm = deltas[i].norm().item()
        blend_norm = blended_bases[i].norm().item()
        pct = delta_norm / (blend_norm + 1e-8) * 100
        log.info(f"      Expert {new_id} ({DONOR_MAP[new_id]['name']}): "
                 f"delta/blend = {pct:.1f}%, "
                 f"rotation = {EXPERT_SPECIALIZATION[new_id]['svd_rotation_deg'] * depth_factor:.1f}deg")

    return new_weights


def expand_router_weight(router_weight, layer_idx):
    """Expand router gate from [16, 5120] -> [20, 5120]."""
    assert router_weight.shape == (ORIGINAL_NUM_EXPERTS, HIDDEN_SIZE), \
        f"Expected router [{ORIGINAL_NUM_EXPERTS}, {HIDDEN_SIZE}], got {router_weight.shape}"
    router_float = router_weight.float()
    mean_row = router_float.mean(dim=0, keepdim=True)
    centered = router_float - mean_row
    try:
        U, S, Vh = torch.linalg.svd(centered, full_matrices=False)
        pca_dirs = Vh[:4]
    except Exception:
        pca_dirs = torch.randn(4, HIDDEN_SIZE)
        pca_dirs = pca_dirs / pca_dirs.norm(dim=1, keepdim=True)

    new_rows = []
    for idx, new_id in enumerate(range(ORIGINAL_NUM_EXPERTS, NEW_NUM_EXPERTS)):
        donor_info = DONOR_MAP[new_id]
        donors = donor_info["donors"]
        blend_w = torch.tensor(donor_info["blend_weights"], dtype=torch.float32)
        routing_bias = donor_info["routing_bias"]
        donor_rows = torch.stack([router_float[d] for d in donors])
        blended_row = torch.einsum("i, ij -> j", blend_w, donor_rows)
        mean_magnitude = router_float.abs().mean()
        pca_bias = pca_dirs[idx] * mean_magnitude * routing_bias * 2.0
        jitter_scale = 0.02 * (1.0 - layer_idx / NUM_LAYERS)
        jitter = torch.randn(HIDDEN_SIZE) * mean_magnitude * jitter_scale
        new_row = blended_row + pca_bias + jitter
        new_rows.append(new_row.to(router_weight.dtype))

    expanded = torch.cat([router_weight, torch.stack(new_rows)], dim=0)
    assert expanded.shape == (NEW_NUM_EXPERTS, HIDDEN_SIZE), \
        f"Router expansion failed: {expanded.shape}"
    return expanded


def get_layer_shard_mapping(index_path: str) -> Dict[int, str]:
    """Build mapping: layer_index -> shard_filename."""
    with open(index_path) as f:
        index = json.load(f)
    mapping = {}
    for key, shard in index["weight_map"].items():
        if ".feed_forward.router.weight" in key:
            if any(sub in key for sub in [".absmax", ".quant", ".nested"]):
                continue
            parts = key.split(".")
            for i, p in enumerate(parts):
                if p == "layers":
                    layer_idx = int(parts[i + 1])
                    mapping[layer_idx] = shard
                    break
    return mapping


def get_shard_layers(index_path: str) -> Dict[str, List[int]]:
    """Reverse mapping: shard_filename -> list of layer indices."""
    layer_map = get_layer_shard_mapping(index_path)
    shard_layers = defaultdict(list)
    for layer_idx, shard in sorted(layer_map.items()):
        shard_layers[shard].append(layer_idx)
    return dict(shard_layers)


def identify_expert_tensors(tensor_keys, layer_idx):
    """Identify all expert-related tensors for a specific layer in a shard."""
    prefix = f"language_model.model.layers.{layer_idx}.feed_forward.experts."
    proj_types = ["gate_proj", "up_proj", "down_proj"]
    result = {}
    for proj in proj_types:
        base = f"{prefix}{proj}.weight"
        if base in tensor_keys:
            result[proj] = {
                "main": base,
                "absmax": f"{base}.absmax",
                "nested_absmax": f"{base}.nested_absmax",
                "nested_quant_map": f"{base}.nested_quant_map",
                "quant_map": f"{base}.quant_map",
                "quant_state": f"{base}.quant_state.bitsandbytes__nf4",
            }
    router_key = f"language_model.model.layers.{layer_idx}.feed_forward.router.weight"
    if router_key in tensor_keys:
        result["router"] = {"main": router_key}
    return result


def parse_quant_state(tensor):
    """Parse the quant_state metadata JSON from a uint8 tensor."""
    try:
        raw_bytes = bytes(tensor.to(torch.uint8).numpy())
        return json.loads(raw_bytes.decode("utf-8"))
    except Exception:
        return {}


def process_shard(shard_path, output_path, layer_indices, nf4_handler, dry_run=False):
    """Process one safetensors shard: dequant -> expand -> requant."""
    log.info(f"Loading shard: {shard_path}")
    tensors = load_safetensors_shard(shard_path)
    tensor_keys = list(tensors.keys())
    new_index_entries = {}
    shard_filename = os.path.basename(output_path)

    for layer_idx in layer_indices:
        log.info(f"  --- Layer {layer_idx} ---")
        expert_tensors = identify_expert_tensors(tensor_keys, layer_idx)
        if not expert_tensors:
            log.warning(f"  No expert tensors found for layer {layer_idx}")
            continue

        for proj_type in ["gate_proj", "up_proj", "down_proj"]:
            if proj_type not in expert_tensors:
                log.warning(f"    Missing {proj_type} for layer {layer_idx}")
                continue
            keys = expert_tensors[proj_type]
            log.info(f"    {proj_type}: dequantize -> create 4 experts -> requantize")
            main_tensor = tensors.get(keys["main"])
            absmax_tensor = tensors.get(keys["absmax"])
            quant_map_tensor = tensors.get(keys["quant_map"])
            nested_absmax = tensors.get(keys["nested_absmax"])
            nested_quant_map = tensors.get(keys["nested_quant_map"])
            quant_state_tensor = tensors.get(keys["quant_state"])
            if main_tensor is None:
                log.error(f"    MISSING main weight tensor: {keys['main']}")
                continue
            original_shape = EXPERT_SHAPES.get(proj_type)
            blocksize = 64
            if quant_state_tensor is not None:
                state_info = parse_quant_state(quant_state_tensor)
                if "shape" in state_info:
                    original_shape = tuple(state_info["shape"])
                if "blocksize" in state_info:
                    blocksize = state_info["blocksize"]
            log.info(f"      Shape: {original_shape}, blocksize: {blocksize}")
            dequantized = nf4_handler.dequantize(
                weight_packed=main_tensor, absmax=absmax_tensor,
                quant_map=quant_map_tensor, quant_state_bytes=quant_state_tensor,
                nested_absmax=nested_absmax, nested_quant_map=nested_quant_map,
                target_shape=original_shape, blocksize=blocksize,
            )
            log.info(f"      Dequantized: {dequantized.shape} {dequantized.dtype}")
            assert dequantized.shape[0] == ORIGINAL_NUM_EXPERTS, \
                f"Expected {ORIGINAL_NUM_EXPERTS} experts, got {dequantized.shape[0]}"
            new_expert_weights = create_all_new_expert_weights(dequantized, layer_idx)
            for i, w in enumerate(new_expert_weights):
                eid = ORIGINAL_NUM_EXPERTS + i
                log.info(f"      Expert {eid} ({DONOR_MAP[eid]['name']}): "
                         f"shape={w.shape}, mean={w.float().mean():.6f}, std={w.float().std():.6f}")
            expanded = torch.cat([dequantized, torch.stack(new_expert_weights)], dim=0)
            expected_shape = EXPANDED_SHAPES.get(proj_type)
            assert expanded.shape == expected_shape, \
                f"Expansion failed: got {expanded.shape}, expected {expected_shape}"
            log.info(f"      Expanded: {expanded.shape}")
            _verify_expert_diversity(expanded, layer_idx, proj_type)
            if not dry_run:
                quantized = nf4_handler.quantize(expanded, blocksize=blocksize, double_quant=True)
                prefix = keys["main"]
                tensors[prefix] = quantized["_packed"]
                tensors[f"{prefix}.absmax"] = quantized["_absmax"]
                tensors[f"{prefix}.quant_map"] = quantized["_quant_map"]
                tensors[f"{prefix}.nested_absmax"] = quantized["_nested_absmax"]
                tensors[f"{prefix}.nested_quant_map"] = quantized["_nested_quant_map"]
                tensors[f"{prefix}.quant_state.bitsandbytes__nf4"] = quantized["_quant_state"]
                for suffix in ["", ".absmax", ".quant_map", ".nested_absmax",
                               ".nested_quant_map", ".quant_state.bitsandbytes__nf4"]:
                    new_index_entries[f"{prefix}{suffix}"] = shard_filename
                log.info(f"      Requantized: packed={quantized['_packed'].shape}")
            del dequantized, expanded
            gc.collect()
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

        if "router" in expert_tensors:
            router_key = expert_tensors["router"]["main"]
            router_weight = tensors[router_key]
            log.info(f"    Router: {router_weight.shape} {router_weight.dtype} -> [{NEW_NUM_EXPERTS}, {HIDDEN_SIZE}]")
            expanded_router = expand_router_weight(router_weight, layer_idx)
            if not dry_run:
                tensors[router_key] = expanded_router
                new_index_entries[router_key] = shard_filename
            log.info(f"    Router expanded: {expanded_router.shape}")
        else:
            log.warning(f"    No router found for layer {layer_idx}")

    if not dry_run:
        log.info(f"Saving shard: {output_path}")
        save_safetensors_shard(tensors, output_path)
        size_gb = os.path.getsize(output_path) / 1e9
        log.info(f"Saved: {output_path} ({size_gb:.2f} GB)")
    del tensors
    gc.collect()
    return new_index_entries


def _verify_expert_diversity(weights, layer_idx, proj_type):
    """Verify that new experts are sufficiently diverse."""
    n_experts = weights.shape[0]
    flat = weights.reshape(n_experts, -1).float()
    new_flat = flat[ORIGINAL_NUM_EXPERTS:]
    new_norm = new_flat / (new_flat.norm(dim=1, keepdim=True) + 1e-8)
    sim_matrix = new_norm @ new_norm.T
    for i in range(NUM_NEW_EXPERTS):
        for j in range(i + 1, NUM_NEW_EXPERTS):
            sim = sim_matrix[i, j].item()
            if sim > 0.99:
                log.error(f"    DIVERSITY FAIL: experts {i+16} and {j+16} cosine sim = {sim:.6f}")
            elif sim > 0.97:
                log.warning(f"    DIVERSITY WARN: experts {i+16} and {j+16} cosine sim = {sim:.6f}")
            else:
                log.info(f"    DIVERSITY OK: experts {i+16} and {j+16} cosine sim = {sim:.6f}")
    for i in range(NUM_NEW_EXPERTS):
        new_id = ORIGINAL_NUM_EXPERTS + i
        donors = DONOR_MAP[new_id]["donors"]
        max_donor_sim = 0.0
        for d in donors:
            d_flat = flat[d:d+1]
            d_norm = d_flat / (d_flat.norm(dim=1, keepdim=True) + 1e-8)
            sim = (new_norm[i:i+1] @ d_norm.T).item()
            max_donor_sim = max(max_donor_sim, sim)
        if max_donor_sim > 0.99:
            log.warning(f"    Expert {new_id} too similar to closest donor: sim={max_donor_sim:.6f}")
        else:
            log.info(f"    Expert {new_id} ({DONOR_MAP[new_id]['name']}): max donor sim = {max_donor_sim:.4f}")


def update_index(original_index_path, output_dir, all_new_entries):
    """Update model.safetensors.index.json."""
    with open(original_index_path) as f:
        index = json.load(f)
    for key, shard in all_new_entries.items():
        index["weight_map"][key] = shard
    total_size = 0
    for shard_name in sorted(set(index["weight_map"].values())):
        shard_path = os.path.join(output_dir, shard_name)
        if os.path.exists(shard_path):
            total_size += os.path.getsize(shard_path)
    if total_size > 0:
        index["metadata"]["total_size"] = total_size
    output_path = os.path.join(output_dir, "model.safetensors.index.json")
    with open(output_path, "w") as f:
        json.dump(index, f, indent=2, sort_keys=True)
    log.info(f"Updated index: {output_path}")
    log.info(f"Total model size: {total_size / 1e9:.2f} GB")
    log.info(f"Weight map entries: {len(index['weight_map'])}")


def update_config(original_config_path, output_dir):
    """Update config.json with new expert count."""
    with open(original_config_path) as f:
        config = json.load(f)
    text_cfg = config.get("text_config", config)
    text_cfg["num_local_experts"] = NEW_NUM_EXPERTS
    text_cfg["_osen_custom_experts"] = [
        DONOR_MAP[i]["name"] for i in range(ORIGINAL_NUM_EXPERTS, NEW_NUM_EXPERTS)
    ]
    text_cfg["_osen_expert_config"] = "osen_expert_config.json"
    text_cfg["_osen_surgery_complete"] = True
    text_cfg["_osen_original_num_experts"] = ORIGINAL_NUM_EXPERTS
    text_cfg["_osen_surgery_version"] = "3.0"
    text_cfg["_osen_surgery_method"] = "semantic_orthogonal_donor_blend_v3"
    output_path = os.path.join(output_dir, "config.json")
    with open(output_path, "w") as f:
        json.dump(config, f, indent=2)
    log.info(f"Updated config: {output_path}")
    log.info(f"  num_local_experts = {NEW_NUM_EXPERTS}")


def verify_roundtrip(nf4_handler, device="cpu"):
    """Verify NF4 quantize -> dequantize roundtrip preserves weights."""
    log.info("Running NF4 roundtrip integrity check...")
    test_shape = (2, 128, 64)
    original = torch.randn(test_shape, dtype=torch.bfloat16)
    quantized = nf4_handler.quantize(original, blocksize=64, double_quant=True)
    recovered = nf4_handler.dequantize(
        weight_packed=quantized["_packed"], absmax=quantized["_absmax"],
        quant_map=quantized["_quant_map"], quant_state_bytes=quantized["_quant_state"],
        nested_absmax=quantized["_nested_absmax"], nested_quant_map=quantized["_nested_quant_map"],
        target_shape=test_shape, blocksize=64,
    )
    err = (original.float() - recovered.float()).abs()
    max_err = err.max().item()
    mean_err = err.mean().item()
    cosine_sim = torch.nn.functional.cosine_similarity(
        original.float().flatten().unsqueeze(0),
        recovered.float().flatten().unsqueeze(0)
    ).item()
    log.info(f"  Roundtrip max error:  {max_err:.6f}")
    log.info(f"  Roundtrip mean error: {mean_err:.6f}")
    log.info(f"  Cosine similarity:    {cosine_sim:.6f}")
    if cosine_sim < 0.95:
        log.error("  ROUNDTRIP CHECK FAILED -- NF4 quantization is producing garbage!")
        sys.exit(1)
    elif cosine_sim < 0.99:
        log.warning("  Roundtrip quality is marginal.")
    else:
        log.info("  Roundtrip check PASSED")


def main():
    parser = argparse.ArgumentParser(
        description="MoE Expert Injection v2 -- Add 4 new experts to Llama 4 Scout"
    )
    parser.add_argument("--model-dir", type=str, required=True,
                        help="Path to original model directory with safetensors")
    parser.add_argument("--output-dir", type=str, required=True,
                        help="Path to output directory for modified model")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run without saving (for testing)")
    parser.add_argument("--layers", type=str, default=None,
                        help="Comma-separated layer indices to process (default: all 48)")
    parser.add_argument("--device", type=str, default="auto",
                        help="Device: auto, cpu, or cuda")
    parser.add_argument("--skip-roundtrip", action="store_true",
                        help="Skip the NF4 roundtrip integrity check")
    args = parser.parse_args()

    if args.device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    else:
        device = args.device

    model_dir = Path(args.model_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    index_path = model_dir / "model.safetensors.index.json"
    config_path = model_dir / "config.json"
    if not index_path.exists():
        log.error(f"Index not found: {index_path}")
        sys.exit(1)

    nf4 = NF4Handler(device=device)
    log.info("=" * 70)
    log.info("  MoE Expert Injection Pipeline v2")
    log.info(f"  Model:      {model_dir}")
    log.info(f"  Output:     {output_dir}")
    log.info(f"  Experts:    {ORIGINAL_NUM_EXPERTS} -> {NEW_NUM_EXPERTS}")
    log.info(f"  Layers:     {NUM_LAYERS}")
    log.info(f"  Device:     {device}")
    log.info(f"  NF4 engine: {'bitsandbytes (native)' if nf4.use_bnb else 'manual (fallback)'}")
    log.info(f"  Dry run:    {args.dry_run}")
    log.info("=" * 70)

    if not args.skip_roundtrip:
        verify_roundtrip(nf4, device)
    else:
        log.warning("Skipping NF4 roundtrip check (--skip-roundtrip)")

    shard_layers = get_shard_layers(str(index_path))
    log.info("Shard mapping:")
    for shard, layers in sorted(shard_layers.items()):
        log.info(f"  {shard}: layers {layers}")

    if args.layers:
        target_layers = set(int(x.strip()) for x in args.layers.split(","))
    else:
        target_layers = set(range(NUM_LAYERS))

    import shutil
    log.info("Copying supporting files...")
    for item in model_dir.iterdir():
        if item.is_file() and not item.name.endswith(".safetensors"):
            dest = output_dir / item.name
            if not dest.exists():
                shutil.copy2(item, dest)
                log.info(f"  Copied: {item.name}")

    all_new_entries = {}
    total_shards = len(shard_layers)
    for shard_idx, (shard_name, layers) in enumerate(sorted(shard_layers.items())):
        process_layers = [l for l in layers if l in target_layers]
        if not process_layers:
            src = model_dir / shard_name
            dst = output_dir / shard_name
            if src.exists() and not dst.exists():
                log.info(f"[{shard_idx+1}/{total_shards}] Copying unchanged: {shard_name}")
                shutil.copy2(src, dst)
            continue
        log.info(f"\n[{shard_idx+1}/{total_shards}] Processing: {shard_name} -> layers {process_layers}")
        new_entries = process_shard(
            shard_path=str(model_dir / shard_name),
            output_path=str(output_dir / shard_name),
            layer_indices=process_layers,
            nf4_handler=nf4,
            dry_run=args.dry_run,
        )
        all_new_entries.update(new_entries)

    for shard_file in sorted(model_dir.glob("model-*.safetensors")):
        dest = output_dir / shard_file.name
        if not dest.exists():
            log.info(f"Copying remaining: {shard_file.name}")
            shutil.copy2(shard_file, dest)

    if not args.dry_run:
        update_index(str(index_path), str(output_dir), all_new_entries)
        update_config(str(config_path), str(output_dir))

    log.info("")
    log.info("=" * 70)
    log.info("  MoE Expert Injection COMPLETE")
    log.info(f"  New experts: {[DONOR_MAP[i]['name'] for i in range(16, 20)]}")
    log.info(f"  Method: Orthogonal donor blending + PCA router init")
    log.info(f"  Output: {output_dir}")
    log.info("=" * 70)


if __name__ == "__main__":
    main()
