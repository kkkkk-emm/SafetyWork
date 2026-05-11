using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using DG.Tweening;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class LobbyManager : MonoBehaviour
{
    [Header("核心引用")]
    [SerializeField] private RelayChatClient relayClient;
    [SerializeField] private MainMenuManager mainMenuManager;

    [Header("房间视觉面板")]
    [Tooltip("整个房间 LobbyPanel，默认 inactive。创建/加入成功后会从上方拉下来。")]
    [SerializeField] private RectTransform lobbyPanelRoot;
    [SerializeField] private CanvasGroup lobbyCanvasGroup;

    [Header("加入房间弹窗")]
    [SerializeField] private GameObject joinRoomPanel;
    [SerializeField] private CanvasGroup joinRoomCanvasGroup;

    [Tooltip("外面的 加入房间 按钮：只负责打开 JoinRoomPanel")]
    [SerializeField] private Button openJoinRoomPanelButton;

    [Tooltip("JoinRoomPanel 里的 确定加入 按钮：真正发送 JOIN 请求")]
    [SerializeField] private Button confirmJoinRoomButton;

    [Tooltip("JoinRoomPanel 里的 返回 按钮：关闭 JoinRoomPanel")]
    [SerializeField] private Button closeJoinRoomPanelButton;

    [Header("房间 UI")]
    [SerializeField] private TMP_InputField roomCodeInput;
    [SerializeField] private TMP_Text roomCodeText;
    [SerializeField] private TMP_Text statusText;

    [Header("动态玩家卡片")]
    [SerializeField] private Transform playerCardRoot;
    [SerializeField] private LobbyPlayerCard playerCardPrefab;

    [Header("玩家头像，可选")]
    [SerializeField] private Sprite player1Portrait;
    [SerializeField] private Sprite player2Portrait;

    [Header("按钮")]
    [Tooltip("外面的 创建房间 按钮")]
    [SerializeField] private Button createRoomButton;

    [Tooltip("LobbyPanel 里的 START 按钮")]
    [SerializeField] private Button startButton;

    [Tooltip("LobbyPanel 里的返回按钮")]
    [SerializeField] private Button backButton;

    [Header("Lobby 面板下拉动画")]
    [SerializeField] private float lobbyDropOffsetY = 900f;
    [SerializeField] private float lobbyDropDuration = 0.42f;
    [SerializeField] private Ease lobbyDropEase = Ease.OutCubic;
    [SerializeField] private Ease lobbyCloseEase = Ease.InCubic;

    [Header("加入房间弹窗动画")]
    [SerializeField] private float joinPanelFadeDuration = 0.18f;
    [SerializeField] private float joinPanelScaleDuration = 0.22f;
    [SerializeField] private float joinPanelHiddenScale = 0.92f;
    [SerializeField] private Ease joinPanelOpenEase = Ease.OutBack;
    [SerializeField] private Ease joinPanelCloseEase = Ease.InQuad;

    [Header("玩家卡片动画")]
    [SerializeField] private bool useCardTween = true;
    [SerializeField] private float cardEnterDuration = 0.32f;
    [SerializeField] private float cardExitDuration = 0.18f;
    [SerializeField] private float cardSlideOffsetY = 80f;
    [SerializeField] private float cardStartScale = 0.94f;
    [SerializeField] private Ease cardEnterEase = Ease.OutBack;
    [SerializeField] private Ease cardExitEase = Ease.InQuad;

    [Header("调试")]
    [SerializeField] private bool debugLog = true;

    private readonly Dictionary<string, LobbyPlayerCard> playerCards =
        new Dictionary<string, LobbyPlayerCard>();

    private readonly Dictionary<string, CanvasGroup> cardCanvasGroups =
        new Dictionary<string, CanvasGroup>();

    private static bool globalRoomActionInFlight;

    private RoomStatePayload currentRoomState;
    private bool localReady;

    private bool pendingOpenLobbyAfterRoomAction;
    private bool lobbyPanelOpened;

    private Vector2 lobbyOriginalAnchoredPos;
    private Sequence lobbyPanelSeq;

    private Sequence joinPanelSeq;
    private Vector3 joinPanelOriginalScale = Vector3.one;
    private bool loginAlertShowing;
    private void Awake()
    {
        if (relayClient == null)
            relayClient = RelayChatClient.Instance;

        if (relayClient == null)
            relayClient = FindFirstObjectByType<RelayChatClient>();

        PrepareLobbyPanelAnimation();
        PrepareJoinRoomPanel();

        BindButtons();
        SubscribeRelayEvents();

        CloseLobbyPanelInstant();
        CloseJoinRoomPanelInstant();

        RefreshEmptyLobby();
    }

    private void OnEnable()
    {
        SubscribeRelayEvents();
        RefreshFromCurrentState();

        UserInfoPanel.ShowCurrentUserIfLoggedIn();
    }

    private void OnDisable()
    {
        // 不在这里退订，避免 UI 被隐藏后收不到 ROOM_STATE。
        // 真正销毁时在 OnDestroy 里退订。
    }

    private void OnDestroy()
    {
        lobbyPanelSeq?.Kill();
        joinPanelSeq?.Kill();

        foreach (CanvasGroup group in cardCanvasGroups.Values)
        {
            if (group != null)
                group.DOKill();
        }

        foreach (LobbyPlayerCard card in playerCards.Values)
        {
            if (card == null)
                continue;

            card.transform.DOKill();

            RectTransform rt = card.transform as RectTransform;

            if (rt != null)
                rt.DOKill();
        }

        if (relayClient != null)
        {
            relayClient.OnRoomStateReceived -= HandleRoomState;
            relayClient.OnGameStartReceived -= HandleGameStart;
        }
    }

    // ============================================================
    // Init / Binding
    // ============================================================

    private void BindButtons()
    {
        if (createRoomButton != null)
        {
            createRoomButton.onClick.RemoveListener(OnClickCreateRoomAndEnter);
            createRoomButton.onClick.AddListener(OnClickCreateRoomAndEnter);
        }

        if (openJoinRoomPanelButton != null)
        {
            openJoinRoomPanelButton.onClick.RemoveListener(OpenJoinRoomPanel);
            openJoinRoomPanelButton.onClick.AddListener(OpenJoinRoomPanel);
        }

        if (confirmJoinRoomButton != null)
        {
            confirmJoinRoomButton.onClick.RemoveListener(OnClickConfirmJoinRoom);
            confirmJoinRoomButton.onClick.AddListener(OnClickConfirmJoinRoom);
        }

        if (closeJoinRoomPanelButton != null)
        {
            closeJoinRoomPanelButton.onClick.RemoveListener(CloseJoinRoomPanel);
            closeJoinRoomPanelButton.onClick.AddListener(CloseJoinRoomPanel);
        }

        if (startButton != null)
        {
            startButton.onClick.RemoveListener(OnClickStartGame);
            startButton.onClick.AddListener(OnClickStartGame);
        }

        if (backButton != null)
        {
            backButton.onClick.RemoveListener(OnClickBackButton);
            backButton.onClick.AddListener(OnClickBackButton);
        }
    }

    private void SubscribeRelayEvents()
    {
        RelayChatClient target = RelayChatClient.Instance;

        if (target == null)
            target = FindFirstObjectByType<RelayChatClient>();

        if (target == null)
        {
            Debug.LogError("[LobbyManager] SubscribeRelayEvents failed: RelayChatClient not found.");
            return;
        }

        // 如果之前订阅的是旧 RelayClient，先从旧对象退订
        if (relayClient != null && relayClient != target)
        {
            relayClient.OnRoomStateReceived -= HandleRoomState;
            relayClient.OnGameStartReceived -= HandleGameStart;

            Debug.LogWarning(
                $"[LobbyManager] RelayClient changed. old={relayClient.name}, new={target.name}"
            );
        }

        relayClient = target;

        relayClient.OnRoomStateReceived -= HandleRoomState;
        relayClient.OnRoomStateReceived += HandleRoomState;

        relayClient.OnGameStartReceived -= HandleGameStart;
        relayClient.OnGameStartReceived += HandleGameStart;

        Debug.Log(
            $"[LobbyManager] Subscribed relay events. " +
            $"relay={relayClient.name}, instance={RelayChatClient.Instance?.name}"
        );
    }
    private void PrepareLobbyPanelAnimation()
    {
        if (lobbyPanelRoot == null)
            lobbyPanelRoot = transform as RectTransform;

        if (lobbyCanvasGroup == null && lobbyPanelRoot != null)
            lobbyCanvasGroup = lobbyPanelRoot.GetComponent<CanvasGroup>();

        if (lobbyCanvasGroup == null && lobbyPanelRoot != null)
            lobbyCanvasGroup = lobbyPanelRoot.gameObject.AddComponent<CanvasGroup>();

        if (lobbyPanelRoot != null)
            lobbyOriginalAnchoredPos = lobbyPanelRoot.anchoredPosition;
    }

    private void PrepareJoinRoomPanel()
    {
        if (joinRoomPanel == null)
            return;

        joinPanelOriginalScale = joinRoomPanel.transform.localScale;

        if (joinRoomCanvasGroup == null)
            joinRoomCanvasGroup = joinRoomPanel.GetComponent<CanvasGroup>();

        if (joinRoomCanvasGroup == null)
            joinRoomCanvasGroup = joinRoomPanel.AddComponent<CanvasGroup>();
    }

    // ============================================================
    // JoinRoomPanel
    // ============================================================

    public void OpenJoinRoomPanel()
    {
        if (AuthSession.Ctx == null ||
      string.IsNullOrWhiteSpace(AuthSession.Ctx.serviceTicket) ||
      string.IsNullOrWhiteSpace(AuthSession.Ctx.kcGs))
        {
            SetStatus("请先登录。");
            ShowNeedLoginAlert();
            return;
        }

        if (joinRoomPanel == null)
        {
            Debug.LogError("[LobbyManager] Join Room Panel 没有绑定。");
            return;
        }

        joinPanelSeq?.Kill();

        joinRoomPanel.SetActive(true);
        joinRoomPanel.transform.SetAsLastSibling();

        joinRoomPanel.transform.localScale = joinPanelOriginalScale * joinPanelHiddenScale;

        if (joinRoomCanvasGroup != null)
        {
            joinRoomCanvasGroup.alpha = 0f;
            joinRoomCanvasGroup.interactable = false;
            joinRoomCanvasGroup.blocksRaycasts = false;
        }

        if (roomCodeInput != null)
            roomCodeInput.text = "";

        joinPanelSeq = DOTween.Sequence();

        if (joinRoomCanvasGroup != null)
        {
            joinPanelSeq.Join(
                joinRoomCanvasGroup
                    .DOFade(1f, joinPanelFadeDuration)
                    .SetEase(Ease.OutQuad)
            );
        }

        joinPanelSeq.Join(
            joinRoomPanel.transform
                .DOScale(joinPanelOriginalScale, joinPanelScaleDuration)
                .SetEase(joinPanelOpenEase)
        );

        joinPanelSeq.OnComplete(() =>
        {
            joinRoomPanel.transform.localScale = joinPanelOriginalScale;

            if (joinRoomCanvasGroup != null)
            {
                joinRoomCanvasGroup.alpha = 1f;
                joinRoomCanvasGroup.interactable = true;
                joinRoomCanvasGroup.blocksRaycasts = true;
            }

            if (roomCodeInput != null)
                roomCodeInput.ActivateInputField();

            if (debugLog)
                Debug.Log("[LobbyManager] OpenJoinRoomPanel");
        });
    }

    public void CloseJoinRoomPanel()
    {
        if (joinRoomPanel == null)
            return;

        joinPanelSeq?.Kill();

        if (joinRoomCanvasGroup != null)
        {
            joinRoomCanvasGroup.interactable = false;
            joinRoomCanvasGroup.blocksRaycasts = false;
        }

        joinPanelSeq = DOTween.Sequence();

        if (joinRoomCanvasGroup != null)
        {
            joinPanelSeq.Join(
                joinRoomCanvasGroup
                    .DOFade(0f, joinPanelFadeDuration)
                    .SetEase(Ease.OutQuad)
            );
        }

        joinPanelSeq.Join(
            joinRoomPanel.transform
                .DOScale(joinPanelOriginalScale * joinPanelHiddenScale, joinPanelScaleDuration)
                .SetEase(joinPanelCloseEase)
        );

        joinPanelSeq.OnComplete(() =>
        {
            joinRoomPanel.SetActive(false);
            joinRoomPanel.transform.localScale = joinPanelOriginalScale;

            if (joinRoomCanvasGroup != null)
            {
                joinRoomCanvasGroup.alpha = 1f;
                joinRoomCanvasGroup.interactable = true;
                joinRoomCanvasGroup.blocksRaycasts = true;
            }

            if (debugLog)
                Debug.Log("[LobbyManager] CloseJoinRoomPanel");
        });
    }

    private void CloseJoinRoomPanelInstant()
    {
        joinPanelSeq?.Kill();

        if (joinRoomPanel != null)
        {
            joinRoomPanel.transform.localScale = joinPanelOriginalScale;
            joinRoomPanel.SetActive(false);
        }

        if (joinRoomCanvasGroup != null)
        {
            joinRoomCanvasGroup.alpha = 1f;
            joinRoomCanvasGroup.interactable = true;
            joinRoomCanvasGroup.blocksRaycasts = true;
        }
    }

    // ============================================================
    // LobbyPanel
    // ============================================================

    public void OpenLobbyPanelWithDropDown()
    {
        if (lobbyPanelRoot == null)
        {
            Debug.LogError("[LobbyManager] LobbyPanelRoot 没有绑定！请把整个 LobbyPanel 拖到 Lobby Panel Root。");
            return;
        }

        if (lobbyCanvasGroup == null)
        {
            lobbyCanvasGroup = lobbyPanelRoot.GetComponent<CanvasGroup>();

            if (lobbyCanvasGroup == null)
                lobbyCanvasGroup = lobbyPanelRoot.gameObject.AddComponent<CanvasGroup>();
        }

        if (debugLog)
        {
            Debug.Log(
                $"[LobbyManager] OpenLobbyPanelWithDropDown root={lobbyPanelRoot.name}, " +
                $"parent={(lobbyPanelRoot.parent != null ? lobbyPanelRoot.parent.name : "NULL")}, " +
                $"parentActive={(lobbyPanelRoot.parent != null ? lobbyPanelRoot.parent.gameObject.activeInHierarchy : true)}"
            );
        }

        lobbyPanelRoot.gameObject.SetActive(true);
        lobbyPanelRoot.SetAsLastSibling();

        if (!lobbyPanelRoot.gameObject.activeInHierarchy)
        {
            Debug.LogError(
                "[LobbyManager] LobbyPanel 已 SetActive(true)，但 activeInHierarchy=false。 " +
                "说明它的父物体是 inactive。请把 LobbyPanel 移到 Canvas 直属层级。"
            );
            return;
        }

        lobbyPanelOpened = true;

        PlayLobbyDropDown();
    }

    public void CloseLobbyPanelInstant()
    {
        lobbyPanelSeq?.Kill();

        if (lobbyPanelRoot != null)
        {
            lobbyPanelRoot.anchoredPosition = lobbyOriginalAnchoredPos;
            lobbyPanelRoot.gameObject.SetActive(false);
        }

        if (lobbyCanvasGroup != null)
        {
            lobbyCanvasGroup.alpha = 1f;
            lobbyCanvasGroup.interactable = true;
            lobbyCanvasGroup.blocksRaycasts = true;
        }

        lobbyPanelOpened = false;
        pendingOpenLobbyAfterRoomAction = false;
    }

    private void PlayLobbyDropDown()
    {
        if (lobbyPanelRoot == null || lobbyCanvasGroup == null)
        {
            Debug.LogError("[LobbyManager] PlayLobbyDropDown failed: lobbyPanelRoot 或 lobbyCanvasGroup 为空。");
            return;
        }

        lobbyPanelSeq?.Kill();

        Vector2 targetPos = lobbyOriginalAnchoredPos;
        Vector2 startPos = targetPos + new Vector2(0f, lobbyDropOffsetY);

        lobbyPanelRoot.gameObject.SetActive(true);
        lobbyPanelRoot.SetAsLastSibling();

        lobbyPanelRoot.anchoredPosition = startPos;

        lobbyCanvasGroup.alpha = 0f;
        lobbyCanvasGroup.interactable = false;
        lobbyCanvasGroup.blocksRaycasts = false;

        if (debugLog)
        {
            Debug.Log(
                $"[LobbyManager] PlayLobbyDropDown start={startPos}, " +
                $"target={targetPos}, active={lobbyPanelRoot.gameObject.activeInHierarchy}"
            );
        }

        lobbyPanelSeq = DOTween.Sequence();

        lobbyPanelSeq.Join(
            lobbyPanelRoot
                .DOAnchorPos(targetPos, lobbyDropDuration)
                .SetEase(lobbyDropEase)
        );

        lobbyPanelSeq.Join(
            lobbyCanvasGroup
                .DOFade(1f, lobbyDropDuration * 0.75f)
                .SetEase(Ease.OutQuad)
        );

        lobbyPanelSeq.OnComplete(() =>
        {
            lobbyPanelRoot.anchoredPosition = targetPos;
            lobbyCanvasGroup.alpha = 1f;
            lobbyCanvasGroup.interactable = true;
            lobbyCanvasGroup.blocksRaycasts = true;

            if (debugLog)
            {
                Debug.Log(
                    $"[LobbyManager] LobbyPanel opened. " +
                    $"active={lobbyPanelRoot.gameObject.activeInHierarchy}, " +
                    $"pos={lobbyPanelRoot.anchoredPosition}"
                );
            }
        });
    }

    private async Task PlayLobbyDropUpAndWait()
    {
        if (lobbyPanelRoot == null || lobbyCanvasGroup == null)
            return;

        lobbyPanelSeq?.Kill();

        Vector2 targetPos = lobbyOriginalAnchoredPos + new Vector2(0f, lobbyDropOffsetY);

        lobbyCanvasGroup.interactable = false;
        lobbyCanvasGroup.blocksRaycasts = false;

        bool done = false;

        lobbyPanelSeq = DOTween.Sequence();

        lobbyPanelSeq.Join(
            lobbyPanelRoot
                .DOAnchorPos(targetPos, lobbyDropDuration * 0.75f)
                .SetEase(lobbyCloseEase)
        );

        lobbyPanelSeq.Join(
            lobbyCanvasGroup
                .DOFade(0f, lobbyDropDuration * 0.6f)
                .SetEase(Ease.OutQuad)
        );

        lobbyPanelSeq.OnComplete(() =>
        {
            lobbyPanelRoot.anchoredPosition = lobbyOriginalAnchoredPos;
            lobbyPanelRoot.gameObject.SetActive(false);

            lobbyCanvasGroup.alpha = 1f;
            lobbyCanvasGroup.interactable = true;
            lobbyCanvasGroup.blocksRaycasts = true;

            lobbyPanelOpened = false;
            done = true;
        });

        while (!done)
            await Task.Delay(10);
    }

    // ============================================================
    // Button callbacks
    // ============================================================

    public async void OnClickCreateRoomAndEnter()
    {
        if (globalRoomActionInFlight)
        {
            Debug.LogWarning("[LobbyManager] 创建房间请求正在进行中，忽略重复点击。");
            return;
        }
        if (!await EnsureRelayReady())
            return;

        globalRoomActionInFlight = true;
        pendingOpenLobbyAfterRoomAction = true;

        SetStatus("正在创建房间...");

        try
        {
            if (NetworkSession.Instance != null &&
                !string.IsNullOrWhiteSpace(NetworkSession.Instance.roomId))
            {
                await relayClient.LeaveRoom();
                relayClient.ClearLocalRoomState();

                NetworkSession.Instance.ClearRoom();
                AuthSession.EnsureExists().ClearRoom();
            }

            await relayClient.SendCreateRoom();

            if (debugLog)
                Debug.Log("[LobbyManager] Send ROOM_CREATE_REQ");
        }
        catch (Exception ex)
        {
            globalRoomActionInFlight = false;
            pendingOpenLobbyAfterRoomAction = false;
            SetStatus("创建房间失败：" + ex.Message);
            Debug.LogError("[LobbyManager] Create room failed: " + ex);
        }
    }

    public async void OnClickConfirmJoinRoom()
    {
        if (globalRoomActionInFlight)
        {
            Debug.LogWarning("[LobbyManager] 加入房间请求正在进行中，忽略重复点击。");
            return;
        }

        if (!await EnsureRelayReady())
            return;

        string wantedRoomId = roomCodeInput != null
            ? roomCodeInput.text.Trim().ToUpper()
            : "";

        if (string.IsNullOrWhiteSpace(wantedRoomId))
        {
            SetStatus("请输入房间号。");
            return;
        }

        globalRoomActionInFlight = true;
        pendingOpenLobbyAfterRoomAction = true;

        CloseJoinRoomPanel();

        SetStatus($"正在加入房间 {wantedRoomId}...");

        try
        {
            await relayClient.SendJoinRoomManual("", wantedRoomId);

            if (debugLog)
                Debug.Log($"[LobbyManager] Send ROOM_JOIN_REQ room={wantedRoomId}");
        }
        catch (Exception ex)
        {
            globalRoomActionInFlight = false;
            pendingOpenLobbyAfterRoomAction = false;
            SetStatus("加入房间失败：" + ex.Message);
            Debug.LogError("[LobbyManager] Join room failed: " + ex);
        }
    }

    public async void OnClickReady()
    {
        if (!await EnsureRelayReady())
            return;
        if (currentRoomState == null ||
            string.IsNullOrWhiteSpace(currentRoomState.roomId))
        {
            SetStatus("还没有加入房间。");
            return;
        }

        localReady = !localReady;

        SetStatus(localReady ? "已准备。" : "已取消准备。");

        await relayClient.SendReady(localReady);

        if (debugLog)
            Debug.Log($"[LobbyManager] Send ROOM_READY_REQ ready={localReady}");
    }

    public async void OnClickStartGame()
    {
        if (!await EnsureRelayReady())
            return;

        bool isHost = IsLocalHost();
        bool canStart = currentRoomState != null && currentRoomState.canStart;

        if (!isHost)
        {
            SetStatus("只有房主可以开始游戏。");
            return;
        }

        if (!canStart)
        {
            SetStatus("还不能开始：需要所有玩家准备。");
            return;
        }

        SetStatus("正在开始游戏...");

        await relayClient.SendStartGame();

        if (debugLog)
            Debug.Log("[LobbyManager] Send ROOM_START_REQ");
    }

    public async void OnClickBackButton()
    {
        Debug.Log("点击返回：取消/退出当前房间...");

        if (globalRoomActionInFlight)
        {
            Debug.LogWarning("[LobbyManager] 当前房间操作正在进行中，忽略返回点击。");
            return;
        }

        globalRoomActionInFlight = true;
        pendingOpenLobbyAfterRoomAction = false;

        if (backButton != null)
            backButton.interactable = false;

        if (startButton != null)
            startButton.interactable = false;

        SetStatus("正在退出房间...");

        try
        {
            if (relayClient == null)
                relayClient = RelayChatClient.Instance;

            if (relayClient == null)
                relayClient = FindFirstObjectByType<RelayChatClient>();

            bool hasRoom =
                currentRoomState != null &&
                !string.IsNullOrWhiteSpace(currentRoomState.roomId);

            if (!hasRoom &&
                NetworkSession.Instance != null &&
                !string.IsNullOrWhiteSpace(NetworkSession.Instance.roomId))
            {
                hasRoom = true;
            }

            if (!hasRoom &&
                AuthSession.Ctx != null &&
                !string.IsNullOrWhiteSpace(AuthSession.Ctx.roomId))
            {
                hasRoom = true;
            }

            // 1. 如果当前确实在房间里，通知服务器退出房间
            if (hasRoom && relayClient != null)
            {
                await relayClient.LeaveRoom();

                if (debugLog)
                    Debug.Log("[LobbyManager] Send LEAVE_ROOM from Back button");
            }

            // 2. 清理本地 Relay 房间状态
            if (relayClient != null)
                relayClient.ClearLocalRoomState();

            // 3. 清理本地 NetworkSession 房间状态
            if (NetworkSession.Instance != null)
                NetworkSession.Instance.ClearRoom();

            // 4. 清理 AuthSession 里的房间状态
            AuthSession.EnsureExists().ClearRoom();

            // 5. 清理 LobbyManager 自己的 UI 状态
            currentRoomState = null;
            localReady = false;
            pendingOpenLobbyAfterRoomAction = false;

            RefreshEmptyLobby();

            // 6. 关闭 Lobby 面板
            await PlayLobbyDropUpAndWait();

            // 7. 回主菜单动画
            if (mainMenuManager != null)
            {
                mainMenuManager.OnClickBackToMain();
            }
            else
            {
                Debug.LogWarning("[LobbyManager] mainMenuManager 没有绑定，已只关闭 LobbyPanel。");
            }

            SetStatus("");
        }
        catch (Exception ex)
        {
            Debug.LogError("[LobbyManager] Back/LeaveRoom failed: " + ex);

            // 网络失败也要允许 UI 回去，避免卡死在房间界面
            if (relayClient != null)
                relayClient.ClearLocalRoomState();

            if (NetworkSession.Instance != null)
                NetworkSession.Instance.ClearRoom();

            AuthSession.EnsureExists().ClearRoom();

            currentRoomState = null;
            localReady = false;
            pendingOpenLobbyAfterRoomAction = false;

            RefreshEmptyLobby();

            await PlayLobbyDropUpAndWait();

            if (mainMenuManager != null)
                mainMenuManager.OnClickBackToMain();
        }
        finally
        {
            globalRoomActionInFlight = false;

            if (backButton != null)
                backButton.interactable = true;

            RefreshStartButton();
        }
    }

    // ============================================================
    // Network events
    // ============================================================

    private void HandleRoomState(RoomStatePayload state)
    {
        if (state == null)
            return;

        NormalizeRoomState(state);

        currentRoomState = state;

        string localClientId = GetLocalClientId(state);
        localReady = FindLocalReady(state, localClientId);

        if (debugLog)
        {
            Debug.Log(
                $"[LobbyManager] HandleRoomState received " +
                $"room={state.roomId}, pendingOpen={pendingOpenLobbyAfterRoomAction}, " +
                $"opened={lobbyPanelOpened}, " +
                $"lobbyPanelRoot={(lobbyPanelRoot != null ? lobbyPanelRoot.name : "NULL")}"
            );
        }

        if (pendingOpenLobbyAfterRoomAction || !lobbyPanelOpened)
        {
            pendingOpenLobbyAfterRoomAction = false;
            OpenLobbyPanelWithDropDown();
        }

        RefreshRoomStateUI(state);

        globalRoomActionInFlight = false;

        if (debugLog)
        {
            Debug.Log(
                $"[LobbyManager] ROOM_STATE " +
                $"room={state.roomId}, local={state.localClientId}, " +
                $"slot={state.localSlotNo}, localIsHost={state.localIsHost}, " +
                $"hostClientId={state.hostClientId}, canStart={state.canStart}, " +
                $"players={(state.players != null ? state.players.Length : 0)}"
            );
        }
    }

    private void HandleGameStart(GameStartPayload start)
    {
        if (start == null)
            return;

        SetStatus("游戏开始。");

        if (debugLog)
        {
            Debug.Log(
                $"[LobbyManager] GAME_START room={start.roomId}, " +
                $"scene={start.sceneName}, local={start.localClientId}, " +
                $"slot={start.localSlotNo}, isHost={start.localIsHost}"
            );
        }
    }

    // ============================================================
    // UI refresh
    // ============================================================

    private void RefreshFromCurrentState()
    {
        if (currentRoomState != null)
        {
            RefreshRoomStateUI(currentRoomState);
            return;
        }

        RefreshStartButton();
    }

    private void RefreshRoomStateUI(RoomStatePayload state)
    {
        if (state == null)
        {
            RefreshEmptyLobby();
            return;
        }

        if (roomCodeText != null)
        {
            roomCodeText.gameObject.SetActive(true);
            roomCodeText.text = string.IsNullOrWhiteSpace(state.roomId)
                ? "----"
                : state.roomId;
        }

        RefreshDynamicPlayerCards(state);
        RefreshStartButton();

        string status = !string.IsNullOrWhiteSpace(state.status)
            ? state.status
            : (!string.IsNullOrWhiteSpace(state.state) ? state.state : "WAITING");

        SetStatus(
            $"房间 {state.roomId} | 状态：{status} | " +
            $"你是 {state.localClientId} | 房主：{state.hostClientId}"
        );
    }

    private void RefreshDynamicPlayerCards(RoomStatePayload state)
    {
        if (playerCardRoot == null || playerCardPrefab == null)
        {
            Debug.LogError("[LobbyManager] PlayerCardRoot 或 PlayerCardPrefab 没有绑定！");
            return;
        }

        HashSet<string> aliveClientIds = new HashSet<string>();
        string localClientId = GetLocalClientId(state);
        RoomPlayerInfo[] sortedPlayers = GetSortedPlayers(state.players);

        for (int i = 0; i < sortedPlayers.Length; i++)
        {
            RoomPlayerInfo player = sortedPlayers[i];

            if (player == null || string.IsNullOrWhiteSpace(player.clientId))
                continue;

            aliveClientIds.Add(player.clientId);

            LobbyPlayerCard card = GetOrCreatePlayerCard(player.clientId, i);

            bool isLocal = string.Equals(
                player.clientId,
                localClientId,
                StringComparison.OrdinalIgnoreCase
            );

            Sprite portrait = GetPortraitForSlot(player.slotNo);

            card.Setup(
                player,
                isLocal,
                portrait,
                OnClickReady
            );

            card.transform.SetSiblingIndex(i);
        }

        RemoveMissingCards(aliveClientIds);
    }
    private void ShowNeedLoginAlert()
    {
        if (loginAlertShowing)
            return;

        loginAlertShowing = true;

        GameAlert.Show(
            "请先登录",
            "创建房间或加入房间前，需要先登录账号。",
            "去登录",
            () =>
            {
                loginAlertShowing = false;

                LoginPanelController loginPanel = FindFirstObjectByType<LoginPanelController>();

                if (loginPanel != null)
                    loginPanel.OpenLoginPanel();
                else
                    Debug.LogWarning("[LobbyManager] LoginPanelController not found.");
            },
            "取消",
            () =>
            {
                loginAlertShowing = false;
            }
        );
    }
    private LobbyPlayerCard GetOrCreatePlayerCard(string cardKey, int index)
    {
        if (playerCards.TryGetValue(cardKey, out LobbyPlayerCard existing) &&
            existing != null)
        {
            existing.gameObject.SetActive(true);
            existing.transform.SetParent(playerCardRoot, false);
            return existing;
        }

        LobbyPlayerCard card = Instantiate(playerCardPrefab, playerCardRoot);
        card.name = $"LobbyPlayerCard_{cardKey}";

        // 关键：无论 prefab 原来是不是 inactive，生成后强制打开
        card.gameObject.SetActive(true);

        RectTransform rt = card.transform as RectTransform;
        if (rt != null)
        {
            rt.localScale = Vector3.one;
            rt.anchoredPosition = Vector2.zero;
        }
        else
        {
            card.transform.localScale = Vector3.one;
            card.transform.localPosition = Vector3.zero;
        }

        playerCards[cardKey] = card;

        CanvasGroup group = card.GetComponent<CanvasGroup>();

        if (group == null)
            group = card.gameObject.AddComponent<CanvasGroup>();

        group.alpha = 1f;
        group.interactable = true;
        group.blocksRaycasts = true;

        cardCanvasGroups[cardKey] = group;

        if (useCardTween)
            AnimateCardIn(card, group, index);
        else
            group.alpha = 1f;

        return card;
    }
    private void AnimateCardIn(LobbyPlayerCard card, CanvasGroup group, int index)
    {
        if (card == null || group == null)
            return;

        RectTransform rt = card.transform as RectTransform;
        Transform cardTransform = card.transform;

        group.DOKill();
        cardTransform.DOKill();

        if (rt != null)
            rt.DOKill();

        group.alpha = 0f;

        float delay = index * 0.06f;

        Vector3 targetScale = Vector3.one;
        Vector3 startScale = Vector3.one * cardStartScale;

        cardTransform.localScale = startScale;

        if (rt != null)
        {
            Vector2 targetPos = rt.anchoredPosition;
            Vector2 startPos = targetPos + new Vector2(0f, cardSlideOffsetY);

            rt.anchoredPosition = startPos;

            rt.DOAnchorPos(targetPos, cardEnterDuration)
                .SetEase(cardEnterEase)
                .SetDelay(delay);
        }

        group.DOFade(1f, cardEnterDuration * 0.75f)
            .SetEase(Ease.OutQuad)
            .SetDelay(delay);

        cardTransform
            .DOScale(targetScale, cardEnterDuration)
            .SetEase(cardEnterEase)
            .SetDelay(delay);
    }

    private void RemoveMissingCards(HashSet<string> aliveClientIds)
    {
        List<string> removeKeys = new List<string>();

        foreach (KeyValuePair<string, LobbyPlayerCard> pair in playerCards)
        {
            string key = pair.Key;

            if (!aliveClientIds.Contains(key))
                removeKeys.Add(key);
        }

        foreach (string key in removeKeys)
        {
            LobbyPlayerCard card = playerCards[key];

            playerCards.Remove(key);
            cardCanvasGroups.Remove(key);

            if (card == null)
                continue;

            if (!useCardTween)
            {
                Destroy(card.gameObject);
                continue;
            }

            CanvasGroup cg = card.GetComponent<CanvasGroup>();

            if (cg == null)
                cg = card.gameObject.AddComponent<CanvasGroup>();

            RectTransform rt = card.transform as RectTransform;

            cg.DOKill();
            card.transform.DOKill();

            if (rt != null)
                rt.DOKill();

            Sequence seq = DOTween.Sequence();

            seq.Join(
                cg.DOFade(0f, cardExitDuration)
                    .SetEase(Ease.OutQuad)
            );

            if (rt != null)
            {
                seq.Join(
                    rt.DOAnchorPosY(
                        rt.anchoredPosition.y + cardSlideOffsetY * 0.5f,
                        cardExitDuration
                    ).SetEase(cardExitEase)
                );
            }

            seq.Join(
                card.transform
                    .DOScale(Vector3.one * cardStartScale, cardExitDuration)
                    .SetEase(cardExitEase)
            );

            seq.OnComplete(() =>
            {
                if (card != null)
                    Destroy(card.gameObject);
            });
        }
    }

    private void RefreshStartButton()
    {
        bool isHost = IsLocalHost();
        bool canStart = currentRoomState != null && currentRoomState.canStart;

        if (startButton != null)
            startButton.interactable = isHost && canStart;

        if (debugLog)
        {
            Debug.Log(
                $"[LobbyManager] RefreshStartButton " +
                $"isHost={isHost}, canStart={canStart}, " +
                $"slot={(currentRoomState != null ? currentRoomState.localSlotNo : -1)}, " +
                $"client={(currentRoomState != null ? currentRoomState.localClientId : "null")}"
            );
        }
    }

    private void RefreshEmptyLobby()
    {
        currentRoomState = null;
        localReady = false;

        if (roomCodeText != null)
            roomCodeText.text = "----";

        ClearAllCards();

        if (startButton != null)
            startButton.interactable = false;

        SetStatus("");
    }

    private void ClearAllCards()
    {
        foreach (KeyValuePair<string, LobbyPlayerCard> pair in playerCards)
        {
            if (pair.Value != null)
                Destroy(pair.Value.gameObject);
        }

        playerCards.Clear();
        cardCanvasGroups.Clear();
    }

    // ============================================================
    // Helpers
    // ============================================================

    private void NormalizeRoomState(RoomStatePayload state)
    {
        if (state == null)
            return;

        if (string.IsNullOrWhiteSpace(state.hostClientId) &&
            state.players != null)
        {
            foreach (RoomPlayerInfo player in state.players)
            {
                if (player != null && player.slotNo == 1)
                {
                    state.hostClientId = player.clientId;
                    break;
                }
            }
        }

        if (!string.IsNullOrWhiteSpace(state.hostClientId) &&
            !string.IsNullOrWhiteSpace(state.localClientId))
        {
            state.localIsHost = state.hostClientId == state.localClientId;
        }
        else if (state.localSlotNo == 1)
        {
            state.localIsHost = true;
        }

        if (state.players != null)
        {
            foreach (RoomPlayerInfo player in state.players)
            {
                if (player == null)
                    continue;

                player.isHost =
                    (!string.IsNullOrWhiteSpace(state.hostClientId) &&
                     player.clientId == state.hostClientId) ||
                    player.slotNo == 1;
            }
        }
    }

    private RoomPlayerInfo[] GetSortedPlayers(RoomPlayerInfo[] players)
    {
        if (players == null || players.Length == 0)
            return Array.Empty<RoomPlayerInfo>();

        RoomPlayerInfo[] copy = new RoomPlayerInfo[players.Length];
        Array.Copy(players, copy, players.Length);

        Array.Sort(copy, (a, b) =>
        {
            if (a == null && b == null)
                return 0;

            if (a == null)
                return 1;

            if (b == null)
                return -1;

            return a.slotNo.CompareTo(b.slotNo);
        });

        return copy;
    }

    private Sprite GetPortraitForSlot(int slotNo)
    {
        if (slotNo == 1)
            return player1Portrait;

        if (slotNo == 2)
            return player2Portrait;

        return null;
    }

    private string GetLocalClientId(RoomStatePayload state)
    {
        if (state != null && !string.IsNullOrWhiteSpace(state.localClientId))
            return state.localClientId;

        if (NetworkSession.Instance != null &&
            !string.IsNullOrWhiteSpace(NetworkSession.Instance.clientId))
        {
            return NetworkSession.Instance.clientId;
        }

        if (!string.IsNullOrWhiteSpace(AuthSession.Ctx.localClientId))
            return AuthSession.Ctx.localClientId;

        return "";
    }

    private bool FindLocalReady(RoomStatePayload state, string localClientId)
    {
        if (state == null ||
            state.players == null ||
            string.IsNullOrWhiteSpace(localClientId))
        {
            return false;
        }

        foreach (RoomPlayerInfo player in state.players)
        {
            if (player == null)
                continue;

            if (string.Equals(
                    player.clientId,
                    localClientId,
                    StringComparison.OrdinalIgnoreCase))
            {
                return player.ready;
            }
        }

        return false;
    }

    private bool IsLocalHost()
    {
        if (currentRoomState != null)
        {
            if (currentRoomState.localIsHost)
                return true;

            if (currentRoomState.localSlotNo == 1)
                return true;

            if (!string.IsNullOrWhiteSpace(currentRoomState.hostClientId) &&
                !string.IsNullOrWhiteSpace(currentRoomState.localClientId))
            {
                return currentRoomState.hostClientId == currentRoomState.localClientId;
            }
        }

        if (NetworkSession.Instance != null)
        {
            if (NetworkSession.Instance.isHost)
                return true;

            if (NetworkSession.Instance.slotNo == 1)
                return true;
        }

        return false;
    }

    private async Task<bool> EnsureRelayReady()
    {
        if (relayClient == null)
        {
            relayClient = RelayChatClient.Instance;

            if (relayClient == null)
                relayClient = FindFirstObjectByType<RelayChatClient>();
        }

        if (relayClient == null)
        {
            SetStatus("RelayChatClient 不存在。");
            return false;
        }

        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null ||
      string.IsNullOrWhiteSpace(ctx.serviceTicket) ||
      string.IsNullOrWhiteSpace(ctx.kcGs))
        {
            SetStatus("请先登录。");
            ShowNeedLoginAlert();
            return false;
        }

        // 关键：如果结算后回大厅，旧 sessionId 已经清掉，
        // 这里会自动重新连接 GS 并重新做 GS_AUTH。
        bool ok = await relayClient.EnsureGsReady();

        if (!ok || !AuthSession.Ctx.HasGsSession)
        {
            SetStatus("GS_AUTH 失败，请重新登录或稍后再试。");
            return false;
        }

        return true;
    }

    private void SetStatus(string message)
    {
        if (statusText != null)
        {
            statusText.gameObject.SetActive(true);
            statusText.text = message ?? "";
        }

        if (debugLog && !string.IsNullOrWhiteSpace(message))
            Debug.Log("[LobbyManager] " + message);
    }
}