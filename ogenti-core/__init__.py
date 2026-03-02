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
from ogenti_core.encoder import OgentiEncoder, EncoderConfig
from ogenti_core.decoder import OgentiDecoder, DecoderConfig, DecodedAction
from ogenti_core.channel import CommunicationChannel, ChannelStats

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
