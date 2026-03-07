"""
ogenti-core — AI Telepathy Protocol Core Library

Defines the Ogenti telepathy adapter structure, encoder/decoder interfaces,
and the shared embedding space abstraction used during MARL training
and inference.
"""

__version__ = "0.1.0"

from ogenti_core.protocol import (
    ProtocolMessage,
    MessageType,
    OpCode,
    ProtocolConfig,
)
from ogenti_core.channel import CommunicationChannel, ChannelStats


def __getattr__(name):
    """Lazy imports for modules requiring torch."""
    if name == "OgentiEncoder":
        from ogenti_core.encoder import OgentiEncoder
        return OgentiEncoder
    if name == "EncoderConfig":
        from ogenti_core.encoder import EncoderConfig
        return EncoderConfig
    if name == "OgentiDecoder":
        from ogenti_core.decoder import OgentiDecoder
        return OgentiDecoder
    if name == "DecoderConfig":
        from ogenti_core.decoder import DecoderConfig
        return DecoderConfig
    if name == "DecodedAction":
        from ogenti_core.decoder import DecodedAction
        return DecodedAction
    # ── Universal adapter & interpreter (Phase 4+) ──
    if name == "OgentiAdapter":
        from ogenti_core.adapter import OgentiAdapter
        return OgentiAdapter
    if name == "AdapterConfig":
        from ogenti_core.adapter import AdapterConfig
        return AdapterConfig
    if name == "ProtocolVocab":
        from ogenti_core.adapter import ProtocolVocab
        return ProtocolVocab
    if name == "ProtocolInterpreter":
        from ogenti_core.interpreter import ProtocolInterpreter
        return ProtocolInterpreter
    # ── Telepathy v2 ──
    if name == "TelepathyAdapter":
        from ogenti_core.telepathy_adapter import TelepathyAdapter
        return TelepathyAdapter
    if name == "TelepathyAdapterConfig":
        from ogenti_core.telepathy_adapter import TelepathyAdapterConfig
        return TelepathyAdapterConfig
    if name in ("TextProjector", "VisionProjector", "InjectionHead",
                "TelepathyConfig", "TelepathyMessage", "TelepathyChannel"):
        from ogenti_core import telepathy as _tp
        return getattr(_tp, name)
    raise AttributeError(f"module 'ogenti_core' has no attribute {name!r}")


__all__ = [
    "ProtocolMessage",
    "MessageType",
    "OpCode",
    "ProtocolConfig",
    "OgentiEncoder",
    "EncoderConfig",
    "OgentiDecoder",
    "DecoderConfig",
    "DecodedAction",
    "CommunicationChannel",
    "ChannelStats",
    # Phase 4+ universal adapter
    "OgentiAdapter",
    "AdapterConfig",
    "ProtocolVocab",
    "ProtocolInterpreter",
    # Telepathy v2
    "TelepathyAdapter",
    "TelepathyAdapterConfig",
    "TextProjector",
    "VisionProjector",
    "InjectionHead",
    "TelepathyConfig",
    "TelepathyMessage",
    "TelepathyChannel",
]
