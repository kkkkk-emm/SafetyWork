using System;

[Serializable]
public class RoomPlayerInfo
{
    public long userId;
    public string username;

    public string clientId;
    public int slotNo;
    public bool ready;

    // 关键：UI 房主标识用这个
    public bool isHost;

    public bool online;
}

[Serializable]
public class RoomStatePayload
{
    public string type;

    public string roomId;
    public string hostClientId;

    // 服务端现在发的是 state，不是 status
    public string state;

    // 兼容旧字段
    public string status;

    public long ownerUserId;
    public RoomPlayerInfo[] players;
    public bool canStart;

    // 服务端告诉当前这个客户端：你是谁
    public string localClientId;
    public int localSlotNo;
    public bool localIsHost;
}

[Serializable]
public class ReadyPayload
{
    public bool ready;
}

[Serializable]
public class GameStartPayload
{
    public string type;

    public string roomId;
    public string hostClientId;

    public string state;
    public string status;

    public long ownerUserId;
    public RoomPlayerInfo[] players;
    public bool canStart;

    public string sceneName;
    public string matchId;
    public int countdownMs;

    public string localClientId;
    public int localSlotNo;
    public bool localIsHost;
}