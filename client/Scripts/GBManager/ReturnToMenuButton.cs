using UnityEngine;
using UnityEngine.SceneManagement;

public class ReturnToMenuButton : MonoBehaviour
{
    [Header("Scene")]
    [SerializeField] private string mainMenuSceneName = "MainMenu";

    [Header("Network")]
    [SerializeField] private bool disconnectGsWhenReturn = true;

    public async void OnClickReturnToMenu()
    {
        if (RelayChatClient.Instance != null)
            await RelayChatClient.Instance.DisconnectButKeepSession();

        UnityEngine.SceneManagement.SceneManager.LoadScene("MainMenu");
    }
}