from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[2]
HOST = os.getenv("APP_HOSTNAME", "discord").strip().lower().rstrip(".") or "discord"
INSTANCE_DIR = Path(os.getenv("DISCORD_INSTANCE_DIR", str(ROOT / "instance"))).expanduser().resolve()
TLS_DIR = INSTANCE_DIR / "tls"
TLS_DIR.mkdir(parents=True, exist_ok=True)
CA_CERT = TLS_DIR / "local-ca.cer"
SERVER_CERT = TLS_DIR / "server-cert.pem"
SERVER_KEY = TLS_DIR / "server-key.pem"


def valid_existing() -> bool:
    if not (CA_CERT.is_file() and SERVER_CERT.is_file() and SERVER_KEY.is_file()):
        return False
    try:
        cert = x509.load_pem_x509_certificate(SERVER_CERT.read_bytes())
        now = datetime.now(timezone.utc)
        if cert.not_valid_after_utc <= now + timedelta(days=30):
            return False
        san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        return HOST in san.get_values_for_type(x509.DNSName)
    except Exception:
        return False


if not valid_existing():
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Local Development WebAuthn CA")])
    now = datetime.now(timezone.utc)
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=1825))
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=False, content_commitment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=True,
                                     crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, HOST)])
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(ca_cert.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=825))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(HOST)]), critical=False)
        .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
        .add_extension(x509.KeyUsage(digital_signature=True, key_encipherment=True, content_commitment=False,
                                     data_encipherment=False, key_agreement=False, key_cert_sign=False,
                                     crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
        .sign(ca_key, hashes.SHA256())
    )

    CA_CERT.write_bytes(ca_cert.public_bytes(serialization.Encoding.DER))
    SERVER_CERT.write_bytes(leaf_cert.public_bytes(serialization.Encoding.PEM) + ca_cert.public_bytes(serialization.Encoding.PEM))
    SERVER_KEY.write_bytes(leaf_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ))

print(str(CA_CERT))
