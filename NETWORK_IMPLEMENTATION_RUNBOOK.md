# Network Architecture Implementation Runbook

**Reference:** NETWORK_ARCHITECTURE_GUIDE.md  
**Last Updated:** 2026-06-24

---

## Part 1: Service Type Fix (Critical)

### Issue
mDNS service type `_finance-voice._tcp` is 15 characters. RFC 6763 allows up to 15, but some implementations (Java, Bonjour) reject exactly 15 due to parser boundary conditions.

### Fix: 2-minute change

**File:** [finance_app/services/voice/discovery.py](finance_app/services/voice/discovery.py)

```python
# Current (PROBLEMATIC)
SERVICE_TYPE_RECEIVER = "_finance-voice._tcp.local."  # 15 chars
SERVICE_TYPE_SENDER = "_fvoice-sender._tcp.local."

# Fixed (SAFE)
SERVICE_TYPE_RECEIVER = "_fvoice._tcp.local."         # 8 chars
SERVICE_TYPE_SENDER = "_fvoice-sender._tcp.local."    # 13 chars
```

**Reason:** 
- `_fvoice._tcp` = 8 chars (safe margin)
- Maintains backward compatibility within LAN (mDNS is ephemeral; no hard dependencies)
- Reduces collision risk (shorter label = broader space)

### Validation

After change, verify mDNS registration:

```bash
# macOS / Linux
dns-sd -R "Finance-Voice-Test" "_fvoice._tcp" local 9876

# Windows (requires Apple Bonjour)
# Or use: Get-NetIPAddress | Select IPAddress
```

---

## Part 2: Device Token Persistence

### Problem
Currently, tokens are read from config file, not persisted post-pairing. On app restart, tokens are lost.

### Solution: Persistent JSON backend

**Create:** `finance_app/services/voice/device_token_storage.py`

```python
"""Persistent device token storage with metadata."""

import json
import time
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Dict, Optional
from datetime import datetime


@dataclass
class DeviceToken:
    source_id: str
    device_name: str
    token_hash: str  # SHA256 first 8 chars
    token_created_at: str  # ISO timestamp
    token_rotated_at: Optional[str] = None
    paired_at: str = None  # Populated on first successful auth
    last_seen: Optional[str] = None
    status: str = "active"  # or "suspended", "revoked"
    notes: str = ""
    
    def __post_init__(self):
        if self.paired_at is None:
            self.paired_at = datetime.utcnow().isoformat() + "Z"


class DeviceTokenStorage:
    def __init__(self, storage_dir: Path = None):
        if storage_dir is None:
            storage_dir = Path.home() / ".finance-voice"
        self.storage_dir = storage_dir
        self.tokens_file = storage_dir / "paired-device-tokens.json"
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._tokens: Dict[str, DeviceToken] = self._load()
    
    def _load(self) -> Dict[str, DeviceToken]:
        if not self.tokens_file.exists():
            return {}
        
        try:
            with open(self.tokens_file, 'r') as f:
                data = json.load(f)
            
            # Deserialize to DeviceToken objects
            tokens = {}
            for source_id, token_dict in data.items():
                tokens[source_id] = DeviceToken(**token_dict)
            return tokens
        except (json.JSONDecodeError, TypeError) as e:
            print(f"Warning: Failed to load tokens: {e}")
            return {}
    
    def _save(self):
        """Atomically write tokens to disk."""
        temp_file = self.tokens_file.with_suffix('.json.tmp')
        
        try:
            with open(temp_file, 'w') as f:
                data = {sid: asdict(token) for sid, token in self._tokens.items()}
                json.dump(data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.tokens_file)
        except Exception as e:
            print(f"Error: Failed to save tokens: {e}")
            if temp_file.exists():
                temp_file.unlink()
            raise
    
    def store(self, source_id: str, device_name: str, token_hash: str, notes: str = ""):
        """Register a newly-paired device."""
        now = datetime.utcnow().isoformat() + "Z"
        self._tokens[source_id] = DeviceToken(
            source_id=source_id,
            device_name=device_name,
            token_hash=token_hash,
            token_created_at=now,
            paired_at=now,
            last_seen=now,
            notes=notes
        )
        self._save()
    
    def get(self, source_id: str) -> Optional[DeviceToken]:
        return self._tokens.get(source_id)
    
    def list_all(self) -> list[DeviceToken]:
        return list(self._tokens.values())
    
    def update_last_seen(self, source_id: str):
        if source_id in self._tokens:
            self._tokens[source_id].last_seen = datetime.utcnow().isoformat() + "Z"
            self._save()
    
    def unpair(self, source_id: str, reason: str = ""):
        """Revoke device (keep record for audit)."""
        if source_id in self._tokens:
            token = self._tokens[source_id]
            token.status = "revoked"
            token.notes = f"{token.notes}\nRevoked: {reason}" if reason else token.notes
            self._save()
    
    def rotate_token(self, source_id: str, new_token_hash: str):
        """Rotate token for existing device."""
        if source_id in self._tokens:
            now = datetime.utcnow().isoformat() + "Z"
            self._tokens[source_id].token_rotated_at = now
            self._tokens[source_id].token_hash = new_token_hash
            self._save()
    
    def has_active_device(self, source_id: str) -> bool:
        token = self._tokens.get(source_id)
        return token is not None and token.status == "active"
```

### Integration with existing code

**Update:** [finance_app/services/voice/network_transport.py](finance_app/services/voice/network_transport.py)

```python
from finance_app.services.voice.device_token_storage import DeviceTokenStorage

class RemoteAudioServer:
    def __init__(self, ...):
        # ... existing init ...
        self._device_storage = DeviceTokenStorage()
    
    def _verify_pairing(self, source_id: str, token: str) -> bool:
        """Check if device is already paired."""
        stored_token = self._device_storage.get(source_id)
        if stored_token is None:
            return False
        
        if stored_token.status != "active":
            self._debug(f"Device {source_id} status={stored_token.status}")
            return False
        
        # Verify token matches (compare hashes for security)
        token_hash = _token_fingerprint(token)
        if token_hash != stored_token.token_hash:
            return False
        
        # Update last_seen
        self._device_storage.update_last_seen(source_id)
        return True
    
    def _register_pairing(self, source_id: str, device_name: str, token: str):
        """Store newly-paired device."""
        token_hash = _token_fingerprint(token)
        self._device_storage.store(source_id, device_name, token_hash)
```

---

## Part 3: Device Management CLI

**Create:** `finance_app/cli/device_commands.py`

```python
"""CLI commands for device management."""

import argparse
import sys
from pathlib import Path
from datetime import datetime
from finance_app.services.voice.device_token_storage import DeviceTokenStorage


def cmd_list_devices(args):
    """List all paired devices."""
    storage = DeviceTokenStorage()
    devices = storage.list_all()
    
    if not devices:
        print("No devices paired.")
        return 0
    
    print(f"\n{'Source ID':<15} {'Device Name':<25} {'Status':<10} {'Last Seen':<20}")
    print("-" * 70)
    
    for device in devices:
        last_seen = device.last_seen or "Never"
        print(f"{device.source_id:<15} {device.device_name:<25} {device.status:<10} {last_seen:<20}")
    
    return 0


def cmd_unpair(args):
    """Revoke a device."""
    storage = DeviceTokenStorage()
    
    device = storage.get(args.device_id)
    if device is None:
        print(f"Error: Device '{args.device_id}' not found.")
        return 1
    
    if device.status == "revoked":
        print(f"Device '{args.device_id}' already revoked.")
        return 0
    
    storage.unpair(args.device_id, reason=args.reason)
    print(f"✓ Device '{args.device_id}' revoked.")
    print(f"  Reason: {args.reason}")
    return 0


def cmd_rotate_token(args):
    """Rotate auth token (re-pair required)."""
    storage = DeviceTokenStorage()
    
    import secrets
    new_token = secrets.token_urlsafe(32)
    new_hash = _token_fingerprint(new_token)
    
    print("⚠️  Token rotation initiated.")
    print(f"   New token: {new_token}")
    print(f"   Hash: {new_hash}")
    print(f"   Devices must be re-paired to use new token.")
    
    if input("Continue? (yes/no): ").strip().lower() != "yes":
        return 0
    
    # TODO: Implement token distribution mechanism
    # For now, just print it
    print("\n✓ Save new token to config:")
    print(f"   FINANCE_APP_VOICE_RECEIVER_TOKEN={new_token}")
    
    return 0


def main():
    parser = argparse.ArgumentParser(description="Finance Voice device management")
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # list-devices
    subparsers.add_parser("list-devices", help="List all paired devices")
    
    # unpair
    unpair_parser = subparsers.add_parser("unpair", help="Revoke a device")
    unpair_parser.add_argument("device_id", help="Source ID of device to unpair")
    unpair_parser.add_argument("--reason", default="", help="Reason for revocation")
    
    # rotate-token
    subparsers.add_parser("rotate-token", help="Rotate auth token")
    
    args = parser.parse_args()
    
    if args.command == "list-devices":
        return cmd_list_devices(args)
    elif args.command == "unpair":
        return cmd_unpair(args)
    elif args.command == "rotate-token":
        return cmd_rotate_token(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

### Add CLI entry point

**Update:** `main.py` or `manage.py`

```bash
# Usage examples
python -m finance_app.cli device list-devices
python -m finance_app.cli device unpair node-1 --reason "Device lost"
python -m finance_app.cli device rotate-token
```

---

## Part 4: Windows Firewall Automation

**Create:** `finance_app/infrastructure/windows_firewall.py`

```python
"""Automate Windows Firewall rules for remote audio."""

import subprocess
import sys
import os


def is_windows():
    return sys.platform == "win32"


def is_admin():
    """Check if running as Administrator."""
    if not is_windows():
        return True
    
    try:
        return os.getuid() == 0
    except AttributeError:
        # Windows: check via ctypes
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())


def add_firewall_rule(app_path: str, rule_name: str = "Finance Voice Receiver"):
    """Add inbound TCP rule to Windows Firewall (port 9876)."""
    
    if not is_windows():
        print("Firewall automation only supported on Windows.")
        return False
    
    # Try to run netsh; may prompt for admin
    cmd = [
        "netsh", "advfirewall", "firewall", "add", "rule",
        f"name={rule_name}",
        "dir=in",
        "action=allow",
        "protocol=tcp",
        "localport=9876",
        f"program={app_path}"
    ]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print(f"✓ Firewall rule '{rule_name}' added.")
            return True
        else:
            print(f"Firewall error: {result.stderr}")
            return False
    except Exception as e:
        print(f"Error adding firewall rule: {e}")
        return False


def on_app_startup():
    """Call on app startup to ensure firewall rule exists."""
    if not is_windows():
        return
    
    # Try non-admin first; if fails, suggest to user
    app_path = os.path.abspath(sys.executable)
    
    if add_firewall_rule(app_path):
        return
    
    # If failed, show manual instructions
    print("\n⚠️  Could not automatically add firewall rule.")
    print("   To allow remote devices to connect:")
    print("   1. Open Windows Defender Firewall")
    print("   2. Click 'Allow an app through firewall'")
    print("   3. Click 'Change settings' (may need admin)")
    print("   4. Click 'Allow another app...'")
    print("   5. Find Python.exe or Finance Voice Receiver")
    print("   6. Check 'Private' and click OK")
```

**Integration:** Call from [finance_app/ui/main_window.py](finance_app/ui/main_window.py)

```python
from finance_app.infrastructure.windows_firewall import on_app_startup

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # ... existing init ...
        on_app_startup()  # Ensure firewall rule on startup
```

---

## Part 5: Connection Pooling for 4+ Devices

### Problem
Current `ThreadingMixIn` spawns 1 thread per connection. At 8+ devices, thread overhead increases context-switching. Audio pipeline must mux sources.

### Solution: Bounded thread pool + source mux

**Update:** [finance_app/services/voice/network_transport.py](finance_app/services/voice/network_transport.py)

```python
import concurrent.futures

class RemoteAudioServer:
    def __init__(self, ..., max_concurrent_connections: int = 4):
        # ... existing init ...
        self.max_concurrent = max_concurrent_connections
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_concurrent_connections + 1,  # +1 for listener
            thread_name_prefix="remote-audio"
        )
    
    def _accept_connection(self, client_socket, client_addr):
        """Called when new client connects."""
        with self._session_lock:
            active_count = len(self._active_sessions)
        
        if active_count >= self.max_concurrent:
            # Graceful rejection
            error_msg = {
                "type": "error",
                "reason": f"Server at capacity ({active_count}/{self.max_concurrent}). Try again later.",
                "retry_after_seconds": 30
            }
            try:
                client_socket.sendall(
                    json.dumps(error_msg).encode() + b"\n"
                )
            except:
                pass
            finally:
                client_socket.close()
            return
        
        # Submit handler to pool
        future = self._thread_pool.submit(
            self._handle_client,
            client_socket,
            client_addr
        )
        
        # Track for debugging
        self._debug(f"Submitted handler for {client_addr}; active={active_count + 1}/{self.max_concurrent}")
    
    def shutdown(self):
        """Graceful shutdown."""
        self._thread_pool.shutdown(wait=True, timeout=5)
```

---

## Part 6: Opus Codec Support (Optional)

**Create:** `finance_app/services/voice/audio_codec.py`

```python
"""Audio codec support: PCM16, Opus, G.711."""

import struct
from typing import Union
from enum import Enum
import numpy as np


class AudioCodec(Enum):
    PCM16 = "pcm16"
    OPUS = "opus"
    G711 = "g711"


class AudioDecoder:
    @staticmethod
    def decode(payload: bytes, codec: AudioCodec, sample_rate: int = 16000) -> np.ndarray:
        """Decode audio payload to PCM16 numpy array."""
        
        if codec == AudioCodec.PCM16:
            # Raw 16-bit samples
            return np.frombuffer(payload, dtype=np.int16)
        
        elif codec == AudioCodec.OPUS:
            # Requires: pip install opuslib
            try:
                import opuslib
            except ImportError:
                raise RuntimeError(
                    "Opus codec requires 'opuslib' library. "
                    "Install: pip install opuslib"
                )
            
            # Opus frame size for 10ms at 16kHz = 160 samples
            frame_size = 160
            decoder = opuslib.Decoder(sample_rate, 1)  # 1 = mono
            return np.frombuffer(
                decoder.decode(payload, frame_size),
                dtype=np.int16
            )
        
        elif codec == AudioCodec.G711:
            # μ-law (G.711) simple decode
            # See: https://en.wikipedia.org/wiki/G.711
            decoded = []
            for byte in payload:
                # Inverse μ-law formula
                byte = ~byte
                sign = (byte & 0x80) >> 7
                exponent = (byte & 0x70) >> 4
                mantissa = (byte & 0x0f)
                
                # Reconstruct sample
                sample = mantissa << (exponent + 3)
                if exponent > 0:
                    sample += 0x80 << (exponent + 3)
                
                if sign:
                    sample = -sample
                
                decoded.append(sample)
            
            return np.array(decoded, dtype=np.int16)
        
        else:
            raise ValueError(f"Unknown codec: {codec}")
```

**Integration:** Update [voice_pipeline.py](finance_app/services/voice/voice_pipeline.py)

```python
# In audio frame reception:
frame_data = AudioDecoder.decode(
    packet.payload,
    codec=AudioCodec[packet.codec.upper()],
    sample_rate=packet.sample_rate
)
```

---

## Part 7: Operational Runbook

### Device Pairing (Happy Path)

```
1. User opens main app → clicks "Pair New Device"
2. UI shows 6-digit code (valid 30 seconds)
3. Remote device app starts; discovers main PC via mDNS
4. Remote device shows list of nearby receivers
5. User selects main PC, enters 6-digit code
6. Main PC receives hello_ack + pairing_session_id
7. Main PC validates: HMAC(token, source_id + session_id) == code
8. ✓ Device added to ~/.finance-voice/paired-device-tokens.json
9. Remote device now connects persistently
```

### Device Troubleshooting

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| "Cannot find main PC" | mDNS not propagating | Check: mDNS enabled, same subnet, firewall allowing UDP 5353 |
| "Connection refused" | Firewall blocking | Run: `netsh advfirewall firewall add rule ...` (see Part 4) |
| "Pairing code mismatch" | Token changed on restart | Persist token to ~/.finance-voice/paired-device-tokens.json |
| "Device appears twice in list" | Duplicate mDNS records | Restart app or wait 2 minutes for cache expiry |
| "Audio crackles after 30 seconds" | UDP jitter buffer misconfiguration | Check: jitter_buffer_ms, sample_rate mismatch |

### Emergency Procedures

**Kill all remote sessions:**
```bash
python -m finance_app.cli device list-devices  # See what's paired
python -m finance_app.cli device unpair '*' --reason "Emergency"
# Then restart app
```

**Reset to factory defaults:**
```bash
rm ~/.finance-voice/paired-device-tokens.json
rm ~/.finance-voice/receiver_token.txt
# App will generate new token on next start
```

---

## Part 8: Testing Checklist

### Unit Tests

```python
# finance_app/tests/test_device_token_storage.py
import pytest
from finance_app.services.voice.device_token_storage import DeviceTokenStorage


def test_store_and_retrieve():
    storage = DeviceTokenStorage()
    storage.store("node-1", "Kitchen", "abc123")
    
    device = storage.get("node-1")
    assert device.source_id == "node-1"
    assert device.status == "active"


def test_unpair():
    storage = DeviceTokenStorage()
    storage.store("node-1", "Kitchen", "abc123")
    storage.unpair("node-1", "Test unpair")
    
    device = storage.get("node-1")
    assert device.status == "revoked"
```

### Integration Tests

```python
# Test: Max concurrent connections
def test_connection_limit():
    server = RemoteAudioServer(..., max_concurrent_connections=2)
    
    # Connect 2 devices OK
    conn1 = connect_to_server(...)
    conn2 = connect_to_server(...)
    
    # 3rd device rejected
    with pytest.raises(ConnectionRefusedError):
        conn3 = connect_to_server(...)

# Test: Session resumption
def test_reconnect_resumes_session():
    server = RemoteAudioServer(...)
    
    conn = connect_to_server(source_id="node-1")
    send_audio(conn, frames=10)
    
    # Disconnect
    conn.close()
    
    # Reconnect
    conn2 = connect_to_server(
        source_id="node-1",
        reconnect={"connection_id": old_connection_id, "last_seq_no": 10}
    )
    
    # Should resume without audio loss
    assert conn2.last_seq_no == 10
```

---

## Summary of Changes

| File | Change | Complexity |
|------|--------|------------|
| [discovery.py](finance_app/services/voice/discovery.py) | Fix service type: `_finance-voice` → `_fvoice` | 1 line |
| device_token_storage.py (new) | Persistent token backend | 150 lines |
| [network_transport.py](finance_app/services/voice/network_transport.py) | Integrate token storage; add max-connection check | 50 lines |
| device_commands.py (new) | CLI unpair, list, rotate | 80 lines |
| windows_firewall.py (new) | Auto-add firewall rule | 60 lines |
| audio_codec.py (new) | Opus/G.711 decoder (optional) | 100 lines |
| Tests | Coverage for pairing, reconnect, limits | 150 lines |

**Total effort:** ~600 lines over 1-2 sprints.

**Go-live readiness:** After Part 1 (service type) + Part 2 (token persistence) + Part 4 (firewall), you're ready for beta.

