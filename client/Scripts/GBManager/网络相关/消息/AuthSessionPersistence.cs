using System;
using System.Text;
using UnityEngine;

public static class AuthSessionPersistence
{
    // 旧版本用过的全局 Key。保留它，是为了可以清理老数据。
    private const string LegacyKey = "GB_AUTH_SESSION_V1";

    // 新版本：按 userId 分开保存，避免本机两个账号互相覆盖。
    private const string KeyPrefix = "GB_AUTH_SESSION_V1_USER_";

    [Serializable]
    private class SaveData
    {
        public long userId;
        public string username;
        public string clientId;

        public string tgt;
        public string kcTgs;
        public long tgtExpireAtMs;
        public long loginGen;

        public string serviceTicket;
        public string kcGs;
        public long serviceTicketExpireAtMs;

        public string sessionId;
        public long gsSessionExpireAtMs;

        public string roomId;
        public string localClientId;
        public int localSlotNo;
        public bool localIsHost;

        public long savedAtMs;
    }

    private static string GetKey(long userId)
    {
        return KeyPrefix + userId;
    }

    /// <summary>
    /// 保存当前 AuthSession，用于之后“登录后再恢复重连信息”。
    /// 注意：如果当前没有完整房间身份，不保存，避免登录后的空 room 覆盖旧重连记录。
    /// </summary>
    public static void Save()
    {
        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null)
        {
            Debug.LogWarning("[AuthSessionPersistence] Save failed: ctx is null.");
            return;
        }

        if (ctx.userId <= 0)
        {
            Debug.Log("[AuthSessionPersistence] Save skipped: userId invalid.");
            return;
        }

        // 关键保护：
        // 登录 / GS_AUTH_OK 后经常只有 sessionId，没有 roomId/localClientId。
        // 这种情况下不能保存，否则会把旧的可重连记录覆盖成空房间记录。
        if (string.IsNullOrWhiteSpace(ctx.sessionId) ||
            string.IsNullOrWhiteSpace(ctx.roomId) ||
            string.IsNullOrWhiteSpace(ctx.localClientId))
        {
            Debug.Log(
                $"[AuthSessionPersistence] Save skipped: incomplete reconnect fields. " +
                $"userId={ctx.userId}, session={ctx.sessionId}, room={ctx.roomId}, local={ctx.localClientId}"
            );
            return;
        }

        SaveData data = new SaveData
        {
            userId = ctx.userId,
            username = ctx.username ?? "",
            clientId = ctx.clientId ?? "",

            tgt = ctx.tgt ?? "",
            kcTgs = ctx.kcTgs ?? "",
            tgtExpireAtMs = ctx.tgtExpireAtMs,
            loginGen = ctx.loginGen,

            serviceTicket = ctx.serviceTicket ?? "",
            kcGs = ctx.kcGs ?? "",
            serviceTicketExpireAtMs = ctx.serviceTicketExpireAtMs,

            sessionId = ctx.sessionId ?? "",
            gsSessionExpireAtMs = ctx.gsSessionExpireAtMs,

            roomId = ctx.roomId ?? "",
            localClientId = ctx.localClientId ?? "",
            localSlotNo = ctx.localSlotNo,
            localIsHost = ctx.localIsHost,

            savedAtMs = NowMs()
        };

        string json = JsonUtility.ToJson(data);
        string encoded = Convert.ToBase64String(Encoding.UTF8.GetBytes(json));

        string key = GetKey(data.userId);

        PlayerPrefs.SetString(key, encoded);
        PlayerPrefs.Save();

        Debug.Log(
            $"[AuthSessionPersistence] Saved session. " +
            $"key={key}, user={data.username}, userId={data.userId}, " +
            $"room={data.roomId}, localClient={data.localClientId}, session={data.sessionId}"
        );
    }

    /// <summary>
    /// 不建议启动时自动调用。你现在的设计是：启动后必须先登录。
    /// 这个方法保留给调试/特殊情况使用。
    /// </summary>
    public static bool Load()
    {
        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null || ctx.userId <= 0)
        {
            Debug.LogWarning("[AuthSessionPersistence] Load skipped: no current logged-in user.");
            return false;
        }

        return LoadForUser(ctx.userId, restoreFullAuthSession: true);
    }

    /// <summary>
    /// 是否有当前 userId 对应的可重连记录。
    /// 只检查本地保存，不会修改 AuthSession.Ctx。
    /// </summary>
    public static bool HasReconnectForUser(long currentUserId)
    {
        if (currentUserId <= 0)
            return false;

        if (!TryReadSaveDataForUser(currentUserId, out SaveData data))
            return false;

        if (data.userId != currentUserId)
        {
            Debug.LogWarning(
                $"[AuthSessionPersistence] User mismatch. saved={data.userId}, current={currentUserId}."
            );
            ClearForUser(data.userId);
            return false;
        }

        bool has =
            !string.IsNullOrWhiteSpace(data.sessionId) &&
            !string.IsNullOrWhiteSpace(data.roomId) &&
            !string.IsNullOrWhiteSpace(data.localClientId) &&
            !string.IsNullOrWhiteSpace(data.kcGs);

        //Debug.Log(
        //    $"[AuthSessionPersistence] HasReconnectForUser userId={currentUserId}, " +
        //    $"has={has}, room={data.roomId}, local={data.localClientId}, " +
        //    $"session={data.sessionId}, kcGs={(string.IsNullOrWhiteSpace(data.kcGs) ? "empty" : "set")}"
        //);

        return has;
    }

    /// <summary>
    /// 点击“重新连接”时调用。
    /// 它只恢复重连需要的字段，不恢复 username/tgt/serviceTicket 等登录态。
    /// 当前用户必须已经重新登录。
    /// </summary>
    public static bool RestoreReconnectForUser(long currentUserId)
    {
        if (currentUserId <= 0)
            return false;

        if (!TryReadSaveDataForUser(currentUserId, out SaveData data))
            return false;

        if (data.userId != currentUserId)
        {
            Debug.LogWarning(
                $"[AuthSessionPersistence] Restore failed: saved userId={data.userId}, currentUserId={currentUserId}."
            );

            ClearForUser(data.userId);
            return false;
        }

        if (string.IsNullOrWhiteSpace(data.sessionId) ||
            string.IsNullOrWhiteSpace(data.roomId) ||
            string.IsNullOrWhiteSpace(data.localClientId) ||
            string.IsNullOrWhiteSpace(data.kcGs))
        {
            Debug.LogWarning(
                $"[AuthSessionPersistence] Restore failed: incomplete saved reconnect fields. " +
                $"session={data.sessionId}, room={data.roomId}, local={data.localClientId}, " +
                $"kcGs={(string.IsNullOrWhiteSpace(data.kcGs) ? "empty" : "set")}"
            );

            ClearForUser(currentUserId);
            return false;
        }

        AuthContext ctx = AuthSession.Ctx;

        // 保留当前刚登录拿到的新 AS/TGS 身份。
        // 这里只恢复“旧对局重连”必需字段。
        ctx.sessionId = data.sessionId ?? "";
        ctx.gsSessionExpireAtMs = data.gsSessionExpireAtMs;

        ctx.roomId = data.roomId ?? "";
        ctx.localClientId = data.localClientId ?? "";
        ctx.localSlotNo = data.localSlotNo;
        ctx.localIsHost = data.localIsHost;

        // 你的服务器 RECONNECT_REQ 当前使用旧 kcGs 解密 auth/payload，
        // 所以这里必须恢复旧 kcGs。
        ctx.kcGs = data.kcGs ?? "";

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.SyncFromAuthSession();

        Debug.Log(
            $"[AuthSessionPersistence] Restored reconnect fields for userId={currentUserId}. " +
            $"room={ctx.roomId}, local={ctx.localClientId}, session={ctx.sessionId}"
        );

        return true;
    }

    /// <summary>
    /// 清理旧全局 Key，以及当前 AuthSession.Ctx.userId 对应的新 Key。
    /// </summary>
    public static void Clear()
    {
        PlayerPrefs.DeleteKey(LegacyKey);

        AuthContext ctx = AuthSession.Ctx;

        if (ctx != null && ctx.userId > 0)
            PlayerPrefs.DeleteKey(GetKey(ctx.userId));

        PlayerPrefs.Save();

        Debug.Log("[AuthSessionPersistence] Cleared legacy key and current user's saved session.");
    }

    public static void ClearForUser(long userId)
    {
        if (userId <= 0)
            return;

        string key = GetKey(userId);

        PlayerPrefs.DeleteKey(key);
        PlayerPrefs.Save();

        Debug.Log($"[AuthSessionPersistence] Cleared saved session for userId={userId}, key={key}");
    }

    public static void DebugDumpReconnectForUser(long currentUserId)
    {
        Debug.Log($"[AuthSessionPersistence] DebugDumpReconnectForUser currentUserId={currentUserId}");

        string key = GetKey(currentUserId);

        if (!PlayerPrefs.HasKey(key))
        {
            Debug.Log($"[AuthSessionPersistence] No saved session key={key}.");

            if (PlayerPrefs.HasKey(LegacyKey))
                Debug.Log($"[AuthSessionPersistence] Legacy key exists: {LegacyKey}");

            return;
        }

        try
        {
            string encoded = PlayerPrefs.GetString(key, "");

            Debug.Log($"[AuthSessionPersistence] Raw Base64 key={key}:\n{encoded}");

            string json = Encoding.UTF8.GetString(Convert.FromBase64String(encoded));

            Debug.Log("[AuthSessionPersistence] Saved JSON:\n" + json);

            SaveData data = JsonUtility.FromJson<SaveData>(json);

            if (data == null)
            {
                Debug.LogWarning("[AuthSessionPersistence] Saved data parse null.");
                return;
            }

            bool canReconnect =
                data.userId == currentUserId &&
                !string.IsNullOrWhiteSpace(data.sessionId) &&
                !string.IsNullOrWhiteSpace(data.roomId) &&
                !string.IsNullOrWhiteSpace(data.localClientId) &&
                !string.IsNullOrWhiteSpace(data.kcGs);

            Debug.Log(
                $"[AuthSessionPersistence] savedUserId={data.userId}, currentUserId={currentUserId}, " +
                $"username={data.username}, session={data.sessionId}, room={data.roomId}, " +
                $"local={data.localClientId}, kcGs={(string.IsNullOrWhiteSpace(data.kcGs) ? "empty" : "set")}, " +
                $"canReconnect={canReconnect}"
            );
        }
        catch (Exception ex)
        {
            Debug.LogWarning("[AuthSessionPersistence] DebugDump failed: " + ex);
        }
    }

    private static bool LoadForUser(long userId, bool restoreFullAuthSession)
    {
        if (!TryReadSaveDataForUser(userId, out SaveData data))
            return false;

        long now = NowMs();

        // 这里不强制判断 serviceTicketExpireAtMs，因为你的重连方案是：
        // 先重新登录，再恢复旧 kcGs/sessionId/roomId 用于 RECONNECT_REQ。
        // 如果以后服务器改成新 ticket 认领旧 session，可以再调整这里。

        if (restoreFullAuthSession)
        {
            AuthSession session = AuthSession.EnsureExists();
            AuthContext ctx = AuthSession.Ctx;

            ctx.userId = data.userId;
            ctx.username = data.username ?? "";
            ctx.clientId = data.clientId ?? "";

            ctx.tgt = data.tgt ?? "";
            ctx.kcTgs = data.kcTgs ?? "";
            ctx.tgtExpireAtMs = data.tgtExpireAtMs;
            ctx.loginGen = data.loginGen;

            ctx.serviceTicket = data.serviceTicket ?? "";
            ctx.kcGs = data.kcGs ?? "";
            ctx.serviceTicketExpireAtMs = data.serviceTicketExpireAtMs;

            ctx.sessionId = data.sessionId ?? "";
            ctx.gsSessionExpireAtMs = data.gsSessionExpireAtMs;

            ctx.roomId = data.roomId ?? "";
            ctx.localClientId = data.localClientId ?? "";
            ctx.localSlotNo = data.localSlotNo;
            ctx.localIsHost = data.localIsHost;

            session.EnsureClientId();

            if (NetworkSession.Instance != null)
                NetworkSession.Instance.SyncFromAuthSession();

            Debug.Log(
                $"[AuthSessionPersistence] Loaded full session for userId={userId}. " +
                $"room={ctx.roomId}, local={ctx.localClientId}, session={ctx.sessionId}"
            );
        }

        return true;
    }

    private static bool TryReadSaveDataForUser(long userId, out SaveData data)
    {
        data = null;

        if (userId <= 0)
            return false;

        string key = GetKey(userId);

        if (!PlayerPrefs.HasKey(key))
        {
            Debug.Log($"[AuthSessionPersistence] No saved session for userId={userId}, key={key}.");
            return false;
        }

        try
        {
            string encoded = PlayerPrefs.GetString(key, "");

            if (string.IsNullOrWhiteSpace(encoded))
            {
                Debug.LogWarning($"[AuthSessionPersistence] Saved value empty. key={key}");
                return false;
            }

            string json = Encoding.UTF8.GetString(Convert.FromBase64String(encoded));
            data = JsonUtility.FromJson<SaveData>(json);

            if (data == null)
            {
                Debug.LogWarning($"[AuthSessionPersistence] SaveData parse null. key={key}");
                return false;
            }

            return true;
        }
        catch (Exception ex)
        {
            Debug.LogWarning($"[AuthSessionPersistence] Read failed. key={key}, ex={ex.Message}");
            PlayerPrefs.DeleteKey(key);
            PlayerPrefs.Save();
            return false;
        }
    }

    private static long NowMs()
    {
        return DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
    }
}