using System;
using System.Collections.Generic;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

public sealed class RsaRawPublicKey
{
    public BigInteger N { get; private set; }
    public BigInteger E { get; private set; }

    public RsaRawPublicKey(BigInteger n, BigInteger e)
    {
        if (n <= 0) throw new ArgumentException("RSA modulus n must be positive.");
        if (e <= 0) throw new ArgumentException("RSA exponent e must be positive.");

        N = n;
        E = e;
    }
}

public static class RsaRawBlocksJson
{
    public static RsaRawPublicKey ParsePublicKeyJson(string publicKeyJson)
    {
        if (string.IsNullOrWhiteSpace(publicKeyJson))
            throw new ArgumentException("RSA public key JSON is empty.");

        string type = MatchString(publicKeyJson, "type", required: false);
        if (!string.IsNullOrEmpty(type) && type != "RSA_PUBLIC_KEY")
            throw new ArgumentException("Invalid RSA public key type: " + type);

        string nText = MatchNumberOrString(publicKeyJson, "n");
        string eText = MatchNumberOrString(publicKeyJson, "e");

        BigInteger n = BigInteger.Parse(nText);
        BigInteger e = BigInteger.Parse(eText);

        return new RsaRawPublicKey(n, e);
    }

    public static string EncryptJsonToBase64Envelope(string publicKeyJson, string json)
    {
        if (json == null)
            json = "{}";

        RsaRawPublicKey publicKey = ParsePublicKeyJson(publicKeyJson);
        byte[] plainBytes = Encoding.UTF8.GetBytes(json);

        byte[] envelopeBytes = EncryptBytesToEnvelopeBytes(plainBytes, publicKey);
        return Convert.ToBase64String(envelopeBytes);
    }

    public static byte[] EncryptBytesToEnvelopeBytes(byte[] plaintext, RsaRawPublicKey publicKey)
    {
        if (plaintext == null)
            plaintext = Array.Empty<byte>();

        int plainBlockSize = MaxPlainBlockBytes(publicKey.N);
        int cipherBlockSize = CipherBlockBytes(publicKey.N);

        List<int> lengths = new List<int>();
        List<string> blocks = new List<string>();

        if (plaintext.Length == 0)
        {
            BigInteger cipherInt = ModPow(BigInteger.Zero, publicKey.E, publicKey.N);
            blocks.Add(ToFixedBigEndianHex(cipherInt, cipherBlockSize));
            lengths.Add(0);
        }
        else
        {
            for (int offset = 0; offset < plaintext.Length; offset += plainBlockSize)
            {
                int len = Math.Min(plainBlockSize, plaintext.Length - offset);
                byte[] block = new byte[len];
                Buffer.BlockCopy(plaintext, offset, block, 0, len);

                BigInteger m = BigEndianUnsignedToBigInteger(block);

                if (m >= publicKey.N)
                    throw new ArgumentException("RSA message block is out of range.");

                BigInteger c = ModPow(m, publicKey.E, publicKey.N);

                blocks.Add(ToFixedBigEndianHex(c, cipherBlockSize));
                lengths.Add(len);
            }
        }

        string envelopeJson = BuildEnvelopeJson(
            plainBlockSize,
            cipherBlockSize,
            lengths,
            blocks
        );

        return Encoding.UTF8.GetBytes(envelopeJson);
    }

    private static string BuildEnvelopeJson(
        int blockSize,
        int cipherBlockSize,
        List<int> lengths,
        List<string> blocks
    )
    {
        StringBuilder sb = new StringBuilder();

        sb.Append("{");
        sb.Append("\"type\":\"RSA_RAW_BLOCKS\",");
        sb.Append("\"version\":1,");
        sb.Append("\"block_size\":").Append(blockSize).Append(",");
        sb.Append("\"cipher_block_size\":").Append(cipherBlockSize).Append(",");

        sb.Append("\"lengths\":[");
        for (int i = 0; i < lengths.Count; i++)
        {
            if (i > 0) sb.Append(",");
            sb.Append(lengths[i]);
        }
        sb.Append("],");

        sb.Append("\"blocks\":[");
        for (int i = 0; i < blocks.Count; i++)
        {
            if (i > 0) sb.Append(",");
            sb.Append("\"").Append(blocks[i]).Append("\"");
        }
        sb.Append("]");

        sb.Append("}");

        return sb.ToString();
    }

    public static int MaxPlainBlockBytes(BigInteger n)
    {
        int bitLength = BitLength(n);
        int blockSize = (bitLength - 1) / 8;

        if (blockSize <= 0)
            throw new ArgumentException("Invalid RSA modulus.");

        return blockSize;
    }

    public static int CipherBlockBytes(BigInteger n)
    {
        return (BitLength(n) + 7) / 8;
    }

    private static BigInteger ModPow(BigInteger value, BigInteger exponent, BigInteger modulus)
    {
        if (modulus <= 0)
            throw new ArgumentException("modulus must be positive.");

        if (exponent < 0)
            throw new ArgumentException("exponent must be non-negative.");

        BigInteger result = BigInteger.One;
        value %= modulus;

        while (exponent > 0)
        {
            if (!exponent.IsEven)
                result = (result * value) % modulus;

            value = (value * value) % modulus;
            exponent >>= 1;
        }

        return result;
    }

    private static int BitLength(BigInteger value)
    {
        if (value < 0)
            throw new ArgumentException("value must be non-negative.");

        if (value.IsZero)
            return 0;

        byte[] bytes = BigIntegerToBigEndianUnsigned(value);
        int bits = (bytes.Length - 1) * 8;

        byte top = bytes[0];
        while (top != 0)
        {
            bits++;
            top >>= 1;
        }

        return bits;
    }

    private static BigInteger BigEndianUnsignedToBigInteger(byte[] bigEndian)
    {
        if (bigEndian == null || bigEndian.Length == 0)
            return BigInteger.Zero;

        byte[] littleEndian = new byte[bigEndian.Length + 1];

        for (int i = 0; i < bigEndian.Length; i++)
            littleEndian[i] = bigEndian[bigEndian.Length - 1 - i];

        littleEndian[littleEndian.Length - 1] = 0x00;
        return new BigInteger(littleEndian);
    }

    private static byte[] BigIntegerToBigEndianUnsigned(BigInteger value)
    {
        if (value < 0)
            throw new ArgumentException("value must be non-negative.");

        byte[] littleEndian = value.ToByteArray();

        int actualLength = littleEndian.Length;
        while (actualLength > 1 && littleEndian[actualLength - 1] == 0x00)
            actualLength--;

        byte[] bigEndian = new byte[actualLength];

        for (int i = 0; i < actualLength; i++)
            bigEndian[actualLength - 1 - i] = littleEndian[i];

        return bigEndian;
    }

    private static string ToFixedBigEndianHex(BigInteger value, int outputBytes)
    {
        byte[] raw = BigIntegerToBigEndianUnsigned(value);

        if (raw.Length > outputBytes)
            throw new ArgumentException("RSA integer too large for fixed output size.");

        byte[] fixedBytes = new byte[outputBytes];
        Buffer.BlockCopy(raw, 0, fixedBytes, outputBytes - raw.Length, raw.Length);

        StringBuilder sb = new StringBuilder(outputBytes * 2);
        for (int i = 0; i < fixedBytes.Length; i++)
            sb.Append(fixedBytes[i].ToString("x2"));

        return sb.ToString();
    }

    private static string MatchString(string json, string key, bool required)
    {
        Match m = Regex.Match(
            json,
            "\"" + Regex.Escape(key) + "\"\\s*:\\s*\"([^\"]*)\""
        );

        if (!m.Success)
        {
            if (required)
                throw new ArgumentException("Missing JSON string field: " + key);

            return "";
        }

        return m.Groups[1].Value;
    }

    private static string MatchNumberOrString(string json, string key)
    {
        Match m = Regex.Match(
            json,
            "\"" + Regex.Escape(key) + "\"\\s*:\\s*(?:\"([0-9]+)\"|([0-9]+))"
        );

        if (!m.Success)
            throw new ArgumentException("Missing JSON number field: " + key);

        string a = m.Groups[1].Value;
        string b = m.Groups[2].Value;

        return !string.IsNullOrEmpty(a) ? a : b;
    }
}