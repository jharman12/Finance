"""Tests for Phase 2: Robust pairing protocol with session IDs and HMAC codes."""

import hashlib
import hmac
import time
import unittest

from finance_app.services.voice.pairing import PairingCode, PairingCodeGenerator
from finance_app.services.voice.pairing_manager import PairingState, RemoteVoicePairingManager


class TestPairingCodeGeneratorWithSessionId(unittest.TestCase):
    """Test deterministic pairing code generation with session-based validation (Phase 2)."""

    def test_generate_code_deterministic_regardless_of_session_id(self) -> None:
        """Test that code is deterministic and NOT affected by session_id.
        
        Phase 2: Remote device doesn't know session_id, so code must be deterministic.
        Session_id is only used for server-side validation, not code generation.
        """
        auth_token = "1234567890abcdef"
        source_id = "remote-device-1"
        session_id_1 = "session-12345"
        session_id_2 = "session-67890"

        # Same code regardless of session_id
        code_with_session_1 = PairingCodeGenerator.generate(auth_token, source_id, session_id_1)
        code_with_session_2 = PairingCodeGenerator.generate(auth_token, source_id, session_id_2)
        code_without_session = PairingCodeGenerator.generate(auth_token, source_id, "")

        # All should produce identical code
        self.assertEqual(code_with_session_1.code, code_with_session_2.code)
        self.assertEqual(code_with_session_1.code, code_without_session.code)
        self.assertEqual(len(code_with_session_1.code), 6)

    def test_code_is_deterministic_for_remote_device_display(self) -> None:
        """Test that code is deterministic so remote device can independently compute it."""
        auth_token = "test-token-1234567890"
        source_id = "remote-device-1"

        code1 = PairingCodeGenerator.generate(auth_token, source_id, "session-1")
        code2 = PairingCodeGenerator.generate(auth_token, source_id, "different-session")

        # Same code - remote device can compute without knowing session_id
        self.assertEqual(code1.code, code2.code)

    def test_session_code_expires_after_60_seconds(self) -> None:
        """Test that pairing codes expire after 60 seconds."""
        auth_token = "1234567890abcdef"
        source_id = "remote-device-1"

        # Code with 55 seconds elapsed
        past_time = time.time() - 55
        code = PairingCodeGenerator.generate(auth_token, source_id, "", past_time)
        self.assertTrue(code.is_valid())

        # Code with 65 seconds elapsed
        past_time = time.time() - 65
        code = PairingCodeGenerator.generate(auth_token, source_id, "", past_time)
        self.assertFalse(code.is_valid())

    def test_verify_code_independent_of_session_id(self) -> None:
        """Test that code verification works without session_id knowledge."""
        auth_token = "1234567890abcdef"
        source_id = "remote-device-1"

        # Generate code (remote device does this)
        code = PairingCodeGenerator.generate(auth_token, source_id, "")

        # Verify code (server does this, with different session_ids)
        # Both should succeed because code doesn't depend on session_id
        self.assertTrue(PairingCodeGenerator.verify(code.code, auth_token, source_id, "session-1"))
        self.assertTrue(PairingCodeGenerator.verify(code.code, auth_token, source_id, "session-2"))
        self.assertTrue(PairingCodeGenerator.verify(code.code, auth_token, source_id, ""))

    def test_verify_code_is_case_insensitive(self) -> None:
        """Test that code verification is case insensitive."""
        auth_token = "1234567890abcdef"
        source_id = "remote-device-1"

        code = PairingCodeGenerator.generate(auth_token, source_id, "")

        # Verify with lowercase
        self.assertTrue(PairingCodeGenerator.verify(code.code.lower(), auth_token, source_id))

        # Verify with uppercase
        self.assertTrue(PairingCodeGenerator.verify(code.code.upper(), auth_token, source_id))


class TestPairingStateWithSessionId(unittest.TestCase):
    """Test pairing state management with session IDs and expiration (Phase 2)."""

    def test_pairing_state_tracks_session_id(self) -> None:
        """Test that PairingState stores session_id."""
        state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-xyz",
            session_created_at=time.time(),
        )

        self.assertEqual(state.pairing_session_id, "session-xyz")

    def test_session_expiration_after_timeout(self) -> None:
        """Test that session expires after configured timeout."""
        created_at = time.time() - 65  # 65 seconds ago

        state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-1",
            session_created_at=created_at,
            session_timeout_seconds=60.0,
        )

        self.assertTrue(state.is_session_expired())

    def test_session_not_expired_before_timeout(self) -> None:
        """Test that session is valid before timeout."""
        created_at = time.time() - 30  # 30 seconds ago

        state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-1",
            session_created_at=created_at,
            session_timeout_seconds=60.0,
        )

        self.assertFalse(state.is_session_expired())

    def test_get_session_age_seconds(self) -> None:
        """Test session age calculation."""
        created_at = time.time() - 25

        state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-1",
            session_created_at=created_at,
        )

        age = state.get_session_age_seconds()
        self.assertGreaterEqual(age, 25)
        self.assertLess(age, 26)  # Should be around 25 seconds


class TestRemoteVoicePairingManagerWithSessionId(unittest.TestCase):
    """Test pairing manager with session ID validation (Phase 2)."""

    def setUp(self) -> None:
        self.manager = RemoteVoicePairingManager()

    def test_start_pairing_with_session_id(self) -> None:
        """Test starting pairing with session_id."""
        self.manager.start_pairing("device-1", "ABC123", "session-xyz")

        self.assertTrue(self.manager.is_pairing())
        state = self.manager._pairing_state
        self.assertIsNotNone(state)
        self.assertEqual(state.pairing_session_id, "session-xyz")

    def test_verify_rejects_expired_session(self) -> None:
        """Test that verification rejects expired sessions."""
        # Create pairing with old timestamp
        old_time = time.time() - 70
        state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-1",
            session_created_at=old_time,
            session_timeout_seconds=60.0,
        )
        self.manager._pairing_state = state

        # Verification should fail due to expiration
        result = self.manager.verify_pairing_code("device-1", "ABC123", "session-1")
        self.assertFalse(result)

    def test_verify_rejects_mismatched_session_id(self) -> None:
        """Test that verification rejects mismatched session_id."""
        self.manager.start_pairing("device-1", "ABC123", "session-correct")

        # Verify with wrong session_id
        result = self.manager.verify_pairing_code("device-1", "ABC123", "session-wrong")
        self.assertFalse(result)

    def test_verify_accepts_matching_session_id(self) -> None:
        """Test that verification accepts matching session_id."""
        self.manager.start_pairing("device-1", "ABC123", "session-xyz")

        # Verify with correct session_id
        result = self.manager.verify_pairing_code("device-1", "ABC123", "session-xyz")
        self.assertTrue(result)

    def test_verify_backward_compatible_without_session_id(self) -> None:
        """Test that verification works without session_id (backward compatibility)."""
        self.manager.start_pairing("device-1", "ABC123", "session-xyz")

        # Verify without session_id should still work if code matches
        result = self.manager.verify_pairing_code("device-1", "ABC123", "")
        self.assertTrue(result)

    def test_callback_fired_on_successful_verification(self) -> None:
        """Test that callback is fired on successful verification with session_id."""
        callback_args = []

        def callback(source_id: str, code: str) -> None:
            callback_args.append((source_id, code))

        self.manager.set_callbacks(on_confirmed=callback)
        self.manager.start_pairing("device-1", "ABC123", "session-xyz")
        self.manager.verify_pairing_code("device-1", "ABC123", "session-xyz")

        self.assertEqual(len(callback_args), 1)
        self.assertEqual(callback_args[0], ("device-1", "ABC123"))


class TestPhase2Protocol(unittest.TestCase):
    """Integration tests for Phase 2 pairing protocol."""

    def test_complete_phase2_pairing_flow(self) -> None:
        """Test complete Phase 2 pairing flow with session IDs."""
        # Step 1: User clicks "Pair Selected Device" in dialog
        auth_token = "server-token-1234567890"
        source_id = "remote-device-1"
        session_id = "uuid-12345-67890"

        # Step 2: Dialog generates pairing code with session_id
        pairing_code = PairingCodeGenerator.generate(auth_token, source_id, session_id).code

        # Step 3: Manager starts waiting for pairing
        manager = RemoteVoicePairingManager()
        manager.start_pairing(source_id, pairing_code, session_id)

        # Step 4: Remote device connects with hello message (session_id in payload)
        # (simulated - in real flow, network_transport validates)

        # Step 5: Manager verifies pairing code and session_id
        verified = manager.verify_pairing_code(source_id, pairing_code, session_id)
        self.assertTrue(verified)

        # Step 6: Verify that wrong session_id fails
        verified_wrong = manager.verify_pairing_code(source_id, pairing_code, "wrong-session")
        self.assertFalse(verified_wrong)

    def test_session_id_prevents_cross_session_pairing(self) -> None:
        """Test that session_id prevents accidental cross-session pairing."""
        auth_token = "server-token"

        # Scenario: User initiates pairing attempt 1
        manager = RemoteVoicePairingManager()
        manager.start_pairing("device-1", "ABC123", "session-attempt-1")

        # Scenario: Device from a DIFFERENT pairing attempt sends code
        # (e.g., stale cached code from 10 minutes ago)
        old_code = PairingCodeGenerator.generate(auth_token, "device-1", "session-attempt-old")

        # Verification should fail because session_id doesn't match
        verified = manager.verify_pairing_code("device-1", old_code.code, "session-attempt-old")
        self.assertFalse(verified)  # Session doesn't match current one

    def test_session_timeout_prevents_replay_attacks(self) -> None:
        """Test that 60-second session timeout prevents replay attacks."""
        # Create an old pairing session
        old_session_time = time.time() - 70
        manager = RemoteVoicePairingManager()

        state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-old",
            session_created_at=old_session_time,
            session_timeout_seconds=60.0,
        )
        manager._pairing_state = state

        # Even with correct code and session_id, verification fails due to expiration
        result = manager.verify_pairing_code("device-1", "ABC123", "session-old")
        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
