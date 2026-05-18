from __future__ import annotations

from dataclasses import dataclass
import json
import math
import secrets
from typing import Any


DEFAULT_PUBLIC_EXPONENT = 65537
DEFAULT_MILLER_RABIN_ROUNDS = 24


@dataclass(frozen=True)
class PublicKey:
    n: int
    e: int


@dataclass(frozen=True)
class PrivateKey:
    n: int
    d: int
    p: int
    q: int
    phi: int


@dataclass(frozen=True)
class RSAKeyPair:
    public_key: PublicKey
    private_key: PrivateKey

# 扩展欧几里得算法(a*x + b*y = gcd(a, b))
def egcd(a: int, b: int) -> tuple[int, int, int]:
    if b == 0:
        return a, 1, 0
    g, x1, y1 = egcd(b, a % b)
    return g, y1, x1 - (a // b) * y1

# 模逆运算(a*x ≡ 1 (mod n))
def mod_inverse(a: int, modulus: int) -> int:
    g, x, _ = egcd(a, modulus)
    if g != 1:
        raise ValueError("inverse does not exist")
    return x % modulus

# 快速幂算法
def qpow(base: int, exponent: int, modulus: int) -> int:
    if modulus <= 0:
        raise ValueError("modulus must be positive")
    if exponent < 0:
        raise ValueError("exponent must be non-negative")

    result = 1
    base %= modulus
    while exponent > 0:
        if exponent & 1:
            result = (result * base) % modulus
        base = (base * base) % modulus
        exponent >>= 1
    return result

# Miller-Rabin 素数测试
def is_prime(n: int, rounds: int = DEFAULT_MILLER_RABIN_ROUNDS) -> bool:
    if n < 2:
        return False

    small_primes = (
        2, 3, 5, 7, 11, 13, 17, 19, 23, 29,
        31, 37, 41, 43, 47, 53, 59, 61, 67, 71,
    )
    for prime in small_primes:
        if n == prime:
            return True
        if n % prime == 0:
            return False
    # 将 n-1 表示为 2^s * d，其中 d 是奇数
    d = n - 1
    s = 0
    while d % 2 == 0:
        s += 1
        d //= 2

    for _ in range(rounds):
        a = secrets.randbelow(n - 3) + 2  # 随机底数 a ∈ [2, n-2]
        x = qpow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(s - 1):
            x = qpow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True

# 生成素数
def generate_prime(bits: int) -> int:
    if bits < 8:
        raise ValueError("prime size must be at least 8 bits")

    while True:
        candidate = secrets.randbits(bits)
        candidate |= 1 << (bits - 1)
        candidate |= 1
        if is_prime(candidate):
            return candidate

# 生成 RSA 密钥对
def generate_keypair(modulus_bits: int = 1024) -> RSAKeyPair:
    if modulus_bits < 512:
        raise ValueError("RSA modulus must be at least 512 bits")

    half_bits = modulus_bits // 2
    while True:
        p = generate_prime(half_bits)
        q = generate_prime(modulus_bits - half_bits)
        if p == q:
            continue

        n = p * q
        if n.bit_length() != modulus_bits:
            continue

        phi = (p - 1) * (q - 1)
        e = DEFAULT_PUBLIC_EXPONENT
        if math.gcd(e, phi) != 1:
            continue

        d = mod_inverse(e, phi)
        return RSAKeyPair(
            public_key=PublicKey(n=n, e=e),
            private_key=PrivateKey(n=n, d=d, p=p, q=q, phi=phi),
        )


def serialize_public_key(public_key: PublicKey) -> bytes:
    return _json_dumps_bytes(
        {
            "type": "RSA_PUBLIC_KEY",
            "version": 1,
            "n": str(public_key.n),
            "e": str(public_key.e),
        }
    )


def serialize_private_key(private_key: PrivateKey) -> bytes:
    return _json_dumps_bytes(
        {
            "type": "RSA_PRIVATE_KEY",
            "version": 1,
            "n": str(private_key.n),
            "d": str(private_key.d),
            "p": str(private_key.p),
            "q": str(private_key.q),
            "phi": str(private_key.phi),
        }
    )


def deserialize_public_key(raw: bytes | str) -> PublicKey:
    data = _json_loads(raw)
    if data.get("type") != "RSA_PUBLIC_KEY":
        raise ValueError("invalid RSA public key")
    return PublicKey(n=_positive_int(data, "n"), e=_positive_int(data, "e"))


def deserialize_private_key(raw: bytes | str) -> PrivateKey:
    data = _json_loads(raw)
    if data.get("type") != "RSA_PRIVATE_KEY":
        raise ValueError("invalid RSA private key")

    key = PrivateKey(
        n=_positive_int(data, "n"),
        d=_positive_int(data, "d"),
        p=_positive_int(data, "p"),
        q=_positive_int(data, "q"),
        phi=_positive_int(data, "phi"),
    )
    if key.p * key.q != key.n:
        raise ValueError("invalid RSA private key factors")
    if (key.p - 1) * (key.q - 1) != key.phi:
        raise ValueError("invalid RSA private key phi")
    return key

# 求 RSA 模数 n 的最大明文块大小
def max_plain_block_bytes(n: int) -> int:
    block_size = (n.bit_length() - 1) // 8
    if block_size <= 0:
        raise ValueError("invalid RSA modulus")
    return block_size

# 求 RSA 密文块大小
def cipher_block_bytes(n: int) -> int:
    return (n.bit_length() + 7) // 8

# 加密整数
def encrypt_int(message: int, public_key: PublicKey) -> int:
    if not 0 <= message < public_key.n:
        raise ValueError("RSA message integer out of range")
    return qpow(message, public_key.e, public_key.n)

# 解密整数
def decrypt_int(ciphertext: int, private_key: PrivateKey) -> int:
    if not 0 <= ciphertext < private_key.n:
        raise ValueError("RSA ciphertext integer out of range")
    return qpow(ciphertext, private_key.d, private_key.n)

# 加密字节数据
def encrypt_bytes(plaintext: bytes, public_key: PublicKey) -> dict[str, Any]:
    plain_block_size = max_plain_block_bytes(public_key.n)
    cipher_size = cipher_block_bytes(public_key.n)
    blocks: list[str] = []
    lengths: list[int] = []

    for offset in range(0, len(plaintext), plain_block_size):
        block = plaintext[offset : offset + plain_block_size]
        block_int = int.from_bytes(block, "big")
        cipher_int = encrypt_int(block_int, public_key)
        blocks.append(cipher_int.to_bytes(cipher_size, "big").hex())
        lengths.append(len(block))

    if not plaintext:
        cipher_int = encrypt_int(0, public_key)
        blocks.append(cipher_int.to_bytes(cipher_size, "big").hex())
        lengths.append(0)

    return {
        "type": "RSA_RAW_BLOCKS",
        "version": 1,
        "block_size": plain_block_size,
        "cipher_block_size": cipher_size,
        "lengths": lengths,
        "blocks": blocks,
    }

# 解密字节数据
def decrypt_bytes(envelope: dict[str, Any], private_key: PrivateKey) -> bytes:
    if envelope.get("type") != "RSA_RAW_BLOCKS":
        raise ValueError("invalid RSA ciphertext envelope")

    blocks = envelope.get("blocks")
    lengths = envelope.get("lengths")
    if not isinstance(blocks, list) or not isinstance(lengths, list):
        raise ValueError("invalid RSA ciphertext envelope")
    if len(blocks) != len(lengths):
        raise ValueError("RSA ciphertext block count mismatch")

    recovered = bytearray()
    for block_hex, length in zip(blocks, lengths):
        if not isinstance(block_hex, str) or type(length) is not int:
            raise ValueError("invalid RSA ciphertext block")
        if length < 0 or length > max_plain_block_bytes(private_key.n):
            raise ValueError("invalid RSA plaintext block length")

        cipher_int = int.from_bytes(bytes.fromhex(block_hex), "big")
        plain_int = decrypt_int(cipher_int, private_key)
        if length == 0:
            block = b""
        else:
            block = plain_int.to_bytes(length, "big")
        recovered.extend(block)

    return bytes(recovered)


def envelope_to_bytes(envelope: dict[str, Any]) -> bytes:
    return _json_dumps_bytes(envelope)


def envelope_from_bytes(raw: bytes | str) -> dict[str, Any]:
    data = _json_loads(raw)
    if data.get("type") != "RSA_RAW_BLOCKS":
        raise ValueError("invalid RSA ciphertext envelope")
    return data


def _json_dumps_bytes(obj: dict[str, Any]) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _json_loads(raw: bytes | str) -> dict[str, Any]:
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("expected JSON object")
    return data

# 从 JSON 对象中提取正整数字段
def _positive_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)
    if isinstance(value, str):
        parsed = int(value)
    elif type(value) is int:
        parsed = value
    else:
        raise ValueError(f"invalid integer field: {key}")
    if parsed <= 0:
        raise ValueError(f"{key} must be positive")
    return parsed