using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class CryptoTraceToggleButton : MonoBehaviour
{
    [Header("按钮")]
    [SerializeField] private Button toggleButton;
    [SerializeField] private TextMeshProUGUI buttonText;

    [Header("按钮文字")]
    [SerializeField] private string showText = "显示加密过程";
    [SerializeField] private string hideText = "隐藏加密过程";

    private void Awake()
    {
        if (toggleButton == null)
            toggleButton = GetComponent<Button>();

        if (toggleButton != null)
            toggleButton.onClick.AddListener(TogglePanel);
    }

    private void Start()
    {
        RefreshText();
    }

    private void TogglePanel()
    {
        if (CryptoTracePanel.Instance == null)
        {
            Debug.LogWarning("[CryptoTraceToggleButton] CryptoTracePanel.Instance is null.");
            return;
        }

        CryptoTracePanel.Instance.ToggleVisible();
        RefreshText();
    }

    private void RefreshText()
    {
        if (buttonText == null || CryptoTracePanel.Instance == null)
            return;

        buttonText.text = CryptoTracePanel.Instance.IsVisible() ? hideText : showText;
    }
}