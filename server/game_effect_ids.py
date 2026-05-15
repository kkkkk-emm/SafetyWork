
from __future__ import annotations

from typing import List

# 效果 ID 别名表：多方映射到单一标准名
EFFECT_ID_ALIASES = {
    "hoversplit": "hover_split",
    "hover_split": "hover_split",
    "Effect_HoverSplit": "hover_split",
    "delayedexplosion": "delayed_explosion",
    "delayed_explosion": "delayed_explosion",
    "Effect_DelayedExplosion": "delayed_explosion",
    "swordwave": "sword_wave",
    "sword_wave": "sword_wave",
    "Effect_SwordWave": "sword_wave",
    "parry": "parry",
    "Effect_Parry": "parry",
}


def normalize_effect_id(effect_id: str) -> str:
    """规范化 normalize_effect_id 相关的效果 ID 数据。"""
    if effect_id is None:
        return ""
    return EFFECT_ID_ALIASES.get(effect_id, effect_id)


def normalize_effect_list(effect_ids: List[str]) -> List[str]:
    """规范化 normalize_effect_list 相关的效果 ID 数据。"""
    result = []
    if effect_ids is None:
        return result
    for effect_id in effect_ids:
        normalized = normalize_effect_id(effect_id)
        if normalized and normalized not in result:
            result.append(normalized)
    return result
