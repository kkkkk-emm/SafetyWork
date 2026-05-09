from __future__ import annotations

from typing import List

from game_config import EFFECT_DB


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
    if effect_id is None:
        return ""
    return EFFECT_ID_ALIASES.get(effect_id, effect_id)


def normalize_effect_list(effect_ids: List[str]) -> List[str]:
    result = []
    if effect_ids is None:
        return result
    for effect_id in effect_ids:
        normalized = normalize_effect_id(effect_id)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def get_effect_cfg(effect_id: str):
    normalized = normalize_effect_id(effect_id)
    return normalized, EFFECT_DB.get(normalized)
