using System.Collections;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class CryptoTracePanel : MonoBehaviour
{
    public static CryptoTracePanel Instance { get; private set; }

    [Header("摘要区域")]
    [SerializeField] private TextMeshProUGUI headerText;
    [SerializeField] private TextMeshProUGUI progressText;
    [SerializeField] private TextMeshProUGUI stepTitleText;
    [SerializeField] private TextMeshProUGUI stepSummaryText;
    [SerializeField] private TextMeshProUGUI stepIOText;

    [Header("详细日志区域，可不填")]
    [SerializeField] private TextMeshProUGUI detailLogText;
    [SerializeField] private ScrollRect scrollRect;

    [Header("根节点")]
    [SerializeField] private GameObject panelRoot;

    [Header("分页按钮")]
    [SerializeField] private Button prevButton;
    [SerializeField] private Button nextButton;
    [SerializeField] private Button playPauseButton;
    [SerializeField] private Button clearButton;
    [SerializeField] private Button closeButton;

    [Header("设置")]
    [SerializeField] private bool enableTrace = true;
    [SerializeField] private bool startVisible = false;

    [Tooltip("新步骤来了是否自动打开面板。建议关闭。")]
    [SerializeField] private bool openPanelWhenNewStep = false;

    [Tooltip("新步骤来了是否自动播放。建议关闭，手动点击播放。")]
    [SerializeField] private bool autoPlayOnNewStep = false;

    [Tooltip("每一步自动播放停留时间。")]
    [SerializeField] private float stepDisplaySeconds = 0.85f;

    [Tooltip("每帧最多处理多少条 Trace 事件，防止 UI 一帧处理太多导致卡顿。")]
    [SerializeField] private int maxTraceEventsPerFrame = 2;

    [Tooltip("是否忽略高频 INPUT / SNAPSHOT / HEARTBEAT Trace。建议开启。")]
    [SerializeField] private bool ignoreRealtimeNetworkTrace = true;

    [Header("批次刷新")]
    [Tooltip("如果新一批 Trace 距离上一批超过一定时间，则自动清空旧页面。")]
    [SerializeField] private bool clearWhenNewTraceBatchStarts = true;

    [Tooltip("超过多少秒没有新 Trace，就认为下一次 Step 是新流程。")]
    [SerializeField] private float newTraceBatchIdleSeconds = 1.0f;

    [Tooltip("日志区最多保留多少字符。")]
    [SerializeField] private int maxCharacters = 4000;

    [Tooltip("日志区是否自动滚到底。如果不用 ScrollView，建议关闭。")]
    [SerializeField] private bool autoScrollToBottom = false;

    [Header("文本长度限制")]
    [SerializeField] private int maxFormulaChars = 300;
    [SerializeField] private int maxInputChars = 600;
    [SerializeField] private int maxOutputChars = 600;
    [SerializeField] private int maxLogItemChars = 400;

    [Header("快捷键")]
    [SerializeField] private KeyCode toggleKey = KeyCode.F8;
    [SerializeField] private KeyCode clearKey = KeyCode.F9;

    [Header("播放按钮图片，可选")]
    [SerializeField] private Image playPauseIcon;
    [SerializeField] private Sprite playSprite;
    [SerializeField] private Sprite pauseSprite;

    private enum PendingTraceKind
    {
        Clear,
        Step,
        Log
    }

    private struct PendingTraceEvent
    {
        public PendingTraceKind kind;
        public CryptoTraceStep step;
        public string log;
    }

    private readonly List<CryptoTraceStep> steps = new List<CryptoTraceStep>();
    private readonly StringBuilder detailBuilder = new StringBuilder();

    private readonly ConcurrentQueue<PendingTraceEvent> pendingEvents =
        new ConcurrentQueue<PendingTraceEvent>();

    private int currentIndex = -1;
    private bool isPlaying;
    private bool hasTraceData;
    private Coroutine playCoroutine;

    private long lastTraceTicks;

    private static double StopwatchTicksToSeconds(long ticks)
    {
        return ticks / (double)Stopwatch.Frequency;
    }

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;

        transform.SetParent(null);
        DontDestroyOnLoad(gameObject);

        CryptoTrace.Enabled = enableTrace;

        if (panelRoot == null)
            panelRoot = gameObject;

        panelRoot.SetActive(startVisible);

        if (prevButton != null)
            prevButton.onClick.AddListener(ShowPreviousStep);

        if (nextButton != null)
            nextButton.onClick.AddListener(ShowNextStep);

        if (playPauseButton != null)
            playPauseButton.onClick.AddListener(TogglePlay);

        if (clearButton != null)
            clearButton.onClick.AddListener(Clear);

        if (closeButton != null)
            closeButton.onClick.AddListener(() => SetVisible(false));

        ResetSummary(force: true);
        RefreshButtons();
    }

    private void OnEnable()
    {
        CryptoTrace.OnClear += HandleClearEvent;
        CryptoTrace.OnStep += HandleStepEvent;
        CryptoTrace.OnLog += HandleLogEvent;
    }

    private void OnDisable()
    {
        CryptoTrace.OnClear -= HandleClearEvent;
        CryptoTrace.OnStep -= HandleStepEvent;
        CryptoTrace.OnLog -= HandleLogEvent;

        StopAutoPlay();
    }

    private void OnDestroy()
    {
        if (Instance == this)
            Instance = null;
    }

    private void Update()
    {
        if (Input.GetKeyDown(toggleKey))
            ToggleVisible();

        if (Input.GetKeyDown(clearKey))
            Clear();

        DrainPendingTraceEvents();
    }

    // ============================================================
    // 外部调用
    // ============================================================

    public void ToggleVisible()
    {
        if (panelRoot == null)
            return;

        SetVisible(!panelRoot.activeSelf);
    }

    public void TogglePanel()
    {
        ToggleVisible();
    }

    public void SetVisible(bool visible)
    {
        if (panelRoot != null)
            panelRoot.SetActive(visible);

        if (visible)
            RefreshVisibleUi();
        else
            StopAutoPlay();
    }

    public bool IsVisible()
    {
        return panelRoot != null && panelRoot.activeSelf;
    }

    public void Clear()
    {
        EnqueueClear();
    }

    public void AppendLog(string msg)
    {
        EnqueueLog(msg);
    }

    public void BeginNewTraceBatch()
    {
        EnqueueClear();

        lastTraceTicks = 0;
        hasTraceData = false;
    }

    // ============================================================
    // CryptoTrace 回调：这里只入队，不直接操作 UI
    // ============================================================

    private void HandleClearEvent()
    {
        EnqueueClear();
    }

    private void HandleStepEvent(CryptoTraceStep step)
    {
        if (ignoreRealtimeNetworkTrace && IsRealtimeNetworkStep(step))
            return;

        TryAutoClearForNewBatch();
        EnqueueStep(step);
        MarkTraceEventTime();
    }

    private void HandleLogEvent(string msg)
    {
        if (ignoreRealtimeNetworkTrace && IsRealtimeNetworkText(msg))
            return;

        TryAutoClearForNewBatch();
        EnqueueLog(msg);
        MarkTraceEventTime();
    }

    private void TryAutoClearForNewBatch()
    {
        if (!clearWhenNewTraceBatchStarts)
            return;

        if (!hasTraceData)
            return;

        if (lastTraceTicks <= 0)
            return;

        long now = Stopwatch.GetTimestamp();
        double idleSeconds = StopwatchTicksToSeconds(now - lastTraceTicks);

        if (idleSeconds >= Mathf.Max(0.1f, newTraceBatchIdleSeconds))
        {
            EnqueueClear();
            hasTraceData = false;
        }
    }

    private void MarkTraceEventTime()
    {
        lastTraceTicks = Stopwatch.GetTimestamp();
    }

    private void EnqueueClear()
    {
        pendingEvents.Enqueue(new PendingTraceEvent
        {
            kind = PendingTraceKind.Clear
        });
    }

    private void EnqueueStep(CryptoTraceStep step)
    {
        pendingEvents.Enqueue(new PendingTraceEvent
        {
            kind = PendingTraceKind.Step,
            step = step
        });
    }

    private void EnqueueLog(string msg)
    {
        pendingEvents.Enqueue(new PendingTraceEvent
        {
            kind = PendingTraceKind.Log,
            log = msg
        });
    }

    private void DrainPendingTraceEvents()
    {
        int budget = Mathf.Max(1, maxTraceEventsPerFrame);

        while (budget > 0 && pendingEvents.TryDequeue(out PendingTraceEvent evt))
        {
            switch (evt.kind)
            {
                case PendingTraceKind.Clear:
                    ClearNow();
                    break;

                case PendingTraceKind.Step:
                    AddStepToData(evt.step);
                    break;

                case PendingTraceKind.Log:
                    AddLogToData(evt.log);
                    break;
            }

            budget--;
        }
    }

    // ============================================================
    // 后台数据处理：面板关闭时也执行，但不会强制弹出
    // ============================================================

    private void ClearNow()
    {
        StopAutoPlay();

        steps.Clear();
        detailBuilder.Clear();
        currentIndex = -1;
        hasTraceData = false;

        if (IsVisible())
        {
            if (detailLogText != null)
                detailLogText.text = "";

            ResetSummary(force: true);
            RefreshButtons();
        }
    }

    private void AddStepToData(CryptoTraceStep step)
    {
        steps.Add(step);
        hasTraceData = true;

        AppendDetailDataOnly(
            $"[{CryptoTrace.FlowName(step.flow)} - {step.stepIndex}/{step.stepCount}] {step.title}\n" +
            $"{step.summary}"
        );

        if (currentIndex < 0)
            currentIndex = 0;

        if (openPanelWhenNewStep && panelRoot != null && !panelRoot.activeSelf)
            panelRoot.SetActive(true);

        if (IsVisible())
        {
            DisplayCurrentStep();

            if (detailLogText != null)
                detailLogText.text = detailBuilder.ToString();

            if (autoPlayOnNewStep)
                StartAutoPlayFromCurrent();
            else
                RefreshButtons();
        }
    }

    private void AddLogToData(string msg)
    {
        hasTraceData = true;

        AppendDetailDataOnly(msg);

        if (openPanelWhenNewStep && panelRoot != null && !panelRoot.activeSelf)
            panelRoot.SetActive(true);

        if (IsVisible())
        {
            if (detailLogText != null)
                detailLogText.text = detailBuilder.ToString();

            RefreshButtons();

            if (autoScrollToBottom && scrollRect != null)
                StartCoroutine(ScrollToBottomNextFrame());
        }
    }

    private void AppendDetailDataOnly(string msg)
    {
        if (string.IsNullOrWhiteSpace(msg))
            return;

        detailBuilder.AppendLine(LimitText(msg, maxLogItemChars));
        detailBuilder.AppendLine("----------------------------------------");
        detailBuilder.AppendLine();

        if (detailBuilder.Length > maxCharacters)
            detailBuilder.Remove(0, detailBuilder.Length - maxCharacters);
    }

    private void RefreshVisibleUi()
    {
        if (!IsVisible())
            return;

        if (currentIndex < 0 && steps.Count > 0)
            currentIndex = 0;

        if (steps.Count > 0)
            DisplayCurrentStep();
        else
            ResetSummary(force: true);

        if (detailLogText != null)
            detailLogText.text = detailBuilder.ToString();

        RefreshButtons();
    }

    // ============================================================
    // 分页显示
    // ============================================================

    public void ShowPreviousStep()
    {
        if (steps.Count <= 0)
            return;

        StopAutoPlay();

        currentIndex = Mathf.Max(0, currentIndex - 1);
        DisplayCurrentStep();
    }

    public void ShowNextStep()
    {
        if (steps.Count <= 0)
            return;

        StopAutoPlay();

        currentIndex = Mathf.Min(steps.Count - 1, currentIndex + 1);
        DisplayCurrentStep();
    }

    private void DisplayCurrentStep()
    {
        if (!IsVisible())
            return;

        if (steps.Count <= 0 || currentIndex < 0 || currentIndex >= steps.Count)
        {
            ResetSummary(force: true);
            return;
        }

        CryptoTraceStep step = steps[currentIndex];

        SetText(headerText, LimitTextSingleLine(CryptoTrace.FlowName(step.flow), 18));
        SetText(progressText, $"步骤 {currentIndex + 1} / {steps.Count}");

        string titlePrefix = "";
        if (step.stepIndex > 0 && step.stepCount > 0)
            titlePrefix = $"{step.stepIndex}/{step.stepCount}  ";

        SetText(stepTitleText, LimitText($"{titlePrefix}{step.title}", 80));
        SetText(stepSummaryText, LimitText(step.summary, 180));
        SetText(stepIOText, BuildStepIO(step));

        RefreshButtons();
    }

    // ============================================================
    // 播放 / 暂停
    // ============================================================

    public void TogglePlay()
    {
        if (isPlaying)
            StopAutoPlay();
        else
            StartAutoPlayFromCurrent();
    }

    private void StartAutoPlayFromCurrent()
    {
        if (steps.Count <= 0)
            return;

        if (!IsVisible())
            SetVisible(true);

        if (currentIndex < 0)
            currentIndex = 0;

        if (playCoroutine != null)
            StopCoroutine(playCoroutine);

        isPlaying = true;
        playCoroutine = StartCoroutine(PlayStepsCoroutine());

        RefreshButtons();
    }

    private void StopAutoPlay()
    {
        if (playCoroutine != null)
        {
            StopCoroutine(playCoroutine);
            playCoroutine = null;
        }

        isPlaying = false;
        RefreshButtons();
    }

    private IEnumerator PlayStepsCoroutine()
    {
        while (currentIndex >= 0 && currentIndex < steps.Count)
        {
            DisplayCurrentStep();

            yield return new WaitForSecondsRealtime(Mathf.Max(0.1f, stepDisplaySeconds));

            if (currentIndex >= steps.Count - 1)
                break;

            currentIndex++;
        }

        isPlaying = false;
        playCoroutine = null;
        RefreshButtons();
    }

    // ============================================================
    // ScrollView，可不用
    // ============================================================

    private IEnumerator ScrollToBottomNextFrame()
    {
        yield return null;

        Canvas.ForceUpdateCanvases();

        if (scrollRect != null)
            scrollRect.verticalNormalizedPosition = 0f;
    }

    // ============================================================
    // 格式化
    // ============================================================

    private string BuildStepIO(CryptoTraceStep step)
    {
        StringBuilder ioBuilder = new StringBuilder();

        if (!string.IsNullOrWhiteSpace(step.formula))
        {
            ioBuilder.AppendLine("公式 / 规则：");
            ioBuilder.AppendLine(LimitText(step.formula, maxFormulaChars));
            ioBuilder.AppendLine();
        }

        if (!string.IsNullOrWhiteSpace(step.input))
        {
            ioBuilder.AppendLine("输入：");
            ioBuilder.AppendLine(LimitText(step.input, maxInputChars));
            ioBuilder.AppendLine();
        }

        if (!string.IsNullOrWhiteSpace(step.output))
        {
            ioBuilder.AppendLine("输出：");
            ioBuilder.AppendLine(LimitText(step.output, maxOutputChars));
        }

        return ioBuilder.ToString();
    }

    private string LimitText(string text, int maxLength)
    {
        if (string.IsNullOrEmpty(text))
            return "";

        if (maxLength <= 0)
            return "";

        text = text.Replace("\r\n", "\n");

        if (text.Length <= maxLength)
            return text;

        int tailLength = Mathf.Min(100, maxLength / 4);
        int headLength = Mathf.Max(0, maxLength - tailLength - 40);

        return text.Substring(0, headLength)
               + "\n...已折叠 "
               + (text.Length - maxLength)
               + " 个字符...\n"
               + text.Substring(text.Length - tailLength);
    }

    private string LimitTextSingleLine(string text, int maxLength)
    {
        if (string.IsNullOrEmpty(text))
            return "";

        text = text.Replace("\r", " ").Replace("\n", " ");

        if (text.Length <= maxLength)
            return text;

        return text.Substring(0, maxLength) + "...";
    }

    private void ResetSummary(bool force)
    {
        if (!force && !IsVisible())
            return;

        SetText(headerText, "加密过程可视化");
        SetText(progressText, "等待加密流程...");
        SetText(stepTitleText, "暂无步骤");
        SetText(stepSummaryText, "登录、注册、请求票据或进入游戏时，这里会分页展示 RSA / DES 的加解密步骤。");
        SetText(stepIOText, "");
    }

    private void SetText(TextMeshProUGUI target, string value)
    {
        if (target != null)
            target.text = value ?? "";
    }

    private void RefreshButtons()
    {
        bool hasSteps = steps.Count > 0;

        if (prevButton != null)
            prevButton.interactable = hasSteps && currentIndex > 0;

        if (nextButton != null)
            nextButton.interactable = hasSteps && currentIndex < steps.Count - 1;

        if (playPauseButton != null)
        {
            playPauseButton.interactable = hasSteps;

            TextMeshProUGUI label = playPauseButton.GetComponentInChildren<TextMeshProUGUI>();
            if (label != null)
                label.text = "";
        }

        if (clearButton != null)
            clearButton.interactable = hasSteps || detailBuilder.Length > 0;

        if (playPauseIcon != null)
        {
            if (isPlaying && pauseSprite != null)
                playPauseIcon.sprite = pauseSprite;
            else if (!isPlaying && playSprite != null)
                playPauseIcon.sprite = playSprite;
        }
    }

    // ============================================================
    // 高频消息过滤
    // ============================================================

    private bool IsRealtimeNetworkStep(CryptoTraceStep step)
    {
        string text =
            (step.title ?? "") + " " +
            (step.summary ?? "") + " " +
            (step.input ?? "") + " " +
            (step.output ?? "");

        return IsRealtimeNetworkText(text);
    }

    private bool IsRealtimeNetworkText(string text)
    {
        if (string.IsNullOrEmpty(text))
            return false;

        return text.Contains("SNAPSHOT") ||
               text.Contains("Snapshot") ||
               text.Contains("snapshot") ||
               text.Contains("INPUT") ||
               text.Contains("Input") ||
               text.Contains("input") ||
               text.Contains("HEARTBEAT") ||
               text.Contains("Heartbeat") ||
               text.Contains("heartbeat");
    }
}