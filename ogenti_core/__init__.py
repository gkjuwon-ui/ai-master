"""
ogenti-core — AI-to-AI Communication Protocol Core Library

Defines the Ogenti protocol structure, encoder/decoder interfaces,
and the communication channel abstraction used during MARL training
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
]
