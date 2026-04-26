using UnityEngine;

public class Player_Health : Entity_Health
{
    private Player player;

    protected override void Awake()
    {
        base.Awake();
        player = GetComponent<Player>();
    }

    private void Update()
    {
        // if (Input.GetKeyDown(KeyCode.N))
        //     Die();
    }

    public void ApplyServerPlayerHealthSnapshot(PlayerSnapshot snapshot)
    {
        if (snapshot == null)
            return;

        ApplyServerHealthSnapshot(
            snapshot.damagePercent,
            snapshot.isDead
        );
    }

    protected override void Die()
    {
        base.Die();
        // player.ui.OpenDeathScreenUI();
        // GameManager.instance.SetLastPlayerPosition(transform.position);
        // GameManager.instance.RestartScene();
    }
}