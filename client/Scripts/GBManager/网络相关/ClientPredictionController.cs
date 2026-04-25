using System;
using System.Collections.Generic;
using UnityEngine;

public class ClientPredictionController : MonoBehaviour
{
    [Header("引用")]
    [SerializeField] private Player player;

    [Header("参数")]
    [SerializeField] private float fixedDt = 0.05f;
    [SerializeField] private float moveSpeed = 3.2f;
    [SerializeField] private float gravity = -0.4f;
    [SerializeField] private float jumpVelocity = 6.0f;
    [SerializeField] private float fallSpeedCap = -7.2f;
    [SerializeField] private float snapThreshold = 1.0f;

    [Header("地图参数，需要和服务器一致")]
    [SerializeField] private float groundEpsilon = 0.001f;
    [SerializeField] private float playerHalfWidth = 0.46f;
    [SerializeField] private float playerHalfHeight = 0.42f;
    [SerializeField] private float offsetY = 0.7f;

    [Header("调试")]
    [SerializeField] private bool debugLog = true;

    private readonly List<PlayerInputCmd> pendingInputs = new List<PlayerInputCmd>();
    private PredictedPlayerState predictedState;

    private float GroundY => -1.45f + offsetY;
    private const int MaxJumpCount = 2;

    [Serializable]
    private struct PlatformData
    {
        public float xMin;
        public float xMax;
        public float y;
        public string kind;

        public PlatformData(float xMin, float xMax, float y, string kind)
        {
            this.xMin = xMin;
            this.xMax = xMax;
            this.y = y;
            this.kind = kind;
        }
    }

    [Serializable]
    private struct RectColliderData
    {
        public float xMin;
        public float xMax;
        public float yMin;
        public float yMax;
        public string kind;

        public RectColliderData(float xMin, float xMax, float yMin, float yMax, string kind)
        {
            this.xMin = xMin;
            this.xMax = xMax;
            this.yMin = yMin;
            this.yMax = yMax;
            this.kind = kind;
        }
    }

    private List<PlatformData> mapPlatforms;
    private List<RectColliderData> mapWalls;

    private void Awake()
    {
        BuildMapData();

        if (player != null)
            ResetPredictedStateFromPlayer();
    }

    public void BindPlayer(Player newPlayer)
    {
        player = newPlayer;
        pendingInputs.Clear();

        if (player == null)
        {
            Debug.LogError("[ClientPredictionController] BindPlayer 收到空 Player");
            return;
        }

        ResetPredictedStateFromPlayer();

        Debug.Log($"[ClientPredictionController] BindPlayer -> {player.name}");
    }

    private void ResetPredictedStateFromPlayer()
    {
        Vector3 p = player.transform.position;

        predictedState.posX = p.x;
        predictedState.posY = TransformYToFootY(p.y);
        predictedState.velX = 0f;
        predictedState.velY = 0f;
        predictedState.grounded = true;
        predictedState.jumpCount = 0;
        predictedState.acceptedDrop = false;
        predictedState.stateName = "Grounded";
    }

    public void AddLocalInput(PlayerInputCmd cmd)
    {
        pendingInputs.Add(cmd);
        Simulate(ref predictedState, cmd);
        ApplyPredictedState();
    }

    public void Reconcile(MatchSnapshot snapshot, string localClientId)
    {
        if (snapshot == null)
            return;

        if (player == null)
            return;

        if (string.IsNullOrWhiteSpace(localClientId))
            return;

        PlayerSnapshot localPlayer = null;

        if (snapshot.players != null)
        {
            foreach (PlayerSnapshot ps in snapshot.players)
            {
                if (ps == null)
                    continue;

                if (ps.clientId == localClientId)
                {
                    localPlayer = ps;
                    break;
                }
            }
        }

        if (localPlayer == null)
            return;

        // 移除服务器已经处理过的输入
        pendingInputs.RemoveAll(cmd => cmd.seq <= snapshot.lastProcessedSeq);

        float beforeX = predictedState.posX;
        float beforeY = predictedState.posY;

        // 服务器位置是 footY，predictedState 里也统一存 footY
        predictedState.posX = localPlayer.posX;
        predictedState.posY = localPlayer.posY;
        predictedState.velX = localPlayer.velX;
        predictedState.velY = localPlayer.velY;
        predictedState.grounded = localPlayer.grounded;
        predictedState.jumpCount = localPlayer.jumpCount;
        predictedState.stateName = localPlayer.state;

        bool serverForcedState =
            localPlayer.isDead ||
            localPlayer.state == "Dead" ||
            localPlayer.state == "Respawn" ||
            localPlayer.state == "Hitstun";

        bool recentlyHit =
            localPlayer.lastHitTick >= 0 &&
            snapshot.tick - localPlayer.lastHitTick < 12;

        if (serverForcedState || recentlyHit)
        {
            // 被击飞、死亡、复活等待期间，服务器是绝对权威。
            // 不 replay pending input，否则本地会把自己预测到错误高度。
            pendingInputs.Clear();

            if (debugLog)
            {
                Debug.Log(
                    $"[Reconcile] SERVER FORCED local={localClientId} " +
                    $"state={localPlayer.state} isDead={localPlayer.isDead} " +
                    $"tick={snapshot.tick} lastHitTick={localPlayer.lastHitTick} " +
                    $"pos=({localPlayer.posX:F3},{localPlayer.posY:F3}) " +
                    $"vel=({localPlayer.velX:F3},{localPlayer.velY:F3})"
                );
            }

            ApplyPredictedState();
            return;
        }

        // 普通移动状态才 replay 未确认输入
        foreach (PlayerInputCmd cmd in pendingInputs)
        {
            Simulate(ref predictedState, cmd);
        }

        float error = Vector2.Distance(
            new Vector2(beforeX, beforeY),
            new Vector2(predictedState.posX, predictedState.posY)
        );

        if (error > snapThreshold)
        {
            if (debugLog)
            {
                Debug.LogWarning(
                    $"[Reconcile] Large error={error:F3}, trust server and clear pending. " +
                    $"server=({localPlayer.posX:F3},{localPlayer.posY:F3}) " +
                    $"before=({beforeX:F3},{beforeY:F3})"
                );
            }

            pendingInputs.Clear();

            predictedState.posX = localPlayer.posX;
            predictedState.posY = localPlayer.posY;
            predictedState.velX = localPlayer.velX;
            predictedState.velY = localPlayer.velY;
            predictedState.grounded = localPlayer.grounded;
            predictedState.jumpCount = localPlayer.jumpCount;
            predictedState.stateName = localPlayer.state;
        }

        ApplyPredictedState();

        if (debugLog)
        {
            Debug.Log(
                $"[Reconcile] local={localClientId} tick={snapshot.tick} " +
                $"ack={snapshot.lastProcessedSeq} pending={pendingInputs.Count} " +
                $"state={predictedState.stateName} " +
                $"pos=({predictedState.posX:F3},{predictedState.posY:F3}) " +
                $"vel=({predictedState.velX:F3},{predictedState.velY:F3})"
            );
        }
    }

    public PredictedPlayerState GetPredictedState()
    {
        return predictedState;
    }

    private void ApplyPredictedState()
    {
        if (player == null)
            return;

        float displayY = predictedState.posY + playerHalfHeight;

        player.SetLogicalPosition(
            predictedState.posX,
            displayY
        );

        player.ApplyServerState(
            predictedState.stateName,
            predictedState.grounded,
            predictedState.jumpCount
        );
    }
    private void Simulate(ref PredictedPlayerState state, PlayerInputCmd cmd)
    {
        float inputX = Mathf.Clamp(cmd.moveX, -1f, 1f);
        bool jumpPressed = cmd.jumpPressed;
        bool downHeld = cmd.downHeld;
        bool dropPressed = cmd.dropPressed;

        state.acceptedDrop = false;

        state.velX = inputX * moveSpeed;
        float nextX = state.posX + state.velX * fixedDt;

        if (!HitsWall(nextX, state.posY))
            state.posX = nextX;
        else
            state.velX = 0f;

        RefreshGroundedFromMap(ref state);

        PlatformData? currentPlatform = GetStandingPlatform(state.posX, state.posY);

        if (dropPressed && downHeld)
        {
            if (currentPlatform.HasValue && currentPlatform.Value.kind == "oneway")
            {
                state.acceptedDrop = true;
                state.grounded = false;
                state.stateName = "Fall";
                state.velY = Mathf.Min(state.velY, -2f);
                state.posY -= 0.15f;
            }
        }
        else if (jumpPressed)
        {
            if (state.grounded)
            {
                state.grounded = false;
                state.jumpCount = 1;
                state.stateName = "Jump";
                state.velY = jumpVelocity;
            }
            else if (state.jumpCount < MaxJumpCount)
            {
                state.jumpCount += 1;
                state.stateName = "Jump";
                state.velY = jumpVelocity;
            }
        }

        StepVertical(ref state);
        RefreshGroundedFromMap(ref state);

        if (state.grounded)
        {
            if (Mathf.Abs(inputX) > 0.01f)
                state.stateName = "Player_MoveState";
            else
                state.stateName = "Player_IdleState";
        }
    }

    private void RefreshGroundedFromMap(ref PredictedPlayerState state)
    {
        if (state.velY > 0f)
        {
            state.grounded = false;
            return;
        }

        PlatformData? standingPlatform = GetStandingPlatform(state.posX, state.posY);

        if (standingPlatform.HasValue)
        {
            state.grounded = true;
            state.velY = 0f;
            state.posY = standingPlatform.Value.y;

            if (state.stateName != "Dash" && state.stateName != "BasicAttack")
                state.stateName = "Grounded";

            state.jumpCount = 0;
        }
        else
        {
            state.grounded = false;

            if (state.stateName == "Grounded")
                state.stateName = "Airborne";
        }
    }
    public bool CanJumpDebug()
    {
        return predictedState.grounded || predictedState.jumpCount < MaxJumpCount;
    }

    public bool IsGroundedDebug()
    {
        return predictedState.grounded;
    }

    public int JumpCountDebug()
    {
        return predictedState.jumpCount;
    }

    public float PredictedPosXDebug()
    {
        return predictedState.posX;
    }

    public float PredictedPosYDebug()
    {
        return predictedState.posY;
    }

    public float PredictedVelYDebug()
    {
        return predictedState.velY;
    }
    private void StepVertical(ref PredictedPlayerState state)
    {
        PlatformData? standing = GetStandingPlatform(state.posX, state.posY);

        if (standing.HasValue && state.grounded && state.velY <= 0f)
        {
            state.posY = standing.Value.y;
            state.velY = 0f;
            return;
        }

        state.velY += gravity;

        if (state.velY < fallSpeedCap)
            state.velY = fallSpeedCap;

        float previousY = state.posY;
        float nextY = state.posY + state.velY * fixedDt;

        PlatformData? landing = FindLandingPlatform(state.posX, previousY, nextY);

        if (landing.HasValue && state.velY <= 0f)
        {
            state.posY = landing.Value.y;
            state.velY = 0f;
            state.grounded = true;

            if (state.stateName != "Dash" && state.stateName != "BasicAttack")
                state.stateName = "Grounded";
        }
        else
        {
            state.posY = nextY;
            state.grounded = false;

            if (state.velY < 0f &&
                state.stateName != "Jump" &&
                state.stateName != "Dash" &&
                state.stateName != "BasicAttack")
            {
                state.stateName = "Fall";
            }
        }
    }

    private bool HitsWall(float x, float footY)
    {
        float playerLeft = x - playerHalfWidth;
        float playerRight = x + playerHalfWidth;
        float playerBottom = footY;
        float playerTop = footY + playerHalfHeight * 2f;

        foreach (RectColliderData wall in mapWalls)
        {
            bool overlapX = playerRight > wall.xMin && playerLeft < wall.xMax;
            bool overlapY = playerTop > wall.yMin && playerBottom < wall.yMax;

            if (overlapX && overlapY)
                return true;
        }

        return false;
    }

    private PlatformData? GetStandingPlatform(float x, float footY)
    {
        foreach (PlatformData platform in mapPlatforms)
        {
            if (IsOnPlatform(x, footY, platform))
                return platform;
        }

        return null;
    }

    private bool IsOnPlatform(float x, float footY, PlatformData platform)
    {
        bool withinX = (x + playerHalfWidth) >= platform.xMin &&
                       (x - playerHalfWidth) <= platform.xMax;

        bool closeY = Mathf.Abs(footY - platform.y) <= groundEpsilon;

        return withinX && closeY;
    }

    private PlatformData? FindLandingPlatform(float x, float previousY, float nextY)
    {
        List<PlatformData> candidates = new List<PlatformData>();

        foreach (PlatformData platform in mapPlatforms)
        {
            bool withinX = (x + playerHalfWidth) >= platform.xMin &&
                           (x - playerHalfWidth) <= platform.xMax;

            bool crossedY = previousY >= platform.y && platform.y >= nextY;

            if (withinX && crossedY)
                candidates.Add(platform);
        }

        if (candidates.Count == 0)
            return null;

        candidates.Sort((a, b) => b.y.CompareTo(a.y));
        return candidates[0];
    }

    private float TransformYToFootY(float transformY)
    {
        return transformY - playerHalfHeight;
    }

    private float FootYToTransformY(float footY)
    {
        return footY + playerHalfHeight;
    }

    private void BuildMapData()
    {
        mapPlatforms = new List<PlatformData>
        {
            new PlatformData(-9f,    29f,    GroundY,           "solid"),
            new PlatformData(-1.25f, 1.25f,  1.0f + offsetY,    "oneway"),
            new PlatformData(8.75f,  11.25f, 1.0f + offsetY,    "oneway"),
            new PlatformData(18.75f, 21.25f, 1.0f + offsetY,    "oneway"),
            new PlatformData(3.75f,  6.25f,  2.5f + offsetY,    "oneway"),
            new PlatformData(13.75f, 16.25f, 2.5f + offsetY,    "oneway"),
        };

        mapWalls = new List<RectColliderData>
        {
            new RectColliderData(-9.0f, -8.5f, GroundY, GroundY + 1.5f, "solid"),
            new RectColliderData(29.0f, 29.5f, GroundY, GroundY + 1.5f, "solid"),
        };
    }
}