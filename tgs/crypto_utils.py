"""TGS 使用的密码学工具函数。

本模块集中实现 TGS 需要的基础操作:
- Base64 编解码。
- DES-CBC-PKCS7 加解密 JSON 对象。
- 8 字节 DES 会话密钥生成。
"""

import base64
import json
import os
from typing import Any, Dict

try:
    from Crypto.Cipher import DES
    from Crypto.Util.Padding import pad, unpad
except ImportError as exc:  # pragma: no cover - 仅依赖缺失时触发。
    DES = None
    pad = None
    unpad = None
    _DES_IMPORT_ERROR = exc
else:
    _DES_IMPORT_ERROR = None


DES_KEY_BYTES = 8
DES_BLOCK_BYTES = 8


class CryptoError(RuntimeError):
    """密码学处理错误。"""

    pass


def b64encode(raw: bytes) -> str:
    """把字节串编码为 Base64 文本。"""

    return base64.b64encode(raw).decode("ascii")


def b64decode(value: str) -> bytes:
    """把 Base64 文本解码为字节串。"""

    try:
        return base64.b64decode(value.encode("ascii"), validate=True)
    except Exception as exc:
        raise CryptoError("INVALID_BASE64") from exc


def generate_des_key() -> bytes:
    """生成 8 字节 DES key。"""

    return os.urandom(DES_KEY_BYTES)


def _json_bytes(obj: Dict[str, Any]) -> bytes:
    """把 JSON 对象稳定序列化成 UTF-8 字节。"""

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_object(raw: bytes) -> Dict[str, Any]:
    """把 UTF-8 JSON 字节解析成 dict。"""

    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise CryptoError("INVALID_JSON_PLAINTEXT") from exc

    if not isinstance(obj, dict):
        raise CryptoError("INVALID_JSON_PLAINTEXT")
    return obj


def _require_des() -> None:
    """确认 pycryptodome 的 DES 实现可用。"""

    if DES is None:
        raise CryptoError(
            "pycryptodome is required for DES-CBC support; install tgs/requirements.txt"
        ) from _DES_IMPORT_ERROR


def des_encrypt_object(key: bytes, obj: Dict[str, Any]) -> str:
    """用 DES-CBC-PKCS7 加密 JSON 对象。

    返回 Base64(iv + ciphertext)。
    """

    _require_des()
    if len(key) != DES_KEY_BYTES:
        raise CryptoError("INVALID_DES_KEY_LENGTH")

    iv = os.urandom(DES_BLOCK_BYTES)
    cipher = DES.new(key, DES.MODE_CBC, iv)
    ciphertext = cipher.encrypt(pad(_json_bytes(obj), DES_BLOCK_BYTES))
    return b64encode(iv + ciphertext)


def des_decrypt_object(key: bytes, ciphertext_b64: str) -> Dict[str, Any]:
    """解密 DES-CBC-PKCS7 加密的 JSON 对象。"""

    _require_des()
    if len(key) != DES_KEY_BYTES:
        raise CryptoError("INVALID_DES_KEY_LENGTH")

    raw = b64decode(ciphertext_b64)
    if len(raw) <= DES_BLOCK_BYTES:
        raise CryptoError("INVALID_DES_CIPHERTEXT")

    iv = raw[:DES_BLOCK_BYTES]
    ciphertext = raw[DES_BLOCK_BYTES:]
    cipher = DES.new(key, DES.MODE_CBC, iv)
    try:
        plaintext = unpad(cipher.decrypt(ciphertext), DES_BLOCK_BYTES)
    except ValueError as exc:
        raise CryptoError("INVALID_DES_PADDING") from exc
    return _json_object(plaintext)
