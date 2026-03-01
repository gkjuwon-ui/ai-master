"""
test_channel.py ??Unit tests for communication channel.
"""

import pytest
from ogenti_core.channel import CommunicationChannel, ChannelStats
from ogenti_core.protocol import ProtocolMessage, ProtocolConfig, MessageType


class TestCommunicationChannel:
    def test_basic_send(self):
        cfg = ProtocolConfig(max_message_tokens=30)
        channel = CommunicationChannel(cfg)

        received = []
        channel.register("agent_1", lambda m: received.append(m))

        msg = ProtocolMessage(
            token_ids=[1, 2, 3],
            sender_id="agent_0",
            receiver_id="agent_1",
        )
        result = channel.send(msg, original_nl_tokens=50)

        assert result is True
        assert len(received) == 1
        assert channel.stats.messages_sent == 1

    def test_budget_violation(self):
        cfg = ProtocolConfig(max_message_tokens=5)
        channel = CommunicationChannel(cfg)

        msg = ProtocolMessage(
            token_ids=list(range(10)),  # 10 tokens > budget 5
            sender_id="agent_0",
            receiver_id="agent_1",
        )
        result = channel.send(msg)

        assert result is False
        assert channel.stats.messages_dropped == 1

    def test_broadcast(self):
        cfg = ProtocolConfig(max_message_tokens=30)
        channel = CommunicationChannel(cfg)

        msgs_a = []
        msgs_b = []
        channel.register("agent_a", lambda m: msgs_a.append(m))
        channel.register("agent_b", lambda m: msgs_b.append(m))

        msg = ProtocolMessage(
            token_ids=[1, 2],
            sender_id="agent_0",
        )
        delivered = channel.broadcast(msg)

        assert delivered == 2
        assert len(msgs_a) == 1
        assert len(msgs_b) == 1

    def test_history(self):
        channel = CommunicationChannel()
        msg = ProtocolMessage(token_ids=[1], sender_id="a", receiver_id="b")
        channel.send(msg)

        assert len(channel.history) == 1

    def test_reset(self):
        channel = CommunicationChannel()
        msg = ProtocolMessage(token_ids=[1], sender_id="a")
        channel.send(msg)
        channel.reset()

        assert len(channel.history) == 0
        assert channel.stats.messages_sent == 0

    def test_hook_rejection(self):
        channel = CommunicationChannel()
        channel.register("b", lambda m: None)

        # Hook that rejects all messages
        channel.add_hook(lambda m: None)

        msg = ProtocolMessage(token_ids=[1], sender_id="a", receiver_id="b")
        result = channel.send(msg)

        assert result is False
        assert channel.stats.messages_dropped == 1

    def test_conversation_filter(self):
        channel = CommunicationChannel()
        channel.register("a", lambda m: None)
        channel.register("b", lambda m: None)

        channel.send(ProtocolMessage(token_ids=[1], sender_id="a", receiver_id="b"))
        channel.send(ProtocolMessage(token_ids=[2], sender_id="b", receiver_id="a"))
        channel.send(ProtocolMessage(token_ids=[3], sender_id="c", receiver_id="a"))

        convo = channel.get_conversation("a", "b")
        assert len(convo) == 2


class TestChannelStats:
    def test_compression(self):
        stats = ChannelStats(
            messages_sent=10,
            total_tokens_transmitted=100,
            total_original_tokens=1500,
        )
        assert stats.compression_ratio == 15.0

    def test_drop_rate(self):
        stats = ChannelStats(messages_sent=8, messages_dropped=2)
        assert stats.drop_rate == 0.2
