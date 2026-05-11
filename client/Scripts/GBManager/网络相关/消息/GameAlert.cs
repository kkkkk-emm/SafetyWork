using System;
using DG.Tweening;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class GameAlert : MonoBehaviour
{
    public static GameAlert Instance { get; private set; }

    [Header("Root")]
    [SerializeField] private GameObject panelRoot;

    [Header("Animation Targets")]
    [SerializeField] private CanvasGroup backgroundGroup;
    [SerializeField] private CanvasGroup boxGroup;
    [SerializeField] private RectTransform alertBox;

    [Header("Texts")]
    [SerializeField] private TMP_Text titleText;
    [SerializeField] private TMP_Text messageText;

    [Header("Buttons")]
    [SerializeField] private Button confirmButton;
    [SerializeField] private Button cancelButton;
    [SerializeField] private TMP_Text confirmButtonText;
    [SerializeField] private TMP_Text cancelButtonText;

    [Header("Animation")]
    [SerializeField] private float showDuration = 0.22f;
    [SerializeField] private float hideDuration = 0.16f;
    [SerializeField] private float startScale = 0.82f;
    [SerializeField] private Ease showEase = Ease.OutBack;
    [SerializeField] private Ease hideEase = Ease.InQuad;

    private Action onConfirm;
    private Action onCancel;
    private Sequence currentSequence;
    private bool isClosing;

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);

        if (panelRoot == null)
            panelRoot = gameObject;

        if (confirmButton != null)
            confirmButton.onClick.AddListener(HandleConfirm);

        if (cancelButton != null)
            cancelButton.onClick.AddListener(HandleCancel);

        HideInstant();
    }

    private void OnDestroy()
    {
        currentSequence?.Kill();

        if (Instance == this)
            Instance = null;
    }

    public static void Show(
        string title,
        string message,
        string confirmText = "确定",
        Action confirm = null,
        string cancelText = "",
        Action cancel = null
    )
    {
        if (Instance == null)
        {
            Debug.LogWarning("[GameAlert] Instance is null. " + title + " / " + message);
            return;
        }

        Instance.ShowInternal(title, message, confirmText, confirm, cancelText, cancel);
    }

    public static void Close()
    {
        if (Instance == null)
            return;

        Instance.HideAnimated(null);
    }

    private void ShowInternal(
        string title,
        string message,
        string confirmText,
        Action confirm,
        string cancelText,
        Action cancel
    )
    {
        currentSequence?.Kill();
        isClosing = false;

        onConfirm = confirm;
        onCancel = cancel;

        if (titleText != null)
            titleText.text = title;

        if (messageText != null)
            messageText.text = message;

        if (confirmButtonText != null)
            confirmButtonText.text = string.IsNullOrWhiteSpace(confirmText) ? "确定" : confirmText;

        bool hasCancel = !string.IsNullOrWhiteSpace(cancelText);

        if (cancelButton != null)
            cancelButton.gameObject.SetActive(hasCancel);

        if (cancelButtonText != null)
            cancelButtonText.text = cancelText;

        if (panelRoot != null)
            panelRoot.SetActive(true);

        if (backgroundGroup != null)
        {
            backgroundGroup.alpha = 0f;
            backgroundGroup.interactable = true;
            backgroundGroup.blocksRaycasts = true;
        }

        if (boxGroup != null)
        {
            boxGroup.alpha = 0f;
            boxGroup.interactable = false;
            boxGroup.blocksRaycasts = false;
        }

        if (alertBox != null)
            alertBox.localScale = Vector3.one * startScale;

        currentSequence = DOTween.Sequence();

        if (backgroundGroup != null)
        {
            currentSequence.Join(
                backgroundGroup
                    .DOFade(1f, showDuration)
                    .SetEase(Ease.OutQuad)
            );
        }

        if (boxGroup != null)
        {
            currentSequence.Join(
                boxGroup
                    .DOFade(1f, showDuration)
                    .SetEase(Ease.OutQuad)
            );
        }

        if (alertBox != null)
        {
            currentSequence.Join(
                alertBox
                    .DOScale(1f, showDuration)
                    .SetEase(showEase)
            );
        }

        currentSequence.OnComplete(() =>
        {
            if (boxGroup != null)
            {
                boxGroup.interactable = true;
                boxGroup.blocksRaycasts = true;
            }
        });
    }

    private void HideAnimated(Action afterHide)
    {
        if (isClosing)
            return;

        isClosing = true;
        currentSequence?.Kill();

        if (boxGroup != null)
        {
            boxGroup.interactable = false;
            boxGroup.blocksRaycasts = false;
        }

        currentSequence = DOTween.Sequence();

        if (backgroundGroup != null)
        {
            currentSequence.Join(
                backgroundGroup
                    .DOFade(0f, hideDuration)
                    .SetEase(hideEase)
            );
        }

        if (boxGroup != null)
        {
            currentSequence.Join(
                boxGroup
                    .DOFade(0f, hideDuration)
                    .SetEase(hideEase)
            );
        }

        if (alertBox != null)
        {
            currentSequence.Join(
                alertBox
                    .DOScale(startScale, hideDuration)
                    .SetEase(hideEase)
            );
        }

        currentSequence.OnComplete(() =>
        {
            HideInstant();
            afterHide?.Invoke();
        });
    }

    private void HideInstant()
    {
        currentSequence?.Kill();

        if (panelRoot != null)
            panelRoot.SetActive(false);

        if (backgroundGroup != null)
        {
            backgroundGroup.alpha = 0f;
            backgroundGroup.interactable = false;
            backgroundGroup.blocksRaycasts = false;
        }

        if (boxGroup != null)
        {
            boxGroup.alpha = 0f;
            boxGroup.interactable = false;
            boxGroup.blocksRaycasts = false;
        }

        if (alertBox != null)
            alertBox.localScale = Vector3.one;

        onConfirm = null;
        onCancel = null;
        isClosing = false;
    }

    private void HandleConfirm()
    {
        Action callback = onConfirm;

        HideAnimated(() =>
        {
            callback?.Invoke();
        });
    }

    private void HandleCancel()
    {
        Action callback = onCancel;

        HideAnimated(() =>
        {
            callback?.Invoke();
        });
    }
}