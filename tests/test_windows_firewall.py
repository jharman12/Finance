from __future__ import annotations

import subprocess
import unittest
from unittest.mock import patch

from finance_app.infrastructure.windows_firewall import ensure_remote_voice_receiver_rule


class WindowsFirewallAutomationTests(unittest.TestCase):
    def test_non_windows_is_noop(self) -> None:
        with patch("finance_app.infrastructure.windows_firewall.platform.system", return_value="Linux"):
            result = ensure_remote_voice_receiver_rule(45881)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "not_applicable")

    def test_rule_added_successfully(self) -> None:
        completed = subprocess.CompletedProcess(args=["netsh"], returncode=0, stdout="Ok.", stderr="")
        with patch("finance_app.infrastructure.windows_firewall.platform.system", return_value="Windows"), patch(
            "finance_app.infrastructure.windows_firewall.subprocess.run",
            return_value=completed,
        ):
            result = ensure_remote_voice_receiver_rule(45881)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "added")
        self.assertFalse(result.requires_admin)

    def test_existing_rule_is_treated_as_success(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["netsh"],
            returncode=1,
            stdout="",
            stderr="An object with this name already exists.",
        )
        with patch("finance_app.infrastructure.windows_firewall.platform.system", return_value="Windows"), patch(
            "finance_app.infrastructure.windows_firewall.subprocess.run",
            return_value=completed,
        ):
            result = ensure_remote_voice_receiver_rule(45881)

        self.assertTrue(result.success)
        self.assertEqual(result.status, "already_exists")

    def test_requires_admin_detected(self) -> None:
        completed = subprocess.CompletedProcess(
            args=["netsh"],
            returncode=1,
            stdout="",
            stderr="The requested operation requires elevation.",
        )
        with patch("finance_app.infrastructure.windows_firewall.platform.system", return_value="Windows"), patch(
            "finance_app.infrastructure.windows_firewall.subprocess.run",
            return_value=completed,
        ), patch("finance_app.infrastructure.windows_firewall.WindowsFirewallAutomation.is_admin", return_value=False):
            result = ensure_remote_voice_receiver_rule(45881)

        self.assertFalse(result.success)
        self.assertEqual(result.status, "requires_admin")
        self.assertTrue(result.requires_admin)


if __name__ == "__main__":
    unittest.main()
