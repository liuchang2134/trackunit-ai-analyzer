import base64
import json
import pytest
pytest.importorskip('cryptography', reason='Install requirements-xgss.txt for optional XGSS tests')
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from app.xgss_crypto import read_public_key, encrypt_payload


@pytest.fixture(scope='module')
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=1024)


@pytest.mark.parametrize('size', [0, 107, 108, 109, 350])
def test_java_style_blocks_preserve_json_across_boundaries(private_key, size):
    payload = {'text': 'x' * size, 'lang': 'zh', 'username': '模拟用户'}
    result = encrypt_payload(payload, private_key.public_key())
    cipher = base64.b64decode(result['data'], validate=True)
    assert len(cipher) % 128 == 0
    chunks = [private_key.decrypt(cipher[i:i+128], padding.PKCS1v15()) for i in range(0, len(cipher), 128)]
    assert all(len(chunk) == 117 for chunk in chunks[:-1])
    assert json.loads(b''.join(chunks)) == payload
    assert b''.join(chunks).isascii()


def test_supplied_file_format_and_random_padding(tmp_path, private_key):
    key = private_key.public_key()
    der = key.public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    file = tmp_path / 'rsa.txt'
    file.write_text('publicKey: ' + base64.b64encode(der).decode() + '\nJava example follows', encoding='utf-8')
    loaded = read_public_key(file)
    assert loaded.public_numbers() == key.public_numbers()
    assert encrypt_payload({'vin': 'SYNTHETIC'}, loaded) != encrypt_payload({'vin': 'SYNTHETIC'}, loaded)


def test_invalid_or_private_key_is_rejected(tmp_path):
    file = tmp_path / 'rsa.txt'
    for content in ['invalid', '-----BEGIN PRIVATE KEY-----']:
        file.write_text(content)
        with pytest.raises(ValueError):read_public_key(file)


def test_other_key_size_and_oversized_payload_rejected(private_key):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048).public_key()
    with pytest.raises(ValueError):encrypt_payload({}, other)
    with pytest.raises(ValueError):encrypt_payload({'x': 'a' * 16384}, private_key.public_key())
