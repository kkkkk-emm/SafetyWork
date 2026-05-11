using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class ExitPanelController : MonoBehaviour
{
    [Header("Panel")]
    [SerializeField] private GameObject panelRoot;

    [Header("Buttons")]
    [SerializeField] private Button continueButton;
    [SerializeField] private Button returnLobbyButton;

    [Header("Scene")]
    [SerializeField] private string lobbySceneName = "MainMenu";

    private bool isReturning;

    private void Awake()
    {
        if (continueButton != null)
            continueButton.onClick.AddListener(HidePanel);

        if (returnLobbyButton != null)
            returnLobbyButton.onClick.AddListener(OnClickReturnLobby);

        HidePanel();
    }

    private void Update()
    {
        if (Input.GetKeyDown(KeyCode.Escape))
        {
            if (IsVisible())
                HidePanel();
            else
                ShowPanel();
        }
    }

    public void ShowPanel()
    {
        if (panelRoot != null)
            panelRoot.SetActive(true);
    }

    public void HidePanel()
    {
        if (panelRoot != null)
            panelRoot.SetActive(false);
    }

    public bool IsVisible()
    {
        return panelRoot != null && panelRoot.activeSelf;
    }

    private async void OnClickReturnLobby()
    {
        if (isReturning)
            return;

        isReturning = true;

        if (returnLobbyButton != null)
            returnLobbyButton.interactable = false;

        try
        {
            Debug.Log("[ExitPanel] Return lobby for reconnect.");

            if (RelayChatClient.Instance != null)
                await RelayChatClient.Instance.DisconnectForReconnectToSameMatch();

            SceneManager.LoadScene(lobbySceneName);
        }
        catch (System.Exception ex)
        {
            Debug.LogError("[ExitPanel] Return lobby failed: " + ex);

            isReturning = false;

            if (returnLobbyButton != null)
                returnLobbyButton.interactable = true;
        }
    }
}