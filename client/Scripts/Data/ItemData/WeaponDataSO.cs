using System.Collections.Generic;
using UnityEngine;

[CreateAssetMenu(menuName = "RPG Setup/Item Data/Weapon item", fileName = "Weapon data - ")]

[System.Serializable]
public class WeaponStatModifier
{
    public StatType statType; // 使用你现成的 StatType 枚举
    public float value;       // 加多少数值
}
public class WeaponDataSO : EquipmentDataSO
{
    [Header("武器基础配置")]
    [Tooltip("这把武器属于什么类型？")]
    public WeaponCategory category = WeaponCategory.Melee;

    [Header("Weapon Type")]
    public bool isRanged; // 勾选表示枪，不勾选表示刀
    [Header("Weapon Specific")]
    public GameObject weaponPrefab;

    public float baseAttackCooldown;

    [Header("武器属性加成")]
    public ElementType weaponElement = ElementType.None; // 武器自带的元素属性
    public WeaponStatModifier[] statModifiers;
    [Header("武器特殊能力")]
    public List<WeaponEffectSO> weaponEffects; // 🌟 挂载点在这里！
    // --- 补上下面这两个字段 ---
    [Header("Bullet Settings")]
    public float bulletSpeed;         // 子弹飞行速度
    public DamageScaleData damageScaleData; // 伤害缩放数据（用于你的 GetAttackData 方法）
     public GameObject bulletPrefab;

    [Header("Detection")]
    [Tooltip("近战武器用的范围半径")]
    public float hitboxRadius;




    [Header("Ranged Specific (枪械专属参数)")]
    [Tooltip("是否支持长按连发")]
    public bool isAutomatic = false;
    [Tooltip("每次开火发射的子弹数量")]
    public int bulletsPerShot = 1;
    [Tooltip("子弹散射角度 (0为绝对精准)")]
    public float spreadAngle = 0f;
    [Tooltip("子弹存活时间(秒)。配合 bulletSpeed 共同决定武器射程")]
    public float bulletLifeTime = 2f; // 默认2秒


    public string weaponId;
    public string bulletId;
}