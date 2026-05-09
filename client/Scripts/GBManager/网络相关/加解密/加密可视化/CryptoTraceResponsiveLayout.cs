using UnityEngine;

[ExecuteAlways]
public class CryptoTraceResponsiveLayout : MonoBehaviour
{
    [Header("目标面板")]
    [SerializeField] private RectTransform panelRect;

    [Header("宽屏布局")]
    [SerializeField] private float wideWidthRatio = 0.36f;
    [SerializeField] private float wideHeightRatio = 0.62f;
    [SerializeField] private Vector2 wideMargin = new Vector2(24f, 24f);

    [Header("窄屏布局")]
    [SerializeField] private float narrowWidthRatio = 0.92f;
    [SerializeField] private float narrowHeightRatio = 0.42f;
    [SerializeField] private Vector2 narrowMargin = new Vector2(24f, 24f);

    [Header("尺寸限制")]
    [SerializeField] private Vector2 minSize = new Vector2(420f, 260f);
    [SerializeField] private Vector2 maxSize = new Vector2(760f, 640f);

    [Header("切换阈值")]
    [SerializeField] private float narrowAspectThreshold = 1.45f;

    private Vector2 lastScreenSize;

    private void Awake()
    {
        if (panelRect == null)
            panelRect = transform as RectTransform;

        ApplyLayout();
    }

    private void Update()
    {
        Vector2 current = new Vector2(Screen.width, Screen.height);

        if (current != lastScreenSize)
        {
            lastScreenSize = current;
            ApplyLayout();
        }
    }

    public void ApplyLayout()
    {
        if (panelRect == null)
            return;

        float screenW = Screen.width;
        float screenH = Screen.height;

        if (screenW <= 0 || screenH <= 0)
            return;

        float aspect = screenW / screenH;

        if (aspect >= narrowAspectThreshold)
        {
            ApplyWideLayout(screenW, screenH);
        }
        else
        {
            ApplyNarrowLayout(screenW, screenH);
        }
    }

    private void ApplyWideLayout(float screenW, float screenH)
    {
        float width = Mathf.Clamp(screenW * wideWidthRatio, minSize.x, maxSize.x);
        float height = Mathf.Clamp(screenH * wideHeightRatio, minSize.y, maxSize.y);

        // 右下角布局
        panelRect.anchorMin = new Vector2(1f, 0f);
        panelRect.anchorMax = new Vector2(1f, 0f);
        panelRect.pivot = new Vector2(1f, 0f);

        panelRect.sizeDelta = new Vector2(width, height);
        panelRect.anchoredPosition = new Vector2(-wideMargin.x, wideMargin.y);
    }

    private void ApplyNarrowLayout(float screenW, float screenH)
    {
        float width = Mathf.Clamp(screenW * narrowWidthRatio, minSize.x, screenW - narrowMargin.x * 2f);
        float height = Mathf.Clamp(screenH * narrowHeightRatio, minSize.y, maxSize.y);

        // 底部居中布局
        panelRect.anchorMin = new Vector2(0.5f, 0f);
        panelRect.anchorMax = new Vector2(0.5f, 0f);
        panelRect.pivot = new Vector2(0.5f, 0f);

        panelRect.sizeDelta = new Vector2(width, height);
        panelRect.anchoredPosition = new Vector2(0f, narrowMargin.y);
    }
}