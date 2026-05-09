using System;
using System.Numerics;
using System.Security.Cryptography;

public static class CustomRsa
{
    private const int Sha256Bytes = 32;

    public static byte[] EncryptOaepSha256(
        byte[] modulusBigEndian,
        byte[] exponentBigEndian,
        byte[] message
    )
    {
        if (modulusBigEndian == null || modulusBigEndian.Length == 0)
            throw new ArgumentException("RSA modulus is empty.");

        if (exponentBigEndian == null || exponentBigEndian.Length == 0)
            throw new ArgumentException("RSA exponent is empty.");

        if (message == null)
            message = Array.Empty<byte>();

        int k = modulusBigEndian.Length;

        if (message.Length > k - 2 * Sha256Bytes - 2)
        {
            throw new ArgumentException(
                $"Message too long for RSA-OAEP-SHA256. message={message.Length}, max={k - 2 * Sha256Bytes - 2}"
            );
        }

        byte[] encodedMessage = OaepEncodeSha256(message, k);

        BigInteger n = BigEndianUnsignedToBigInteger(modulusBigEndian);
        BigInteger e = BigEndianUnsignedToBigInteger(exponentBigEndian);
        BigInteger m = BigEndianUnsignedToBigInteger(encodedMessage);

        if (m >= n)
            throw new ArgumentException("OAEP encoded message representative is too large.");

        BigInteger c = BigInteger.ModPow(m, e, n);

        return BigIntegerToBigEndianUnsigned(c, k);
    }

    private static byte[] OaepEncodeSha256(byte[] message, int encodedLength)
    {
        int hLen = Sha256Bytes;
        int mLen = message.Length;

        byte[] lHash;

        using (SHA256 sha = SHA256.Create())
        {
            lHash = sha.ComputeHash(Array.Empty<byte>());
        }

        int psLen = encodedLength - mLen - 2 * hLen - 2;

        if (psLen < 0)
            throw new ArgumentException("Message too long for OAEP.");

        // DB = lHash || PS || 0x01 || M
        byte[] db = new byte[encodedLength - hLen - 1];

        Buffer.BlockCopy(lHash, 0, db, 0, hLen);

        int separatorIndex = hLen + psLen;
        db[separatorIndex] = 0x01;

        Buffer.BlockCopy(message, 0, db, separatorIndex + 1, message.Length);

        byte[] seed = new byte[hLen];

        using (RandomNumberGenerator rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(seed);
        }

        byte[] dbMask = Mgf1Sha256(seed, db.Length);
        byte[] maskedDb = Xor(db, dbMask);

        byte[] seedMask = Mgf1Sha256(maskedDb, hLen);
        byte[] maskedSeed = Xor(seed, seedMask);

        // EM = 0x00 || maskedSeed || maskedDB
        byte[] em = new byte[encodedLength];

        em[0] = 0x00;
        Buffer.BlockCopy(maskedSeed, 0, em, 1, hLen);
        Buffer.BlockCopy(maskedDb, 0, em, 1 + hLen, maskedDb.Length);

        return em;
    }

    private static byte[] Mgf1Sha256(byte[] seed, int maskLength)
    {
        if (maskLength < 0)
            throw new ArgumentException("maskLength must be non-negative.");

        byte[] mask = new byte[maskLength];
        int offset = 0;
        uint counter = 0;

        using (SHA256 sha = SHA256.Create())
        {
            while (offset < maskLength)
            {
                byte[] counterBytes = I2osp4(counter);

                byte[] input = new byte[seed.Length + 4];
                Buffer.BlockCopy(seed, 0, input, 0, seed.Length);
                Buffer.BlockCopy(counterBytes, 0, input, seed.Length, 4);

                byte[] digest = sha.ComputeHash(input);

                int copy = Math.Min(digest.Length, maskLength - offset);
                Buffer.BlockCopy(digest, 0, mask, offset, copy);

                offset += copy;
                counter++;
            }
        }

        return mask;
    }

    private static byte[] I2osp4(uint value)
    {
        return new[]
        {
            (byte)(value >> 24),
            (byte)(value >> 16),
            (byte)(value >> 8),
            (byte)value
        };
    }

    private static byte[] Xor(byte[] a, byte[] b)
    {
        if (a.Length != b.Length)
            throw new ArgumentException("XOR input lengths differ.");

        byte[] output = new byte[a.Length];

        for (int i = 0; i < a.Length; i++)
            output[i] = (byte)(a[i] ^ b[i]);

        return output;
    }

    private static BigInteger BigEndianUnsignedToBigInteger(byte[] bigEndian)
    {
        if (bigEndian == null || bigEndian.Length == 0)
            return BigInteger.Zero;

        byte[] littleEndian = new byte[bigEndian.Length + 1];

        for (int i = 0; i < bigEndian.Length; i++)
        {
            littleEndian[i] = bigEndian[bigEndian.Length - 1 - i];
        }

        // 最后额外补一个 0，确保 BigInteger 按正数处理。
        littleEndian[littleEndian.Length - 1] = 0x00;

        return new BigInteger(littleEndian);
    }

    private static byte[] BigIntegerToBigEndianUnsigned(BigInteger value, int outputLength)
    {
        if (value < 0)
            throw new ArgumentException("BigInteger must be non-negative.");

        byte[] littleEndian = value.ToByteArray();

        int actualLength = littleEndian.Length;

        // 去掉 BigInteger 为了表示正数可能额外加的 0x00。
        while (actualLength > 1 && littleEndian[actualLength - 1] == 0x00)
            actualLength--;

        if (actualLength > outputLength)
            throw new ArgumentException("Integer too large for requested output length.");

        byte[] output = new byte[outputLength];

        for (int i = 0; i < actualLength; i++)
        {
            output[outputLength - 1 - i] = littleEndian[i];
        }

        return output;
    }
}