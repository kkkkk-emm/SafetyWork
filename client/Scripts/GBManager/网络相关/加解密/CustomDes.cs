using System;

public static class CustomDes
{
    public const int BlockBytes = 8;
    public const int KeyBytes = 8;

    private static readonly int[] IP =
    {
        58,50,42,34,26,18,10,2,
        60,52,44,36,28,20,12,4,
        62,54,46,38,30,22,14,6,
        64,56,48,40,32,24,16,8,
        57,49,41,33,25,17,9,1,
        59,51,43,35,27,19,11,3,
        61,53,45,37,29,21,13,5,
        63,55,47,39,31,23,15,7
    };

    private static readonly int[] FP =
    {
        40,8,48,16,56,24,64,32,
        39,7,47,15,55,23,63,31,
        38,6,46,14,54,22,62,30,
        37,5,45,13,53,21,61,29,
        36,4,44,12,52,20,60,28,
        35,3,43,11,51,19,59,27,
        34,2,42,10,50,18,58,26,
        33,1,41,9,49,17,57,25
    };

    private static readonly int[] E =
    {
        32,1,2,3,4,5,
        4,5,6,7,8,9,
        8,9,10,11,12,13,
        12,13,14,15,16,17,
        16,17,18,19,20,21,
        20,21,22,23,24,25,
        24,25,26,27,28,29,
        28,29,30,31,32,1
    };

    private static readonly int[] P =
    {
        16,7,20,21,
        29,12,28,17,
        1,15,23,26,
        5,18,31,10,
        2,8,24,14,
        32,27,3,9,
        19,13,30,6,
        22,11,4,25
    };

    private static readonly int[] PC1 =
    {
        57,49,41,33,25,17,9,
        1,58,50,42,34,26,18,
        10,2,59,51,43,35,27,
        19,11,3,60,52,44,36,
        63,55,47,39,31,23,15,
        7,62,54,46,38,30,22,
        14,6,61,53,45,37,29,
        21,13,5,28,20,12,4
    };

    private static readonly int[] PC2 =
    {
        14,17,11,24,1,5,
        3,28,15,6,21,10,
        23,19,12,4,26,8,
        16,7,27,20,13,2,
        41,52,31,37,47,55,
        30,40,51,45,33,48,
        44,49,39,56,34,53,
        46,42,50,36,29,32
    };

    private static readonly int[] SHIFTS =
    {
        1,1,2,2,2,2,2,2,
        1,2,2,2,2,2,2,1
    };

    private static readonly int[,,] SBOX =
    {
        {
            {14,4,13,1,2,15,11,8,3,10,6,12,5,9,0,7},
            {0,15,7,4,14,2,13,1,10,6,12,11,9,5,3,8},
            {4,1,14,8,13,6,2,11,15,12,9,7,3,10,5,0},
            {15,12,8,2,4,9,1,7,5,11,3,14,10,0,6,13}
        },
        {
            {15,1,8,14,6,11,3,4,9,7,2,13,12,0,5,10},
            {3,13,4,7,15,2,8,14,12,0,1,10,6,9,11,5},
            {0,14,7,11,10,4,13,1,5,8,12,6,9,3,2,15},
            {13,8,10,1,3,15,4,2,11,6,7,12,0,5,14,9}
        },
        {
            {10,0,9,14,6,3,15,5,1,13,12,7,11,4,2,8},
            {13,7,0,9,3,4,6,10,2,8,5,14,12,11,15,1},
            {13,6,4,9,8,15,3,0,11,1,2,12,5,10,14,7},
            {1,10,13,0,6,9,8,7,4,15,14,3,11,5,2,12}
        },
        {
            {7,13,14,3,0,6,9,10,1,2,8,5,11,12,4,15},
            {13,8,11,5,6,15,0,3,4,7,2,12,1,10,14,9},
            {10,6,9,0,12,11,7,13,15,1,3,14,5,2,8,4},
            {3,15,0,6,10,1,13,8,9,4,5,11,12,7,2,14}
        },
        {
            {2,12,4,1,7,10,11,6,8,5,3,15,13,0,14,9},
            {14,11,2,12,4,7,13,1,5,0,15,10,3,9,8,6},
            {4,2,1,11,10,13,7,8,15,9,12,5,6,3,0,14},
            {11,8,12,7,1,14,2,13,6,15,0,9,10,4,5,3}
        },
        {
            {12,1,10,15,9,2,6,8,0,13,3,4,14,7,5,11},
            {10,15,4,2,7,12,9,5,6,1,13,14,0,11,3,8},
            {9,14,15,5,2,8,12,3,7,0,4,10,1,13,11,6},
            {4,3,2,12,9,5,15,10,11,14,1,7,6,0,8,13}
        },
        {
            {4,11,2,14,15,0,8,13,3,12,9,7,5,10,6,1},
            {13,0,11,7,4,9,1,10,14,3,5,12,2,15,8,6},
            {1,4,11,13,12,3,7,14,10,15,6,8,0,5,9,2},
            {6,11,13,8,1,4,10,7,9,5,0,15,14,2,3,12}
        },
        {
            {13,2,8,4,6,15,11,1,10,9,3,14,5,0,12,7},
            {1,15,13,8,10,3,7,4,12,5,6,11,0,14,9,2},
            {7,11,4,1,9,12,14,2,0,6,10,13,15,3,5,8},
            {2,1,14,7,4,10,8,13,15,12,9,0,3,5,6,11}
        }
    };

    public static byte[] EncryptCbcPkcs7(byte[] key, byte[] iv, byte[] plaintext)
    {
        ValidateKeyAndIv(key, iv);

        if (plaintext == null)
            plaintext = Array.Empty<byte>();

        byte[] padded = AddPkcs7Padding(plaintext, BlockBytes);
        byte[] output = new byte[padded.Length];

        byte[] previous = new byte[BlockBytes];
        Buffer.BlockCopy(iv, 0, previous, 0, BlockBytes);

        for (int offset = 0; offset < padded.Length; offset += BlockBytes)
        {
            byte[] block = new byte[BlockBytes];

            for (int i = 0; i < BlockBytes; i++)
                block[i] = (byte)(padded[offset + i] ^ previous[i]);

            byte[] encrypted = EncryptBlock(key, block);

            Buffer.BlockCopy(encrypted, 0, output, offset, BlockBytes);
            Buffer.BlockCopy(encrypted, 0, previous, 0, BlockBytes);
        }

        return output;
    }

    public static byte[] DecryptCbcPkcs7(byte[] key, byte[] iv, byte[] ciphertext)
    {
        ValidateKeyAndIv(key, iv);

        if (ciphertext == null || ciphertext.Length == 0 || ciphertext.Length % BlockBytes != 0)
            throw new ArgumentException("DES-CBC ciphertext length must be a positive multiple of 8.");

        byte[] output = new byte[ciphertext.Length];

        byte[] previous = new byte[BlockBytes];
        Buffer.BlockCopy(iv, 0, previous, 0, BlockBytes);

        for (int offset = 0; offset < ciphertext.Length; offset += BlockBytes)
        {
            byte[] cipherBlock = new byte[BlockBytes];
            Buffer.BlockCopy(ciphertext, offset, cipherBlock, 0, BlockBytes);

            byte[] decrypted = DecryptBlock(key, cipherBlock);

            for (int i = 0; i < BlockBytes; i++)
                output[offset + i] = (byte)(decrypted[i] ^ previous[i]);

            Buffer.BlockCopy(cipherBlock, 0, previous, 0, BlockBytes);
        }

        return RemovePkcs7Padding(output, BlockBytes);
    }

    public static byte[] EncryptBlock(byte[] key, byte[] block)
    {
        if (key == null || key.Length != KeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (block == null || block.Length != BlockBytes)
            throw new ArgumentException("DES block must be exactly 8 bytes.");

        ulong[] subKeys = GenerateSubKeys(key);
        return ProcessBlock(block, subKeys, decrypt: false);
    }

    public static byte[] DecryptBlock(byte[] key, byte[] block)
    {
        if (key == null || key.Length != KeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (block == null || block.Length != BlockBytes)
            throw new ArgumentException("DES block must be exactly 8 bytes.");

        ulong[] subKeys = GenerateSubKeys(key);
        return ProcessBlock(block, subKeys, decrypt: true);
    }

    private static byte[] ProcessBlock(byte[] block, ulong[] subKeys, bool decrypt)
    {
        ulong input = BytesToUInt64BigEndian(block);
        ulong permuted = Permute(input, 64, IP);

        uint left = (uint)(permuted >> 32);
        uint right = (uint)(permuted & 0xFFFFFFFFUL);

        for (int round = 0; round < 16; round++)
        {
            int keyIndex = decrypt ? 15 - round : round;

            uint oldLeft = left;
            left = right;
            right = oldLeft ^ Feistel(right, subKeys[keyIndex]);
        }

        ulong preOutput = ((ulong)right << 32) | left;
        ulong finalBlock = Permute(preOutput, 64, FP);

        return UInt64ToBytesBigEndian(finalBlock);
    }

    private static uint Feistel(uint halfBlock, ulong subKey)
    {
        ulong expanded = Permute(halfBlock, 32, E);
        ulong mixed = expanded ^ subKey;

        uint sboxOutput = 0;

        for (int box = 0; box < 8; box++)
        {
            int shift = 42 - box * 6;
            int sixBits = (int)((mixed >> shift) & 0x3F);

            int row = ((sixBits & 0x20) >> 4) | (sixBits & 0x01);
            int col = (sixBits >> 1) & 0x0F;

            int value = SBOX[box, row, col];
            sboxOutput = (sboxOutput << 4) | (uint)value;
        }

        return (uint)Permute(sboxOutput, 32, P);
    }

    private static ulong[] GenerateSubKeys(byte[] key)
    {
        ulong key64 = BytesToUInt64BigEndian(key);
        ulong key56 = Permute(key64, 64, PC1);

        uint c = (uint)((key56 >> 28) & 0x0FFFFFFF);
        uint d = (uint)(key56 & 0x0FFFFFFF);

        ulong[] subKeys = new ulong[16];

        for (int round = 0; round < 16; round++)
        {
            c = RotateLeft28(c, SHIFTS[round]);
            d = RotateLeft28(d, SHIFTS[round]);

            ulong cd = ((ulong)c << 28) | d;
            subKeys[round] = Permute(cd, 56, PC2);
        }

        return subKeys;
    }

    private static ulong Permute(ulong input, int inputBits, int[] table)
    {
        ulong output = 0;

        for (int i = 0; i < table.Length; i++)
        {
            int sourcePosition = table[i];
            int shift = inputBits - sourcePosition;
            ulong bit = (input >> shift) & 1UL;

            output = (output << 1) | bit;
        }

        return output;
    }

    private static uint RotateLeft28(uint value, int count)
    {
        value &= 0x0FFFFFFF;
        return (uint)(((value << count) | (value >> (28 - count))) & 0x0FFFFFFF);
    }

    private static ulong BytesToUInt64BigEndian(byte[] bytes)
    {
        ulong value = 0;

        for (int i = 0; i < 8; i++)
        {
            value = (value << 8) | bytes[i];
        }

        return value;
    }

    private static byte[] UInt64ToBytesBigEndian(ulong value)
    {
        byte[] bytes = new byte[8];

        for (int i = 7; i >= 0; i--)
        {
            bytes[i] = (byte)(value & 0xFF);
            value >>= 8;
        }

        return bytes;
    }

    private static byte[] AddPkcs7Padding(byte[] input, int blockSize)
    {
        int padding = blockSize - (input.Length % blockSize);
        if (padding == 0)
            padding = blockSize;

        byte[] output = new byte[input.Length + padding];
        Buffer.BlockCopy(input, 0, output, 0, input.Length);

        for (int i = input.Length; i < output.Length; i++)
            output[i] = (byte)padding;

        return output;
    }

    private static byte[] RemovePkcs7Padding(byte[] input, int blockSize)
    {
        if (input == null || input.Length == 0 || input.Length % blockSize != 0)
            throw new ArgumentException("Invalid PKCS7 padded data length.");

        int padding = input[input.Length - 1];

        if (padding <= 0 || padding > blockSize)
            throw new ArgumentException("Invalid PKCS7 padding.");

        for (int i = input.Length - padding; i < input.Length; i++)
        {
            if (input[i] != padding)
                throw new ArgumentException("Invalid PKCS7 padding bytes.");
        }

        byte[] output = new byte[input.Length - padding];
        Buffer.BlockCopy(input, 0, output, 0, output.Length);
        return output;
    }

    private static void ValidateKeyAndIv(byte[] key, byte[] iv)
    {
        if (key == null || key.Length != KeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (iv == null || iv.Length != BlockBytes)
            throw new ArgumentException("DES IV must be exactly 8 bytes.");
    }
}