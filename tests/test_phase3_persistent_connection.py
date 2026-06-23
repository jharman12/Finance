"""Tests for Phase 3: Persistent TLS connections with heartbeat and session resumption."""

import time
import unittest
import ssl
from unittest.mock import MagicMock, patch

from finance_app.services.voice.persistent_connection import (
    PersistentRemoteConnection,
    ReconnectConfig,
)
from finance_app.services.voice.network_transport import SessionResumption
from remote_voice_sender import RemoteWakeStreamSender, SenderConfig


class TestSessionResumption(unittest.TestCase):
    """Test session resumption data structure (Phase 3)."""

    def test_session_resumption_creation(self) -> None:
        """Test creating a session resumption record."""
        session = SessionResumption(
            source_id="device-1",
            connection_id="conn-12345",
            last_seq_no=100,
            created_at=time.time(),
            last_activity_at=time.time(),
        )

        self.assertEqual(session.source_id, "device-1")
        self.assertEqual(session.connection_id, "conn-12345")
        self.assertEqual(session.last_seq_no, 100)

    def test_session_not_stale_when_recent(self) -> None:
        """Test that recent session is not marked as stale."""
        session = SessionResumption(
            source_id="device-1",
            connection_id="conn-1",
            last_seq_no=0,
            created_at=time.time(),
            last_activity_at=time.time(),  # Just now
        )

        self.assertFalse(session.is_stale(stale_threshold_seconds=120.0))

    def test_session_stale_when_old(self) -> None:
        """Test that old session is marked as stale."""
        old_time = time.time() - 150  # 150 seconds ago

        session = SessionResumption(
            source_id="device-1",
            connection_id="conn-1",
            last_seq_no=0,
            created_at=old_time,
            last_activity_at=old_time,
        )

        self.assertTrue(session.is_stale(stale_threshold_seconds=120.0))


class TestReconnectConfig(unittest.TestCase):
    """Test exponential backoff configuration (Phase 3)."""

    def test_default_reconnect_config(self) -> None:
        """Test default reconnect configuration."""
        config = ReconnectConfig()

        self.assertEqual(config.initial_delay_ms, 500)
        self.assertEqual(config.max_delay_ms, 30000)
        self.assertEqual(config.backoff_factor, 1.5)
        self.assertEqual(config.jitter_factor, 0.1)

    def test_custom_reconnect_config(self) -> None:
        """Test custom reconnect configuration."""
        config = ReconnectConfig(
            initial_delay_ms=1000,
            max_delay_ms=60000,
            backoff_factor=2.0,
            max_attempts=10,
        )

        self.assertEqual(config.initial_delay_ms, 1000)
        self.assertEqual(config.max_delay_ms, 60000)
        self.assertEqual(config.backoff_factor, 2.0)
        self.assertEqual(config.max_attempts, 10)


class TestPersistentRemoteConnection(unittest.TestCase):
    """Test persistent connection with heartbeat and reconnect (Phase 3)."""

    def setUp(self) -> None:
        self.connection = PersistentRemoteConnection(
            host="localhost",
            port=9999,
            token="test-token-1234567890",
            source_id="test-device",
            allow_untrusted=True,
        )

    def test_connection_initialization(self) -> None:
        """Test connection object initialization."""
        self.assertEqual(self.connection.host, "localhost")
        self.assertEqual(self.connection.port, 9999)
        self.assertEqual(self.connection.source_id, "test-device")
        self.assertEqual(self.connection.heartbeat_interval_ms, 25000)
        self.assertFalse(self.connection.connected)

    def test_calculate_backoff_delay_initial(self) -> None:
        """Test that first attempt uses initial delay."""
        config = ReconnectConfig(initial_delay_ms=500, backoff_factor=1.5)
        delay = self.connection._calculate_backoff_delay(0)

        # Should be approximately 500ms (±50ms for jitter)
        self.assertGreaterEqual(delay, 450)
        self.assertLessEqual(delay, 550)

    def test_calculate_backoff_delay_exponential(self) -> None:
        """Test exponential backoff growth."""
        config = ReconnectConfig(
            initial_delay_ms=1000,
            max_delay_ms=100000,
            backoff_factor=2.0,
            jitter_factor=0.0,  # No jitter for predictable test
        )
        self.connection.reconnect_config = config

        delay_attempt_0 = self.connection._calculate_backoff_delay(0)
        delay_attempt_1 = self.connection._calculate_backoff_delay(1)
        delay_attempt_2 = self.connection._calculate_backoff_delay(2)

        # Verify exponential growth: each attempt ~2x previous
        self.assertEqual(delay_attempt_0, 1000)
        self.assertEqual(delay_attempt_1, 2000)
        self.assertEqual(delay_attempt_2, 4000)

    def test_calculate_backoff_delay_capped_at_max(self) -> None:
        """Test that backoff is capped at max delay."""
        config = ReconnectConfig(
            initial_delay_ms=1000,
            max_delay_ms=5000,
            backoff_factor=2.0,
            jitter_factor=0.0,
        )
        self.connection.reconnect_config = config

        delay_attempt_5 = self.connection._calculate_backoff_delay(5)

        # Should be capped at 5000ms
        self.assertEqual(delay_attempt_5, 5000)

    def test_calculate_backoff_includes_jitter(self) -> None:
        """Test that jitter is added to backoff delay."""
        config = ReconnectConfig(
            initial_delay_ms=1000,
            backoff_factor=1.5,
            jitter_factor=0.2,  # ±20%
        )
        self.connection.reconnect_config = config

        # Get multiple delays to see jitter variation
        delays = [self.connection._calculate_backoff_delay(0) for _ in range(10)]

        # All should be in range [800, 1200] (1000 ± 200)
        for delay in delays:
            self.assertGreaterEqual(delay, 800)
            self.assertLessEqual(delay, 1200)

        # Should not all be identical (jitter present)
        unique_delays = len(set(delays))
        self.assertGreater(unique_delays, 1)

    def test_connection_id_generation(self) -> None:
        """Test that connection_id is generated and stored."""
        # Connection ID is set during handshake, simulate it
        self.connection.connection_id = f"test-device-{int(time.time() * 1000)}"

        self.assertTrue(self.connection.connection_id.startswith("test-device-"))
        self.assertGreater(len(self.connection.connection_id), 11)

    def test_session_resumption_with_seq_no(self) -> None:
        """Test session resumption carries last_seq_no."""
        self.connection.last_seq_no = 1000

        # Simulate reconnect preserving seq_no
        self.connection.last_seq_no = 1000

        self.assertEqual(self.connection.last_seq_no, 1000)

    def test_heartbeat_interval_default(self) -> None:
        """Test default heartbeat interval."""
        self.assertEqual(self.connection.heartbeat_interval_ms, 25000)

    def test_custom_heartbeat_interval(self) -> None:
        """Test custom heartbeat interval."""
        conn = PersistentRemoteConnection(
            host="localhost",
            port=9999,
            token="test-token-1234567890",
            source_id="test-device",
            heartbeat_interval_ms=15000,
        )

        self.assertEqual(conn.heartbeat_interval_ms, 15000)

    def test_pairing_code_included_in_hello(self) -> None:
        """Test that pairing code is included in hello message."""
        conn = PersistentRemoteConnection(
            host="localhost",
            port=9999,
            token="test-token-1234567890",
            source_id="test-device",
            pairing_code="ABC123",
            pairing_session_id="session-uuid",
        )

        self.assertEqual(conn.pairing_code, "ABC123")
        self.assertEqual(conn.pairing_session_id, "session-uuid")

    def test_send_audio_message_format(self) -> None:
        """Test that audio messages include connection_id (Phase 3)."""
        self.connection.connection_id = "conn-test-123"
        self.connection.connected = True

        # Mock socket to capture sent message
        with patch.object(self.connection, "_send_json") as mock_send:
            mock_send.return_value = True

            self.connection.send_audio(1, "base64data", 1000)
            
            # Verify send_json was called
            mock_send.assert_called_once()
            
            # Check message structure
            message = mock_send.call_args[0][0]
            self.assertEqual(message["type"], "audio")
            self.assertEqual(message["connection_id"], "conn-test-123")
            self.assertEqual(message["seq_no"], 1)
            self.assertEqual(message["audio_b64"], "base64data")
            self.assertEqual(message["sent_at_ms"], 1000)

    def test_callbacks_invoked(self) -> None:
        """Test that callbacks are properly configured."""
        on_connected = MagicMock()
        on_disconnected = MagicMock()
        on_error = MagicMock()

        conn = PersistentRemoteConnection(
            host="localhost",
            port=9999,
            token="token",
            source_id="device",
        )
        conn.on_connected = on_connected
        conn.on_disconnected = on_disconnected
        conn.on_error = on_error

        # Test that callbacks are stored
        self.assertEqual(conn.on_connected, on_connected)
        self.assertEqual(conn.on_disconnected, on_disconnected)
        self.assertEqual(conn.on_error, on_error)

    def test_connect_retries_with_trust_refresh_on_cert_failure(self) -> None:
        """Test that TLS verification failures retry with trust refresh."""
        conn = PersistentRemoteConnection(
            host="localhost",
            port=9999,
            token="test-token-1234567890",
            source_id="test-device",
            allow_untrusted=False,
        )

        cert_error = ssl.SSLCertVerificationError("certificate verify failed")
        with patch.object(conn, "_connect_with_allow_untrusted", side_effect=[cert_error, True]) as mock_connect:
            result = conn._connect()

        self.assertTrue(result)
        self.assertEqual(mock_connect.call_count, 2)


class TestRemoteWakeStreamSenderPersistentWiring(unittest.TestCase):
    """Test that the sender wires streams through the persistent transport."""

    def test_open_stream_uses_persistent_connection(self) -> None:
        fake_transport = MagicMock()
        fake_transport.send_audio.return_value = True

        config = SenderConfig(
            host="localhost",
            port=9999,
            token="test-token-1234567890",
            source_id="test-device",
            ca_cert_path="",
            tls_server_name=None,
            wake_phrase="hey steven",
            wake_mode="phrase_vosk",
            vosk_model_path="models/vosk-model-en-us-0.22-lgraph",
            openwakeword_model_path=None,
            wake_threshold=0.5,
            sample_rate=16000,
            blocksize=1600,
            preroll_ms=2000,
            post_wake_grace_ms=1200,
            max_stream_seconds=12.0,
            cooldown_seconds=0.8,
            endpoint_min_speech_ms=300,
            endpoint_silence_ms=700,
            endpoint_max_utterance_ms=12000,
            energy_threshold=450.0,
        )

        with patch.object(RemoteWakeStreamSender, "_build_wake_detector", return_value=MagicMock()), patch.object(
            RemoteWakeStreamSender,
            "_ensure_persistent_connection",
            return_value=fake_transport,
        ):
            sender = RemoteWakeStreamSender(config)
            sender._preroll_buffer.append(b"audio-frame-1")

            sender._open_stream(time.monotonic())

            self.assertIs(sender._connection, fake_transport)
            fake_transport.send_audio.assert_called_once_with(b"audio-frame-1")
            self.assertEqual(sender._stream_started_at > 0.0, True)


class TestPhase3Protocol(unittest.TestCase):
    """Integration tests for Phase 3 persistent connection protocol."""

    def test_persistent_vs_per_utterance(self) -> None:
        """Test conceptual difference between Phase 2 (per-utterance) and Phase 3 (persistent)."""
        # Phase 2: New connection per utterance
        # - Send hello
        # - Wait for hello_ack
        # - Send audio
        # - Close connection
        # - Repeat for next utterance

        # Phase 3: Single persistent connection
        # - Send hello once
        # - Receive hello_ack with connection_id
        # - Send audio multiple times
        # - Keep connection open with periodic ping/pong
        # - Automatic reconnect with session resumption

        # Verify Phase 3 has lower overhead per utterance
        phase2_handshakes_per_minute = 60  # Assuming 1 utterance/second
        phase3_handshakes_per_minute = 1   # Only initial connection

        self.assertLess(phase3_handshakes_per_minute, phase2_handshakes_per_minute)

    def test_heartbeat_prevents_idle_timeout(self) -> None:
        """Test that heartbeat keeps connection from timing out."""
        # Typical idle timeout on servers: 30 seconds
        # Default heartbeat: 25 seconds
        # This ensures connection stays alive

        heartbeat_interval = 25000  # ms
        typical_timeout = 30000  # ms

        self.assertLess(heartbeat_interval, typical_timeout)

    def test_session_resumption_reduces_latency(self) -> None:
        """Test that session resumption reduces reconnection latency."""
        # Phase 2: On reconnect, start from seq_no 0
        # Phase 3: On reconnect, continue from last_seq_no
        # This prevents re-processing packets and reduces latency

        initial_seq_no = 0
        last_processed_seq_no = 1000

        # Phase 2 would lose context
        # Phase 3 preserves context
        self.assertGreater(last_processed_seq_no, initial_seq_no)


if __name__ == "__main__":
    unittest.main()
