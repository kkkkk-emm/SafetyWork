using UnityEngine;

public class NetworkSession : MonoBehaviour
{
    public static NetworkSession Instance { get; private set; }

    [Header("连接信息")]
    public string serverUrl = "ws://127.0.0.1:8765";

    [Header("GS 会话")]
    public string sessionId = "";

    [Header("房间信息")]
    public string roomId = "";
    public string hostClientId = "";
    public string roomStatus = "";

    [Header("房间内玩家身份")]
    public string clientId = "";
    public int slotNo = 0;
    public bool isHost = false;
    public bool canStart = false;

    [Header("场景")]
    public string gameSceneName = "MainGame";

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);

        SyncFromAuthSession();
    }

    public void SyncFromAuthSession()
    {
        AuthContext ctx = AuthSession.Ctx;

        sessionId = ctx.sessionId;
        roomId = ctx.roomId;
        clientId = ctx.localClientId;
        slotNo = ctx.localSlotNo;
        isHost = ctx.localIsHost;
    }

    public void ApplyGsSession(string newSessionId)
    {
        sessionId = newSessionId ?? "";
        AuthSession.Ctx.sessionId = sessionId;

        Debug.Log($"[NetworkSession] ApplyGsSession sessionId={sessionId}");
    }

    public void ApplyRoomState(RoomStatePayload state)
    {
        if (state == null)
            return;

        roomId = state.roomId ?? "";
        hostClientId = state.hostClientId ?? "";
        roomStatus = !string.IsNullOrWhiteSpace(state.state)
            ? state.state
            : (state.status ?? "");

        canStart = state.canStart;

        clientId = state.localClientId ?? "";
        slotNo = state.localSlotNo;

        // 如果服务端没给 localClientId / slotNo，就从 players 里兜底找
        if ((string.IsNullOrWhiteSpace(clientId) || slotNo <= 0) &&
            state.players != null)
        {
            foreach (RoomPlayerInfo p in state.players)
            {
                if (p == null)
                    continue;

                // 优先找服务端标记的本地身份
                if (!string.IsNullOrWhiteSpace(state.localClientId) &&
                    p.clientId == state.localClientId)
                {
                    clientId = p.clientId;
                    slotNo = p.slotNo;
                    break;
                }

                // 再用 slot=1 的房主兜底，但只在本地为空时使用
                if (string.IsNullOrWhiteSpace(clientId) && p.slotNo == 1)
                {
                    clientId = p.clientId;
                    slotNo = p.slotNo;
                }
            }
        }

        // 关键：本地是否房主，优先用 hostClientId 和房间 clientId 算
        if (!string.IsNullOrWhiteSpace(hostClientId) &&
            !string.IsNullOrWhiteSpace(clientId))
        {
            isHost = hostClientId == clientId;
        }
        else
        {
            // 兜底：slot 1 就是房主
            isHost = state.localIsHost || slotNo == 1;
        }

        // 同步回 state，后续 UI 如果用 state.localIsHost 也是正确的
        state.localClientId = clientId;
        state.localSlotNo = slotNo;
        state.localIsHost = isHost;

        // 修正 players 里的 isHost，防止 LobbyPlayerCard 显示不出 HOST
        if (state.players != null)
        {
            foreach (RoomPlayerInfo p in state.players)
            {
                if (p == null)
                    continue;

                p.isHost =
                    (!string.IsNullOrWhiteSpace(hostClientId) && p.clientId == hostClientId) ||
                    p.slotNo == 1;
            }
        }

        AuthSession.EnsureExists().ApplyRoomIdentity(
            roomId,
            clientId,
            slotNo,
            isHost
        );

        Debug.Log(
            $"[NetworkSession] ApplyRoomState " +
            $"room={roomId}, hostClientId={hostClientId}, " +
            $"clientId={clientId}, slot={slotNo}, isHost={isHost}, " +
            $"canStart={canStart}, status={roomStatus}, sessionId={sessionId}"
        );
    }

    public void ApplyGameStart(GameStartPayload start)
    {
        if (start == null)
            return;

        roomId = start.roomId ?? "";
        hostClientId = start.hostClientId ?? "";
        roomStatus = !string.IsNullOrWhiteSpace(start.state)
            ? start.state
            : (start.status ?? "");

        canStart = start.canStart;

        clientId = start.localClientId ?? "";
        slotNo = start.localSlotNo;

        if (!string.IsNullOrWhiteSpace(hostClientId) &&
            !string.IsNullOrWhiteSpace(clientId))
        {
            isHost = hostClientId == clientId;
        }
        else
        {
            isHost = start.localIsHost || slotNo == 1;
        }

        if (!string.IsNullOrWhiteSpace(start.sceneName))
            gameSceneName = start.sceneName;

        start.localClientId = clientId;
        start.localSlotNo = slotNo;
        start.localIsHost = isHost;

        if (start.players != null)
        {
            foreach (RoomPlayerInfo p in start.players)
            {
                if (p == null)
                    continue;

                p.isHost =
                    (!string.IsNullOrWhiteSpace(hostClientId) && p.clientId == hostClientId) ||
                    p.slotNo == 1;
            }
        }

        AuthSession.EnsureExists().ApplyRoomIdentity(
            roomId,
            clientId,
            slotNo,
            isHost
        );

        Debug.Log(
            $"[NetworkSession] ApplyGameStart " +
            $"room={roomId}, hostClientId={hostClientId}, " +
            $"clientId={clientId}, slot={slotNo}, isHost={isHost}, " +
            $"canStart={canStart}, scene={gameSceneName}, sessionId={sessionId}"
        );
    }

    public void ClearRoom()
    {
        roomId = "";
        hostClientId = "";
        roomStatus = "";

        clientId = "";
        slotNo = 0;
        isHost = false;
        canStart = false;

        AuthSession.Ctx.ClearRoom();
    }

    public void Clear()
    {
        ClearRoom();
    }

    public void ClearAll()
    {
        sessionId = "";
        ClearRoom();

        AuthSession.Ctx.ClearAll();
    }
}