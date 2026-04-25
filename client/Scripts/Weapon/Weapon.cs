using UnityEngine;
using System.Collections.Generic;
using System.Collections; // 如果用 List 需要加上这个命名空间

public class Weapon : MonoBehaviour
{
    public WeaponDataSO data;

    // [新增] 武器自己记住它的持有者
    protected Entity ownerEntity;
    protected Entity_Stats ownerStats;
    protected float lastAttackTime;

    // 🌟 1. 缓存目标图层，供继承的子类（MeleeWeapon / RangedWeapon）随时调用
    public LayerMask targetMask;

    public List<WeaponEffectSO> RuntimeEffects => runtimeEffects;
    [SerializeField] protected List<WeaponEffectSO> runtimeEffects = new List<WeaponEffectSO>();
    private Dictionary<WeaponEffectSO, Coroutine> activeCoroutines = new Dictionary<WeaponEffectSO, Coroutine>();
    // 只有在装备这把武器的那一刻，调用一次

    protected virtual void Start()
    {
        // 游戏开始时，把 ScriptableObject 里的初始特效塞进“运行时口袋”
        if (data != null && data.weaponEffects != null)
        {
            foreach (var effect in data.weaponEffects)
            {
                // 注意：这里只是引用，不会修改硬盘数据
                runtimeEffects.Add(effect);
            }
        }
    }
    public virtual void SetupWeapon(WeaponDataSO weaponData, Entity owner)
    {
        this.data = weaponData;
        this.ownerEntity = owner;

        if (owner != null)
        {
            this.ownerStats = owner.GetComponent<Entity_Stats>();

            // ==========================================
            // 🌟 核心补充：在装备武器时，直接从主人身上获取目标图层！
            // ==========================================
            Player_Combat playerCombat = owner.GetComponent<Player_Combat>();
            if (playerCombat != null)
            {
                // 注意检查你 Player_Combat 里的变量名是大小写（WhatIsTarget 还是 whatIsTarget）
                this.targetMask = playerCombat.whatIsTarget;
            }
            // 防呆提醒：如果以后有拿武器的敌人，可以在这里再加一个分支
            // else if (owner.GetComponent<Enemy_Combat>() != null) { ... }
        }
    }

    // 现在的 ExecuteAttack 不需要任何参数了！动画事件可以直接无脑调用它
    public virtual void ExecuteAttack()
    {
        // 1. 冷却检查
        if (Time.time < lastAttackTime + data.baseAttackCooldown) return;
        lastAttackTime = Time.time;

        // ==========================================
        // 🌟 钩子 1：触发【攻击瞬间】的特效
        // ==========================================

        // 💡 关键点：这里不再读 data.weaponEffects，而是读我们维护的 runtimeEffects
        if (runtimeEffects != null && runtimeEffects.Count > 0)
        {
            // 使用 for 循环或转换成数组备份，防止在遍历过程中列表被修改（比如某个特效刚好到时被删了）
            var effectsToExecute = runtimeEffects.ToArray();

            foreach (var effect in effectsToExecute)
            {
                if (effect == null) continue;

                // 依然传这些参数，保持兼容性
                effect.OnAttackExecute(ownerEntity, data, transform, data.hitboxRadius);

                Debug.Log($"武器 {data.name} 触发了动态特效: {effect.name}");
            }
        }
    }

    // ==========================================
    // 🌟 钩子 2：提供给子类或子弹调用的【命中结算】通道
    // ==========================================
    public void TriggerOnTargetHit(Entity target)
    {
        if (data.weaponEffects != null)
        {
            foreach (var effect in data.weaponEffects)
            {
                // 触发特效！（如：吸血、挂易伤、元素爆炸）
                effect.OnTargetHit(ownerEntity, data, target); // 传 data！
            }
        }
    }

    // ==========================================
    // 🌟 钩子 3：提供给远程武器子弹生成的通道
    // ==========================================
    public void TriggerOnProjectileSpawned(Projectile proj)
    {
        if (data.weaponEffects != null)
        {
            foreach (var effect in data.weaponEffects)
            {
                // 让发牌官给这颗刚出膛的实体子弹挂上 Behavior 外挂！
                effect.OnProjectileSpawned(proj, ownerEntity, data);
            }
        }
    }

    public void AddEffect(WeaponEffectSO newEffect)
    {
        if (newEffect == null) return;

        // ==========================================
        // 🌟 4. 分类检查拦截逻辑
        // ==========================================
        if (!newEffect.IsCompatibleWith(data.category))
        {
            Debug.LogWarning($"类型不匹配：{data.category} 武器无法挂载 {newEffect.name} 特效");
            return;
        }

        if (runtimeEffects.Contains(newEffect))
        {
            if (activeCoroutines.ContainsKey(newEffect) && activeCoroutines[newEffect] != null)
            {
                StopCoroutine(activeCoroutines[newEffect]);
            }
        }
        else
        {
            runtimeEffects.Add(newEffect);
            Debug.Log($"武器 {data.name} 已加载动态特效: {newEffect.name}");
        }

        if (newEffect.duration > 0)
        {
            Coroutine timer = StartCoroutine(EffectExpiryRoutine(newEffect));
            activeCoroutines[newEffect] = timer;
        }
    }
    private IEnumerator EffectExpiryRoutine(WeaponEffectSO effect)
    {
        yield return new WaitForSeconds(effect.duration);

        if (runtimeEffects.Contains(effect))
        {
            runtimeEffects.Remove(effect);
            activeCoroutines.Remove(effect); // 字典里也清掉
            Debug.Log($"特效已过期: {effect.name}");
        }
    }

    public virtual void PlayAttackVisual()
    {
    }
}