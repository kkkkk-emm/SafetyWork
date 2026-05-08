using System.Collections.Generic;
using UnityEngine;

[DisallowMultipleComponent]
public class RemotePlayerInterpolator : MonoBehaviour
{
    private struct Frame
    {
        public int tick;
        public Vector2 pos;
        public Vector2 vel;
        public string state;
        public bool grounded;
        public int jumpCount;
    }

    [Header("远端插值")]
    [SerializeField] private int interpolationDelayTicks = 3;
    [SerializeField] private int maxBufferedFrames = 30;

    [Header("修正")]
    [SerializeField] private float snapDistance = 5f;
    [SerializeField] private float smoothStrength = 18f;
    [SerializeField] private float maxExtrapolateSeconds = 0.12f;

    private readonly List<Frame> frames = new List<Frame>();

    private Player player;
    private int latestReceivedTick = -1;
    private bool initialized;

    private void Awake()
    {
        player = GetComponent<Player>();
    }

    private void OnDisable()
    {
        Clear();
    }

    public void PushServerFrame(
        int tick,
        float posX,
        float posY,
        float velX,
        float velY,
        string state,
        bool grounded,
        int jumpCount
    )
    {
        if (frames.Count > 0)
        {
            int lastTick = frames[frames.Count - 1].tick;

            // 旧包 / 重复包直接丢掉
            if (tick <= lastTick)
                return;
        }

        latestReceivedTick = Mathf.Max(latestReceivedTick, tick);

        Frame frame = new Frame
        {
            tick = tick,
            pos = new Vector2(posX, posY),
            vel = new Vector2(velX, velY),
            state = state,
            grounded = grounded,
            jumpCount = jumpCount
        };

        frames.Add(frame);

        while (frames.Count > maxBufferedFrames)
            frames.RemoveAt(0);

        if (!initialized)
        {
            initialized = true;
            ApplyPosition(frame.pos, frame.vel.y);
        }
    }

    private void Update()
    {
        if (!initialized || frames.Count == 0)
            return;

        float renderTick = latestReceivedTick - interpolationDelayTicks;

        Vector2 targetPos;
        float targetVelY;

        Sample(renderTick, out targetPos, out targetVelY);

        Vector2 currentPos = transform.position;
        float distance = Vector2.Distance(currentPos, targetPos);

        if (distance > snapDistance)
        {
            ApplyPosition(targetPos, targetVelY);
            return;
        }

        float t = 1f - Mathf.Exp(-smoothStrength * Time.deltaTime);
        Vector2 smoothed = Vector2.Lerp(currentPos, targetPos, t);

        ApplyPosition(smoothed, targetVelY);
    }

    private void Sample(float renderTick, out Vector2 pos, out float velY)
    {
        if (frames.Count == 1)
        {
            pos = frames[0].pos;
            velY = frames[0].vel.y;
            return;
        }

        for (int i = 0; i < frames.Count - 1; i++)
        {
            Frame a = frames[i];
            Frame b = frames[i + 1];

            if (a.tick <= renderTick && renderTick <= b.tick)
            {
                float denom = Mathf.Max(1f, b.tick - a.tick);
                float t = Mathf.Clamp01((renderTick - a.tick) / denom);

                pos = Vector2.Lerp(a.pos, b.pos, t);
                velY = Mathf.Lerp(a.vel.y, b.vel.y, t);
                return;
            }
        }

        if (renderTick <= frames[0].tick)
        {
            pos = frames[0].pos;
            velY = frames[0].vel.y;
            return;
        }

        // 如果 renderTick 比最新帧还新，短暂外推
        Frame last = frames[frames.Count - 1];

        float ticksAhead = renderTick - last.tick;
        float secondsAhead = Mathf.Clamp(
            ticksAhead * Time.fixedDeltaTime,
            0f,
            maxExtrapolateSeconds
        );

        pos = last.pos + last.vel * secondsAhead;
        velY = last.vel.y;
    }

    private void ApplyPosition(Vector2 pos, float velY)
    {
        if (player == null)
            player = GetComponent<Player>();

        if (player != null)
        {
            player.ApplyServerPosition(pos.x, pos.y, velY);
        }
        else
        {
            transform.position = new Vector3(pos.x, pos.y, transform.position.z);
        }
    }

    public void Clear()
    {
        frames.Clear();
        latestReceivedTick = -1;
        initialized = false;
    }
}