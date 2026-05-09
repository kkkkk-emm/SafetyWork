"""Crypto helpers for GS using project-local handwritten DES code."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import sys
import time
from typing import Any, Dict


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from shared_crypto.des import DES_BLOCK_BYTES, DES_KEY_BYTES, cbc_decrypt, cbc_encrypt


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


def now_ms() -> int:
    return int(time.time() * 1000)


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
