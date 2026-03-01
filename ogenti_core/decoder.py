"""
decoder.py — Protocol → Natural Language / Action Decoder

The decoder is the mirror of the encoder. It receives a compressed
ProtocolMessage and reconstructs the original intent, either as
natural language or as a structured action that a downstream agent
can execute.

Architecture
------------
                ┌────────────────────┐
  protocol  ───▶│  Base LLM (frozen) │
  token IDs     │  + LoRA (trained)  │ ──▶ NL reconstruction / action
                └────────────────────┘

Both encoder and decoder share the same base model but have
*separate* LoRA adapters trained through the MARL loop.
"""

from __future__ import annotations

import json
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

from ogenti_core.protocol import ProtocolMessage, ProtocolConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Decoder Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class DecoderConfig:
    """Configuration for the Ogenti decoder."""

    model_name: str = "Qwen/Qwen2.5-3B-Instruct"
    lora_rank: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.05
    lora_target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"]
    )
    device: str = "auto"
    dtype: str = "bfloat16"
    max_decode_tokens: int = 256  # NL reconstruction / action output budget

    # Prompt template
    decode_prefix: str = "<|proto|>"   # prefix before protocol tokens
    decode_suffix: str = "<|decode|>"  # separator before NL output

    @property
    def torch_dtype(self) -> torch.dtype:
        return {
            "bfloat16": torch.bfloat16,
            "float16": torch.float16,
            "float32": torch.float32,
        }[self.dtype]


# ─────────────────────────────────────────────────────────────────
#  Structured Action Output
# ─────────────────────────────────────────────────────────────────

@dataclass
class DecodedAction:
    """
    Structured representation of what the decoder understood
    from the protocol message.

    Can be used either as free-text reconstruction or as
    a structured tool call.
    """

    text: str                       # NL reconstruction
    confidence: float = 0.0        # decoder self-assessed confidence
    action_type: Optional[str] = None   # e.g. "summarize", "translate"
    action_params: dict = field(default_factory=dict)  # parsed params

    def to_dict(self) -> dict:
        return {
            "text": self.text,
            "confidence": self.confidence,
            "action_type": self.action_type,
            "action_params": self.action_params,
        }


# ─────────────────────────────────────────────────────────────────
#  Decoder Module
# ─────────────────────────────────────────────────────────────────

class OgentiDecoder(nn.Module):
    """
    Decodes protocol token sequences back into natural language
    or structured actions.

    Usage (inference)
    -----------------
    >>> decoder = OgentiDecoder.from_pretrained("ogenti/ogenti-3b-v1.0")
    >>> action = decoder.decode(protocol_message)
    >>> print(action.text)  # NL reconstruction
    """

    def __init__(
        self,
        model: PreTrainedModel,
        tokenizer: PreTrainedTokenizerBase,
        config: DecoderConfig,
        protocol_config: ProtocolConfig,
    ):
        super().__init__()
        self.model = model
        self.tokenizer = tokenizer
        self.config = config
        self.protocol_config = protocol_config

    # ── Factory ──

    @classmethod
    def build(
        cls,
        decoder_config: Optional[DecoderConfig] = None,
        protocol_config: Optional[ProtocolConfig] = None,
    ) -> OgentiDecoder:
        """Build decoder from scratch (for training)."""
        dec_cfg = decoder_config or DecoderConfig()
        proto_cfg = protocol_config or ProtocolConfig()

        logger.info("Loading base model for decoder: %s", dec_cfg.model_name)

        tokenizer = AutoTokenizer.from_pretrained(
            dec_cfg.model_name, trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        model = AutoModelForCausalLM.from_pretrained(
            dec_cfg.model_name,
            torch_dtype=dec_cfg.torch_dtype,
            device_map=dec_cfg.device,
            trust_remote_code=True,
        )

        model = cls._apply_lora(model, dec_cfg)

        return cls(model, tokenizer, dec_cfg, proto_cfg)

    @classmethod
    def from_pretrained(cls, path: str) -> OgentiDecoder:
        """Load a trained decoder (LoRA adapter + config)."""
        from peft import PeftModel
        from pathlib import Path

        ckpt = Path(path)

        with open(ckpt / "decoder_config.json") as f:
            dec_cfg = DecoderConfig(**json.load(f))
        with open(ckpt / "protocol_config.json") as f:
            proto_cfg = ProtocolConfig.from_dict(json.load(f))

        tokenizer = AutoTokenizer.from_pretrained(
            dec_cfg.model_name, trust_remote_code=True
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        base_model = AutoModelForCausalLM.from_pretrained(
            dec_cfg.model_name,
            torch_dtype=dec_cfg.torch_dtype,
            device_map=dec_cfg.device,
            trust_remote_code=True,
        )
        model = PeftModel.from_pretrained(base_model, str(ckpt / "lora_adapter"))
        return cls(model, tokenizer, dec_cfg, proto_cfg)

    # ── Core Decode ──

    @torch.no_grad()
    def decode(
        self,
        message: ProtocolMessage,
        return_structured: bool = False,
    ) -> DecodedAction:
        """
        Decode a ProtocolMessage into a DecodedAction.

        Parameters
        ----------
        message : ProtocolMessage
            The compressed protocol message.
        return_structured : bool
            If True, attempt to parse the output as structured
            action (action_type + action_params).

        Returns
        -------
        DecodedAction
        """
        self.model.eval()

        # Build decoder input: <decode_prefix> protocol_tokens <decode_suffix>
        proto_text = self.tokenizer.decode(
            message.token_ids, skip_special_tokens=False
        )
        prompt = f"{self.config.decode_prefix}{proto_text}{self.config.decode_suffix}"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=self.config.max_decode_tokens,
            do_sample=False,
            temperature=1.0,
            pad_token_id=self.tokenizer.pad_token_id,
        )

        # Extract generated text (strip prompt)
        prompt_len = inputs["input_ids"].shape[1]
        decoded_text = self.tokenizer.decode(
            outputs[0, prompt_len:], skip_special_tokens=True
        ).strip()

        action = DecodedAction(text=decoded_text)

        if return_structured:
            action = self._parse_structured(decoded_text, action)

        return action

    def decode_for_training(
        self,
        message: ProtocolMessage,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Decode with full gradient flow for RL training.

        Returns (sequences, scores) for policy gradient computation.
        """
        proto_text = self.tokenizer.decode(
            message.token_ids, skip_special_tokens=False
        )
        prompt = f"{self.config.decode_prefix}{proto_text}{self.config.decode_suffix}"
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)

        outputs = self.model.generate(
            **inputs,
            max_new_tokens=self.config.max_decode_tokens,
            do_sample=True,
            temperature=0.8,
            top_p=0.95,
            pad_token_id=self.tokenizer.pad_token_id,
            return_dict_in_generate=True,
            output_scores=True,
        )

        return outputs.sequences, outputs.scores

    def compute_reconstruction_loss(
        self,
        message: ProtocolMessage,
        target_text: str,
    ) -> torch.Tensor:
        """
        Compute cross-entropy loss between decoder output and
        the target NL text. Used as an auxiliary supervised signal
        during early training phases.
        """
        # Build input
        proto_text = self.tokenizer.decode(
            message.token_ids, skip_special_tokens=False
        )
        prompt = f"{self.config.decode_prefix}{proto_text}{self.config.decode_suffix}"
        full_text = prompt + target_text

        inputs = self.tokenizer(
            full_text, return_tensors="pt", truncation=True, max_length=512
        ).to(self.model.device)

        labels = inputs["input_ids"].clone()
        # Mask the prompt portion (only compute loss on target)
        prompt_ids = self.tokenizer(prompt, return_tensors="pt")["input_ids"]
        labels[:, : prompt_ids.shape[1]] = -100

        outputs = self.model(
            input_ids=inputs["input_ids"],
            attention_mask=inputs["attention_mask"],
            labels=labels,
        )
        return outputs.loss

    # ── Structured Parsing ──

    @staticmethod
    def _parse_structured(text: str, action: DecodedAction) -> DecodedAction:
        """
        Attempt to parse the decoded text as a structured JSON action.
        Falls back to plain text if parsing fails.
        """
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                action.action_type = data.get("action", data.get("type"))
                action.action_params = {
                    k: v for k, v in data.items()
                    if k not in ("action", "type", "confidence")
                }
                action.confidence = float(data.get("confidence", 0.0))
        except (json.JSONDecodeError, ValueError):
            # Not structured — that's fine, use raw text
            pass
        return action

    # ── LoRA ──

    @staticmethod
    def _apply_lora(model: PreTrainedModel, config: DecoderConfig) -> PreTrainedModel:
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
            "Decoder LoRA — trainable: %s / %s (%.2f%%)",
            f"{trainable:,}", f"{total:,}", 100 * trainable / total,
        )
        return model

    # ── Persistence ──

    def save_pretrained(self, path: str) -> None:
        """Save LoRA adapter + configs."""
        from pathlib import Path as P

        out = P(path)
        out.mkdir(parents=True, exist_ok=True)

        self.model.save_pretrained(str(out / "lora_adapter"))
        self.tokenizer.save_pretrained(str(out / "lora_adapter"))

        with open(out / "decoder_config.json", "w") as f:
            json.dump({
                "model_name": self.config.model_name,
                "lora_rank": self.config.lora_rank,
                "lora_alpha": self.config.lora_alpha,
                "lora_dropout": self.config.lora_dropout,
                "lora_target_modules": self.config.lora_target_modules,
                "max_decode_tokens": self.config.max_decode_tokens,
                "decode_prefix": self.config.decode_prefix,
                "decode_suffix": self.config.decode_suffix,
            }, f, indent=2)
        with open(out / "protocol_config.json", "w") as f:
            json.dump(self.protocol_config.to_dict(), f, indent=2)
