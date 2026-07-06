from __future__ import annotations

import ctypes
import platform
import subprocess
from dataclasses import dataclass


RULE_NAME_PREFIX = "Finance Remote Voice Receiver TCP"


@dataclass(slots=True)
class FirewallAutomationResult:
    success: bool
    status: str
    message: str
    requires_admin: bool = False


class WindowsFirewallAutomation:
    """Windows-only netsh helper for inbound remote voice receiver rules."""

    @staticmethod
    def is_windows() -> bool:
        return platform.system().lower() == "windows"

    @staticmethod
    def is_admin() -> bool:
        if not WindowsFirewallAutomation.is_windows():
            return False
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:
            return False

    @staticmethod
    def build_rule_name(port: int) -> str:
        return f"{RULE_NAME_PREFIX} {port}"


def ensure_remote_voice_receiver_rule(port: int) -> FirewallAutomationResult:
    """Ensure an inbound TCP rule exists for the remote voice receiver port."""
    if not WindowsFirewallAutomation.is_windows():
        return FirewallAutomationResult(
            success=True,
            status="not_applicable",
            message="Windows firewall automation skipped on non-Windows platform.",
        )

    if int(port) <= 0 or int(port) > 65535:
        return FirewallAutomationResult(
            success=False,
            status="invalid_port",
            message=f"Windows firewall automation skipped due to invalid port: {port}.",
        )

    rule_name = WindowsFirewallAutomation.build_rule_name(int(port))
    add_cmd = [
        "netsh",
        "advfirewall",
        "firewall",
        "add",
        "rule",
        f"name={rule_name}",
        "dir=in",
        "action=allow",
        "protocol=TCP",
        f"localport={int(port)}",
        "profile=private,domain",
        "enable=yes",
    ]

    try:
        result = subprocess.run(add_cmd, capture_output=True, text=True, check=False, timeout=15)
    except FileNotFoundError:
        return FirewallAutomationResult(
            success=False,
            status="netsh_unavailable",
            message="Could not run Windows firewall automation because netsh was not found.",
        )
    except Exception as exc:
        return FirewallAutomationResult(
            success=False,
            status="execution_error",
            message=f"Windows firewall automation failed: {exc}",
            requires_admin=not WindowsFirewallAutomation.is_admin(),
        )

    output = f"{result.stdout}\n{result.stderr}".lower()

    if result.returncode == 0:
        return FirewallAutomationResult(
            success=True,
            status="added",
            message=f"Windows firewall rule ready for remote voice receiver on TCP {int(port)}.",
        )

    if "already exists" in output:
        return FirewallAutomationResult(
            success=True,
            status="already_exists",
            message=f"Windows firewall rule already exists for remote voice receiver on TCP {int(port)}.",
        )

    requires_admin = (
        "requires elevation" in output
        or "access is denied" in output
        or "requested operation requires" in output
        or not WindowsFirewallAutomation.is_admin()
    )
    if requires_admin:
        return FirewallAutomationResult(
            success=False,
            status="requires_admin",
            message=(
                "Remote receiver is running, but Windows firewall rule could not be added. "
                "Run the app as Administrator once to allow inbound remote voice traffic."
            ),
            requires_admin=True,
        )

    trimmed = (result.stderr or result.stdout or "").strip()
    if trimmed:
        error_tail = f" Detail: {trimmed}"
    else:
        error_tail = ""

    return FirewallAutomationResult(
        success=False,
        status="failed",
        message=(
            "Remote receiver is running, but automatic Windows firewall configuration failed."
            f"{error_tail}"
        ),
    )
