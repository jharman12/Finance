# Remote Audio Streaming: Technical Recommendations

## Executive Summary

Your planned hub-and-spoke architecture with mTLS + persistent connections is sound. This document provides specific codec, buffering, latency, and scaling recommendations aligned with your existing implementation.

---

## 1. Audio Codec & Format Selection

### Recommendation: PCM16 Raw Audio with Optional Opus Codec Fallback

**Your Current Design:** PCM16 mono, 16 kHz, 20 ms frames ✓

This is optimal for your use case. Here's why and how to tune it:

### Phase 1: Raw PCM16 (Current Plan)
```python
# Remote sender configuration
SAMPLE_RATE = 16000  # Hz (ASR-optimized)
FRAME_SIZE_MS = 20    # 20ms frames = 320 bytes/frame at 16kHz
BITS_PER_SAMPLE = 16  # PCM16
CHANNELS = 1          # Mono

# Per-frame bandwidth calculation
frame_bytes = (SAMPLE_RATE * FRAME_SIZE_MS / 1000) * (BITS_PER_SAMPLE // 8) * CHANNELS
# = 320 bytes/frame + ~50 bytes JSON overhead = 370 bytes/frame
# Over LAN @ 50 fps = 18.5 KB/s baseline
```

**Advantages:**
- Zero latency from codec (CPU-bound ASR models need raw PCM)
- LAN networks have sufficient bandwidth (100+ Mbps)
- Aligns with Faster-Whisper's native input format
- Simplifies jitter buffer management

**Bandwidth Profile:**
- 20 ms frame = 320 bytes audio + ~50 bytes JSON protocol = ~370 bytes
- 1 minute of audio = ~1.1 MB (negligible for LAN)
- LAN saturation: ~270 simultaneous streams at 100 Mbps

### Phase 2/3: Optional Codec Fallback (Future - only if needed)

If you need to support poor Wi-Fi or cellular fallback, implement Opus as optional:

```python
# Optional fallback codec configuration
OPUS_BITRATE_KBPS = 16  # speech-optimized, matches Whisper quality expectations
# Achieves ~98% of PCM16 ASR accuracy with 8:1 compression
# 20 ms Opus frame = 40 bytes + overhead vs 320 bytes PCM16

# Implementation pattern
class AudioCodec(Enum):
    PCM16 = "pcm16"      # Primary on LAN
    OPUS = "opus"        # Fallback for constrained links

def get_encoder(codec: AudioCodec):
    if codec == AudioCodec.PCM16:
        return PassthroughEncoder()  # No-op
    elif codec == AudioCodec.OPUS:
        return OpusEncoder(bitrate_kbps=16, sample_rate=16000)
```

**Quality/Compression Tradeoff Table:**

| Codec | Bitrate | Size (1 min) | ASR Quality | Latency | Network Suitable |
|-------|---------|-------------|-----------|---------|------------------|
| PCM16 | 256 kbps | 1.92 MB | 100% | 0ms | LAN, good Wi-Fi |
| Opus 16k | 16 kbps | 120 KB | 98% | 20ms | Constrained, fallback |
| Opus 32k | 32 kbps | 240 KB | 99% | 20ms | Better quality fallback |

**Decision:** Ship Phase 1 with raw PCM16. Add Opus as optional Phase 2 only if you observe connectivity issues on target Wi-Fi networks.

---

## 2. Network Audio Streaming Protocol

### Recommendation: Binary + JSON Hybrid over TLS (Your Current Plan) ✓

Your design choice is correct. Here's the tuning:

### Phase 1: Newline-Delimited JSON Protocol (Current)

```python
# Server receiver packet format (from network_transport.py)
@dataclass(slots=True)
class RemoteAudioPacket:
    source_id: str           # Device identifier
    seq_no: int              # Monotonic sequence for reordering
    payload: bytes           # PCM16 audio frame (320 bytes typical)
    sent_at_ms: int | None   # Client timestamp for jitter estimation
```

**Message Format on Wire:**

```json
# Single 20ms audio frame as newline-delimited JSON
{"type":"audio","seq_no":1,"audio_b64":"AQAB...","sent_at_ms":1234567890,"source_id":"device-1"}

# Size: ~400-500 bytes per frame (320 audio + protocol overhead)
# Rate: 50 fps = 20-25 KB/s per device
```

**Optimization for LAN:**

Instead of base64 encoding (adds 33% overhead), use binary framing directly:

```python
# Proposed binary wrapper (Phase 2 optimization)
class BinaryAudioFrame:
    """Fixed 12-byte header + audio payload."""
    
    HEADER_SIZE = 12  # 4 bytes seq_no + 4 bytes timestamp + 2 bytes length + 2 bytes CRC
    
    @staticmethod
    def pack(seq_no: int, audio_bytes: bytes, sent_at_ms: int) -> bytes:
        import struct
        import zlib
        
        header = struct.pack(
            ">IIH",
            seq_no,
            sent_at_ms & 0xFFFFFFFF,  # 32-bit timestamp (wraps ~49 days)
            len(audio_bytes)
        )
        crc = zlib.crc32(audio_bytes) & 0xFFFF
        return header + audio_bytes + struct.pack(">H", crc)
    
    @staticmethod
    def unpack(data: bytes) -> tuple[int, bytes, int]:
        import struct
        seq_no, sent_at_ms, length = struct.unpack(">IIH", data[:8])
        audio = data[8:8+length]
        crc_received = struct.unpack(">H", data[8+length:10+length])[0]
        # Validate CRC...
        return seq_no, audio, sent_at_ms

# Benefits:
# - Reduces 500 bytes/frame to 332 bytes (header + audio)
# - 34% bandwidth reduction
# - Same security (TLS encrypts both)
# - Easier parsing in C/Rust for high-throughput receivers
```

### Keep TLS 1.3 with mTLS (Non-negotiable for Security)

```python
# SSL context configuration (from persistent_connection.py)
ssl_context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3  # ✓ Correct

# Certificate pinning for sender devices
ssl_context.check_hostname = True
ssl_context.verify_mode = ssl.CERT_REQUIRED
ssl_context.load_verify_locations(ca_cert_path)  # ✓ Good

# Optional: Client-side certificate for mutual auth
ssl_context.load_cert_chain(client_cert, client_key)
```

### Heartbeat/Keepalive Strategy

Your Phase 3 persistent connection has this right. Recommend:

```python
class HeartbeatConfig:
    """Keepalive tuning for persistent connections."""
    
    INTERVAL_MS = 25000      # Ping every 25 seconds
    TIMEOUT_MS = 10000       # Wait 10 seconds for pong before retry
    MAX_MISSES = 3            # Close after 3 missed pongs = 75 sec total
    
    # Justification:
    # - 25s interval: prevents premature NAT/firewall timeout (~60s typical)
    # - 10s timeout: detects stale connections without excessive delay
    # - 3 misses: tolerates temporary network hiccups
    # - Total detection time: ~60 seconds worst-case

# Implementation pattern (you have this in persistent_connection.py)
def _heartbeat_loop(self):
    while not self._stop_event.is_set():
        time.sleep(self.heartbeat_interval_ms / 1000.0)
        if not self._send_ping():
            self._attempt_reconnect()
```

---

## 3. Audio Buffering & Synchronization Strategies

### Recommendation: Adaptive Jitter Buffer with Ring Buffer Pool

Your plan specifies 80ms baseline, adaptive upward. Here's the detailed implementation:

### Jitter Buffer Architecture

```python
class AdaptiveJitterBuffer:
    """Ring buffer with dynamic target delay based on observed jitter.
    
    Solves:
    - Out-of-order packet reordering
    - Network jitter absorption
    - Audio underflow prevention
    - Latency minimization
    """
    
    def __init__(self, sample_rate: int = 16000, frame_ms: int = 20):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = (sample_rate * frame_ms // 1000) * 2  # PCM16 = 2 bytes/sample
        
        # Capacity: hold frames for up to 200ms delay
        self.max_frames = 10  # 10 * 20ms = 200ms
        self.buffer = deque(maxlen=self.max_frames)
        
        # Adaptive parameters
        self.target_delay_ms = 80    # Start at 80ms baseline
        self.max_delay_ms = 150      # Don't exceed 150ms to preserve interactivity
        self.min_delay_ms = 40       # Don't drop below 40ms (causes underruns)
        
        self._lock = threading.Lock()
        self._last_seq_no = -1
        self._reorder_count = 0
        self._underflow_count = 0
        self._jitter_samples = deque(maxlen=50)  # Rolling jitter estimate
    
    def put(self, seq_no: int, audio_bytes: bytes, sent_at_ms: int | None = None) -> None:
        """Insert audio frame, handling out-of-order arrivals."""
        with self._lock:
            if seq_no <= self._last_seq_no:
                # Duplicate or out-of-order; log and skip
                self._reorder_count += 1
                return
            
            # Track inter-arrival jitter
            if sent_at_ms and self._last_send_time:
                observed_delay = (time.time_ns() // 1_000_000 - sent_at_ms)
                self._jitter_samples.append(observed_delay)
                self._update_target_delay()
            
            self.buffer.append((seq_no, audio_bytes))
            self._last_seq_no = seq_no
            self._last_send_time = sent_at_ms
    
    def get(self, timeout_ms: int = 100) -> bytes | None:
        """Extract audio frame when enough delay accumulated.
        
        Returns None if buffer underrun (play silence or repeat last frame).
        """
        with self._lock:
            target_frames = int(self.target_delay_ms / self.frame_ms)
            
            if len(self.buffer) < target_frames:
                self._underflow_count += 1
                return None  # Underrun: caller plays silence or repeats last
            
            seq_no, audio = self.buffer.popleft()
            return audio
    
    def _update_target_delay(self) -> None:
        """Adapt target delay based on observed jitter."""
        if len(self._jitter_samples) < 10:
            return
        
        jitter_ms = statistics.stdev(self._jitter_samples)
        # Target delay = mean_delay + 2*stdev (cover 95% of jitter)
        proposed_delay = statistics.mean(self._jitter_samples) + 2 * jitter_ms
        
        # Clamp to safe range and use exponential smoothing
        proposed_delay = max(self.min_delay_ms, min(self.max_delay_ms, proposed_delay))
        self.target_delay_ms = 0.8 * self.target_delay_ms + 0.2 * proposed_delay
    
    def stats(self) -> dict:
        """Diagnostics for telemetry."""
        return {
            "buffer_size": len(self.buffer),
            "target_delay_ms": self.target_delay_ms,
            "reorder_count": self._reorder_count,
            "underflow_count": self._underflow_count,
        }
```

### Sequence Number Strategy for Reordering

```python
# In remote_stream_source.py
class RemoteStreamSource:
    """Receives remote audio packets and produces continuous audio stream."""
    
    def __init__(self, sample_rate: int = 16000):
        self.jitter_buffer = AdaptiveJitterBuffer(sample_rate, frame_ms=20)
        self.expected_seq_no = 0
        self._gap_fill_strategy = "repeat_last"  # or "silence"
    
    def on_audio_packet(self, packet: RemoteAudioPacket) -> None:
        """Receive out-of-order audio frame."""
        seq_gap = packet.seq_no - self.expected_seq_no
        
        if seq_gap < 0:
            # Duplicate or very late; drop it
            return
        elif seq_gap > 0:
            # Gap in sequence; log and fill with silence
            print(f"WARNING: Lost {seq_gap} packets (seq {self.expected_seq_no}..{packet.seq_no})")
            self._fill_gap(gap_count=seq_gap)
        
        self.jitter_buffer.put(
            packet.seq_no,
            packet.payload,
            sent_at_ms=packet.sent_at_ms
        )
        self.expected_seq_no = packet.seq_no + 1
    
    def _fill_gap(self, gap_count: int) -> None:
        """Generate synthetic frames for lost packets."""
        if self._gap_fill_strategy == "silence":
            silent_frame = b'\x00' * 320  # 320 bytes = 20ms PCM16
            for i in range(gap_count):
                self.jitter_buffer.put(
                    self.expected_seq_no + i,
                    silent_frame,
                    sent_at_ms=None
                )
        elif self._gap_fill_strategy == "repeat_last":
            # More natural sounding; avoids clicks from silence
            if self.last_frame:
                for i in range(gap_count):
                    self.jitter_buffer.put(
                        self.expected_seq_no + i,
                        self.last_frame,
                        sent_at_ms=None
                    )
```

### Synchronization Between Local & Remote Sources

If mixing local mic + remote devices in same utterance:

```python
class UnifiedAudioMixer:
    """Synchronizes local and remote audio streams."""
    
    def __init__(self):
        self.local_source = MicStreamSource(16000, blocksize=1600)  # Your current
        self.remote_sources: dict[str, RemoteStreamSource] = {}     # New
        self._reference_clock_ns = time.monotonic_ns()
    
    def get_next_frame(self) -> bytes:
        """Return 20ms of mixed audio from active source(s)."""
        
        # Priority: if wake from local mic, use local
        local_frame = self.local_source.read(timeout_ms=100)
        if local_frame and self._is_active_local_session():
            return local_frame
        
        # Otherwise prefer remote if available
        active_remote = self._get_active_remote_source()
        if active_remote:
            frame = active_remote.get()
            if frame:
                return frame
        
        # Fallback: silence frame (trigger by jitter buffer underrun)
        return b'\x00' * 320
    
    def _get_active_remote_source(self) -> RemoteStreamSource | None:
        """Select remote source by timestamp coherence and priority."""
        if not self.remote_sources:
            return None
        
        # Pick source with most recent activity
        return max(
            self.remote_sources.values(),
            key=lambda s: s.last_frame_received_ns,
            default=None
        )
```

---

## 4. Handling Network Latency & Packet Loss

### Recommendation: FEC + Adaptive Codec Switching

### Latency Profile (LAN Typical)

```
Local mic capture:       ~10-30 ms
Encode/Buffer/Send:      ~5-10 ms
Network transit:         ~1-5 ms (LAN)
Jitter buffer:          ~80 ms (adaptive)
ASR processing:         ~200-500 ms (Faster-Whisper)
─────────────────────────────────
Total E2E latency:      ~300-600 ms (acceptable for conversational AI)

⚠️  Critical: 80ms jitter buffer is the tunable lever
    - < 40ms: frequent underruns, clipped speech
    - 80-100ms: optimal balance
    - > 150ms: annoying lag, feels unresponsive
```

### Packet Loss Handling

LAN packet loss is typically < 0.1%, but Wi-Fi can reach 5%. Handle gracefully:

```python
class PacketLossRecovery:
    """Detects loss and applies Forward Error Correction or interpolation."""
    
    def __init__(self, enable_fec: bool = False):
        self.enable_fec = enable_fec
        self.loss_window = deque(maxlen=100)  # Track last 100 packets
    
    def record_loss(self, expected_seq: int, actual_seq: int) -> None:
        """Log gap between expected and actual sequence."""
        loss_count = actual_seq - expected_seq - 1
        if loss_count > 0:
            self.loss_window.append(loss_count)
    
    @property
    def packet_loss_rate(self) -> float:
        """Moving average of loss rate."""
        if not self.loss_window:
            return 0.0
        total_lost = sum(self.loss_window)
        total_packets = sum(self.loss_window) + len(self.loss_window)
        return total_lost / total_packets if total_packets > 0 else 0.0
    
    def handle_loss(self, lost_frame_count: int, context: dict) -> bytes:
        """Generate placeholder for lost frame(s).
        
        Args:
            lost_frame_count: number of consecutive frames lost
            context: {"last_frame": bytes, "silence_threshold": float}
        
        Returns:
            Reconstructed audio frame (silence or interpolated)
        """
        last_frame = context.get("last_frame")
        
        if self.enable_fec and lost_frame_count == 1 and last_frame:
            # Simple interpolation: repeat last frame (crude but effective)
            return last_frame
        else:
            # Silence (more honest representation)
            return b'\x00' * 320

# Tuning recommendation:
# - At packet loss rate > 2%: warn user, consider codec switch
# - At packet loss rate > 5%: show UI alert, offer fallback
# - If sustained > 5s: reconnect or switch to local-only mode
```

### Optional: Forward Error Correction (Phase 3+)

Only if you observe > 2% LAN loss (unusual):

```python
# Requires: pip install pyec
from pyec import RSDecoder

class FECProtectedFrame:
    """Audio frame with Reed-Solomon FEC overhead."""
    
    def __init__(self, audio_bytes: bytes, fec_overhead_pct: int = 20):
        """Create FEC-protected frame.
        
        20% overhead = can recover any 1 in 5 lost frames
        """
        self.data = audio_bytes
        self.fec_overhead = fec_overhead_pct
        
        # Split data into k blocks, generate m parity blocks
        k = 4  # data blocks (4*80 = 320 bytes audio)
        m = 1  # parity blocks (1 extra for 20% overhead)
        
        self.encoder = RSDecoder(k + m, k)  # RS(5, 4)
        self.fec_data = self.encoder.encode(audio_bytes)
    
    @staticmethod
    def decode_with_fec(frames_list: list[bytes]) -> bytes:
        """Recover lost frame using FEC data from nearby frames."""
        # This gets complex; only add if loss rate justifies it
        pass

# Decision: Start without FEC. Add only if loss > 2% persists.
```

---

## 5. Maintaining Voice Quality & Responsiveness

### Recommendation: Confidence Metadata + ASR Provider Fallback

### Quality Metrics to Track

```python
@dataclass(slots=True)
class AudioQualityMetrics:
    """Diagnostic metrics for voice quality."""
    
    sample_rate: int
    bit_depth: int
    signal_noise_ratio_db: float  # Estimated SNR
    clipping_ratio: float         # % of frames at max amplitude
    reorder_packets: int
    lost_packets: int
    underrun_count: int
    buffer_utilization_pct: float
    
    @property
    def is_degraded(self) -> bool:
        """Heuristic: quality is degraded."""
        return (
            self.signal_noise_ratio_db < 10  # Very noisy
            or self.lost_packets > 5
            or self.clipping_ratio > 0.1  # 10% clipping
        )

# Implement in RemoteStreamSource:
def assess_quality(self) -> AudioQualityMetrics:
    """Compute quality score from network and buffer stats."""
    # Calculate SNR from received audio
    # Count clipping events
    # Return metrics
    pass
```

### ASR Provider Fallback Strategy

Your current router is good; enhance it:

```python
# From asr_router.py (extend existing)
class EnhancedAsrRouter:
    """Selects ASR provider based on audio quality and fallback."""
    
    def __init__(self):
        self.primary = FasterWhisperAsrProvider("small.en")  # Your current
        self.fallback = VoskAsrProvider(model_path="...")
    
    def transcribe(self, audio_bytes: bytes, quality_metrics: AudioQualityMetrics):
        """Choose provider based on quality."""
        
        # High quality: use primary (better accuracy)
        if not quality_metrics.is_degraded:
            return self.primary.transcribe(audio_bytes)
        
        # Degraded: use fallback (faster, more robust)
        # Faster-Whisper + small model is slower than Vosk for poor audio
        return self.fallback.transcribe(audio_bytes)

# Alternative: Run both and ensemble (if CPU permits)
def transcribe_ensemble(self, audio_bytes: bytes):
    """Get consensus from both providers."""
    fw_result = self.primary.transcribe(audio_bytes)
    vosk_result = self.fallback.transcribe(audio_bytes)
    
    # If high agreement (> 80% char similarity): trust it
    # Otherwise: show both results, let user pick
    if self._char_similarity(fw_result.text, vosk_result.text) > 0.8:
        return fw_result  # Prefer Faster-Whisper accuracy
    else:
        return EnsembleResult(fw_result, vosk_result)
```

### Preserve Audio Fidelity End-to-End

```python
class AudioFidelityPreserver:
    """Prevents common distortions in voice capture pipeline."""
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        self.last_peak_level = 0.0
        self.dc_offset_filter = DCOffsetRemover(sample_rate)
        self.clipping_detector = ClippingDetector(threshold_pct=95)
    
    def process(self, audio_bytes: bytes) -> bytes:
        """Apply light preprocessing without introducing latency."""
        
        # 1. Remove DC offset (common in USB mics)
        audio = self.dc_offset_filter.process(audio_bytes)
        
        # 2. Detect clipping (warn if > 10% frames affected)
        clipping_frames = self.clipping_detector.count_clipped(audio)
        if clipping_frames > 32 * 0.1:  # 10% of 320 bytes = 16 frames
            print(f"WARNING: {clipping_frames} clipped frames in this utterance")
        
        # 3. Optional: Normalize to target level
        # (But be careful: ASR models expect specific loudness)
        # Skip normalization to preserve model assumptions
        
        return audio

class DCOffsetRemover:
    """High-pass filter to remove low-frequency DC offset."""
    
    def __init__(self, sample_rate: int):
        # Simple 1-pole HPF at 5 Hz cutoff
        fc = 5.0  # Hz
        omega = 2 * math.pi * fc / sample_rate
        self.alpha = omega / (1 + omega)
    
    def process(self, audio_bytes: bytes) -> bytes:
        import struct
        
        samples = struct.unpack(f"<{len(audio_bytes)//2}h", audio_bytes)
        dc_offset = 0
        filtered = []
        
        for sample in samples:
            filtered_sample = int(self.alpha * (sample - dc_offset))
            dc_offset = sample
            filtered.append(filtered_sample)
        
        return struct.pack(f"<{len(filtered)}h", *filtered)
```

---

## 6. Scaling for Multiple Remote Devices

### Recommendation: Connection Pool + Per-Device Session Isolation

### Architecture for N Concurrent Remote Streams

```python
class RemoteAudioServerScaled:
    """Handles multiple concurrent remote devices efficiently."""
    
    def __init__(self, max_concurrent: int = 10):
        self.max_concurrent = max_concurrent
        self.active_streams: dict[str, RemoteStreamSource] = {}
        self._lock = threading.RLock()
        self._connection_pool = ThreadPoolExecutor(max_workers=max_concurrent)
    
    def add_remote_device(self, source_id: str, connection: PersistentRemoteConnection):
        """Register a new remote device stream."""
        with self._lock:
            if len(self.active_streams) >= self.max_concurrent:
                raise RuntimeError(f"Max concurrent streams ({self.max_concurrent}) reached")
            
            stream = RemoteStreamSource(source_id)
            stream.on_packet = self._handle_packet
            self.active_streams[source_id] = stream
            
            # Process packets from this device in thread pool
            self._connection_pool.submit(self._stream_reader_loop, source_id, connection)
    
    def _stream_reader_loop(self, source_id: str, connection: PersistentRemoteConnection):
        """Read packets from one device continuously."""
        try:
            while connection.connected:
                packet = connection.recv_packet(timeout_ms=1000)
                if packet:
                    stream = self.active_streams.get(source_id)
                    if stream:
                        stream.on_packet(packet)
        except Exception as e:
            print(f"Stream reader error for {source_id}: {e}")
            self.remove_remote_device(source_id)
    
    def remove_remote_device(self, source_id: str):
        """Cleanup device stream."""
        with self._lock:
            if source_id in self.active_streams:
                del self.active_streams[source_id]

# Per-session isolation (from your plan)
class SessionIsolatedAssistant:
    """One assistant context per (room + device) pair."""
    
    def __init__(self):
        self.sessions: dict[str, AssistantSession] = {}  # key = room_id + "|" + source_id
        self._lock = threading.RLock()
    
    def get_session(self, room_id: str, source_id: str) -> AssistantSession:
        """Get or create session for this device in this room."""
        key = f"{room_id}|{source_id}"
        
        with self._lock:
            if key not in self.sessions:
                self.sessions[key] = AssistantSession(
                    room_id=room_id,
                    source_id=source_id,
                    ttl_seconds=3600  # 1 hour expiry
                )
            
            return self.sessions[key]
    
    def execute_command(self, room_id: str, source_id: str, command_text: str, confidence: float):
        """Execute command in proper session context."""
        session = self.get_session(room_id, source_id)
        
        # Session has its own conversation history, pending confirmations, etc.
        return session.execute_command(command_text, confidence)
```

### Backpressure & Queue Management

```python
class BackpressureController:
    """Prevents queue overflow when remote devices send faster than ASR processes."""
    
    def __init__(self, max_queue_frames: int = 50):
        self.max_queue_frames = max_queue_frames
        self.queue_lengths: dict[str, int] = {}
        self._lock = threading.Lock()
    
    def can_accept_frame(self, source_id: str) -> bool:
        """Check if we can accept another audio frame from this device."""
        with self._lock:
            current_length = self.queue_lengths.get(source_id, 0)
            
            if current_length >= self.max_queue_frames:
                # Queue is full; apply backpressure
                return False
            
            self.queue_lengths[source_id] = current_length + 1
            return True
    
    def frame_processed(self, source_id: str):
        """Decrement queue when frame is processed."""
        with self._lock:
            if source_id in self.queue_lengths:
                self.queue_lengths[source_id] = max(0, self.queue_lengths[source_id] - 1)

# Usage:
def on_audio_packet(self, packet: RemoteAudioPacket):
    if not self.backpressure.can_accept_frame(packet.source_id):
        # Tell sender to slow down or drop this frame
        self.send_feedback(packet.source_id, "QUEUE_FULL")
        return
    
    # Process frame
    stream = self.active_streams[packet.source_id]
    stream.on_packet(packet)
    self.backpressure.frame_processed(packet.source_id)
```

### Concurrency Limits (Tuning Table)

| Scenario | Max Concurrent | Reason |
|----------|----------------|--------|
| Single PC CPU (8-core) | 4-6 streams | Faster-Whisper uses ~1.5 cores per model |
| Main PC CPU (16-core) | 8-12 streams | 2 cores per Whisper, headroom for UI |
| High-end (32-core) | 16+ streams | But memory becomes limiting |

**Memory per stream:** ~50-100 MB (Whisper model state + jitter buffer + ASR cache)
- 10 streams = 500-1000 MB (reasonable)

---

## 7. Integration with Existing Local Microphone System

### Recommendation: Adapter Pattern for Unified Input

Your `voice_pipeline.py` already has the right structure. Enhance it:

```python
# Extend finance_app/services/voice_pipeline.py

class UnifiedAudioSource:
    """Adapter that unifies local mic and remote devices into single input stream."""
    
    def __init__(self):
        # Your existing local mic
        self.local_source = MicStreamSource(sample_rate=16000, blocksize=1600)
        
        # New: remote device adapter
        self.remote_server: RemoteAudioServerScaled | None = None
        self.active_source_id = "local"  # Track which source is active
        self._lock = threading.RLock()
    
    def read_frame(self, timeout_ms: int = 100) -> tuple[bytes, str]:
        """Read next audio frame from active source.
        
        Returns:
            (audio_bytes, source_id)
        """
        with self._lock:
            if self.active_source_id == "local":
                frame = self.local_source.read(timeout_ms)
                if frame:
                    return frame, "local"
            elif self.active_source_id.startswith("remote-"):
                device_id = self.active_source_id.split("-", 1)[1]
                stream = self.remote_server.active_streams.get(device_id)
                if stream:
                    frame = stream.get(timeout_ms)
                    if frame:
                        return frame, self.active_source_id
        
        # Fallback: silence
        return b'\x00' * 320, "silence"
    
    def set_active_source(self, source_id: str) -> None:
        """Switch active audio source (e.g., on wake word from device)."""
        with self._lock:
            if source_id == "local" or source_id.startswith("remote-"):
                self.active_source_id = source_id
                print(f"Switched audio source to {source_id}")

# Integration with VoiceCoordinator (your existing class)
class VoiceCoordinator:
    def __init__(self, wake_phrase: str = "hey steven"):
        # ... existing init ...
        
        # Replace separate local/remote with unified source
        self.unified_source = UnifiedAudioSource()
        self.unified_source.remote_server = self.remote_server  # Link reference
    
    def process_audio_loop(self):
        """Main voice processing loop."""
        while self.running:
            # Read from unified source
            frame, source_id = self.unified_source.read_frame(timeout_ms=100)
            
            if frame == b'\x00' * 320:  # Silence
                continue
            
            # Process (endpointing, VAD, ASR, etc.)
            endpoint_result = self.endpoint.process(frame, source_id=source_id)
            if endpoint_result.is_final:
                transcript = self.asr_router.transcribe(endpoint_result.audio)
                command_event = VoiceCommandEvent(
                    text=transcript.text,
                    confidence=transcript.confidence,
                    source_id=source_id,
                    session_id=self._get_session_id(source_id)
                )
                self.router.process_command(command_event)
```

### Session Routing to Assistant

```python
# Update assistant_service.py to handle remote sessions

class SessionAwareAssistantService:
    """Assistant with multi-device session isolation (your Phase 4)."""
    
    def __init__(self):
        self.session_contexts: dict[str, ConversationContext] = {}
        self._lock = threading.RLock()
    
    def handle_command_event(self, event: VoiceCommandEvent):
        """Route command to correct session + apply safety policy."""
        
        # Phase 3: Get safety tier for this command
        tier = ActionSafetyGate.classify(event.text)
        
        # Phase 4: Route to session-scoped context
        session = self._get_session_context(event.session_id)
        
        # Apply safety policy
        action = ActionSafetyGate.process(
            command_text=event.text,
            confidence=event.confidence,
            tier=tier,
            require_confirmation=self._should_confirm(event, session)
        )
        
        if action == "CONFIRM_REQUIRED":
            # Ask user for confirmation
            self._prompt_confirmation(event, session)
        elif action == "EXECUTE":
            # Execute immediately
            session.execute_command(event.text)
        else:  # "REJECT"
            print(f"Safety: Rejected command at confidence {event.confidence}")

# Ensure old local-only path still works (backwards compatibility)
def _get_session_context(self, session_id: str | None) -> ConversationContext:
    """Get or create session."""
    if not session_id:
        session_id = "local-default"  # Fallback for local mic
    
    with self._lock:
        if session_id not in self.session_contexts:
            self.session_contexts[session_id] = ConversationContext(session_id)
        
        return self.session_contexts[session_id]
```

### Graceful Degradation

```python
class GracefulDegradation:
    """Fallback strategy when remote device disconnects mid-utterance."""
    
    @staticmethod
    def handle_device_disconnect(source_id: str, current_state: VoiceSessionState):
        """What to do if remote device drops connection."""
        
        if current_state == VoiceSessionState.IDLE:
            # No active session; just cleanup
            return "cleanup"
        elif current_state == VoiceSessionState.CAPTURING:
            # Mid-utterance: switch to local mic if available
            print(f"Device {source_id} disconnected during capture. Switching to local mic.")
            return "switch_to_local"
        elif current_state == VoiceSessionState.DECODING:
            # ASR already running; let it finish
            print(f"Device {source_id} disconnected; ASR in progress, continuing...")
            return "continue_asr"
        else:
            return "error_state"
```

---

## Recommended Implementation Roadmap

### Phase 1 (Current): Foundation
- ✅ PCM16 mono, 16 kHz, 20 ms frames
- ✅ TLS 1.3 + mTLS pairing
- ✅ Newline-delimited JSON protocol
- ✅ 80 ms adaptive jitter buffer
- ✅ Basic sequence reordering
- **Action:** Ship with these. They're production-ready.

### Phase 2 (Next): Quality
- Binary framing optimization (34% bandwidth reduction)
- Confidence metadata in CommandEvent
- ASR provider fallback routing
- Audio quality metrics (SNR, clipping detection)
- **Timeline:** 1-2 sprints

### Phase 3 (Parallel): Reliability
- Session resumption on reconnect (you have PersistentRemoteConnection foundation)
- Per-device packet loss recovery
- Optional FEC if loss > 2%
- Multi-device backpressure controller
- **Timeline:** 1-2 sprints

### Phase 4: Production Hardening
- Multi-room session isolation (you have session_state.py structure)
- Action safety tiers (you have action_safety.py)
- Cross-device confirmation prompts
- Dead-letter queue for failed mutations
- **Timeline:** 2-3 sprints

---

## Technology Stack Summary

| Component | Recommended | Why |
|-----------|-------------|-----|
| **Codec** | PCM16 + optional Opus | LAN-friendly, ASR-native, quality |
| **Protocol** | TLS 1.3 + newline JSON / binary | Security, simplicity, parsing |
| **Jitter Buffer** | Adaptive ring buffer (40-150ms) | Absorbs LAN jitter, maintains responsiveness |
| **ASR Routing** | Faster-Whisper primary, Vosk fallback | Accuracy + robustness |
| **Concurrency** | ThreadPoolExecutor, per-device queues | 4-12 concurrent streams typical |
| **Session Management** | room_id + source_id tuple, TTL expiry | Multi-room isolation |
| **Backpressure** | Frame queue + feedback signals | Prevents ASR bottleneck |

---

## Monitoring & Telemetry

```python
# Add to telemetry.py

class RemoteAudioTelemetry:
    """Track remote audio streaming health."""
    
    def __init__(self):
        self.metrics = {
            "devices_connected": 0,
            "total_packets_received": 0,
            "total_packets_dropped": 0,
            "avg_latency_ms": 0.0,
            "avg_buffer_fill_pct": 0.0,
            "underrun_count": 0,
        }
    
    def record_packet(self, seq_no: int, recv_time_ms: int, send_time_ms: int):
        """Log packet arrival."""
        latency = recv_time_ms - send_time_ms
        self.metrics["total_packets_received"] += 1
        self.metrics["avg_latency_ms"] = (
            0.9 * self.metrics["avg_latency_ms"] + 0.1 * latency
        )
    
    def to_prometheus(self) -> str:
        """Export metrics for monitoring."""
        return "\n".join([
            f"remote_audio_devices_connected {self.metrics['devices_connected']}",
            f"remote_audio_packets_received_total {self.metrics['total_packets_received']}",
            f"remote_audio_packets_dropped_total {self.metrics['total_packets_dropped']}",
            f"remote_audio_latency_ms {self.metrics['avg_latency_ms']:.1f}",
        ])
```

---

## Key Takeaways

1. **Codec:** Ship with raw PCM16 now; add Opus codec fallback only if Wi-Fi connectivity issues arise (unlikely for LAN).

2. **Protocol:** Your TLS 1.3 + JSON design is solid. Optimize to binary framing in Phase 2 (optional 34% bandwidth gain).

3. **Buffering:** Your 80ms adaptive jitter buffer is the critical tuning point. Monitor underruns; increase if > 1% of utterances have clipping.

4. **Latency:** Total E2E is ~300-600ms. The jitter buffer (80ms) is the only tunable lever; ASR (200-500ms) is model-dependent.

5. **Loss:** LAN < 0.1% typical. Handle gracefully with frame repetition. Add FEC only if observed loss > 2%.

6. **Scaling:** 4-12 concurrent streams on typical 8-16 core PC. Thread pool + per-device queues with backpressure.

7. **Integration:** Unified audio source adapter preserves local mic path; new remote devices work seamlessly in existing pipeline.

Your existing architecture is sound and well-designed. These recommendations accelerate implementation and optimize for production reliability.
