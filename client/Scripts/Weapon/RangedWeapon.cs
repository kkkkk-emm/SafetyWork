using System.Collections.Generic;
using UnityEngine;

public class RangedWeapon : Weapon
{
    [SerializeField] private Transform firePoint;

    WeaponProceduralAnimator animator;
    [SerializeField] private bool disableLocalProjectileSpawn = true;
    protected override void Start()
    {
        // 必须调用 base.Start() 初始化特效
        base.Start();

        animator = GetComponentInChildren<WeaponProceduralAnimator>();

        // 🚨 删除了原来 ownerEntity.GetComponent 的代码！
        // 因为父类 Weapon.cs 的 SetupWeapon() 已经会处理 targetMask 了，这里不要去碰它！
    }

    public override void ExecuteAttack()
    {
        // ==========================================
        // 🌟 防呆保护：如果武器还没认主，或者没配数据，直接不开火！
        // 这样可以彻底把 NullReferenceException 扼杀在摇篮里
        // ==========================================
        if (ownerEntity == null || data == null)
        {
            Debug.LogWarning($"【武器警告】{gameObject.name} 还没有绑定主人！请检查玩家脚本是否调用了 weapon.SetupWeapon(...)！");
            return;
        }

        // 1. 检查 CD
        if (Time.time < lastAttackTime + data.baseAttackCooldown) return;

        // 2. 调用父类的攻击逻辑（更新冷却时间，并触发攻击瞬间的动态特效）
        base.ExecuteAttack();

        // 触发程序化动画
        if (animator != null) animator.ApplyRecoil();

        int bulletCount = data.bulletsPerShot > 0 ? data.bulletsPerShot : 1;

        for (int i = 0; i < bulletCount; i++)
        {
            // 1. 计算随机偏移角度
            float randomAngle = Random.Range(-data.spreadAngle, data.spreadAngle);

            // 2. 计算子弹实际的飞行方向
            Vector2 fireDirection = Quaternion.Euler(0, 0, randomAngle) * firePoint.right;

            // 3. 计算子弹的初始旋转角度
            Quaternion bulletRotation = firePoint.rotation * Quaternion.Euler(0, 0, randomAngle);

            // 4. 生成并发射！
            if (disableLocalProjectileSpawn)
            {
                Debug.Log("[LOCAL RANGED OFF] 跳过本地 projectile Instantiate，等待服务器快照/事件驱动");
                continue;
            }

            GameObject newBullet = Instantiate(this.data.bulletPrefab, firePoint.position, bulletRotation);
            Projectile script = newBullet.GetComponent<Projectile>();

            if (script != null)
            {
                script.SetupProjectile(ownerEntity, data, fireDirection, targetMask, runtimeEffects);
            }
        }
    }

    public override void PlayAttackVisual()
    {
        WeaponProceduralAnimator animator = GetComponentInChildren<WeaponProceduralAnimator>();

        if (animator != null)
            animator.ApplyRecoil();
    }
}