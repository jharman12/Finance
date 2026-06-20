from __future__ import annotations

import importlib
import socket
from dataclasses import dataclass
from typing import Any, Callable

SERVICE_TYPE_RECEIVER = "_finance-voice._tcp.local."
SERVICE_TYPE_SENDER = "_fvoice-sender._tcp.local."
SERVICE_TYPE = SERVICE_TYPE_RECEIVER  # Default for backward compatibility

_zeroconf_module = None
try:
    _zeroconf_module = importlib.import_module("zeroconf")
except Exception:
    _zeroconf_module = None

ServiceBrowser: Any = getattr(_zeroconf_module, "ServiceBrowser", None)
ServiceInfo: Any = getattr(_zeroconf_module, "ServiceInfo", None)
ServiceStateChange: Any = getattr(_zeroconf_module, "ServiceStateChange", None)
Zeroconf: Any = getattr(_zeroconf_module, "Zeroconf", None)


@dataclass(slots=True)
class RemoteVoiceDiscoveryDevice:
    service_name: str
    device_name: str
    source_id: str
    role: str
    protocol_version: str
    host: str
    port: int
    properties: dict[str, str]


def normalize_label(value: str, fallback: str = "finance-voice") -> str:
    candidate = value.strip().lower()
    candidate = "".join(character if character.isalnum() else "-" for character in candidate)
    candidate = "-".join(part for part in candidate.split("-") if part)
    return candidate or fallback


def build_service_name(device_name: str, source_id: str, service_type: str = SERVICE_TYPE) -> str:
    device_label = normalize_label(device_name)
    source_label = normalize_label(source_id, fallback="node")
    return f"{device_label}-{source_label}.{service_type}"


def build_service_properties(
    source_id: str,
    device_name: str,
    role: str,
    protocol_version: str,
) -> dict[str, bytes]:
    return {
        "source_id": source_id.encode("utf-8"),
        "device_name": device_name.encode("utf-8"),
        "role": role.encode("utf-8"),
        "protocol_version": protocol_version.encode("utf-8"),
    }


def decode_service_properties(properties: dict[Any, Any] | None) -> dict[str, str]:
    decoded: dict[str, str] = {}
    if not properties:
        return decoded

    for key, value in properties.items():
        if isinstance(key, bytes):
            decoded_key = key.decode("utf-8", errors="ignore")
        else:
            decoded_key = str(key)

        if isinstance(value, bytes):
            decoded_value = value.decode("utf-8", errors="ignore")
        else:
            decoded_value = str(value)

        decoded[decoded_key] = decoded_value
    return decoded


def resolve_local_ipv4(default: str = "127.0.0.1") -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("1.1.1.1", 80))
            return sock.getsockname()[0]
    except Exception:
        return default


class RemoteVoiceDiscoveryPublisher:
    def __init__(
        self,
        source_id: str,
        port: int,
        device_name: str | None = None,
        host: str | None = None,
        role: str = "remote-sender",
        protocol_version: str = "1",
    ) -> None:
        self.source_id = source_id
        self.device_name = device_name or source_id
        self.port = int(port)
        self.host = host
        self.role = role
        self.protocol_version = protocol_version
        self.service_type = SERVICE_TYPE  # Can be overridden before calling start()
        self._zeroconf: Any = None
        self._service_info: Any = None

    def start(self) -> bool:
        if Zeroconf is None or ServiceInfo is None:
            return False

        if self._zeroconf is not None:
            return True

        advertised_host = self.host or resolve_local_ipv4()
        service_name = build_service_name(self.device_name, self.source_id, self.service_type)
        properties = build_service_properties(
            source_id=self.source_id,
            device_name=self.device_name,
            role=self.role,
            protocol_version=self.protocol_version,
        )

        try:
            addresses = [socket.inet_aton(advertised_host)]
        except OSError:
            addresses = []

        self._service_info = ServiceInfo(
            self.service_type,
            service_name,
            addresses=addresses,
            port=self.port,
            properties=properties,
            server=f"{normalize_label(self.device_name)}.local.",
        )
        self._zeroconf = Zeroconf()
        self._zeroconf.register_service(self._service_info, allow_name_change=True)
        return True

    def stop(self) -> None:
        zeroconf = self._zeroconf
        service_info = self._service_info
        self._zeroconf = None
        self._service_info = None

        if zeroconf is None:
            return

        try:
            if service_info is not None:
                zeroconf.unregister_service(service_info)
        except Exception:
            pass
        try:
            zeroconf.close()
        except Exception:
            pass


class RemoteVoiceDiscoveryBrowser:
    def __init__(self, service_type: str = SERVICE_TYPE) -> None:
        self.service_type = service_type
        self._zeroconf: Any = None
        self._browser: Any = None
        self._on_device: Callable[[RemoteVoiceDiscoveryDevice], None] | None = None
        self._on_diagnostic: Callable[[dict[str, object]], None] | None = None

    def start(
        self,
        on_device: Callable[[RemoteVoiceDiscoveryDevice], None],
        on_diagnostic: Callable[[dict[str, object]], None] | None = None,
    ) -> bool:
        if Zeroconf is None or ServiceBrowser is None or ServiceStateChange is None:
            return False

        if self._zeroconf is not None:
            return True

        self._on_device = on_device
        self._on_diagnostic = on_diagnostic
        self._zeroconf = Zeroconf()
        self._browser = ServiceBrowser(self._zeroconf, self.service_type, handlers=[self._handle_service_state_change])
        if self._on_diagnostic is not None:
            self._on_diagnostic({"event": "mdns_browser_started", "service_type": self.service_type})
        return True

    def stop(self) -> None:
        zeroconf = self._zeroconf
        self._zeroconf = None
        self._browser = None
        self._on_device = None
        self._on_diagnostic = None

        if zeroconf is None:
            return

        try:
            zeroconf.close()
        except Exception:
            pass

    def _handle_service_state_change(self, zeroconf: Any, service_type: str, name: str, state_change: Any) -> None:
        if self._on_diagnostic is not None:
            self._on_diagnostic({"event": "mdns_service_state", "service_name": name, "state": str(state_change)})

        if ServiceStateChange is not None and state_change == ServiceStateChange.Removed:
            return

        info = zeroconf.get_service_info(service_type, name, timeout=1000)
        if info is None:
            return

        addresses = getattr(info, "addresses", None) or []
        host = ""
        if addresses:
            try:
                host = socket.inet_ntoa(addresses[0])
            except OSError:
                host = ""

        properties = decode_service_properties(getattr(info, "properties", None))
        device = RemoteVoiceDiscoveryDevice(
            service_name=getattr(info, "name", name),
            device_name=properties.get("device_name", normalize_label(name)),
            source_id=properties.get("source_id", ""),
            role=properties.get("role", ""),
            protocol_version=properties.get("protocol_version", ""),
            host=host,
            port=int(getattr(info, "port", 0)),
            properties=properties,
        )

        if self._on_device is not None:
            self._on_device(device)
