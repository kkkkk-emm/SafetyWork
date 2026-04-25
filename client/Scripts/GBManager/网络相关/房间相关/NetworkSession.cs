using UnityEngine;

public class NetworkSession : MonoBehaviour
{
    public static NetworkSession Instance { get; private set; }

    [Header("连接信息")]
    public string serverUrl = "ws://127.0.0.1:8765";

    [Header("玩家身份")]
    public string clientId = "";
    public string roomId = "";
    public int slotNo = 0;
    public bool isHost = false;

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
    }

    public void ApplyRoomState(RoomStatePayload state)
    {
        if (state == null)
            return;

        roomId = state.roomId;

        // 关键：一定要覆盖旧 clientId。
        // 不要写成 if clientId empty 才赋值。
        clientId = state.localClientId;
        slotNo = state.localSlotNo;
        isHost = state.localIsHost;

        if (slotNo <= 0 && state.players != null)
        {
            foreach (RoomPlayerInfo p in state.players)
            {
                if (p == null)
                    continue;

                if (p.clientId == clientId)
                {
                    slotNo = p.slotNo;
                    isHost = p.isHost;
                    break;
                }
            }
        }

        Debug.Log(
            $"[NetworkSession] ApplyRoomState room={roomId}, " +
            $"clientId={clientId}, slot={slotNo}, isHost={isHost}"
        );
    }

    public void ApplyGameStart(GameStartPayload start)
    {
        if (start == null)
            return;

        roomId = start.roomId;
        clientId = start.localClientId;
        slotNo = start.localSlotNo;
        isHost = start.localIsHost;

        if (!string.IsNullOrWhiteSpace(start.sceneName))
            gameSceneName = start.sceneName;

        Debug.Log(
            $"[NetworkSession] ApplyGameStart room={roomId}, " +
            $"clientId={clientId}, slot={slotNo}, isHost={isHost}, scene={gameSceneName}"
        );
    }

    public void Clear()
    {
        roomId = "";
        clientId = "";
        slotNo = 0;
        isHost = false;
    }
}