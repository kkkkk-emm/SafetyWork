"""战斗配置查询——武器/子弹安全的查找函数。

所有查找都有 fallback 链：指定 ID → 默认 ID → 数据库第一个条目。
防止配置错误导致 KeyError 崩溃，同时打印警告方便排查。
"""

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
    """安全查找武器配置——找不到时回退到手枪，打印警告。"""
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
    """读取并规范化 get_bullet_cfg 所需的战斗配置。"""
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
    """读取并规范化 get_weapon_bullet_id 所需的战斗配置。"""
    return str(weapon_cfg.get("bullet_id", DEFAULT_BULLET_ID))

