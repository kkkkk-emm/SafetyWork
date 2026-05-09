from __future__ import annotations

from collections.abc import Iterable


DES_KEY_BYTES = 8
DES_BLOCK_BYTES = 8
MASK_28 = (1 << 28) - 1
MASK_32 = (1 << 32) - 1
MASK_64 = (1 << 64) - 1

IP_TABLE = (
    58, 50, 42, 34, 26, 18, 10, 2,
    60, 52, 44, 36, 28, 20, 12, 4,
    62, 54, 46, 38, 30, 22, 14, 6,
    64, 56, 48, 40, 32, 24, 16, 8,
    57, 49, 41, 33, 25, 17, 9, 1,
    59, 51, 43, 35, 27, 19, 11, 3,
    61, 53, 45, 37, 29, 21, 13, 5,
    63, 55, 47, 39, 31, 23, 15, 7,
)

FP_TABLE = (
    40, 8, 48, 16, 56, 24, 64, 32,
    39, 7, 47, 15, 55, 23, 63, 31,
    38, 6, 46, 14, 54, 22, 62, 30,
    37, 5, 45, 13, 53, 21, 61, 29,
    36, 4, 44, 12, 52, 20, 60, 28,
    35, 3, 43, 11, 51, 19, 59, 27,
    34, 2, 42, 10, 50, 18, 58, 26,
    33, 1, 41, 9, 49, 17, 57, 25,
)

E_TABLE = (
    32, 1, 2, 3, 4, 5,
    4, 5, 6, 7, 8, 9,
    8, 9, 10, 11, 12, 13,
    12, 13, 14, 15, 16, 17,
    16, 17, 18, 19, 20, 21,
    20, 21, 22, 23, 24, 25,
    24, 25, 26, 27, 28, 29,
    28, 29, 30, 31, 32, 1,
)

P_TABLE = (
    16, 7, 20, 21,
    29, 12, 28, 17,
    1, 15, 23, 26,
    5, 18, 31, 10,
    2, 8, 24, 14,
    32, 27, 3, 9,
    19, 13, 30, 6,
    22, 11, 4, 25,
)

PC1_TABLE = (
    57, 49, 41, 33, 25, 17, 9,
    1, 58, 50, 42, 34, 26, 18,
    10, 2, 59, 51, 43, 35, 27,
    19, 11, 3, 60, 52, 44, 36,
    63, 55, 47, 39, 31, 23, 15,
    7, 62, 54, 46, 38, 30, 22,
    14, 6, 61, 53, 45, 37, 29,
    21, 13, 5, 28, 20, 12, 4,
)

LEFT_SHIFTS = (1, 1, 2, 2, 2, 2, 2, 2, 1, 2, 2, 2, 2, 2, 2, 1)

PC2_TABLE = (
    14, 17, 11, 24, 1, 5,
    3, 28, 15, 6, 21, 10,
    23, 19, 12, 4, 26, 8,
    16, 7, 27, 20, 13, 2,
    41, 52, 31, 37, 47, 55,
    30, 40, 51, 45, 33, 48,
    44, 49, 39, 56, 34, 53,
    46, 42, 50, 36, 29, 32,
)

S_BOXES = (
    (
        (14, 4, 13, 1, 2, 15, 11, 8, 3, 10, 6, 12, 5, 9, 0, 7),
        (0, 15, 7, 4, 14, 2, 13, 1, 10, 6, 12, 11, 9, 5, 3, 8),
        (4, 1, 14, 8, 13, 6, 2, 11, 15, 12, 9, 7, 3, 10, 5, 0),
        (15, 12, 8, 2, 4, 9, 1, 7, 5, 11, 3, 14, 10, 0, 6, 13),
    ),
    (
        (15, 1, 8, 14, 6, 11, 3, 4, 9, 7, 2, 13, 12, 0, 5, 10),
        (3, 13, 4, 7, 15, 2, 8, 14, 12, 0, 1, 10, 6, 9, 11, 5),
        (0, 14, 7, 11, 10, 4, 13, 1, 5, 8, 12, 6, 9, 3, 2, 15),
        (13, 8, 10, 1, 3, 15, 4, 2, 11, 6, 7, 12, 0, 5, 14, 9),
    ),
    (
        (10, 0, 9, 14, 6, 3, 15, 5, 1, 13, 12, 7, 11, 4, 2, 8),
        (13, 7, 0, 9, 3, 4, 6, 10, 2, 8, 5, 14, 12, 11, 15, 1),
        (13, 6, 4, 9, 8, 15, 3, 0, 11, 1, 2, 12, 5, 10, 14, 7),
        (1, 10, 13, 0, 6, 9, 8, 7, 4, 15, 14, 3, 11, 5, 2, 12),
    ),
    (
        (7, 13, 14, 3, 0, 6, 9, 10, 1, 2, 8, 5, 11, 12, 4, 15),
        (13, 8, 11, 5, 6, 15, 0, 3, 4, 7, 2, 12, 1, 10, 14, 9),
        (10, 6, 9, 0, 12, 11, 7, 13, 15, 1, 3, 14, 5, 2, 8, 4),
        (3, 15, 0, 6, 10, 1, 13, 8, 9, 4, 5, 11, 12, 7, 2, 14),
    ),
    (
        (2, 12, 4, 1, 7, 10, 11, 6, 8, 5, 3, 15, 13, 0, 14, 9),
        (14, 11, 2, 12, 4, 7, 13, 1, 5, 0, 15, 10, 3, 9, 8, 6),
        (4, 2, 1, 11, 10, 13, 7, 8, 15, 9, 12, 5, 6, 3, 0, 14),
        (11, 8, 12, 7, 1, 14, 2, 13, 6, 15, 0, 9, 10, 4, 5, 3),
    ),
    (
        (12, 1, 10, 15, 9, 2, 6, 8, 0, 13, 3, 4, 14, 7, 5, 11),
        (10, 15, 4, 2, 7, 12, 9, 5, 6, 1, 13, 14, 0, 11, 3, 8),
        (9, 14, 15, 5, 2, 8, 12, 3, 7, 0, 4, 10, 1, 13, 11, 6),
        (4, 3, 2, 12, 9, 5, 15, 10, 11, 14, 1, 7, 6, 0, 8, 13),
    ),
    (
        (4, 11, 2, 14, 15, 0, 8, 13, 3, 12, 9, 7, 5, 10, 6, 1),
        (13, 0, 11, 7, 4, 9, 1, 10, 14, 3, 5, 12, 2, 15, 8, 6),
        (1, 4, 11, 13, 12, 3, 7, 14, 10, 15, 6, 8, 0, 5, 9, 2),
        (6, 11, 13, 8, 1, 4, 10, 7, 9, 5, 0, 15, 14, 2, 3, 12),
    ),
    (
        (13, 2, 8, 4, 6, 15, 11, 1, 10, 9, 3, 14, 5, 0, 12, 7),
        (1, 15, 13, 8, 10, 3, 7, 4, 12, 5, 6, 11, 0, 14, 9, 2),
        (7, 11, 4, 1, 9, 12, 14, 2, 0, 6, 10, 13, 15, 3, 5, 8),
        (2, 1, 14, 7, 4, 10, 8, 13, 15, 12, 9, 0, 3, 5, 6, 11),
    ),
)


def encrypt_block(block: int, key: int) -> int:
    _validate_u64_int("block", block)
    _validate_u64_int("key", key)
    return _des_core(block, _generate_subkeys(key))


def decrypt_block(block: int, key: int) -> int:
    _validate_u64_int("block", block)
    _validate_u64_int("key", key)
    return _des_core(block, tuple(reversed(_generate_subkeys(key))))


def pkcs7_pad(data: bytes, block_size: int = DES_BLOCK_BYTES) -> bytes:
    if not 1 <= block_size <= 255:
        raise ValueError("block_size must be in range [1, 255]")
    pad_len = block_size - (len(data) % block_size)
    if pad_len == 0:
        pad_len = block_size
    return data + bytes([pad_len]) * pad_len


def pkcs7_unpad(data: bytes, block_size: int = DES_BLOCK_BYTES) -> bytes:
    if not data or len(data) % block_size != 0:
        raise ValueError("invalid PKCS7 padded data length")
    pad_len = data[-1]
    if pad_len < 1 or pad_len > block_size:
        raise ValueError("invalid PKCS7 padding")
    if data[-pad_len:] != bytes([pad_len]) * pad_len:
        raise ValueError("invalid PKCS7 padding")
    return data[:-pad_len]


def cbc_encrypt(key: bytes, iv: bytes, plaintext: bytes) -> bytes:
    _validate_key_iv(key, iv)
    key_int = int.from_bytes(key, "big")
    previous = int.from_bytes(iv, "big")
    output = bytearray()

    for block in _iter_blocks(pkcs7_pad(plaintext, DES_BLOCK_BYTES)):
        block_int = int.from_bytes(block, "big") ^ previous
        encrypted = encrypt_block(block_int, key_int)
        output.extend(encrypted.to_bytes(DES_BLOCK_BYTES, "big"))
        previous = encrypted

    return bytes(output)


def cbc_decrypt(key: bytes, iv: bytes, ciphertext: bytes) -> bytes:
    _validate_key_iv(key, iv)
    if len(ciphertext) == 0 or len(ciphertext) % DES_BLOCK_BYTES != 0:
        raise ValueError("ciphertext length must be a positive multiple of 8")

    key_int = int.from_bytes(key, "big")
    previous = int.from_bytes(iv, "big")
    output = bytearray()

    for block in _iter_blocks(ciphertext):
        block_int = int.from_bytes(block, "big")
        decrypted = decrypt_block(block_int, key_int) ^ previous
        output.extend(decrypted.to_bytes(DES_BLOCK_BYTES, "big"))
        previous = block_int

    return pkcs7_unpad(bytes(output), DES_BLOCK_BYTES)


def _validate_key_iv(key: bytes, iv: bytes) -> None:
    if len(key) != DES_KEY_BYTES:
        raise ValueError("DES key must be exactly 8 bytes")
    if len(iv) != DES_BLOCK_BYTES:
        raise ValueError("DES IV must be exactly 8 bytes")


def _iter_blocks(data: bytes) -> Iterable[bytes]:
    for offset in range(0, len(data), DES_BLOCK_BYTES):
        yield data[offset : offset + DES_BLOCK_BYTES]


def _validate_u64_int(name: str, value: int) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} must be an int")
    if not 0 <= value <= MASK_64:
        raise ValueError(f"{name} must be in range [0, 2^64)")


def _permute(block: int, table: Iterable[int], input_bits: int) -> int:
    result = 0
    for bit_pos in table:
        bit = (block >> (input_bits - bit_pos)) & 0x1
        result = (result << 1) | bit
    return result


def _left_rotate_28(value: int, shifts: int) -> int:
    value &= MASK_28
    return ((value << shifts) & MASK_28) | (value >> (28 - shifts))


def _generate_subkeys(key64: int) -> tuple[int, ...]:
    key56 = _permute(key64, PC1_TABLE, 64)
    c = (key56 >> 28) & MASK_28
    d = key56 & MASK_28
    subkeys: list[int] = []

    for shifts in LEFT_SHIFTS:
        c = _left_rotate_28(c, shifts)
        d = _left_rotate_28(d, shifts)
        cd = (c << 28) | d
        subkeys.append(_permute(cd, PC2_TABLE, 56))

    return tuple(subkeys)


def _sbox_lookup(sbox: tuple[tuple[int, ...], ...], six_bits: int) -> int:
    row = ((six_bits & 0b100000) >> 4) | (six_bits & 0b000001)
    col = (six_bits >> 1) & 0b1111
    return sbox[row][col]


def _apply_sboxes(value48: int) -> int:
    output32 = 0
    for index, sbox in enumerate(S_BOXES):
        six_bits = (value48 >> (42 - 6 * index)) & 0x3F
        output32 = (output32 << 4) | _sbox_lookup(sbox, six_bits)
    return output32


def _round_function(r32: int, subkey48: int) -> int:
    expanded_r = _permute(r32, E_TABLE, 32)
    s_out = _apply_sboxes(expanded_r ^ subkey48)
    return _permute(s_out, P_TABLE, 32)


def _des_core(block64: int, subkeys: tuple[int, ...]) -> int:
    if len(subkeys) != 16:
        raise ValueError("DES requires exactly 16 subkeys")

    permuted = _permute(block64, IP_TABLE, 64)
    left = (permuted >> 32) & MASK_32
    right = permuted & MASK_32

    for subkey in subkeys:
        left, right = right, left ^ _round_function(right, subkey)

    pre_output = (right << 32) | left
    return _permute(pre_output, FP_TABLE, 64)
