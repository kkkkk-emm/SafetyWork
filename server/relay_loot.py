"""GS 空投管理 Mixin——生成 / 物理下落 / 拾取 / 清理。

空投在固定间隔（LOOT_SPAWN_INTERVAL_TICKS）从上方随机位置生成，
受 LOOT_GRAVITY 重力下落至平台表面停止，玩家靠近即可拾取。
"""

from __future__ import annotations

import random
from typing import Optional

import game_simulation
from game_config import (
    EFFECT_DROP_POOL,
    LOOT_DROP_PLATFORM_MARGIN,
    LOOT_FALL_SPEED_CAP,
    LOOT_GRAVITY,
    LOOT_HALF_HEIGHT,
    LOOT_MAX_ALIVE,
    LOOT_PICKUP_ONLY_WHEN_LANDED,
    LOOT_PICKUP_RADIUS,
    LOOT_SPAWN_INTERVAL_TICKS,
    LOOT_SPAWN_Y,
    LOOT_TYPE_WEIGHTS,
    SIM_DT,
    WEAPON_DROP_POOL,
)
from game_models import ClientSession, ServerLoot
from relay_contracts import RelayServerContext


_GAME_RANDOM = random.SystemRandom()


class LootManagerMixin:
    def get_room_loots(self: RelayServerContext, room_id: str) -> dict[str, ServerLoot]:
        """获取房间空投字典，不存在时懒初始化。"""
        if room_id not in self.room_loots:
            self.room_loots[room_id] = {}
        return self.room_loots[room_id]

    def choose_random_loot_x(self: RelayServerContext) -> float:
        """在所有平台的 x 范围内加权随机选择一个 x 坐标。

        权重 = 平台宽度（越宽的平台上空投出现概率越高）。
        """
        candidates = []
        for platform in game_simulation.MAP_PLATFORMS:
            left = float(platform.x_min) + LOOT_DROP_PLATFORM_MARGIN
            right = float(platform.x_max) - LOOT_DROP_PLATFORM_MARGIN
            if right <= left:
                continue
            candidates.append({"left": left, "right": right, "weight": right - left})
        if not candidates:
            return 0.0
        total_weight = sum(c["weight"] for c in candidates)
        roll = _GAME_RANDOM.random() * total_weight
        chosen = candidates[-1]
        for c in candidates:
            roll -= c["weight"]
            if roll <= 0:
                chosen = c
                break
        return _GAME_RANDOM.uniform(chosen["left"], chosen["right"])

    def find_loot_landing_platform_y(
        self: RelayServerContext, x: float, previous_y: float, next_y: float
    ) -> Optional[float]:
        candidates = []
        for platform in game_simulation.MAP_PLATFORMS:
            left = float(platform.x_min) + LOOT_DROP_PLATFORM_MARGIN
            right = float(platform.x_max) - LOOT_DROP_PLATFORM_MARGIN
            if x < left or x > right:
                continue
            landing_y = float(platform.y) + LOOT_HALF_HEIGHT
            if previous_y >= landing_y >= next_y:
                candidates.append(landing_y)
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return candidates[0]

    def maybe_spawn_loot_for_room(self: RelayServerContext, room_id: str) -> None:
        """在间隔 tick 到达且场上空投数未达到上限时，随机生成一个空投。

        空投类型按 LOOT_TYPE_WEIGHTS 权重随机：effect（效果道具）或 weapon（武器）。
        空投从 LOOT_SPAWN_Y 高度生成，将在后续 step 中受重力下落。
        """
        if not room_id:
            return
        next_tick = self.room_next_loot_tick.get(room_id, 0)
        if self.tick < next_tick:
            return
        loots = self.get_room_loots(room_id)
        alive_count = sum(1 for loot in loots.values() if loot.alive)
        if alive_count >= LOOT_MAX_ALIVE:
            self.room_next_loot_tick[room_id] = self.tick + LOOT_SPAWN_INTERVAL_TICKS
            return
        x = self.choose_random_loot_x()
        effect_weight = float(LOOT_TYPE_WEIGHTS.get("effect", 0.7))
        weapon_weight = float(LOOT_TYPE_WEIGHTS.get("weapon", 0.3))
        total_weight = max(0.0001, effect_weight + weapon_weight)
        roll = _GAME_RANDOM.random() * total_weight
        if roll < effect_weight and EFFECT_DROP_POOL:
            loot_type = "effect"
            item_id = _GAME_RANDOM.choice(EFFECT_DROP_POOL)
        elif WEAPON_DROP_POOL:
            loot_type = "weapon"
            item_id = _GAME_RANDOM.choice(WEAPON_DROP_POOL)
        elif EFFECT_DROP_POOL:
            loot_type = "effect"
            item_id = _GAME_RANDOM.choice(EFFECT_DROP_POOL)
        else:
            return
        loot_id = f"loot_{self.next_loot_id}"
        self.next_loot_id += 1
        loot = ServerLoot(
            loot_id=loot_id,
            loot_type=loot_type,
            item_id=item_id,
            pos_x=float(x),
            pos_y=float(LOOT_SPAWN_Y),
            radius=LOOT_PICKUP_RADIUS,
            alive=True,
            vel_y=0.0,
            landed=False,
            target_platform_y=0.0,
        )
        loots[loot_id] = loot
        self.combat.push_event(
            "LOOT_SPAWNED",
            {
                "lootId": loot.loot_id,
                "lootType": loot.loot_type,
                "itemId": loot.item_id,
                "x": loot.pos_x,
                "y": loot.pos_y,
                "radius": loot.radius,
            },
        )
        self.room_next_loot_tick[room_id] = self.tick + LOOT_SPAWN_INTERVAL_TICKS

    def step_loots_for_room(self: RelayServerContext, room_id: str) -> None:
        if not room_id:
            return
        loots = self.get_room_loots(room_id)
        if not loots:
            return
        for loot in loots.values():
            if not loot.alive or loot.landed:
                continue
            previous_y = loot.pos_y
            loot.vel_y += LOOT_GRAVITY
            if loot.vel_y < LOOT_FALL_SPEED_CAP:
                loot.vel_y = LOOT_FALL_SPEED_CAP
            next_y = loot.pos_y + loot.vel_y * SIM_DT
            landing_y = self.find_loot_landing_platform_y(
                x=loot.pos_x, previous_y=previous_y, next_y=next_y
            )
            if landing_y is not None:
                loot.pos_y = landing_y
                loot.vel_y = 0.0
                loot.landed = True
                loot.target_platform_y = landing_y
                self.combat.push_event(
                    "LOOT_LANDED",
                    {
                        "lootId": loot.loot_id,
                        "lootType": loot.loot_type,
                        "itemId": loot.item_id,
                        "x": loot.pos_x,
                        "y": loot.pos_y,
                    },
                )
            else:
                loot.pos_y = next_y

    def check_loot_pickups_for_room(self: RelayServerContext, room_id: str) -> None:
        if not room_id:
            return
        loots = self.get_room_loots(room_id)
        if not loots:
            return
        for session in list(self.sessions.values()):
            if (
                session.room_id != room_id
                or session.client_id is None
                or session.is_dead
            ):
                continue
            player_center_y = session.pos_y + 0.4
            for loot in list(loots.values()):
                if not loot.alive:
                    continue
                if LOOT_PICKUP_ONLY_WHEN_LANDED and not loot.landed:
                    continue
                dx = session.pos_x - loot.pos_x
                dy = player_center_y - loot.pos_y
                dist_sq = dx * dx + dy * dy
                pickup_radius = max(loot.radius, LOOT_PICKUP_RADIUS)
                if dist_sq > pickup_radius * pickup_radius:
                    continue
                self.apply_loot_to_session(session, loot)
                loot.alive = False
                self.combat.push_event(
                    "LOOT_PICKED",
                    {
                        "lootId": loot.loot_id,
                        "lootType": loot.loot_type,
                        "itemId": loot.item_id,
                        "clientId": session.client_id,
                        "x": loot.pos_x,
                        "y": loot.pos_y,
                    },
                )

    def apply_loot_to_session(
        self: RelayServerContext, session: ClientSession, loot: ServerLoot
    ) -> None:
        if loot.loot_type == "effect":
            if (
                not hasattr(session, "equipped_effect_ids")
                or session.equipped_effect_ids is None
            ):
                session.equipped_effect_ids = []
            if loot.item_id not in session.equipped_effect_ids:
                session.equipped_effect_ids.append(loot.item_id)
        elif loot.loot_type == "weapon":
            session.equipped_weapon_id = loot.item_id

    def cleanup_dead_loots_for_room(self: RelayServerContext, room_id: str) -> None:
        loots = self.get_room_loots(room_id)
        dead_ids = [lid for lid, loot in loots.items() if not loot.alive]
        for lid in dead_ids:
            loots.pop(lid, None)

    # ═══════════════════════════════════════════════════════════════
    # Physics delegates (unchanged)
    # ═══════════════════════════════════════════════════════════════
