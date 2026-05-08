using DG.Tweening;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class LoginPanelController : MonoBehaviour
{
    [Header("核心组件")]
    [SerializeField] private AuthClient authClient;
    [SerializeField] private RelayChatClient relayClient;

    [Header("外层面板")]
    [SerializeField] private GameObject loginPanel;
    [SerializeField] private GameObject lobbyPanel;

    [Header("登录/注册表单")]
    [SerializeField] private GameObject loginForm;
    [SerializeField] private GameObject registerForm;

    [Header("切换按钮")]
    [SerializeField] private Button loginTabButton;
    [SerializeField] private Button registerTabButton;
    [SerializeField] private TMP_Text loginTabText;
    [SerializeField] private TMP_Text registerTabText;

    [Header("登录表单输入框")]
    [SerializeField] private TMP_InputField usernameInput;
    [SerializeField] private TMP_InputField passwordInput;

    [Header("注册表单输入框")]
    [SerializeField] private TMP_InputField registerUsernameInput;
    [SerializeField] private TMP_InputField registerPasswordInput;
    [SerializeField] private TMP_InputField registerConfirmPasswordInput;

    [Header("功能按钮")]
    [SerializeField] private Button loginButton;
    [SerializeField] private Button registerButton;
    [SerializeField] private Button closeButton;

    [Header("状态文本")]
    [SerializeField] private TMP_Text statusText;

    [Header("大厅调试信息，可选")]
    [SerializeField] private TMP_Text accountText;
    [SerializeField] private TMP_Text sessionText;

    [Header("状态颜色")]
    [SerializeField] private Color infoColor = Color.white;
    [SerializeField] private Color busyColor = new Color(1f, 0.82f, 0.25f);
    [SerializeField] private Color successColor = new Color(0.35f, 1f, 0.45f);
    [SerializeField] private Color errorColor = new Color(1f, 0.35f, 0.35f);

    [Header("Tab 颜色")]
    [SerializeField] private Color activeTabColor = Color.red;
    [SerializeField] private Color inactiveTabColor = new Color(0.45f, 0.45f, 0.45f);
    [SerializeField] private float activeTabScale = 1.08f;
    [SerializeField] private float inactiveTabScale = 1f;

    [Header("外层面板动画")]
    [SerializeField] private float panelFadeDuration = 0.22f;
    [SerializeField] private float panelScaleDuration = 0.28f;
    [SerializeField] private float hiddenScale = 0.92f;
    [SerializeField] private Ease showEase = Ease.OutBack;
    [SerializeField] private Ease hideEase = Ease.InQuad;

    [Header("表单切换动画")]
    [SerializeField] private float formFadeDuration = 0.18f;
    [SerializeField] private float formScaleDuration = 0.22f;
    [SerializeField] private float formHiddenScale = 0.96f;
    [SerializeField] private Ease formShowEase = Ease.OutBack;
    [SerializeField] private Ease formHideEase = Ease.InQuad;

    private bool busy;
    private bool showingRegister;

    private CanvasGroup loginCanvasGroup;
    private CanvasGroup lobbyCanvasGroup;
    private CanvasGroup loginFormGroup;
    private CanvasGroup registerFormGroup;

    private Sequence panelSwitchSeq;
    private Sequence formSwitchSeq;

    private Vector3 loginPanelOriginalScale = Vector3.one;
    private Vector3 lobbyPanelOriginalScale = Vector3.one;
    private Vector3 loginFormOriginalScale = Vector3.one;
    private Vector3 registerFormOriginalScale = Vector3.one;

    private void Awake()
    {
        if (authClient == null)
            authClient = FindFirstObjectByType<AuthClient>();

        if (relayClient == null)
            relayClient = RelayChatClient.Instance;

        if (relayClient == null)
            relayClient = FindFirstObjectByType<RelayChatClient>();

        PreparePanelCanvasGroups();
        PrepareFormCanvasGroups();

        if (loginPanel != null)
        {
            loginPanel.SetActive(false);
            SetPanelInstant(loginPanel, loginCanvasGroup, false);
        }

        if (lobbyPanel != null)
        {
            lobbyPanel.SetActive(false);
            SetPanelInstant(lobbyPanel, lobbyCanvasGroup, false);
        }

        ShowLoginFormInstant();

        HideStatus();
        RefreshButtons();
    }

    private void Start()
    {
        SetupPasswordInput(passwordInput);
        SetupPasswordInput(registerPasswordInput);
        SetupPasswordInput(registerConfirmPasswordInput);
    }

    private void OnDestroy()
    {
        panelSwitchSeq?.Kill();
        formSwitchSeq?.Kill();
    }

    // ============================================================
    // 外部入口
    // ============================================================

    public void OpenLoginPanel()
    {
        busy = false;
        HideStatus();

        ShowLoginFormInstant();
        RefreshButtons();
        ShowLogin();
    }

    public void CloseLoginPanel()
    {
        panelSwitchSeq?.Kill();

        GameObject currentPanel = null;
        CanvasGroup currentGroup = null;

        if (lobbyPanel != null && lobbyPanel.activeSelf)
        {
            currentPanel = lobbyPanel;
            currentGroup = lobbyCanvasGroup;
        }
        else if (loginPanel != null && loginPanel.activeSelf)
        {
            currentPanel = loginPanel;
            currentGroup = loginCanvasGroup;
        }

        if (currentPanel == null || currentGroup == null)
        {
            busy = false;
            HideStatus();
            RefreshButtons();
            return;
        }

        Vector3 originalScale = GetPanelOriginalScale(currentPanel);
        Vector3 targetScale = originalScale * hiddenScale;

        currentGroup.interactable = false;
        currentGroup.blocksRaycasts = false;

        panelSwitchSeq = DOTween.Sequence();

        panelSwitchSeq.Join(
            currentGroup
                .DOFade(0f, panelFadeDuration)
                .SetEase(hideEase)
        );

        panelSwitchSeq.Join(
            currentPanel.transform
                .DOScale(targetScale, panelScaleDuration)
                .SetEase(hideEase)
        );

        panelSwitchSeq.OnComplete(() =>
        {
            currentPanel.SetActive(false);
            currentPanel.transform.localScale = originalScale;

            currentGroup.alpha = 1f;
            currentGroup.interactable = true;
            currentGroup.blocksRaycasts = true;

            busy = false;
            HideStatus();
            RefreshButtons();
        });
    }

    // ============================================================
    // 登录 / 注册 Tab
    // ============================================================

    public void ShowLoginForm()
    {
        if (!showingRegister)
        {
            showingRegister = false;
            ApplyTabVisual();
            RefreshButtons();
            return;
        }

        showingRegister = false;

        SwitchForm(
            fromForm: registerForm,
            fromGroup: registerFormGroup,
            toForm: loginForm,
            toGroup: loginFormGroup,
            fromOriginalScale: registerFormOriginalScale,
            toOriginalScale: loginFormOriginalScale
        );

        ApplyTabVisual();
        HideStatus();
        RefreshButtons();
    }

    public void ShowRegisterForm()
    {
        if (showingRegister)
        {
            showingRegister = true;
            ApplyTabVisual();
            RefreshButtons();
            return;
        }

        showingRegister = true;

        SwitchForm(
            fromForm: loginForm,
            fromGroup: loginFormGroup,
            toForm: registerForm,
            toGroup: registerFormGroup,
            fromOriginalScale: loginFormOriginalScale,
            toOriginalScale: registerFormOriginalScale
        );

        ApplyTabVisual();
        HideStatus();
        RefreshButtons();
    }

    private void ShowLoginFormInstant()
    {
        showingRegister = false;

        SetFormInstant(loginForm, loginFormGroup, true);
        SetFormInstant(registerForm, registerFormGroup, false);

        ApplyTabVisual();
        RefreshButtons();
    }

    private void ApplyTabVisual()
    {
        bool registerActive = showingRegister;

        if (loginTabText != null)
        {
            loginTabText.color = registerActive ? inactiveTabColor : activeTabColor;
            loginTabText.transform
                .DOScale(registerActive ? inactiveTabScale : activeTabScale, 0.12f)
                .SetEase(Ease.OutQuad);
        }

        if (registerTabText != null)
        {
            registerTabText.color = registerActive ? activeTabColor : inactiveTabColor;
            registerTabText.transform
                .DOScale(registerActive ? activeTabScale : inactiveTabScale, 0.12f)
                .SetEase(Ease.OutQuad);
        }

        // Tab 按钮永远保持可点，避免切换状态乱掉。
        if (loginTabButton != null)
            loginTabButton.interactable = !busy;

        if (registerTabButton != null)
            registerTabButton.interactable = !busy;
    }

    // ============================================================
    // 登录 / 注册按钮
    // ============================================================

    public async void OnClickRegister()
    {
        if (busy)
            return;

        string username = GetRegisterUsername();
        string password = GetRegisterPassword();
        string confirmPassword = GetRegisterConfirmPassword();

        if (!ValidateRegisterInput(username, password, confirmPassword))
            return;

        if (authClient == null)
        {
            SetError("注册失败：找不到 AuthClient。");
            return;
        }

        SetBusy(true, "注册中...");

        AuthClient.RegisterResult result = await authClient.RegisterAsync(
            username,
            password
        );

        if (!result.ok)
        {
            SetBusy(false);
            SetError("注册失败：" + NormalizeError(result.error));
            return;
        }

        SetBusy(false);
        SetSuccess($"注册成功，userId={result.userId}。正在切回登录。");

        if (usernameInput != null)
            usernameInput.text = username;

        if (passwordInput != null)
            passwordInput.text = password;

        ShowLoginForm();
    }

    public async void OnClickLogin()
    {
        if (busy)
            return;

        string username = GetLoginUsername();
        string password = GetLoginPassword();

        if (!ValidateLoginInput(username, password))
            return;

        if (authClient == null)
        {
            SetError("登录失败：找不到 AuthClient。");
            return;
        }

        if (relayClient == null)
        {
            SetError("登录失败：找不到 RelayChatClient。");
            return;
        }

        SetBusy(true, "正在清理旧连接...");

        await relayClient.ResetConnectionForNewLogin();

        AuthSession.EnsureExists().ClearTicketsAndSession();
        AuthSession.EnsureExists().ClearRoom();

        if (NetworkSession.Instance != null)
            NetworkSession.Instance.Clear();

        SetBusy(true, "登录中：正在请求 AS/TGS...");

        AuthClient.AuthResult authResult = await authClient.FullLoginToTicketAsync(
            username,
            password
        );

        if (!authResult.ok)
        {
            SetBusy(false);
            SetError("登录失败：" + NormalizeError(authResult.error));
            return;
        }

        SetBusy(true, "AS/TGS 成功，正在连接游戏服务器...");

        bool gsAuthOk = await relayClient.ConnectAndAuthenticateGs();

        if (!gsAuthOk || !AuthSession.Ctx.HasGsSession)
        {
            SetBusy(false);
            SetError("GS_AUTH 失败：没有拿到 sessionId。");
            return;
        }

        SetBusy(false);
        SetSuccess("登录成功。");

        //ShowLobby();
    }

    // ============================================================
    // 外层面板切换
    // ============================================================

    public void ShowLogin()
    {
        SwitchPanel(
            fromPanel: lobbyPanel,
            fromGroup: lobbyCanvasGroup,
            toPanel: loginPanel,
            toGroup: loginCanvasGroup,
            onComplete: null
        );
    }

    public void ShowLobby()
    {
        RefreshLobbyDebugInfo();

        SwitchPanel(
            fromPanel: loginPanel,
            fromGroup: loginCanvasGroup,
            toPanel: lobbyPanel,
            toGroup: lobbyCanvasGroup,
            onComplete: RefreshLobbyDebugInfo
        );
    }

    private void SwitchPanel(
        GameObject fromPanel,
        CanvasGroup fromGroup,
        GameObject toPanel,
        CanvasGroup toGroup,
        System.Action onComplete
    )
    {
        panelSwitchSeq?.Kill();

        if (toPanel == null || toGroup == null)
        {
            Debug.LogWarning("[LoginPanel] SwitchPanel failed: target panel missing.");
            return;
        }

        Vector3 toOriginalScale = GetPanelOriginalScale(toPanel);
        Vector3 toHiddenScale = toOriginalScale * hiddenScale;

        toPanel.SetActive(true);
        toPanel.transform.localScale = toHiddenScale;

        toGroup.alpha = 0f;
        toGroup.interactable = false;
        toGroup.blocksRaycasts = false;

        if (fromGroup != null)
        {
            fromGroup.interactable = false;
            fromGroup.blocksRaycasts = false;
        }

        panelSwitchSeq = DOTween.Sequence();

        bool hasFrom = fromPanel != null && fromGroup != null && fromPanel.activeSelf;

        if (hasFrom)
        {
            Vector3 fromOriginalScale = GetPanelOriginalScale(fromPanel);
            Vector3 fromHiddenScale = fromOriginalScale * hiddenScale;

            panelSwitchSeq.Join(
                fromGroup
                    .DOFade(0f, panelFadeDuration)
                    .SetEase(hideEase)
            );

            panelSwitchSeq.Join(
                fromPanel.transform
                    .DOScale(fromHiddenScale, panelScaleDuration)
                    .SetEase(hideEase)
            );

            panelSwitchSeq.AppendCallback(() =>
            {
                fromPanel.SetActive(false);
                fromPanel.transform.localScale = fromOriginalScale;
            });
        }

        panelSwitchSeq.AppendCallback(() =>
        {
            toPanel.SetActive(true);
            toPanel.transform.localScale = toHiddenScale;
        });

        panelSwitchSeq.Join(
            toGroup
                .DOFade(1f, panelFadeDuration)
                .SetEase(Ease.OutQuad)
        );

        panelSwitchSeq.Join(
            toPanel.transform
                .DOScale(toOriginalScale, panelScaleDuration)
                .SetEase(showEase)
        );

        panelSwitchSeq.OnComplete(() =>
        {
            toGroup.alpha = 1f;
            toGroup.interactable = true;
            toGroup.blocksRaycasts = true;
            toPanel.transform.localScale = toOriginalScale;

            onComplete?.Invoke();
            RefreshButtons();
        });
    }

    private void SwitchForm(
        GameObject fromForm,
        CanvasGroup fromGroup,
        GameObject toForm,
        CanvasGroup toGroup,
        Vector3 fromOriginalScale,
        Vector3 toOriginalScale
    )
    {
        formSwitchSeq?.Kill();

        if (toForm == null || toGroup == null)
        {
            RefreshButtons();
            return;
        }

        Vector3 toHiddenScale = toOriginalScale * formHiddenScale;

        toForm.SetActive(true);
        toForm.transform.localScale = toHiddenScale;

        toGroup.alpha = 0f;
        toGroup.interactable = false;
        toGroup.blocksRaycasts = false;

        if (fromGroup != null)
        {
            fromGroup.interactable = false;
            fromGroup.blocksRaycasts = false;
        }

        formSwitchSeq = DOTween.Sequence();

        bool hasFrom = fromForm != null && fromGroup != null && fromForm.activeSelf;

        if (hasFrom)
        {
            Vector3 fromHiddenScale = fromOriginalScale * formHiddenScale;

            formSwitchSeq.Join(
                fromGroup
                    .DOFade(0f, formFadeDuration)
                    .SetEase(formHideEase)
            );

            formSwitchSeq.Join(
                fromForm.transform
                    .DOScale(fromHiddenScale, formScaleDuration)
                    .SetEase(formHideEase)
            );

            formSwitchSeq.AppendCallback(() =>
            {
                fromForm.SetActive(false);
                fromForm.transform.localScale = fromOriginalScale;
            });
        }

        formSwitchSeq.AppendCallback(() =>
        {
            toForm.SetActive(true);
            toForm.transform.localScale = toHiddenScale;
        });

        formSwitchSeq.Join(
            toGroup
                .DOFade(1f, formFadeDuration)
                .SetEase(Ease.OutQuad)
        );

        formSwitchSeq.Join(
            toForm.transform
                .DOScale(toOriginalScale, formScaleDuration)
                .SetEase(formShowEase)
        );

        formSwitchSeq.OnComplete(() =>
        {
            toGroup.alpha = 1f;
            toGroup.interactable = true;
            toGroup.blocksRaycasts = true;
            toForm.transform.localScale = toOriginalScale;

            RefreshButtons();
        });
    }

    // ============================================================
    // CanvasGroup / Scale 初始化
    // ============================================================

    private void PreparePanelCanvasGroups()
    {
        if (loginPanel != null)
        {
            loginCanvasGroup = GetOrAddCanvasGroup(loginPanel);
            loginPanelOriginalScale = loginPanel.transform.localScale;
        }

        if (lobbyPanel != null)
        {
            lobbyCanvasGroup = GetOrAddCanvasGroup(lobbyPanel);
            lobbyPanelOriginalScale = lobbyPanel.transform.localScale;
        }
    }

    private void PrepareFormCanvasGroups()
    {
        if (loginForm != null)
        {
            loginFormGroup = GetOrAddCanvasGroup(loginForm);
            loginFormOriginalScale = loginForm.transform.localScale;
        }

        if (registerForm != null)
        {
            registerFormGroup = GetOrAddCanvasGroup(registerForm);
            registerFormOriginalScale = registerForm.transform.localScale;
        }
    }

    private CanvasGroup GetOrAddCanvasGroup(GameObject target)
    {
        CanvasGroup group = target.GetComponent<CanvasGroup>();

        if (group == null)
            group = target.AddComponent<CanvasGroup>();

        return group;
    }

    private void SetPanelInstant(GameObject panel, CanvasGroup group, bool visible)
    {
        if (panel == null || group == null)
            return;

        Vector3 originalScale = GetPanelOriginalScale(panel);

        panel.SetActive(visible);

        group.alpha = visible ? 1f : 0f;
        group.interactable = visible;
        group.blocksRaycasts = visible;

        panel.transform.localScale = visible
            ? originalScale
            : originalScale * hiddenScale;
    }

    private void SetFormInstant(GameObject form, CanvasGroup group, bool visible)
    {
        if (form == null || group == null)
            return;

        Vector3 originalScale = GetFormOriginalScale(form);

        form.SetActive(visible);

        group.alpha = visible ? 1f : 0f;
        group.interactable = visible;
        group.blocksRaycasts = visible;

        form.transform.localScale = visible
            ? originalScale
            : originalScale * formHiddenScale;
    }

    private Vector3 GetPanelOriginalScale(GameObject panel)
    {
        if (panel == loginPanel)
            return loginPanelOriginalScale;

        if (panel == lobbyPanel)
            return lobbyPanelOriginalScale;

        return Vector3.one;
    }

    private Vector3 GetFormOriginalScale(GameObject form)
    {
        if (form == loginForm)
            return loginFormOriginalScale;

        if (form == registerForm)
            return registerFormOriginalScale;

        return Vector3.one;
    }

    // ============================================================
    // 输入读取 / 校验
    // ============================================================

    private string GetLoginUsername()
    {
        return usernameInput != null ? usernameInput.text.Trim() : "";
    }

    private string GetLoginPassword()
    {
        return passwordInput != null ? passwordInput.text : "";
    }

    private string GetRegisterUsername()
    {
        return registerUsernameInput != null ? registerUsernameInput.text.Trim() : "";
    }

    private string GetRegisterPassword()
    {
        return registerPasswordInput != null ? registerPasswordInput.text : "";
    }

    private string GetRegisterConfirmPassword()
    {
        return registerConfirmPasswordInput != null ? registerConfirmPasswordInput.text : "";
    }

    private bool ValidateLoginInput(string username, string password)
    {
        if (string.IsNullOrWhiteSpace(username))
        {
            SetError("账号不能为空。");
            return false;
        }

        if (string.IsNullOrWhiteSpace(password))
        {
            SetError("密码不能为空。");
            return false;
        }

        if (username.Length < 3)
        {
            SetError("账号至少需要 3 个字符。");
            return false;
        }

        if (password.Length < 6)
        {
            SetError("密码至少需要 6 个字符。");
            return false;
        }

        return true;
    }

    private bool ValidateRegisterInput(string username, string password, string confirmPassword)
    {
        if (string.IsNullOrWhiteSpace(username))
        {
            SetError("账号不能为空。");
            return false;
        }

        if (string.IsNullOrWhiteSpace(password))
        {
            SetError("密码不能为空。");
            return false;
        }

        if (username.Length < 3)
        {
            SetError("账号至少需要 3 个字符。");
            return false;
        }

        if (password.Length < 6)
        {
            SetError("密码至少需要 6 个字符。");
            return false;
        }

        if (password != confirmPassword)
        {
            SetError("两次输入的密码不一致。");
            return false;
        }

        return true;
    }

    private void SetupPasswordInput(TMP_InputField input)
    {
        if (input == null)
            return;

        input.contentType = TMP_InputField.ContentType.Password;
        input.ForceLabelUpdate();
    }

    // ============================================================
    // Lobby debug info
    // ============================================================

    private void RefreshLobbyDebugInfo()
    {
        AuthContext ctx = AuthSession.Ctx;

        if (accountText != null)
        {
            accountText.text =
                $"账号：{ctx.username}\n" +
                $"UserId：{ctx.userId}\n" +
                $"ClientId：{ctx.clientId}";
        }

        if (sessionText != null)
        {
            sessionText.text =
                $"SessionId：{ctx.sessionId}\n" +
                $"TGT：{(string.IsNullOrWhiteSpace(ctx.tgt) ? "empty" : "set")}\n" +
                $"ServiceTicket：{(string.IsNullOrWhiteSpace(ctx.serviceTicket) ? "empty" : "set")}";
        }
    }

    // ============================================================
    // 状态 / Busy / Buttons
    // ============================================================

    private void SetBusy(bool value, string message = "")
    {
        busy = value;
        RefreshButtons();

        if (value)
        {
            if (string.IsNullOrWhiteSpace(message))
                message = "处理中...";

            SetStatus(message, busyColor);
        }
    }

    private void RefreshButtons()
    {
        bool interactable = !busy;

        if (loginButton != null)
        {
            loginButton.gameObject.SetActive(!showingRegister);
            loginButton.interactable = interactable && !showingRegister;
        }

        if (registerButton != null)
        {
            registerButton.gameObject.SetActive(showingRegister);
            registerButton.interactable = interactable && showingRegister;
        }

        if (loginTabButton != null)
            loginTabButton.interactable = interactable;

        if (registerTabButton != null)
            registerTabButton.interactable = interactable;

        if (closeButton != null)
            closeButton.interactable = interactable;

        ApplyTabVisualNoTween();
    }

    private void ApplyTabVisualNoTween()
    {
        bool registerActive = showingRegister;

        if (loginTabText != null)
        {
            loginTabText.color = registerActive ? inactiveTabColor : activeTabColor;
            loginTabText.transform.localScale = Vector3.one * (registerActive ? inactiveTabScale : activeTabScale);
        }

        if (registerTabText != null)
        {
            registerTabText.color = registerActive ? activeTabColor : inactiveTabColor;
            registerTabText.transform.localScale = Vector3.one * (registerActive ? activeTabScale : inactiveTabScale);
        }
    }

    private void SetSuccess(string message)
    {
        SetStatus(message, successColor);
    }

    private void SetError(string message)
    {
        SetStatus(message, errorColor);
    }

    private void SetStatus(string message, Color color)
    {
        if (statusText != null)
        {
            statusText.gameObject.SetActive(true);
            statusText.text = message;
            statusText.color = color;
        }

        Debug.Log("[LoginPanel] " + message);
    }

    private void HideStatus()
    {
        if (statusText != null)
        {
            statusText.text = "";
            statusText.gameObject.SetActive(false);
        }
    }

    private string NormalizeError(string error)
    {
        if (string.IsNullOrWhiteSpace(error))
            return "未知错误";

        switch (error)
        {
            case "USERNAME_EXISTS":
                return "账号已存在";

            case "BAD_CREDENTIALS":
                return "账号或密码错误";

            case "ACCOUNT_DISABLED":
                return "账号已被禁用";

            case "USERNAME_OR_PASSWORD_EMPTY":
                return "账号或密码不能为空";

            case "WEAK_PASSWORD":
                return "密码强度不够";

            case "AS_NO_RESPONSE":
                return "AS 服务器无响应";

            case "TGS_NO_RESPONSE":
                return "TGS 服务器无响应";

            case "TGT_OR_KCTGS_MISSING":
                return "登录票据缺失";

            case "GS_AUTH_FAILED":
                return "游戏服务器认证失败";

            case "GS_AUTH_PENDING_RELAY_REWRITE":
                return "RelayChatClient 尚未完成 GS_AUTH 接入";

            default:
                return error;
        }
    }
}