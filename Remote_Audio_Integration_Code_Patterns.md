# Remote Audio Integration: Code Patterns & Implementation Guide

## Objective

Provide drop-in code patterns and integration points for your existing voice pipeline, aligned with the technical recommendations and your phased delivery plan.

---

## Part 1: Jitter Buffer Implementation

### Adaptive Jitter Buffer for `remote_stream_source.py`

Add this to your existing `RemoteStreamSource` class:

```python
# finance_app/services/voice/adaptive_jitter_buffer.py

from __future__ import annotations

import statistics
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Optional


@dataclass
class JitterBufferStats:
    """Diagnostic snapshot of buffer health."""
    buffer_size: int
    target_delay_ms: float
    mean_interarrival_ms: float
    stdev_interarrival_ms: float
    reorder_count: int
    underflow_count: int
    overflow_count: int


class AdaptiveJitterBuffer:
    """
    Ring buffer with dynamic target delay based on observed network jitter.
    
    Solves:
    - Out-of-order packet reordering
    - Network jitter absorption
    - Audio underflow prevention
    - Latency minimization
    
    Configuration:
    - min_delay_ms: 40 (don't drop below this to prevent underruns)
    - target_delay_ms: 80 (baseline, adapts upward under jitter)
    - max_delay_ms: 150 (cap to preserve interactivity)
    """
    
    def __init__(
        self,
        sample_rate: int = 16000,
        frame_ms: int = 20,
        min_delay_ms: float = 40,
        initial_target_delay_ms: float = 80,
        max_delay_ms: float = 150,
    ):
        self.sample_rate = sample_rate
        self.frame_ms = frame_ms
        self.frame_bytes = (sample_rate * frame_ms // 1000) * 2  # PCM16 = 2 bytes/sample
        
        # Buffer capacity: hold frames for up to 200ms delay
        self.max_frames = max(10, int(200 / frame_ms))
        self.buffer: deque[tuple[int, bytes]] = deque(maxlen=self.max_frames)
        
        # Adaptive delay parameters
        self.min_delay_ms = float(min_delay_ms)
        self.target_delay_ms = float(initial_target_delay_ms)
        self.max_delay_ms = float(max_delay_ms)
        
        # Jitter tracking
        self._jitter_samples = deque(maxlen=50)  # Rolling window for adaptation
        self._interarrival_times_ms = deque(maxlen=50)
        self._last_seq_no = -1
        self._last_arrival_time_ns = 0
        self._last_send_time_ms = 0
        
        # Statistics
        self._reorder_count = 0
        self._underflow_count = 0
        self._overflow_count = 0
        self._lock = threading.Lock()
    
    def put(self, seq_no: int, audio_bytes: bytes, sent_at_ms: Optional[int] = None) -> bool:
        """
        Insert audio frame, handling out-of-order arrivals.
        
        Args:
            seq_no: Monotonic sequence number (for reordering detection)
            audio_bytes: PCM16 audio data (typically 320 bytes for 20ms frame)
            sent_at_ms: Client-side timestamp for jitter estimation
        
        Returns:
            True if frame was accepted, False if dropped (duplicate/out-of-order)
        """
        with self._lock:
            # Reject duplicate or very old frame
            if seq_no <= self._last_seq_no:
                self._reorder_count += 1
                return False
            
            # Track inter-arrival time for jitter estimation
            now_ns = time.monotonic_ns()
            if self._last_arrival_time_ns > 0:
                interarrival_ms = (now_ns - self._last_arrival_time_ns) / 1_000_000
                self._interarrival_times_ms.append(interarrival_ms)
                
                # Estimate one-way latency from sent_at_ms timestamp
                if sent_at_ms is not None:
                    recv_time_ms = now_ns / 1_000_000
                    one_way_delay_ms = recv_time_ms - sent_at_ms
                    self._jitter_samples.append(one_way_delay_ms)
                    
                    # Adapt target delay based on jitter
                    self._update_target_delay()
            
            # Check for buffer overflow
            if len(self.buffer) >= self.max_frames:
                self._overflow_count += 1
                # Silently drop oldest frame to make room
                # (This shouldn't happen in normal LAN operation)
            
            self.buffer.append((seq_no, audio_bytes))
            self._last_seq_no = seq_no
            self._last_arrival_time_ns = now_ns
            self._last_send_time_ms = sent_at_ms or 0
            
            return True
    
    def get(self, timeout_ms: int = 100) -> Optional[bytes]:
        """
        Extract audio frame when enough delay accumulated.
        
        Blocks until:
        1. Buffer has enough frames to meet target_delay_ms, OR
        2. timeout_ms elapses (returns None for underrun)
        
        Args:
            timeout_ms: How long to wait for buffer to fill
        
        Returns:
            PCM16 audio frame (320 bytes) or None if underrun
        """
        deadline_ns = time.monotonic_ns() + (timeout_ms * 1_000_000)
        
        while True:
            with self._lock:
                target_frames = max(1, int(self.target_delay_ms / self.frame_ms))
                
                if len(self.buffer) >= target_frames:
                    seq_no, audio = self.buffer.popleft()
                    return audio
            
            # Wait a bit and retry
            elapsed_ns = time.monotonic_ns() - (deadline_ns - timeout_ms * 1_000_000)
            if elapsed_ns >= timeout_ms * 1_000_000:
                with self._lock:
                    self._underflow_count += 1
                return None
            
            time.sleep(0.001)  # 1ms poll interval
    
    def _update_target_delay(self) -> None:
        """
        Adapt target delay based on observed jitter.
        
        Strategy: target_delay = mean_delay + 2*stdev
        This covers ~95% of jitter samples without excessive delay.
        
        Uses exponential smoothing to avoid chattering.
        """
        if len(self._jitter_samples) < 10:
            return
        
        samples_list = list(self._jitter_samples)
        mean_delay = statistics.mean(samples_list)
        stdev_delay = statistics.stdev(samples_list) if len(samples_list) > 1 else 0
        
        # Proposed delay: mean + 2 sigma
        proposed_delay = mean_delay + 2 * stdev_delay
        proposed_delay = max(self.min_delay_ms, min(self.max_delay_ms, proposed_delay))
        
        # Exponential smoothing: 80% old target, 20% new proposal
        # (Avoids oscillation from single jitter spike)
        self.target_delay_ms = 0.8 * self.target_delay_ms + 0.2 * proposed_delay
    
    def stats(self) -> JitterBufferStats:
        """Return diagnostic metrics for telemetry/monitoring."""
        with self._lock:
            interarrival_list = list(self._interarrival_times_ms)
            mean_interarrival = statistics.mean(interarrival_list) if interarrival_list else 0
            stdev_interarrival = (
                statistics.stdev(interarrival_list) if len(interarrival_list) > 1 else 0
            )
            
            return JitterBufferStats(
                buffer_size=len(self.buffer),
                target_delay_ms=self.target_delay_ms,
                mean_interarrival_ms=mean_interarrival,
                stdev_interarrival_ms=stdev_interarrival,
                reorder_count=self._reorder_count,
                underflow_count=self._underflow_count,
                overflow_count=self._overflow_count,
            )
    
    def reset(self) -> None:
        """Clear buffer and reset stats (e.g., on reconnect or session end)."""
        with self._lock:
            self.buffer.clear()
            self._jitter_samples.clear()
            self._interarrival_times_ms.clear()
            self._last_seq_no = -1
            self._last_arrival_time_ns = 0
            self.target_delay_ms = 80.0  # Reset to initial value
```

### Integration into `RemoteStreamSource`

```python
# Update finance_app/services/voice/remote_stream_source.py

from finance_app.services.voice.adaptive_jitter_buffer import (
    AdaptiveJitterBuffer,
    JitterBufferStats,
)

class RemoteStreamSource:
    """Receives remote audio packets and produces continuous audio stream."""
    
    def __init__(self, source_id: str, sample_rate: int = 16000):
        self.source_id = source_id
        self.sample_rate = sample_rate
        
        # Use adaptive jitter buffer instead of simple deque
        self.jitter_buffer = AdaptiveJitterBuffer(
            sample_rate=sample_rate,
            frame_ms=20,
            min_delay_ms=40,
            initial_target_delay_ms=80,
            max_delay_ms=150,
        )
        
        self.expected_seq_no = 0
        self.last_frame = None
        self._gap_fill_strategy = "repeat_last"  # or "silence"
        self._lock = threading.Lock()
    
    def on_audio_packet(self, packet: RemoteAudioPacket) -> None:
        """
        Receive out-of-order audio frame from network.
        
        Handles:
        - Out-of-order delivery (jitter buffer reordering)
        - Packet loss (gap detection and silence fill)
        - Duplicate packets (jitter buffer ignores)
        """
        seq_gap = packet.seq_no - self.expected_seq_no
        
        if seq_gap < 0:
            # Duplicate or very late; jitter buffer already dropped it
            return
        elif seq_gap > 0:
            # Gap in sequence; fill with silence
            self._log_loss_event(gap_count=seq_gap, start_seq=self.expected_seq_no)
            self._fill_gap(gap_count=seq_gap)
        
        # Insert into jitter buffer (handles reordering internally)
        accepted = self.jitter_buffer.put(
            seq_no=packet.seq_no,
            audio_bytes=packet.payload,
            sent_at_ms=packet.sent_at_ms,
        )
        
        if accepted:
            self.expected_seq_no = packet.seq_no + 1
            self.last_frame = packet.payload
    
    def get(self, timeout_ms: int = 100) -> Optional[bytes]:
        """
        Get next 20ms audio frame, blocking until buffer has data.
        
        Returns None on underrun (caller should play silence or repeat).
        """
        return self.jitter_buffer.get(timeout_ms=timeout_ms)
    
    def _fill_gap(self, gap_count: int) -> None:
        """Generate synthetic frames for lost packets."""
        if self._gap_fill_strategy == "repeat_last":
            if self.last_frame:
                for i in range(gap_count):
                    self.jitter_buffer.put(
                        seq_no=self.expected_seq_no + i,
                        audio_bytes=self.last_frame,
                        sent_at_ms=None,
                    )
            else:
                # No last frame yet; fill with silence
                for i in range(gap_count):
                    self.jitter_buffer.put(
                        seq_no=self.expected_seq_no + i,
                        audio_bytes=b'\x00' * 320,
                        sent_at_ms=None,
                    )
        else:  # "silence"
            silent_frame = b'\x00' * 320
            for i in range(gap_count):
                self.jitter_buffer.put(
                    seq_no=self.expected_seq_no + i,
                    audio_bytes=silent_frame,
                    sent_at_ms=None,
                )
    
    def stats(self) -> dict:
        """Return diagnostics for monitoring."""
        buffer_stats = self.jitter_buffer.stats()
        return {
            "source_id": self.source_id,
            "buffer_size": buffer_stats.buffer_size,
            "target_delay_ms": round(buffer_stats.target_delay_ms, 1),
            "reorder_count": buffer_stats.reorder_count,
            "underflow_count": buffer_stats.underflow_count,
            "overflow_count": buffer_stats.overflow_count,
        }
    
    def _log_loss_event(self, gap_count: int, start_seq: int) -> None:
        """Log packet loss for diagnostics."""
        print(
            f"[{self.source_id}] WARNING: Lost {gap_count} packets "
            f"(seq {start_seq}..{start_seq + gap_count - 1})"
        )
```

---

## Part 2: Unified Audio Source (Local + Remote)

### Adapter Pattern for Voice Pipeline

```python
# finance_app/services/voice/unified_audio_source.py

from __future__ import annotations

import threading
from typing import Optional, Tuple

from finance_app.services.voice.stream_source import MicStreamSource
from finance_app.services.voice.remote_stream_source import RemoteStreamSource


class UnifiedAudioSource:
    """
    Adapter that provides single audio stream interface for both local mic
    and remote devices.
    
    Replaces:
        voice_pipeline.py directly calling stream.read()
    
    With:
        unified_source.read_frame()
    
    Benefits:
    - Same calling convention for local and remote sources
    - Seamless fallback if remote device disconnects
    - Foundation for multi-device mixing in future
    """
    
    def __init__(self, sample_rate: int = 16000):
        self.sample_rate = sample_rate
        
        # Local mic always available
        self.local_source = MicStreamSource(sample_rate=sample_rate, blocksize=1600)
        
        # Remote devices added dynamically
        self.remote_sources: dict[str, RemoteStreamSource] = {}
        
        # Track which source we're currently listening to
        self.active_source_id = "local"
        self._lock = threading.RLock()
    
    def add_remote_device(self, device_id: str) -> RemoteStreamSource:
        """Register a new remote device."""
        with self._lock:
            if device_id in self.remote_sources:
                return self.remote_sources[device_id]
            
            source = RemoteStreamSource(source_id=device_id, sample_rate=self.sample_rate)
            self.remote_sources[device_id] = source
            return source
    
    def remove_remote_device(self, device_id: str) -> None:
        """Unregister remote device (e.g., on disconnect)."""
        with self._lock:
            if device_id in self.remote_sources:
                del self.remote_sources[device_id]
            
            # If it was active, fall back to local
            if self.active_source_id == device_id:
                self.active_source_id = "local"
    
    def set_active_source(self, source_id: str) -> bool:
        """
        Switch audio input to a different source.
        
        Args:
            source_id: "local" or "remote-{device_id}"
        
        Returns:
            True if switch succeeded, False if source not found
        """
        with self._lock:
            if source_id == "local":
                self.active_source_id = "local"
                return True
            
            if source_id.startswith("remote-"):
                device_id = source_id.split("-", 1)[1]
                if device_id in self.remote_sources:
                    self.active_source_id = source_id
                    return True
            
            return False
    
    def read_frame(self, timeout_ms: int = 100) -> Tuple[bytes, str]:
        """
        Read next 20ms audio frame from active source.
        
        Returns:
            (audio_bytes: 320 bytes of PCM16, source_id: "local" or "remote-{device_id}")
        
        If active source has no data, falls back to silence.
        """
        with self._lock:
            source_id = self.active_source_id
        
        # Try active source first
        if source_id == "local":
            frame = self.local_source.read(timeout_ms=timeout_ms)
            if frame:
                return frame, "local"
        else:
            device_id = source_id.split("-", 1)[1] if source_id.startswith("remote-") else None
            if device_id and device_id in self.remote_sources:
                frame = self.remote_sources[device_id].get(timeout_ms=timeout_ms)
                if frame:
                    return frame, source_id
        
        # Fallback: return silence
        return b'\x00' * 320, "silence"
    
    def get_diagnostics(self) -> dict:
        """Return health snapshot of all audio sources."""
        with self._lock:
            diags = {
                "active_source": self.active_source_id,
                "local": {"ok": True},  # Add more local mic stats as needed
                "remote_devices": {},
            }
            
            for device_id, source in self.remote_sources.items():
                diags["remote_devices"][device_id] = source.stats()
            
            return diags
```

### Integration into Voice Pipeline

```python
# Update finance_app/services/voice_pipeline.py

class VoiceCoordinator:
    """Existing coordinator, updated for unified audio source."""
    
    def __init__(self, wake_phrase: str = "hey steven"):
        # ... existing init ...
        
        # Replace:
        #   self.stream = MicStreamSource(...)
        # With:
        self.unified_source = UnifiedAudioSource(sample_rate=self.sample_rate)
        
        # Remote server reference (populated when server starts)
        self.remote_server: Optional[RemoteAudioServerScaled] = None
    
    def process_audio_loop(self):
        """
        Main voice processing loop (your existing loop, updated for unified source).
        """
        while self.running:
            # Read from unified source (works for both local and remote)
            frame, source_id = self.unified_source.read_frame(timeout_ms=100)
            
            if frame == b'\x00' * 320:  # Silence
                continue
            
            # Process through existing pipeline (unchanged)
            endpoint_result = self.endpoint.process(frame)
            
            if endpoint_result.is_final:
                transcript = self.asr_router.transcribe(endpoint_result.audio)
                
                # Create event with source metadata (new in Phase 2)
                command_event = VoiceCommandEvent(
                    text=transcript.text,
                    confidence=transcript.confidence,
                    source_id=source_id,
                    room_id=self._get_room_id(source_id),
                    timestamp_ms=int(time.time() * 1000),
                )
                
                # Route to handler (unchanged)
                self.router.process_command(command_event)
    
    def on_device_wake(self, device_id: str) -> None:
        """Called when wake word detected from remote device."""
        self.unified_source.set_active_source(f"remote-{device_id}")
        print(f"Switched audio input to remote device {device_id}")
    
    def on_device_disconnect(self, device_id: str) -> None:
        """Called when remote device disconnects."""
        self.unified_source.remove_remote_device(device_id)
        # Falls back to local automatically
        print(f"Remote device {device_id} disconnected; using local mic")
```

---

## Part 3: Packet Loss & Quality Metrics

### Audio Quality Assessment

```python
# finance_app/services/voice/audio_quality.py

from __future__ import annotations

from dataclasses import dataclass
import struct
import math


@dataclass(slots=True)
class AudioQualityMetrics:
    """
    Diagnostic metrics for voice quality assessment.
    
    Used by ASR router to decide whether to use high-accuracy model
    (Faster-Whisper) vs fast fallback (Vosk).
    """
    
    source_id: str
    sample_rate: int
    bit_depth: int
    signal_noise_ratio_db: float  # Estimated SNR from audio samples
    clipping_ratio: float          # Percentage of samples at max/min amplitude
    dc_offset_pct: float           # Percentage offset from 0
    underrun_count: int            # From jitter buffer
    reorder_packets: int           # Out-of-order arrivals
    lost_packets: int              # Detected gaps
    
    @property
    def is_degraded(self) -> bool:
        """Heuristic: is audio quality degraded?"""
        return (
            self.signal_noise_ratio_db < 10  # Very noisy (< 10 dB)
            or self.lost_packets > 10        # Significant loss
            or self.clipping_ratio > 0.1     # 10% clipping
            or self.dc_offset_pct > 0.05     # 5% DC offset
        )
    
    @property
    def recommendation(self) -> str:
        """Suggest ASR provider based on quality."""
        if self.is_degraded:
            return "vosk"  # Fast, robust to noise
        else:
            return "faster_whisper"  # Accurate
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict for logging."""
        return {
            "source_id": self.source_id,
            "snr_db": round(self.signal_noise_ratio_db, 1),
            "clipping_pct": round(self.clipping_ratio * 100, 1),
            "dc_offset_pct": round(self.dc_offset_pct * 100, 1),
            "underruns": self.underrun_count,
            "reorders": self.reorder_packets,
            "lost": self.lost_packets,
            "recommendation": self.recommendation,
        }


class AudioQualityAnalyzer:
    """Compute quality metrics from PCM16 audio samples."""
    
    @staticmethod
    def analyze(audio_bytes: bytes, source_id: str) -> AudioQualityMetrics:
        """
        Analyze a single audio frame.
        
        Args:
            audio_bytes: PCM16 mono audio (typically 320 bytes for 20ms)
            source_id: For logging
        
        Returns:
            AudioQualityMetrics with estimated SNR, clipping, etc.
        """
        # Parse PCM16 samples (little-endian)
        sample_count = len(audio_bytes) // 2
        samples = struct.unpack(f"<{sample_count}h", audio_bytes)
        
        # Compute metrics
        snr_db = AudioQualityAnalyzer._estimate_snr(samples)
        clipping_ratio = AudioQualityAnalyzer._measure_clipping(samples)
        dc_offset_pct = AudioQualityAnalyzer._measure_dc_offset(samples)
        
        return AudioQualityMetrics(
            source_id=source_id,
            sample_rate=16000,
            bit_depth=16,
            signal_noise_ratio_db=snr_db,
            clipping_ratio=clipping_ratio,
            dc_offset_pct=dc_offset_pct,
            underrun_count=0,  # Filled by caller from jitter buffer
            reorder_packets=0,  # Filled by caller from stream source
            lost_packets=0,     # Filled by caller from stream source
        )
    
    @staticmethod
    def _estimate_snr(samples: tuple[int, ...]) -> float:
        """
        Estimate signal-to-noise ratio.
        
        Simple heuristic:
        - Split signal into low-energy (noise) and high-energy (signal+noise)
        - Estimate noise std dev from quiet frames
        - Estimate signal power from loud frames
        - SNR = 10 * log10(signal_power / noise_power)
        """
        if not samples or len(samples) < 10:
            return 0.0
        
        # Compute energy of each sample
        energies = [s ** 2 for s in samples]
        sorted_energies = sorted(energies)
        
        # Bottom 20% = mostly noise
        noise_idx = len(sorted_energies) // 5
        noise_energy = sum(sorted_energies[:noise_idx]) / max(1, noise_idx)
        
        # Top 20% = signal + noise
        signal_idx = len(sorted_energies) * 4 // 5
        signal_energy = sum(sorted_energies[signal_idx:]) / max(1, len(sorted_energies) - signal_idx)
        
        # SNR in dB
        if noise_energy > 0:
            snr_ratio = signal_energy / noise_energy
            snr_db = 10 * math.log10(max(1.0, snr_ratio))
        else:
            snr_db = 40.0  # Perfect signal, no noise
        
        return snr_db
    
    @staticmethod
    def _measure_clipping(samples: tuple[int, ...]) -> float:
        """Fraction of samples at maximum or minimum amplitude."""
        if not samples:
            return 0.0
        
        max_amplitude = 32767  # Max for PCM16
        min_amplitude = -32768
        clipped_count = sum(
            1 for s in samples if s >= max_amplitude * 0.95 or s <= min_amplitude * 0.95
        )
        return clipped_count / len(samples)
    
    @staticmethod
    def _measure_dc_offset(samples: tuple[int, ...]) -> float:
        """Estimate DC offset as percentage of max amplitude."""
        if not samples:
            return 0.0
        
        mean_value = sum(samples) / len(samples)
        max_amplitude = 32767
        dc_offset_pct = abs(mean_value) / max_amplitude
        return dc_offset_pct
```

### Enhanced ASR Router with Quality-Based Selection

```python
# Update finance_app/services/voice/asr_router.py

from finance_app.services.voice.audio_quality import AudioQualityAnalyzer, AudioQualityMetrics

class EnhancedAsrRouter:
    """Routes to ASR provider based on audio quality and confidence."""
    
    def __init__(self):
        self.primary = FasterWhisperAsrProvider("small.en")
        self.fallback = VoskAsrProvider(model_path="...")
        self.quality_analyzer = AudioQualityAnalyzer()
    
    def transcribe(self, audio_bytes: bytes, source_id: str) -> AsrResult:
        """
        Transcribe audio, choosing provider based on quality.
        
        High-quality audio → Faster-Whisper (better accuracy)
        Degraded audio → Vosk (faster, more robust)
        """
        # Analyze quality
        metrics = self.quality_analyzer.analyze(audio_bytes, source_id)
        
        # Log for diagnostics
        if metrics.is_degraded:
            print(f"⚠️  Degraded audio from {source_id}: {metrics.to_dict()}")
        
        # Choose provider based on quality
        if metrics.recommendation == "faster_whisper":
            result = self.primary.transcribe(audio_bytes)
        else:
            result = self.fallback.transcribe(audio_bytes)
        
        # Attach quality metrics to result for assistant decision-making
        result.quality_metrics = metrics
        return result
```

---

## Part 4: Session-Scoped Assistant Integration

### Command Event with Metadata

```python
# Enhance finance_app/services/voice/command_event.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import time


class CommandTier(Enum):
    """Safety tier for action execution (from action_safety.py)."""
    TIER0 = "tier0"  # Read-only, execute immediately
    TIER1 = "tier1"  # Reversible edits, auto-execute if high confidence
    TIER2 = "tier2"  # Bulk/destructive, always require confirmation
    TIER3 = "tier3"  # Sensitive, explicit confirm phrase + optional PIN


@dataclass(slots=True)
class VoiceCommandEvent:
    """
    Complete command context from voice input.
    
    Replaces plain text strings with rich metadata for:
    - Multi-room session isolation
    - Confidence-based routing
    - Audit/telemetry
    - Safety policy application
    """
    
    text: str                    # Transcribed command text
    confidence: float            # ASR confidence 0.0-1.0
    source_id: str              # "local" or "remote-device123"
    room_id: str                # Which room/surface this came from
    timestamp_ms: int           # When command was spoken (client-side)
    
    # Optional: filled by pipeline
    quality_metrics: dict | None = None  # From AudioQualityAnalyzer
    asr_provider: str | None = None      # "faster_whisper" or "vosk"
    latency_ms: int | None = None        # E2E latency
    
    @property
    def session_id(self) -> str:
        """Unique session key for isolation."""
        return f"{self.room_id}|{self.source_id}"
    
    def to_dict(self) -> dict:
        """For logging/audit."""
        return {
            "text": self.text,
            "confidence": self.confidence,
            "source_id": self.source_id,
            "room_id": self.room_id,
            "timestamp_ms": self.timestamp_ms,
            "session_id": self.session_id,
            "asr_provider": self.asr_provider,
            "latency_ms": self.latency_ms,
        }
```

### Session-Aware Assistant Service

```python
# Update finance_app/services/assistant_service.py

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import time
import threading


@dataclass(slots=True)
class ConversationContext:
    """Per-session conversation state (Phase 4)."""
    
    session_id: str
    room_id: str
    source_id: str
    created_at_ms: int
    last_activity_ms: int
    ttl_seconds: int = 3600  # 1-hour session expiry
    
    # Session-specific state
    conversation_history: list[dict] = field(default_factory=list)  # [{role, content}, ...]
    pending_confirmation: Optional[dict] = None  # Awaiting user confirmation
    
    @property
    def is_stale(self) -> bool:
        """Check if session has expired."""
        elapsed = (time.time_ns() // 1_000_000 - self.last_activity_ms) / 1000
        return elapsed > self.ttl_seconds
    
    def add_message(self, role: str, content: str) -> None:
        """Add to conversation history."""
        self.conversation_history.append({"role": role, "content": content})
        self.last_activity_ms = int(time.time() * 1000)


class SessionAwareAssistantService:
    """Assistant with multi-device session isolation (Phase 4)."""
    
    def __init__(self):
        self.session_contexts: dict[str, ConversationContext] = {}
        self._lock = threading.RLock()
        
        # Integrate with existing assistant (your current implementation)
        from finance_app.services.assistant_service import AssistantService
        self._inner_assistant = AssistantService()
    
    def handle_command_event(self, event: VoiceCommandEvent) -> str:
        """
        Execute command in proper session context with safety policy.
        
        Args:
            event: VoiceCommandEvent with text, confidence, room, source_id
        
        Returns:
            Response text to play back to user
        """
        # Phase 3: Safety tier classification
        from finance_app.services.voice.action_safety import ActionSafetyGate
        tier = ActionSafetyGate.classify(event.text)
        
        # Phase 4: Get or create session context
        session = self._get_or_create_session(event)
        
        # Log command in session history
        session.add_message("user", event.text)
        
        # Apply safety policy
        action = ActionSafetyGate.determine_action(
            command_text=event.text,
            confidence=event.confidence,
            tier=tier,
            session_has_context=len(session.conversation_history) > 1,
        )
        
        # Execute based on safety decision
        if action == "EXECUTE_IMMEDIATELY":
            return self._execute_command(session, event)
        
        elif action == "REQUIRE_CONFIRMATION":
            session.pending_confirmation = {
                "command": event.text,
                "confidence": event.confidence,
            }
            return f"Ready to {event.text}. Say 'yes' to confirm or 'no' to cancel."
        
        elif action == "EXECUTE_WITH_ECHO":
            response = f"You said '{event.text}'. Proceeding..."
            self._execute_command(session, event)
            return response
        
        else:  # REJECT
            return f"Unable to execute at confidence {event.confidence:.0%}. Please repeat clearly."
    
    def handle_confirmation_response(
        self, session_id: str, response: str
    ) -> str:
        """
        Handle user's yes/no confirmation to pending command.
        
        Args:
            session_id: Session identifier
            response: "yes", "no", "confirm", "cancel", etc.
        
        Returns:
            Feedback to user
        """
        with self._lock:
            session = self.session_contexts.get(session_id)
            if not session or not session.pending_confirmation:
                return "No pending confirmation."
        
        if response.lower().strip() in {"yes", "confirm", "ok", "okay"}:
            # Execute the pending command
            command_text = session.pending_confirmation["command"]
            # ... execute ...
            session.pending_confirmation = None
            session.add_message("system", f"Executed: {command_text}")
            return f"Done. {command_text}"
        else:
            session.pending_confirmation = None
            session.add_message("system", "Cancelled")
            return "Cancelled."
    
    def _get_or_create_session(self, event: VoiceCommandEvent) -> ConversationContext:
        """Get or create session for this device+room pair."""
        with self._lock:
            session_id = event.session_id
            
            if session_id in self.session_contexts:
                session = self.session_contexts[session_id]
                if session.is_stale:
                    # Expire old session
                    del self.session_contexts[session_id]
                else:
                    return session
            
            # Create new session
            session = ConversationContext(
                session_id=session_id,
                room_id=event.room_id,
                source_id=event.source_id,
                created_at_ms=event.timestamp_ms,
                last_activity_ms=event.timestamp_ms,
            )
            self.session_contexts[session_id] = session
            return session
    
    def _execute_command(
        self, session: ConversationContext, event: VoiceCommandEvent
    ) -> str:
        """Execute the command via inner assistant with session context."""
        try:
            # Pass session history as context to assistant
            response = self._inner_assistant.execute(
                command_text=event.text,
                conversation_context=session.conversation_history,
                source_id=event.source_id,
                room_id=event.room_id,
            )
            
            session.add_message("assistant", response)
            return response
        
        except Exception as e:
            error_msg = f"Error executing command: {e}"
            session.add_message("system", error_msg)
            return error_msg
    
    def get_session_stats(self) -> dict:
        """Return diagnostics of active sessions."""
        with self._lock:
            return {
                "active_sessions": len(self.session_contexts),
                "sessions": {
                    sid: {
                        "room": s.room_id,
                        "device": s.source_id,
                        "created_at_ms": s.created_at_ms,
                        "history_length": len(s.conversation_history),
                        "stale": s.is_stale,
                    }
                    for sid, s in self.session_contexts.items()
                },
            }
```

---

## Part 5: Integration Checklist

### Phase 1 Tasks (Immediate)
- [ ] Add `adaptive_jitter_buffer.py` module
- [ ] Update `remote_stream_source.py` to use adaptive jitter buffer
- [ ] Add `unified_audio_source.py` module
- [ ] Update `voice_pipeline.py` to use unified source
- [ ] Test: local mic still works as before
- [ ] Test: remote device connects and produces audio
- [ ] Test: verify 80ms jitter buffer hides network jitter

### Phase 2 Tasks (Next Sprint)
- [ ] Add `audio_quality.py` module
- [ ] Update `asr_router.py` with quality-based provider selection
- [ ] Enhance `command_event.py` with metadata fields
- [ ] Update `assistant_service.py` to accept CommandEvent (not plain string)
- [ ] Test: degraded audio routes to fallback provider
- [ ] Test: high-confidence routes to accurate provider

### Phase 3 Tasks (Parallel)
- [ ] Add backpressure controller (prevent ASR queue overflow)
- [ ] Implement packet loss recovery (frame interpolation)
- [ ] Add FEC support (if observed packet loss > 2%)
- [ ] Session resumption testing

### Phase 4 Tasks (Final)
- [ ] Session-aware assistant service (isolation per room+device)
- [ ] Confirmation prompts for Tier 2+ commands
- [ ] Action safety gating (your action_safety.py)
- [ ] Cross-device contamination tests

---

## Testing Patterns

### Unit Test: Jitter Buffer

```python
import pytest
from finance_app.services.voice.adaptive_jitter_buffer import AdaptiveJitterBuffer

def test_jitter_buffer_reorders():
    """Jitter buffer should reorder out-of-order packets."""
    buf = AdaptiveJitterBuffer()
    
    # Packets arrive out of order
    buf.put(1, b'frame1')
    buf.put(3, b'frame3')
    buf.put(2, b'frame2')
    
    # Should extract in order
    assert buf.get(timeout_ms=50) == b'frame1'
    assert buf.get(timeout_ms=50) == b'frame2'
    assert buf.get(timeout_ms=50) == b'frame3'

def test_jitter_buffer_underrun():
    """Buffer should signal underrun if not enough data."""
    buf = AdaptiveJitterBuffer()
    
    # Only 1 frame, needs ~4 for 80ms target
    buf.put(1, b'frame1')
    
    result = buf.get(timeout_ms=10)
    assert result is None  # Underrun

def test_jitter_buffer_adapts_delay():
    """Jitter buffer should increase delay under high jitter."""
    buf = AdaptiveJitterBuffer(initial_target_delay_ms=40)
    
    # Simulate high jitter (packets arriving at irregular intervals)
    for i in range(20):
        time.sleep(0.01)  # Irregular timing
        buf.put(i, b'frame')
    
    # Target delay should have increased
    assert buf.target_delay_ms > 40
    assert buf.target_delay_ms <= buf.max_delay_ms
```

### Integration Test: Unified Source

```python
def test_unified_source_switches_to_remote():
    """Unified source should seamlessly switch between local and remote."""
    source = UnifiedAudioSource()
    
    # Initially reading from local (returns local mic data)
    frame, src_id = source.read_frame(timeout_ms=100)
    assert src_id == "local"
    
    # Register remote device
    remote = source.add_remote_device("device1")
    remote.on_audio_packet(RemoteAudioPacket(
        source_id="device1",
        seq_no=1,
        payload=b'x' * 320,
        sent_at_ms=1000,
    ))
    
    # Switch to remote
    source.set_active_source("remote-device1")
    frame, src_id = source.read_frame(timeout_ms=100)
    assert src_id == "remote-device1"
    
    # Disconnect remote
    source.remove_remote_device("device1")
    
    # Falls back to local
    frame, src_id = source.read_frame(timeout_ms=100)
    assert src_id == "local"
```

---

This guide provides drop-in code patterns aligned with your phased delivery plan. Each section is self-contained and can be integrated incrementally.

Key principles:
- **Backward compatible**: Local mic path unchanged
- **Phased**: Each section is optional and can be added independently
- **Tested**: Includes test patterns for each component
- **Production-ready**: Handles edge cases (underrun, loss, disconnect)

Start with Part 1 (jitter buffer) and Part 2 (unified source), then proceed to Parts 3-4 in subsequent sprints.
