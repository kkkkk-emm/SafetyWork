using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class LobbyManager : MonoBehaviour
{
    [Header("网络")]
    [SerializeField] private RelayChatClient relayClient;

    [Header("默认配置")]
    [SerializeField] private string defaultClientId = "Guest";
    [SerializeField] private string gameSceneName = "MainGame";

    [Header("加入房间弹窗")]
    [SerializeField] private TMP_InputField joinRoomInput;
    [SerializeField] private Button confirmJoinButton;
    [SerializeField] private Button cancelJoinButton;

    [Header("动态玩家卡片")]
    [SerializeField] private Transform playerCardRoot;
    [SerializeField] private LobbyPlayerCard playerCardPrefab;

    [Header("玩家立绘")]
    [SerializeField] private Sprite p1Portrait;
    [SerializeField] private Sprite p2Portrait;

    [Header("Lobby UI")]
    [SerializeField] private Button startButton;
    [SerializeField] private Button backButton;
    [SerializeField] private TextMeshProUGUI roomCodeText;

    [Header("管理器引用")]
    [SerializeField] private MainMenuManager mainMenuManager;

    private string clientId;
    private string roomId;

    private int localSlotNo = 0;
    private bool localReady = false;
    private bool localIsHost = false;

    private RoomStatePayload latestRoomState;

    private readonly List<LobbyPlayerCard> spawnedCards = new List<LobbyPlayerCard>();

    private void Awake()
    {
        if (relayClient == null)
            relayClient = FindFirstObjectByType<RelayChatClient>();

        clientId = defaultClientId;
        ApplyCommandLineArgs();
    }

    private void OnEnable()
    {
        BindButtons();
        BindRelayEvents();
        ResetLobbyVisual();
    }

    private void OnDisable()
    {
        UnbindRelayEvents();
    }

    private void BindButtons()
    {
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

        if (confirmJoinButton != null)
        {
            confirmJoinButton.onClick.RemoveListener(OnClickConfirmJoinRoom);
            confirmJoinButton.onClick.AddListener(OnClickConfirmJoinRoom);
        }

        if (cancelJoinButton != null)
        {
            cancelJoinButton.onClick.RemoveListener(OnClickCancelJoinRoom);
            cancelJoinButton.onClick.AddListener(OnClickCancelJoinRoom);
        }
    }

    private void BindRelayEvents()
    {
        if (relayClient == null)
            return;

        relayClient.OnRoomStateReceived -= OnRoomStateReceived;
        relayClient.OnRoomStateReceived += OnRoomStateReceived;

        relayClient.OnGameStartReceived -= OnGameStartReceived;
        relayClient.OnGameStartReceived += OnGameStartReceived;
    }

    private void UnbindRelayEvents()
    {
        if (relayClient == null)
            return;

        relayClient.OnRoomStateReceived -= OnRoomStateReceived;
        relayClient.OnGameStartReceived -= OnGameStartReceived;
    }

    private void ApplyCommandLineArgs()
    {
        string[] args = Environment.GetCommandLineArgs();

        for (int i = 0; i < args.Length; i++)
        {
            if (args[i] == "--clientId" && i + 1 < args.Length)
            {
                clientId = args[i + 1];
            }
        }

        if (string.IsNullOrWhiteSpace(clientId))
            clientId = defaultClientId;

        clientId = clientId.Trim();
    }

    private void ResetLobbyVisual()
    {
        localSlotNo = 0;
        localReady = false;
        localIsHost = false;
        latestRoomState = null;
        roomId = "";

        ClearPlayerCards();

        if (roomCodeText != null)
            roomCodeText.text = "房间号：----";

        if (startButton != null)
            startButton.interactable = false;
    }

    private void ClearPlayerCards()
    {
        for (int i = 0; i < spawnedCards.Count; i++)
        {
            if (spawnedCards[i] != null)
                Destroy(spawnedCards[i].gameObject);
        }

        spawnedCards.Clear();
    }

    private async Task EnsureConnectedAndIdentity()
    {
        if (relayClient == null)
        {
            Debug.LogError("[LobbyManager] RelayChatClient 为空");
            return;
        }

        string serverUrl = "";

        if (NetworkSession.Instance != null)
        {
            NetworkSession.Instance.gameSceneName = gameSceneName;
            serverUrl = NetworkSession.Instance.serverUrl;
        }

        relayClient.ConfigureIdentity(
            serverUrl,
            clientId,
            roomId
        );

        await relayClient.Connect();
    }

    public async void OnClickCreateRoomAndEnter()
    {
        if (relayClient == null)
        {
            Debug.LogError("[LobbyManager] RelayChatClient 为空");
            return;
        }

        // 创建新房间时，不要沿用旧 Client1 / Client2。
        // 最终身份必须等服务器 ROOM_STATE 返回。
        clientId = "";
        roomId = "";
        localSlotNo = 0;
        localReady = false;
        localIsHost = false;

        if (NetworkSession.Instance != null)
        {
            NetworkSession.Instance.Clear();
            NetworkSession.Instance.gameSceneName = gameSceneName;
        }

        await EnsureConnectedAndIdentity();

        if (!relayClient.IsConnected)
        {
            Debug.LogWarning("[LobbyManager] 连接还没准备好，创建房间取消。请检查服务器是否启动。");
            return;
        }

        if (mainMenuManager != null)
            mainMenuManager.OnClickMultiplayer();

        await relayClient.SendCreateRoom();

        Debug.Log("[LobbyManager] Send CREATE_ROOM");
    }
    public void OnClickShowJoinRoomPopup()
    {
        if (mainMenuManager != null)
            mainMenuManager.ShowJoinRoomPopup();
    }

    public async void OnClickConfirmJoinRoom()
    {
        if (relayClient == null)
            return;

        string inputRoomId = joinRoomInput != null
            ? joinRoomInput.text.Trim().ToUpper()
            : "";

        if (string.IsNullOrWhiteSpace(inputRoomId))
        {
            Debug.LogWarning("[LobbyManager] 请输入房间号");
            return;
        }

        // 加入已有房间时，也不要声明自己是谁。
        // 服务器会在 lobby 阶段分配 Client1 / Client2。
        clientId = "";
        roomId = inputRoomId;
        localSlotNo = 0;
        localReady = false;
        localIsHost = false;

        if (NetworkSession.Instance != null)
        {
            NetworkSession.Instance.Clear();
            NetworkSession.Instance.gameSceneName = gameSceneName;
        }

        await EnsureConnectedAndIdentity();

        if (!relayClient.IsConnected)
        {
            Debug.LogWarning("[LobbyManager] 连接还没准备好，加入房间取消。请检查服务器是否启动。");
            return;
        }

        if (mainMenuManager != null)
        {
            mainMenuManager.HideJoinRoomPopup();
            mainMenuManager.OnClickMultiplayer();
        }

        await relayClient.SendJoinRoomManual("", roomId);

        Debug.Log($"[LobbyManager] Send JOIN_ROOM room={roomId}");
    }
    public void OnClickCancelJoinRoom()
    {
        if (mainMenuManager != null)
            mainMenuManager.HideJoinRoomPopup();
    }

    private async void OnClickReadyFromCard()
    {
        await ToggleReady();
    }

    private async Task ToggleReady()
    {
        if (relayClient == null)
            return;

        localReady = !localReady;

        await relayClient.SendReady(localReady);
    }

    public async void OnClickStartGame()
    {
        if (relayClient == null)
            return;

        if (!localIsHost)
        {
            Debug.Log("[LobbyManager] 只有房主可以开始");
            return;
        }

        if (latestRoomState == null || !latestRoomState.canStart)
        {
            Debug.Log("[LobbyManager] 还不能开始，需要双方 Ready");
            return;
        }

        await relayClient.SendStartGame();
    }

    public async void OnClickBackButton()
    {
        localReady = false;
        localSlotNo = 0;
        localIsHost = false;
        latestRoomState = null;
        roomId = "";

        if (relayClient != null)
            await relayClient.LeaveRoom();

        ResetLobbyVisual();

        if (mainMenuManager != null)
            mainMenuManager.OnClickBackToMain();
    }

    private void OnRoomStateReceived(RoomStatePayload state)
    {
        latestRoomState = state;

        if (state == null)
            return;

        roomId = state.roomId;

        if (!string.IsNullOrWhiteSpace(state.localClientId))
            clientId = state.localClientId;

        if (NetworkSession.Instance != null)
        {
            NetworkSession.Instance.ApplyRoomState(state);
            clientId = NetworkSession.Instance.clientId;
        }

        localSlotNo = state.localSlotNo;
        localIsHost = state.localIsHost;
        localReady = false;

        ClearPlayerCards();

        if (state.players != null)
        {
            Array.Sort(state.players, (a, b) => a.slotNo.CompareTo(b.slotNo));

            foreach (RoomPlayerInfo player in state.players)
            {
                if (player == null)
                    continue;

                CreatePlayerCard(player);

                if (player.clientId == clientId)
                {
                    localSlotNo = player.slotNo;
                    localIsHost = player.isHost;
                    localReady = player.ready;
                }
            }
        }

        if (roomCodeText != null)
            roomCodeText.text = $"房间号：{state.roomId}";

        if (startButton != null)
            startButton.interactable = localIsHost && state.canStart;

        Debug.Log(
            $"[LobbyManager] ROOM_STATE local={clientId} slot={localSlotNo} " +
            $"host={localIsHost} canStart={state.canStart}"
        );
    }

    private void CreatePlayerCard(RoomPlayerInfo player)
    {
        if (playerCardRoot == null || playerCardPrefab == null)
        {
            Debug.LogWarning("[LobbyManager] playerCardRoot 或 playerCardPrefab 没有拖引用");
            return;
        }

        LobbyPlayerCard card = Instantiate(playerCardPrefab, playerCardRoot);

        bool isLocalPlayer = player.clientId == clientId;
        Sprite portrait = GetPortraitBySlot(player.slotNo);

        card.Setup(
            player,
            isLocalPlayer,
            portrait,
            isLocalPlayer ? OnClickReadyFromCard : null
        );

        spawnedCards.Add(card);
    }

    private Sprite GetPortraitBySlot(int slotNo)
    {
        if (slotNo == 1)
            return p1Portrait;

        if (slotNo == 2)
            return p2Portrait;

        return null;
    }

    private void OnGameStartReceived(GameStartPayload start)
    {
        if (start == null)
            return;

        if (!string.IsNullOrWhiteSpace(start.localClientId))
            clientId = start.localClientId;

        if (!string.IsNullOrWhiteSpace(start.roomId))
            roomId = start.roomId;

        if (NetworkSession.Instance != null)
        {
            NetworkSession.Instance.ApplyGameStart(start);
        }

        Debug.Log(
            $"[LobbyManager] GAME_START received " +
            $"client={clientId}, room={roomId}, scene={start.sceneName}"
        );

        // 不要在这里 SceneManager.LoadScene。
        // RelayChatClient 已经负责加载 MainGame。
    }
}