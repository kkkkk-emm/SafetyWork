using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class UserInfoPanel : MonoBehaviour
{
    public static UserInfoPanel Instance { get; private set; }

    [Header("Root")]
    [SerializeField] private GameObject panelRoot;

    [Header("UI")]
    [SerializeField] private Image avatarImage;
    [SerializeField] private TextMeshProUGUI userIdText;
    [SerializeField] private TextMeshProUGUI usernameText;

    [Header("Avatar")]
    [SerializeField] private Sprite defaultAvatar;
    [SerializeField] private Sprite[] avatarPool;

    [Header("Behavior")]
    [SerializeField] private bool hideBeforeLogin = true;
    [SerializeField] private bool dontDestroyOnLoad = true;

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;

        if (panelRoot == null)
            panelRoot = gameObject;

        if (dontDestroyOnLoad)
            DontDestroyOnLoad(gameObject);

        if (hideBeforeLogin && panelRoot != null)
            panelRoot.SetActive(false);
    }

    private void OnDestroy()
    {
        if (Instance == this)
            Instance = null;
    }

    public static void ShowCurrentUserIfLoggedIn()
    {
        AuthContext ctx = AuthSession.Ctx;

        if (ctx == null || ctx.userId <= 0 || string.IsNullOrWhiteSpace(ctx.username))
        {
            HideIfExists();
            return;
        }

        ShowUserIfExists(ctx.userId, ctx.username);
    }

    public static void ShowUserIfExists(long userId, string username)
    {
        if (Instance == null)
        {
            Debug.LogWarning("[UserInfoPanel] Instance is null. Cannot ShowUser.");
            return;
        }

        Instance.ShowUser(userId, username);
    }

    public static void HideIfExists()
    {
        if (Instance == null)
            return;

        Instance.Hide();
    }

    public void ShowUser(long userId, string username)
    {
        if (panelRoot == null)
            panelRoot = gameObject;

        if (gameObject != null && !gameObject.activeSelf)
            gameObject.SetActive(true);

        if (panelRoot != null)
            panelRoot.SetActive(true);

        if (userIdText != null)
            userIdText.text = $"ID: {userId}";

        if (usernameText != null)
            usernameText.text = string.IsNullOrWhiteSpace(username)
                ? "Î´ÃüÃûÍæ¼Ò"
                : username;

        if (avatarImage != null)
            avatarImage.sprite = PickAvatar(userId);

        Debug.Log($"[UserInfoPanel] ShowUser userId={userId}, username={username}");
    }

    public void Hide()
    {
        if (panelRoot != null)
            panelRoot.SetActive(false);
    }

    private Sprite PickAvatar(long userId)
    {
        if (avatarPool != null && avatarPool.Length > 0)
        {
            long safeId = userId < 0 ? -userId : userId;
            int index = (int)(safeId % avatarPool.Length);

            if (avatarPool[index] != null)
                return avatarPool[index];
        }

        return defaultAvatar;
    }
}