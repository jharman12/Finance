"""
Tests for the device management CLI commands in manage.py.

Covers:
- list-devices with no devices
- list-devices with one active + one revoked device
- unpair removes DB entry and revokes token
- rotate-token revokes old token and issues a new one (new token printed)
- show-token reports PRESENT / ABSENT correctly
"""
from __future__ import annotations

import argparse
import sys
import unittest
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, call, patch

# Ensure the project root is importable when the test is run with
# ``py -m unittest tests.test_cli_device_management`` from the workspace root.
import importlib
import os
import pathlib

_ROOT = str(pathlib.Path(__file__).parent.parent)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import manage  # noqa: E402  (must come after sys.path tweak)
from finance_app.models import PairedRemoteDevice  # noqa: E402
from finance_app.services.voice.device_token_store import DeviceTokenRecord  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_device(
    source_id: str,
    name: str = "TestDevice",
    host: str = "192.168.1.10",
    last_conn: datetime | None = None,
    is_active: bool = True,
) -> PairedRemoteDevice:
    return PairedRemoteDevice(
        id=1,
        source_id=source_id,
        device_name=name,
        host_ip=host,
        port=8765,
        role="sender",
        protocol_version="1",
        paired_at=datetime(2025, 1, 1),
        last_connected_at=last_conn,
        is_active=is_active,
    )


def _make_token(source_id: str, revoked: bool = False) -> DeviceTokenRecord:
    return DeviceTokenRecord(
        source_id=source_id,
        token_hash="deadbeef" * 8,
        device_name="TestDevice",
        paired_at="2025-01-01T00:00:00",
        last_used_at="",
        revoked_at="2025-06-01T12:00:00" if revoked else "",
    )


def _ns(**kwargs: object) -> argparse.Namespace:
    """Create an argparse.Namespace from keyword args."""
    return argparse.Namespace(**kwargs)


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestCLIDeviceManagement(unittest.TestCase):
    # ------------------------------------------------------------------
    # list-devices
    # ------------------------------------------------------------------

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    @patch("manage.FinanceRepository")
    def test_list_devices_empty(
        self,
        MockRepo: MagicMock,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """list-devices with no devices prints a friendly 'no devices' message."""
        MockRepo.return_value._paired_device_repository.list_all.return_value = []
        MockStore.return_value.list_tokens.return_value = []

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_list_devices(_ns())

        output = mock_out.getvalue()
        self.assertIn("No paired remote devices found", output)

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    @patch("manage.FinanceRepository")
    def test_list_devices_active_and_revoked(
        self,
        MockRepo: MagicMock,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """list-devices shows one active and one revoked device with correct token status."""
        active_device = _make_device("device-alpha", name="Alpha", host="10.0.0.1")
        revoked_device = _make_device("device-beta", name="Beta", host="10.0.0.2")

        MockRepo.return_value._paired_device_repository.list_all.return_value = [
            active_device,
            revoked_device,
        ]
        MockStore.return_value.list_tokens.return_value = [
            _make_token("device-alpha", revoked=False),
            _make_token("device-beta", revoked=True),
        ]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_list_devices(_ns())

        output = mock_out.getvalue()

        # Both source IDs appear
        self.assertIn("device-alpha", output)
        self.assertIn("device-beta", output)

        # Token statuses are reported correctly
        self.assertIn("active", output)
        self.assertIn("revoked", output)

        # Raw token hashes must never appear
        self.assertNotIn("deadbeef", output)

    # ------------------------------------------------------------------
    # unpair
    # ------------------------------------------------------------------

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    @patch("manage.FinanceRepository")
    def test_unpair_removes_device_and_revokes_token(
        self,
        MockRepo: MagicMock,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """unpair calls delete() on the repo and revoke_token() on the token store."""
        device = _make_device("device-alpha")
        mock_repo_inst = MockRepo.return_value
        mock_repo_inst._paired_device_repository.get_by_source_id.return_value = device
        mock_store_inst = MockStore.return_value
        mock_store_inst.revoke_token.return_value = True

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_unpair(_ns(source_id="device-alpha"))

        mock_repo_inst._paired_device_repository.delete.assert_called_once_with("device-alpha")
        mock_store_inst.revoke_token.assert_called_once_with("device-alpha")

        output = mock_out.getvalue()
        self.assertIn("Unpaired", output)
        self.assertIn("device-alpha", output)

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    @patch("manage.FinanceRepository")
    def test_unpair_exits_when_device_not_found(
        self,
        MockRepo: MagicMock,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """unpair exits with code 1 when the device is not in the DB."""
        MockRepo.return_value._paired_device_repository.get_by_source_id.return_value = None

        with self.assertRaises(SystemExit) as ctx:
            manage.cmd_unpair(_ns(source_id="no-such-device"))

        self.assertEqual(ctx.exception.code, 1)
        # Token store must not be touched
        MockStore.return_value.revoke_token.assert_not_called()

    # ------------------------------------------------------------------
    # rotate-token
    # ------------------------------------------------------------------

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    @patch("manage.FinanceRepository")
    def test_rotate_token_revokes_old_and_issues_new(
        self,
        MockRepo: MagicMock,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """rotate-token revokes the current token, issues a new one, and prints it."""
        device = _make_device("device-alpha", name="Alpha")
        MockRepo.return_value._paired_device_repository.get_by_source_id.return_value = device

        new_plaintext_token = "supersecrettoken-new-abc123"
        mock_store_inst = MockStore.return_value
        mock_store_inst.revoke_token.return_value = True
        mock_store_inst.issue_token.return_value = new_plaintext_token

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_rotate_token(_ns(source_id="device-alpha"))

        mock_store_inst.revoke_token.assert_called_once_with("device-alpha")
        mock_store_inst.issue_token.assert_called_once_with("device-alpha", "Alpha")

        output = mock_out.getvalue()
        # The new token plaintext must be printed so the user can configure the device
        self.assertIn(new_plaintext_token, output)
        self.assertIn("device-alpha", output)

    # ------------------------------------------------------------------
    # show-token
    # ------------------------------------------------------------------

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    def test_show_token_present(
        self,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """show-token reports PRESENT for a device with an active token."""
        MockStore.return_value.list_tokens.return_value = [
            _make_token("device-alpha", revoked=False),
        ]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_show_token(_ns(source_id="device-alpha"))

        output = mock_out.getvalue()
        self.assertIn("PRESENT", output)
        self.assertNotIn("deadbeef", output)  # raw hash must never appear

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    def test_show_token_absent_revoked(
        self,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """show-token reports ABSENT when the token has been revoked."""
        MockStore.return_value.list_tokens.return_value = [
            _make_token("device-alpha", revoked=True),
        ]

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_show_token(_ns(source_id="device-alpha"))

        output = mock_out.getvalue()
        self.assertIn("ABSENT", output)
        self.assertIn("revoked", output)

    @patch("manage._db_exists_check", return_value=True)
    @patch("manage.DeviceTokenStore")
    def test_show_token_absent_no_record(
        self,
        MockStore: MagicMock,
        _mock_check: MagicMock,
    ) -> None:
        """show-token reports ABSENT when no token record exists at all."""
        MockStore.return_value.list_tokens.return_value = []

        with patch("sys.stdout", new_callable=StringIO) as mock_out:
            manage.cmd_show_token(_ns(source_id="ghost-device"))

        output = mock_out.getvalue()
        self.assertIn("ABSENT", output)
        self.assertIn("no token record found", output)


if __name__ == "__main__":
    unittest.main()
