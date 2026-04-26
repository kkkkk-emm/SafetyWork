using UnityEditor;
using UnityEngine;

[CreateAssetMenu(menuName ="Dungeon/Dungeon data",fileName ="new Dungeon")]
public class DungeonDataSO : ScriptableObject
{
    public string dungeonID;
    public string dungeonName;
    [TextArea] public string dungeonDescription;
    public string sceneName;
    public int recommendedLevel = 1;


    public Sprite icon;
    public GameObject previewPrefab;


    

}
