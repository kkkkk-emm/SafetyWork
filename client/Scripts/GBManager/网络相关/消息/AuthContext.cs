using System;

[Serializable]
public class AuthContext
{
    // ------------------------------------------------------------
    // 客户端实例身份
    // ------------------------------------------------------------

    // 认证阶段客户端实例 ID，例如 cli_xxx。
    // 这个 ID 会放进 AS_REQ / TGS_REQ / GS_AUTH 的顶层 clientId。
    public string clientId = "";

    // ------------------------------------------------------------
    // 账号身份
    // ------------------------------------------------------------

    public long userId = 0;
    public string username = "";

    // ------------------------------------------------------------
    // AS -> Client
    // ------------------------------------------------------------

    // AS_REP.ticket。
    // 这是 TGT：Base64(DES(K_TGS, TGT_JSON))。
    // 客户端不能解，只能转交给 TGS。
    public string tgt = "";

    // AS_REP.payload.part 解密后得到。
    // Base64 后的 8 字节 DES key。
    public string kcTgs = "";

    public long tgtExpireAtMs = 0;
    public long loginGen = 0;

    // ------------------------------------------------------------
    // TGS -> Client
    // ------------------------------------------------------------

    // TGS_REP.ticket。
    // 这是 Service Ticket：Base64(DES(K_GS, ServiceTicket_JSON))。
    // 客户端不能解，只能转交给 GS_AUTH。
    public string serviceTicket = "";

    // TGS_REP.payload 用 KcTgs 解密后得到。
    // Base64 后的 8 字节 DES key。
    public string kcGs = "";

    public long serviceTicketExpireAtMs = 0;

    // ------------------------------------------------------------
    // GS -> Client
    // ------------------------------------------------------------

    // GS_AUTH_OK 返回。
    public string sessionId = "";

    public long gsSessionExpireAtMs = 0;

    // ------------------------------------------------------------
    // 房间身份
    // ------------------------------------------------------------

    // 房间号。
    public string roomId = "";

    // 房间/对战身份：Client1 / Client2。
    // 注意：这不是认证阶段 clientId。
    public string localClientId = "";

    public int localSlotNo = 0;
    public bool localIsHost = false;

    // ------------------------------------------------------------
    // 状态判断
    // ------------------------------------------------------------

    public bool HasClientId =>
        !string.IsNullOrWhiteSpace(clientId);

    public bool HasTgt =>
        !string.IsNullOrWhiteSpace(tgt) &&
        !string.IsNullOrWhiteSpace(kcTgs);

    public bool HasServiceTicket =>
        !string.IsNullOrWhiteSpace(serviceTicket) &&
        !string.IsNullOrWhiteSpace(kcGs);

    public bool HasGsSession =>
        !string.IsNullOrWhiteSpace(sessionId);

    public bool HasRoomIdentity =>
        !string.IsNullOrWhiteSpace(roomId) &&
        !string.IsNullOrWhiteSpace(localClientId) &&
        localSlotNo > 0;

    public byte[] KcTgsBytes
    {
        get
        {
            return ClientCrypto.Base64Decode(kcTgs);
        }
    }

    public byte[] KcGsBytes
    {
        get
        {
            return ClientCrypto.Base64Decode(kcGs);
        }
    }

    // ------------------------------------------------------------
    // 清理
    // ------------------------------------------------------------

    public void ClearAsTicket()
    {
        tgt = "";
        kcTgs = "";
        tgtExpireAtMs = 0;
        loginGen = 0;
    }

    public void ClearTgsTicket()
    {
        serviceTicket = "";
        kcGs = "";
        serviceTicketExpireAtMs = 0;
    }

    public void ClearGsSession()
    {
        sessionId = "";
        gsSessionExpireAtMs = 0;
    }

    public void ClearRoom()
    {
        roomId = "";
        localClientId = "";
        localSlotNo = 0;
        localIsHost = false;
    }

    public void ClearTicketsAndSession()
    {
        ClearAsTicket();
        ClearTgsTicket();
        ClearGsSession();
    }

    public void ClearAll()
    {
        clientId = "";

        userId = 0;
        username = "";

        ClearTicketsAndSession();
        ClearRoom();
    }
}