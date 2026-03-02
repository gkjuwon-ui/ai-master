"""
encoder.py — Natural Language → Protocol Encoder

The encoder takes a natural language instruction and produces a
compact ProtocolMessage. It wraps a small LLM (e.g. Qwen2.5-3B)
with a LoRA adapter trained via MARL to emit minimal token sequences
that preserve the original intent.

Architecture
------------
                ┌────────────────────┐
  NL input ───▶ │  Base LLM (frozen) │
                │  + LoRA (trained)  │ ──▶ protocol token IDs
                └────────────────────┘

The encoder is *generative*: it auto-regressively produces protocol
tokens given the NL input as a prefix, stopping when it emits the
end-of-message token or hits the budget ceiling.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

import torch
import torch.nn as nn
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    PreTrainedModel,
    PreTrainedTokenizerBase,
)

from ogenti_core.protocol import ProtocolMessage, ProtocolConfig, MessageType

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Encoder Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class EncoderConfig:
    """Configuration for the Ogenti encoder."""

    model_name: str = "Qwen/Qwen2.5-3B-Instruct"
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"]
    )
    device: str = "auto"
    dtype: str = "bfloat16"  # bfloat16 | float16 | float32
    max_new_tokens: int = 30  # maximum protocol tokens to generate

    # Special prompt template
    encode_prefix: str = "<|encode|>"  # prefix injected before NL input
    encode_suffix: str = "<|proto|>"   # separator before protocol output

    @property
    def torch_dtype(self) -> torch.dtype:
        return {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }[self.dtype]


# ─────────────────────────────────────────────────────────────────
#  Encoder Module
# ─────────────────────────────────────────────────────────────────

class OgentiEncoder(nn.Module):
    """
    Encodes natural language instructions into compact protocol
    token sequences.

    Wraps a base causal LM with LoRA adapters.  During MARL training
    the LoRA weights are updated via policy gradient (PPO / MAPPO);
    the base model weights stay frozen.

    Usage (inference)
    -----------------
    >>> encoder = OgentiEncoder.from_pretrained("ogenti/ogenti-3b-v1.0")
    >>> msg = encoder.encode("Summarize this file in 200 words")
    >>> print(msg.token_count)  # e.g. 8
    """

    def __init__(
        self,
        model: PreTrainedModel,
        tokenizer: PreTrainedTokenizerBase,
        config: EncoderConfig,
        protocol_config: ProtocolConfig,
    ):
        super().__init__()
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.protocol_config = protocol_config

        # Cache special token IDs
        self._end_token_id = self._resolve_token_id(protocol_config.end_token)
        self._eos_token_id = tokenizer.eos_token_id

        # Set protocol vocab size from tokenizer
        if protocol_config.vocab_size == 0:
            protocol_config.vocab_size = len(tokenizer)

    # ── Factory ──

    @classmethod
    def build(
        cls,
        encoder_config: Optional[EncoderConfig] = None,
        protocol_config: Optional[ProtocolConfig] = None,
    ) -> OgentiEncoder:
        """
        Build encoder from scratch (for training).

        Loads the base model, applies LoRA, and returns
        a ready-to-train encoder.
        """
        enc_cfg = encoder_config or EncoderConfig()
        proto_cfg = protocol_config or ProtocolConfig()

        logger.info("Loading base model: %s", enc_cfg.model_name)

        tokenizer = AutoTokenizer.from_pretrained(
            enc_cfg.model_name,
            trust_remote_code=True,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            enc_cfg.model_name,
            dtype=enc_cfg.torch_dtype,
            device_map=enc_cfg.device,
            trust_remote_code=True,
        )

        # Apply LoRA
        model = cls._apply_lora(model, enc_cfg)

        return cls(model, tokenizer, enc_cfg, proto_cfg)

    @classmethod
    def from_pretrained(cls, path: str) -> OgentiEncoder:
        """Load a trained encoder (LoRA adapter + config)."""
        from peft import PeftModel
        import json
        from pathlib import Path

        ckpt = Path(path)

        with open(ckpt / "encoder_config.json", encoding="utf-8") as f:
            enc_cfg = EncoderConfig(**json.load(f))
        with open(ckpt / "protocol_config.json", encoding="utf-8") as f:
            proto_cfg = ProtocolConfig.from_dict(json.load(f))

        tokenizer = AutoTokenizer.from_pretrained(
            enc_cfg.model_name, trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            enc_cfg.model_name,
            torch_dtype=enc_cfg.torch_dtype,
            device_map=enc_cfg.device,
            trust_remote_code=True,
        )

        model = PeftModel.from_pretrained(base_model, str(ckpt / "lora_adapter"))

        return cls(model, tokenizer, enc_cfg, proto_cfg)

    # ── Core Encode ──

    @torch.no_grad()
    def encode(
        self,
        natural_language: str,
        sender_id: str = "agent_0",
        receiver_id: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> ProtocolMessage:
        """
        Encode a natural language instruction into a ProtocolMessage.

        Parameters
        ----------
        natural_language : str
            The NL instruction to compress.
        sender_id : str
            Sending agent identifier.
        receiver_id : str | None
            Receiving agent identifier (None = broadcast).
        max_tokens : int | None
            Override max protocol tokens (default: from config).

        Returns
        -------
        ProtocolMessage
        """
        self.model.eval()
        budget = max_tokens or self.config.max_new_tokens

        # Build input: <encode_prefix> NL <encode_suffix>
        prompt = f"{self.config.encode_prefix}{natural_language}{self.config.encode_suffix}"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        # Generate protocol tokens
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=budget,
            do_sample=False,
            temperature=1.0,
            eos_token_id=[self._end_token_id, self._eos_token_id],
            pad_token_id=self.tokenizer.pad_token_id,
        )

        # Extract only the generated tokens (strip prompt)
        prompt_len = inputs["input_ids"].shape[1]
        protocol_ids = outputs[0, prompt_len:].tolist()

        # Remove end/eos tokens from the tail
        protocol_ids = self._strip_special(protocol_ids)

        return ProtocolMessage(
            token_ids=protocol_ids,
            sender_id=sender_id,
            receiver_id=receiver_id,
        )

    def encode_for_training(
        self,
        natural_language: str,
        max_tokens: Optional[int] = None,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Encode with full gradient flow for RL training.

        Returns (input_ids, logits) so the trainer can compute
        log-probabilities for policy gradient.
        """
        budget = max_tokens or self.config.max_new_tokens
        prompt = f"{self.config.encode_prefix}{natural_language}{self.config.encode_suffix}"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        # Forward pass (with gradients)
        outputs = self.model.generate(
            **inputs,
            max_new_tokens=budget,
            do_sample=True,
            temperature=0.8,
            top_p=0.95,
            eos_token_id=[self._end_token_id, self._eos_token_id],
            pad_token_id=self.tokenizer.pad_token_id,
            return_dict_in_generate=True,
            output_scores=True,
        )

        return outputs.sequences, outputs.scores

    # ── LoRA ──

    @staticmethod
    def _apply_lora(model: PreTrainedModel, config: EncoderConfig) -> PreTrainedModel:
        """Apply LoRA adapters to the base model."""
        from peft import LoraConfig, get_peft_model, TaskType

        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=config.lora_rank,
            lora_alpha=config.lora_alpha,
            lora_dropout=config.lora_dropout,
            target_modules=config.lora_target_modules,
            bias="none",
        )
        model = get_peft_model(model, lora_config)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        total = sum(p.numel() for p in model.parameters())
        logger.info(
            "LoRA applied — trainable: %s / %s (%.2f%%)",
            f"{trainable:,}", f"{total:,}", 100 * trainable / total,
        )
        return model

    # ── Helpers ──

    def _resolve_token_id(self, char: str) -> int:
        """Get the token ID for a single character."""
        ids = self.tokenizer.encode(char, add_special_tokens=False)
        if not ids:
            logger.warning("Token %r not in vocabulary, using EOS", char)
            return self.tokenizer.eos_token_id
        return ids[0]

    def _strip_special(self, token_ids: list[int]) -> list[int]:
        """Remove trailing end/eos tokens."""
        special = {self._end_token_id, self._eos_token_id}
        while token_ids and token_ids[-1] in special:
            token_ids.pop()
        return token_ids

    def save_pretrained(self, path: str) -> None:
        """Save LoRA adapter + configs."""
        import json
        from pathlib import Path

        out = Path(path)
        out.mkdir(parents=True, exist_ok=True)

        # Save LoRA weights
        self.model.save_pretrained(str(out / "lora_adapter"))
        self.tokenizer.save_pretrained(str(out / "lora_adapter"))

        # Save configs
        with open(out / "encoder_config.json", "w", encoding="utf-8") as f:
            json.dump({
                "model_name": self.config.model_name,
                "lora_rank": self.config.lora_rank,
                "lora_alpha": self.config.lora_alpha,
                "lora_dropout": self.config.lora_dropout,
                "lora_target_modules": self.config.lora_target_modules,
                "max_new_tokens": self.config.max_new_tokens,
                "encode_prefix": self.config.encode_prefix,
                "encode_suffix": self.config.encode_suffix,
            }, f, indent=2, ensure_ascii=False)
        with open(out / "protocol_config.json", "w", encoding="utf-8") as f:
            json.dump(self.protocol_config.to_dict(), f, indent=2, ensure_ascii=False)
