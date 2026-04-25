using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class LobbyPlayerCard : MonoBehaviour
{
    [Header("UI")]
    [SerializeField] private Image portraitImage;
    [SerializeField] private TextMeshProUGUI slotText;
    [SerializeField] private TextMeshProUGUI nameText;
    [SerializeField] private GameObject hostBadge;
    [SerializeField] private Button readyButton;

    [Header("Ready ÑÕÉ«")]
    [SerializeField] private Color readyColor = Color.green;
    [SerializeField] private Color notReadyColor = Color.white;
    [SerializeField] private Color disabledColor = new Color(0.75f, 0.75f, 0.75f, 1f);

    private Action onReadyClicked;
    private bool isLocalPlayer;

    private void Awake()
    {
        if (readyButton != null)
        {
            readyButton.onClick.RemoveListener(HandleReadyClicked);
            readyButton.onClick.AddListener(HandleReadyClicked);
        }
    }

    public void Setup(
        RoomPlayerInfo player,
        bool isLocal,
        Sprite portrait,
        Action onReadyClickedCallback
    )
    {
        if (player == null)
            return;

        isLocalPlayer = isLocal;
        onReadyClicked = onReadyClickedCallback;

        if (portraitImage != null)
            portraitImage.sprite = portrait;

        if (slotText != null)
            slotText.text = player.slotNo == 1 ? "P1" : "P2";

        if (nameText != null)
        {
            string hostText = player.isHost ? "  HOST" : "";
            nameText.text = $"{player.clientId}{hostText}";
        }

        if (hostBadge != null)
            hostBadge.SetActive(player.isHost);

        if (readyButton != null)
            readyButton.interactable = isLocalPlayer;

        ApplyReadyVisual(player.ready);
    }

    private void ApplyReadyVisual(bool ready)
    {
        if (readyButton == null)
            return;

        TextMeshProUGUI label = readyButton.GetComponentInChildren<TextMeshProUGUI>();

        if (label != null)
        {
            if (isLocalPlayer)
            {
                label.text = ready ? "CANCEL" : "READY";
            }
            else
            {
                label.text = ready ? "READY" : "WAIT";
            }
        }

        Color targetColor;

        if (ready)
            targetColor = readyColor;
        else if (isLocalPlayer)
            targetColor = notReadyColor;
        else
            targetColor = disabledColor;

        ColorBlock colors = readyButton.colors;
        colors.normalColor = targetColor;
        colors.highlightedColor = targetColor;
        colors.selectedColor = targetColor;
        colors.disabledColor = targetColor;
        colors.pressedColor = ready ? readyColor * 0.85f : targetColor * 0.85f;

        readyButton.colors = colors;
    }

    private void HandleReadyClicked()
    {
        if (!isLocalPlayer)
            return;

        onReadyClicked?.Invoke();
    }
}