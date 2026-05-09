using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class CryptoTracePanel : MonoBehaviour
{
    public static CryptoTracePanel Instance { get; private set; }

    [Header("UI")]
    [SerializeField] private TextMeshProUGUI traceText;
    [SerializeField] private ScrollRect scrollRect;
    [SerializeField] private GameObject panelRoot;

    [Header("设置")]
    [SerializeField] private bool enableTrace = true;
    [SerializeField] private int maxCharacters = 20000;
    [SerializeField] private bool autoScrollToBottom = true;

    private readonly StringBuilder builder = new StringBuilder();

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;

        // 关键：如果它挂在某个会被销毁的父物体下，先脱离父物体
        transform.SetParent(null);

        // 关键：切场景不销毁
        DontDestroyOnLoad(gameObject);

        CryptoTrace.Enabled = enableTrace;

        if (panelRoot == null)
            panelRoot = gameObject;
    }

    private void OnEnable()
    {
        CryptoTrace.OnTrace += HandleTrace;
    }

    private void OnDisable()
    {
        CryptoTrace.OnTrace -= HandleTrace;
    }

    public void Clear()
    {
        builder.Clear();

        if (traceText != null)
            traceText.text = "";
    }

    public void ToggleVisible()
    {
        if (panelRoot != null)
            panelRoot.SetActive(!panelRoot.activeSelf);
    }

    public void SetVisible(bool visible)
    {
        if (panelRoot != null)
            panelRoot.SetActive(visible);
    }

    public void SetTraceEnabled(bool enabled)
    {
        enableTrace = enabled;
        CryptoTrace.Enabled = enabled;
    }

    private void HandleTrace(string msg)
    {
        if (msg == "__CLEAR__")
        {
            Clear();
            return;
        }

        builder.AppendLine(msg);
        builder.AppendLine("----------------------------------------");
        builder.AppendLine();

        if (builder.Length > maxCharacters)
        {
            builder.Remove(0, builder.Length - maxCharacters);
        }

        if (traceText != null)
            traceText.text = builder.ToString();

        if (autoScrollToBottom && scrollRect != null)
        {
            Canvas.ForceUpdateCanvases();
            scrollRect.verticalNormalizedPosition = 0f;
        }
    }

    private void Update()
    {
        // 演示用：按 F8 显示/隐藏加密过程面板
        if (Input.GetKeyDown(KeyCode.F8))
        {
            ToggleVisible();
        }

        // 演示用：按 F9 清空日志
        if (Input.GetKeyDown(KeyCode.F9))
        {
            Clear();
        }
    }
}