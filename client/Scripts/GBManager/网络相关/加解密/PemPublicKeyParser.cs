using System;
using System.Collections.Generic;

public sealed class PemRsaPublicKey
{
    public byte[] Modulus { get; private set; }
    public byte[] Exponent { get; private set; }

    public PemRsaPublicKey(byte[] modulus, byte[] exponent)
    {
        Modulus = modulus ?? throw new ArgumentNullException(nameof(modulus));
        Exponent = exponent ?? throw new ArgumentNullException(nameof(exponent));
    }
}

public static class PemPublicKeyParser
{
    public static PemRsaPublicKey ParseSubjectPublicKeyInfo(string pem)
    {
        if (string.IsNullOrWhiteSpace(pem))
            throw new ArgumentException("RSA public PEM is empty.");

        string header = DetectHeader(pem);
        byte[] der = PemToDer(pem);

        DerReader reader = new DerReader(der);

        // -----BEGIN RSA PUBLIC KEY-----
        // PKCS#1:
        // SEQUENCE
        //   INTEGER n
        //   INTEGER e
        if (header == "RSA PUBLIC KEY")
        {
            byte[] seq = reader.ReadSequence();
            DerReader rsaReader = new DerReader(seq);

            byte[] n = rsaReader.ReadIntegerBytes();
            byte[] e = rsaReader.ReadIntegerBytes();

            rsaReader.RequireEnd();
            reader.RequireEnd();

            return new PemRsaPublicKey(StripLeadingZero(n), StripLeadingZero(e));
        }

        // -----BEGIN PUBLIC KEY-----
        // SubjectPublicKeyInfo:
        // SEQUENCE
        //   SEQUENCE algorithmIdentifier
        //   BIT STRING
        //      SEQUENCE
        //        INTEGER n
        //        INTEGER e
        if (header == "PUBLIC KEY")
        {
            byte[] spkiSeq = reader.ReadSequence();
            reader.RequireEnd();

            DerReader spkiReader = new DerReader(spkiSeq);

            // algorithmIdentifier£¬Ìø¹ý
            spkiReader.ReadSequence();

            byte[] bitString = spkiReader.ReadBitString();
            spkiReader.RequireEnd();

            if (bitString.Length < 1)
                throw new ArgumentException("Invalid SubjectPublicKeyInfo BIT STRING.");

            int unusedBits = bitString[0];
            if (unusedBits != 0)
                throw new ArgumentException("Unsupported RSA public key BIT STRING unused bits.");

            byte[] rsaPublicKeyDer = new byte[bitString.Length - 1];
            Buffer.BlockCopy(bitString, 1, rsaPublicKeyDer, 0, rsaPublicKeyDer.Length);

            DerReader rsaOuterReader = new DerReader(rsaPublicKeyDer);
            byte[] rsaSeq = rsaOuterReader.ReadSequence();
            rsaOuterReader.RequireEnd();

            DerReader rsaReader = new DerReader(rsaSeq);

            byte[] n = rsaReader.ReadIntegerBytes();
            byte[] e = rsaReader.ReadIntegerBytes();

            rsaReader.RequireEnd();

            return new PemRsaPublicKey(StripLeadingZero(n), StripLeadingZero(e));
        }

        throw new ArgumentException("Unsupported PEM public key header: " + header);
    }

    private static string DetectHeader(string pem)
    {
        if (pem.Contains("-----BEGIN PUBLIC KEY-----"))
            return "PUBLIC KEY";

        if (pem.Contains("-----BEGIN RSA PUBLIC KEY-----"))
            return "RSA PUBLIC KEY";

        throw new ArgumentException("Unsupported PEM format. Expected PUBLIC KEY or RSA PUBLIC KEY.");
    }

    private static byte[] PemToDer(string pem)
    {
        string base64 = pem
            .Replace("-----BEGIN PUBLIC KEY-----", "")
            .Replace("-----END PUBLIC KEY-----", "")
            .Replace("-----BEGIN RSA PUBLIC KEY-----", "")
            .Replace("-----END RSA PUBLIC KEY-----", "")
            .Replace("\r", "")
            .Replace("\n", "")
            .Replace(" ", "")
            .Trim();

        if (string.IsNullOrWhiteSpace(base64))
            throw new ArgumentException("PEM has no Base64 body.");

        return Convert.FromBase64String(base64);
    }

    private static byte[] StripLeadingZero(byte[] value)
    {
        if (value == null || value.Length == 0)
            return Array.Empty<byte>();

        int index = 0;

        while (index < value.Length - 1 && value[index] == 0x00)
            index++;

        if (index == 0)
            return value;

        byte[] output = new byte[value.Length - index];
        Buffer.BlockCopy(value, index, output, 0, output.Length);
        return output;
    }

    private sealed class DerReader
    {
        private readonly byte[] data;
        private int offset;

        public DerReader(byte[] der)
        {
            data = der ?? throw new ArgumentNullException(nameof(der));
            offset = 0;
        }

        public byte[] ReadSequence()
        {
            return ReadValue(0x30);
        }

        public byte[] ReadBitString()
        {
            return ReadValue(0x03);
        }

        public byte[] ReadIntegerBytes()
        {
            return ReadValue(0x02);
        }

        public void RequireEnd()
        {
            if (offset != data.Length)
                throw new ArgumentException("DER has trailing bytes.");
        }

        private byte[] ReadValue(byte expectedTag)
        {
            if (offset >= data.Length)
                throw new ArgumentException("Unexpected end of DER.");

            byte tag = data[offset++];

            if (tag != expectedTag)
            {
                throw new ArgumentException(
                    $"Unexpected DER tag. Expected 0x{expectedTag:X2}, got 0x{tag:X2}."
                );
            }

            int length = ReadLength();

            if (length < 0 || offset + length > data.Length)
                throw new ArgumentException("Invalid DER length.");

            byte[] value = new byte[length];
            Buffer.BlockCopy(data, offset, value, 0, length);
            offset += length;

            return value;
        }

        private int ReadLength()
        {
            if (offset >= data.Length)
                throw new ArgumentException("Unexpected end of DER length.");

            int first = data[offset++];

            if ((first & 0x80) == 0)
                return first;

            int lengthBytes = first & 0x7F;

            if (lengthBytes == 0)
                throw new ArgumentException("Indefinite DER length is not supported.");

            if (lengthBytes > 4)
                throw new ArgumentException("DER length too large.");

            if (offset + lengthBytes > data.Length)
                throw new ArgumentException("Invalid DER length bytes.");

            int length = 0;

            for (int i = 0; i < lengthBytes; i++)
            {
                length = (length << 8) | data[offset++];
            }

            return length;
        }
    }
}