"""Local encryption adapter for the supplied XGSS Java RSA example; no network calls."""
import base64
import json
import re
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa


def read_public_key(path: str | Path) -> rsa.RSAPublicKey:
    text = Path(path).read_text(encoding='utf-8-sig')
    if 'PRIVATE KEY' in text:
        raise ValueError('Provide an XGSS public key, not a private key')
    try:
        if '-----BEGIN PUBLIC KEY-----' in text:
            key = serialization.load_pem_public_key(text.encode('ascii'))
        else:
            match = re.search(r'publicKey:\s*([A-Za-z0-9+/=]+)', text)
            encoded = match.group(1) if match else ''.join(text.split())
            key = serialization.load_der_public_key(base64.b64decode(encoded, validate=True))
    except (ValueError, UnicodeError):
        raise ValueError('Invalid XGSS public key encoding') from None
    if not isinstance(key, rsa.RSAPublicKey) or key.key_size != 1024:
        raise ValueError('This adapter expects the documented 1024-bit RSA public key')
    return key


def encrypt_payload(payload: dict, public_key: rsa.RSAPublicKey) -> dict[str, str]:
    """117-byte PKCS#1 v1.5 blocks, concatenated then Base64 as in the supplied example.

    ASCII JSON escapes make the wire plaintext independent of the Java host's
    default charset for Unicode field values. This does not validate API fields.
    """
    if not isinstance(public_key, rsa.RSAPublicKey) or public_key.key_size != 1024:
        raise ValueError('This adapter expects the documented 1024-bit RSA public key')
    if not isinstance(payload, dict):
        raise ValueError('XGSS payload must be an object')
    plaintext = json.dumps(payload, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('ascii')
    if len(plaintext) > 16384:
        raise ValueError('XGSS login payload exceeds the local size limit')
    encrypted = b''.join(public_key.encrypt(plaintext[offset:offset + 117], padding.PKCS1v15())
                         for offset in range(0, len(plaintext), 117))
    return {'data': base64.b64encode(encrypted).decode('ascii')}
