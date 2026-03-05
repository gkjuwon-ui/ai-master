"""
detector.py — PHIREN Hallucination Detector

Two-stage pipeline:
  1. Claim Extraction: decompose text into atomic claims
  2. NLI Verification: for each claim, run NLI against context

Follows the same nn.Module pattern as OgentiEncoder / OgentiDecoder
so it can be trained with LoRA + MAPPO.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import torch
import torch.nn as nn
import torch.nn.functional as F

from .protocol import (
    Claim,
    ClaimCategory,
    ClaimConfig,
    ClaimVerdict,
    VerificationMessage,
    VerificationMode,
    compute_factuality_score,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Detector Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class DetectorConfig:
    """Configuration for the PhirenDetector."""

    # Backbone LLM (for claim extraction)
    model_name: str = "meta-llama/Llama-3.1-8B-Instruct"

    # NLI cross-encoder
    nli_model_name: str = "cross-encoder/nli-deberta-v3-base"

    # LoRA
    lora_r: int = 16
    lora_alpha: float = 32.0
    lora_dropout: float = 0.05
    lora_target_modules: list[str] = field(
        default_factory=lambda: ["q_proj", "v_proj", "k_proj", "o_proj"]
    )

    # Quantization
    load_in_4bit: bool = True
    bnb_4bit_compute_dtype: str = "bfloat16"
    bnb_4bit_quant_type: str = "nf4"

    # Claim extraction
    max_claims: int = 20
    extraction_prompt_template: str = (
        "Decompose the following text into atomic factual claims.\n"
        "Return one claim per line, prefixed with a number.\n"
        "Skip opinions and subjective statements.\n\n"
        "Text: {text}\n\n"
        "Claims:"
    )

    # Verification
    confidence_threshold: float = 0.5
    contradiction_threshold: float = 0.3

    # Hidden size (set from model after loading)
    hidden_size: int = 4096

    def to_dict(self) -> dict:
        return {
            "model_name": self.model_name,
            "nli_model_name": self.nli_model_name,
            "lora_r": self.lora_r,
            "lora_alpha": self.lora_alpha,
            "lora_dropout": self.lora_dropout,
            "load_in_4bit": self.load_in_4bit,
            "max_claims": self.max_claims,
            "hidden_size": self.hidden_size,
        }


# ─────────────────────────────────────────────────────────────────
#  Claim Extraction Head
# ─────────────────────────────────────────────────────────────────

class ClaimExtractionHead(nn.Module):
    """
    Linear head on top of the backbone LLM.
    Produces per-token *claim boundary* logits:
      [O, B-CLAIM, I-CLAIM]
    Used in training to learn claim extraction as a sequence labelling task.
    """

    def __init__(self, hidden_size: int, num_labels: int = 3):
        super().__init__()
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 4),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size // 4, num_labels),
        )

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        return self.classifier(hidden_states)


# ─────────────────────────────────────────────────────────────────
#  NLI Verification Head
# ─────────────────────────────────────────────────────────────────

class NLIVerificationHead(nn.Module):
    """
    Produces 3-way NLI logits (entailment, neutral, contradiction)
    from a [CLS]-style representation of (claim, context).
    """

    def __init__(self, hidden_size: int):
        super().__init__()
        self.nli_head = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden_size // 2, 3),  # entail, neutral, contradict
        )

    def forward(self, cls_hidden: torch.Tensor) -> torch.Tensor:
        return self.nli_head(cls_hidden)


# ─────────────────────────────────────────────────────────────────
#  PHIREN Detector
# ─────────────────────────────────────────────────────────────────

class PhirenDetector(nn.Module):
    """
    Two-stage hallucination detector.

    Stage 1 — Claim Extraction
        Uses the backbone LLM (with LoRA) to extract atomic claims
        from generated text. In inference, this can use generation;
        in training, learned via sequence labelling (BIO).

    Stage 2 — NLI Verification
        Each claim is paired with context and run through the NLI
        model/head to produce (entailment, neutral, contradiction).
    """

    def __init__(self, config: DetectorConfig):
        super().__init__()
        self.config = config

        # Heads (lightweight — allocated now)
        self.claim_head = ClaimExtractionHead(config.hidden_size)
        self.nli_head = NLIVerificationHead(config.hidden_size)

        # Backbone references (set by build() or attach())
        self.backbone = None
        self.tokenizer = None
        self.nli_model = None
        self.nli_tokenizer = None

        # LoRA state
        self._lora_applied = False

    # ──────────── Construction ────────────

    @classmethod
    def build(
        cls,
        config: Optional[DetectorConfig] = None,
        device: str = "auto",
    ) -> PhirenDetector:
        """
        Build a PhirenDetector by loading backbone + NLI models.
        Uses 4-bit quantization and LoRA by default.
        """
        config = config or DetectorConfig()

        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig
        except ImportError:
            raise ImportError("pip install transformers bitsandbytes peft")

        logger.info(f"Loading backbone: {config.model_name}")

        bnb_config = None
        if config.load_in_4bit:
            import torch as _torch
            dtype = getattr(_torch, config.bnb_4bit_compute_dtype, _torch.bfloat16)
            bnb_config = BitsAndBytesConfig(
                load_in_4bit=True,
                bnb_4bit_compute_dtype=dtype,
                bnb_4bit_quant_type=config.bnb_4bit_quant_type,
            )

        backbone = AutoModelForCausalLM.from_pretrained(
            config.model_name,
            quantization_config=bnb_config,
            device_map=device,
            torch_dtype=torch.bfloat16,
        )
        tokenizer = AutoTokenizer.from_pretrained(config.model_name)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        config.hidden_size = backbone.config.hidden_size

        detector = cls(config)
        detector.backbone = backbone
        detector.tokenizer = tokenizer
        detector._apply_lora()

        # Load NLI model
        detector._load_nli_model(device)

        logger.info(
            f"PhirenDetector built | backbone={config.model_name} | "
            f"nli={config.nli_model_name} | LoRA r={config.lora_r}"
        )
        return detector

    @classmethod
    def from_pretrained(cls, path: str, device: str = "auto") -> PhirenDetector:
        """Load a saved PhirenDetector checkpoint."""
        import json
        from pathlib import Path

        ckpt_dir = Path(path)
        with open(ckpt_dir / "config.json") as f:
            cfg_dict = json.load(f)

        config = DetectorConfig(**{
            k: v for k, v in cfg_dict.items()
            if k in DetectorConfig.__dataclass_fields__
        })

        detector = cls.build(config, device=device)

        heads_path = ckpt_dir / "heads.pt"
        if heads_path.exists():
            state = torch.load(heads_path, map_location="cpu", weights_only=True)
            detector.claim_head.load_state_dict(state["claim_head"])
            detector.nli_head.load_state_dict(state["nli_head"])
            logger.info(f"Loaded heads from {heads_path}")

        # Load LoRA adapter if present
        adapter_path = ckpt_dir / "lora_adapter"
        if adapter_path.exists() and detector.backbone is not None:
            try:
                from peft import PeftModel
                detector.backbone = PeftModel.from_pretrained(
                    detector.backbone, str(adapter_path)
                )
                logger.info(f"Loaded LoRA adapter from {adapter_path}")
            except ImportError:
                logger.warning("peft not installed, skipping LoRA adapter load")

        return detector

    def _load_nli_model(self, device: str = "auto") -> None:
        """Load the cross-encoder NLI model."""
        try:
            from transformers import AutoModelForSequenceClassification, AutoTokenizer

            self.nli_model = AutoModelForSequenceClassification.from_pretrained(
                self.config.nli_model_name,
                torch_dtype=torch.float16,
            )
            self.nli_tokenizer = AutoTokenizer.from_pretrained(
                self.config.nli_model_name
            )

            if device != "auto" and device != "cpu":
                self.nli_model = self.nli_model.to(device)

            self.nli_model.eval()
            logger.info(f"NLI model loaded: {self.config.nli_model_name}")
        except Exception as e:
            logger.warning(f"Failed to load NLI model: {e}")
            self.nli_model = None
            self.nli_tokenizer = None

    def _apply_lora(self) -> None:
        """Apply LoRA to the backbone."""
        if self._lora_applied or self.backbone is None:
            return
        try:
            from peft import LoraConfig, get_peft_model, TaskType

            lora_config = LoraConfig(
                r=self.config.lora_r,
                lora_alpha=self.config.lora_alpha,
                lora_dropout=self.config.lora_dropout,
                target_modules=self.config.lora_target_modules,
                task_type=TaskType.CAUSAL_LM,
                bias="none",
            )
            self.backbone = get_peft_model(self.backbone, lora_config)
            self._lora_applied = True
            trainable = sum(
                p.numel() for p in self.backbone.parameters() if p.requires_grad
            )
            total = sum(p.numel() for p in self.backbone.parameters())
            logger.info(
                f"LoRA applied | trainable={trainable:,} / {total:,} "
                f"({100 * trainable / total:.2f}%)"
            )
        except ImportError:
            logger.warning("peft not installed, skipping LoRA")

    # ──────────── Stage 1: Claim Extraction ────────────

    @torch.no_grad()
    def extract_claims(self, text: str) -> list[Claim]:
        """
        Extract atomic claims from text using the backbone LLM.

        In inference: uses generation (prompt → LLM → parse numbered list).
        Falls back to sentence splitting if no LLM is available.
        """
        if self.backbone is None or self.tokenizer is None:
            return self._fallback_extract(text)

        prompt = self.config.extraction_prompt_template.format(text=text)
        inputs = self.tokenizer(
            prompt,
            return_tensors="pt",
            max_length=self.config.max_claims * 30 + 200,
            truncation=True,
        )
        device = next(self.backbone.parameters()).device
        inputs = {k: v.to(device) for k, v in inputs.items()}

        outputs = self.backbone.generate(
            **inputs,
            max_new_tokens=self.config.max_claims * 50,
            temperature=0.1,
            do_sample=True,
            top_p=0.9,
        )

        generated = self.tokenizer.decode(
            outputs[0][inputs["input_ids"].shape[1]:],
            skip_special_tokens=True,
        )

        return self._parse_claims(generated)

    def extract_claims_for_training(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        labels: Optional[torch.Tensor] = None,
    ) -> tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Training-time claim extraction via sequence labelling.

        Returns:
            (claim_logits, loss) — claim_logits shape [B, T, 3]
        """
        if self.backbone is None:
            raise RuntimeError("Backbone not loaded")

        outputs = self.backbone(
            input_ids=input_ids,
            attention_mask=attention_mask,
            output_hidden_states=True,
        )
        hidden = outputs.hidden_states[-1]  # [B, T, H]
        logits = self.claim_head(hidden)     # [B, T, 3]

        loss = None
        if labels is not None:
            loss = F.cross_entropy(
                logits.view(-1, 3),
                labels.view(-1),
                ignore_index=-100,
            )

        return logits, loss

    def _parse_claims(self, text: str) -> list[Claim]:
        """Parse numbered list output from LLM into Claim objects."""
        claims = []
        lines = text.strip().split("\n")
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            # Remove numbering prefixes like "1.", "1)", "- "
            cleaned = re.sub(r"^[\d]+[.)]\s*", "", line)
            cleaned = re.sub(r"^[-•]\s*", "", cleaned)
            cleaned = cleaned.strip()

            if len(cleaned) < 5:
                continue

            category = self._classify_claim_category(cleaned)

            claims.append(Claim(
                claim_id=len(claims),
                text=cleaned,
                category=category,
            ))

            if len(claims) >= self.config.max_claims:
                break

        return claims

    def _fallback_extract(self, text: str) -> list[Claim]:
        """Sentence-splitting fallback when backbone is not available."""
        sentences = re.split(r"(?<=[.!?])\s+", text)
        claims = []
        for i, sent in enumerate(sentences):
            sent = sent.strip()
            if len(sent) < 5:
                continue
            claims.append(Claim(
                claim_id=i,
                text=sent,
                category=self._classify_claim_category(sent),
            ))
            if len(claims) >= self.config.max_claims:
                break
        return claims

    @staticmethod
    def _classify_claim_category(text: str) -> ClaimCategory:
        """Simple heuristic-based claim classification."""
        text_lower = text.lower()

        # Numerical
        if re.search(r"\d+\.?\d*\s*(%|percent|million|billion|thousand)", text_lower):
            return ClaimCategory.NUMERICAL

        # Temporal
        if re.search(r"\b(in \d{4}|century|year|date|era|founded|created)\b", text_lower):
            return ClaimCategory.TEMPORAL

        # Causal
        if re.search(r"\b(because|causes?|leads? to|results? in|due to)\b", text_lower):
            return ClaimCategory.CAUSAL

        # Comparative
        if re.search(r"\b(more|less|better|worse|larger|smaller|greater|than)\b", text_lower):
            return ClaimCategory.COMPARATIVE

        # Definitional
        if re.search(r"\b(is defined as|refers to|means|is a type of)\b", text_lower):
            return ClaimCategory.DEFINITIONAL

        # Meta
        if re.search(r"\b(I think|I believe|in my opinion)\b", text_lower):
            return ClaimCategory.META

        return ClaimCategory.FACTUAL

    # ──────────── Stage 2: NLI Verification ────────────

    @torch.no_grad()
    def verify_claims(
        self,
        claims: list[Claim],
        context: str,
    ) -> list[Claim]:
        """
        Verify each claim against the context using NLI.

        Returns claims with verdict, confidence, and nli_scores filled in.
        """
        if not claims:
            return claims

        if self.nli_model is None or self.nli_tokenizer is None:
            logger.warning("NLI model not loaded, returning unverified claims")
            for c in claims:
                c.verdict = ClaimVerdict.UNVERIFIABLE
            return claims

        device = next(self.nli_model.parameters()).device

        for claim in claims:
            if claim.category == ClaimCategory.SUBJECTIVE:
                claim.verdict = ClaimVerdict.UNVERIFIABLE
                claim.confidence = 1.0
                continue

            inputs = self.nli_tokenizer(
                context,
                claim.text,
                return_tensors="pt",
                max_length=512,
                truncation=True,
                padding=True,
            )
            inputs = {k: v.to(device) for k, v in inputs.items()}

            logits = self.nli_model(**inputs).logits  # [1, 3]
            probs = F.softmax(logits, dim=-1)[0]      # [3]

            # DeBERTa NLI: 0=contradiction, 1=neutral, 2=entailment
            scores = {
                "entailment": probs[2].item(),
                "neutral": probs[1].item(),
                "contradiction": probs[0].item(),
            }
            claim.nli_scores = scores

            # Determine verdict
            max_score = max(scores.values())
            claim.confidence = max_score

            if scores["entailment"] >= self.config.confidence_threshold:
                claim.verdict = ClaimVerdict.SUPPORTED
            elif scores["contradiction"] >= self.config.contradiction_threshold:
                claim.verdict = ClaimVerdict.CONTRADICTED
            else:
                claim.verdict = ClaimVerdict.UNVERIFIABLE

        return claims

    def verify_claims_for_training(
        self,
        hidden_states: torch.Tensor,
        nli_labels: Optional[torch.Tensor] = None,
    ) -> tuple[torch.Tensor, Optional[torch.Tensor]]:
        """
        Training-time NLI verification using the learned NLI head.

        Args:
            hidden_states: [B, H] — CLS-like hidden states for (claim, context) pairs
            nli_labels: [B] — 0=contradiction, 1=neutral, 2=entailment

        Returns:
            (nli_logits, loss)
        """
        logits = self.nli_head(hidden_states)  # [B, 3]

        loss = None
        if nli_labels is not None:
            loss = F.cross_entropy(logits, nli_labels)

        return logits, loss

    # ──────────── Full Pipeline ────────────

    @torch.no_grad()
    def detect(
        self,
        text: str,
        context: str,
        mode: VerificationMode = VerificationMode.FULL,
    ) -> VerificationMessage:
        """
        Full hallucination detection pipeline.

        1. Extract claims from `text`.
        2. Verify each claim against `context`.
        3. Compute aggregate factuality score.
        """
        if mode == VerificationMode.QUICK:
            claims = self._fallback_extract(text)  # fast extraction
        else:
            claims = self.extract_claims(text)

        claims = self.verify_claims(claims, context)

        if mode == VerificationMode.STRICT:
            for c in claims:
                if c.verdict == ClaimVerdict.UNVERIFIABLE:
                    c.verdict = ClaimVerdict.CONTRADICTED

        factuality = compute_factuality_score(claims)

        return VerificationMessage(
            text=text,
            context=context,
            claims=claims,
            mode=mode,
            factuality_score=factuality,
        )

    # ──────────── Save / Load ────────────

    def save_pretrained(self, path: str) -> None:
        """Save detector heads and config."""
        import json
        from pathlib import Path

        save_dir = Path(path)
        save_dir.mkdir(parents=True, exist_ok=True)

        # Save config
        with open(save_dir / "config.json", "w") as f:
            json.dump(self.config.to_dict(), f, indent=2)

        # Save heads
        torch.save(
            {
                "claim_head": self.claim_head.state_dict(),
                "nli_head": self.nli_head.state_dict(),
            },
            save_dir / "heads.pt",
        )

        # Save LoRA adapter
        if self._lora_applied and self.backbone is not None:
            try:
                self.backbone.save_pretrained(str(save_dir / "lora_adapter"))
                logger.info(f"LoRA adapter saved to {save_dir / 'lora_adapter'}")
            except Exception as e:
                logger.warning(f"Failed to save LoRA adapter: {e}")

        logger.info(f"PhirenDetector saved to {save_dir}")

    def trainable_parameters(self) -> list[nn.Parameter]:
        """Return all trainable parameters (LoRA + heads)."""
        params = []
        params.extend(self.claim_head.parameters())
        params.extend(self.nli_head.parameters())
        if self.backbone is not None:
            params.extend(
                p for p in self.backbone.parameters() if p.requires_grad
            )
        return params

    def parameter_count(self) -> dict[str, int]:
        """Count trainable vs total parameters."""
        trainable = sum(p.numel() for p in self.trainable_parameters())
        total = trainable
        if self.backbone is not None:
            total += sum(p.numel() for p in self.backbone.parameters())
        return {"trainable": trainable, "total": total}
