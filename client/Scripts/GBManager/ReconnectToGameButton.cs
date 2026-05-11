using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class ReconnectToGameButton : MonoBehaviour
{
    [Header("Button")]
    [SerializeField] private Button button;

    [Header("Visible Root")]
    [Tooltip("建议拖按钮本体或按钮外层容器。不要拖挂着本脚本的对象，如果你打算 SetActive 隐藏。")]
    [SerializeField] private GameObject visibleRoot;

    [Header("Scene")]
    [SerializeField] private string mainGameSceneName = "MainGame";

    [Header("Behavior")]
    [SerializeField] private bool hideWhenCannotReconnect = true;

    private bool reconnecting;
    private CanvasGroup canvasGroup;

    private void Awake()
    {
        if (button == null)
            button = GetComponent<Button>();

        if (visibleRoot == null)
            visibleRoot = button != null ? button.gameObject : gameObject;

        canvasGroup = visibleRoot.GetComponent<CanvasGroup>();

        if (canvasGroup == null)
            canvasGroup = visibleRoot.AddComponent<CanvasGroup>();

        if (button != null)
        {
            button.onClick.RemoveListener(OnClickReconnect);
            button.onClick.AddListener(OnClickReconnect);
        }
    }

    private void OnEnable()
    {
        RefreshVisible();
    }

    private void Update()
    {
        RefreshVisible();
    }

    private void RefreshVisible()
    {
        bool canReconnect = CanReconnectCandidate();

        if (button != null)
            button.interactable = canReconnect && !reconnecting;

        if (hideWhenCannotReconnect && canvasGroup != null)
        {
            canvasGroup.alpha = canReconnect ? 1f : 0f;
            canvasGroup.interactable = canReconnect;
            canvasGroup.blocksRaycasts = canReconnect;
        }
    }

    /// <summary>
    /// 这里只判断“当前登录账号是否有本地保存的可重连记录”。
    /// 注意：这里不要要求 ctx.sessionId / roomId / localClientId，
    /// 因为这些旧对局信息还没 Restore 到 AuthSession.Ctx。
    /// </summary>
    private bool CanReconnectCandidate()
    {
        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null)
            return false;

        if (ctx.userId <= 0)
            return false;

        // 必须已经登录并拿到当前账号的 ServiceTicket。
        if (!ctx.HasServiceTicket)
            return false;

        // 本地保存的旧对局必须属于当前登录 userId。
        return AuthSessionPersistence.HasReconnectForUser(ctx.userId);
    }

    /// <summary>
    /// Restore 之后，才检查 AuthSession.Ctx 里面是否真的有完整重连信息。
    /// </summary>
    private bool HasRestoredReconnectSession()
    {
        AuthContext ctx = AuthSession.Ctx;

        return ctx != null
               && ctx.userId > 0
               && ctx.HasServiceTicket
               && !string.IsNullOrWhiteSpace(ctx.kcGs)
               && !string.IsNullOrWhiteSpace(ctx.sessionId)
               && !string.IsNullOrWhiteSpace(ctx.roomId)
               && !string.IsNullOrWhiteSpace(ctx.localClientId);
    }

    public async void OnClickReconnect()
    {
        if (reconnecting)
            return;

        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null || ctx.userId <= 0 || !ctx.HasServiceTicket)
        {
            GameAlert.Show(
                "请先登录",
                "重新连接前需要先登录账号。",
                "确定"
            );
            return;
        }

        if (!AuthSessionPersistence.RestoreReconnectForUser(ctx.userId))
        {
            GameAlert.Show(
                "无法重连",
                "没有找到当前账号可重连的对局，或者重连信息已失效。",
                "确定"
            );
            return;
        }

        if (!HasRestoredReconnectSession())
        {
            GameAlert.Show(
                "无法重连",
                "本地重连信息不完整，请返回大厅重新创建或加入房间。",
                "确定"
            );

            AuthSessionPersistence.Clear();
            return;
        }

        if (RelayChatClient.Instance == null)
        {
            GameAlert.Show(
                "网络组件缺失",
                "找不到 RelayChatClient，无法重新连接。",
                "确定"
            );
            return;
        }

        reconnecting = true;
        RefreshVisible();

        Debug.Log(
            $"[ReconnectButton] 尝试重连：room={AuthSession.Ctx.roomId}, " +
            $"localClientId={AuthSession.Ctx.localClientId}, " +
            $"sessionId={AuthSession.Ctx.sessionId}, " +
            $"userId={AuthSession.Ctx.userId}"
        );

        bool ok = await RelayChatClient.Instance.ReconnectToGameAsync();

        if (ok)
        {
            Debug.Log("[ReconnectButton] 重连成功，进入 MainGame。");
            SceneManager.LoadScene(mainGameSceneName);
            return;
        }

        Debug.LogWarning("[ReconnectButton] 重连失败。");

        reconnecting = false;
        RefreshVisible();

        GameAlert.Show(
            "重连失败",
            "服务器上的对局可能已经结束，或者重连时间已过。",
            "确定"
        );
    }
}