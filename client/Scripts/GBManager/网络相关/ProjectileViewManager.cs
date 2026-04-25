using System.Collections.Generic;
using UnityEngine;

public class ProjectileViewManager : MonoBehaviour
{
    public static ProjectileViewManager Instance { get; private set; }

    [System.Serializable]
    public class ProjectileViewEntry
    {
        public string visualId;
        public GameObject prefab;
    }

    [Header("Prefab 映射")]
    [SerializeField] private ProjectileViewEntry[] projectilePrefabs;

    [Header("默认 Prefab")]
    [SerializeField] private GameObject defaultProjectilePrefab;

    [Header("Root")]
    [SerializeField] private Transform projectileRoot;

    [Header("表现")]
    [SerializeField] private bool smoothMove = true;
    [SerializeField] private float smoothLerp = 25f;

    [Header("调试")]
    [SerializeField] private bool debugLog = false;

    private readonly Dictionary<string, GameObject> prefabByVisualId = new Dictionary<string, GameObject>();
    private readonly Dictionary<int, ProjectileView> viewsById = new Dictionary<int, ProjectileView>();
    private readonly HashSet<int> aliveIdsThisSnapshot = new HashSet<int>();

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Debug.LogWarning("[ProjectileViewManager] 场景里存在多个 ProjectileViewManager，销毁重复对象。");
            Destroy(gameObject);
            return;
        }

        Instance = this;

        if (projectileRoot == null)
            projectileRoot = transform;

        BuildPrefabMap();
    }

    private void BuildPrefabMap()
    {
        prefabByVisualId.Clear();

        if (projectilePrefabs == null)
            return;

        foreach (var entry in projectilePrefabs)
        {
            if (entry == null)
                continue;

            if (string.IsNullOrWhiteSpace(entry.visualId))
                continue;

            if (entry.prefab == null)
                continue;

            if (prefabByVisualId.ContainsKey(entry.visualId))
            {
                Debug.LogWarning($"[ProjectileViewManager] 重复 visualId={entry.visualId}，后者覆盖前者。");
            }

            prefabByVisualId[entry.visualId] = entry.prefab;
        }
    }

    public void ApplySnapshot(ProjectileSnapshot[] projectiles)
    {
        aliveIdsThisSnapshot.Clear();

        if (projectiles != null)
        {
            foreach (var snapshot in projectiles)
            {
                if (snapshot == null)
                    continue;

                if (!snapshot.alive)
                    continue;

                aliveIdsThisSnapshot.Add(snapshot.projId);

                ProjectileView view = GetOrCreateView(snapshot);
                if (view == null)
                    continue;

                view.ApplySnapshot(snapshot, smoothMove, smoothLerp);
            }
        }

        RemoveMissingViews();
    }

    private ProjectileView GetOrCreateView(ProjectileSnapshot snapshot)
    {
        if (viewsById.TryGetValue(snapshot.projId, out ProjectileView existing) && existing != null)
            return existing;

        GameObject prefab = ResolvePrefab(snapshot);
        if (prefab == null)
        {
            Debug.LogWarning(
                $"[ProjectileViewManager] 找不到 projectile prefab. " +
                $"projId={snapshot.projId}, visualId={snapshot.visualId}, bulletId={snapshot.bulletId}"
            );
            return null;
        }

        Vector3 pos = new Vector3(snapshot.posX, snapshot.posY, 0f);
        Quaternion rot = Quaternion.Euler(0f, 0f, snapshot.rotationDeg);

        GameObject obj = Instantiate(prefab, pos, rot, projectileRoot);
        obj.name = $"ProjectileView_{snapshot.projId}_{snapshot.visualId}";

        ProjectileView view = obj.GetComponent<ProjectileView>();
        if (view == null)
            view = obj.AddComponent<ProjectileView>();

        view.Init(snapshot.projId);

        viewsById[snapshot.projId] = view;

        if (debugLog)
        {
            Debug.Log(
                $"[ProjectileViewManager] Create projId={snapshot.projId} " +
                $"visualId={snapshot.visualId} bulletId={snapshot.bulletId} " +
                $"pos=({snapshot.posX:F2},{snapshot.posY:F2}) rot={snapshot.rotationDeg:F1}"
            );
        }

        return view;
    }

    private GameObject ResolvePrefab(ProjectileSnapshot snapshot)
    {
        if (!string.IsNullOrWhiteSpace(snapshot.visualId) &&
            prefabByVisualId.TryGetValue(snapshot.visualId, out GameObject visualPrefab))
        {
            return visualPrefab;
        }

        if (!string.IsNullOrWhiteSpace(snapshot.bulletId) &&
            prefabByVisualId.TryGetValue(snapshot.bulletId, out GameObject bulletPrefab))
        {
            return bulletPrefab;
        }

        return defaultProjectilePrefab;
    }

    private void RemoveMissingViews()
    {
        if (viewsById.Count == 0)
            return;

        List<int> removeIds = null;

        foreach (var pair in viewsById)
        {
            int projId = pair.Key;
            ProjectileView view = pair.Value;

            if (aliveIdsThisSnapshot.Contains(projId))
                continue;

            if (removeIds == null)
                removeIds = new List<int>();

            removeIds.Add(projId);

            if (view != null)
            {
                if (debugLog)
                    Debug.Log($"[ProjectileViewManager] Destroy projId={projId}");

                Destroy(view.gameObject);
            }
        }

        if (removeIds == null)
            return;

        foreach (int id in removeIds)
            viewsById.Remove(id);
    }

    public void ClearAll()
    {
        foreach (var pair in viewsById)
        {
            if (pair.Value != null)
                Destroy(pair.Value.gameObject);
        }

        viewsById.Clear();
        aliveIdsThisSnapshot.Clear();
    }
}

public class ProjectileView : MonoBehaviour
{
    public int ProjId { get; private set; }

    private Vector3 targetPosition;
    private Quaternion targetRotation;
    private bool hasSnapshot;

    public void Init(int projId)
    {
        ProjId = projId;
    }

    public void ApplySnapshot(ProjectileSnapshot snapshot, bool smoothMove, float smoothLerp)
    {
        targetPosition = new Vector3(snapshot.posX, snapshot.posY, 0f);
        targetRotation = Quaternion.Euler(0f, 0f, snapshot.rotationDeg);
        hasSnapshot = true;

        if (!smoothMove)
        {
            transform.position = targetPosition;
            transform.rotation = targetRotation;
        }
    }

    private void Update()
    {
        if (!hasSnapshot)
            return;

        transform.position = Vector3.Lerp(
            transform.position,
            targetPosition,
            1f - Mathf.Exp(-25f * Time.deltaTime)
        );

        transform.rotation = Quaternion.Slerp(
            transform.rotation,
            targetRotation,
            1f - Mathf.Exp(-25f * Time.deltaTime)
        );
    }
}