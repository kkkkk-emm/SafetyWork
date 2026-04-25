using System;
using System.Threading.Tasks;
using UnityEngine;

public class MainGameNetworkBootstrap : MonoBehaviour
{
    [Header("引用")]
    [SerializeField] private RelayChatClient relayClient;

    [Header("调试")]
    [SerializeField] private bool showDebugOverlay = true;
    [SerializeField] private bool debugLog = true;

    [Header("连接等待")]
    [SerializeField] private float connectTimeoutSeconds = 5f;

    private string debugStatus = "Not started";
    private bool started;

    private async void Start()
    {
        if (started)
            return;

        started = true;

        debugStatus = "Start() entered";
        Log(debugStatus);

        await Task.Yield();

        await Bootstrap();
    }

    private async Task Bootstrap()
    {
        try
        {
            debugStatus = "Finding RelayChatClient...";
            Log(debugStatus);

            if (relayClient == null)
                relayClient = FindFirstObjectByType<RelayChatClient>();

            if (relayClient == null)
            {
                debugStatus = "ERROR: RelayChatClient not found";
                Debug.LogError("[MainGameNetworkBootstrap] 找不到 RelayChatClient");
                return;
            }

            debugStatus = "Checking NetworkSession...";
            Log(debugStatus);

            if (NetworkSession.Instance == null)
            {
                debugStatus = "ERROR: NetworkSession.Instance is null";
                Debug.LogError("[MainGameNetworkBootstrap] 没有 NetworkSession");
                return;
            }

            string roomId = NetworkSession.Instance.roomId;
            string clientId = NetworkSession.Instance.clientId;
            string serverUrl = NetworkSession.Instance.serverUrl;

            debugStatus =
                $"Session room={roomId}, client={clientId}, server={serverUrl}, " +
                $"slot={NetworkSession.Instance.slotNo}, host={NetworkSession.Instance.isHost}";
            Log(debugStatus);

            if (string.IsNullOrWhiteSpace(roomId) || string.IsNullOrWhiteSpace(clientId))
            {
                debugStatus =
                    $"ERROR: NetworkSession info incomplete. room={roomId}, client={clientId}";

                Debug.LogError("[MainGameNetworkBootstrap] " + debugStatus);
                return;
            }

            if (string.IsNullOrWhiteSpace(serverUrl))
            {
                serverUrl = "ws://127.0.0.1:8765";
                NetworkSession.Instance.serverUrl = serverUrl;
            }

            debugStatus = "Configuring RelayChatClient...";
            Log(debugStatus);

            relayClient.ConfigureIdentity(
                serverUrl,
                clientId,
                roomId
            );

            debugStatus =
                $"Relay before connect: connected={relayClient.IsConnected}, " +
                $"joined={relayClient.HasJoinedRoom}, client={relayClient.ClientId}, room={relayClient.RoomId}";
            Log(debugStatus);

            if (!relayClient.IsConnected)
            {
                debugStatus = "Starting websocket connect...";
                Log(debugStatus);

                // 关键：不要 await relayClient.Connect()
                // NativeWebSocket 有时 OnOpen 已经触发，但 Connect Task 不往下返回。
                _ = relayClient.Connect();

                bool connected = await WaitUntilConnected(connectTimeoutSeconds);

                if (!connected)
                {
                    debugStatus =
                        $"ERROR: connect timeout. connected={relayClient.IsConnected}, " +
                        $"client={relayClient.ClientId}, room={relayClient.RoomId}";

                    Debug.LogError("[MainGameNetworkBootstrap] " + debugStatus);
                    return;
                }
            }

            debugStatus =
                $"Connected. joined={relayClient.HasJoinedRoom}, " +
                $"client={relayClient.ClientId}, room={relayClient.RoomId}";
            Log(debugStatus);

            bool alreadyJoinedSameRoom =
                relayClient.HasJoinedRoom &&
                relayClient.RoomId == roomId &&
                relayClient.ClientId == clientId;

            if (alreadyJoinedSameRoom)
            {
                debugStatus =
                    $"Already joined same room. client={clientId}, room={roomId}";
                Log(debugStatus);
                return;
            }

            debugStatus = $"Sending JOIN_ROOM as {clientId} room={roomId}";
            Log(debugStatus);

            await relayClient.SendJoinRoomManual(
                clientId,
                roomId
            );

            debugStatus =
                $"JOIN sent. joined={relayClient.HasJoinedRoom}, " +
                $"client={relayClient.ClientId}, room={relayClient.RoomId}";

            Log(debugStatus);
        }
        catch (Exception ex)
        {
            debugStatus = "EXCEPTION: " + ex.Message;
            Debug.LogError("[MainGameNetworkBootstrap] Exception:\n" + ex);
        }
    }

    private async Task<bool> WaitUntilConnected(float timeoutSeconds)
    {
        float startTime = Time.realtimeSinceStartup;

        while (Time.realtimeSinceStartup - startTime < timeoutSeconds)
        {
            if (relayClient != null && relayClient.IsConnected)
                return true;

            debugStatus =
                $"Waiting connect... elapsed={(Time.realtimeSinceStartup - startTime):F1}s, " +
                $"connected={(relayClient != null && relayClient.IsConnected)}";

            await Task.Delay(50);
        }

        return relayClient != null && relayClient.IsConnected;
    }

    private void Log(string msg)
    {
        if (debugLog)
            Debug.Log("[MainGameNetworkBootstrap] " + msg);
    }

    private void OnGUI()
    {
        if (!showDebugOverlay)
            return;

        GUI.color = Color.white;

        string sessionInfo = "NetworkSession: null";

        if (NetworkSession.Instance != null)
        {
            sessionInfo =
                $"NetworkSession room={NetworkSession.Instance.roomId}\n" +
                $"NetworkSession client={NetworkSession.Instance.clientId}\n" +
                $"NetworkSession slot={NetworkSession.Instance.slotNo}\n" +
                $"NetworkSession host={NetworkSession.Instance.isHost}\n" +
                $"NetworkSession server={NetworkSession.Instance.serverUrl}";
        }

        string relayInfo = "RelayChatClient: null";

        if (relayClient != null)
        {
            relayInfo =
                $"Relay connected={relayClient.IsConnected}\n" +
                $"Relay joined={relayClient.HasJoinedRoom}\n" +
                $"Relay client={relayClient.ClientId}\n" +
                $"Relay room={relayClient.RoomId}";
        }

        GUI.Box(
            new Rect(10, 10, 560, 250),
            "MainGame Network Bootstrap\n\n" +
            $"Status: {debugStatus}\n\n" +
            sessionInfo + "\n\n" +
            relayInfo
        );
    }
}