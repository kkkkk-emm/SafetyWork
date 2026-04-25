using UnityEngine;
using UnityEngine.SceneManagement;
using DG.Tweening;

public class MainMenuManager : MonoBehaviour
{
    [Header("UI 面板引用")]
    public RectTransform mainPanel;
    public RectTransform lobbyPanel;

    [Header("加入房间弹窗")]
    public RectTransform joinRoomPopup;

    [Header("动画参数")]
    public float animDuration = 0.5f;

    private Vector2 mainPanelVisiblePos;
    private Vector2 mainPanelHiddenPos = new Vector2(-1500, 200);

    private Vector2 lobbyPanelVisiblePos = Vector2.zero;
    private Vector2 lobbyPanelHiddenPos = new Vector2(0, 1200);

    private void Start()
    {
        if (mainPanel != null)
        {
            mainPanel.gameObject.SetActive(true);
            mainPanelVisiblePos = mainPanel.anchoredPosition;
        }

        if (lobbyPanel != null)
        {
            lobbyPanel.gameObject.SetActive(true);
            lobbyPanel.anchoredPosition = lobbyPanelHiddenPos;
        }

        if (joinRoomPopup != null)
        {
            joinRoomPopup.gameObject.SetActive(false);
            joinRoomPopup.localScale = Vector3.zero;
        }
    }

    public void OnClickTrainingMode()
    {
        Debug.Log("进入训练模式...");
        SceneManager.LoadScene("MainGame");
    }

    /// <summary>
    /// 进入 Lobby 面板。
    /// 注意：这个函数现在只负责 UI 动画，不负责创建房间。
    /// 创建房间由 LobbyManager.OnClickCreateRoomAndEnter() 负责。
    /// </summary>
    public void OnClickMultiplayer()
    {
        Debug.Log("[MainMenuManager] 打开双人联机房间 UI");

        if (mainPanel != null)
        {
            mainPanel.DOAnchorPos(mainPanelHiddenPos, animDuration)
                .SetEase(Ease.InBack);
        }

        if (lobbyPanel != null)
        {
            lobbyPanel.DOAnchorPos(lobbyPanelVisiblePos, animDuration)
                .SetEase(Ease.OutBack)
                .SetDelay(0.15f);
        }
    }

    public void OnClickBackToMain()
    {
        Debug.Log("[MainMenuManager] 返回主菜单");

        if (lobbyPanel != null)
        {
            lobbyPanel.DOAnchorPos(lobbyPanelHiddenPos, animDuration)
                .SetEase(Ease.InBack);
        }

        if (mainPanel != null)
        {
            mainPanel.DOAnchorPos(mainPanelVisiblePos, animDuration)
                .SetEase(Ease.OutBack)
                .SetDelay(0.15f);
        }
    }

    /// <summary>
    /// 主菜单“加入房间”按钮调用这个。
    /// </summary>
    public void OnClickShowJoinRoomPopup()
    {
        ShowJoinRoomPopup();
    }

    public void ShowJoinRoomPopup()
    {
        if (joinRoomPopup == null)
        {
            Debug.LogWarning("[MainMenuManager] joinRoomPopup 没有拖引用");
            return;
        }

        joinRoomPopup.gameObject.SetActive(true);
        joinRoomPopup.DOKill();

        joinRoomPopup.localScale = Vector3.zero;
        joinRoomPopup
            .DOScale(Vector3.one, 0.25f)
            .SetEase(Ease.OutBack);

        Debug.Log("[MainMenuManager] 显示加入房间弹窗");
    }

    public void HideJoinRoomPopup()
    {
        if (joinRoomPopup == null)
            return;

        joinRoomPopup.DOKill();

        joinRoomPopup
            .DOScale(Vector3.zero, 0.18f)
            .SetEase(Ease.InBack)
            .OnComplete(() =>
            {
                if (joinRoomPopup != null)
                    joinRoomPopup.gameObject.SetActive(false);
            });

        Debug.Log("[MainMenuManager] 隐藏加入房间弹窗");
    }

    public void OnClickQuitGame()
    {
        Debug.Log("退出游戏！");
        Application.Quit();
    }
}