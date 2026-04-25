using TMPro;
using Unity.VisualScripting;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.UI;

public class DungeonEntryButton : MonoBehaviour
{
    public Image icon;
    public TextMeshProUGUI titleText;
    public TextMeshProUGUI levelText;
    public Button button;

    DungeonDataSO data;
    public UnityEvent<DungeonDataSO> onSelected;

    public void Init(DungeonDataSO d)
    {
        data = d;
        if (icon) icon.sprite = d.icon;
        if (titleText) titleText.text = d.dungeonName;
        if (levelText) levelText.text = $"Lv {d.recommendedLevel}";
        if (button) button.onClick.RemoveAllListeners();
        if (button) button.onClick.AddListener(OnClicked);

    }


    void OnClicked()
    {
        onSelected?.Invoke(data);
    }
}
