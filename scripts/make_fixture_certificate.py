"""Generate a local self-signed certificate for the XGSS fixture host.

The catalog reader only accepts `https://xgss.xcmg.com` — it checks the protocol
and the hostname — so a fixture served over plain http cannot exercise the marking
path at all. Serving the fixture over local https under that exact hostname, with
`--host-resolver-rules` pointing the name at loopback, makes `location.href` a real
XGSS URL without touching the network or the real site.

The key is written for a throwaway local server and is not a credential for
anything. It never leaves `.tmp/`.

    .\\.tmp\\venv\\Scripts\\python.exe scripts/make_fixture_certificate.py
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = ROOT / '.tmp/fixture-cert'
HOST = 'xgss.xcmg.com'


def write_certificate(directory: Path, host: str = HOST, days: int = 30) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    key_path = directory / 'key.pem'
    cert_path = directory / 'cert.pem'
    if key_path.is_file() and cert_path.is_file():
        return cert_path, key_path

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        # The fixture is reached at this name; a certificate without it would fail
        # the TLS handshake before any of the code under test runs.
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
        .sign(key, hashes.SHA256())
    )
    key_path.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    cert_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return cert_path, key_path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dir', type=Path, default=DEFAULT_DIR)
    parser.add_argument('--host', default=HOST)
    args = parser.parse_args(argv)
    cert, key = write_certificate(args.dir, args.host)
    print(f'certificate: {cert}')
    print(f'key        : {key}')
    print(f'host       : {args.host}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
