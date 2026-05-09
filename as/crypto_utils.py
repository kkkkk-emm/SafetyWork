"""Crypto helpers for AS using project-local handwritten DES/RSA code."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import sys
from typing import Any, Dict, Tuple


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared_crypto.des import DES_BLOCK_BYTES, DES_KEY_BYTES, cbc_decrypt, cbc_encrypt
from shared_crypto.rsa import (
    decrypt_bytes,
    deserialize_private_key,
    deserialize_public_key,
    encrypt_bytes,
    envelope_from_bytes,
    envelope_to_bytes,
    generate_keypair,
    serialize_private_key,
    serialize_public_key,
)


PASSWORD_HASH_BYTES = 32
PASSWORD_SALT_BYTES = 16
PASSWORD_MIN_LENGTH = 8


class CryptoError(RuntimeError):
    pass


def b64encode(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def b64decode(value: str) -> bytes:
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise CryptoError("INVALID_BASE64") from exc


def generate_nonce() -> str:
    return secrets.token_urlsafe(18)


def generate_des_key() -> bytes:
    return os.urandom(DES_KEY_BYTES)


def generate_salt() -> bytes:
    return os.urandom(PASSWORD_SALT_BYTES)


def validate_password_policy(password: str) -> bool:
    if len(password) < PASSWORD_MIN_LENGTH:
        return False
    if re.search(r"[A-Z]", password) is None:
        return False
    if re.search(r"[a-z]", password) is None:
        return False
    if re.search(r"\d", password) is None:
        return False
    return True


def normalize_username(username: str) -> str:
    return username.strip().lower()


def derive_password_material(password: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iterations,
        dklen=PASSWORD_HASH_BYTES,
    )


def derive_kuser(password: str, salt: bytes, iterations: int) -> bytes:
    return derive_password_material(password, salt, iterations)[:DES_KEY_BYTES]


def verify_password_hash(
    password: str,
    salt: bytes,
    iterations: int,
    expected_hash: bytes,
) -> bool:
    actual = derive_password_material(password, salt, iterations)
    return hmac.compare_digest(actual, expected_hash)


def _json_bytes(obj: Dict[str, Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_object(raw: bytes) -> Dict[str, Any]:
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CryptoError("INVALID_JSON_PLAINTEXT") from exc
    if not isinstance(obj, dict):
        raise CryptoError("INVALID_JSON_PLAINTEXT")
    return obj


def des_encrypt_object(key: bytes, obj: Dict[str, Any]) -> str:
    if len(key) != DES_KEY_BYTES:
        raise CryptoError("INVALID_DES_KEY_LENGTH")
    iv = os.urandom(DES_BLOCK_BYTES)
    ciphertext = cbc_encrypt(key, iv, _json_bytes(obj))
    return b64encode(iv + ciphertext)


def des_decrypt_object(key: bytes, ciphertext_b64: str) -> Dict[str, Any]:
    if len(key) != DES_KEY_BYTES:
        raise CryptoError("INVALID_DES_KEY_LENGTH")

    raw = b64decode(ciphertext_b64)
    if len(raw) <= DES_BLOCK_BYTES:
        raise CryptoError("INVALID_DES_CIPHERTEXT")

    iv = raw[:DES_BLOCK_BYTES]
    ciphertext = raw[DES_BLOCK_BYTES:]
    try:
        plaintext = cbc_decrypt(key, iv, ciphertext)
    except ValueError as exc:
        raise CryptoError("INVALID_DES_PADDING") from exc
    return _json_object(plaintext)


def generate_rsa_key_pair(modulus_bits: int = 1024) -> Tuple[bytes, bytes]:
    keypair = generate_keypair(modulus_bits)
    return (
        serialize_private_key(keypair.private_key),
        serialize_public_key(keypair.public_key),
    )


def validate_rsa_private_key(private_key_bytes: bytes) -> None:
    try:
        deserialize_private_key(private_key_bytes)
    except Exception as exc:
        raise CryptoError("INVALID_RSA_PRIVATE_KEY") from exc


def rsa_encrypt_object(public_key_bytes: bytes, obj: Dict[str, Any]) -> str:
    try:
        public_key = deserialize_public_key(public_key_bytes)
        envelope = encrypt_bytes(_json_bytes(obj), public_key)
        return b64encode(envelope_to_bytes(envelope))
    except Exception as exc:
        raise CryptoError("RSA_ENCRYPT_FAILED") from exc


def rsa_decrypt_object(private_key_bytes: bytes, ciphertext_b64: str) -> Dict[str, Any]:
    try:
        private_key = deserialize_private_key(private_key_bytes)
        envelope = envelope_from_bytes(b64decode(ciphertext_b64))
        plaintext = decrypt_bytes(envelope, private_key)
    except CryptoError:
        raise
    except Exception as exc:
        raise CryptoError("RSA_DECRYPT_FAILED") from exc
    return _json_object(plaintext)
