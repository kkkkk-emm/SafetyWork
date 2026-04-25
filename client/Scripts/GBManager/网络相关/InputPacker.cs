using UnityEngine;
using UnityEngine.InputSystem;

public class InputPacker : MonoBehaviour
{
    [Header("调试")]
    [SerializeField] private bool debugInputLog = true;
    [SerializeField] private int logEveryNPackets = 10;

    [Header("引用")]
    [SerializeField] private RelayChatClient relayClient;
    [SerializeField] private ClientPredictionController predictionController;
    [SerializeField] private Transform aimOrigin;
    [SerializeField] private Player player;

    private PlayerInputSet input;

    private int currentSeq = 0;
    private int currentTick = 0;

    private bool jumpPressedBuffered;
    private bool attackPressedBuffered;
    private bool lastAttackHeld;

    private void Awake()
    {
        if (relayClient == null)
            relayClient = FindFirstObjectByType<RelayChatClient>();

        // 等 Binder 来绑定本地 Player。
        enabled = false;
    }

    private void OnDisable()
    {
        UnbindInputEvents();
    }

    public void BindPlayer(Player newPlayer, ClientPredictionController newPredictionController)
    {
        UnbindInputEvents();

        player = newPlayer;
        predictionController = newPredictionController;

        if (relayClient == null)
            relayClient = FindFirstObjectByType<RelayChatClient>();

        currentSeq = 0;
        currentTick = 0;

        jumpPressedBuffered = false;
        attackPressedBuffered = false;
        lastAttackHeld = false;

        if (player == null)
        {
            Debug.LogError("[InputPacker] BindPlayer 收到空 Player");
            enabled = false;
            return;
        }

        aimOrigin = player.transform;
        input = player.input;

        if (input == null)
        {
            Debug.LogError($"[InputPacker] {player.name}.input 为空");
            enabled = false;
            return;
        }

        input.Enable();

        input.Player.Jump.performed += OnJumpPerformed;
        input.Player.Attack.performed += OnAttackPerformed;

        enabled = true;

        Debug.Log(
            $"[InputPacker] BindPlayer -> player={player.name}, " +
            $"localClient={relayClient?.ClientId}, " +
            $"prediction={(predictionController != null ? predictionController.name : "null")}"
        );
    }

    private void UnbindInputEvents()
    {
        if (input == null)
            return;

        input.Player.Jump.performed -= OnJumpPerformed;
        input.Player.Attack.performed -= OnAttackPerformed;
    }

    private void OnJumpPerformed(InputAction.CallbackContext _)
    {
        jumpPressedBuffered = true;

        if (debugInputLog)
            Debug.Log($"[InputPacker:{player?.name}] Jump performed");
    }

    private void OnAttackPerformed(InputAction.CallbackContext _)
    {
        attackPressedBuffered = true;

        if (debugInputLog)
            Debug.Log($"[InputPacker:{player?.name}] Attack performed");
    }

    private void FixedUpdate()
    {
        if (relayClient == null || player == null || input == null)
            return;

        if (!relayClient.HasJoinedRoom)
            return;

        currentTick++;

        Vector2 move = input.Player.Movement.ReadValue<Vector2>();
        Vector2 aim = ReadAimDirection();

        bool jumpPressed = jumpPressedBuffered || input.Player.Jump.WasPressedThisFrame();
        bool attackPressed = attackPressedBuffered || input.Player.Attack.WasPressedThisFrame();

        bool attackHeld = input.Player.Attack.IsPressed();
        bool attackReleased = lastAttackHeld && !attackHeld;
        lastAttackHeld = attackHeld;

        bool downHeld = move.y < -0.5f;
        bool dropPressed = downHeld && jumpPressed;

        player.ApplyNetworkInputFrame(
            move,
            jumpPressed,
            false,
            attackPressed,
            attackHeld,
            downHeld,
            dropPressed
        );

        PredictedPlayerState predicted = predictionController != null
            ? predictionController.GetPredictedState()
            : default;

        PlayerInputCmd cmd = new PlayerInputCmd
        {
            seq = currentSeq++,
            tick = currentTick,

            moveX = move.x,

            jumpPressed = jumpPressed,
            downHeld = downHeld,
            dropPressed = dropPressed,

            attackPressed = attackPressed,
            attackHeld = attackHeld,
            attackReleased = attackReleased,

            aimX = aim.x,
            aimY = aim.y,

            clientState = player.GetCurrentStateName(),
            clientGrounded = player.GetIsGroundedForNet(),
            clientJumpCount = player.GetJumpCountForNet(),

            clientPosX = predicted.posX,
            clientPosY = predicted.posY,
            clientVelX = predicted.velX,
            clientVelY = predicted.velY,

            equippedWeaponId = GetCurrentWeaponId(),
            equippedEffectIds = GetCurrentEffectIds()
        };

        predictionController?.AddLocalInput(cmd);

        if (debugInputLog && (cmd.seq == 0 || cmd.seq % Mathf.Max(1, logEveryNPackets) == 0))
        {
            Debug.Log(
                $"[InputPacker:{player.name}] send seq={cmd.seq} tick={cmd.tick} " +
                $"moveX={cmd.moveX:F2} jump={cmd.jumpPressed} " +
                $"atkPressed={cmd.attackPressed} atkHeld={cmd.attackHeld} atkReleased={cmd.attackReleased} " +
                $"aim=({cmd.aimX:F2},{cmd.aimY:F2}) " +
                $"state={cmd.clientState} grounded={cmd.clientGrounded} jumpCount={cmd.clientJumpCount} " +
                $"pos=({cmd.clientPosX:F2},{cmd.clientPosY:F2}) vel=({cmd.clientVelX:F2},{cmd.clientVelY:F2}) " +
                $"weapon={cmd.equippedWeaponId} effects={(cmd.equippedEffectIds != null ? string.Join(",", cmd.equippedEffectIds) : "")}"
            );
        }

        _ = relayClient.SendInput(cmd);

        jumpPressedBuffered = false;
        attackPressedBuffered = false;
    }

    private Vector2 ReadAimDirection()
    {
        if (Mouse.current == null || Camera.main == null || aimOrigin == null)
            return Vector2.right;

        Vector3 mouseScreen = Mouse.current.position.ReadValue();
        Vector3 mouseWorld = Camera.main.ScreenToWorldPoint(mouseScreen);
        mouseWorld.z = 0f;

        Vector2 direction = mouseWorld - aimOrigin.position;

        if (direction.sqrMagnitude < 0.0001f)
            return Vector2.right;

        return direction.normalized;
    }

    private string GetCurrentWeaponId()
    {
        if (player != null && player.currentWeaponData != null)
            return player.currentWeaponData.name;

        return "手枪";
    }

    private string[] GetCurrentEffectIds()
    {
        if (player == null || player.currentWeaponInstance == null)
            return System.Array.Empty<string>();

        var runtimeEffects = player.currentWeaponInstance.RuntimeEffects;

        if (runtimeEffects == null || runtimeEffects.Count == 0)
            return System.Array.Empty<string>();

        string[] ids = new string[runtimeEffects.Count];

        for (int i = 0; i < runtimeEffects.Count; i++)
        {
            var effect = runtimeEffects[i];

            if (effect == null)
            {
                ids[i] = "";
                continue;
            }

            ids[i] = effect.name;
        }

        return ids;
    }
}