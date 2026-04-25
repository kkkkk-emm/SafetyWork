using System.Linq;
using UnityEditor;
using UnityEngine;
[CreateAssetMenu(menuName ="Dungeon / DungeonDatabaseSO", fileName ="DungeonDatabaseSO" )]
public class DungeonDatabaseSO : ScriptableObject
{
    public DungeonDataSO[] dungeons;

    public DungeonDataSO GetDungeonById(string id)
    {
        return dungeons.FirstOrDefault(q => q != null && q.dungeonID == id);
    }

#if UNITY_EDITOR
    [ContextMenu("Auto-fill with all DungeonDataSO")]
    public void CollectItemsData()
    {
        string[] guids = AssetDatabase.FindAssets("t:DungeonDataSO");

        dungeons = guids
             .Select(guid => AssetDatabase.LoadAssetAtPath<DungeonDataSO>(AssetDatabase.GUIDToAssetPath(guid)))
             .Where(q => q != null)
             .ToArray();

        EditorUtility.SetDirty(this);
        AssetDatabase.SaveAssets();
    }
#endif
}
