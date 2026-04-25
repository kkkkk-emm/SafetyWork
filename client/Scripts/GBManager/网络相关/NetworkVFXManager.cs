using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class NetworkVFXManager : MonoBehaviour
{
    public static NetworkVFXManager Instance { get; private set; }

    [System.Serializable]
    public class VFXEntry
    {
        public string vfxId;
        public GameObject prefab;
        public float defaultLifetime = 2f;
    }

    [Header("VFX 映射")]
    [SerializeField] private VFXEntry[] vfxEntries;

    [Header("默认 VFX")]
    [SerializeField] private GameObject defaultVfxPrefab;
    [SerializeField] private float defaultLifetime = 2f;

    [Header("Root")]
    [SerializeField] private Transform vfxRoot;

    [Header("调试")]
    [SerializeField] private bool debugLog = true;

    private readonly Dictionary<string, VFXEntry> entryById = new Dictionary<string, VFXEntry>();

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Debug.LogWarning("[NetworkVFXManager] 场景里存在多个 NetworkVFXManager，销毁重复对象。");
            Destroy(gameObject);
            return;
        }

        Instance = this;

        if (vfxRoot == null)
            vfxRoot = transform;

        BuildMap();
    }

    private void BuildMap()
    {
        entryById.Clear();

        if (vfxEntries == null)
            return;

        foreach (var entry in vfxEntries)
        {
            if (entry == null)
                continue;

            if (string.IsNullOrWhiteSpace(entry.vfxId))
                continue;

            if (entry.prefab == null)
                continue;

            if (entryById.ContainsKey(entry.vfxId))
                Debug.LogWarning($"[NetworkVFXManager] 重复 vfxId={entry.vfxId}，后者覆盖前者。");

            entryById[entry.vfxId] = entry;
        }
    }

    public void Spawn(string vfxId, float x, float y, float rotationDeg = 0f, float scale = 1f)
    {
        GameObject prefab = defaultVfxPrefab;
        float lifetime = defaultLifetime;

        if (!string.IsNullOrWhiteSpace(vfxId) && entryById.TryGetValue(vfxId, out VFXEntry entry))
        {
            prefab = entry.prefab;
            lifetime = entry.defaultLifetime > 0f ? entry.defaultLifetime : defaultLifetime;
        }

        if (prefab == null)
        {
            Debug.LogWarning($"[NetworkVFXManager] 找不到 VFX prefab. vfxId={vfxId}");
            return;
        }

        Vector3 pos = new Vector3(x, y, 0f);
        Quaternion rot = Quaternion.Euler(0f, 0f, rotationDeg);

        GameObject obj = Instantiate(prefab, pos, rot, vfxRoot);
        obj.transform.localScale *= Mathf.Max(0.01f, scale);

        if (debugLog)
        {
            Debug.Log(
                $"[NetworkVFXManager] Spawn vfxId={vfxId} " +
                $"pos=({x:F2},{y:F2}) rot={rotationDeg:F1} scale={scale:F2}"
            );
        }

        if (lifetime > 0f)
            StartCoroutine(DestroyAfter(obj, lifetime));
    }

    public void SpawnExplosion(float x, float y, float radius)
    {
        // scale 可以根据爆炸半径调大
        float scale = Mathf.Max(0.5f, radius);
        Spawn("explosion", x, y, 0f, scale);
    }

    public void SpawnHit(float x, float y)
    {
        Spawn("hit", x, y);
    }

    public void SpawnParry(float x, float y)
    {
        Spawn("parry", x, y);
    }

    public void SpawnMelee(float x, float y, float radius)
    {
        Spawn("melee_hitbox", x, y, 0f, Mathf.Max(0.5f, radius));
    }

    public void SpawnProjectileDestroy(float x, float y)
    {
        Spawn("projectile_destroy", x, y);
    }

    private IEnumerator DestroyAfter(GameObject obj, float seconds)
    {
        yield return new WaitForSeconds(seconds);

        if (obj != null)
            Destroy(obj);
    }
}