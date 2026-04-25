using System;

[Serializable]
public class PlayerInputCmd
{
    // 输入序号：客户端本地递增
    public int seq;

    // 客户端本地模拟 tick（可选，但建议保留）
    public int tick;

    // -------------------------
    // 基础移动输入
    // -------------------------
    public float moveX;
    public bool jumpPressed;
    public bool downHeld;
    public bool dropPressed;

    // -------------------------
    // 攻击输入
    // -------------------------
    public bool attackPressed;
    public bool attackHeld;
    public bool attackReleased;

    // -------------------------
    // 瞄准
    // -------------------------
    public float aimX;
    public float aimY;

    // -------------------------
    // 客户端本地状态摘要
    // 这些不是权威结果，只是发给服务器做参考 / 调试 / 对账
    // -------------------------
    public string clientState;
    public bool clientGrounded;
    public int clientJumpCount;

    public float clientPosX;
    public float clientPosY;
    public float clientVelX;
    public float clientVelY;

    // -------------------------
    // 当前装备
    // -------------------------
    public string equippedWeaponId;
    public string[] equippedEffectIds;
}