"""TLS material and the same-port dispatch decision.

`server.tls.mode` is three-valued: false serves HTTP only, true serves HTTPS only, and "both" accepts either on one port by looking at the first byte a client sends.

Cert and key are set together or not at all.
Omitting both generates a self-signed pair once and reuses it.
"""

import datetime as dt
import ipaddress
import ssl
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from app.config.schema import ProxyConfig, TlsMode

# A TLS ClientHello starts with the handshake content type.
TLS_HANDSHAKE_BYTE = 0x16

CERT_FILENAME = "cert.pem"
KEY_FILENAME = "key.pem"
SELF_SIGNED_DAYS = 3650


class TlsConfigurationError(ValueError):
    """The TLS settings cannot produce a usable listener."""


@dataclass(frozen=True, slots=True)
class TlsMaterial:
    cert_path: Path
    key_path: Path
    generated: bool = False


def build_server_ssl_context(material: TlsMaterial) -> ssl.SSLContext:
    """Load the configured certificate pair into a server-side TLS context."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(material.cert_path, material.key_path)
    return context


def is_tls_handshake(first_byte: int) -> bool:
    """Whether a connection's first byte marks it as TLS.

    A plaintext HTTP request starts with a method letter.
    The two are therefore distinguishable without reading further.
    """
    return first_byte == TLS_HANDSHAKE_BYTE


def serves_plaintext(mode: TlsMode) -> bool:
    return mode is not True


def serves_tls(mode: TlsMode) -> bool:
    return mode is not False


def generate_self_signed(directory: Path, *, host: str = "localhost") -> TlsMaterial:
    """Write a self-signed pair into `directory` and return it.

    Deleting the directory is how an operator asks for a fresh pair.
    """
    directory.mkdir(parents=True, exist_ok=True)
    cert_path = directory / CERT_FILENAME
    key_path = directory / KEY_FILENAME

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = dt.datetime.now(dt.UTC)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(minutes=5))
        .not_valid_after(now + dt.timedelta(days=SELF_SIGNED_DAYS))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName(host),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    key_path.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    key_path.chmod(0o600)
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return TlsMaterial(cert_path=cert_path, key_path=key_path, generated=True)


def resolve_tls_material(config: ProxyConfig, *, tls_dir: Path) -> TlsMaterial | None:
    """Find or make the material for the configured mode.

    Returns None when the mode serves no TLS at all.
    A caller therefore cannot build an HTTPS listener for an HTTP-only deployment.
    """
    tls = config.server.tls
    if not serves_tls(tls.mode):
        return None

    if bool(tls.cert) != bool(tls.key):
        raise TlsConfigurationError("server.tls.cert and server.tls.key must be set together")

    if tls.cert and tls.key:
        cert_path = Path(tls.cert)
        key_path = Path(tls.key)
        for path in (cert_path, key_path):
            if not path.is_file():
                raise TlsConfigurationError(f"TLS file not found: {path}")
        return TlsMaterial(cert_path=cert_path, key_path=key_path)

    cert_path = tls_dir / CERT_FILENAME
    key_path = tls_dir / KEY_FILENAME
    if cert_path.is_file() and key_path.is_file():
        # Reuse rather than regenerate; a new pair every start would retrain every client.
        return TlsMaterial(cert_path=cert_path, key_path=key_path)
    return generate_self_signed(tls_dir)
