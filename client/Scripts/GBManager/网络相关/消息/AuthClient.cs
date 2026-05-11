using System;
using System.Collections.Generic;
using System.Text;
using System.Threading.Tasks;
using NativeWebSocket;
using UnityEngine;

public class AuthClient : MonoBehaviour
{
    [Header("认证服务地址")]
    [SerializeField] private string asUrl = "ws://127.0.0.1:9000";
    [SerializeField] private string tgsUrl = "ws://127.0.0.1:9001";

    [Header("目标 GS 服务名")]
    [SerializeField] private string gsServiceName = "game/ws@127.0.0.1:8765";

    [Header("AS 公钥")]
    [Tooltip("把 as_public_key.pem 复制成 as_public_key.txt 后，作为 TextAsset 拖进来。")]
    [SerializeField] private TextAsset asPublicKeyPemAsset;

    [TextArea(4, 10)]
    [Tooltip("也可以直接粘贴 PUBLIC KEY PEM。优先使用这里；为空时使用 asPublicKeyPemAsset。")]
    [SerializeField] private string asPublicKeyPemOverride = "";

    [Header("请求设置")]
    [SerializeField] private int requestTimeoutMs = 5000;
    [SerializeField] private bool debugLog = true;

    private readonly List<WebSocket> tempSockets = new List<WebSocket>();

    // ============================================================
    // Payload classes
    // ============================================================

    [Serializable]
    private class RegisterReqPayload
    {
        public string username;
        public string password;
    }

    [Serializable]
    private class RegisterRepPayload
    {
        public bool ok;
        public long userId;
        public string error;
    }

    [Serializable]
    private class AsReqPayload
    {
        public string username;
        public string password;
        public string nonce;
    }

    [Serializable]
    private class AsRepOuterPayload
    {
        public string salt;
        public int iter;
        public string part;
    }

    [Serializable]
    private class AsRepProtectedPart
    {
        public long userId;
        public string username;
        public string nonce;
        public string kcTgs;
        public long exp;
        public long loginGen;
    }

    [Serializable]
    private class ChangePasswordReqPayload
    {
        public string username;
        public string oldPassword;
        public string newPassword;
    }

    [Serializable]
    private class ChangePasswordRepPayload
    {
        public bool ok;
        public string error;
    }

    [Serializable]
    private class TgsAuthPayload
    {
        public string type;
        public long ts;
        public string nonce;
    }

    [Serializable]
    private class TgsReqPayload
    {
        public string type;
        public string service;
        public string nonce;
    }

    [Serializable]
    private class TgsRepProtectedPayload
    {
        public string nonce;
        public string kcGs;
        public long exp;
    }

    [Serializable]
    private class GsAuthPayload
    {
        public long ts;
        public string nonce;
    }

    [Serializable]
    public class AuthResult
    {
        public bool ok;
        public string error;
    }

    [Serializable]
    public class RegisterResult : AuthResult
    {
        public long userId;
    }

    [Serializable]
    public class LoginResult : AuthResult
    {
        public long userId;
        public string username;
        public string tgt;
        public string kcTgs;
        public long exp;
        public long loginGen;
    }

    [Serializable]
    public class TicketResult : AuthResult
    {
        public string serviceTicket;
        public string kcGs;
        public long exp;
    }

    // ============================================================
    // Unity lifecycle
    // ============================================================

    private void Awake()
    {
        AuthSession.EnsureExists().EnsureClientId();
    }

    private void Update()
    {
#if !UNITY_WEBGL || UNITY_EDITOR
        for (int i = tempSockets.Count - 1; i >= 0; i--)
        {
            WebSocket socket = tempSockets[i];

            if (socket == null)
            {
                tempSockets.RemoveAt(i);
                continue;
            }

            socket.DispatchMessageQueue();
        }
#endif
    }

    // ============================================================
    // Config
    // ============================================================

    public void ConfigureUrls(string newAsUrl, string newTgsUrl, string newGsServiceName)
    {
        if (!string.IsNullOrWhiteSpace(newAsUrl))
            asUrl = newAsUrl.Trim();

        if (!string.IsNullOrWhiteSpace(newTgsUrl))
            tgsUrl = newTgsUrl.Trim();

        if (!string.IsNullOrWhiteSpace(newGsServiceName))
            gsServiceName = newGsServiceName.Trim();

        DebugAuth($"ConfigureUrls AS={asUrl}, TGS={tgsUrl}, GSService={gsServiceName}");
    }

    private string GetAsPublicKeyPem()
    {
        if (!string.IsNullOrWhiteSpace(asPublicKeyPemOverride))
            return asPublicKeyPemOverride.Trim();

        if (asPublicKeyPemAsset != null && !string.IsNullOrWhiteSpace(asPublicKeyPemAsset.text))
            return asPublicKeyPemAsset.text.Trim();

        throw new InvalidOperationException(
            "AS public key missing. 请把 as_public_key.txt 拖到 AuthClient.asPublicKeyPemAsset，或者粘贴到 asPublicKeyPemOverride。"
        );
    }

    // ============================================================
    // REGISTER_REQ
    // ============================================================

    public async Task<RegisterResult> RegisterAsync(string username, string password)
    {
        AuthSession.EnsureExists().EnsureClientId();

        RegisterResult result = new RegisterResult
        {
            ok = false,
            error = ""
        };

        username = NormalizeInput(username);

        if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password))
        {
            result.error = "USERNAME_OR_PASSWORD_EMPTY";
            return result;
        }

        try
        {
            RegisterReqPayload plain = new RegisterReqPayload
            {
                username = username,
                password = password
            };

            string plainJson = JsonUtility.ToJson(plain);

            string encryptedPayload = ClientCrypto.RsaEncryptJsonWithPublicPem(
                GetAsPublicKeyPem(),
                plainJson
            );

            ProtocolMessage req = new ProtocolMessage
            {
                type = "REGISTER_REQ",
                clientId = AuthSession.Ctx.clientId,
                payload = encryptedPayload
            };

            ProtocolMessage rep = await SendRequestAsync(
                asUrl,
                req,
                "REGISTER_REP"
            );

            if (rep == null)
            {
                result.error = "REGISTER_NO_RESPONSE";
                return result;
            }

            if (rep.type == "ERROR")
            {
                result.error = rep.error;
                return result;
            }

            RegisterRepPayload payload = SafeFromJson<RegisterRepPayload>(rep.payload);

            if (payload == null)
            {
                result.error = "REGISTER_BAD_PAYLOAD";
                return result;
            }

            result.ok = payload.ok;
            result.userId = payload.userId;
            result.error = payload.error ?? "";

            DebugAuth($"REGISTER ok={result.ok}, userId={result.userId}, error={result.error}");

            return result;
        }
        catch (Exception ex)
        {
            result.error = ex.Message;
            Debug.LogError($"[AuthClient] RegisterAsync failed: {ex}");
            return result;
        }
    }

    // ============================================================
    // AS_REQ
    // ============================================================

    public async Task<LoginResult> LoginAsync(string username, string password)
    {
        AuthSession.EnsureExists().EnsureClientId();

        LoginResult result = new LoginResult
        {
            ok = false,
            error = ""
        };

        username = NormalizeInput(username);

        if (string.IsNullOrWhiteSpace(username) || string.IsNullOrWhiteSpace(password))
        {
            result.error = "USERNAME_OR_PASSWORD_EMPTY";
            return result;
        }

        try
        {
            string nonce = ClientCrypto.GenerateNonce();

            AsReqPayload plain = new AsReqPayload
            {
                username = username,
                password = password,
                nonce = nonce
            };

            string plainJson = JsonUtility.ToJson(plain);

            string encryptedPayload = ClientCrypto.RsaEncryptJsonWithPublicPem(
                GetAsPublicKeyPem(),
                plainJson
            );

            ProtocolMessage req = new ProtocolMessage
            {
                type = "AS_REQ",
                clientId = AuthSession.Ctx.clientId,
                payload = encryptedPayload
            };

            ProtocolMessage rep = await SendRequestAsync(
                asUrl,
                req,
                "AS_REP"
            );

            if (rep == null)
            {
                result.error = "AS_NO_RESPONSE";
                return result;
            }

            if (rep.type == "ERROR")
            {
                result.error = rep.error;
                return result;
            }

            if (string.IsNullOrWhiteSpace(rep.ticket))
            {
                result.error = "AS_TGT_MISSING";
                return result;
            }

            AsRepOuterPayload outer = SafeFromJson<AsRepOuterPayload>(rep.payload);

            if (outer == null)
            {
                result.error = "AS_BAD_PAYLOAD";
                return result;
            }

            if (string.IsNullOrWhiteSpace(outer.salt) ||
                outer.iter <= 0 ||
                string.IsNullOrWhiteSpace(outer.part))
            {
                result.error = "AS_PAYLOAD_FIELDS_MISSING";
                return result;
            }

            byte[] salt = ClientCrypto.Base64Decode(outer.salt);
            byte[] kuser = ClientCrypto.DeriveKuser(password, salt, outer.iter);

            string partJson = ClientCrypto.DesDecryptJson(kuser, outer.part);
            AsRepProtectedPart part = SafeFromJson<AsRepProtectedPart>(partJson);

            if (part == null)
            {
                result.error = "AS_BAD_PART";
                return result;
            }

            if (part.nonce != nonce)
            {
                result.error = "AS_NONCE_MISMATCH";
                return result;
            }

            if (string.IsNullOrWhiteSpace(part.kcTgs))
            {
                result.error = "AS_KCTGS_MISSING";
                return result;
            }

            ClientCrypto.RequireDesKeyBase64(part.kcTgs, "KcTgs");

            result.ok = true;
            result.userId = part.userId;
            result.username = string.IsNullOrWhiteSpace(part.username) ? username : part.username;
            result.tgt = rep.ticket;
            result.kcTgs = part.kcTgs;
            result.exp = part.exp;
            result.loginGen = part.loginGen;
            result.error = "";

            AuthSession.EnsureExists().ApplyAsLogin(
                userId: result.userId,
                username: result.username,
                tgt: result.tgt,
                kcTgs: result.kcTgs,
                expMs: result.exp,
                loginGen: result.loginGen
            );
            Debug.Log($"[UserInfoPanel] ShowUser userId={result.userId}, username={result.username}, instance={UserInfoPanel.Instance}");

            UserInfoPanel.Instance?.ShowUser(result.userId, result.username);
            DebugAuth(
                $"LOGIN ok userId={result.userId}, username={result.username}, " +
                $"tgt=set, kcTgs=set, exp={result.exp}, loginGen={result.loginGen}"
            );

            return result;
        }
        catch (Exception ex)
        {
            result.error = ex.Message;
            Debug.LogError($"[AuthClient] LoginAsync failed: {ex}");
            return result;
        }
    }

    // ============================================================
    // CHANGE_PASSWORD_REQ
    // ============================================================

    public async Task<AuthResult> ChangePasswordAsync(
        string username,
        string oldPassword,
        string newPassword
    )
    {
        AuthSession.EnsureExists().EnsureClientId();

        AuthResult result = new AuthResult
        {
            ok = false,
            error = ""
        };

        username = NormalizeInput(username);

        if (string.IsNullOrWhiteSpace(username) ||
            string.IsNullOrWhiteSpace(oldPassword) ||
            string.IsNullOrWhiteSpace(newPassword))
        {
            result.error = "CHANGE_PASSWORD_FIELDS_EMPTY";
            return result;
        }

        try
        {
            ChangePasswordReqPayload plain = new ChangePasswordReqPayload
            {
                username = username,
                oldPassword = oldPassword,
                newPassword = newPassword
            };

            string plainJson = JsonUtility.ToJson(plain);

            string encryptedPayload = ClientCrypto.RsaEncryptJsonWithPublicPem(
                GetAsPublicKeyPem(),
                plainJson
            );

            ProtocolMessage req = new ProtocolMessage
            {
                type = "CHANGE_PASSWORD_REQ",
                clientId = AuthSession.Ctx.clientId,
                payload = encryptedPayload
            };

            ProtocolMessage rep = await SendRequestAsync(
                asUrl,
                req,
                "CHANGE_PASSWORD_REP"
            );

            if (rep == null)
            {
                result.error = "CHANGE_PASSWORD_NO_RESPONSE";
                return result;
            }

            if (rep.type == "ERROR")
            {
                result.error = rep.error;
                return result;
            }

            ChangePasswordRepPayload payload = SafeFromJson<ChangePasswordRepPayload>(rep.payload);

            if (payload == null)
            {
                result.error = "CHANGE_PASSWORD_BAD_PAYLOAD";
                return result;
            }

            result.ok = payload.ok;
            result.error = payload.error ?? "";

            if (result.ok)
                AuthSession.Ctx.ClearTicketsAndSession();

            DebugAuth($"CHANGE_PASSWORD ok={result.ok}, error={result.error}");

            return result;
        }
        catch (Exception ex)
        {
            result.error = ex.Message;
            Debug.LogError($"[AuthClient] ChangePasswordAsync failed: {ex}");
            return result;
        }
    }

    // ============================================================
    // TGS_REQ
    // ============================================================

    public async Task<TicketResult> RequestGsTicketAsync()
    {
        return await RequestGsTicketAsync(gsServiceName);
    }

    public async Task<TicketResult> RequestGsTicketAsync(string serviceName)
    {
        TicketResult result = new TicketResult
        {
            ok = false,
            error = ""
        };

        AuthContext ctx = AuthSession.Ctx;

        if (!AuthSession.EnsureExists().ValidateTgtReady())
        {
            result.error = "TGT_OR_KCTGS_MISSING";
            return result;
        }

        serviceName = string.IsNullOrWhiteSpace(serviceName)
            ? gsServiceName
            : serviceName.Trim();

        try
        {
            byte[] kcTgs = ctx.KcTgsBytes;

            string authNonce = ClientCrypto.GenerateNonce();
            string payloadNonce = ClientCrypto.GenerateNonce();

            TgsAuthPayload authPlain = new TgsAuthPayload
            {
                type = "TGS_REQ",
                ts = ClientCrypto.NowMs(),
                nonce = authNonce
            };

            TgsReqPayload payloadPlain = new TgsReqPayload
            {
                type = "TGS_REQ",
                service = serviceName,
                nonce = payloadNonce
            };

            string authJson = JsonUtility.ToJson(authPlain);
            string payloadJson = JsonUtility.ToJson(payloadPlain);

            string encryptedAuth = ClientCrypto.DesEncryptJson(kcTgs, authJson);
            string encryptedPayload = ClientCrypto.DesEncryptJson(kcTgs, payloadJson);

            ProtocolMessage req = new ProtocolMessage
            {
                type = "TGS_REQ",
                clientId = ctx.clientId,
                ticket = ctx.tgt,
                auth = encryptedAuth,
                payload = encryptedPayload
            };

            ProtocolMessage rep = await SendRequestAsync(
                tgsUrl,
                req,
                "TGS_REP"
            );

            if (rep == null)
            {
                result.error = "TGS_NO_RESPONSE";
                return result;
            }

            if (rep.type == "ERROR")
            {
                result.error = rep.error;
                return result;
            }

            if (string.IsNullOrWhiteSpace(rep.ticket))
            {
                result.error = "TGS_SERVICE_TICKET_MISSING";
                return result;
            }

            if (string.IsNullOrWhiteSpace(rep.payload))
            {
                result.error = "TGS_PAYLOAD_MISSING";
                return result;
            }

            string protectedJson = ClientCrypto.DesDecryptJson(kcTgs, rep.payload);
            TgsRepProtectedPayload protectedPayload =
                SafeFromJson<TgsRepProtectedPayload>(protectedJson);

            if (protectedPayload == null)
            {
                result.error = "TGS_BAD_PAYLOAD";
                return result;
            }

            if (protectedPayload.nonce != payloadNonce)
            {
                result.error = "TGS_NONCE_MISMATCH";
                return result;
            }

            if (string.IsNullOrWhiteSpace(protectedPayload.kcGs))
            {
                result.error = "TGS_KCGS_MISSING";
                return result;
            }

            ClientCrypto.RequireDesKeyBase64(protectedPayload.kcGs, "KcGs");

            result.ok = true;
            result.serviceTicket = rep.ticket;
            result.kcGs = protectedPayload.kcGs;
            result.exp = protectedPayload.exp;
            result.error = "";

            AuthSession.EnsureExists().ApplyTgsTicket(
                serviceTicket: result.serviceTicket,
                kcGs: result.kcGs,
                expMs: result.exp
            );

            DebugAuth(
                $"TGS ok service={serviceName}, serviceTicket=set, kcGs=set, exp={result.exp}"
            );

            return result;
        }
        catch (Exception ex)
        {
            result.error = ex.Message;
            Debug.LogError($"[AuthClient] RequestGsTicketAsync failed: {ex}");
            return result;
        }
    }

    // ============================================================
    // Combined flow
    // ============================================================

    public async Task<AuthResult> FullLoginToTicketAsync(string username, string password)
    {
        LoginResult login = await LoginAsync(username, password);

        if (!login.ok)
        {
            return new AuthResult
            {
                ok = false,
                error = login.error
            };
        }

        TicketResult ticket = await RequestGsTicketAsync();

        if (!ticket.ok)
        {
            return new AuthResult
            {
                ok = false,
                error = ticket.error
            };
        }

        return new AuthResult
        {
            ok = true,
            error = ""
        };
    }

    // 兼容旧 UI 可能已经绑定 FullLoginToGsAsync。
    // 注意：这一版 AuthClient 只跑到 TGS。
    // 正式 GS_AUTH 下一步由 RelayChatClient 执行。
    public async Task<AuthResult> FullLoginToGsAsync(
        string username,
        string password,
        RelayChatClient relayClient
    )
    {
        AuthResult ticketResult = await FullLoginToTicketAsync(username, password);

        if (!ticketResult.ok)
            return ticketResult;

        return new AuthResult
        {
            ok = false,
            error = "GS_AUTH_PENDING_RELAY_REWRITE"
        };
    }

    // 给下一步 RelayChatClient 用：构造正式 GS_AUTH 消息。
    public ProtocolMessage BuildGsAuthMessage()
    {
        AuthContext ctx = AuthSession.Ctx;

        if (!AuthSession.EnsureExists().ValidateGsTicketReady())
            throw new InvalidOperationException("ServiceTicket/KcGs not ready.");

        byte[] kcGs = ctx.KcGsBytes;

        string authJson = JsonUtility.ToJson(new GsAuthPayload
        {
            ts = ClientCrypto.NowMs(),
            nonce = ClientCrypto.GenerateNonce()
        });

        string encryptedAuth = ClientCrypto.DesEncryptJson(kcGs, authJson);

        return new ProtocolMessage
        {
            type = "GS_AUTH",
            clientId = ctx.clientId,
            ticket = ctx.serviceTicket,
            auth = encryptedAuth
        };
    }

    // ============================================================
    // Request helper
    // ============================================================

    private async Task<ProtocolMessage> SendRequestAsync(
        string url,
        ProtocolMessage request,
        string expectedResponseType
    )
    {
        if (string.IsNullOrWhiteSpace(url))
        {
            Debug.LogError("[AuthClient] SendRequestAsync failed: url empty.");
            return null;
        }

        TaskCompletionSource<ProtocolMessage> tcs =
            new TaskCompletionSource<ProtocolMessage>();

        WebSocket socket = new WebSocket(url);
        tempSockets.Add(socket);

        socket.OnOpen += () =>
        {
            DebugAuth($"OPEN {url}, type={request.type}, expect={expectedResponseType}");
        };

        socket.OnMessage += (bytes) =>
        {
            string text = Encoding.UTF8.GetString(bytes);

            DebugAuth($"RECV RAW {text}");

            try
            {
                ProtocolMessage msg = JsonUtility.FromJson<ProtocolMessage>(text);

                if (msg == null)
                    return;

                if (msg.type == expectedResponseType || msg.type == "ERROR")
                    tcs.TrySetResult(msg);
            }
            catch (Exception ex)
            {
                tcs.TrySetException(ex);
            }
        };

        socket.OnError += (errorMsg) =>
        {
            Debug.LogError($"[AuthClient] SOCKET ERROR {url}: {errorMsg}");
            tcs.TrySetException(new Exception(errorMsg));
        };

        socket.OnClose += (code) =>
        {
            DebugAuth($"CLOSE {url}, code={code}");

            if (!tcs.Task.IsCompleted)
                tcs.TrySetException(new Exception($"Socket closed before response. code={code}"));
        };

        try
        {
            DebugAuth($"CONNECT {url}");

            // NativeWebSocket 在 Unity 下有时 OnOpen 已触发，
            // 但 await socket.Connect() 后续不继续执行。
            // 所以这里不 await Connect，而是轮询 State。
            _ = socket.Connect();

            bool opened = await WaitUntilSocketOpen(socket, requestTimeoutMs);

            if (!opened)
                throw new TimeoutException($"Socket open timeout after {requestTimeoutMs}ms");

            string json = JsonUtility.ToJson(request);

            DebugAuth($"SEND {json}");

            await socket.SendText(json);

            ProtocolMessage response = await WaitWithTimeout(
                tcs.Task,
                requestTimeoutMs
            );

            return response;
        }
        catch (Exception ex)
        {
            Debug.LogError(
                $"[AuthClient] Request failed type={request.type}, url={url}, error={ex.Message}"
            );

            return new ProtocolMessage
            {
                type = "ERROR",
                error = ex.Message
            };
        }
        finally
        {
            try
            {
                if (socket.State == WebSocketState.Open ||
                    socket.State == WebSocketState.Connecting)
                {
                    await socket.Close();
                }
            }
            catch
            {
                // ignore
            }

            tempSockets.Remove(socket);
        }
    }

    private async Task<bool> WaitUntilSocketOpen(WebSocket socket, int timeoutMs)
    {
        int elapsed = 0;

        while (elapsed < timeoutMs)
        {
            if (socket == null)
                return false;

            if (socket.State == WebSocketState.Open)
                return true;

            await Task.Delay(50);
            elapsed += 50;
        }

        return socket != null && socket.State == WebSocketState.Open;
    }

    private async Task<ProtocolMessage> WaitWithTimeout(
        Task<ProtocolMessage> task,
        int timeoutMs
    )
    {
        Task timeoutTask = Task.Delay(timeoutMs);
        Task finished = await Task.WhenAny(task, timeoutTask);

        if (finished == timeoutTask)
            throw new TimeoutException($"Request timeout after {timeoutMs}ms");

        return await task;
    }

    private T SafeFromJson<T>(string json) where T : class
    {
        if (string.IsNullOrWhiteSpace(json))
            return null;

        try
        {
            return JsonUtility.FromJson<T>(json);
        }
        catch (Exception ex)
        {
            Debug.LogError($"[AuthClient] Json parse failed: {ex.Message}\nJson={json}");
            return null;
        }
    }

    private string NormalizeInput(string value)
    {
        return string.IsNullOrWhiteSpace(value) ? "" : value.Trim();
    }

    private void DebugAuth(string message)
    {
        if (!debugLog)
            return;

        Debug.Log("[AuthClient] " + message);
    }

    // ============================================================
    // Context menu test helpers
    // ============================================================

    [ContextMenu("Debug Register TestUser")]
    private async void DebugRegisterTestUser()
    {
        RegisterResult result = await RegisterAsync("testuser", "TestUser123");

        Debug.Log(
            $"[AuthClient] DebugRegister ok={result.ok}, " +
            $"userId={result.userId}, error={result.error}"
        );
    }

    [ContextMenu("Debug Login To Ticket TestUser")]
    private async void DebugLoginToTicketTestUser()
    {
        AuthResult result = await FullLoginToTicketAsync("testuser", "TestUser123");

        Debug.Log(
            $"[AuthClient] DebugLoginToTicket ok={result.ok}, error={result.error}"
        );
    }
}