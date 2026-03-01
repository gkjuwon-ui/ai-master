"""
interpreter.py — Protocol Interpreter & Analyzer

Standalone module that translates between Ogenti protocol tokens
and human-readable representations. Also provides real-time
analysis of protocol efficiency, pattern detection, and
vocabulary statistics.

This is the "Rosetta Stone" of the Ogenti protocol — it lets
humans understand what agents are saying to each other, and
enables debugging, monitoring, and protocol auditing.

Usage
─────
  # Create from trained adapter
  interpreter = ProtocolInterpreter.from_adapter(adapter)
  
  # Or load standalone
  interpreter = ProtocolInterpreter.load("ogenti/protocol-v1")
  
  # Translate protocol → human readable
  readable = interpreter.translate([7, 42, 3, 67, 22])
  # → "BEGIN_CTX → SUMMARIZE → KEY_POINTS → ENUMERATE → END_RESPONSE"
  
  # Analyze a conversation
  analysis = interpreter.analyze_session(messages)
  # → compression stats, pattern frequency, vocabulary coverage
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
#  Token Definition
# ─────────────────────────────────────────────────────────────────

@dataclass
class TokenDefinition:
    """Definition of a single protocol token."""
    token_id: int
    symbol: str            # short symbol: "SUM", "CMP", "BEG"
    meaning: str           # full meaning: "summarize"
    category: str          # struct | op | rel | mod | semantic | meta
    description: str = ""  # human-readable description
    
    # Usage statistics
    frequency: int = 0
    co_occurs_with: list[int] = field(default_factory=list)
    avg_position: float = 0.0  # average position in messages


# ─────────────────────────────────────────────────────────────────
#  Built-in Protocol Vocabulary
# ─────────────────────────────────────────────────────────────────

# Standard protocol tokens discovered during training
STANDARD_VOCAB: dict[int, TokenDefinition] = {
    # ── Structural tokens ──
    7:  TokenDefinition(7,  "BEG", "begin-ctx",     "struct", "Start of context/instruction"),
    22: TokenDefinition(22, "END", "end-response",  "struct", "End of response sequence"),
    1:  TokenDefinition(1,  "SEP", "separator",     "struct", "Segment separator"),
    15: TokenDefinition(15, "ACK", "ack",           "struct", "Acknowledgement"),
    
    # ── Operation tokens ──
    42: TokenDefinition(42, "SUM", "summarize",     "op", "Summarize content"),
    87: TokenDefinition(87, "CMP", "compare",       "op", "Compare two or more items"),
    91: TokenDefinition(91, "EXT", "extract",       "op", "Extract specific information"),
    3:  TokenDefinition(3,  "KEY", "key-points",    "op", "Identify key points"),
    67: TokenDefinition(67, "ENM", "enumerate",     "op", "List/enumerate items"),
    45: TokenDefinition(45, "ANL", "analyze",       "op", "Perform analysis"),
    55: TokenDefinition(55, "AGG", "aggregate",     "op", "Aggregate/combine data"),
    30: TokenDefinition(30, "TRN", "transform",     "op", "Transform data format"),
    
    # ── Relational tokens ──
    33: TokenDefinition(33, "CAU", "causal-link",   "rel", "Causal relationship"),
    14: TokenDefinition(14, "CTR", "contrast",      "rel", "Contrast/opposition"),
    
    # ── Modifier tokens ──
    200: TokenDefinition(200, "TMP", "temporal",     "mod", "Time-related modifier"),
    8:   TokenDefinition(8,   "QNT", "quantitative", "mod", "Numeric/quantitative modifier"),
    
    # ── Semantic tokens ──
    77:  TokenDefinition(77,  "T↑",  "trend-up",      "semantic", "Upward trend"),
    78:  TokenDefinition(78,  "T↓",  "trend-down",    "semantic", "Downward trend"),
    120: TokenDefinition(120, "ENT", "entity-ref",    "semantic", "Entity reference"),
    156: TokenDefinition(156, "S+",  "sentiment-pos", "semantic", "Positive sentiment"),
    
    # ── Meta tokens ──
    99:  TokenDefinition(99,  "C↑",  "confidence-hi", "meta", "High confidence"),
    100: TokenDefinition(100, "C↓",  "confidence-lo", "meta", "Low confidence"),
    250: TokenDefinition(250, "UNC", "uncertainty",   "meta", "Uncertainty marker"),
    11:  TokenDefinition(11,  "GLB", "scope-global",  "meta", "Global scope marker"),
}


# ─────────────────────────────────────────────────────────────────
#  Message Analysis Result
# ─────────────────────────────────────────────────────────────────

@dataclass
class MessageAnalysis:
    """Analysis of a single protocol message."""
    token_ids: list[int]
    human_readable: str
    symbols: list[str]
    categories: dict[str, int]  # category → count
    known_ratio: float          # fraction of tokens with known meaning
    structure_score: float      # 0-1: how well-structured the message is
    estimated_intent: str       # best-guess human intent


@dataclass
class SessionAnalysis:
    """Analysis of a full communication session."""
    total_messages: int
    total_tokens: int
    unique_tokens: int
    avg_message_length: float
    compression_ratio: float
    
    # Pattern analysis
    most_common_tokens: list[tuple[int, str, int]]  # (id, meaning, count)
    most_common_bigrams: list[tuple[str, int]]       # (pair, count)
    category_distribution: dict[str, float]           # category → percentage
    
    # Quality metrics
    vocabulary_coverage: float    # fraction of known vocab used
    structural_consistency: float # how consistent message structure is
    
    # Cross-model compatibility score (0-1)
    universality_score: float


# ─────────────────────────────────────────────────────────────────
#  Protocol Interpreter
# ─────────────────────────────────────────────────────────────────

class ProtocolInterpreter:
    """
    Translates, analyzes, and monitors Ogenti protocol messages.
    
    The interpreter serves multiple roles:
    
    1. **Translator**: Convert protocol token IDs ↔ human-readable text
    2. **Analyzer**: Compute statistics on protocol usage patterns
    3. **Monitor**: Real-time protocol health and efficiency tracking
    4. **Debugger**: Help engineers understand what agents communicate
    5. **Auditor**: Verify protocol consistency across model pairs
    
    The interpreter is model-agnostic — it works with the shared
    protocol vocabulary regardless of which models produced the tokens.
    """
    
    def __init__(self, vocab: Optional[dict[int, TokenDefinition]] = None):
        self.vocab = vocab or dict(STANDARD_VOCAB)
        self._history: list[list[int]] = []
        self._bigram_counter = Counter()
        self._token_counter = Counter()
        self._position_sums: dict[int, tuple[float, int]] = defaultdict(lambda: (0.0, 0))
    
    # ── Core Translation ───────────────────────────────────────

    def translate(
        self,
        token_ids: list[int],
        style: str = "symbols",
    ) -> str:
        """
        Translate protocol token IDs to human-readable format.
        
        Args:
            token_ids: List of protocol token IDs
            style: Output format
                   "symbols"  → "BEG → SUM → KEY → ENM → END"
                   "meanings" → "begin-ctx → summarize → key-points → enumerate → end-response"
                   "full"     → "[7:BEG:struct] [42:SUM:op] [3:KEY:op] [67:ENM:op] [22:END:struct]"
                   "natural"  → "Begin context, then summarize, extracting key points as enumerated list"
        Returns:
            Human-readable string
        """
        if style == "symbols":
            parts = [self._token_symbol(tid) for tid in token_ids]
            return " → ".join(parts)
        
        elif style == "meanings":
            parts = [self._token_meaning(tid) for tid in token_ids]
            return " → ".join(parts)
        
        elif style == "full":
            parts = []
            for tid in token_ids:
                defn = self.vocab.get(tid)
                if defn:
                    parts.append(f"[{tid}:{defn.symbol}:{defn.category}]")
                else:
                    parts.append(f"[{tid}:?:unknown]")
            return " ".join(parts)
        
        elif style == "natural":
            return self._to_natural_language(token_ids)
        
        else:
            raise ValueError(f"Unknown style: {style}")
    
    def _token_symbol(self, tid: int) -> str:
        defn = self.vocab.get(tid)
        return defn.symbol if defn else f"#{tid}"
    
    def _token_meaning(self, tid: int) -> str:
        defn = self.vocab.get(tid)
        return defn.meaning if defn else f"unknown-{tid}"
    
    def _to_natural_language(self, token_ids: list[int]) -> str:
        """Convert token sequence to natural language description."""
        parts = []
        i = 0
        
        while i < len(token_ids):
            tid = token_ids[i]
            defn = self.vocab.get(tid)
            
            if defn is None:
                parts.append(f"[token {tid}]")
            elif defn.category == "struct":
                if defn.meaning == "begin-ctx":
                    parts.append("Begin instruction:")
                elif defn.meaning == "end-response":
                    parts.append("(end)")
                elif defn.meaning == "separator":
                    parts.append("|")
                elif defn.meaning == "ack":
                    parts.append("(acknowledged)")
            elif defn.category == "op":
                parts.append(defn.meaning.replace("-", " "))
            elif defn.category == "rel":
                parts.append(f"with {defn.meaning.replace('-', ' ')}")
            elif defn.category == "mod":
                parts.append(f"({defn.meaning})")
            elif defn.category == "semantic":
                parts.append(defn.meaning.replace("-", " "))
            elif defn.category == "meta":
                parts.append(f"[{defn.meaning}]")
            
            i += 1
        
        return " ".join(parts)
    
    # ── Message Analysis ───────────────────────────────────────

    def analyze_message(self, token_ids: list[int]) -> MessageAnalysis:
        """Analyze a single protocol message."""
        symbols = [self._token_symbol(tid) for tid in token_ids]
        
        # Category distribution
        categories = Counter()
        known = 0
        for tid in token_ids:
            defn = self.vocab.get(tid)
            if defn:
                categories[defn.category] += 1
                known += 1
            else:
                categories["unknown"] += 1
        
        known_ratio = known / len(token_ids) if token_ids else 0
        
        # Structure score: does it follow BEG...END pattern?
        has_begin = any(
            self.vocab.get(t) and self.vocab[t].meaning == "begin-ctx"
            for t in token_ids[:3]
        )
        has_end = any(
            self.vocab.get(t) and self.vocab[t].meaning == "end-response"
            for t in token_ids[-3:]
        )
        has_ops = categories.get("op", 0) > 0
        structure_score = (
            (0.3 if has_begin else 0) +
            (0.3 if has_end else 0) +
            (0.2 if has_ops else 0) +
            (0.2 * known_ratio)
        )
        
        # Estimate intent
        estimated_intent = self._estimate_intent(token_ids)
        
        return MessageAnalysis(
            token_ids=token_ids,
            human_readable=self.translate(token_ids, "symbols"),
            symbols=symbols,
            categories=dict(categories),
            known_ratio=known_ratio,
            structure_score=structure_score,
            estimated_intent=estimated_intent,
        )
    
    def _estimate_intent(self, token_ids: list[int]) -> str:
        """Best-guess intent from operation tokens."""
        ops = []
        for tid in token_ids:
            defn = self.vocab.get(tid)
            if defn and defn.category == "op":
                ops.append(defn.meaning)
        
        if not ops:
            return "unknown"
        
        # Map to high-level intent
        intent_map = {
            "summarize": "Summarize content",
            "compare": "Compare items",
            "extract": "Extract information",
            "key-points": "Identify key points",
            "enumerate": "List items",
            "analyze": "Analyze data",
            "aggregate": "Combine data",
            "transform": "Transform format",
        }
        
        primary = ops[0]
        base_intent = intent_map.get(primary, primary)
        
        if len(ops) > 1:
            secondary = [intent_map.get(op, op) for op in ops[1:]]
            return f"{base_intent}, then {', '.join(secondary)}"
        
        return base_intent
    
    # ── Session Analysis ───────────────────────────────────────

    def record(self, token_ids: list[int]) -> None:
        """Record a message for ongoing session analysis."""
        self._history.append(token_ids)
        
        # Update counters
        for i, tid in enumerate(token_ids):
            self._token_counter[tid] += 1
            total, count = self._position_sums[tid]
            self._position_sums[tid] = (total + i, count + 1)
            
            if i > 0:
                bigram = (token_ids[i - 1], tid)
                self._bigram_counter[bigram] += 1
    
    def analyze_session(
        self,
        messages: Optional[list[list[int]]] = None,
        original_token_counts: Optional[list[int]] = None,
    ) -> SessionAnalysis:
        """
        Analyze a full communication session.
        
        Args:
            messages: List of token ID sequences (or use recorded history)
            original_token_counts: Original NL token counts for compression ratio
        Returns:
            SessionAnalysis with comprehensive statistics
        """
        msgs = messages or self._history
        if not msgs:
            return SessionAnalysis(
                total_messages=0, total_tokens=0, unique_tokens=0,
                avg_message_length=0, compression_ratio=1.0,
                most_common_tokens=[], most_common_bigrams=[],
                category_distribution={}, vocabulary_coverage=0,
                structural_consistency=0, universality_score=0,
            )
        
        all_tokens = [tid for msg in msgs for tid in msg]
        token_counts = Counter(all_tokens)
        
        # Basic stats
        total_messages = len(msgs)
        total_tokens = len(all_tokens)
        unique_tokens = len(token_counts)
        avg_length = total_tokens / total_messages
        
        # Compression
        if original_token_counts:
            orig_total = sum(original_token_counts)
            compression = orig_total / total_tokens if total_tokens else 1.0
        else:
            compression = 0.0  # unknown
        
        # Most common tokens
        most_common = []
        for tid, count in token_counts.most_common(10):
            meaning = self._token_meaning(tid)
            most_common.append((tid, meaning, count))
        
        # Most common bigrams
        bigrams = Counter()
        for msg in msgs:
            for i in range(len(msg) - 1):
                pair = f"{self._token_symbol(msg[i])}→{self._token_symbol(msg[i+1])}"
                bigrams[pair] += 1
        most_common_bigrams = bigrams.most_common(10)
        
        # Category distribution
        cat_counter = Counter()
        for tid in all_tokens:
            defn = self.vocab.get(tid)
            cat_counter[defn.category if defn else "unknown"] += 1
        cat_total = sum(cat_counter.values())
        cat_dist = {k: v / cat_total for k, v in cat_counter.items()}
        
        # Vocabulary coverage
        known_tokens = sum(1 for tid in unique_tokens.__class__(token_counts.keys()) if tid in self.vocab)
        vocab_coverage = known_tokens / len(self.vocab) if self.vocab else 0
        
        # Structural consistency
        consistencies = []
        for msg in msgs:
            analysis = self.analyze_message(msg)
            consistencies.append(analysis.structure_score)
        structural_consistency = sum(consistencies) / len(consistencies) if consistencies else 0
        
        # Universality score
        # Higher = more reliant on known protocol tokens (model-agnostic)
        known_usage = sum(1 for tid in all_tokens if tid in self.vocab)
        universality = known_usage / total_tokens if total_tokens else 0
        
        return SessionAnalysis(
            total_messages=total_messages,
            total_tokens=total_tokens,
            unique_tokens=unique_tokens,
            avg_message_length=avg_length,
            compression_ratio=compression,
            most_common_tokens=most_common,
            most_common_bigrams=most_common_bigrams,
            category_distribution=cat_dist,
            vocabulary_coverage=vocab_coverage,
            structural_consistency=structural_consistency,
            universality_score=universality,
        )
    
    # ── Compatibility Check ────────────────────────────────────

    def check_compatibility(
        self,
        model_a_messages: list[list[int]],
        model_b_messages: list[list[int]],
    ) -> dict:
        """
        Check protocol compatibility between two model pairs.
        
        Verifies that Model A and Model B use the protocol vocabulary
        consistently — same tokens for same operations, similar
        message structures, compatible encoding patterns.
        
        Args:
            model_a_messages: Messages produced by Model A's adapter
            model_b_messages: Messages produced by Model B's adapter
        Returns:
            dict with compatibility metrics
        """
        vocab_a = set(tid for msg in model_a_messages for tid in msg)
        vocab_b = set(tid for msg in model_b_messages for tid in msg)
        
        overlap = vocab_a & vocab_b
        union = vocab_a | vocab_b
        jaccard = len(overlap) / len(union) if union else 0
        
        # Category distribution similarity
        def cat_dist(messages):
            cats = Counter()
            for msg in messages:
                for tid in msg:
                    defn = self.vocab.get(tid)
                    cats[defn.category if defn else "unknown"] += 1
            total = sum(cats.values())
            return {k: v / total for k, v in cats.items()} if total else {}
        
        dist_a = cat_dist(model_a_messages)
        dist_b = cat_dist(model_b_messages)
        
        all_cats = set(dist_a) | set(dist_b)
        cosine_sim = 0
        if all_cats:
            dot = sum(dist_a.get(c, 0) * dist_b.get(c, 0) for c in all_cats)
            norm_a = sum(v ** 2 for v in dist_a.values()) ** 0.5
            norm_b = sum(v ** 2 for v in dist_b.values()) ** 0.5
            cosine_sim = dot / (norm_a * norm_b) if norm_a * norm_b > 0 else 0
        
        # Length distribution similarity
        avg_len_a = sum(len(m) for m in model_a_messages) / len(model_a_messages) if model_a_messages else 0
        avg_len_b = sum(len(m) for m in model_b_messages) / len(model_b_messages) if model_b_messages else 0
        len_ratio = min(avg_len_a, avg_len_b) / max(avg_len_a, avg_len_b) if max(avg_len_a, avg_len_b) > 0 else 1
        
        compatibility = (
            0.4 * jaccard +
            0.3 * cosine_sim +
            0.2 * len_ratio +
            0.1  # base score for using the protocol at all
        )
        
        return {
            "compatible": compatibility > 0.6,
            "score": round(compatibility, 3),
            "vocab_overlap_jaccard": round(jaccard, 3),
            "category_similarity": round(cosine_sim, 3),
            "length_ratio": round(len_ratio, 3),
            "shared_tokens": len(overlap),
            "unique_to_a": len(vocab_a - vocab_b),
            "unique_to_b": len(vocab_b - vocab_a),
        }
    
    # ── Persistence ────────────────────────────────────────────

    def save(self, path: Union[str, Path]) -> None:
        path = Path(path)
        data = {
            "vocab": {
                str(tid): asdict(defn)
                for tid, defn in self.vocab.items()
            },
        }
        path.write_text(json.dumps(data, indent=2))
    
    @classmethod
    def load(cls, path: Union[str, Path]) -> "ProtocolInterpreter":
        data = json.loads(Path(path).read_text())
        vocab = {}
        for tid_str, defn_dict in data["vocab"].items():
            tid = int(tid_str)
            vocab[tid] = TokenDefinition(**defn_dict)
        return cls(vocab=vocab)
    
    @classmethod
    def from_adapter(cls, adapter) -> "ProtocolInterpreter":
        """Create interpreter from a trained OgentiAdapter."""
        interpreter = cls()
        
        # Import protocol vocab from adapter
        for entry in adapter.vocab.tokens:
            tid = entry.token_id
            if tid not in interpreter.vocab:
                interpreter.vocab[tid] = TokenDefinition(
                    token_id=tid,
                    symbol=entry.meaning[:3].upper(),
                    meaning=entry.meaning,
                    category=entry.category,
                    frequency=entry.frequency,
                )
            else:
                interpreter.vocab[tid].frequency = entry.frequency
        
        return interpreter
    
    def __repr__(self) -> str:
        return f"ProtocolInterpreter(vocab_size={len(self.vocab)}, history={len(self._history)} msgs)"
