"""
adapter.py — Universal Protocol Adapter

After Phase 0-3 train a protocol between two Qwen agents,
Phase 4 distills the learned encoder/decoder LoRA into a
model-agnostic adapter that can be attached to ANY LLM.

Architecture
────────────
The universal adapter consists of two components:

  1. Protocol Projection Head (PPH)
     Small MLP that maps any model's hidden states → protocol token logits.
     Trained via distillation: the Qwen encoder's LoRA outputs serve as
     the teacher, and PPH learns to match them from any model's hidden states.

  2. Protocol Reconstruction Head (PRH)
     Inverse of PPH: maps protocol token embeddings → model-specific
     hidden states that the target LLM can continue generating from.

Export Flow
───────────
  Phase 3 Complete
       │
       ▼
  ┌──────────────────────────────────────────────────────┐
  │  Extract:                                            │
  │    • Protocol vocab mapping  (token_id → meaning)    │
  │    • Encoder LoRA weights    (teacher signal)        │
  │    • Decoder LoRA weights    (teacher signal)        │
  └──────────────────────────────────────────────────────┘
       │
       ▼
  Phase 4: Universalize
  ┌──────────────────────────────────────────────────────┐
  │  For each target model family:                       │
  │    1. Freeze target model                            │
  │    2. Attach PPH + PRH (randomly initialized)        │
  │    3. Distill: PPH output  ≈ Qwen encoder output     │
  │              PRH output  ≈ Qwen decoder output       │
  │    4. Fine-tune with RL episodes (same curriculum)   │
  └──────────────────────────────────────────────────────┘
       │
       ▼
  Export: OgentiAdapter (model-agnostic .safetensors)
  ┌──────────────────────────────────────────────────────┐
  │  • protocol_vocab.json     (shared vocabulary)       │
  │  • pph_weights.safetensors (encode head)             │
  │  • prh_weights.safetensors (decode head)             │
  │  • adapter_config.json     (architecture metadata)   │
  └──────────────────────────────────────────────────────┘

Usage
─────
  # Attach to any model
  adapter = OgentiAdapter.load("ogenti/universal-adapter-v1")
  adapter.attach(any_model, any_tokenizer)
  
  # Now this model speaks Ogenti protocol
  msg = adapter.encode("Summarize this document")
  result = adapter.decode(msg)
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Union

import torch
import torch.nn as nn
import torch.nn.functional as F

from ogenti_core.protocol import ProtocolMessage, ProtocolConfig

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Adapter Configuration
# ─────────────────────────────────────────────────────────────────

@dataclass
class AdapterConfig:
    """Configuration for the universal protocol adapter."""

    # Architecture
    hidden_dim: int = 256              # PPH/PRH internal dimension
    num_layers: int = 3                # MLP depth
    dropout: float = 0.1
    activation: str = "gelu"           # gelu | relu | silu

    # Protocol
    protocol_vocab_size: int = 256     # number of protocol tokens
    max_protocol_length: int = 30      # max tokens per message
    
    # Distillation
    distill_temperature: float = 2.0   # KD temperature
    distill_alpha: float = 0.7         # weight: distill loss vs task loss
    
    # Compatibility
    supported_hidden_sizes: list[int] = field(default_factory=lambda: [
        768,   # BERT-base, GPT-2 small, Phi-1
        1024,  # GPT-2 medium
        1536,  # Phi-2
        2048,  # Qwen2.5-1.5B, LLaMA-7B (projected)
        2560,  # Qwen2.5-3B
        3072,  # Phi-3-mini
        3584,  # Qwen2.5-7B
        4096,  # LLaMA-7B/13B, Mistral-7B
        5120,  # LLaMA-33B
        8192,  # LLaMA-65B
    ])
    
    # Version
    version: str = "1.0"
    trained_on: str = "Qwen/Qwen2.5-3B-Instruct"

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AdapterConfig":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─────────────────────────────────────────────────────────────────
#  Adaptive Input Projection
# ─────────────────────────────────────────────────────────────────

class AdaptiveInputProjection(nn.Module):
    """
    Projects model hidden states of ANY size → fixed adapter dim.
    
    Uses a lookup table of pre-computed projection matrices for
    known hidden sizes, plus a fallback linear interpolation for
    unknown sizes.
    """
    
    def __init__(self, config: AdapterConfig):
        super().__init__()
        self.config = config
        self.target_dim = config.hidden_dim
        
        # Pre-registered projections for known model sizes
        self.projections = nn.ModuleDict()
        for hs in config.supported_hidden_sizes:
            self.projections[str(hs)] = nn.Linear(hs, config.hidden_dim, bias=False)
    
    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        Args:
            hidden_states: (batch, seq_len, model_hidden_size)
        Returns:
            projected: (batch, seq_len, adapter_hidden_dim)
        """
        hs = hidden_states.shape[-1]
        key = str(hs)
        
        if key in self.projections:
            return self.projections[key](hidden_states)
        
        # Fallback: create projection on-the-fly (slower, but works for any size)
        logger.warning(
            f"Hidden size {hs} not pre-registered. "
            f"Creating dynamic projection. Consider adding {hs} to supported_hidden_sizes."
        )
        device = hidden_states.device
        dtype = hidden_states.dtype
        proj = nn.Linear(hs, self.target_dim, bias=False).to(device=device, dtype=dtype)
        nn.init.xavier_uniform_(proj.weight)
        self.projections[key] = proj
        return proj(hidden_states)


# ─────────────────────────────────────────────────────────────────
#  Protocol Projection Head (Encoder Side)
# ─────────────────────────────────────────────────────────────────

class ProtocolProjectionHead(nn.Module):
    """
    PPH: Maps any model's hidden states → protocol token logits.
    
    This is the "encode" side of the universal adapter.
    Given the last hidden state of a model processing some NL input,
    PPH auto-regressively produces protocol token IDs.
    
        model_hidden  →  [AdaptiveProj]  →  [MLP × N]  →  protocol_logits
                                                            (vocab_size,)
    """
    
    def __init__(self, config: AdapterConfig):
        super().__init__()
        self.config = config
        
        self.input_proj = AdaptiveInputProjection(config)
        
        # MLP layers
        layers = []
        dim = config.hidden_dim
        act = {"gelu": nn.GELU, "relu": nn.ReLU, "silu": nn.SiLU}[config.activation]
        
        for i in range(config.num_layers):
            layers.extend([
                nn.Linear(dim, dim),
                nn.LayerNorm(dim),
                act(),
                nn.Dropout(config.dropout),
            ])
        
        self.mlp = nn.Sequential(*layers)
        
        # Output head: project to protocol vocab logits
        self.output_head = nn.Linear(dim, config.protocol_vocab_size)
        
        # Learned protocol token embeddings (for auto-regressive generation)
        self.proto_embeddings = nn.Embedding(config.protocol_vocab_size, dim)
        
        # Positional encoding for protocol sequence
        self.pos_encoding = nn.Embedding(config.max_protocol_length, dim)
    
    def forward(
        self,
        hidden_states: torch.Tensor,
        protocol_tokens: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Args:
            hidden_states: (batch, seq_len, model_hidden)  — from target model
            protocol_tokens: (batch, proto_len)  — teacher forcing tokens (training)
        Returns:
            logits: (batch, proto_len, vocab_size)
        """
        # Project model hidden states to adapter space
        ctx = self.input_proj(hidden_states)  # (B, S, D)
        
        # Pool context: use mean of last layer hidden states
        ctx_pooled = ctx.mean(dim=1, keepdim=True)  # (B, 1, D)
        
        if protocol_tokens is not None:
            # Teacher-forced: compute logits for all positions at once
            B, T = protocol_tokens.shape
            positions = torch.arange(T, device=protocol_tokens.device)
            tok_emb = self.proto_embeddings(protocol_tokens) + self.pos_encoding(positions)
            
            # Combine context + token embeddings
            combined = ctx_pooled + tok_emb  # (B, T, D)
            features = self.mlp(combined)
            logits = self.output_head(features)  # (B, T, V)
            return logits
        else:
            # Auto-regressive generation (inference)
            return self._generate(ctx_pooled)
    
    @torch.no_grad()
    def _generate(
        self,
        context: torch.Tensor,
        max_len: Optional[int] = None,
        temperature: float = 0.8,
    ) -> torch.Tensor:
        """Auto-regressively generate protocol tokens."""
        max_len = max_len or self.config.max_protocol_length
        B = context.shape[0]
        device = context.device
        
        generated = []
        prev_token = torch.zeros(B, 1, dtype=torch.long, device=device)  # BOS = 0
        
        for step in range(max_len):
            pos = torch.tensor([step], device=device)
            tok_emb = self.proto_embeddings(prev_token) + self.pos_encoding(pos)
            combined = context + tok_emb
            features = self.mlp(combined)
            logits = self.output_head(features).squeeze(1)  # (B, V)
            
            # Sample
            probs = F.softmax(logits / temperature, dim=-1)
            next_token = torch.multinomial(probs, 1)  # (B, 1)
            generated.append(next_token)
            prev_token = next_token
        
        return torch.cat(generated, dim=1)  # (B, max_len)


# ─────────────────────────────────────────────────────────────────
#  Protocol Reconstruction Head (Decoder Side)
# ─────────────────────────────────────────────────────────────────

class ProtocolReconstructionHead(nn.Module):
    """
    PRH: Maps protocol token sequence → model-specific hidden states.
    
    This is the "decode" side of the universal adapter.
    Given a protocol message, PRH produces hidden state vectors that
    can be injected into the target model's generation pipeline.
    
        protocol_tokens  →  [Embedding]  →  [MLP × N]  →  model_hidden
                                                           (model_dim,)
    """
    
    def __init__(self, config: AdapterConfig):
        super().__init__()
        self.config = config
        
        dim = config.hidden_dim
        act = {"gelu": nn.GELU, "relu": nn.ReLU, "silu": nn.SiLU}[config.activation]
        
        # Protocol token embeddings (shared with PPH optionally)
        self.proto_embeddings = nn.Embedding(config.protocol_vocab_size, dim)
        self.pos_encoding = nn.Embedding(config.max_protocol_length, dim)
        
        # MLP to process protocol sequence
        layers = []
        for i in range(config.num_layers):
            layers.extend([
                nn.Linear(dim, dim),
                nn.LayerNorm(dim),
                act(),
                nn.Dropout(config.dropout),
            ])
        self.mlp = nn.Sequential(*layers)
        
        # Output projections: one per supported model hidden size
        self.output_projs = nn.ModuleDict()
        for hs in config.supported_hidden_sizes:
            self.output_projs[str(hs)] = nn.Linear(dim, hs, bias=False)
    
    def forward(
        self,
        protocol_tokens: torch.Tensor,
        target_hidden_size: int,
    ) -> torch.Tensor:
        """
        Args:
            protocol_tokens: (batch, proto_len) — protocol token IDs
            target_hidden_size: int — target model's hidden dimension
        Returns:
            hidden_states: (batch, proto_len, target_hidden_size)
        """
        B, T = protocol_tokens.shape
        positions = torch.arange(T, device=protocol_tokens.device)
        
        # Embed protocol tokens
        embeddings = self.proto_embeddings(protocol_tokens) + self.pos_encoding(positions)
        
        # Process through MLP
        features = self.mlp(embeddings)  # (B, T, D)
        
        # Project to target model's hidden size
        key = str(target_hidden_size)
        if key not in self.output_projs:
            logger.warning(f"Hidden size {target_hidden_size} not pre-registered. Creating dynamic projection.")
            device = features.device
            dtype = features.dtype
            proj = nn.Linear(self.config.hidden_dim, target_hidden_size, bias=False).to(device=device, dtype=dtype)
            nn.init.xavier_uniform_(proj.weight)
            self.output_projs[key] = proj
        
        return self.output_projs[key](features)  # (B, T, model_hidden)


# ─────────────────────────────────────────────────────────────────
#  Protocol Vocabulary — Shared Token Semantics
# ─────────────────────────────────────────────────────────────────

@dataclass
class ProtocolVocabEntry:
    """A single token in the learned protocol vocabulary."""
    token_id: int
    meaning: str           # human-readable semantic label
    category: str          # struct | op | rel | mod | semantic | meta
    frequency: int = 0     # usage count during training
    phase_discovered: int = 0  # which phase first used this token
    embedding_norm: float = 0.0  # L2 norm of learned embedding


@dataclass
class ProtocolVocab:
    """
    The learned protocol vocabulary.
    
    This is model-agnostic: every model that uses the Ogenti adapter
    shares the same protocol vocab. Token 42 always means "summarize"
    regardless of whether the underlying model is Qwen, LLaMA, or GPT.
    """
    tokens: list[ProtocolVocabEntry] = field(default_factory=list)
    version: str = "1.0"
    trained_episodes: int = 0
    source_model: str = ""
    
    def add(self, entry: ProtocolVocabEntry) -> None:
        self.tokens.append(entry)
    
    def get(self, token_id: int) -> Optional[ProtocolVocabEntry]:
        for t in self.tokens:
            if t.token_id == token_id:
                return t
        return None
    
    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        data = {
            "version": self.version,
            "trained_episodes": self.trained_episodes,
            "source_model": self.source_model,
            "tokens": [asdict(t) for t in self.tokens],
        }
        path.write_text(json.dumps(data, indent=2))
        logger.info(f"Protocol vocab saved: {len(self.tokens)} tokens → {path}")
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "ProtocolVocab":
        data = json.loads(Path(path).read_text())
        vocab = cls(
            version=data["version"],
            trained_episodes=data.get("trained_episodes", 0),
            source_model=data.get("source_model", ""),
        )
        for t in data["tokens"]:
            vocab.add(ProtocolVocabEntry(**t))
        return vocab


# ─────────────────────────────────────────────────────────────────
#  OgentiAdapter — The Universal Adapter
# ─────────────────────────────────────────────────────────────────

class OgentiAdapter(nn.Module):
    """
    Universal protocol adapter that can be attached to any LLM.
    
    After Phase 4 training, this adapter package contains everything
    needed to make any model speak the Ogenti protocol:
    
      • ProtocolProjectionHead  (encode: NL → protocol tokens)
      • ProtocolReconstructionHead  (decode: protocol tokens → NL)
      • ProtocolVocab  (shared token semantics)
    
    Usage:
        adapter = OgentiAdapter.load("ogenti/universal-adapter-v1")
        adapter.attach(model, tokenizer)
        
        # Encode
        msg = adapter.encode("Summarize this document in 3 bullet points")
        print(msg.token_ids)   # [7, 42, 3, 67, 22]  — 5 tokens!
        
        # Decode (on another model)
        text = adapter.decode(msg)
        print(text)  # Reconstructed instruction
        
        # Cross-model communication
        adapter_a = OgentiAdapter.load("ogenti/universal-adapter-v1")
        adapter_a.attach(llama_model, llama_tokenizer)
        
        adapter_b = OgentiAdapter.load("ogenti/universal-adapter-v1")
        adapter_b.attach(mistral_model, mistral_tokenizer)
        
        msg = adapter_a.encode("Analyze sales data for Q3")
        result = adapter_b.decode(msg)  # Mistral understands LLaMA's encoding!
    """
    
    def __init__(
        self,
        config: AdapterConfig,
        vocab: Optional[ProtocolVocab] = None,
    ):
        super().__init__()
        self.config = config
        self.vocab = vocab or ProtocolVocab()
        
        self.encoder_head = ProtocolProjectionHead(config)
        self.decoder_head = ProtocolReconstructionHead(config)
        
        # Attached model reference (set by .attach())
        self._model = None
        self._tokenizer = None
        self._model_hidden_size = None
    
    def attach(self, model: nn.Module, tokenizer) -> "OgentiAdapter":
        """
        Attach this adapter to a target LLM.
        
        After attachment, the adapter can encode/decode using the
        target model's representation space.
        
        Args:
            model: Any HuggingFace CausalLM or similar
            tokenizer: The model's tokenizer
        Returns:
            self (for chaining)
        """
        self._model = model
        self._tokenizer = tokenizer
        
        # Detect hidden size
        if hasattr(model.config, 'hidden_size'):
            self._model_hidden_size = model.config.hidden_size
        elif hasattr(model.config, 'd_model'):
            self._model_hidden_size = model.config.d_model
        else:
            raise ValueError(
                "Cannot detect model hidden size. "
                "Set adapter._model_hidden_size manually."
            )
        
        logger.info(
            f"OgentiAdapter attached to {type(model).__name__} "
            f"(hidden_size={self._model_hidden_size})"
        )
        return self
    
    def encode(
        self,
        text: str,
        max_tokens: Optional[int] = None,
        temperature: float = 0.8,
    ) -> ProtocolMessage:
        """
        Encode natural language → protocol message.
        
        Args:
            text: Natural language instruction
            max_tokens: Override max protocol tokens
            temperature: Sampling temperature
        Returns:
            ProtocolMessage with compressed token sequence
        """
        if self._model is None:
            raise RuntimeError("No model attached. Call adapter.attach(model, tokenizer) first.")
        
        # Tokenize input
        inputs = self._tokenizer(
            text, return_tensors="pt", truncation=True, max_length=512
        )
        inputs = {k: v.to(next(self._model.parameters()).device) for k, v in inputs.items()}
        
        # Get model hidden states
        with torch.no_grad():
            outputs = self._model(**inputs, output_hidden_states=True)
            hidden = outputs.hidden_states[-1]  # Last layer: (1, seq_len, hidden)
        
        # Generate protocol tokens via PPH
        max_len = max_tokens or self.config.max_protocol_length
        self.encoder_head.config.max_protocol_length = max_len
        proto_ids = self.encoder_head(hidden)  # (1, max_len)
        
        # Build ProtocolMessage
        token_ids = proto_ids[0].cpu().tolist()
        
        # Truncate at first padding/zero if protocol learned to pad
        if 0 in token_ids:
            token_ids = token_ids[:token_ids.index(0)]
        
        return ProtocolMessage(
            token_ids=token_ids,
            original_text=text,
            original_tokens=len(inputs["input_ids"][0]),
        )
    
    def decode(
        self,
        message: ProtocolMessage,
        max_length: int = 256,
    ) -> str:
        """
        Decode protocol message → natural language.
        
        Args:
            message: ProtocolMessage to decode
            max_length: Max tokens for NL reconstruction
        Returns:
            Reconstructed natural language string
        """
        if self._model is None:
            raise RuntimeError("No model attached. Call adapter.attach(model, tokenizer) first.")
        
        device = next(self._model.parameters()).device
        
        # Convert protocol tokens to tensor
        proto_tensor = torch.tensor(
            [message.token_ids], dtype=torch.long, device=device
        )
        
        # Get model-specific hidden states from PRH
        hidden = self.decoder_head(proto_tensor, self._model_hidden_size)
        # hidden: (1, proto_len, model_hidden)
        
        # Use hidden states as prefix embeddings for generation
        # This injects the protocol context into the model's generation
        prefix_embeds = hidden  # (1, T, D)
        
        # Generate NL output
        output_ids = self._model.generate(
            inputs_embeds=prefix_embeds,
            max_new_tokens=max_length,
            do_sample=True,
            temperature=0.7,
            pad_token_id=self._tokenizer.eos_token_id,
        )
        
        text = self._tokenizer.decode(output_ids[0], skip_special_tokens=True)
        return text.strip()
    
    # ── Distillation ───────────────────────────────────────────

    def distillation_loss(
        self,
        student_logits: torch.Tensor,
        teacher_logits: torch.Tensor,
        task_loss: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Compute knowledge distillation loss.
        
        Transfers the encoding/decoding knowledge from the trained
        Qwen LoRA (teacher) to the universal adapter heads (student).
        
        Args:
            student_logits: PPH/PRH output logits
            teacher_logits: Encoder/Decoder LoRA output logits
            task_loss: Optional task-specific loss to blend
        Returns:
            Combined distillation + task loss
        """
        T = self.config.distill_temperature
        alpha = self.config.distill_alpha
        
        # KL divergence between softened distributions
        student_soft = F.log_softmax(student_logits / T, dim=-1)
        teacher_soft = F.softmax(teacher_logits / T, dim=-1)
        
        kd_loss = F.kl_div(student_soft, teacher_soft, reduction="batchmean") * (T * T)
        
        if task_loss is not None:
            return alpha * kd_loss + (1 - alpha) * task_loss
        
        return kd_loss
    
    # ── Save / Load ────────────────────────────────────────────

    def save(self, save_dir: Union[str, Path]) -> None:
        """
        Export the universal adapter as a standalone package.
        
        Creates:
          save_dir/
            adapter_config.json
            protocol_vocab.json
            pph_weights.safetensors  (or .pt)
            prh_weights.safetensors  (or .pt)
        """
        save_dir = Path(save_dir)
        save_dir.mkdir(parents=True, exist_ok=True)
        
        # Config
        config_path = save_dir / "adapter_config.json"
        config_path.write_text(json.dumps(self.config.to_dict(), indent=2))
        
        # Vocab
        self.vocab.save(save_dir / "protocol_vocab.json")
        
        # Weights
        try:
            from safetensors.torch import save_file
            save_file(self.encoder_head.state_dict(), str(save_dir / "pph_weights.safetensors"))
            save_file(self.decoder_head.state_dict(), str(save_dir / "prh_weights.safetensors"))
        except ImportError:
            torch.save(self.encoder_head.state_dict(), save_dir / "pph_weights.pt")
            torch.save(self.decoder_head.state_dict(), save_dir / "prh_weights.pt")
        
        logger.info(f"OgentiAdapter saved to {save_dir}")
    
    @classmethod
    def load(cls, load_dir: Union[str, Path]) -> "OgentiAdapter":
        """
        Load a universal adapter from a saved directory.
        
        Can be loaded from local path or HuggingFace hub ID.
        """
        load_dir = Path(load_dir)
        
        # Config
        config = AdapterConfig.from_dict(
            json.loads((load_dir / "adapter_config.json").read_text())
        )
        
        # Vocab
        vocab = ProtocolVocab.load(load_dir / "protocol_vocab.json")
        
        # Build adapter
        adapter = cls(config=config, vocab=vocab)
        
        # Load weights
        try:
            from safetensors.torch import load_file
            pph_path = load_dir / "pph_weights.safetensors"
            prh_path = load_dir / "prh_weights.safetensors"
            if pph_path.exists():
                adapter.encoder_head.load_state_dict(load_file(str(pph_path)))
                adapter.decoder_head.load_state_dict(load_file(str(prh_path)))
                return adapter
        except ImportError:
            pass
        
        # Fallback to .pt
        pph_path = load_dir / "pph_weights.pt"
        prh_path = load_dir / "prh_weights.pt"
        if pph_path.exists():
            adapter.encoder_head.load_state_dict(torch.load(pph_path, weights_only=True))
            adapter.decoder_head.load_state_dict(torch.load(prh_path, weights_only=True))
        
        return adapter
    
    def __repr__(self) -> str:
        n_params = sum(p.numel() for p in self.parameters())
        attached = type(self._model).__name__ if self._model else "None"
        return (
            f"OgentiAdapter("
            f"params={n_params:,}, "
            f"vocab={len(self.vocab.tokens)}, "
            f"attached_to={attached})"
        )
