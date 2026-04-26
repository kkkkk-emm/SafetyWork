using UnityEngine;

[CreateAssetMenu(fileName = "Effect_SwordWave", menuName = "Weapon Effects/Sword Wave (剑气)")]
public class Effect_SwordWave : WeaponEffectSO
{
    [Header("剑气设置")]
    public GameObject wavePrefab;
    // public WeaponDataSO waveData;  // 这个删掉，用咱们上一步改的 sourceData

    public override void OnAttackExecute(Entity wielder, WeaponDataSO sourceData, Transform hitPoint, float radius)
    {
        if (wavePrefab == null) return;

        // 🌟 核心破局点：hitPoint 是正在挥舞的刀，而它的 parent 才是永远瞄准鼠标的挂载点！
        Transform aimPoint = hitPoint.parent;

        // 1. 获取绝对正确的发射方向（世界坐标系下的 right，已经自动处理了主角翻转）
        Vector2 forwardDir = aimPoint.right;

        // 2. 为了防止主角 Scale.x = -1 导致剑气图片翻转错乱，我们用方向重新算一个纯净的旋转角度
        float angle = Mathf.Atan2(forwardDir.y, forwardDir.x) * Mathf.Rad2Deg;
        Quaternion cleanRotation = Quaternion.Euler(0, 0, angle);

        // 3. 用纯净的角度生成剑气（依然在刀刃 hitPoint.position 生成，但角度用算出来的）
        GameObject waveObj = Instantiate(wavePrefab, hitPoint.position, cleanRotation);

        Projectile proj = waveObj.GetComponent<Projectile>();
        if (proj != null)
        {
            // 完美复用源武器数据，朝着绝对正前方飞去！
            proj.SetupProjectile(wielder, sourceData, forwardDir,wielder.entity_Combat.whatIsTarget,wielder.currentWeaponInstance.RuntimeEffects);
        }
    }
}