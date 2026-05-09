using System;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;

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
    // 格式：
    // Base64(iv + ciphertext)
    //
    // DES block / CBC / PKCS7 由 CustomDes.cs 自己实现。
    // ============================================================

    public static string DesEncryptJson(byte[] key, string json)
    {
        if (key == null || key.Length != DesKeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (json == null)
            json = "{}";

        CryptoTrace.Log(
            "DES 加密开始",
            "格式：Base64(iv + ciphertext)，算法：自写 DES-CBC-PKCS7。"
        );

        CryptoTrace.Log(
            "1. DES 明文 JSON",
            json
        );

        CryptoTrace.Log(
            "2. DES Key",
            CryptoTrace.Hex(key)
        );

        byte[] iv = new byte[DesBlockBytes];

        using (var rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(iv);
        }

        byte[] plainBytes = Encoding.UTF8.GetBytes(json);

        CryptoTrace.Log(
            "3. 随机 IV 和明文字节",
            $"IV:\n{CryptoTrace.Hex(iv)}\n\n" +
            $"Plain Bytes:\n{CryptoTrace.Hex(plainBytes, 96)}"
        );

        byte[] cipherBytes = CustomDes.EncryptCbcPkcs7(
            key,
            iv,
            plainBytes
        );

        byte[] output = new byte[iv.Length + cipherBytes.Length];

        Buffer.BlockCopy(iv, 0, output, 0, iv.Length);
        Buffer.BlockCopy(cipherBytes, 0, output, iv.Length, cipherBytes.Length);

        string result = Convert.ToBase64String(output);

        CryptoTrace.Log(
            "4. DES-CBC-PKCS7 加密结果",
            $"Ciphertext:\n{CryptoTrace.Hex(cipherBytes, 96)}\n\n" +
            $"Base64(iv + ciphertext):\n{CryptoTrace.Mask(result, 40, 24)}"
        );

        return result;
    }
    public static string DesDecryptJson(byte[] key, string ciphertextB64)
    {
        if (key == null || key.Length != DesKeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (string.IsNullOrWhiteSpace(ciphertextB64))
            throw new ArgumentException("DES ciphertext is empty.");

        CryptoTrace.Log(
            "DES 解密开始",
            "格式：Base64(iv + ciphertext)，算法：自写 DES-CBC-PKCS7。"
        );

        CryptoTrace.Log(
            "1. DES Key",
            CryptoTrace.Hex(key)
        );

        byte[] raw = Convert.FromBase64String(ciphertextB64.Trim());

        if (raw.Length <= DesBlockBytes)
            throw new ArgumentException("DES ciphertext is too short.");

        byte[] iv = new byte[DesBlockBytes];
        byte[] cipherBytes = new byte[raw.Length - DesBlockBytes];

        Buffer.BlockCopy(raw, 0, iv, 0, DesBlockBytes);
        Buffer.BlockCopy(raw, DesBlockBytes, cipherBytes, 0, cipherBytes.Length);

        CryptoTrace.Log(
            "2. 拆分 Base64 密文",
            $"Raw:\n{CryptoTrace.Hex(raw, 96)}\n\n" +
            $"IV:\n{CryptoTrace.Hex(iv)}\n\n" +
            $"Ciphertext:\n{CryptoTrace.Hex(cipherBytes, 96)}"
        );

        byte[] plainBytes = CustomDes.DecryptCbcPkcs7(
            key,
            iv,
            cipherBytes
        );

        string plainJson = Encoding.UTF8.GetString(plainBytes);

        CryptoTrace.Log(
            "3. DES-CBC-PKCS7 解密结果",
            plainJson
        );

        return plainJson;
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
    // 这里不再使用 BouncyCastle。
    // PEM / DER / ASN.1 公钥解析由 PemPublicKeyParser.cs 完成。
    // OAEP-SHA256 + RSA m^e mod n 由 CustomRsa.cs 完成。
    // ============================================================

    public static string RsaEncryptJsonWithPublicPem(string publicPem, string json)
    {
        if (string.IsNullOrWhiteSpace(publicPem))
            throw new ArgumentException("RSA public PEM is empty.");

        if (json == null)
            json = "{}";

        try
        {
            CryptoTrace.Clear();

            CryptoTrace.Log(
                "RSA 加密开始",
                "用途：客户端把 REGISTER_REQ / AS_REQ / CHANGE_PASSWORD_REQ 的敏感 payload 加密后发给 AS。"
            );

            CryptoTrace.Log(
                "1. 明文 JSON",
                json
            );

            PemRsaPublicKey publicKey =
                PemPublicKeyParser.ParseSubjectPublicKeyInfo(publicPem);

            CryptoTrace.Log(
                "2. 解析 AS 公钥 PEM",
                $"Modulus n:\n{CryptoTrace.Hex(publicKey.Modulus, 96)}\n\n" +
                $"Exponent e:\n{CryptoTrace.Hex(publicKey.Exponent)}\n\n" +
                $"说明：RSA 公钥由 n 和 e 组成，后续执行 c = m^e mod n。"
            );

            byte[] plainBytes = Encoding.UTF8.GetBytes(json);

            CryptoTrace.Log(
                "3. UTF-8 明文字节",
                CryptoTrace.BytesInfo(plainBytes)
            );

            byte[] encrypted = CustomRsa.EncryptOaepSha256(
                publicKey.Modulus,
                publicKey.Exponent,
                plainBytes
            );

            string encryptedB64 = Convert.ToBase64String(encrypted);

            CryptoTrace.Log(
                "4. RSA-OAEP-SHA256 加密结果",
                $"Cipher Hex:\n{CryptoTrace.Hex(encrypted, 96)}\n\n" +
                $"Cipher Base64:\n{CryptoTrace.Mask(encryptedB64, 40, 24)}\n\n" +
                $"说明：最终 payload = Base64(RSA-OAEP-SHA256(JSON))。"
            );

            return encryptedB64;
        }
        catch (Exception ex)
        {
            Debug.LogError(
                "[ClientCrypto] Custom RSA-OAEP-SHA256 encrypt failed. " +
                "请确认 as_public_key.txt 内容完整，格式是 PEM PUBLIC KEY。\n" +
                ex
            );

            CryptoTrace.Log(
                "RSA 加密失败",
                ex.ToString()
            );

            throw;
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