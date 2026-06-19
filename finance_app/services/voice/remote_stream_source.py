from __future__ import annotations

from typing import Callable

from finance_app.services.voice.network_transport import RemoteAudioPacket, RemoteAudioServer


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
    ) -> None:
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
            on_audio_chunk(packet.source_id, packet.payload)

        self.server.on_packet = handle_packet
        self.server.start()

    def stop(self) -> None:
        self.server.stop()
