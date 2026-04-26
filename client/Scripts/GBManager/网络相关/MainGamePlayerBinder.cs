using UnityEngine;

public class MainGamePlayerBinder : MonoBehaviour
{
    [Header("场景玩家")]
    [SerializeField] private Player player1;
    [SerializeField] private Player player2;

    [Header("网络组件")]
    [SerializeField] private InputPacker inputPacker;
    [SerializeField] private ClientPredictionController predictionController;
    [SerializeField] private ClientReceiver clientReceiver;

    private void Start()
    {
        Bind();
    }

    private void Bind()
    {
        if (NetworkSession.Instance == null)
        {
            Debug.LogError("[MainGamePlayerBinder] 没有 NetworkSession");
            return;
        }

        string localClientId = NetworkSession.Instance.clientId;

        if (string.IsNullOrWhiteSpace(localClientId))
        {
            Debug.LogError("[MainGamePlayerBinder] NetworkSession.clientId 为空");
            return;
        }

        if (player1 == null || player2 == null)
        {
            Debug.LogError("[MainGamePlayerBinder] player1/player2 没有拖引用");
            return;
        }

        Player localPlayer;
        Player remotePlayer;

        if (localClientId == "Client1")
        {
            localPlayer = player1;
            remotePlayer = player2;
        }
        else if (localClientId == "Client2")
        {
            localPlayer = player2;
            remotePlayer = player1;
        }
        else
        {
            Debug.LogError($"[MainGamePlayerBinder] 未知 localClientId={localClientId}");
            return;
        }

        if (inputPacker == null)
            inputPacker = FindFirstObjectByType<InputPacker>();

        if (predictionController == null)
            predictionController = FindFirstObjectByType<ClientPredictionController>();

        if (clientReceiver == null)
            clientReceiver = FindFirstObjectByType<ClientReceiver>();

        if (inputPacker == null || predictionController == null || clientReceiver == null)
        {
            Debug.LogError("[MainGamePlayerBinder] 网络组件没有拖全");
            return;
        }

        // 两个 Player 都进入网络模式。
        // 这样 Player.cs 自己不要直接吃输入，输入统一从 InputPacker 出。
        player1.useNetworkControl = true;
        player2.useNetworkControl = true;

        // 只有本机对应角色是 Local。
        player1.isLocalPlayer = localClientId == "Client1";
        player2.isLocalPlayer = localClientId == "Client2";

        // 如果 Player 里已经加了 SetNetworkLocalPlayer，就用这个更稳。
        player1.SetNetworkLocalPlayer(localClientId == "Client1");
        player2.SetNetworkLocalPlayer(localClientId == "Client2");

        // 只允许本地玩家的 combat controller 读本地输入。
        // 如果你的 PlayerCombatController 没有 SetReadLocalInput，先看下面我给的补法。
        PlayerCombatController p1Combat = player1.GetComponent<PlayerCombatController>();
        PlayerCombatController p2Combat = player2.GetComponent<PlayerCombatController>();

        if (p1Combat != null)
            p1Combat.SetReadLocalInput(localClientId == "Client1");

        if (p2Combat != null)
            p2Combat.SetReadLocalInput(localClientId == "Client2");

        predictionController.BindPlayer(localPlayer);
        inputPacker.BindPlayer(localPlayer, predictionController);
        clientReceiver.BindPlayers(player1, player2, predictionController, localClientId);

        Debug.Log(
            $"[MainGamePlayerBinder] localClientId={localClientId}, " +
            $"localPlayer={localPlayer.name}, remotePlayer={remotePlayer.name}, " +
            $"p1Local={player1.isLocalPlayer}, p2Local={player2.isLocalPlayer}"
        );
    }
}