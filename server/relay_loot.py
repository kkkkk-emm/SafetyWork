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
    """处理 LootManagerMixin 相关的道具生成、拾取或清理逻辑。"""
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
        """处理 LootManagerMixin.find_loot_landing_platform_y 相关的道具生成、拾取或清理逻辑。"""
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
        # 取最高的命中平台，防止道具穿过上层平台后才落到下层。
        candidates.sort(reverse=True)
        return candidates[0]

    def maybe_spawn_loot_for_room(self: RelayServerContext, room_id: str) -> None:
        """在间隔 tick 到达且场上空投数未达到上限时，随机生成一个空投。"""
        if not room_id:
            return

        tick = self.get_room_tick(room_id)
        combat = self.get_room_combat(room_id)

        next_tick = self.room_next_loot_tick.get(room_id)

        # 第一次进入 PLAYING 后，初始化下一次空投时间。
        if next_tick is None:
            self.room_next_loot_tick[room_id] = tick + LOOT_SPAWN_INTERVAL_TICKS
            print(
                f"[LOOT INIT] room={room_id} "
                f"tick={tick} next={self.room_next_loot_tick[room_id]}"
            )
            return

        if tick < next_tick:
            return

        loots = self.get_room_loots(room_id)
        alive_count = sum(1 for loot in loots.values() if loot.alive)

        if alive_count >= LOOT_MAX_ALIVE:
            self.room_next_loot_tick[room_id] = tick + LOOT_SPAWN_INTERVAL_TICKS
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

        combat.push_event(
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

        self.room_next_loot_tick[room_id] = tick + LOOT_SPAWN_INTERVAL_TICKS

        print(
            f"[LOOT SPAWNED] room={room_id} "
            f"tick={tick} next={self.room_next_loot_tick[room_id]} "
            f"id={loot_id} type={loot_type} item={item_id}"
        )

    def step_loots_for_room(self: RelayServerContext, room_id: str) -> None:
        if not room_id:
            return

        loots = self.get_room_loots(room_id)

        if not loots:
            return

        combat = self.get_room_combat(room_id)

        for loot in loots.values():
            # 仅推进“存活且尚未落地”的空投；落地后保持静止，等待拾取或清理。
            if not loot.alive or loot.landed:
                continue

            previous_y = loot.pos_y
            # 每 tick 施加重力加速度，再用终端速度限制下落速度，避免单帧位移过大。
            loot.vel_y += LOOT_GRAVITY

            if loot.vel_y < LOOT_FALL_SPEED_CAP:
                loot.vel_y = LOOT_FALL_SPEED_CAP

            next_y = loot.pos_y + loot.vel_y * SIM_DT

            # 使用“上一帧 y -> 下一帧 y”的跨帧区间做落台判定，防止高速下落穿过平台。
            landing_y = self.find_loot_landing_platform_y(
                x=loot.pos_x,
                previous_y=previous_y,
                next_y=next_y,
            )

            if landing_y is not None:
                # 命中平台后立即钉在平台表面，并清零竖直速度，后续不再参与下落积分。
                loot.pos_y = landing_y
                loot.vel_y = 0.0
                loot.landed = True
                loot.target_platform_y = landing_y

                # 通过事件流广播“已落地”，驱动客户端表现与状态同步。
                combat.push_event(
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
                # 未命中平台则提交本帧位置更新，继续自由下落。
                loot.pos_y = next_y

    def check_loot_pickups_for_room(self: RelayServerContext, room_id: str) -> None:
        if not room_id:
            return

        loots = self.get_room_loots(room_id)

        if not loots:
            return

        combat = self.get_room_combat(room_id)

        for session in list(self.sessions.values()):
            # 只允许当前房间、已完成身份绑定且存活的玩家参与拾取判定。
            if (
                session.room_id != room_id
                or session.client_id is None
                or session.is_dead
            ):
                continue

            # 用玩家身体中心近似拾取点，减少贴地/跳跃时的体感误差。
            player_center_y = session.pos_y + 0.4

            for loot in list(loots.values()):
                # 已被拾取或标记失效的空投不再参与判定。
                if not loot.alive:
                    continue

                # 当配置要求“仅落地可拾取”时，空中空投直接跳过。
                if LOOT_PICKUP_ONLY_WHEN_LANDED and not loot.landed:
                    continue

                # 使用平方距离比较避免开方，降低每 tick 多玩家多道具的计算开销。
                dx = session.pos_x - loot.pos_x
                dy = player_center_y - loot.pos_y
                dist_sq = dx * dx + dy * dy

                # 取道具半径与全局最小拾取半径的较大值，保证不同道具手感一致。
                pickup_radius = max(loot.radius, LOOT_PICKUP_RADIUS)

                if dist_sq > pickup_radius * pickup_radius:
                    continue

                # 命中拾取范围后立刻应用奖励并置为失效，防止同帧被重复拾取。
                self.apply_loot_to_session(session, loot)
                loot.alive = False

                # 通过事件广播拾取结果，让客户端同步移除道具并更新展示。
                combat.push_event(
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
        """将道具效果应用到玩家会话。"""
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
        """处理 LootManagerMixin.cleanup_dead_loots_for_room 相关的道具生成、拾取或清理逻辑。"""
        loots = self.get_room_loots(room_id)
        dead_ids = [lid for lid, loot in loots.items() if not loot.alive]
        for lid in dead_ids:
            loots.pop(lid, None)
