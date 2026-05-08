using System;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

using Org.BouncyCastle.Crypto;
using Org.BouncyCastle.Crypto.Encodings;
using Org.BouncyCastle.Crypto.Engines;
using Org.BouncyCastle.Crypto.Parameters;
using Org.BouncyCastle.OpenSsl;

public static class ClientCrypto
{
    public const int DesKeyBytes = 8;
    public const int DesBlockBytes = 8;
    public const int PasswordHashBytes = 32;

    // ============================================================
    // Time / Nonce
    // ============================================================

    public static long NowMs()
    {
        return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    }

    public static string GenerateNonce()
    {
        return Guid.NewGuid().ToString("N");
    }

    // ============================================================
    // Base64
    // ============================================================

    public static string Base64Encode(byte[] raw)
    {
        if (raw == null)
            return "";

        return Convert.ToBase64String(raw);
    }

    public static byte[] Base64Decode(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
            throw new ArgumentException("Base64 value is empty.");

        return Convert.FromBase64String(value.Trim());
    }

    public static bool TryBase64Decode(string value, out byte[] bytes)
    {
        bytes = null;

        if (string.IsNullOrWhiteSpace(value))
            return false;

        try
        {
            bytes = Convert.FromBase64String(value.Trim());
            return true;
        }
        catch
        {
            return false;
        }
    }

    // ============================================================
    // PBKDF2-HMAC-SHA256
    //
    // Python AS 端规则：
    // PBKDF2-HMAC-SHA256(password, salt, iter, dklen=32)
    // 前 8 字节作为 Kuser。
    // ============================================================

    public static byte[] DerivePasswordMaterial(
        string password,
        byte[] salt,
        int iterations,
        int outputBytes = PasswordHashBytes
    )
    {
        if (password == null)
            password = "";

        if (salt == null || salt.Length == 0)
            throw new ArgumentException("PBKDF2 salt is empty.");

        if (iterations <= 0)
            throw new ArgumentException("PBKDF2 iterations must be positive.");

        using (var kdf = new Rfc2898DeriveBytes(
            password,
            salt,
            iterations,
            HashAlgorithmName.SHA256
        ))
        {
            return kdf.GetBytes(outputBytes);
        }
    }

    public static byte[] DeriveKuser(string password, byte[] salt, int iterations)
    {
        byte[] material = DerivePasswordMaterial(
            password,
            salt,
            iterations,
            PasswordHashBytes
        );

        byte[] key = new byte[DesKeyBytes];
        Buffer.BlockCopy(material, 0, key, 0, DesKeyBytes);
        return key;
    }

    // ============================================================
    // DES-CBC-PKCS7
    //
    // Python 端格式：
    // Base64(iv + ciphertext)
    //
    // key 必须 8 字节。
    // iv 随机 8 字节。
    // 明文是 UTF-8 JSON。
    // ============================================================

    public static string DesEncryptJson(byte[] key, string json)
    {
        if (key == null || key.Length != DesKeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (json == null)
            json = "{}";

        byte[] iv = new byte[DesBlockBytes];

        using (var rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(iv);
        }

        byte[] plainBytes = Encoding.UTF8.GetBytes(json);

        using (System.Security.Cryptography.DES des = System.Security.Cryptography.DES.Create())
        {
            des.Mode = CipherMode.CBC;
            des.Padding = PaddingMode.PKCS7;
            des.Key = key;
            des.IV = iv;

            using (ICryptoTransform encryptor = des.CreateEncryptor())
            {
                byte[] cipherBytes = encryptor.TransformFinalBlock(
                    plainBytes,
                    0,
                    plainBytes.Length
                );

                byte[] output = new byte[iv.Length + cipherBytes.Length];

                Buffer.BlockCopy(iv, 0, output, 0, iv.Length);
                Buffer.BlockCopy(cipherBytes, 0, output, iv.Length, cipherBytes.Length);

                return Convert.ToBase64String(output);
            }
        }
    }

    public static string DesDecryptJson(byte[] key, string ciphertextB64)
    {
        if (key == null || key.Length != DesKeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (string.IsNullOrWhiteSpace(ciphertextB64))
            throw new ArgumentException("DES ciphertext is empty.");

        byte[] raw = Convert.FromBase64String(ciphertextB64.Trim());

        if (raw.Length <= DesBlockBytes)
            throw new ArgumentException("DES ciphertext is too short.");

        byte[] iv = new byte[DesBlockBytes];
        byte[] cipherBytes = new byte[raw.Length - DesBlockBytes];

        Buffer.BlockCopy(raw, 0, iv, 0, DesBlockBytes);
        Buffer.BlockCopy(raw, DesBlockBytes, cipherBytes, 0, cipherBytes.Length);

        using (System.Security.Cryptography.DES des = System.Security.Cryptography.DES.Create())
        {
            des.Mode = CipherMode.CBC;
            des.Padding = PaddingMode.PKCS7;
            des.Key = key;
            des.IV = iv;

            using (ICryptoTransform decryptor = des.CreateDecryptor())
            {
                byte[] plainBytes = decryptor.TransformFinalBlock(
                    cipherBytes,
                    0,
                    cipherBytes.Length
                );

                return Encoding.UTF8.GetString(plainBytes);
            }
        }
    }

    public static string DesEncryptJsonWithBase64Key(string keyB64, string json)
    {
        byte[] key = Base64Decode(keyB64);
        return DesEncryptJson(key, json);
    }

    public static string DesDecryptJsonWithBase64Key(string keyB64, string ciphertextB64)
    {
        byte[] key = Base64Decode(keyB64);
        return DesDecryptJson(key, ciphertextB64);
    }

    // ============================================================
    // RSA-OAEP-SHA256
    //
    // AS 请求 payload 格式：
    // Base64(RSA-OAEP-SHA256(JSON))
    //
    // 用 BouncyCastle 实现，绕开 Unity/Mono 不支持
    // RSA.ImportSubjectPublicKeyInfo 的问题。
    // ============================================================

    public static string RsaEncryptJsonWithPublicPem(string publicPem, string json)
    {
        if (string.IsNullOrWhiteSpace(publicPem))
            throw new ArgumentException("RSA public PEM is empty.");

        if (json == null)
            json = "{}";

        try
        {
            RsaKeyParameters publicKey = LoadRsaPublicKeyFromPem(publicPem);
            byte[] plainBytes = Encoding.UTF8.GetBytes(json);

            OaepEncoding cipher = new OaepEncoding(
                new RsaEngine(),
                new Org.BouncyCastle.Crypto.Digests.Sha256Digest(),
                new Org.BouncyCastle.Crypto.Digests.Sha256Digest(),
                null
            );

            cipher.Init(true, publicKey);

            byte[] encrypted = cipher.ProcessBlock(
                plainBytes,
                0,
                plainBytes.Length
            );

            return Convert.ToBase64String(encrypted);
        }
        catch (Exception ex)
        {
            Debug.LogError(
                "[ClientCrypto] RSA-OAEP-SHA256 encrypt failed. " +
                "请确认 as_public_key.txt 内容完整，并且 Unity 已成功导入 BouncyCastle。\n" +
                ex
            );

            throw;
        }
    }

    private static RsaKeyParameters LoadRsaPublicKeyFromPem(string publicPem)
    {
        using (StringReader sr = new StringReader(publicPem))
        {
            PemReader reader = new PemReader(sr);
            object pemObject = reader.ReadObject();

            if (pemObject == null)
                throw new ArgumentException("Invalid RSA public PEM: empty PEM object.");

            if (pemObject is RsaKeyParameters rsaKey)
            {
                if (rsaKey.IsPrivate)
                    throw new ArgumentException("Expected RSA public key, got private key.");

                return rsaKey;
            }

            if (pemObject is AsymmetricCipherKeyPair pair)
            {
                if (pair.Public is RsaKeyParameters pairPublicKey)
                    return pairPublicKey;
            }

            if (pemObject is AsymmetricKeyParameter asymmetricKey)
            {
                if (asymmetricKey is RsaKeyParameters asymmetricRsaKey)
                {
                    if (asymmetricRsaKey.IsPrivate)
                        throw new ArgumentException("Expected RSA public key, got private key.");

                    return asymmetricRsaKey;
                }
            }

            throw new ArgumentException(
                "Unsupported PEM key type: " + pemObject.GetType().FullName
            );
        }
    }

    // ============================================================
    // Validation helpers
    // ============================================================

    public static void RequireDesKeyBase64(string keyB64, string label)
    {
        if (!TryBase64Decode(keyB64, out byte[] key))
            throw new ArgumentException($"{label} is not valid Base64.");

        if (key == null || key.Length != DesKeyBytes)
            throw new ArgumentException($"{label} must decode to exactly 8 bytes.");
    }
}