using UnityEngine;
using UnityEngine.SceneManagement;

public class DungeonManager : MonoBehaviour
{
    public static DungeonManager instance;

    private void Awake()
    {
        if (instance == null) instance = this;
        else Destroy(gameObject);
        DontDestroyOnLoad(gameObject); // 需要跨场景管理副本
    }

    public DungeonDataSO currentDungeon;

    public void EnterDungeon(DungeonDataSO dungeon)
    {
        if (dungeon == null)
        {
            Debug.LogWarning("DungeonManager: 未选择副本");
            return;
        }

        currentDungeon = dungeon;

        Debug.Log($"进入副本: {dungeon.dungeonName}，场景: {dungeon.sceneName}");

       
        //GameManager.instance.ChangeScene(currentDungeon.dungeonName, RespawnType.NonSpecific);
    }

    public void ExitDungeon(string mainSceneName)
    {
        currentDungeon = null;
        //GameManager.instance.ChangeScene("平原" , RespawnType.Exit);
    }

    /// <summary>
    /// 获取当前副本信息
    /// </summary>
    public DungeonDataSO GetCurrentDungeon()
    {
        return currentDungeon;
    }

}
