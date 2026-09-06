"""Adaptive jitter buffer for remote audio (staged for the Phase 3b datagram transport).

The Phase 1 transport is TCP/TLS, which already delivers in order, so this buffer is not
wired into the ingest path yet; it exists so the UDP/Opus switch can reorder and smooth
arrivals without redesigning the receive side.
"""

from __future__ import annotations

from dataclasses import dataclass

MIN_DELAY_MS = 40
MAX_DELAY_MS = 150
BASELINE_DELAY_MS = 80


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(slots=True)
class _BufferedPacket:
    seq_no: int
    payload: bytes
    arrival_ms: float


class AdaptiveJitterBuffer:
    """Reorders packets by sequence number and holds them for an adaptive delay."""

    def __init__(
        self,
        baseline_delay_ms: float = BASELINE_DELAY_MS,
        expected_interval_ms: float = 20.0,
        max_packets: int = 256,
    ) -> None:
        self._baseline_delay_ms = _clamp(baseline_delay_ms, MIN_DELAY_MS, MAX_DELAY_MS)
        self._expected_interval_ms = max(1.0, float(expected_interval_ms))
        self._max_packets = max(8, int(max_packets))
        self._packets: dict[int, _BufferedPacket] = {}
        self._next_seq: int | None = None
        self._last_seq: int | None = None
        self._last_arrival_ms: float | None = None
        self._jitter_ms = 0.0
        self._target_delay_ms = self._baseline_delay_ms
        self.dropped_late = 0
        self.dropped_overflow = 0
        self.skipped_gaps = 0

    @property
    def target_delay_ms(self) -> int:
        return int(round(self._target_delay_ms))

    @property
    def jitter_ms(self) -> float:
        return self._jitter_ms

    @property
    def pending(self) -> int:
        return len(self._packets)

    def push(self, seq_no: int, payload: bytes, arrival_ms: float) -> bool:
        """Buffer a packet. False when it is a duplicate, too late, or the buffer is full."""
        if self._next_seq is not None and seq_no < self._next_seq:
            self.dropped_late += 1
            return False
        if seq_no in self._packets:
            return False
        if len(self._packets) >= self._max_packets:
            self.dropped_overflow += 1
            return False

        self._update_jitter(seq_no, arrival_ms)
        self._packets[seq_no] = _BufferedPacket(seq_no=seq_no, payload=payload, arrival_ms=arrival_ms)
        return True

    def pop_ready(self, now_ms: float) -> list[bytes]:
        """Release every packet whose hold time has elapsed, in sequence order."""
        released: list[bytes] = []
        while self._packets:
            if self._next_seq is None:
                self._next_seq = min(self._packets)

            packet = self._packets.get(self._next_seq)
            if packet is not None:
                if (now_ms - packet.arrival_ms) < self._target_delay_ms:
                    break
                released.append(packet.payload)
                del self._packets[self._next_seq]
                self._next_seq += 1
                continue

            # A gap: wait out the hold time before declaring the missing packet lost.
            oldest_seq = min(self._packets)
            if (now_ms - self._packets[oldest_seq].arrival_ms) < self._target_delay_ms:
                break
            self.skipped_gaps += oldest_seq - self._next_seq
            self._next_seq = oldest_seq

        return released

    def flush(self) -> list[bytes]:
        """Release everything buffered and start a new stream."""
        released = [self._packets[seq].payload for seq in sorted(self._packets)]
        self.reset()
        return released

    def reset(self) -> None:
        self._packets.clear()
        self._next_seq = None
        self._last_seq = None
        self._last_arrival_ms = None
        self._jitter_ms = 0.0
        self._target_delay_ms = self._baseline_delay_ms

    def _update_jitter(self, seq_no: int, arrival_ms: float) -> None:
        if self._last_seq is not None and self._last_arrival_ms is not None:
            expected_ms = (seq_no - self._last_seq) * self._expected_interval_ms
            deviation = abs((arrival_ms - self._last_arrival_ms) - expected_ms)
            # RFC 3550 style smoothing so one late packet cannot spike the target delay.
            self._jitter_ms += (deviation - self._jitter_ms) / 16.0
            self._target_delay_ms = _clamp(
                self._baseline_delay_ms + 2.0 * self._jitter_ms, MIN_DELAY_MS, MAX_DELAY_MS
            )

        if self._last_seq is None or seq_no > self._last_seq:
            self._last_seq = seq_no
            self._last_arrival_ms = arrival_ms
