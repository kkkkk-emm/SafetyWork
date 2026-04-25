using System;

[Serializable]
public struct PredictedPlayerState
{
    // 位置 / 速度
    // 约定：posY 表示脚底 y
    public float posX;
    public float posY;
    public float velX;
    public float velY;

    // 基础移动状态
    public bool grounded;
    public int jumpCount;
    public bool acceptedDrop;
    public string stateName;

    // 战斗状态
    public float damagePercent;
    public int stocks;
    public bool isDead;

    public float lastKnockbackX;
    public float lastKnockbackY;
    public int lastHitTick;

    public void ResetToDefaults(float startX, float startFootY)
    {
        posX = startX;
        posY = startFootY;
        velX = 0f;
        velY = 0f;

        grounded = true;
        jumpCount = 0;
        acceptedDrop = false;
        stateName = "Grounded";

        damagePercent = 0f;
        stocks = 3;
        isDead = false;

        lastKnockbackX = 0f;
        lastKnockbackY = 0f;
        lastHitTick = -1;
    }
}