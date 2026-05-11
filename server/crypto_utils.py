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
    """处理 CryptoError 相关的加密、解密或编码逻辑。"""
    pass


def b64encode(raw: bytes) -> str:
    """处理 b64encode 相关的加密、解密或编码逻辑。"""
    return base64.b64encode(raw).decode("ascii")


def b64decode(value: str) -> bytes:
    """处理 b64decode 相关的加密、解密或编码逻辑。"""
    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise CryptoError("INVALID_BASE64") from exc


def generate_nonce() -> str:
    """处理 generate_nonce 相关的加密、解密或编码逻辑。"""
    return secrets.token_urlsafe(18)


def now_ms() -> int:
    """处理 now_ms 相关的加密、解密或编码逻辑。"""
    return int(time.time() * 1000)


def _json_bytes(obj: Dict[str, Any]) -> bytes:
    """处理 _json_bytes 相关的加密、解密或编码逻辑。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_object(raw: bytes) -> Dict[str, Any]:
    """处理 _json_object 相关的加密、解密或编码逻辑。"""
    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CryptoError("INVALID_JSON_PLAINTEXT") from exc
    if not isinstance(obj, dict):
        raise CryptoError("INVALID_JSON_PLAINTEXT")
    return obj


def des_encrypt_object(key: bytes, obj: Dict[str, Any]) -> str:
    """处理 des_encrypt_object 相关的加密、解密或编码逻辑。"""
    if len(key) != DES_KEY_BYTES:
        raise CryptoError("INVALID_DES_KEY_LENGTH")

    # 每次加密都使用新的 IV，并把 IV 拼到密文前面，便于接收端直接解密。
    iv = os.urandom(DES_BLOCK_BYTES)
    ciphertext = cbc_encrypt(key, iv, _json_bytes(obj))
    return b64encode(iv + ciphertext)


def des_decrypt_object(key: bytes, ciphertext_b64: str) -> Dict[str, Any]:
    """处理 des_decrypt_object 相关的加密、解密或编码逻辑。"""
    if len(key) != DES_KEY_BYTES:
        raise CryptoError("INVALID_DES_KEY_LENGTH")

    raw = b64decode(ciphertext_b64)
    if len(raw) <= DES_BLOCK_BYTES:
        raise CryptoError("INVALID_DES_CIPHERTEXT")

    # 传输格式固定为 IV + DES-CBC 密文；长度校验先于切片，避免短密文被误解。
    iv = raw[:DES_BLOCK_BYTES]
    ciphertext = raw[DES_BLOCK_BYTES:]
    try:
        plaintext = cbc_decrypt(key, iv, ciphertext)
    except ValueError as exc:
        raise CryptoError("INVALID_DES_PADDING") from exc
    return _json_object(plaintext)
