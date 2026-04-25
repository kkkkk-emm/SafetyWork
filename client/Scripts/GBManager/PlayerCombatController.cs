using UnityEngine;

public class PlayerCombatController : MonoBehaviour
{
    [Header("状态记录")]
    private bool hasFiredSingleShot = false;
    private Player player;

    public Weapon currentWeapon;
    [SerializeField] private bool readLocalInput = true;

    public void SetReadLocalInput(bool value)
    {
        readLocalInput = value;
    }
    public void EquipWeapon(Weapon newWeapon)
    {
        currentWeapon = newWeapon;
        hasFiredSingleShot = false;

        Debug.Log($"成功装备了新武器: {newWeapon.data.name}");
    }

    private void Awake()
    {
        player = GetComponent<Player>();
    }

    private void Update()
    {
        if (player == null || currentWeapon == null || currentWeapon.data == null)
        {
            return;
        }
        if (!readLocalInput)
            return;
        bool isAuto = currentWeapon.data.isAutomatic;
        bool isHoldingShoot = player.attackHeld;

        if (isHoldingShoot)
        {
            if (isAuto)
            {
                currentWeapon.ExecuteAttack();
            }
            else if (!hasFiredSingleShot)
            {
                currentWeapon.ExecuteAttack();
                hasFiredSingleShot = true;
            }
        }
        else
        {
            hasFiredSingleShot = false;
        }
    }
}
