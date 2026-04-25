using UnityEngine;
using DG.Tweening;
using UnityEngine.Rendering;

public class TerrariaStyleWeapon : MeleeWeapon
{
    [Header("挥砍设置")]
    public float startAngle = 120f;   // 起始角度（脑后）
    public float swingAngle = 150f;   // 挥砍的弧度大小
    public float swingDuration = 0.25f; // 挥砍耗时
    public float bigScale = 2f;
    // 🌟 换成专门掌管渲染的组件
    private SpriteRenderer weaponRenderer;

    private void Start()
    {
        // 自动去自己身上（或者子物体上）找 SpriteRenderer
        weaponRenderer = GetComponentInChildren<SpriteRenderer>();

        // 开局先隐身，等按攻击键再出来
        if (weaponRenderer != null)
        {
            weaponRenderer.enabled = false;
        }
    }

    public override void ExecuteAttack()
    {
        if (Time.time < lastAttackTime + data.baseAttackCooldown)
            return;

        base.ExecuteAttack();

        PlayAttackVisual();
    }


    public override void PlayAttackVisual()
    {
        Debug.Log("Melee visual attack");

        transform.DOKill();

        transform.localRotation = Quaternion.Euler(0, 0, startAngle);
        transform.localScale = Vector3.one;

        if (weaponRenderer == null)
            weaponRenderer = GetComponentInChildren<SpriteRenderer>();

        if (weaponRenderer != null)
            weaponRenderer.enabled = true;

        float endAngle = startAngle - swingAngle;

        transform.DOLocalRotate(new Vector3(0, 0, endAngle), swingDuration, RotateMode.Fast)
            .SetEase(Ease.OutCubic)
            .OnComplete(() =>
            {
                if (weaponRenderer != null)
                    weaponRenderer.enabled = false;
            });

        transform.DOScale(new Vector3(bigScale, bigScale, 1f), swingDuration)
            .SetEase(Ease.OutBack);
    }
}