using UnityEngine;

public class AuthSession : MonoBehaviour
{
    public static AuthSession Instance { get; private set; }

    [SerializeField] private AuthContext context = new AuthContext();

    public AuthContext Context => context;

    public static AuthSession EnsureExists()
    {
        if (Instance != null)
            return Instance;

        GameObject go = new GameObject("AuthSession");
        Instance = go.AddComponent<AuthSession>();
        DontDestroyOnLoad(go);
        return Instance;
    }

    public static AuthContext Ctx
    {
        get
        {
            return EnsureExists().Context;
        }
    }

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);

        EnsureClientId();
    }

    // ------------------------------------------------------------
    // ClientId
    // ------------------------------------------------------------

    public void EnsureClientId()
    {
        if (!string.IsNullOrWhiteSpace(context.clientId))
            return;

        context.clientId = "cli_" + System.Guid.NewGuid().ToString("N");

        Debug.Log($"[AuthSession] Generated clientId={context.clientId}");
    }

    // ------------------------------------------------------------
    // AS 登录结果
    // ------------------------------------------------------------

    public void ApplyAsLogin(
        long userId,
        string username,
        string tgt,
        string kcTgs,
        long expMs,
        long loginGen
    )
    {
        context.userId = userId;
        context.username = username ?? "";

        context.tgt = tgt ?? "";
        context.kcTgs = kcTgs ?? "";
        context.tgtExpireAtMs = expMs;
        context.loginGen = loginGen;

        Debug.Log(
            $"[AuthSession] ApplyAsLogin " +
            $"userId={context.userId}, username={context.username}, " +
            $"tgt={(string.IsNullOrWhiteSpace(context.tgt) ? "empty" : "set")}, " +
            $"kcTgs={(string.IsNullOrWhiteSpace(context.kcTgs) ? "empty" : "set")}, " +
            $"exp={context.tgtExpireAtMs}, loginGen={context.loginGen}"
        );
    }

    // ------------------------------------------------------------
    // TGS 换票结果
    // ------------------------------------------------------------

    public void ApplyTgsTicket(
        string serviceTicket,
        string kcGs,
        long expMs
    )
    {
        context.serviceTicket = serviceTicket ?? "";
        context.kcGs = kcGs ?? "";
        context.serviceTicketExpireAtMs = expMs;

        Debug.Log(
            $"[AuthSession] ApplyTgsTicket " +
            $"serviceTicket={(string.IsNullOrWhiteSpace(context.serviceTicket) ? "empty" : "set")}, " +
            $"kcGs={(string.IsNullOrWhiteSpace(context.kcGs) ? "empty" : "set")}, " +
            $"exp={context.serviceTicketExpireAtMs}"
        );
    }

    // ------------------------------------------------------------
    // GS_AUTH_OK
    // ------------------------------------------------------------

    public void ApplyGsAuthOk(
        string sessionId,
        long expMs = 0
    )
    {
        context.sessionId = sessionId ?? "";
        context.gsSessionExpireAtMs = expMs;

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.ApplyGsSession(context.sessionId);

        Debug.Log(
            $"[AuthSession] ApplyGsAuthOk " +
            $"sessionId={context.sessionId}, exp={context.gsSessionExpireAtMs}"
        );
    }

    // ------------------------------------------------------------
    // 房间身份
    // ------------------------------------------------------------

    public void ApplyRoomIdentity(
        string roomId,
        string localClientId,
        int localSlotNo,
        bool localIsHost
    )
    {
        context.roomId = roomId ?? "";
        context.localClientId = localClientId ?? "";
        context.localSlotNo = localSlotNo;
        context.localIsHost = localIsHost;

        Debug.Log(
            $"[AuthSession] ApplyRoomIdentity " +
            $"room={context.roomId}, localClientId={context.localClientId}, " +
            $"slot={context.localSlotNo}, isHost={context.localIsHost}"
        );
    }

    // ------------------------------------------------------------
    // Validate helpers
    // ------------------------------------------------------------

    public bool ValidateTgtReady()
    {
        if (!context.HasTgt)
        {
            Debug.LogWarning("[AuthSession] TGT/KcTgs missing.");
            return false;
        }

        try
        {
            ClientCrypto.RequireDesKeyBase64(context.kcTgs, "KcTgs");
            return true;
        }
        catch (System.Exception ex)
        {
            Debug.LogError($"[AuthSession] Invalid KcTgs: {ex.Message}");
            return false;
        }
    }

    public bool ValidateGsTicketReady()
    {
        if (!context.HasServiceTicket)
        {
            Debug.LogWarning("[AuthSession] ServiceTicket/KcGs missing.");
            return false;
        }

        try
        {
            ClientCrypto.RequireDesKeyBase64(context.kcGs, "KcGs");
            return true;
        }
        catch (System.Exception ex)
        {
            Debug.LogError($"[AuthSession] Invalid KcGs: {ex.Message}");
            return false;
        }
    }

    // ------------------------------------------------------------
    // Clear
    // ------------------------------------------------------------

    public void ClearRoom()
    {
        context.ClearRoom();
    }

    public void ClearTicketsAndSession()
    {
        context.ClearTicketsAndSession();
    }

    public void ClearAll()
    {
        context.ClearAll();
        EnsureClientId();
    }
}