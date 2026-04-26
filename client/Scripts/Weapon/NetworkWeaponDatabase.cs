using System;
using UnityEngine;

public class NetworkWeaponDatabase : MonoBehaviour
{
    public static NetworkWeaponDatabase Instance { get; private set; }

    [Serializable]
    public class Entry
    {
        public string weaponId;
        public WeaponDataSO weaponData;
    }

    [SerializeField] private Entry[] entries;

    private void Awake()
    {
        Instance = this;
    }

    public WeaponDataSO GetWeaponData(string weaponId)
    {
        if (string.IsNullOrWhiteSpace(weaponId))
            return null;

        if (entries == null)
            return null;

        foreach (Entry entry in entries)
        {
            if (entry == null)
                continue;

            if (entry.weaponId == weaponId)
                return entry.weaponData;
        }

        Debug.LogWarning($"[NetworkWeaponDatabase] ’“≤ªµΩ weaponId={weaponId}");
        return null;
    }
}