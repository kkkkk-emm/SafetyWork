from __future__ import annotations

from game_config import BULLET_DB, WEAPON_DB
from game_debug import debug_print

try:
    from game_config import DEBUG_COMBAT_WARN
except ImportError:
    DEBUG_COMBAT_WARN = True


DEFAULT_WEAPON_ID = "手枪"
DEFAULT_BULLET_ID = "普通子弹"


def get_weapon_cfg(weapon_id: str) -> dict:
    if weapon_id in WEAPON_DB:
        return WEAPON_DB[weapon_id]

    if DEFAULT_WEAPON_ID in WEAPON_DB:
        debug_print(
            DEBUG_COMBAT_WARN,
            f"[COMBAT WARN] weapon_id={weapon_id} not found, fallback={DEFAULT_WEAPON_ID}",
        )
        return WEAPON_DB[DEFAULT_WEAPON_ID]

    first_key = next(iter(WEAPON_DB))
    debug_print(
        DEBUG_COMBAT_WARN,
        f"[COMBAT WARN] DEFAULT_WEAPON_ID missing, fallback first weapon={first_key}",
    )
    return WEAPON_DB[first_key]


def get_bullet_cfg(bullet_id: str) -> dict:
    if bullet_id in BULLET_DB:
        return BULLET_DB[bullet_id]

    if DEFAULT_BULLET_ID in BULLET_DB:
        debug_print(
            DEBUG_COMBAT_WARN,
            f"[COMBAT WARN] bullet_id={bullet_id} not found, fallback={DEFAULT_BULLET_ID}",
        )
        return BULLET_DB[DEFAULT_BULLET_ID]

    first_key = next(iter(BULLET_DB))
    debug_print(
        DEBUG_COMBAT_WARN,
        f"[COMBAT WARN] DEFAULT_BULLET_ID missing, fallback first bullet={first_key}",
    )
    return BULLET_DB[first_key]


def get_weapon_bullet_id(weapon_cfg: dict) -> str:
    return str(weapon_cfg.get("bullet_id", DEFAULT_BULLET_ID))


def resolve_visual_id(bullet_id: str, bullet_cfg: dict) -> str:
    return str(bullet_cfg.get("visual_id", bullet_id))


def normalize_special_bullet_id(bullet_id: str) -> str:
    if bullet_id in ("sword_wave", "swordwave", "SwordWave"):
        return "剑气"
    if bullet_id in ("pistol_bullet", "normal_gun"):
        return "普通子弹"
    if bullet_id in ("sniper_bullet", "sniper"):
        return "狙击子弹"
    if bullet_id in ("heavy_machine_bullet", "machine_gun"):
        return "机枪子弹"
    return bullet_id
