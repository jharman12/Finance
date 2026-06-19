from __future__ import annotations

import json
import os
import secrets
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(slots=True)
class RemoteVoiceCredentials:
    """TLS certificate, key, and shared token for remote audio connection."""

    tls_cert_pem: str
    tls_key_pem: str
    auth_token: str


class RemoteVoiceConfigManager:
    """Auto-generates and persists TLS certificates and auth tokens."""

    def __init__(self, config_dir: Optional[str | Path] = None) -> None:
        if config_dir is None:
            config_dir = Path.home() / ".finance-voice"
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._cert_path = self.config_dir / "tls-cert.pem"
        self._key_path = self.config_dir / "tls-key.pem"
        self._token_path = self.config_dir / "auth-token.txt"

    def get_credentials(self, device_name: str = "Finance Receiver") -> RemoteVoiceCredentials:
        """Get or auto-generate credentials."""
        if not self._cert_path.exists() or not self._key_path.exists():
            self._generate_tls_certificate(device_name)

        if not self._token_path.exists():
            self._generate_token()

        cert_pem = self._cert_path.read_text()
        key_pem = self._key_path.read_text()
        token = self._token_path.read_text().strip()

        return RemoteVoiceCredentials(tls_cert_pem=cert_pem, tls_key_pem=key_pem, auth_token=token)

    def get_token_only(self) -> str:
        """Get or generate auth token."""
        if not self._token_path.exists():
            self._generate_token()
        return self._token_path.read_text().strip()

    def _generate_tls_certificate(self, device_name: str) -> None:
        """Generate self-signed TLS certificate using OpenSSL or Python."""
        try:
            self._generate_tls_with_openssl(device_name)
        except Exception as exc:
            print(f"OpenSSL generation failed: {exc}. Falling back to Python cryptography.")
            try:
                self._generate_tls_with_cryptography(device_name)
            except Exception as exc2:
                raise RuntimeError(f"Could not generate TLS certificate: {exc2}") from exc2

    def _generate_tls_with_openssl(self, device_name: str) -> None:
        """Generate certificate using OpenSSL command line."""
        cmd = [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-sha256",
            "-days",
            "365",
            "-nodes",
            "-keyout",
            str(self._key_path),
            "-out",
            str(self._cert_path),
            "-subj",
            f"/CN={device_name}",
            "-addext",
            f"subjectAltName=DNS:{device_name}",
        ]
        subprocess.run(cmd, check=True, capture_output=True, timeout=30)

    def _generate_tls_with_cryptography(self, device_name: str) -> None:
        """Generate certificate using Python cryptography library."""
        try:
            from cryptography import x509
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.x509.oid import NameOID, ExtensionOID
        except ImportError:
            raise RuntimeError("cryptography library not available. Install OpenSSL or run: pip install cryptography")

        import datetime

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        subject = issuer = x509.Name(
            [
                x509.NameAttribute(NameOID.COMMON_NAME, device_name),
            ]
        )

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(datetime.datetime.utcnow() + datetime.timedelta(days=365))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(device_name)]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256())
        )

        key_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )

        cert_pem = cert.public_bytes(serialization.Encoding.PEM)

        self._key_path.write_bytes(key_pem)
        self._cert_path.write_bytes(cert_pem)

    def _generate_token(self) -> None:
        """Generate a random 32-byte auth token."""
        token = secrets.token_urlsafe(32)
        self._token_path.write_text(token)
        self._token_path.chmod(0o600)
