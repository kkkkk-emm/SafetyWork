using System;

[Serializable]
public class RoomPlayerInfo
{
    public string clientId;
    public int slotNo;
    public bool ready;
    public bool isHost;
}

[Serializable]
public class RoomStatePayload
{
    public string roomId;
    public string hostClientId;
    public string status;
    public RoomPlayerInfo[] players;
    public bool canStart;

    // 服务器专门告诉当前这个客户端：你是谁
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
    public string roomId;
    public string hostClientId;
    public string status;
    public RoomPlayerInfo[] players;
    public bool canStart;
    public string sceneName;

    public string localClientId;
    public int localSlotNo;
    public bool localIsHost;
}