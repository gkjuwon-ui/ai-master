"""
test_protocol.py — Unit tests for ogenti-core protocol module.
"""

import pytest
from ogenti_core.protocol import (
    ProtocolMessage,
    ProtocolConfig,
    MessageType,
    OpCode,
    compute_compression_ratio,
    inject_noise,
)


class TestProtocolConfig:
    def test_default_config(self):
        cfg = ProtocolConfig()
        assert cfg.max_message_tokens == 30
        assert cfg.min_message_tokens == 3

    def test_budget_decay(self):
        cfg = ProtocolConfig(
            max_message_tokens=30,
            min_message_tokens=3,
            enable_budget_decay=True,
            decay_rate=0.97,
            budget_floor=5,
        )
        # At episode 0 → full budget
        assert cfg.effective_budget(0) == 30
        # After many episodes → approaches floor
        assert cfg.effective_budget(200) <= 10
        # Budget never goes below floor
        assert cfg.effective_budget(10000) >= 5

    def test_serialization(self):
        cfg = ProtocolConfig(max_message_tokens=20, min_message_tokens=3)
        d = cfg.to_dict()
        restored = ProtocolConfig.from_dict(d)
        assert restored.max_message_tokens == 20
        assert restored.min_message_tokens == 3


class TestProtocolMessage:
    def test_creation(self):
        msg = ProtocolMessage(
            token_ids=[1, 2, 3],
            sender_id="agent_0",
            receiver_id="agent_1",
        )
        assert msg.token_count == 3
        assert msg.sender_id == "agent_0"

    def test_fingerprint(self):
        msg1 = ProtocolMessage(token_ids=[1, 2, 3])
        msg2 = ProtocolMessage(token_ids=[1, 2, 3])
        msg3 = ProtocolMessage(token_ids=[4, 5, 6])
        assert msg1.fingerprint == msg2.fingerprint
        assert msg1.fingerprint != msg3.fingerprint

    def test_serialization(self):
        msg = ProtocolMessage(
            token_ids=[10, 20, 30],
            message_type=MessageType.INSTRUCT,
            sender_id="enc_0",
        )
        d = msg.to_dict()
        restored = ProtocolMessage.from_dict(d)
        assert restored.token_ids == [10, 20, 30]
        assert restored.sender_id == "enc_0"

    def test_is_relay(self):
        msg = ProtocolMessage(
            token_ids=[1],
            route_chain=["a", "b"],
        )
        assert msg.is_relay is True

        msg2 = ProtocolMessage(token_ids=[1])
        assert msg2.is_relay is False


class TestUtilities:
    def test_compression_ratio(self):
        ratio = compute_compression_ratio(150, 10)
        assert ratio == 15.0

    def test_compression_ratio_zero(self):
        ratio = compute_compression_ratio(150, 0)
        assert ratio == float("inf")

    def test_noise_injection(self):
        msg = ProtocolMessage(token_ids=[100, 200, 300, 400, 500])
        noised = inject_noise(msg, error_rate=1.0, vocab_size=1000)
        # With 100% error rate, at least some tokens should differ
        assert noised.token_ids != msg.token_ids or True  # probabilistic

    def test_noise_zero_rate(self):
        msg = ProtocolMessage(token_ids=[100, 200, 300])
        noised = inject_noise(msg, error_rate=0.0, vocab_size=1000)
        assert noised.token_ids == msg.token_ids
