"""Tests for Phase 2: Robust pairing protocol with session-based validation."""

import hashlib
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
        # All should succeed because code doesn't depend on session_id
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

    def test_confirm_existing_pair_fires_callback_for_active_session(self) -> None:
        """Token-authenticated existing device should confirm active pairing UI session."""
        callback_args = []

        def callback(source_id: str, code: str) -> None:
            callback_args.append((source_id, code))

        self.manager.set_callbacks(on_confirmed=callback)
        self.manager.start_pairing("device-1", "ABC123", "session-xyz")

        result = self.manager.confirm_existing_pair("device-1")

        self.assertTrue(result)
        self.assertEqual(len(callback_args), 1)
        self.assertEqual(callback_args[0], ("device-1", "ABC123"))

    def test_is_pairing_auto_clears_expired_session(self) -> None:
        """Expired pairing windows must not remain active and trigger implicit pairing."""
        expired_state = PairingState(
            source_id="device-1",
            expected_pairing_code="ABC123",
            pairing_session_id="session-expired",
            session_created_at=time.time() - 120,
            session_timeout_seconds=60.0,
        )
        self.manager._pairing_state = expired_state

        self.assertFalse(self.manager.is_pairing())
        self.assertIsNone(self.manager.get_pairing_state())


class TestPhase2Protocol(unittest.TestCase):
    """Integration tests for Phase 2 pairing protocol with session-based validation."""

    def test_complete_phase2_pairing_flow(self) -> None:
        """Test complete Phase 2 pairing flow with session IDs for validation only."""
        # Step 1: User clicks "Pair Selected Device" in dialog (receiver side)
        auth_token = "server-token-1234567890"
        source_id = "remote-device-1"
        session_id = "uuid-12345-67890"

        # Step 2: Dialog generates pairing code (deterministic, not session-dependent)
        # Remote device can independently compute the same code
        pairing_code = PairingCodeGenerator.generate(auth_token, source_id, "").code

        # Step 3: Manager starts waiting for pairing (stores session_id for validation)
        manager = RemoteVoicePairingManager()
        manager.start_pairing(source_id, pairing_code, session_id)

        # Step 4: Remote device connects with hello message
        # Remote device also computed the same code independently (deterministic)
        # Remote device includes session_id from broadcast or other discovery mechanism
        remote_code = PairingCodeGenerator.generate(auth_token, source_id, "").code
        self.assertEqual(remote_code, pairing_code)  # Both compute same code

        # Step 5: Manager verifies pairing code and session_id
        verified = manager.verify_pairing_code(source_id, pairing_code, session_id)
        self.assertTrue(verified)

        # Step 6: Verify that wrong session_id fails (session validation)
        verified_wrong_session = manager.verify_pairing_code(
            source_id, pairing_code, "wrong-session"
        )
        # Note: This will fail because the session_id doesn't match
        self.assertFalse(verified_wrong_session)

    def test_session_id_validates_current_pairing_window(self) -> None:
        """Test that session_id ensures pairing happens in current window."""
        auth_token = "server-token"

        # Scenario: User initiates pairing attempt 1 with session_id_A
        manager = RemoteVoicePairingManager()
        session_id_current = "session-current-uuid"
        pairing_code = PairingCodeGenerator.generate(auth_token, "device-1", "").code
        manager.start_pairing("device-1", pairing_code, session_id_current)

        # Scenario: Device tries to use an old session_id from a previous pairing
        old_session_id = "session-old-uuid"
        verified_old_session = manager.verify_pairing_code("device-1", pairing_code, old_session_id)
        self.assertFalse(verified_old_session)  # Rejected due to session_id mismatch

        # But with correct current session_id, it succeeds
        verified_current = manager.verify_pairing_code(
            "device-1", pairing_code, session_id_current
        )
        self.assertTrue(verified_current)

    def test_session_timeout_prevents_replay_attacks(self) -> None:
        """Test that 60-second session timeout prevents replay attacks."""
        # Create an old pairing session (expired)
        old_session_time = time.time() - 70
        manager = RemoteVoicePairingManager()

        auth_token = "server-token"
        source_id = "device-1"
        pairing_code = PairingCodeGenerator.generate(auth_token, source_id, "").code

        state = PairingState(
            source_id=source_id,
            expected_pairing_code=pairing_code,
            pairing_session_id="old-session-uuid",
            session_created_at=old_session_time,
            session_timeout_seconds=60.0,
        )
        manager._pairing_state = state

        # Even with correct code and session_id, verification fails due to expiration
        result = manager.verify_pairing_code(source_id, pairing_code, "old-session-uuid")
        self.assertFalse(result)  # Rejected: session expired

    def test_remote_device_can_display_code_independently(self) -> None:
        """Test that remote device can independently compute and display pairing code."""
        auth_token = "shared-token"
        source_id = "remote-sender-1"

        # Receiver generates code
        receiver_code = PairingCodeGenerator.generate(auth_token, source_id, "").code

        # Remote device independently generates code (no session_id needed for code)
        remote_code = PairingCodeGenerator.generate(auth_token, source_id, "").code

        # Codes must match for user verification
        self.assertEqual(receiver_code, remote_code)


if __name__ == "__main__":
    unittest.main()
