from __future__ import annotations

from typing import Callable

from finance_app.services.voice.audio_quality import analyze_pcm16
from finance_app.services.voice.network_transport import RemoteAudioPacket, RemoteAudioServer

QUALITY_SAMPLE_EVERY = 50


class RemoteStreamSource:
    """Bridges authenticated network audio packets into the voice coordinator."""

    def __init__(
        self,
        host: str,
        port: int,
        auth_token: str,
        max_chunk_bytes: int = 32768,
        max_messages_per_second: int = 120,
        tls_cert_path: str | None = None,
        tls_key_path: str | None = None,
        pairing_manager: object | None = None,
        sample_rate: int = 16000,
    ) -> None:
        self.sample_rate = sample_rate
        self._packet_counts: dict[str, int] = {}
        self.server = RemoteAudioServer(
            host=host,
            port=port,
            auth_token=auth_token,
            max_chunk_bytes=max_chunk_bytes,
            max_messages_per_second=max_messages_per_second,
            tls_cert_path=tls_cert_path,
            tls_key_path=tls_key_path,
            pairing_manager=pairing_manager,
        )

    @property
    def bound_port(self) -> int:
        return self.server.bound_port

    def start(
        self,
        on_audio_chunk: Callable[[str, bytes], None],
        on_status: Callable[[str], None] | None = None,
        on_error: Callable[[str], None] | None = None,
        on_diagnostic: Callable[[dict[str, object]], None] | None = None,
    ) -> None:
        self.server.on_status = on_status
        self.server.on_error = on_error
        self.server.on_diagnostic = on_diagnostic

        def handle_packet(packet: RemoteAudioPacket) -> None:
            self._sample_quality(packet, on_diagnostic)
            on_audio_chunk(packet.source_id, packet.payload)

        self.server.on_packet = handle_packet
        self.server.start()

    def _sample_quality(
        self,
        packet: RemoteAudioPacket,
        on_diagnostic: Callable[[dict[str, object]], None] | None,
    ) -> None:
        if on_diagnostic is None:
            return
        count = self._packet_counts.get(packet.source_id, 0) + 1
        self._packet_counts[packet.source_id] = count
        if count != 1 and (count % QUALITY_SAMPLE_EVERY) != 0:
            return
        try:
            metrics = analyze_pcm16(packet.payload, self.sample_rate)
            on_diagnostic(
                {
                    "event": "audio_quality",
                    "source_id": packet.source_id,
                    "packets": count,
                    "rms_dbfs": metrics.rms_dbfs,
                    "peak_dbfs": metrics.peak_dbfs,
                    "clipped_ratio": metrics.clipped_ratio,
                    "estimated_snr_db": metrics.estimated_snr_db,
                    "clipping": metrics.is_clipping,
                    "too_quiet": metrics.is_too_quiet,
                }
            )
        except Exception:
            return

    def stop(self) -> None:
        self.server.stop()

    def revoke_device_token(self, source_id: str) -> bool:
        return self.server.revoke_device_token(source_id)

    def has_device_token(self, source_id: str) -> bool:
        return self.server.has_device_token(source_id)

    def connected_source_ids(self) -> list[str]:
        return self.server.connected_source_ids()

    def send_to_device(self, source_id: str, message: dict[str, object]) -> bool:
        return self.server.send_to_device(source_id, message)
