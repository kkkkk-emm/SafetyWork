using System;

[Serializable]
public class ProtocolMessage
{
    public string type;

    // 认证阶段客户端实例 ID，例如 cli_xxx。
    // 注意：不是房间里的 Client1 / Client2。
    public string clientId;

    // GS_AUTH_OK 后由 GS 返回。
    // 后续 ROOM_CREATE_REQ / ROOM_JOIN_REQ / INPUT 等都带这个。
    public string sessionId;

    // 房间号。
    public string roomId;

    // TGT 或 Service Ticket。
    public string ticket;

    // Authenticator。
    // 新协议里通常是 Base64(DES(KcTgs/KcGs, JSON))。
    public string auth;

    // 业务 payload。
    // AS 请求：Base64(RSA(JSON))
    // AS 响应：JSON 字符串
    // TGS/GS/房间/输入：通常是 Base64(DES(JSON))
    public string payload;

    // ERROR 消息使用。
    public string error;

    // 兼容旧聊天/广播字段。
    public string targetId;
    public string fromClientId;
    public string text;
    public string timestamp;
}