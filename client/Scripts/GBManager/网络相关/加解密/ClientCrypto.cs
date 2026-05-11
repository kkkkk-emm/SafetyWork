using System;
using System.Security.Cryptography;
using System.Text;
using UnityEngine;
using System.Numerics;
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

        CryptoTrace.Step(
            CryptoTraceFlow.DesEncrypt,
            1,
            4,
            "准备 DES 明文",
            "客户端把需要发送的 JSON 明文转换成 UTF-8 字节，准备进入 DES-CBC 加密。",
            input: json,
            output: Encoding.UTF8.GetByteCount(json) + " bytes plaintext"
        );

        CryptoTrace.Step(
            CryptoTraceFlow.DesEncrypt,
            2,
            4,
            "准备 DES 密钥和 IV",
            "DES 使用 8 字节密钥。CBC 模式还需要一个随机 8 字节 IV，保证相同明文每次加密结果不同。",
            input: "DES key = " + CryptoTrace.Hex(key),
            output: "IV will be generated randomly",
            formula: "DES key length = 64 bit, IV length = 64 bit"
        );

        byte[] iv = new byte[DesBlockBytes];

        using (var rng = RandomNumberGenerator.Create())
        {
            rng.GetBytes(iv);
        }

        byte[] plainBytes = Encoding.UTF8.GetBytes(json);

        CryptoTrace.Step(
            CryptoTraceFlow.DesEncrypt,
            3,
            4,
            "DES-CBC-PKCS7 加密",
            "先对明文做 PKCS7 填充，然后每一块先和上一块密文或 IV 异或，再进行 DES 块加密。",
            input:
                "IV = " + CryptoTrace.Hex(iv) + "\n" +
                "Plain = " + CryptoTrace.BytesInfo(plainBytes, 32),
            output: "进入自写 CustomDes.EncryptCbcPkcs7",
            formula: "Cᵢ = DES_ENC(Pᵢ XOR Cᵢ₋₁)"
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

        CryptoTrace.Step(
            CryptoTraceFlow.DesEncrypt,
            4,
            4,
            "Base64 封装",
            "最终网络传输格式是 Base64(iv + ciphertext)。服务端收到后会先拆出 IV，再用同样的 DES-CBC-PKCS7 规则解密。",
            input:
                "Ciphertext = " + CryptoTrace.BytesInfo(cipherBytes, 32),
            output:
                "Base64(iv + ciphertext) = " + CryptoTrace.Mask(result),
            formula: "message = Base64(IV || Ciphertext)"
        );

        return result;
    }

    public static string DesDecryptJson(byte[] key, string ciphertextB64)
    {
        if (key == null || key.Length != DesKeyBytes)
            throw new ArgumentException("DES key must be exactly 8 bytes.");

        if (string.IsNullOrWhiteSpace(ciphertextB64))
            throw new ArgumentException("DES ciphertext is empty.");

        CryptoTrace.Step(
            CryptoTraceFlow.DesDecrypt,
            1,
            4,
            "解析 DES 密文",
            "服务端返回的 DES 数据格式是 Base64(iv + ciphertext)。客户端先进行 Base64 解码。",
            input: "Base64 密文 = " + CryptoTrace.Mask(ciphertextB64),
            output: "准备拆分 IV 和 ciphertext",
            formula: "raw = Base64Decode(message)"
        );

        byte[] raw = Convert.FromBase64String(ciphertextB64.Trim());

        if (raw.Length <= DesBlockBytes)
            throw new ArgumentException("DES ciphertext is too short.");

        byte[] iv = new byte[DesBlockBytes];
        byte[] cipherBytes = new byte[raw.Length - DesBlockBytes];

        Buffer.BlockCopy(raw, 0, iv, 0, DesBlockBytes);
        Buffer.BlockCopy(raw, DesBlockBytes, cipherBytes, 0, cipherBytes.Length);

        CryptoTrace.Step(
            CryptoTraceFlow.DesDecrypt,
            2,
            4,
            "拆分 IV 和密文",
            "前 8 字节是 CBC 模式的 IV，后面的部分才是真正的 DES 密文块。",
            input:
                "Raw = " + CryptoTrace.BytesInfo(raw, 32),
            output:
                "IV = " + CryptoTrace.Hex(iv) + "\n" +
                "Ciphertext = " + CryptoTrace.BytesInfo(cipherBytes, 32),
            formula: "raw = IV || Ciphertext"
        );

        CryptoTrace.Step(
            CryptoTraceFlow.DesDecrypt,
            3,
            4,
            "DES-CBC-PKCS7 解密",
            "逐块执行 DES 解密，再和上一块密文或 IV 异或，最后去掉 PKCS7 填充。",
            input:
                "DES key = " + CryptoTrace.Hex(key) + "\n" +
                "Ciphertext length = " + cipherBytes.Length + " bytes",
            output: "进入自写 CustomDes.DecryptCbcPkcs7",
            formula: "Pᵢ = DES_DEC(Cᵢ) XOR Cᵢ₋₁"
        );

        byte[] plainBytes = CustomDes.DecryptCbcPkcs7(
            key,
            iv,
            cipherBytes
        );

        string plainJson = Encoding.UTF8.GetString(plainBytes);

        CryptoTrace.Step(
            CryptoTraceFlow.DesDecrypt,
            4,
            4,
            "得到 JSON 明文",
            "DES 解密完成后，客户端得到服务端返回的票据内容、会话密钥或认证响应。",
            input: plainBytes.Length + " bytes plaintext",
            output: plainJson
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
    // PEM / DER / ASN.1 公钥解析由 PemPublicKeyParser.cs 完成。
    // OAEP-SHA256 + RSA m^e mod n 由 CustomRsa.cs 完成。
    // ============================================================

    public static string RsaEncryptJsonWithPublicPem(string publicKeyJson, string json)
    {
        if (string.IsNullOrWhiteSpace(publicKeyJson))
            throw new ArgumentException("RSA public key JSON is empty.");

        if (json == null)
            json = "{}";

        try
        {
            CryptoTrace.Clear();

            CryptoTrace.Step(
                CryptoTraceFlow.RsaEncrypt,
                1,
                5,
                "生成明文 JSON",
                "客户端把用户名、密码、nonce 等敏感字段组装成 JSON。这个 JSON 不会明文发送给服务器。",
                input: json,
                output: Encoding.UTF8.GetByteCount(json) + " bytes plaintext"
            );

            RsaRawPublicKey publicKey =
                RsaRawBlocksJson.ParsePublicKeyJson(publicKeyJson);

            int plainBlockSize = RsaRawBlocksJson.MaxPlainBlockBytes(publicKey.N);
            int cipherBlockSize = RsaRawBlocksJson.CipherBlockBytes(publicKey.N);

            CryptoTrace.Step(
                CryptoTraceFlow.RsaEncrypt,
                2,
                5,
                "解析 AS 公钥 JSON",
                "客户端读取 as_public_key.json，从中解析 RSA 公钥参数 n 和 e。",
                input: "AS public key JSON",
                output:
                    "n bit length = " + publicKey.N.GetBitLengthSafe() + "\n" +
                    "e = " + publicKey.E,
                formula: "RSA public key = (n, e)"
            );

            byte[] plainBytes = Encoding.UTF8.GetBytes(json);

            CryptoTrace.Step(
                CryptoTraceFlow.RsaEncrypt,
                3,
                5,
                "RSA 明文分块",
                "新版服务器协议使用 RSA_RAW_BLOCKS。客户端把明文按 block_size 分块，每块转成大整数后分别加密。",
                input: "Plain length = " + plainBytes.Length + " bytes",
                output:
                    "block_size = " + plainBlockSize + " bytes\n" +
                    "cipher_block_size = " + cipherBlockSize + " bytes",
                formula: "block_size = floor((bitlen(n)-1)/8)"
            );

            byte[] envelopeBytes =
                RsaRawBlocksJson.EncryptBytesToEnvelopeBytes(plainBytes, publicKey);

            string envelopeJson = Encoding.UTF8.GetString(envelopeBytes);

            CryptoTrace.Step(
                CryptoTraceFlow.RsaEncrypt,
                4,
                5,
                "RSA_RAW_BLOCKS 加密",
                "每个明文块执行 RSA 公钥模幂运算，得到固定长度密文块，然后写入 envelope JSON。",
                input: "plaintext blocks",
                output: CryptoTrace.Mask(envelopeJson, 120, 40),
                formula: "c = m^e mod n"
            );

            string encryptedB64 = Convert.ToBase64String(envelopeBytes);

            CryptoTrace.Step(
                CryptoTraceFlow.RsaEncrypt,
                5,
                5,
                "Base64 封装",
                "客户端把 envelope JSON 转成 UTF-8 字节，再 Base64 编码，作为 AS 请求 payload。",
                input: envelopeBytes.Length + " bytes envelope JSON",
                output: CryptoTrace.Mask(encryptedB64),
                formula: "payload = Base64(EnvelopeJson)"
            );

            return encryptedB64;
        }
        catch (Exception ex)
        {
            Debug.LogError(
                "[ClientCrypto] RSA_RAW_BLOCKS encrypt failed. " +
                "请确认客户端使用的是服务器最新 as_public_key.json。\n" +
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

public static class BigIntegerTraceExtensions
{
    public static int GetBitLengthSafe(this BigInteger value)
    {
        if (value < 0)
            value = BigInteger.Abs(value);

        if (value.IsZero)
            return 0;

        byte[] bytes = value.ToByteArray();
        int actualLength = bytes.Length;

        while (actualLength > 1 && bytes[actualLength - 1] == 0x00)
            actualLength--;

        int bits = (actualLength - 1) * 8;
        byte top = bytes[actualLength - 1];

        while (top != 0)
        {
            bits++;
            top >>= 1;
        }

        return bits;
    }
}