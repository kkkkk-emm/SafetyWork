using System;
using System.Text;
using System.Threading.Tasks;
using NativeWebSocket;
using UnityEngine;
using UnityEngine.SceneManagement;

public class RelayChatClient : MonoBehaviour
{
    public static RelayChatClient Instance { get; private set; }

    [Header("连接配置")]
    [SerializeField] private string serverUrl = "ws://127.0.0.1:8765";

    [Tooltip("房间身份，例如 Client1 / Client2。最终以 ROOM_STATE 返回为准。")]
    [SerializeField] private string clientId = "";

    [SerializeField] private string roomId = "";

    [Header("自动流程")]
    [SerializeField] private bool autoConnect = false;
    [SerializeField] private bool autoJoin = false;
    [SerializeField] private bool requireGsAuth = true;

    [Tooltip("建议保持 false。GS_AUTH 统一由 ConnectAndAuthenticateGs() 触发。")]
    [SerializeField] private bool autoAuthenticateGs = false;

    [Header("调试")]
    [SerializeField] private bool debugNetworkLog = true;
    [SerializeField] private int logEveryNInputs = 10;
    [SerializeField] private int gsAuthTimeoutMs = 5000;

    [Header("Network Simulation")]
    [SerializeField] private bool simulateNetwork = false;
    [SerializeField] private int outgoingDelayMs = 120;
    [SerializeField] private int incomingDelayMs = 120;
    [SerializeField] private int jitterMs = 20;
    [SerializeField, Range(0f, 1f)] private float outgoingDropRate = 0f;
    [SerializeField, Range(0f, 1f)] private float incomingDropRate = 0f;
    [Header("Payload 加密策略")]
    [SerializeField] private bool encryptInputPayload = false;
    public string ClientId => clientId;
    public string RoomId => roomId;

    public bool IsConnected =>
        websocket != null && websocket.State == WebSocketState.Open;

    public bool HasJoinedRoom => hasJoinedRoom;

    public bool IsGsAuthenticated =>
        AuthSession.Ctx.HasGsSession;

    public bool CanSendGameplayMessages =>
        IsConnected &&
        (!requireGsAuth || IsGsAuthenticated) &&
        hasJoinedRoom;

    public event Action<RoomStatePayload> OnRoomStateReceived;
    public event Action<GameStartPayload> OnGameStartReceived;

    private WebSocket websocket;
    private bool hasJoinedRoom;
    private bool gsAuthInFlight;


    private bool reconnectInFlight;
    private bool reconnectOk;
    private string reconnectError;
    private int sentInputCount;
    private int latestAppliedAck = -1;
    private int latestAppliedTick = -1;
    private bool forceApplyNextSnapshot;
    private bool gameOverHandledFromSnapshot = false;
    private bool waitingFreshSnapshotAfterReconnect;
    // ============================================================
    // Message / Payload classes
    // ============================================================

    [Serializable]
    private class NetMessage
    {
        public string type;
        public string clientId;
        public string sessionId;
        public string roomId;
        public string ticket;
        public string auth;
        public string payload;
        public string error;
        public bool payloadEncrypted;
        public string targetId;
        public string fromClientId;
        public string text;
        public string timestamp;
    }

    [Serializable]
    private class GsAuthPayload
    {
        public long ts;
        public string nonce;
    }

    [Serializable]
    private class GsAuthOkPayload
    {
        public bool ok;
        public string clientId;
        public string sessionId;
        public long ts;
        public string nonce;
        public long exp;
        public string error;
    }

    [Serializable]
    private class RoomAuthPayload
    {
        public string type;
        public string sessionId;
        public string roomId;
        public long ts;
        public string nonce;
    }

    [Serializable]
    private class ReadyEncryptedPayload
    {
        public string type;
        public string sessionId;
        public string roomId;
        public bool ready;
        public long ts;
        public string nonce;
    }

    [Serializable]
    private class ChatPayload
    {
        public string text;
    }

    [Serializable]
    private class EncryptedInputPayload
    {
        public string type;
        public string sessionId;
        public string roomId;
        public string clientId;
        public long ts;
        public string nonce;

        public int seq;
        public int tick;

        public float moveX;

        public bool jumpPressed;
        public bool downHeld;
        public bool dropPressed;

        public bool attackPressed;
        public bool attackHeld;
        public bool attackReleased;

        public float aimX;
        public float aimY;

        public string clientState;
        public bool clientGrounded;
        public int clientJumpCount;

        public float clientPosX;
        public float clientPosY;
        public float clientVelX;
        public float clientVelY;

        public string equippedWeaponId;
        public string[] equippedEffectIds;
    }
    [Serializable]
    private class ReconnectAuthPayload
    {
        public string type;
        public string clientId;
        public string sessionId;
        public string roomId;
        public long ts;
        public string nonce;
    }

    [Serializable]
    private class ReconnectPayload
    {
        public string type;
        public string clientId;
        public string sessionId;
        public string roomId;
        public string nonce;
        public int lastProcessedSeq;
        public long ts;
    }

    [Serializable]
    private class ReconnectRepPayload
    {
        public string type;
        public bool ok;
        public string sessionId;
        public string roomId;
        public string phase;
        public int lastProcessedSeq;
        public long ts;
        public string nonce;
    }

    // ============================================================
    // Unity lifecycle
    // ============================================================

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    private void Start()
    {
        ApplyNetworkSessionToLocalFields();

        Debug.Log(
            $"[RelayChatClient] Start object={gameObject.name}, " +
            $"clientId={clientId}, roomId={roomId}, " +
            $"autoConnect={autoConnect}, autoJoin={autoJoin}, " +
            $"requireGsAuth={requireGsAuth}, autoAuthenticateGs={autoAuthenticateGs}"
        );

        if (autoConnect)
            _ = Connect();
    }

    private void Update()
    {
#if !UNITY_WEBGL || UNITY_EDITOR
        websocket?.DispatchMessageQueue();
#endif
    }

    private async void OnApplicationQuit()
    {
        await Disconnect();
    }

    // ============================================================
    // Identity
    // ============================================================

    private void ApplyNetworkSessionToLocalFields()
    {
        if (NetworkSession.Instance == null)
            return;

        if (!string.IsNullOrWhiteSpace(NetworkSession.Instance.serverUrl))
            serverUrl = NetworkSession.Instance.serverUrl;

        if (!string.IsNullOrWhiteSpace(NetworkSession.Instance.roomId))
            roomId = NetworkSession.Instance.roomId;

        if (!string.IsNullOrWhiteSpace(NetworkSession.Instance.clientId))
            clientId = NetworkSession.Instance.clientId;
    }

    public void ConfigureIdentity(string newServerUrl, string newClientId, string newRoomId)
    {
        if (!string.IsNullOrWhiteSpace(newServerUrl))
            serverUrl = newServerUrl.Trim();

        if (newClientId != null)
            clientId = newClientId.Trim();

        if (newRoomId != null)
            roomId = newRoomId.Trim().ToUpper();

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[RelayChatClient] ConfigureIdentity " +
                $"server={serverUrl}, client={clientId}, room={roomId}"
            );
        }
    }

    // ============================================================
    // Connect / Auth
    // ============================================================

    public async Task Connect()
    {
        if (websocket != null &&
            (websocket.State == WebSocketState.Open ||
             websocket.State == WebSocketState.Connecting))
        {
            if (debugNetworkLog)
                Debug.LogWarning($"[{clientId}] WebSocket 已连接或正在连接中。");

            return;
        }

        ApplyNetworkSessionToLocalFields();

        websocket = new WebSocket(serverUrl);

        websocket.OnOpen += () =>
        {
            Debug.Log(
                $"[{clientId}] WebSocket OPEN server={serverUrl}, " +
                $"authClientId={AuthSession.Ctx.clientId}, " +
                $"sessionId={AuthSession.Ctx.sessionId}"
            );
        };

        websocket.OnError += (errorMsg) =>
        {
            Debug.LogError($"[{clientId}] WebSocket 错误: {errorMsg}");
        };

        websocket.OnClose += (closeCode) =>
        {
            Debug.LogWarning($"[{clientId}] 连接已关闭，code={closeCode}");
            hasJoinedRoom = false;
        };

        websocket.OnMessage += (bytes) =>
        {
            string text = Encoding.UTF8.GetString(bytes);
            HandleIncomingMessage(text);
        };

        Debug.Log($"[{clientId}] WebSocket CONNECTING server={serverUrl}");

        _ = websocket.Connect();

        await WaitUntilSocketOpen();

        // 重要：Connect 只负责连接。
        // 不在这里自动 SendGsAuth，避免重复 GS_AUTH。
    }

    public async Task<bool> ConnectAndAuthenticateGs()
    {
        await EnsureConnected();

        if (!EnsureSocketOpen())
            return false;

        if (AuthSession.Ctx.HasGsSession)
        {
            if (debugNetworkLog)
            {
                Debug.Log(
                    $"[RelayChatClient] GS already authenticated, " +
                    $"sessionId={AuthSession.Ctx.sessionId}"
                );
            }

            return true;
        }

        await SendGsAuth();

        bool ok = await WaitUntilGsAuthenticated(gsAuthTimeoutMs);

        if (!ok)
        {
            Debug.LogError(
                "[RelayChatClient] GS_AUTH timeout: " +
                "没有在限定时间内收到 GS_AUTH_OK / sessionId。"
            );
        }

        return ok;
    }

    private async Task<bool> WaitUntilGsAuthenticated(int timeoutMs)
    {
        int elapsed = 0;

        while (elapsed < timeoutMs)
        {
            if (AuthSession.Ctx.HasGsSession)
                return true;

            await Task.Delay(50);
            elapsed += 50;
        }

        return AuthSession.Ctx.HasGsSession;
    }

    public async Task SendGsAuth()
    {
        if (AuthSession.Ctx.HasGsSession)
        {
            if (debugNetworkLog)
            {
                Debug.Log(
                    $"[RelayChatClient] 已经有 sessionId，跳过重复 GS_AUTH。 " +
                    $"sessionId={AuthSession.Ctx.sessionId}"
                );
            }

            return;
        }

        if (gsAuthInFlight)
        {
            if (debugNetworkLog)
                Debug.Log("[RelayChatClient] GS_AUTH 正在进行中，跳过重复发送。");

            return;
        }

        gsAuthInFlight = true;

        try
        {
            await EnsureConnected();

            if (!EnsureSocketOpen())
                return;

            if (!AuthSession.EnsureExists().ValidateGsTicketReady())
            {
                Debug.LogError("[RelayChatClient] GS_AUTH 失败：ServiceTicket/KcGs 未准备好。");
                return;
            }

            AuthContext ctx = AuthSession.Ctx;
            byte[] kcGs = ctx.KcGsBytes;

            string authJson = JsonUtility.ToJson(new GsAuthPayload
            {
                ts = ClientCrypto.NowMs(),
                nonce = ClientCrypto.GenerateNonce()
            });

            string encryptedAuth = ClientCrypto.DesEncryptJson(kcGs, authJson);

            var msg = new NetMessage
            {
                type = "GS_AUTH",
                clientId = ctx.clientId,
                ticket = ctx.serviceTicket,
                auth = encryptedAuth,
                payload = ""
            };

            await SendJson(msg, bypassSimulation: true);

            if (debugNetworkLog)
            {
                Debug.Log(
                    $"[RelayChatClient] SEND GS_AUTH " +
                    $"authClientId={ctx.clientId}, ticket=set, kcGs=set"
                );
            }
        }
        finally
        {
            gsAuthInFlight = false;
        }
    }

    private async Task EnsureConnected()
    {
        if (websocket != null && websocket.State == WebSocketState.Open)
            return;

        if (websocket != null && websocket.State == WebSocketState.Connecting)
        {
            await WaitUntilSocketOpen();
            return;
        }

        await Connect();
        await WaitUntilSocketOpen();
    }

    private async Task WaitUntilSocketOpen(int timeoutMs = 5000)
    {
        int elapsed = 0;

        while (websocket != null &&
               websocket.State != WebSocketState.Open &&
               elapsed < timeoutMs)
        {
            await Task.Delay(50);
            elapsed += 50;
        }

        if (websocket == null || websocket.State != WebSocketState.Open)
        {
            Debug.LogWarning($"[{clientId}] WebSocket 等待 Open 超时，当前状态={websocket?.State}");
        }
    }

    public async Task ResetConnectionForNewLogin()
    {
        await Disconnect();

        hasJoinedRoom = false;
        clientId = "";
        roomId = "";

        sentInputCount = 0;
        latestAppliedAck = -1;
        latestAppliedTick = -1;
        gsAuthInFlight = false;

        if (debugNetworkLog)
            Debug.Log("[RelayChatClient] ResetConnectionForNewLogin done.");
    }

    // ============================================================
    // Room APIs
    // ============================================================

    public async Task SendCreateRoom()
    {
        await EnsureConnectedAndAuthed();

        if (!EnsureSocketOpen())
            return;

        if (requireGsAuth && !AuthSession.Ctx.HasGsSession)
        {
            Debug.LogWarning("[RelayChatClient] ROOM_CREATE_REQ 失败：尚未 GS_AUTH。");
            return;
        }

        roomId = "";
        clientId = "";
        hasJoinedRoom = false;

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.ClearRoom();

        string encryptedAuth = EncryptRoomAuth("ROOM_CREATE_REQ", "");

        var msg = new NetMessage
        {
            type = "ROOM_CREATE_REQ",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = "",
            auth = encryptedAuth,
            payload = ""
        };

        await SendJson(msg, bypassSimulation: false);

        if (debugNetworkLog)
            Debug.Log("[RelayChatClient] SEND ROOM_CREATE_REQ");
    }

    public async Task SendJoinRoomManual(string wantedClientId, string wantedRoomId)
    {
        await EnsureConnectedAndAuthed();

        if (!EnsureSocketOpen())
            return;

        if (requireGsAuth && !AuthSession.Ctx.HasGsSession)
        {
            Debug.LogWarning("[RelayChatClient] ROOM_JOIN_REQ 失败：尚未 GS_AUTH。");
            return;
        }

        if (wantedClientId != null)
            clientId = wantedClientId.Trim();

        if (wantedRoomId != null)
            roomId = wantedRoomId.Trim().ToUpper();

        if (string.IsNullOrWhiteSpace(roomId))
        {
            Debug.LogWarning($"[{clientId}] ROOM_JOIN_REQ 失败：roomId 为空。");
            return;
        }

        string encryptedAuth = EncryptRoomAuth("ROOM_JOIN_REQ", roomId);

        var msg = new NetMessage
        {
            type = "ROOM_JOIN_REQ",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            auth = encryptedAuth,
            payload = ""
        };

        await SendJson(msg, bypassSimulation: false);

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[{clientId}] SEND ROOM_JOIN_REQ room={roomId}, " +
                $"requestedClient={clientId}, sessionId={AuthSession.Ctx.sessionId}"
            );
        }
    }

    public async Task SendReady(bool ready)
    {
        await EnsureConnectedAndAuthed();

        if (!EnsureSocketOpen())
            return;

        if (string.IsNullOrWhiteSpace(roomId))
        {
            Debug.LogWarning($"[{clientId}] ROOM_READY_REQ 失败：roomId 为空。");
            return;
        }

        var payload = new ReadyEncryptedPayload
        {
            type = "ROOM_READY_REQ",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            ready = ready,
            ts = ClientCrypto.NowMs(),
            nonce = ClientCrypto.GenerateNonce()
        };

        string encryptedPayload = EncryptWithKcGs(payload);

        var msg = new NetMessage
        {
            type = "ROOM_READY_REQ",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            payload = encryptedPayload
        };

        await SendJson(msg, bypassSimulation: false);

        if (debugNetworkLog)
            Debug.Log($"[{clientId}] SEND ROOM_READY_REQ ready={ready}");
    }

    public async Task SendStartGame()
    {
        await EnsureConnectedAndAuthed();

        if (!EnsureSocketOpen())
            return;

        if (string.IsNullOrWhiteSpace(roomId))
        {
            Debug.LogWarning($"[{clientId}] ROOM_START_REQ 失败：roomId 为空。");
            return;
        }

        string encryptedAuth = EncryptRoomAuth("ROOM_START_REQ", roomId);

        var msg = new NetMessage
        {
            type = "ROOM_START_REQ",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            auth = encryptedAuth,
            payload = ""
        };

        await SendJson(msg, bypassSimulation: false);

        if (debugNetworkLog)
            Debug.Log($"[{clientId}] SEND ROOM_START_REQ room={roomId}");
    }

    public async Task LeaveRoom()
    {
        string leavingRoomId = roomId;

        if (!EnsureSocketOpen())
        {
            ClearLocalRoomState();
            ClearGsSessionForRenew();
            return;
        }

        if (string.IsNullOrWhiteSpace(leavingRoomId))
        {
            ClearLocalRoomState();
            ClearGsSessionForRenew();
            return;
        }

        if (string.IsNullOrWhiteSpace(AuthSession.Ctx.sessionId))
        {
            Debug.LogWarning("[RelayChatClient] LEAVE_ROOM skipped: sessionId empty.");

            ClearLocalRoomState();
            ClearGsSessionForRenew();
            return;
        }

        string encryptedAuth = EncryptRoomAuth("LEAVE_ROOM", leavingRoomId);

        var leave = new NetMessage
        {
            type = "LEAVE_ROOM",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = leavingRoomId,
            auth = encryptedAuth,
            payload = ""
        };

        await SendJson(leave, bypassSimulation: false);

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[{clientId}] SEND LEAVE_ROOM " +
                $"room={leavingRoomId}, sessionId={AuthSession.Ctx.sessionId}"
            );
        }

        ClearLocalRoomState();

        // 关键：主动 Back / 取消房间后，不再复用旧 GS sessionId。
        // 下次创建/加入房间时，让 EnsureGsReady() 重新 GS_AUTH。
        ClearGsSessionForRenew();
    }
    private void ClearGsSessionForRenew()
    {
        AuthSession.EnsureExists();

        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null)
        {
            Debug.LogWarning("[RelayChatClient] ClearGsSessionForRenew failed: AuthSession.Ctx is null.");
            return;
        }

        string oldSessionId = ctx.sessionId;

        // 只清 GS session，不清 serviceTicket / kcGs
        // 这样下次还能用现有登录票据重新 GS_AUTH
        ctx.sessionId = "";
        ctx.gsSessionExpireAtMs = 0;

        gsAuthInFlight = false;

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.ApplyGsSession("");

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[RelayChatClient] ClearGsSessionForRenew oldSessionId={oldSessionId}"
            );
        }

        AuthSessionPersistence.Save();
    }
    public async Task SendChat(string messageText)
    {
        if (string.IsNullOrWhiteSpace(messageText))
        {
            Debug.LogWarning($"[{clientId}] CHAT 内容为空，已忽略。");
            return;
        }

        if (!EnsureSocketOpen())
            return;

        if (!hasJoinedRoom)
        {
            Debug.LogWarning($"[{clientId}] 尚未加入房间，无法发送 CHAT。");
            return;
        }

        var payload = new ChatPayload
        {
            text = messageText
        };

        var chat = new NetMessage
        {
            type = "CHAT",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            payload = JsonUtility.ToJson(payload)
        };

        await SendJson(chat, bypassSimulation: false);

        if (debugNetworkLog)
            Debug.Log($"[{clientId}] SEND CHAT -> Server: {messageText}");
    }

    private async Task EnsureConnectedAndAuthed()
    {
        await EnsureConnected();

        if (!EnsureSocketOpen())
            return;

        if (requireGsAuth && !AuthSession.Ctx.HasGsSession)
        {
            if (AuthSession.Ctx.HasServiceTicket)
                await SendGsAuth();
            else
                Debug.LogWarning("[RelayChatClient] 缺少 ServiceTicket/KcGs，无法自动 GS_AUTH。");
        }
    }

    // ============================================================
    // Input
    // ============================================================

    public async Task SendInput(PlayerInputCmd cmd)
    {
        if (!EnsureSocketOpen())
            return;

        if (!hasJoinedRoom)
            return;

        if (requireGsAuth && !AuthSession.Ctx.HasGsSession)
            return;

        var payload = new EncryptedInputPayload
        {
            type = "INPUT",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            clientId = clientId,
            ts = ClientCrypto.NowMs(),
            nonce = ClientCrypto.GenerateNonce(),

            seq = cmd.seq,
            tick = cmd.tick,

            moveX = cmd.moveX,

            jumpPressed = cmd.jumpPressed,
            downHeld = cmd.downHeld,
            dropPressed = cmd.dropPressed,

            attackPressed = cmd.attackPressed,
            attackHeld = cmd.attackHeld,
            attackReleased = cmd.attackReleased,

            aimX = cmd.aimX,
            aimY = cmd.aimY,

            clientState = cmd.clientState,
            clientGrounded = cmd.clientGrounded,
            clientJumpCount = cmd.clientJumpCount,

            clientPosX = cmd.clientPosX,
            clientPosY = cmd.clientPosY,
            clientVelX = cmd.clientVelX,
            clientVelY = cmd.clientVelY,

            equippedWeaponId = cmd.equippedWeaponId,
            equippedEffectIds = cmd.equippedEffectIds
        };

        // 高频 INPUT 默认明文，避免每帧 DES 加密/解密导致延迟。
        // 如果以后要演示 INPUT 加密，可以把这个改成 true。
        bool payloadEncrypted = encryptInputPayload;

        string payloadText;

        if (payloadEncrypted)
        {
            payloadText = EncryptWithKcGs(payload);
        }
        else
        {
            payloadText = JsonUtility.ToJson(payload);
        }

        var msg = new NetMessage
        {
            type = "INPUT",
            sessionId = AuthSession.Ctx.sessionId,
            roomId = roomId,
            payloadEncrypted = payloadEncrypted,
            payload = payloadText
        };

        sentInputCount++;

        if (debugNetworkLog &&
            (sentInputCount == 1 || sentInputCount % Mathf.Max(1, logEveryNInputs) == 0))
        {
            Debug.Log(
                $"[{clientId}] SEND INPUT #{sentInputCount} " +
                $"seq={cmd.seq} tick={cmd.tick} " +
                $"payloadEncrypted={payloadEncrypted} " +
                $"payloadLen={payloadText.Length}"
            );
        }

        await SendJson(msg, bypassSimulation: false);
    }

    // ============================================================
    // Disconnect / send helpers
    // ============================================================

    public async Task Disconnect()
    {
        if (websocket == null)
            return;

        if (websocket.State == WebSocketState.Open ||
            websocket.State == WebSocketState.Connecting)
        {
            await websocket.Close();
        }

        websocket = null;
        hasJoinedRoom = false;

        if (debugNetworkLog)
            Debug.Log($"[{clientId}] 已执行 Disconnect。");
    }

    private async Task SendJson(NetMessage message, bool bypassSimulation)
    {
        if (websocket == null)
        {
            Debug.LogWarning($"[{clientId}] websocket 为空，发送失败。");
            return;
        }

        string json = JsonUtility.ToJson(message);

        if (debugNetworkLog)
            Debug.Log($"[{clientId}] SEND RAW {json}");

        if (bypassSimulation || !simulateNetwork)
        {
            await SafeSendText(json);
            return;
        }

        if (UnityEngine.Random.value < outgoingDropRate)
        {
            if (debugNetworkLog)
                Debug.LogWarning($"[{clientId}] [NETSIM] OUT DROP type={message.type}");

            return;
        }

        int delay = GetSimulatedDelay(outgoingDelayMs, jitterMs);

        if (delay > 0)
        {
            if (debugNetworkLog)
                Debug.Log($"[{clientId}] [NETSIM] OUT delay={delay}ms type={message.type}");

            await Task.Delay(delay);
        }

        await SafeSendText(json);
    }

    private async Task SafeSendText(string json)
    {
        if (websocket == null || websocket.State != WebSocketState.Open)
        {
            Debug.LogWarning($"[{clientId}] 发送时 WebSocket 不可用。");
            return;
        }

        await websocket.SendText(json);
    }

    private bool EnsureSocketOpen()
    {
        if (websocket == null || websocket.State != WebSocketState.Open)
        {
            Debug.LogWarning($"[{clientId}] WebSocket 未连接，当前状态不可发送。");
            return false;
        }

        return true;
    }

    // ============================================================
    // Crypto helpers
    // ============================================================

    private string EncryptRoomAuth(string type, string targetRoomId)
    {
        var payload = new RoomAuthPayload
        {
            type = type,
            sessionId = AuthSession.Ctx.sessionId,
            roomId = targetRoomId ?? "",
            ts = ClientCrypto.NowMs(),
            nonce = ClientCrypto.GenerateNonce()
        };

        return EncryptWithKcGs(payload);
    }

    private string EncryptWithKcGs(object payloadObj)
    {
        if (!AuthSession.EnsureExists().ValidateGsTicketReady())
            throw new InvalidOperationException("KcGs not ready.");

        string json = JsonUtility.ToJson(payloadObj);
        return ClientCrypto.DesEncryptJson(AuthSession.Ctx.KcGsBytes, json);
    }

    private string DecryptWithKcGs(string encryptedPayload, string label)
    {
        if (string.IsNullOrWhiteSpace(encryptedPayload))
            throw new ArgumentException($"{label} payload empty.");

        if (!AuthSession.EnsureExists().ValidateGsTicketReady())
            throw new InvalidOperationException("KcGs not ready.");

        return ClientCrypto.DesDecryptJson(AuthSession.Ctx.KcGsBytes, encryptedPayload);
    }

    // ============================================================
    // Receive
    // ============================================================

    private void HandleIncomingMessage(string json)
    {
        _ = HandleIncomingMessageAsync(json);
    }

    private async Task HandleIncomingMessageAsync(string json)
    {
        if (debugNetworkLog)
            Debug.Log($"[{clientId}] RECV RAW {json}");

        NetMessage msg;

        try
        {
            msg = JsonUtility.FromJson<NetMessage>(json);
        }
        catch (Exception ex)
        {
            Debug.LogError($"[{clientId}] 解析顶层消息失败: {ex.Message}\nRaw={json}");
            return;
        }

        if (msg == null || string.IsNullOrWhiteSpace(msg.type))
            return;

        switch (msg.type)
        {
            case "GS_AUTH_OK":
                HandleGsAuthOk(msg);
                return;
            case "RECONNECT_REP":
                HandleReconnectRep(msg);
                return;
            case "ROOM_CREATE_REP":
                HandleRoomCreateRep(msg);
                return;

            case "ROOM_JOIN_REP":
                HandleRoomJoinRep(msg);
                return;

            case "ROOM_READY_REP":
                HandleRoomReadyRep(msg);
                return;

            case "ROOM_STATE":
                HandleRoomState(msg);
                return;

            case "ROOM_START_REP":
            case "GAME_START":
                HandleRoomStartRep(msg);
                return;

            case "SNAPSHOT":
                await HandleSnapshot(msg);
                return;

            case "RESULT":
                HandleResult(msg);
                return;

            case "SERVER_BROADCAST":
                if (debugNetworkLog)
                    Debug.Log($"[{clientId}] SERVER_BROADCAST from={msg.fromClientId} text={msg.text}");
                return;

            case "ERROR":
                HandleServerError(msg);
                return;

            default:
                if (debugNetworkLog)
                    Debug.Log($"[{clientId}] UNHANDLED MSG type={msg.type}");
                return;
        }
    }

    private void HandleGsAuthOk(NetMessage msg)
    {
        long exp = 0;

        if (!string.IsNullOrWhiteSpace(msg.payload))
        {
            try
            {
                string payloadJson = DecryptWithKcGs(msg.payload, "GS_AUTH_OK");
                GsAuthOkPayload payload = JsonUtility.FromJson<GsAuthOkPayload>(payloadJson);

                if (payload != null)
                    exp = payload.exp;

                if (debugNetworkLog)
                    Debug.Log($"[RelayChatClient] GS_AUTH_OK payload={payloadJson}");
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[RelayChatClient] GS_AUTH_OK payload 解密失败，但继续应用 sessionId: {ex.Message}");
            }
        }

        string newSessionId = !string.IsNullOrWhiteSpace(msg.sessionId)
            ? msg.sessionId
            : AuthSession.Ctx.sessionId;

        AuthSession.EnsureExists().ApplyGsAuthOk(newSessionId, exp);

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.ApplyGsSession(newSessionId);

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[RelayChatClient] RECV GS_AUTH_OK sessionId={newSessionId}, exp={exp}"
            );
        }
        AuthSessionPersistence.Save();
    }
    private void HandleReconnectRep(NetMessage msg)
    {
        try
        {
            string payloadJson = DecryptWithKcGs(msg.payload, "RECONNECT_REP");
            ReconnectRepPayload payload = JsonUtility.FromJson<ReconnectRepPayload>(payloadJson);

            if (debugNetworkLog)
                Debug.Log($"[RelayChatClient] RECONNECT_REP payload={payloadJson}");

            if (payload == null || !payload.ok)
            {
                reconnectError = "RECONNECT_REP_NOT_OK";
                reconnectOk = false;
                return;
            }

            string newSessionId = !string.IsNullOrWhiteSpace(msg.sessionId)
                ? msg.sessionId
                : payload.sessionId;

            string newRoomId = !string.IsNullOrWhiteSpace(msg.roomId)
                ? msg.roomId
                : payload.roomId;

            if (!string.IsNullOrWhiteSpace(newSessionId))
                AuthSession.EnsureExists().ApplyGsAuthOk(newSessionId, payload.ts);

            if (!string.IsNullOrWhiteSpace(newRoomId))
                roomId = newRoomId.Trim().ToUpper();

            AuthContext ctx = AuthSession.Ctx;

            if (!string.IsNullOrWhiteSpace(ctx.localClientId))
                clientId = ctx.localClientId;

            hasJoinedRoom =
                !string.IsNullOrWhiteSpace(roomId) &&
                !string.IsNullOrWhiteSpace(clientId);
            ResetLocalPredictionForReconnect();
            forceApplyNextSnapshot = true;
            if (NetworkSession.Instance != null)
            {
                NetworkSession.Instance.roomId = roomId;
                NetworkSession.Instance.clientId = clientId;
                NetworkSession.Instance.ApplyGsSession(AuthSession.Ctx.sessionId);
            }

            reconnectOk = true;
            reconnectError = "";

            if (debugNetworkLog)
            {
                Debug.Log(
                    $"[RelayChatClient] RECONNECT OK " +
                    $"room={roomId}, client={clientId}, joined={hasJoinedRoom}, " +
                    $"sessionId={AuthSession.Ctx.sessionId}"
                );
            }
        }
        catch (Exception ex)
        {
            reconnectOk = false;
            reconnectError = ex.Message;
            Debug.LogError("[RelayChatClient] RECONNECT_REP parse/decrypt failed: " + ex);
        }
    }
    private void ResetLocalPredictionForReconnect()
    {
        latestAppliedAck = -1;
        latestAppliedTick = -1;
        sentInputCount = 0;

        // 如果你项目里有缓存列表，在这里 Clear：
        // pendingInputs.Clear();
        // snapshotBuffer.Clear();
        // inputHistory.Clear();

        Debug.Log("[RelayChatClient] Reconnect reset local prediction/cache.");
    }
    private void HandleRoomCreateRep(NetMessage msg)
    {
        try
        {
            if (!string.IsNullOrWhiteSpace(msg.payload))
            {
                string payloadJson = DecryptWithKcGs(msg.payload, "ROOM_CREATE_REP");

                if (debugNetworkLog)
                    Debug.Log($"[RelayChatClient] ROOM_CREATE_REP payload={payloadJson}");
            }

            if (!string.IsNullOrWhiteSpace(msg.roomId))
                roomId = msg.roomId.Trim().ToUpper();
            AuthSessionPersistence.Save();
        }
        catch (Exception ex)
        {
            Debug.LogError($"[RelayChatClient] ROOM_CREATE_REP 解密/解析失败: {ex.Message}");
        }
    }

    private void HandleRoomJoinRep(NetMessage msg)
    {
        try
        {
            if (!string.IsNullOrWhiteSpace(msg.payload))
            {
                string payloadJson = DecryptWithKcGs(msg.payload, "ROOM_JOIN_REP");

                if (debugNetworkLog)
                    Debug.Log($"[RelayChatClient] ROOM_JOIN_REP payload={payloadJson}");
            }

            if (!string.IsNullOrWhiteSpace(msg.roomId))
                roomId = msg.roomId.Trim().ToUpper();
        }
        catch (Exception ex)
        {
            Debug.LogError($"[RelayChatClient] ROOM_JOIN_REP 解密/解析失败: {ex.Message}");
        }
    }

    private void HandleRoomReadyRep(NetMessage msg)
    {
        try
        {
            if (!string.IsNullOrWhiteSpace(msg.payload))
            {
                string payloadJson = DecryptWithKcGs(msg.payload, "ROOM_READY_REP");

                if (debugNetworkLog)
                    Debug.Log($"[RelayChatClient] ROOM_READY_REP payload={payloadJson}");
            }
        }
        catch (Exception ex)
        {
            Debug.LogError($"[RelayChatClient] ROOM_READY_REP 解密/解析失败: {ex.Message}");
        }
    }

    private void HandleRoomState(NetMessage msg)
    {
        RoomStatePayload state;

        try
        {
            string payloadJson = DecryptWithKcGs(msg.payload, "ROOM_STATE");
            state = JsonUtility.FromJson<RoomStatePayload>(payloadJson);

            NormalizeRoomState(state);

            if (debugNetworkLog)
                Debug.Log($"[RelayChatClient] ROOM_STATE payload={payloadJson}");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[{clientId}] 解析 ROOM_STATE 失败: {ex.Message}\nPayload={msg.payload}");
            return;
        }

        if (state == null)
            return;

        ApplyRoomStateToClient(state, "ROOM_STATE");
        Debug.Log(
            $"[RelayChatClient] Invoke OnRoomStateReceived " +
            $"room={state.roomId}, local={state.localClientId}, slot={state.localSlotNo}"
        );
        OnRoomStateReceived?.Invoke(state);

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[{clientId}] ROOM_STATE room={state.roomId} " +
                $"localClientId={state.localClientId} " +
                $"slot={state.localSlotNo} " +
                $"isHost={state.localIsHost} " +
                $"hostClientId={state.hostClientId} " +
                $"canStart={state.canStart}"
            );
        }
    }

    private void HandleRoomStartRep(NetMessage msg)
    {
        GameStartPayload start;

        try
        {
            string payloadJson = DecryptWithKcGs(msg.payload, "ROOM_START_REP");
            start = JsonUtility.FromJson<GameStartPayload>(payloadJson);

            NormalizeGameStart(start);

            if (debugNetworkLog)
                Debug.Log($"[RelayChatClient] ROOM_START_REP payload={payloadJson}");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[{clientId}] 解析 ROOM_START_REP 失败: {ex.Message}\nPayload={msg.payload}");
            return;
        }

        if (start == null)
            return;

        ApplyGameStartToClient(start);
        OnGameStartReceived?.Invoke(start);

        string sceneName = string.IsNullOrWhiteSpace(start.sceneName)
            ? "MainGame"
            : start.sceneName;

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[{clientId}] ROOM_START_REP -> LoadScene {sceneName}, " +
                $"sessionClient={NetworkSession.Instance?.clientId}, " +
                $"slot={NetworkSession.Instance?.slotNo}"
            );
        }

        SceneManager.LoadScene(sceneName);
    }

    private async Task HandleSnapshot(NetMessage msg)
    {
        MatchSnapshot snapshot;

        try
        {
            string payloadJson;

            if (msg.payloadEncrypted)
            {
                payloadJson = DecryptWithKcGs(msg.payload, "SNAPSHOT");
            }
            else
            {
                payloadJson = msg.payload;
            }

            snapshot = JsonUtility.FromJson<MatchSnapshot>(payloadJson);
        }
        catch (Exception ex)
        {
            Debug.LogError(
                $"[{clientId}] 解析 SNAPSHOT payload 失败: {ex.Message}\n" +
                $"payloadEncrypted={msg.payloadEncrypted}\n" +
                $"Payload={msg.payload}"
            );
            return;
        }

        if (snapshot == null)
            return;

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[{clientId}] SNAPSHOT RAW tick={snapshot.tick} ack={snapshot.lastProcessedSeq} " +
                $"encrypted={msg.payloadEncrypted} " +
                $"players={(snapshot.players != null ? snapshot.players.Length : 0)} " +
                $"projectiles={(snapshot.projectiles != null ? snapshot.projectiles.Length : 0)} " +
                $"events={(snapshot.events != null ? snapshot.events.Length : 0)} " +
                $"reject={snapshot.rejectReason}"
            );
        }
        if (forceApplyNextSnapshot)
        {
            forceApplyNextSnapshot = false;

            latestAppliedTick = -1;
            latestAppliedAck = -1;

            Debug.Log(
                $"[{clientId}] Force apply first SNAPSHOT after reconnect. " +
                $"snapshotTick={snapshot.tick}, ack={snapshot.lastProcessedSeq}"
            );
        }
        await DispatchSnapshotWithSimulation(snapshot);
        CheckGameOverFromSnapshot(snapshot);
    }
    private void CheckGameOverFromSnapshot(MatchSnapshot snapshot)
    {
        if (gameOverHandledFromSnapshot)
            return;

        if (snapshot == null || snapshot.players == null || snapshot.players.Length <= 0)
            return;

        string loserClientId = "";
        string winnerClientId = "";

        foreach (var player in snapshot.players)
        {
            if (player == null)
                continue;

            if (player.stocks <= 0)
            {
                loserClientId = player.clientId;
                break;
            }
        }

        if (string.IsNullOrWhiteSpace(loserClientId))
            return;

        foreach (var player in snapshot.players)
        {
            if (player == null)
                continue;

            if (player.clientId != loserClientId && player.stocks > 0)
            {
                winnerClientId = player.clientId;
                break;
            }
        }

        if (string.IsNullOrWhiteSpace(winnerClientId))
        {
            winnerClientId = loserClientId == "Client1"
                ? "Client2"
                : "Client1";
        }

        gameOverHandledFromSnapshot = true;

        Debug.Log(
            $"[RelayChatClient] GAME OVER from SNAPSHOT. " +
            $"winner={winnerClientId}, loser={loserClientId}, tick={snapshot.tick}"
        );

        GameManager.Instance?.ShowGameOverFromNetwork(winnerClientId);
    }
    private void HandleResult(NetMessage msg)
    {
        try
        {
            string payloadJson = DecryptWithKcGs(msg.payload, "RESULT");

            if (debugNetworkLog)
                Debug.Log($"[RelayChatClient] RESULT payload={payloadJson}");
        }
        catch (Exception ex)
        {
            Debug.LogError($"[RelayChatClient] RESULT 解密失败: {ex.Message}");
        }
    }

    // ============================================================
    // Normalize / apply room state
    // ============================================================

    private void NormalizeRoomState(RoomStatePayload state)
    {
        if (state == null)
            return;

        if (string.IsNullOrWhiteSpace(state.hostClientId) && state.players != null)
        {
            foreach (RoomPlayerInfo p in state.players)
            {
                if (p != null && p.slotNo == 1)
                {
                    state.hostClientId = p.clientId;
                    break;
                }
            }
        }

        if (!string.IsNullOrWhiteSpace(state.hostClientId) &&
            !string.IsNullOrWhiteSpace(state.localClientId))
        {
            state.localIsHost = state.hostClientId == state.localClientId;
        }
        else if (state.localSlotNo == 1)
        {
            state.localIsHost = true;
        }

        if (state.players != null)
        {
            foreach (RoomPlayerInfo p in state.players)
            {
                if (p == null)
                    continue;

                p.isHost =
                    (!string.IsNullOrWhiteSpace(state.hostClientId) && p.clientId == state.hostClientId) ||
                    p.slotNo == 1;
            }
        }
    }

    private void NormalizeGameStart(GameStartPayload start)
    {
        if (start == null)
            return;

        if (string.IsNullOrWhiteSpace(start.hostClientId) && start.players != null)
        {
            foreach (RoomPlayerInfo p in start.players)
            {
                if (p != null && p.slotNo == 1)
                {
                    start.hostClientId = p.clientId;
                    break;
                }
            }
        }

        if (!string.IsNullOrWhiteSpace(start.hostClientId) &&
            !string.IsNullOrWhiteSpace(start.localClientId))
        {
            start.localIsHost = start.hostClientId == start.localClientId;
        }
        else if (start.localSlotNo == 1)
        {
            start.localIsHost = true;
        }

        if (start.players != null)
        {
            foreach (RoomPlayerInfo p in start.players)
            {
                if (p == null)
                    continue;

                p.isHost =
                    (!string.IsNullOrWhiteSpace(start.hostClientId) && p.clientId == start.hostClientId) ||
                    p.slotNo == 1;
            }
        }
    }

    private void ApplyRoomStateToClient(RoomStatePayload state, string reason)
    {
        if (state == null)
            return;

        roomId = state.roomId;

        if (!string.IsNullOrWhiteSpace(state.localClientId))
            clientId = state.localClientId;

        bool computedIsHost = state.localIsHost;

        if (!string.IsNullOrWhiteSpace(state.hostClientId) &&
            !string.IsNullOrWhiteSpace(clientId))
        {
            computedIsHost = state.hostClientId == clientId;
        }
        else if (state.localSlotNo == 1)
        {
            computedIsHost = true;
        }

        state.localIsHost = computedIsHost;

        hasJoinedRoom =
            !string.IsNullOrWhiteSpace(roomId) &&
            !string.IsNullOrWhiteSpace(clientId);

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.ApplyRoomState(state);

        AuthSession.EnsureExists().ApplyRoomIdentity(
            roomId,
            clientId,
            state.localSlotNo,
            state.localIsHost
        );

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[RelayChatClient] ApplyRoomState reason={reason} " +
                $"room={roomId}, client={clientId}, joined={hasJoinedRoom}, " +
                $"hostClientId={state.hostClientId}, " +
                $"slot={state.localSlotNo}, isHost={state.localIsHost}, " +
                $"canStart={state.canStart}"
            );
        }
    }
    public async System.Threading.Tasks.Task DisconnectForReconnectToSameMatch()
    {
        Debug.Log("[RelayChatClient] DisconnectForReconnectToSameMatch");

        // 关键：中途回大厅前，保存当前可重连信息。
        // 这里必须在清理/断开之前保存。
        AuthSessionPersistence.Save();

        await DisconnectButKeepSession();

        // 注意：这里不要清 roomId / sessionId / localClientId。
        // 这些字段是重连需要的。
    }
    public async System.Threading.Tasks.Task<bool> EnsureGsReady()
    {
        await EnsureConnected();

        if (!EnsureSocketOpen())
            return false;

        if (AuthSession.Ctx.HasGsSession)
        {
            if (debugNetworkLog)
            {
                Debug.Log(
                    $"[RelayChatClient] EnsureGsReady: reuse GS sessionId={AuthSession.Ctx.sessionId}"
                );
            }

            return true;
        }

        Debug.Log("[RelayChatClient] EnsureGsReady: need GS_AUTH.");

        bool ok = await ConnectAndAuthenticateGs();

        if (!ok || !AuthSession.Ctx.HasGsSession)
        {
            Debug.LogWarning("[RelayChatClient] EnsureGsReady failed.");
            return false;
        }

        Debug.Log(
            $"[RelayChatClient] EnsureGsReady OK. sessionId={AuthSession.Ctx.sessionId}"
        );

        return true;
    }
    public async System.Threading.Tasks.Task DisconnectAfterMatchFinished()
    {
        Debug.Log("[RelayChatClient] DisconnectAfterMatchFinished");

        await DisconnectButKeepSession();

        // 这局已经结束，清掉旧房间和旧 GS session。
        // 保留 AS/TGS 登录态，这样用户不需要重新输入账号密码。
        AuthContext ctx = AuthSession.Ctx;

        ctx.sessionId = "";
        ctx.gsSessionExpireAtMs = 0;

        ctx.roomId = "";
        ctx.localClientId = "";
        ctx.localSlotNo = -1;
        ctx.localIsHost = false;

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.Clear();

        hasJoinedRoom = false;
        roomId = "";
        clientId = "";

        Debug.Log("[RelayChatClient] Cleared finished match state.");
    }
    private void ResetRuntimeStateForNewMatch()
    {
        latestAppliedAck = -1;
        latestAppliedTick = -1;
        sentInputCount = 0;

        gameOverHandledFromSnapshot = false;
        forceApplyNextSnapshot = true;
        waitingFreshSnapshotAfterReconnect = false;

        reconnectInFlight = false;
        reconnectOk = false;
        reconnectError = "";

        Debug.Log("[RelayChatClient] Reset runtime state for new match.");
    }
    private void ApplyGameStartToClient(GameStartPayload start)
    {
        if (start == null)
            return;
        ResetRuntimeStateForNewMatch();
        gameOverHandledFromSnapshot = false;
        roomId = start.roomId;

        if (!string.IsNullOrWhiteSpace(start.localClientId))
            clientId = start.localClientId;

        bool computedIsHost = start.localIsHost;

        if (!string.IsNullOrWhiteSpace(start.hostClientId) &&
            !string.IsNullOrWhiteSpace(clientId))
        {
            computedIsHost = start.hostClientId == clientId;
        }
        else if (start.localSlotNo == 1)
        {
            computedIsHost = true;
        }

        start.localIsHost = computedIsHost;

        hasJoinedRoom =
            !string.IsNullOrWhiteSpace(roomId) &&
            !string.IsNullOrWhiteSpace(clientId);

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.ApplyGameStart(start);

        AuthSession.EnsureExists().ApplyRoomIdentity(
            roomId,
            clientId,
            start.localSlotNo,
            start.localIsHost
        );

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[RelayChatClient] ApplyGameStart " +
                $"room={roomId}, client={clientId}, joined={hasJoinedRoom}, " +
                $"hostClientId={start.hostClientId}, " +
                $"slot={start.localSlotNo}, isHost={start.localIsHost}, " +
                $"scene={start.sceneName}"
            );
        }
    }

    // ============================================================
    // Snapshot apply
    // ============================================================

    private async Task DispatchSnapshotWithSimulation(MatchSnapshot snapshot)
    {
        if (!simulateNetwork)
        {
            ApplySnapshot(snapshot);
            return;
        }

        if (UnityEngine.Random.value < incomingDropRate)
        {
            if (debugNetworkLog)
                Debug.LogWarning($"[{clientId}] [NETSIM] IN DROP tick={snapshot.tick}");

            return;
        }

        int delay = GetSimulatedDelay(incomingDelayMs, jitterMs);

        if (delay > 0)
        {
            if (debugNetworkLog)
                Debug.Log($"[{clientId}] [NETSIM] IN delay={delay}ms tick={snapshot.tick}");

            await Task.Delay(delay);
        }

        ApplySnapshot(snapshot);
    }

    private void ApplySnapshot(MatchSnapshot snapshot)
    {
        bool isOlder =
            snapshot.lastProcessedSeq < latestAppliedAck ||
            (snapshot.lastProcessedSeq == latestAppliedAck && snapshot.tick <= latestAppliedTick);

        if (isOlder)
        {
            if (debugNetworkLog)
            {
                Debug.LogWarning(
                    $"[{clientId}] DROP OLD SNAPSHOT tick={snapshot.tick} ack={snapshot.lastProcessedSeq} " +
                    $"latestTick={latestAppliedTick} latestAck={latestAppliedAck}"
                );
            }

            return;
        }

        latestAppliedAck = snapshot.lastProcessedSeq;
        latestAppliedTick = snapshot.tick;

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[{clientId}] APPLY SNAPSHOT tick={snapshot.tick} ack={snapshot.lastProcessedSeq} " +
                $"players={(snapshot.players != null ? snapshot.players.Length : 0)} " +
                $"projectiles={(snapshot.projectiles != null ? snapshot.projectiles.Length : 0)} " +
                $"events={(snapshot.events != null ? snapshot.events.Length : 0)} " +
                $"reject={snapshot.rejectReason}"
            );
        }

        ClientReceiver.Instance?.OnReceiveSnapshot(snapshot);
    }
    public async System.Threading.Tasks.Task DisconnectButKeepSession()
    {
        if (websocket == null)
            return;

        try
        {
            var oldSocket = websocket;

            if (oldSocket.State == NativeWebSocket.WebSocketState.Open ||
                oldSocket.State == NativeWebSocket.WebSocketState.Connecting)
            {
                await oldSocket.Close();
            }

            int waitMs = 0;
            while (oldSocket.State != NativeWebSocket.WebSocketState.Closed && waitMs < 1000)
            {
                await System.Threading.Tasks.Task.Delay(50);
                waitMs += 50;
            }
        }
        catch (System.Exception ex)
        {
            Debug.LogWarning("[RelayChatClient] DisconnectButKeepSession failed: " + ex.Message);
        }

        websocket = null;
        hasJoinedRoom = false;

        Debug.Log("[RelayChatClient] DisconnectButKeepSession done. AuthSession kept.");
    }
    public async Task<bool> ReconnectToGameAsync(int timeoutMs = 5000)
    {
        if (reconnectInFlight)
        {
            Debug.LogWarning("[RelayChatClient] Reconnect already in flight.");
            return false;
        }

        ApplyNetworkSessionToLocalFields();

        AuthContext ctx = AuthSession.Ctx;

        if (!ctx.HasServiceTicket)
        {
            Debug.LogWarning("[RelayChatClient] Reconnect failed: missing serviceTicket/kcGs.");
            return false;
        }

        if (string.IsNullOrWhiteSpace(ctx.sessionId))
        {
            Debug.LogWarning("[RelayChatClient] Reconnect failed: missing sessionId.");
            return false;
        }

        string reconnectRoomId = !string.IsNullOrWhiteSpace(roomId)
            ? roomId
            : ctx.roomId;

        string reconnectClientId = !string.IsNullOrWhiteSpace(clientId)
            ? clientId
            : ctx.localClientId;

        if (string.IsNullOrWhiteSpace(reconnectRoomId))
        {
            Debug.LogWarning("[RelayChatClient] Reconnect failed: missing roomId.");
            return false;
        }

        if (string.IsNullOrWhiteSpace(reconnectClientId))
        {
            Debug.LogWarning("[RelayChatClient] Reconnect failed: missing localClientId.");
            return false;
        }

        reconnectInFlight = true;
        reconnectOk = false;
        reconnectError = "";

        try
        {
            await EnsureConnected();

            if (!EnsureSocketOpen())
            {
                Debug.LogWarning("[RelayChatClient] Reconnect failed: socket not open.");
                return false;
            }

            await SendReconnectReq(reconnectRoomId, reconnectClientId);

            int elapsed = 0;

            while (elapsed < timeoutMs)
            {
                if (reconnectOk)
                    return true;

                if (!string.IsNullOrWhiteSpace(reconnectError))
                {
                    Debug.LogWarning("[RelayChatClient] Reconnect failed: " + reconnectError);
                    return false;
                }

                await Task.Delay(50);
                elapsed += 50;
            }

            Debug.LogWarning("[RelayChatClient] Reconnect timeout.");
            return false;
        }
        catch (Exception ex)
        {
            Debug.LogError("[RelayChatClient] Reconnect exception: " + ex);
            return false;
        }
        finally
        {
            reconnectInFlight = false;
        }
    }
    private async Task SendReconnectReq(string reconnectRoomId, string reconnectClientId)
    {
        AuthContext ctx = AuthSession.Ctx;

        if (!AuthSession.EnsureExists().ValidateGsTicketReady())
            throw new InvalidOperationException("ServiceTicket/KcGs not ready.");

        if (string.IsNullOrWhiteSpace(ctx.sessionId))
            throw new InvalidOperationException("sessionId missing.");

        if (string.IsNullOrWhiteSpace(reconnectRoomId))
            throw new InvalidOperationException("roomId missing.");

        if (string.IsNullOrWhiteSpace(reconnectClientId))
            throw new InvalidOperationException("localClientId missing.");

        long ts = ClientCrypto.NowMs();
        string nonce = ClientCrypto.GenerateNonce();

        var authPayload = new ReconnectAuthPayload
        {
            type = "RECONNECT_REQ",
            clientId = ctx.clientId,
            sessionId = ctx.sessionId,
            roomId = reconnectRoomId,
            ts = ts,
            nonce = nonce
        };

        var payload = new ReconnectPayload
        {
            type = "RECONNECT_REQ",
            clientId = ctx.clientId,
            sessionId = ctx.sessionId,
            roomId = reconnectRoomId,
            nonce = nonce,
            lastProcessedSeq = latestAppliedAck,
            ts = ts
        };

        var msg = new NetMessage
        {
            type = "RECONNECT_REQ",
            clientId = ctx.clientId,
            sessionId = ctx.sessionId,
            roomId = reconnectRoomId,
            ticket = ctx.serviceTicket,
            auth = EncryptWithKcGs(authPayload),
            payload = EncryptWithKcGs(payload)
        };

        await SendJson(msg, bypassSimulation: true);

        if (debugNetworkLog)
        {
            Debug.Log(
                $"[RelayChatClient] SEND RECONNECT_REQ " +
                $"authClientId={ctx.clientId}, localClient={reconnectClientId}, " +
                $"room={reconnectRoomId}, sessionId={ctx.sessionId}, lastAck={latestAppliedAck}"
            );
        }
    }

    private int GetSimulatedDelay(int baseDelayMs, int jitterRangeMs)
    {
        int jitter = 0;

        if (jitterRangeMs > 0)
            jitter = UnityEngine.Random.Range(-jitterRangeMs, jitterRangeMs + 1);

        int finalDelay = baseDelayMs + jitter;
        return Mathf.Max(0, finalDelay);
    }
    public void ClearLocalRoomState()
    {
        hasJoinedRoom = false;
        roomId = "";
        clientId = "";

        if (debugNetworkLog)
            Debug.Log("[RelayChatClient] ClearLocalRoomState done.");
    }
    private void HandleServerError(NetMessage msg)
    {
        string error = msg.error ?? "";

        Debug.LogError($"[{clientId}] SERVER ERROR: {error}");

        switch (error)
        {
            case "ACCOUNT_LOGGED_IN_ELSEWHERE":
            case "SESSION_REPLACED":
                GameAlert.Show(
                    "账号已在其他设备登录",
                    "你的账号刚刚在另一台设备登录，本客户端会退出到登录页。",
                    "确定",
                    async () =>
                    {
                        await DisconnectAfterMatchFinished();
                        AuthSession.EnsureExists().ClearAll();
                        UnityEngine.SceneManagement.SceneManager.LoadScene("MainMenu");
                    }
                );
                break;

            case "AUTH_EXPIRED":
                GameAlert.Show(
                    "登录已过期",
                    "你的登录状态已经过期，请重新登录。",
                    "重新登录",
                    async () =>
                    {
                        await DisconnectAfterMatchFinished();
                        AuthSession.EnsureExists().ClearAll();
                        UnityEngine.SceneManagement.SceneManager.LoadScene("MainMenu");
                    }
                );
                break;

            case "RECONNECT_EXPIRED":
                GameAlert.Show(
                    "重连失败",
                    "当前对局的重连时间已过，请返回大厅。",
                    "返回大厅",
                    async () =>
                    {
                        await DisconnectAfterMatchFinished();
                        UnityEngine.SceneManagement.SceneManager.LoadScene("MainMenu");
                    }
                );
                break;

            case "NOT_AUTHENTICATED":
                GameAlert.Show(
                    "连接未认证",
                    "服务器连接状态已失效，请重新进入房间。",
                    "确定"
                );
                break;

            case "ROOM_MISMATCH":
                GameAlert.Show(
                    "房间状态异常",
                    "当前房间信息不一致，请返回大厅后重新加入。",
                    "返回大厅",
                    async () =>
                    {
                        await DisconnectAfterMatchFinished();
                        UnityEngine.SceneManagement.SceneManager.LoadScene("MainMenu");
                    }
                );
                break;

            default:
                GameAlert.Show(
                    "服务器错误",
                    $"错误信息：{error}",
                    "确定"
                );
                break;
        }
    }
    // ============================================================
    // Context menu
    // ============================================================

    [ContextMenu("Connect")]
    private void ConnectFromMenu()
    {
        _ = Connect();
    }

    [ContextMenu("Connect And GS_AUTH")]
    private void ConnectAndAuthFromMenu()
    {
        _ = ConnectAndAuthenticateGs();
    }

    [ContextMenu("Send GS_AUTH")]
    private void SendGsAuthFromMenu()
    {
        _ = SendGsAuth();
    }

    [ContextMenu("Create Room")]
    private void CreateRoomFromMenu()
    {
        _ = SendCreateRoom();
    }

    [ContextMenu("Leave Room")]
    private void LeaveFromMenu()
    {
        _ = LeaveRoom();
    }

    [ContextMenu("Disconnect")]
    private void DisconnectFromMenu()
    {
        _ = Disconnect();
    }
}