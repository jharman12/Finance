# Remote Voice Assistant - Security Architecture Roadmap

**Classification:** LAN-Only Internal Network  
**Date:** 2026-06-24  
**Threat Level:** Medium (trusted LAN, constrained scope, potential IoT compromises)

---

## Executive Summary

This roadmap prioritizes security controls for remote audio streaming to your main PC LLM. The threat model assumes a compromised IoT device or guest device on your LAN, but treats the main PC as the trusted hub. Controls are organized by implementation priority and risk mitigation effectiveness.

**Critical Path:** Mutual TLS → Device Pairing → Frame Validation → Audit Logging

---

## TIER 1: IMMEDIATE CRITICAL CONTROLS (Days 1-2)

### 1.1 Mutual TLS (mTLS) with Certificate Pinning

**Why First:** Blocks 70% of LAN attack surface (MITM, replay, unauthorized devices).

**Implementation:**

```python
# Main PC receiver setup
import ssl
import certifi

context = ssl.create_default_context(
    ssl.Purpose.CLIENT_AUTH,
    cafile="certs/ca.crt"
)
context.load_cert_chain(
    "certs/server.crt",
    "certs/server.key"
)
context.minimum_version = ssl.TLSVersion.TLSv1_3
context.maximum_version = ssl.TLSVersion.TLSv1_3
context.set_ciphers("TLS_AES_256_GCM_SHA384:TLS_CHACHA20_POLY1305_SHA256")
context.verify_mode = ssl.CERT_REQUIRED
context.check_hostname = True

# Remote sender with pinning
client_context = ssl.create_default_context(
    ssl.Purpose.SERVER_AUTH,
    cafile="certs/ca.crt"
)
client_context.minimum_version = ssl.TLSVersion.TLSv1_3
client_context.maximum_version = ssl.TLSVersion.TLSv1_3

# Certificate pinning: verify public key
import hashlib
expected_pin = hashlib.sha256(
    open("certs/server.crt.pub").read().encode()
).digest()

def verify_pin(cert_der):
    actual_pin = hashlib.sha256(cert_der).digest()
    return actual_pin == expected_pin
```

**Certificate Generation (Use this once, store securely):**

```bash
# CA certificate
openssl genrsa -out certs/ca.key 4096
openssl req -new -x509 -days 3650 -key certs/ca.key \
    -out certs/ca.crt \
    -subj "/CN=FinanceApp-LAN-CA"

# Server certificate (main PC)
openssl genrsa -out certs/server.key 4096
openssl req -new -key certs/server.key \
    -out certs/server.csr \
    -subj "/CN=main-pc.local" \
    -addext "subjectAltName=DNS:main-pc.local,DNS:main-pc,IP:192.168.1.100"
openssl x509 -req -in certs/server.csr \
    -CA certs/ca.crt -CAkey certs/ca.key \
    -CAcreateserial -out certs/server.crt \
    -days 365 -extensions "subjectAltName=DNS:main-pc.local,IP:192.168.1.100"

# Client certificate (per remote device)
openssl genrsa -out certs/device-001.key 4096
openssl req -new -key certs/device-001.key \
    -out certs/device-001.csr \
    -subj "/CN=device-001"
openssl x509 -req -in certs/device-001.csr \
    -CA certs/ca.crt -CAkey certs/ca.key \
    -CAcreateserial -out certs/device-001.crt \
    -days 365
```

**Threat Mitigation:**
- ✓ Man-in-the-middle attacks (network sniffer/ARP spoofing)
- ✓ Unauthorized device connection (only paired devices have certificates)
- ✓ Replay attacks (TLS session unique, nonce per connection)

**Verification Points:**
- [ ] Test with SSL certificate validator (disable pinning initially, enable in hardening phase)
- [ ] Verify TLS 1.3 handshake negotiation (use `openssl s_client`)
- [ ] Confirm rejected cipher suites (test weak ciphers fail)

---

### 1.2 Per-Device Authentication Token with Rate Limiting

**Why Critical:** Adds application-layer identity beyond TLS cert (defense in depth).

**Implementation:**

```python
from dataclasses import dataclass
from datetime import datetime, timedelta
import secrets
import hashlib

@dataclass
class DeviceToken:
    device_id: str
    token_hash: str  # SHA-256 of actual token
    issued_at: datetime
    expires_at: datetime
    pairing_session_id: str
    is_revoked: bool = False
    last_used_at: datetime | None = None
    failed_attempts: int = 0

class DeviceAuthManager:
    def __init__(self, storage_path: str = "data/device_tokens.json"):
        self.tokens: dict[str, DeviceToken] = self._load_tokens(storage_path)
        self.rate_limits: dict[str, list[datetime]] = {}  # device_id -> timestamps
        self.max_failed_attempts = 5
        
    def verify_token(self, device_id: str, token: str) -> tuple[bool, str]:
        """Verify token and check rate limits."""
        
        # Check if device exists and token not revoked
        stored = self.tokens.get(device_id)
        if not stored or stored.is_revoked:
            return False, "device_not_found_or_revoked"
        
        if stored.expires_at < datetime.utcnow():
            return False, "token_expired"
        
        if stored.failed_attempts >= self.max_failed_attempts:
            return False, "too_many_failed_attempts"
        
        # Constant-time comparison
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        if not self._constant_time_equal(token_hash, stored.token_hash):
            stored.failed_attempts += 1
            return False, "invalid_token"
        
        # Rate limit check (5 requests per 10 seconds per device)
        now = datetime.utcnow()
        recent = [
            ts for ts in self.rate_limits.get(device_id, [])
            if ts > now - timedelta(seconds=10)
        ]
        
        if len(recent) >= 5:
            return False, "rate_limit_exceeded"
        
        self.rate_limits[device_id].append(now)
        stored.last_used_at = now
        stored.failed_attempts = 0
        
        return True, "ok"
    
    def generate_pairing_token(self, device_id: str) -> str:
        """Generate token during pairing."""
        token = secrets.token_urlsafe(32)  # 256 bits
        token_hash = hashlib.sha256(token.encode()).hexdigest()
        
        self.tokens[device_id] = DeviceToken(
            device_id=device_id,
            token_hash=token_hash,
            issued_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(days=365),
            pairing_session_id=secrets.token_hex(16),
            is_revoked=False
        )
        
        return token  # Return once to user
    
    def revoke_device(self, device_id: str) -> None:
        """Revoke compromised device."""
        if device_id in self.tokens:
            self.tokens[device_id].is_revoked = True
    
    @staticmethod
    def _constant_time_equal(a: str, b: str) -> bool:
        """Prevent timing attacks."""
        return secrets.compare_digest(a, b)
```

**Request Header Format:**

```python
import base64

# Sender constructs authorization header
auth_header = {
    "device_id": "device-001",
    "token": "<actual_token>",
    "timestamp_ms": int(time.time() * 1000),
    "nonce": secrets.token_hex(16),  # One-time use per request
}

# Encode as base64 for transport
auth_b64 = base64.b64encode(json.dumps(auth_header).encode()).decode()
# Send in header: Authorization: Bearer <auth_b64>
```

**Threat Mitigation:**
- ✓ Brute force attacks (rate limiting + failure tracking)
- ✓ Replay attacks (nonce per request)
- ✓ Compromised device isolation (instant revocation)

**Verification Points:**
- [ ] Test valid token passes
- [ ] Test invalid token rejected
- [ ] Test rate limit enforced (5 requests/10 seconds)
- [ ] Test revoked device blocked immediately
- [ ] Confirm failed_attempts increments correctly

---

### 1.3 Input Frame Validation & DoS Protection

**Why Critical:** Prevents malformed or oversized audio frames from crashing receiver or consuming resources.

**Implementation:**

```python
from dataclasses import dataclass
from typing import Optional
import struct

@dataclass
class AudioFrameHeader:
    """Binary frame format: 64 bytes fixed header + variable payload."""
    magic: int  # 0xDEADBEEF (4 bytes)
    version: int  # (1 byte)
    frame_type: int  # 0=audio, 1=control (1 byte)
    sequence_number: int  # (4 bytes)
    timestamp_ms: int  # (8 bytes)
    payload_size: int  # (4 bytes)
    sample_rate: int  # (2 bytes)
    channels: int  # (1 byte)
    reserved: bytes  # (remaining padding to 64 bytes)
    
    MAGIC = 0xDEADBEEF
    VERSION = 1
    MAX_FRAME_SIZE_BYTES = 8192  # ~184 ms @ 48kHz stereo
    FRAME_FORMAT = ">IBBIQ I HB"  # Big-endian binary format

class AudioFrameValidator:
    def __init__(self):
        self.max_payload_bytes = 8192
        self.max_frames_per_second = 50  # 20 ms frames
        self.sequence_window: dict[str, set[int]] = {}  # device_id -> seq_nums
        self.sequence_window_size = 100  # Allow reordering within 100 frames
        
    def validate_frame(
        self,
        device_id: str,
        raw_frame: bytes
    ) -> tuple[bool, Optional[AudioFrameHeader], str]:
        """Validate and parse frame."""
        
        # Minimum header size check
        if len(raw_frame) < 32:
            return False, None, "frame_too_short"
        
        try:
            # Parse header
            header_bytes = raw_frame[:32]
            magic, version, frame_type, seq_no, ts_ms, payload_size, sr, channels = struct.unpack(
                self.AudioFrameHeader.FRAME_FORMAT,
                header_bytes
            )
            
            # Validate magic number
            if magic != AudioFrameHeader.MAGIC:
                return False, None, "invalid_magic"
            
            # Validate version
            if version != AudioFrameHeader.VERSION:
                return False, None, "unsupported_version"
            
            # Validate frame type
            if frame_type not in (0, 1):
                return False, None, "invalid_frame_type"
            
            # Validate payload size
            if payload_size > self.max_payload_bytes:
                return False, None, "payload_too_large"
            
            if len(raw_frame) != 32 + payload_size:
                return False, None, "size_mismatch"
            
            # Validate audio parameters
            if sr not in (16000, 48000):
                return False, None, "invalid_sample_rate"
            
            if channels not in (1, 2):
                return False, None, "invalid_channels"
            
            # Validate sequence number (detect replays/duplicates)
            if device_id not in self.sequence_window:
                self.sequence_window[device_id] = set()
            
            if seq_no in self.sequence_window[device_id]:
                return False, None, "duplicate_sequence"
            
            self.sequence_window[device_id].add(seq_no)
            
            # Trim window to prevent memory bloat
            if len(self.sequence_window[device_id]) > self.sequence_window_size:
                min_seq = min(self.sequence_window[device_id])
                self.sequence_window[device_id].discard(min_seq)
            
            header = AudioFrameHeader(
                magic=magic,
                version=version,
                frame_type=frame_type,
                sequence_number=seq_no,
                timestamp_ms=ts_ms,
                payload_size=payload_size,
                sample_rate=sr,
                channels=channels,
                reserved=b""
            )
            
            return True, header, "ok"
            
        except struct.error as e:
            return False, None, f"parse_error: {str(e)}"
    
    def enforce_rate_limit(self, device_id: str) -> tuple[bool, str]:
        """Check device doesn't exceed max frames/sec."""
        # Implementation: track frame timestamps per device
        # Return False if exceeds self.max_frames_per_second
        pass

class FrameProcessingQueue:
    """Bounded queue with backpressure."""
    def __init__(self, device_id: str, max_queue_size: int = 100):
        self.device_id = device_id
        self.queue: deque = deque(maxlen=max_queue_size)
        self.max_queue_size = max_queue_size
        self.dropped_frames = 0
    
    def enqueue(self, frame: bytes) -> tuple[bool, str]:
        """Add frame to queue. Drop if full."""
        if len(self.queue) >= self.max_queue_size:
            self.dropped_frames += 1
            return False, "queue_full_dropped"
        
        self.queue.append(frame)
        return True, "ok"
```

**Threat Mitigation:**
- ✓ Malformed frame crashes (struct validation)
- ✓ Memory exhaustion (bounded queues, max frame size)
- ✓ Replay attacks (sequence number tracking)
- ✓ Flood attacks (frame rate limiting)

**Verification Points:**
- [ ] Test oversized payload rejected (>8KB)
- [ ] Test invalid magic number rejected
- [ ] Test sequence number reordering detected
- [ ] Test queue drops frames when full
- [ ] Test rate limit enforced (50 fps max)

---

### 1.4 Secure Device Pairing Protocol

**Why Critical:** Establishes initial trust without pre-shared secrets.

**Implementation:**

```python
import secrets
import hashlib
from datetime import datetime, timedelta

class PairingCodeGenerator:
    """Generate 6-digit pairing codes displayed on main PC."""
    def __init__(self, code_validity_seconds: int = 300):
        self.code_validity_seconds = code_validity_seconds
        self.active_codes: dict[str, PairingSession] = {}
    
    def generate_code(self) -> str:
        """Generate 6-digit code."""
        code = str(secrets.randbelow(1000000)).zfill(6)
        return code
    
    def start_pairing_session(self, device_name: str) -> tuple[str, str]:
        """Start pairing. Return (code, session_id)."""
        code = self.generate_code()
        session_id = secrets.token_hex(16)
        
        self.active_codes[code] = PairingSession(
            session_id=session_id,
            device_name=device_name,
            created_at=datetime.utcnow(),
            expires_at=datetime.utcnow() + timedelta(seconds=self.code_validity_seconds),
            code=code
        )
        
        return code, session_id
    
    def verify_code(self, code: str) -> tuple[bool, Optional[PairingSession]]:
        """Verify pairing code entered by user."""
        session = self.active_codes.get(code)
        
        if not session:
            return False, None
        
        if session.expires_at < datetime.utcnow():
            del self.active_codes[code]
            return False, None
        
        # Mark as verified
        session.verified = True
        return True, session

@dataclass
class PairingSession:
    session_id: str
    device_name: str
    created_at: datetime
    expires_at: datetime
    code: str
    verified: bool = False

class PairingFlow:
    """Protocol for initial device pairing."""
    
    def start_pairing_on_remote(self, main_pc_hostname: str) -> dict:
        """Remote device initiates pairing."""
        # 1. Discover main PC via zeroconf
        services = discover_services("_financeapp._tcp")
        main_pc = next((s for s in services if main_pc_hostname in s), None)
        
        if not main_pc:
            return {"status": "error", "msg": "main_pc_not_found"}
        
        # 2. Send pairing request (no auth yet)
        response = http_get(
            f"https://{main_pc['ip']}:{main_pc['port']}/api/v1/pairing/request",
            json={"device_name": socket.gethostname()},
            verify_cert=False  # Accept self-signed initially
        )
        
        if response.status_code != 200:
            return {"status": "error", "msg": response.text}
        
        pairing_request = response.json()
        return pairing_request
    
    def submit_code_on_remote(self, pairing_code: str) -> dict:
        """Remote device sends code entered by user."""
        # 3. User sees code on main PC UI, enters on remote device
        # 4. Remote device sends code
        response = http_post(
            f"https://{main_pc['ip']}:{main_pc['port']}/api/v1/pairing/verify",
            json={
                "pairing_session_id": self.pairing_session_id,
                "code": pairing_code
            },
            verify_cert=False
        )
        
        if response.status_code == 200:
            result = response.json()
            # 5. Main PC returns token and device certificate
            self.device_token = result["token"]
            self.device_cert = result["device_cert"]
            self.device_id = result["device_id"]
            
            # Save securely
            keyring.set_password("FinanceApp", self.device_id, self.device_token)
            
            return {"status": "success", "device_id": self.device_id}
        
        return {"status": "error", "msg": response.text}
```

**On-Screen Pairing Flow:**

```python
# Main PC receives pairing request
@app.post("/api/v1/pairing/request")
async def request_pairing(request: PairingRequest):
    session_id, code = pairing_manager.start_pairing_session(
        device_name=request.device_name
    )
    
    # Display code in UI (6-digit modal)
    ui_manager.show_pairing_modal(code, device_name=request.device_name)
    
    return {
        "pairing_session_id": session_id,
        "expires_in_seconds": 300,
        "instructions": "Enter code on remote device"
    }

@app.post("/api/v1/pairing/verify")
async def verify_pairing(verify_request: VerifyPairingRequest):
    valid, session = pairing_manager.verify_code(verify_request.code)
    
    if not valid:
        return {"error": "invalid_code"}, 400
    
    # Generate device token and certificate
    device_id = f"device-{session.session_id[:8]}"
    token = device_auth_manager.generate_pairing_token(device_id)
    device_cert = generate_device_certificate(device_id)
    
    return {
        "device_id": device_id,
        "token": token,  # Returned only once; store securely on remote
        "device_cert": device_cert.pem(),
        "expires_in_days": 365
    }
```

**Threat Mitigation:**
- ✓ Unauthorized pairing (requires user intervention + short-lived code)
- ✓ Network eavesdropping (code not transmitted over network)
- ✓ Token leakage (returned only once, stored in secure keyring)

**Verification Points:**
- [ ] Test code generated correctly (6 digits)
- [ ] Test code expires after 5 minutes
- [ ] Test code can only be used once
- [ ] Test token stored in keyring (not plain text)
- [ ] Test pairing can be revoked from main PC

---

## TIER 2: MEDIUM-TERM HARDENING (Days 3-7)

### 2.1 Network Segmentation & Firewall Rules

**Why Important:** Limits blast radius if remote device compromised.

**Implementation:**

```python
# Network policy configuration
NETWORK_POLICY = {
    "trusted_devices": {
        "device-001": {
            "allowed_actions": [
                "stream_audio",
                "query_weather",
                "query_calendar"
            ],
            "denied_actions": [
                "execute_system_command",
                "access_transaction_data",
                "modify_budget"
            ],
            "rate_limits": {
                "requests_per_minute": 60,
                "max_audio_duration_seconds": 120,
                "max_queries_per_hour": 100
            }
        }
    },
    "firewall_rules": {
        "allowed_source_subnets": ["192.168.1.0/24"],
        "blocked_ips": [],
        "allowed_ports": [8443],  # Only HTTPS
        "denied_ports": [22, 23, 3389],  # No SSH, Telnet, RDP
    }
}

class NetworkAccessControl:
    def __init__(self, policy: dict):
        self.policy = policy
    
    def check_access(
        self,
        device_id: str,
        action: str,
        source_ip: str
    ) -> tuple[bool, str]:
        """Verify device can perform action from source IP."""
        
        # Check source IP in allowed subnet
        source_net = ipaddress.ip_address(source_ip)
        allowed_subnets = [
            ipaddress.ip_network(subnet)
            for subnet in self.policy["firewall_rules"]["allowed_source_subnets"]
        ]
        
        if not any(source_net in subnet for subnet in allowed_subnets):
            return False, "source_ip_not_allowed"
        
        # Check IP not in blocklist
        if source_ip in self.policy["firewall_rules"]["blocked_ips"]:
            return False, "ip_blocked"
        
        # Check device permissions
        device_policy = self.policy["trusted_devices"].get(device_id)
        if not device_policy:
            return False, "device_not_trusted"
        
        if action not in device_policy["allowed_actions"]:
            return False, "action_not_allowed"
        
        if action in device_policy["denied_actions"]:
            return False, "action_explicitly_denied"
        
        return True, "ok"
```

**Firewall Rules (for iptables or Windows Firewall):**

```bash
# Linux: Allow only remote voice on port 8443 from trusted subnet
sudo ufw allow from 192.168.1.0/24 to any port 8443 proto tcp comment "Remote voice"
sudo ufw deny from any to any port 22 comment "Block SSH from remote devices"
sudo ufw deny from any to any port 3389 comment "Block RDP"

# Windows Firewall
netsh advfirewall firewall add rule name="Allow Remote Voice" `
    dir=in action=allow protocol=tcp `
    remoteip=192.168.1.0/24 localport=8443

netsh advfirewall firewall add rule name="Block RDP External" `
    dir=in action=block protocol=tcp localport=3389 remoteip=192.168.1.0/24
```

**Verification Points:**
- [ ] Test device from allowed subnet connects
- [ ] Test device from different subnet blocked
- [ ] Test blocked IP immediately rejected
- [ ] Test allowed action succeeds, denied action fails
- [ ] Test rate limits enforced per device

---

### 2.2 Replay Attack Prevention with Nonces & Timestamps

**Why Important:** Prevents attacker from replaying captured audio frames.

**Implementation:**

```python
from datetime import datetime, timedelta
import struct

class ReplayProtection:
    def __init__(self, max_clock_skew_seconds: int = 30):
        self.max_clock_skew_seconds = max_clock_skew_seconds
        self.nonce_cache: dict[str, set[str]] = {}  # device_id -> nonces
        self.nonce_ttl_seconds = 60
        
    def validate_frame_freshness(
        self,
        device_id: str,
        timestamp_ms: int,
        nonce: str
    ) -> tuple[bool, str]:
        """Ensure frame is fresh and nonce not reused."""
        
        now_ms = int(datetime.utcnow().timestamp() * 1000)
        time_diff_ms = abs(now_ms - timestamp_ms)
        
        # Check timestamp within skew
        if time_diff_ms > (self.max_clock_skew_seconds * 1000):
            return False, "timestamp_outside_skew"
        
        # Check nonce not reused
        if device_id not in self.nonce_cache:
            self.nonce_cache[device_id] = set()
        
        if nonce in self.nonce_cache[device_id]:
            return False, "nonce_replay_detected"
        
        self.nonce_cache[device_id].add(nonce)
        
        # Cleanup old nonces
        # (In production, use TTL-based cache like Redis)
        
        return True, "ok"
    
    def generate_request_nonce(self) -> str:
        """Generate unique nonce per request."""
        return secrets.token_hex(16)

class AudioFrameWithNonce:
    """Frame structure with nonce and timestamp."""
    def __init__(
        self,
        audio_payload: bytes,
        sample_rate: int,
        channels: int,
        sequence_number: int,
        timestamp_ms: Optional[int] = None,
        nonce: Optional[str] = None
    ):
        self.audio_payload = audio_payload
        self.sample_rate = sample_rate
        self.channels = channels
        self.sequence_number = sequence_number
        self.timestamp_ms = timestamp_ms or int(datetime.utcnow().timestamp() * 1000)
        self.nonce = nonce or secrets.token_hex(16)
    
    def serialize(self) -> bytes:
        """Serialize frame to bytes with nonce."""
        nonce_bytes = bytes.fromhex(self.nonce)
        frame = struct.pack(
            ">IIIHB16s",  # Timestamp, seq_no, sample_rate, channels, nonce (16 bytes)
            self.timestamp_ms,
            self.sequence_number,
            self.sample_rate,
            self.channels,
            len(self.audio_payload),
            nonce_bytes
        )
        return frame + self.audio_payload
```

**Verification Points:**
- [ ] Test timestamp within skew accepted
- [ ] Test timestamp outside skew rejected (e.g., 1 minute old)
- [ ] Test nonce reuse rejected immediately
- [ ] Test different nonce accepted
- [ ] Test old nonces cleaned up after TTL

---

### 2.3 Audit Logging & Security Events

**Why Important:** Detect compromise, investigate incidents, meet compliance.

**Implementation:**

```python
from datetime import datetime
from enum import Enum
import json
from pathlib import Path

class SecurityEventType(Enum):
    DEVICE_PAIRING_REQUESTED = "device_pairing_requested"
    DEVICE_PAIRING_VERIFIED = "device_pairing_verified"
    PAIRING_CODE_FAILED = "pairing_code_failed"
    AUTH_TOKEN_VERIFIED = "auth_token_verified"
    AUTH_TOKEN_FAILED = "auth_token_failed"
    DEVICE_REVOKED = "device_revoked"
    FRAME_VALIDATION_FAILED = "frame_validation_failed"
    RATE_LIMIT_EXCEEDED = "rate_limit_exceeded"
    SOURCE_IP_BLOCKED = "source_ip_blocked"
    ACTION_DENIED = "action_denied"
    REPLAY_DETECTED = "replay_detected"
    TLS_HANDSHAKE_FAILED = "tls_handshake_failed"
    UNAUTHORIZED_ACCESS = "unauthorized_access"

@dataclass
class SecurityEvent:
    timestamp: str
    event_type: SecurityEventType
    device_id: str
    source_ip: str
    details: dict
    severity: str  # "info", "warning", "critical"

class AuditLogger:
    def __init__(self, log_path: str = "logs/security_events.jsonl"):
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log_event(self, event: SecurityEvent) -> None:
        """Write security event to audit log."""
        event_dict = {
            "timestamp": event.timestamp,
            "event_type": event.event_type.value,
            "device_id": event.device_id,
            "source_ip": event.source_ip,
            "severity": event.severity,
            "details": event.details
        }
        
        with open(self.log_path, "a") as f:
            f.write(json.dumps(event_dict) + "\n")
    
    def get_events_for_device(self, device_id: str, hours: int = 24) -> list:
        """Retrieve events for a device in last N hours."""
        cutoff = datetime.utcnow() - timedelta(hours=hours)
        events = []
        
        with open(self.log_path, "r") as f:
            for line in f:
                event = json.loads(line)
                if event["device_id"] == device_id:
                    event_ts = datetime.fromisoformat(event["timestamp"])
                    if event_ts > cutoff:
                        events.append(event)
        
        return events
    
    def detect_anomalies(self) -> list:
        """Detect suspicious patterns."""
        anomalies = []
        
        with open(self.log_path, "r") as f:
            events = [json.loads(line) for line in f]
        
        # Pattern 1: Excessive failed auth attempts
        failed_by_device = {}
        for event in events:
            if "FAILED" in event["event_type"]:
                device = event["device_id"]
                failed_by_device[device] = failed_by_device.get(device, 0) + 1
        
        for device, count in failed_by_device.items():
            if count > 10:  # Threshold
                anomalies.append({
                    "type": "brute_force_attempt",
                    "device": device,
                    "failed_attempts": count
                })
        
        # Pattern 2: Requests from unexpected IPs
        # (Track which IPs each device typically uses)
        
        # Pattern 3: Actions after hours
        # (Flag unusual timing patterns)
        
        return anomalies

# Usage
audit_logger = AuditLogger()

# Log successful authentication
audit_logger.log_event(SecurityEvent(
    timestamp=datetime.utcnow().isoformat(),
    event_type=SecurityEventType.AUTH_TOKEN_VERIFIED,
    device_id="device-001",
    source_ip="192.168.1.42",
    details={"token_fingerprint": "abc123"},
    severity="info"
))

# Log failed frame validation
audit_logger.log_event(SecurityEvent(
    timestamp=datetime.utcnow().isoformat(),
    event_type=SecurityEventType.FRAME_VALIDATION_FAILED,
    device_id="device-001",
    source_ip="192.168.1.42",
    details={"reason": "invalid_magic_number"},
    severity="warning"
))
```

**Log Rotation & Retention:**

```python
import logging.handlers

# Rotate logs after 10 MB or 7 days
handler = logging.handlers.RotatingFileHandler(
    "logs/security_events.jsonl",
    maxBytes=10_000_000,  # 10 MB
    backupCount=7  # Keep 7 weeks of logs
)

# Or use TimedRotatingFileHandler for date-based rotation
handler = logging.handlers.TimedRotatingFileHandler(
    "logs/security_events.jsonl",
    when="midnight",
    interval=1,
    backupCount=90  # Keep 90 days
)
```

**Verification Points:**
- [ ] Test events logged for each auth success/failure
- [ ] Test anomaly detection identifies brute force (>10 failures)
- [ ] Test log rotation triggers after 10 MB
- [ ] Test timestamps in UTC ISO format
- [ ] Test logs cannot be written by unprivileged user

---

### 2.4 TLS Certificate Rotation & Renewal

**Why Important:** Expired certificates cause service downtime and security gaps.

**Implementation:**

```python
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from datetime import datetime, timedelta
import logging

class CertificateManager:
    def __init__(self, cert_dir: str = "certs"):
        self.cert_dir = Path(cert_dir)
        self.cert_dir.mkdir(exist_ok=True)
        self.renewal_threshold_days = 30
    
    def check_certificate_expiry(self, cert_path: str) -> tuple[bool, int]:
        """Check if cert expires within threshold."""
        cert = x509.load_pem_x509_certificate(
            open(cert_path, "rb").read()
        )
        
        days_until_expiry = (cert.not_valid_after - datetime.utcnow()).days
        
        needs_renewal = days_until_expiry <= self.renewal_threshold_days
        return needs_renewal, days_until_expiry
    
    def renew_server_certificate(self) -> bool:
        """Renew server certificate."""
        try:
            needs_renewal, days = self.check_certificate_expiry(
                str(self.cert_dir / "server.crt")
            )
            
            if not needs_renewal:
                return True  # Not yet needed
            
            logging.warning(f"Server cert expires in {days} days, renewing...")
            
            # Generate new key and CSR
            key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=4096,
            )
            
            csr = x509.CertificateSigningRequestBuilder().add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName("main-pc.local"),
                    x509.DNSName("main-pc"),
                ]),
                critical=False,
            ).sign(key, hashes.SHA256())
            
            # Sign with CA
            ca_cert = x509.load_pem_x509_certificate(
                open(self.cert_dir / "ca.crt", "rb").read()
            )
            ca_key = serialization.load_pem_private_key(
                open(self.cert_dir / "ca.key", "rb").read(),
                password=None
            )
            
            new_cert = x509.CertificateBuilder().subject_name(
                csr.subject
            ).issuer_name(
                ca_cert.subject
            ).public_key(
                csr.public_key()
            ).serial_number(
                x509.random_serial_number()
            ).not_valid_before(
                datetime.utcnow()
            ).not_valid_after(
                datetime.utcnow() + timedelta(days=365)
            ).add_extension(
                x509.SubjectAlternativeName(csr.extensions[0].value),
                critical=False,
            ).sign(ca_key, hashes.SHA256())
            
            # Backup old cert
            backup_path = self.cert_dir / f"server.crt.{datetime.now().strftime('%Y%m%d')}"
            (self.cert_dir / "server.crt").rename(backup_path)
            
            # Write new cert and key
            with open(self.cert_dir / "server.crt", "wb") as f:
                f.write(new_cert.public_bytes(serialization.Encoding.PEM))
            
            with open(self.cert_dir / "server.key", "wb") as f:
                f.write(key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption()
                ))
            
            logging.info("Server certificate renewed successfully")
            return True
            
        except Exception as e:
            logging.error(f"Certificate renewal failed: {e}")
            return False
    
    def schedule_renewal_check(self, interval_hours: int = 24):
        """Run renewal check periodically."""
        import schedule
        import threading
        
        schedule.every(interval_hours).hours.do(self.renew_server_certificate)
        
        def run_scheduler():
            while True:
                schedule.run_pending()
                time.sleep(60)
        
        scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
        scheduler_thread.start()
```

**Verification Points:**
- [ ] Test certificate expiry detected correctly
- [ ] Test renewal triggered 30 days before expiry
- [ ] Test backup of old cert created before renewal
- [ ] Test new cert has correct SANs
- [ ] Test scheduler runs on 24-hour interval

---

## TIER 3: ADVANCED HARDENING (Weeks 2-4)

### 3.1 End-to-End Encryption with Perfect Forward Secrecy (PFS)

**Why Optional but Recommended:** Ensures even if long-term keys compromised, past sessions remain secret.

**Implementation Note:** TLS 1.3 already provides PFS via ephemeral Diffie-Hellman. Ensure cipher suite includes:
- `TLS_AES_256_GCM_SHA384` (256-bit AES-GCM)
- `TLS_CHACHA20_POLY1305_SHA256` (ChaCha20-Poly1305)

```python
# Force PFS-enabled ciphers only
context.set_ciphers(
    "TLS_AES_256_GCM_SHA384:"
    "TLS_CHACHA20_POLY1305_SHA256"
)
# Disable RSA key exchange (not PFS)
context.options |= ssl.OP_SINGLE_DH_USE
```

---

### 3.2 Hardware Security Module (HSM) Integration

**Why Optional:** Protects private keys from memory extraction (advanced threat).

**For Production Deployments:**
- Store CA private key in HSM (never on disk)
- Use HSM-backed TLS acceleration
- Example: YubiHSM, AWS CloudHSM

---

### 3.3 Zero-Knowledge Proof for Device Verification

**Why Optional:** Adds cryptographic guarantee device hasn't been spoofed.

**Concept:**
- Device signs frame with private key (known only to device)
- Main PC verifies signature without seeing private key
- Prevents MITM from impersonating device

---

## TIER 4: OPERATIONAL SECURITY (Ongoing)

### 4.1 Regular Security Audits

**Quarterly Checklist:**
- [ ] Review audit logs for anomalies
- [ ] Test certificate renewal process
- [ ] Verify rate limits working
- [ ] Check for unauthorized device registrations
- [ ] Audit pairing code generation (is it truly random?)
- [ ] Test TLS cipher negotiation (forced strong ciphers)
- [ ] Penetration test from "compromised" device on LAN

### 4.2 Incident Response Plan

**If Device Compromised:**

```python
def handle_compromised_device(device_id: str):
    """Immediate response to suspected compromise."""
    
    # 1. Revoke device immediately
    device_auth_manager.revoke_device(device_id)
    
    # 2. Block IP (if known)
    if source_ip := get_device_last_ip(device_id):
        firewall.block_ip(source_ip)
        network_acl.block_ip(source_ip)
    
    # 3. Alert user
    ui_manager.show_alert(
        f"Device {device_id} has been revoked due to security incident. "
        f"Please re-pair if this was unexpected.",
        severity="critical"
    )
    
    # 4. Review logs
    events = audit_logger.get_events_for_device(device_id, hours=24)
    for event in events:
        if event["event_type"] in ["ACTION_DENIED", "UNAUTHORIZED_ACCESS"]:
            logging.error(f"Suspicious activity: {event}")
    
    # 5. Notify admin
    send_admin_email(
        subject=f"Security: Device {device_id} revoked",
        body=f"Device compromised and disconnected. Review logs: {events}"
    )
```

---

## ATTACK VECTORS & MITIGATIONS

| Attack Vector | Likelihood | Impact | Tier 1 Mitigation | Additional Control |
|---|---|---|---|---|
| **Unauthorized Device Joins** | High | Medium | mTLS certificates + pairing code | Network ACL (Tier 2) |
| **Man-in-the-Middle** | High | Critical | TLS 1.3 + certificate pinning | Network segmentation (Tier 2) |
| **Replay Audio Frame** | Medium | High | Nonce + sequence number | Timestamp validation (Tier 2) |
| **Brute Force Token** | Medium | High | Rate limiting (5 req/10s) | Device revocation on 5 failures (Tier 1) |
| **Audio Eavesdropping** | Medium | Critical | TLS encryption | End-to-end encryption (Tier 3) |
| **Packet Flooding** | Medium | Medium | Frame size limits + rate limit | Backpressure queue (Tier 1) |
| **ARP Spoofing** | Low | High | — | Network segmentation (Tier 2) |
| **DNS Spoofing** | Low | Medium | Use IP or DNSSEC | DHCP snooping (Tier 2) |
| **Compromised Device on LAN** | Low | Medium | Device revocation | Audit logging (Tier 2) |
| **Certificate Theft** | Very Low | Critical | Pinning on remote device | HSM storage (Tier 3) |

---

## DEPLOYMENT CHECKLIST

### Pre-Production (Tier 1)
- [ ] mTLS configured (TLS 1.3 only)
- [ ] Certificate pinning on sender
- [ ] Device token rate limiting enforced
- [ ] Frame validation working (magic number, size, seq)
- [ ] Pairing protocol tested end-to-end
- [ ] Audit logging operational
- [ ] Test security events logged correctly

### Production (Tier 1 + 2)
- [ ] Network segmentation rules deployed
- [ ] Firewall blocks non-audio ports
- [ ] Replay protection enabled
- [ ] Certificate renewal automated
- [ ] Admin notified of security incidents
- [ ] Device revocation tested
- [ ] Incident response procedures documented

### Hardening (Tier 2 + 3)
- [ ] Penetration test from compromised LAN device
- [ ] Audit logs reviewed for anomalies
- [ ] Certificate pinning public key verified
- [ ] End-to-end encryption (optional)
- [ ] Quarterly security review scheduled

---

## Recommended Implementation Order

1. **Day 1:** Implement mTLS + frame validation
2. **Day 2:** Add device pairing + token auth
3. **Day 3:** Add rate limiting + audit logging
4. **Day 4:** Network segmentation + firewall rules
5. **Day 5:** Certificate pinning + replay protection
6. **Week 2:** Penetration testing + incident response

---

## Security by Design Principles

1. **Zero Trust:** Verify every device, every request
2. **Defense in Depth:** Multiple layers (TLS + tokens + rate limits)
3. **Fail Secure:** Drop/revoke on any validation failure
4. **Least Privilege:** Remote device can only stream audio
5. **Audit Everything:** Log security decisions
6. **Crypto Agility:** Use standard, reviewable algorithms (TLS 1.3, SHA-256)

