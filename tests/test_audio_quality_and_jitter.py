from __future__ import annotations

import math
import struct
import unittest

from finance_app.services.voice.audio_quality import analyze_pcm16
from finance_app.services.voice.jitter_buffer import (
    MAX_DELAY_MS,
    MIN_DELAY_MS,
    AdaptiveJitterBuffer,
)


def _tone(amplitude: int, samples: int = 1600, sample_rate: int = 16000) -> bytes:
    values = [
        int(amplitude * math.sin(2 * math.pi * 440 * index / sample_rate)) for index in range(samples)
    ]
    return struct.pack(f"<{len(values)}h", *values)


class AudioQualityTests(unittest.TestCase):
    def test_silence_reports_floor_level(self) -> None:
        metrics = analyze_pcm16(b"\x00\x00" * 800)

        self.assertEqual(metrics.rms_dbfs, -120.0)
        self.assertEqual(metrics.clipped_ratio, 0.0)
        self.assertTrue(metrics.is_too_quiet)

    def test_loud_tone_is_not_flagged_as_quiet(self) -> None:
        metrics = analyze_pcm16(_tone(20000))

        self.assertGreater(metrics.rms_dbfs, -20.0)
        self.assertFalse(metrics.is_too_quiet)
        self.assertFalse(metrics.is_clipping)

    def test_clipped_audio_is_detected(self) -> None:
        metrics = analyze_pcm16(struct.pack("<800h", *([32767] * 800)))

        self.assertEqual(metrics.clipped_ratio, 1.0)
        self.assertTrue(metrics.is_clipping)

    def test_empty_and_odd_length_payloads_are_safe(self) -> None:
        self.assertEqual(analyze_pcm16(b"").frames, 0)
        self.assertEqual(analyze_pcm16(b"\x01").frames, 0)

    def test_noisy_signal_scores_lower_snr_than_clean_speech(self) -> None:
        quiet = bytes(400)
        loud = _tone(20000, samples=200)
        clean = analyze_pcm16(quiet + loud + quiet + loud)
        constant = analyze_pcm16(_tone(20000, samples=1600))

        self.assertGreater(clean.estimated_snr_db, constant.estimated_snr_db)


class AdaptiveJitterBufferTests(unittest.TestCase):
    def setUp(self) -> None:
        self.buffer = AdaptiveJitterBuffer(baseline_delay_ms=80, expected_interval_ms=20)

    def test_packet_is_held_for_the_target_delay(self) -> None:
        self.buffer.push(1, b"a", arrival_ms=0)

        self.assertEqual(self.buffer.pop_ready(now_ms=50), [])
        self.assertEqual(self.buffer.pop_ready(now_ms=80), [b"a"])

    def test_out_of_order_packets_are_released_in_sequence(self) -> None:
        self.buffer.push(2, b"b", arrival_ms=0)
        self.buffer.push(1, b"a", arrival_ms=5)

        self.assertEqual(self.buffer.pop_ready(now_ms=200), [b"a", b"b"])

    def test_duplicate_and_late_packets_are_dropped(self) -> None:
        self.buffer.push(1, b"a", arrival_ms=0)
        self.assertFalse(self.buffer.push(1, b"a", arrival_ms=1))

        self.buffer.pop_ready(now_ms=200)
        self.assertFalse(self.buffer.push(1, b"a", arrival_ms=201))
        self.assertEqual(self.buffer.dropped_late, 1)

    def test_gap_is_skipped_once_the_hold_time_expires(self) -> None:
        self.buffer.push(1, b"a", arrival_ms=0)
        self.buffer.push(3, b"c", arrival_ms=20)

        self.assertEqual(self.buffer.pop_ready(now_ms=90), [b"a"])
        self.assertEqual(self.buffer.pop_ready(now_ms=200), [b"c"])
        self.assertEqual(self.buffer.skipped_gaps, 1)

    def test_target_delay_grows_with_jitter_and_stays_in_range(self) -> None:
        baseline = self.buffer.target_delay_ms
        arrival = 0.0
        for seq_no in range(1, 40):
            arrival += 20 if seq_no % 2 else 220
            self.buffer.push(seq_no, b"x", arrival_ms=arrival)
            self.buffer.pop_ready(now_ms=arrival)

        self.assertGreater(self.buffer.target_delay_ms, baseline)
        self.assertLessEqual(self.buffer.target_delay_ms, MAX_DELAY_MS)
        self.assertGreaterEqual(self.buffer.target_delay_ms, MIN_DELAY_MS)

    def test_overflow_is_bounded(self) -> None:
        buffer = AdaptiveJitterBuffer(max_packets=8)
        for seq_no in range(1, 20):
            buffer.push(seq_no, b"x", arrival_ms=seq_no)

        self.assertEqual(buffer.pending, 8)
        self.assertGreater(buffer.dropped_overflow, 0)

    def test_flush_releases_everything_in_order_and_resets(self) -> None:
        self.buffer.push(2, b"b", arrival_ms=0)
        self.buffer.push(1, b"a", arrival_ms=0)

        self.assertEqual(self.buffer.flush(), [b"a", b"b"])
        self.assertEqual(self.buffer.pending, 0)
        self.assertTrue(self.buffer.push(1, b"a", arrival_ms=0))


if __name__ == "__main__":
    unittest.main()
