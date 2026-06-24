# LAN Remote Audio Assistant Network Architecture Guide

**Status:** Production-ready recommendations based on current implementation review  
**Last Updated:** 2026-06-24  
**Scope:** Single-LAN deployment (optional internet backup for audio processing/LLM fallback)

---

## Executive Summary

Your current implementation is **architecturally sound**. The hub-and-spoke design with persistent TLS connections, mDNS-SD discovery, and phase-gated security hardening aligns with enterprise patterns (AirPlay 2, Google Cast, Amazon Alexa private cloud).

**Recommended status:** Proceed with Phase 3 deployment (persistent connections + session resumption). Defer Phase 5 (replay/MITM tests + operational hardening) to post-launch.

**Quick improvements to prioritize:**
1. Upgrade mDNS service type from `_finance-voice._tcp` (15 chars) to `_fvoice._tcp` (8 chars) to prevent BadTypeInNameException
2. Implement connection pooling (keep-alive + graceful degradation) for multi-room scenarios
3. Add explicit firewall profile rules for Windows Defender (allow-by-app)
4. Define failover for mixed LAN/internet ASR routing
5. Add device rotation/unpair operational command in CLI

---

## 1. Discovery Protocol: mDNS/Zeroconf (Validated ✓)

### Current Implementation ✓
- **Service type:** `_finance-voice._tcp.local.` (main PC receiver)  
- **Sender service:** `_fvoice-sender._tcp.local.` (remote devices)
- **Properties advertised:** `source_id`, `device_name`, `role`, `protocol_version`
- **Non-advertised:** `auth_token` (security hardening ✓)

### Issue & Fix

**ISSUE:** `_finance-voice` is 15 characters. mDNS service type labels **must be ≤ 15 characters**, and some implementations (Java, Bonjour) throw `BadTypeInNameException` on exactly 15.

**RECOMMENDED FIX:**
```
Current:  _finance-voice._tcp.local.   [15 chars] → FAILS on strict parsers
Better:   _fvoice._tcp.local.          [8 chars]  → COMPATIBLE
Alt:      _voice-ai._tcp.local.        [9 chars]  → READABLE & SAFE
```

**Action:** Update [discovery.py](finance_app/services/voice/discovery.py):
```python
SERVICE_TYPE_RECEIVER = "_fvoice._tcp.local."  # Changed from _finance-voice
SERVICE_TYPE_SENDER = "_fvoice-sender._tcp.local."  # OK: 13 chars
```

### Why mDNS for discovery? ✓

| Criterion | mDNS | Zeroconf | Multicast DNS |
|-----------|------|----------|---------------|
| **Zero-config** | ✓✓ | ✓✓ (same thing) | ✓✓ |
| **LAN-only** | ✓ | ✓ | ✓ |
| **Firewall-friendly** | ✓ (UDP 5353 multicast) | ✓ | ✓ |
| **Device count scale** | 1-100 devices | 1-100 devices | 1-100 devices |
| **Latency** | 100-500 ms probe | 100-500 ms probe | Same |
| **Battery drain** | Low (periodic probe) | Low | Low |

**Verdict:** Correct choice. mDNS is the de-facto standard for LAN discovery (Chromecast, Airplay, Bonjour).

### Operational controls

Add mDNS disable flag for airgapped networks:
```python
FINANCE_APP_MDNS_ENABLED = os.getenv("FINANCE_APP_MDNS_ENABLED", "true").lower() in {"true", "yes", "1"}
```

If disabled, require manual IP/port config file.

---

## 2. Connection Protocol: TLS 1.3 + TCP (Recommended ✓)

### Current Implementation ✓
- **Transport:** Persistent TCP with optional TLS 1.2+
- **Protocol:** Newline-delimited JSON on framed binary stream
- **Heartbeat:** Ping/pong keep-alive

### Decision Matrix: TCP vs UDP vs WebSocket

```
╔═══════════════╦════════════════╦═══════════════╦═════════════════╗
║ Criterion     ║ UDP (RTP-based)║ TCP (current) ║ WebSocket       ║
╠═══════════════╬════════════════╬═══════════════╬═════════════════╣
║ Reliability   ║ NO (lossy)     ║ YES (ordered) ║ YES (ordered)   ║
║ Latency       ║ 10-50ms lowest ║ 20-80ms       ║ 30-100ms (TLS)  ║
║ Firewall easy ║ NO (strict)    ║ YES (NAT-ok)  ║ YES (port 80/443)║
║ LAN native    ║ YES (RTP std)  ║ YES           ║ Not native LAN  ║
║ Complexity    ║ HIGH (resend,  ║ LOW (kernel)  ║ MEDIUM (framing)║
║               ║  jitter buf)   ║               ║                 ║
║ TLS support   ║ DTLS (rare)    ║ Standard TLS  ║ Standard TLS    ║
║ Python easy   ║ MEDIUM (custom)║ EASY (ssl)    ║ EASY (websockets)║
╚═══════════════╩════════════════╩═══════════════╩═════════════════╝
```

**VERDICT:** TCP is correct for LAN home assistant. Rationale:

1. **Reliability > Latency** — home device pairing tolerance is 100-500ms; UDP complexity not justified
2. **Firewall transparency** — TCP traverses corporate/guest Wi-Fi better
3. **In-band control** — heartbeat, pairing, and audio share same connection
4. **Python simplicity** — `ssl.wrap_socket()` requires 1 import vs RTP jitter buffer implementation

### Recommended frame format

Your current **newline-delimited JSON** is good. Add length-prefix for binary safety:

```json
{
  "type": "audio",
  "connection_id": "node-1-1719240000000",
  "seq_no": 42,
  "audio_b64": "...",
  "sent_at_ms": 1719240123456,
  "sample_rate": 16000,
  "codec": "pcm16"
}
```

For high-volume audio, consider **msgpack** (binary framing) instead of base64:
- Current: ~16 KB/s audio → ~21 KB/s on wire (base64 overhead)
- Msgpack: ~16 KB/s audio → ~16.2 KB/s on wire (binary)
- Savings: ~4-5% bandwidth per 10 devices

**Action:** Add feature flag:
```python
FINANCE_APP_AUDIO_ENCODING = os.getenv("FINANCE_APP_AUDIO_ENCODING", "base64")  # or "msgpack"
```

### TLS Configuration

**Minimum:** TLS 1.2  
**Recommended:** TLS 1.3  
**Reason:** TLS 1.3 has 1-RTT handshake vs 2-RTT for 1.2; for persistent connections, insignificant, but better for reconnect scenarios.

```python
context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.minimum_version = ssl.TLSVersion.TLSv1_3  # or TLSv1_2 for older devices
context.maximum_version = ssl.TLSVersion.TLSv1_3
context.options |= ssl.OP_NO_COMPRESSION  # Prevent CRIME attacks
```

---

## 3. Pairing Mechanism: Secure Device Registration (Recommended ✓)

### Current Implementation ✓

**Phase 1 (Current):**
- One-time 6-8 character code derived from `HMAC(token, source_id + pairing_session_id)`
- Code display on main PC UI during 30-60 second window
- Remote device operator enters code

**Phase 2 (Planned):**
- Add `pairing_session_id` to prevent cross-session attacks
- Compute: `code = HMAC-6(token, source_id + pairing_session_id)`
- Expire session after 30 seconds

### Issues & Improvements

1. **Token storage:** Currently per-config, regenerates on app restart → lost pairing
   - **Fix:** Persist tokens to `~/.finance-voice/paired-device-tokens.json` (already done ✓)

2. **Token rotation:** No CLI to rotate/revoke compromised device
   - **Fix:** Add command:
   ```bash
   python -m finance_app.cli unpair --device-id node-1 --reason "Lost device"
   python -m finance_app.cli rotate-token --new-hash
   ```

3. **QR code support:** For easier pairing on small-screen devices
   - **Fix:** Encode pairing code + connection details as QR:
   ```
   fvoice://pair?token=ABCD1234&session_id=sess-xyz&ttl=30
   ```
   - Scan with phone camera → opens pairing UI

4. **Device limit:** No max-device check (prevent brute-force pair flooding)
   - **Fix:**
   ```python
   MAX_PAIRED_DEVICES = 16  # Home + office + guest
   if len(paired_tokens) >= MAX_PAIRED_DEVICES:
       raise PairingLimitExceeded(f"Max {MAX_PAIRED_DEVICES} devices")
   ```

### Pairing state machine

```
[Idle] 
  ↓
User clicks "Pair New Device" 
  ↓
[PairingActive] ← session_id generated, code shown (30s TTL)
  ↓
Remote device enters code, computes HMAC
  ↓
Main PC validates:
  ✓ code matches HMAC(token, source_id + session_id)
  ✓ session_id in cache and not expired
  ✓ source_id not already paired
  ↓
[Paired] ← store token to persistent JSON
  ↓
Connect with persistent TLS
```

### Recommended token format

Current: Unstructured random string  
**Better:** Include metadata for operational clarity:

```json
{
  "source_id": "node-1",
  "device_name": "Kitchen Echo",
  "token_hash": "sha256:abc123...",
  "token_created_at": "2026-06-24T10:30:00Z",
  "token_rotated_at": null,
  "paired_at": "2026-06-24T10:35:15Z",
  "last_seen": "2026-06-24T15:45:00Z",
  "status": "active",  // or "suspended", "revoked"
  "notes": ""
}
```

**Action:** Update [remote_config.py](finance_app/services/voice/remote_config.py) to persist metadata.

---

## 4. Connection Persistence & Reconnection (Phase 3 ✓)

### Current Implementation ✓

Your Phase 3 plan is solid:
- **Session resumption metadata:** `connection_id`, `last_seq_no`, `created_at`
- **Heartbeat:** Ping/pong keep-alive
- **Reconnect:** Exponential backoff + jitter

### Detailed reconnection strategy

**Scenario 1: Network hiccup (< 5 seconds)**
- Client detects socket close
- Immediately reconnect to same endpoint (no delay)
- Resume with `last_seq_no` from lost session
- Expected downtime: 100-500ms (imperceptible)

**Scenario 2: Wi-Fi roaming (5-30 seconds)**
- Client retries with exponential backoff: 100ms → 200ms → 400ms → 800ms → 2s → 5s
- After 3 attempts, show UI notification "Reconnecting..."
- Resume with session resumption
- Expected downtime: 2-5 seconds

**Scenario 3: Device moved off LAN (> 60 seconds)**
- Client gives up after max-retries (12 attempts = ~15 seconds)
- Clear session from server after 120 seconds inactivity
- User must re-pair on return
- Expected behavior: "Device offline"

### Recommended backoff formula

```python
def calculate_backoff_ms(attempt: int, jitter_seed: str) -> int:
    """Exponential backoff with jitter.
    
    attempt 0: 50-150ms
    attempt 1: 100-300ms
    attempt 2: 200-600ms
    attempt 3: 400-1200ms
    attempt 4: 800-2400ms
    ... caps at 10s
    """
    base_ms = min(50 * (2 ** attempt), 10000)
    jitter_factor = hash(f"{jitter_seed}{attempt}") % 100 / 100  # deterministic jitter
    return int(base_ms * (0.5 + jitter_factor))
```

### Session resumption edge cases

| Scenario | Action | Code |
|----------|--------|------|
| Client reconnects with OLD `connection_id` + `last_seq_no` | Resume | Accept packets >= last_seq_no |
| Server has discarded old session (stale > 120s) | Restart | hello_ack with new connection_id |
| Client sends duplicate seq_no | Deduplicate | Drop, log telemetry |
| Client advances seq_no by > 1000 (jumped frames) | Flag loss | Backfill or request retransmit |

**Action:** Implement in [network_transport.py](finance_app/services/voice/network_transport.py) `_get_session()` and `_update_session_activity()`.

---

## 5. Multiple Simultaneous Remote Devices (Concurrency Model ✓)

### Current Implementation ✓

Your `SessionResumption` per-device design is correct. Let's scale it:

```
Main PC
├─ Server socket (port 9876)
│  ├─ Thread: RemoteVoiceServer (listener)
│  ├─ Handler 1: kitchen-echo (connection_id: node-1-xxx)
│  ├─ Handler 2: living-room (connection_id: node-2-xxx)
│  ├─ Handler 3: bedroom (connection_id: node-3-xxx)
│  └─ Handler 4: garage (connection_id: node-4-xxx)
│
├─ AudioPipeline (single instance, thread-safe)
│  ├─ StreamMux: multiplexes 4 input streams
│  │  (kitchen-echo audio frames + source_id tag)
│  ├─ VAD + Endpointing
│  ├─ ASR (Faster-Whisper)
│  └─ Output: (transcript, source_id, confidence)
│
└─ Assistant State (session-scoped)
   ├─ Session 1: (room="kitchen", user="Jack")
   ├─ Session 2: (room="living-room", user="Sarah")
   ├─ Session 3: (room="bedroom", user="")
   └─ Session 4: (room="garage", user="")
```

### Concurrency limits

**Recommended max concurrent connections:**
- 4 on home Wi-Fi (channel capacity ~50 Mbps, audio ~64 kbps/device)
- 8 on wired LAN (100 Mbps+)
- 16 max practical (diminishing returns on single-core ASR)

**Action:** Implement hard limit in [network_transport.py](finance_app/services/voice/network_transport.py):

```python
MAX_CONCURRENT_CONNECTIONS = int(os.getenv("FINANCE_APP_MAX_AUDIO_SOURCES", "4"))

def _accept_connection(self, client_socket):
    with self._session_lock:
        if len(self._active_sessions) >= MAX_CONCURRENT_CONNECTIONS:
            client_socket.sendall(json.dumps({
                "type": "error",
                "reason": f"Server at capacity ({len(self._active_sessions)}/{MAX_CONCURRENT_CONNECTIONS})"
            }).encode() + b"\n")
            client_socket.close()
            return
```

### Thread pool sizing

Python's `ThreadingMixIn` spawns 1 thread per connection. With 4 devices:
- 1 listener thread
- 4 handler threads
- **Total: 5 threads** ← manageable on 4-core CPU

Do NOT pool threads from a shared pool; use separate handler per device (current architecture is right).

### Audio stream multiplexing

Your `voice_pipeline.py` must accept multiple sources. Implement:

```python
class VoicePipelineWithRemoteStreams:
    def __init__(self):
        self.local_stream = None  # Built-in mic
        self.remote_streams: dict[str, RemoteStreamSource] = {}  # source_id -> stream
        self.active_source_id: str | None = None  # Which device was utterance from?
    
    async def process_audio_frame(self, frame: AudioFrame, source_id: str):
        """Called by network_transport on audio packet."""
        if source_id not in self.remote_streams:
            self.remote_streams[source_id] = RemoteStreamSource(source_id)
        
        stream = self.remote_streams[source_id]
        stream.queue_frame(frame)
        
        # Endpointing decides when to commit utterance
        if stream.is_utterance_complete():
            self.active_source_id = source_id
            transcript = await self.asr(stream.get_utterance())
            # ... process with session context
```

---

## 6. Bandwidth Optimization for Continuous Audio (Phase 3)

### Current approach: PCM16 @ 16 kHz

- **Sample size:** 2 bytes (16-bit)
- **Sample rate:** 16,000 Hz
- **Channels:** 1 (mono)
- **Bitrate:** 16,000 × 2 × 8 = 256 kbps uncompressed

**Network cost per device:** ~32 KB/s

### Compression options

| Codec | Bitrate | Latency | Quality | Recommendation |
|-------|---------|---------|---------|-----------------|
| **PCM16 (none)** | 256 kbps | 0ms | Lossless | Baseline; use for dev/testing |
| **Opus (10ms frames)** | 32-64 kbps | 20ms | Transparent (q=10) | ✓ BEST for LAN |
| **G.711 μ-law** | 64 kbps | 0ms | Telephone (3kHz BW) | Legacy; OK for voice-only |
| **FLAC (HQ lossless)** | 96-128 kbps | 20ms | Lossless | Overkill; use for archival |

**RECOMMENDED:** Opus @ 32-48 kbps with 10ms frames.

**Why?**
1. Network: ~4-6 KB/s per device (8× compression)
2. Latency: 10ms frames stay within ASR tolerance (Faster-Whisper chunk size ~960 samples = 60ms)
3. Quality: Opus handles voice intelligibility perfectly; ASR doesn't need full fidelity
4. Standard: Used by Discord, WhatsApp, Google Duo

### Implementation path

**Phase 3a (Current):** PCM16 only  
**Phase 3b (Short-term):** Add Opus codec option  
**Phase 3c (Long-term):** Make Opus default

**Action:** Add to [network_transport.py](finance_app/services/voice/network_transport.py):

```python
SUPPORTED_CODECS = {
    "pcm16": {"decoder": None, "bitrate": 256},  # Raw
    "opus": {"decoder": "librosa.effects.time_stretch", "bitrate": 48},  # Requires opus library
    "g711": {"decoder": "g711.decoder", "bitrate": 64},
}

def decode_audio_frame(self, frame: AudioFrame, codec: str) -> np.ndarray:
    if codec == "opus":
        # pip install opuslib
        import opus
        return opus.decode(frame.payload, frame_size=480, fs=16000)
    elif codec == "pcm16":
        return np.frombuffer(frame.payload, dtype=np.int16)
    # ...
```

### Jitter buffer tuning

Current target: **80ms baseline, adaptive upward**

```
Time ──────────────────────────────────→
Send:  [frame 1] [frame 2] [frame 3] [frame 4] [frame 5]
       t=0       t=20ms    t=40ms    t=60ms    t=80ms
         ↓
Recv:  [20ms]    [40ms]    [35ms] ← late  [65ms]    [95ms]
       ──────────────────────────────────────────────────
Buff:  max jitter = 30ms (frame 3 arrived 5ms late)
      
Recommend buffer = 80ms + 30ms = 110ms
```

Target SLO: p95 jitter buffer depth < 150ms.

---

## 7. LAN-Only vs Internet Backup Considerations

### Threat model

```
┌─ MAIN PC ────────────────────────────────────┐
│  ✓ Local ASR (Faster-Whisper)                │
│  ✓ Local LLM (Ollama)                        │
│  ✓ Local audio storage                       │
│  ✓ Fully offline-capable                     │
│                                              │
│  Optional internet:                          │
│  • Backup ASR (Google Speech-to-Text API)    │
│  • Cloud LLM (Claude API)                    │
│  • Telemetry / crash logs                    │
└────────────────────────────────────────────────┘
       ↑                  ↑
      LAN                INTERNET
      (required)         (optional failover)
```

### Recommended failover logic

**ASR Failover:**
```python
async def transcribe(audio_frames, device_source):
    # Step 1: Try local Faster-Whisper
    try:
        result = await asr_faster_whisper.transcribe(audio_frames, timeout=5s)
        telemetry.record("asr_provider", "faster-whisper")
        return result
    except (TimeoutError, cuda_error):
        pass  # Fall through
    
    # Step 2: Try cloud API (if internet available)
    if has_internet_connectivity():
        try:
            result = await asr_google.transcribe(audio_frames, timeout=10s)
            telemetry.record("asr_provider", "google-speech")
            telemetry.alert("asr_local_degraded", device_source)  # Wake owner
            return result
        except ConnectionError:
            pass  # Continue to error
    
    # Step 3: Error state
    raise TranscriptionFailed(f"No ASR available for {device_source}")
```

**LLM Failover:**
```python
async def invoke_assistant(transcript):
    # Try local Ollama
    try:
        response = await ollama_client.generate(transcript, timeout=3s)
        telemetry.record("llm_provider", "ollama")
        return response
    except timeout:
        pass
    
    # Try cloud Claude
    if has_internet() and user_consented_to_cloud():
        try:
            response = await claude_api.generate(transcript, timeout=5s)
            telemetry.record("llm_provider", "claude")
            telemetry.alert("llm_local_degraded", device=None)
            return response
        except Exception:
            pass
    
    # Error
    raise AssistantUnavailable()
```

### Privacy implications

**LAN-only (recommended default):**
- ✓ No audio leaves house
- ✓ No transcripts uploaded
- ✓ No IP logs from cloud providers
- ✗ Limited to local model quality

**With internet backup:**
- ✓ Better ASR/LLM quality
- ✗ Transcript sent to Google/Anthropic
- ✗ Requires consent + privacy policy
- ✗ Billing exposure if API key leaked

**Action:** Add explicit user opt-in:

```python
FINANCE_APP_ALLOW_CLOUD_ASR = os.getenv("FINANCE_APP_ALLOW_CLOUD_ASR", "false").lower() in {"true", "yes"}
FINANCE_APP_ALLOW_CLOUD_LLM = os.getenv("FINANCE_APP_ALLOW_CLOUD_LLM", "false").lower() in {"true", "yes"}
```

And UI checkbox: "[ ] Use cloud ASR if local unavailable (shares audio with Google)"

---

## 8. Network Interface Binding & Firewall Implications

### Binding strategy

**Option 1: Bind to all interfaces (current default)**
```python
host = "0.0.0.0"
```
- ✓ Accessible from any device on subnet
- ✗ Accessible from WAN if port forwarded (security risk)

**Option 2: Bind to local interface only (RECOMMENDED)**
```python
host = "127.0.0.1"
```
- ✓ Immune to LAN attacks
- ✗ Only localhost; won't work for remote devices

**Option 3: Bind to specific LAN interface (BEST)**
```python
local_ipv4 = resolve_local_ipv4()  # e.g., 192.168.1.100
host = local_ipv4
```
- ✓ LAN-accessible
- ✓ Not on WAN
- ✓ Works across device restarts (IP stable via DHCP reservation)

**Action:** Use Option 3 in [network_transport.py](finance_app/services/voice/network_transport.py):

```python
def __init__(self, host: str | None = None, ...):
    if host is None:
        host = resolve_local_ipv4()  # Already implemented ✓
    self.host = host
    self._log(f"Binding to {self.host}:9876")
```

### Windows Firewall Rules

**For app users, firewall blocks inbound by default.** Add rules:

**Method 1: Netsh (admin-less; user can grant via UAC)**
```powershell
# One-time setup
& netsh advfirewall firewall add rule `
    name="Finance Voice Receiver" `
    dir=in `
    action=allow `
    program="C:\Users\%USERNAME%\AppData\Local\finance-voice\main.exe" `
    protocol=tcp `
    localport=9876
```

**Method 2: Windows Defender Firewall UI (users do manually)**
- Settings → Privacy & Security → Firewall & network protection
- "Allow an app through firewall"
- Check "Finance Voice Receiver" for Private networks (NOT public)

**Method 3: Deploy via Group Policy (IT managed)**
```xml
<Firewall>
  <LocalFirewallRules>
    <Rule name="FinanceVoiceReceiver" action="allow" protocol="tcp" port="9876"/>
  </LocalFirewallRules>
</Firewall>
```

**Recommended:** Method 1 (Netsh) on first app launch + settings UI option to re-run.

### Port assignment

**Current:** Port 9876 (arbitrary)  
**Should it be static?** Yes.

**Why:**
1. Users whitelist in firewall rules → must be stable
2. mDNS advertises port → devices discover automatically
3. Hardcoding enables multi-instance debugging (one per port)

**Port range recommendation:**

```
9876-9890   Reserved for Finance Voice Receiver
  9876      Main receiver (phase 1-3)
  9877-9890 Reserved for future multi-PC mesh
```

**Action:** Add to [config.py](finance_app/config.py):

```python
DEFAULT_VOICE_RECEIVER_PORT = 9876
DEFAULT_VOICE_SENDER_PORT_RANGE = (9877, 9890)
```

### Port forwarding warning

**DO NOT port-forward port 9876 to WAN.** If user wants remote access:

1. **Option A: Manual VPN** (recommended)
   - User sets up WireGuard/Tailscale on main PC + remote devices
   - Remote devices connect via VPN tunnel to main PC local IP
   - App sees all as LAN (no code changes needed)

2. **Option B: Cloud relay** (future; not now)
   - Send audio via encrypted WebSocket to relay server (e.g., your backend)
   - Relay proxies to main PC via authenticated channel
   - Requires: certificate pinning, rate limiting, audit logging

**Action:** Add to docs:
```markdown
## Accessing from outside home?

⚠️ DO NOT port-forward port 9876 to the internet. Instead:

1. Install WireGuard or Tailscale on both devices
2. Connect remote device via VPN to your home network
3. All traffic stays encrypted over internet, appears as LAN locally
```

---

## 9. Handling Device Connect/Disconnect During Active Sessions

### State machine

```
[Idle] 
  ↓ Device sends hello
[Listening] ← new remote audio stream, audio frames queue up
  ↓ Endpointing detects utterance boundary
[Utterance Ready] ← frame sequence committed
  ↓ ASR processes
[Transcribed] ← final transcript available
  ↓ Assistant decision
[Processing] ← command execution (e.g., update budget)
  ↓
[Complete] ← action done, response sent back
  ↓
[Idle] ← ready for next utterance

Device disconnect scenarios:
1. Mid-utterance (e.g., Wi-Fi drops during speech) → ABORT utterance
2. Post-transcription (e.g., drops during assistant processing) → DEDUP via idempotency_id
3. Post-execution (e.g., TLS reset after action committed) → USER doesn't hear response, but action IS done
```

### Recommended behaviors

| Event | Current Behavior | Recommended | Rationale |
|-------|------------------|-------------|-----------|
| Device disconnects mid-speech | Audio stream ends; utterance dropped | Same (correct) | Incomplete input = no output |
| Device reconnects within 5s | Fresh hello; new session | Resume old session if last_seq_no available | Transparent recovery |
| Device offline > 120s | Session cleared | Session cleared + user notified "Device offline" | Cleanup + UX clarity |
| Action committed, device disconnects before ACK | User hears nothing; server logged success | Log + telemetry alert + retry ACK on reconnect | Eventually consistent |
| Duplicate packet (seq_no repeat) | Applied twice | Deduplicated by seq_no | Idempotency |

### Implementation details

**1. Graceful disconnect on audio mid-utterance**

```python
async def handle_remote_audio_stream(connection_id: str, stream: AsyncIterator):
    try:
        session = SessionResumption(source_id=..., connection_id=connection_id, ...)
        async for frame in stream:
            # Add to utterance buffer
            utterance_buffer.append(frame)
            
            if endpointing.is_complete(utterance_buffer):
                # Commit utterance
                transcript = await asr(utterance_buffer)
                utterance_buffer.clear()
                
    except ConnectionError:
        # Device dropped mid-utterance
        utterance_buffer.clear()  # Discard incomplete utterance
        self._log(f"Device {connection_id} disconnected; discarded {len(utterance_buffer)} frames")
    finally:
        session.mark_closed()
```

**2. Deduplication on reconnect**

```python
async def execute_action(action_id: str, command: str, source_id: str):
    """
    action_id is deterministic hash of (command, source_id, timestamp_bucket).
    Prevents double-execution if ACK is lost.
    """
    
    # Check idempotency log
    if await idempotency_log.exists(action_id):
        result = await idempotency_log.get_result(action_id)
        self._log(f"Replay detected for {action_id}; returning cached result")
        return result
    
    # Execute
    result = await self.assistant.execute(command)
    
    # Store result for TTL=24h (in case device reconnects)
    await idempotency_log.store(action_id, result, ttl="24h")
    
    return result
```

**3. Reconnection with session resumption**

```python
# Device sends on reconnect:
{
    "type": "reconnect",
    "connection_id": "node-1-1719240000000",
    "last_seq_no": 127
}

# Server responds:
{
    "type": "reconnect_ack",
    "connection_id": "node-1-1719240000000",
    "last_seq_no": 127,
    "next_expected_seq_no": 128,
    "buffered_packets_ready": true
}
```

**4. Session cleanup**

```python
async def cleanup_stale_sessions(self):
    """Run every 60 seconds; evict sessions inactive > 120s."""
    while True:
        await asyncio.sleep(60)
        
        with self._session_lock:
            now = time.time()
            stale_ids = [
                cid for cid, session in self._active_sessions.items()
                if (now - session.last_activity_at) > 120
            ]
            
            for cid in stale_ids:
                session = self._active_sessions.pop(cid)
                self._log(f"Evicted stale session {cid} (source={session.source_id})")
                self.on_status(f"Device {session.source_id} offline")
```

**5. Action execution with eventual consistency**

```python
async def send_action_response(connection_id: str, response: dict):
    """Send response; if socket closed, log for retry queue."""
    try:
        await socket.sendall(json.dumps(response).encode() + b"\n")
    except ConnectionError:
        # Device disconnected; store for later delivery
        await retry_queue.put({
            "connection_id": connection_id,
            "response": response,
            "retry_count": 0,
            "enqueued_at": time.time()
        })
        self._log(f"Queued response for {connection_id} (will retry on reconnect)")
```

**Action:** Implement in [network_transport.py](finance_app/services/voice/network_transport.py):

- Add `handle_connection_loss()` method
- Add idempotency log (Redis or simple dict with TTL)
- Add retry queue for responses
- Add `cleanup_stale_sessions()` background task

---

## Port & Protocol Reference Card

| Component | Protocol | Port | Binding | Note |
|-----------|----------|------|---------|------|
| **mDNS Discovery** | UDP | 5353 | Multicast 224.0.0.251:5353 | System-managed; no app binding |
| **Remote Audio Receiver** | TCP/TLS 1.3 | 9876 | 192.168.x.x (local) | Accept persistent connections |
| **Remote Audio Sender** | TCP/TLS 1.3 | 9876 (outbound) | Client ephemeral | Initiate connection to 9876 |
| **Local Mic Input** | Internal | N/A | N/A | pyaudio/sounddevice |
| **Speaker Output** | Internal | N/A | N/A | pydub/wave |
| **Telemetry (optional)** | HTTPS/TLS | 443 | Outbound to cloud | Only if user opt-in |

### Firewall checklist

- [ ] Windows: Allow port 9876 inbound (TCP) for Finance Voice Receiver
- [ ] macOS: System Preferences > Security & Privacy > Firewall > Options > Add Finance Voice Receiver
- [ ] Linux: `sudo ufw allow 9876/tcp`
- [ ] Router: Do NOT port-forward 9876 to WAN
- [ ] Guest Wi-Fi: Ensure remote devices can reach main PC (VLAN isolation may block)

---

## Recommended next steps (priority order)

### ✅ Already Done (Validate)
1. ✓ mDNS-SD discovery (note service type length issue)
2. ✓ TLS 1.3 transport
3. ✓ Phase 1-2 pairing (6-digit code)
4. ✓ Session resumption metadata (Phase 3)
5. ✓ Deduplication by seq_no

### 🔄 Near-term (Next Sprint)
1. **Fix service type name:** `_finance-voice` → `_fvoice` (15→8 chars)
2. **Persist device tokens:** Store to `~/.finance-voice/paired-device-tokens.json` with metadata
3. **Add device management CLI:** `python -m finance_app.cli unpair --device-id node-1`
4. **Implement connection pooling:** Keep-alive + graceful degradation for 4+ devices
5. **Add Opus codec support:** Feature-flag for Opus @ 48kbps

### 📅 Medium-term (Post-launch)
1. **Harden Windows Firewall:** Automate `netsh` rule on first launch
2. **Add QR code pairing:** Encode session URL as QR (phone scan)
3. **Implement cloud failover:** ASR/LLM fallback to Google/Claude APIs (opt-in)
4. **Add telemetry:** Track jitter, reconnect rate, ASR provider usage
5. **Multi-room support:** Session-scoped assistant memory per room

### 🔐 Production (Pre-release)
1. **Security audit:** Penetration test TLS handshake + pairing flow
2. **Replay/MITM tests:** Verify packet sequencing + certificate pinning
3. **Load test:** 8-device concurrent audio + failover behavior
4. **Privacy policy:** Disclose LAN traffic, optional cloud fallback
5. **Operational runbook:** Device unpair, key rotation, incident response

---

## Technical debt to address

| Item | Impact | Effort | Priority |
|------|--------|--------|----------|
| Service type name (15 chars) | Medium (BadTypeInNameException on strict mDNS) | Low (1 line) | HIGH |
| Device token persistence | Low (just lose pairing on restart) | Medium (file I/O + versioning) | MEDIUM |
| Concurrent audio streams > 4 | Medium (audio pipeline must mux sources) | Medium (threading + queue) | MEDIUM |
| Codec compression (Opus) | Low (works at 256 kbps; Opus saves BW) | Medium (decode library) | LOW |
| Cloud failover (ASR/LLM) | Low (LAN-only is fine; optional later) | High (auth + API) | LOW |

---

## Conclusion

Your current architecture is **production-ready** for single-LAN deployment with up to 4 simultaneous devices. The hub-and-spoke model with persistent TLS, mDNS discovery, and phase-gated security is correct and aligned with industry standards (Apple AirPlay 2, Google Cast, Amazon Alexa private).

**Go live with Phase 3** (persistent connections + session resumption). Prioritize:
1. Service type name fix (1 line)
2. Device token persistence + CLI unpair
3. Firewall automation for Windows users

**Defer to post-launch:** cloud failover, Opus compression, multi-room isolation.

**Risk level: LOW.** Your implementation avoids common pitfalls (hardcoded tokens, plaintext audio, no pairing).

