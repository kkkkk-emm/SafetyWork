using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class GameOverPanelController : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private GameObject panelRoot;
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text winnerText;
    [SerializeField] private Button returnLobbyButton;

    [Header("Scene")]
    [SerializeField] private string lobbySceneName = "MainMenu";

    private bool returning;

    private void Awake()
    {
        if (panelRoot == null)
            panelRoot = gameObject;

        if (returnLobbyButton != null)
            returnLobbyButton.onClick.AddListener(OnClickReturnLobby);

        Hide();
    }

    public void Show(string winnerName)
    {
        returning = false;

        if (panelRoot != null)
            panelRoot.SetActive(true);

        if (titleText != null)
            titleText.text = "”Œœ∑Ω· ¯";

        if (winnerText != null)
            winnerText.text = $"{winnerName} ªÒ §";

        if (returnLobbyButton != null)
            returnLobbyButton.interactable = true;

        Time.timeScale = 0f;
    }

    public void Hide()
    {
        if (panelRoot != null)
            panelRoot.SetActive(false);
    }

    private async void OnClickReturnLobby()
    {
        if (returning)
            return;

        returning = true;

        if (returnLobbyButton != null)
            returnLobbyButton.interactable = false;

        Time.timeScale = 1f;

        try
        {
            Debug.Log("[GameOverPanel] Return lobby after match finished.");

            if (RelayChatClient.Instance != null)
                await RelayChatClient.Instance.DisconnectAfterMatchFinished();

            SceneManager.LoadScene(lobbySceneName);
        }
        catch (System.Exception ex)
        {
            Debug.LogError("[GameOverPanel] Return lobby failed: " + ex);

            returning = false;

            if (returnLobbyButton != null)
                returnLobbyButton.interactable = true;
        }
    }
}