from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from game_config import (
    SNAPSHOT_FORCE_BROADCAST_ON_EVENTS,
    SNAPSHOT_INTERVAL_TICKS,
    SNAPSHOT_THROTTLE_ENABLED,
)
from game_models import ClientSession
from gs_protocol import TYPE_RESULT, TYPE_SNAPSHOT
from relay_contracts import RelayServerContext


class SnapshotBroadcastMixin:
    """处理 SnapshotBroadcastMixin 相关的快照构造或广播逻辑。"""
    async def maybe_broadcast_snapshot(
        self: RelayServerContext,
        room_id: str,
        websocket: Any,
        reject_reason: str = "",
    ) -> None:
        if not room_id:
            return

        tick = self.get_room_tick(room_id)
        combat = self.get_room_combat(room_id)

        should_broadcast = True

        # interval 至少为 1，避免配置误填 0 或负数导致除零/异常行为。
        if SNAPSHOT_THROTTLE_ENABLED:
            interval = max(1, int(SNAPSHOT_INTERVAL_TICKS))
            should_broadcast = tick % interval == 0

        if SNAPSHOT_FORCE_BROADCAST_ON_EVENTS and len(combat.pending_events) > 0:
            should_broadcast = True

        if not should_broadcast:
            return

        await self.broadcast_snapshot(
            room_id, reject_reason_by_socket={websocket: reject_reason}
        )
        combat.clear_events()

    def build_snapshot_payload(
        self: RelayServerContext, session: ClientSession, reject_reason: str
    ) -> dict:
        room_id = session.room_id or ""
        tick = self.get_room_tick(room_id)
        combat = self.get_room_combat(room_id)

        players = []
        # 快照只包含同房间玩家，且按服务端认可状态输出，客户端预测状态不会直接透传。
        for s in self.sessions.values():
            if s.room_id != room_id or s.client_id is None:
                continue
            players.append(
                {
                    "slotNo": 1 if s.client_id == "Client1" else 2,
                    "userId": s.user_id or 0,
                    "clientId": s.client_id,
                    "state": s.accepted_state,
                    "grounded": s.accepted_grounded,
                    "jumpCount": s.accepted_jump_count,
                    "posX": s.pos_x,
                    "posY": s.pos_y,
                    "velX": s.vel_x,
                    "velY": s.vel_y,
                    "aimX": getattr(s, "aim_x", 1.0),
                    "aimY": getattr(s, "aim_y", 0.0),
                    "equippedWeaponId": s.equipped_weapon_id,
                    "equippedEffectIds": list(s.equipped_effect_ids),
                    "damagePercent": s.damage_percent,
                    "stocks": s.stocks,
                    "isDead": s.is_dead,
                    "facing": s.facing,
                    "lastKnockbackX": s.last_knockback_x,
                    "lastKnockbackY": s.last_knockback_y,
                    "lastHitTick": s.last_hit_tick,
                }
            )

        projectiles = []
        for p in combat.projectiles.values():
            if not p.alive:
                continue
            projectiles.append(
                {
                    "projId": p.proj_id,
                    "ownerClientId": p.owner_client_id,
                    "weaponId": p.weapon_id,
                    "bulletId": getattr(p, "bullet_id", ""),
                    "visualId": getattr(p, "visual_id", ""),
                    "posX": p.pos_x,
                    "posY": p.pos_y,
                    "velX": p.vel_x,
                    "velY": p.vel_y,
                    "rotationDeg": getattr(p, "rotation_deg", 0.0),
                    "radius": p.radius,
                    "ttl": p.ttl,
                    "alive": p.alive,
                    "effectIds": list(p.effect_ids),
                }
            )

        loots = []
        room_loots = self.get_room_loots(room_id)
        for loot in room_loots.values():
            if not loot.alive:
                continue
            loots.append(
                {
                    "lootId": loot.loot_id,
                    "lootType": loot.loot_type,
                    "itemId": loot.item_id,
                    "posX": loot.pos_x,
                    "posY": loot.pos_y,
                    "velY": loot.vel_y,
                    "radius": loot.radius,
                    "landed": loot.landed,
                }
            )

        events = []
        for e in combat.pending_events:
            events.append(
                {"eventType": e.event_type, "eventSeq": e.event_seq, "data": e.data}
            )

        return {
            "tick": tick,
            "lastProcessedSeq": session.last_seq,
            "rejectReason": reject_reason,
            "players": players,
            "projectiles": projectiles,
            "loots": loots,
            "events": events,
        }

    async def send_snapshot(
        self: RelayServerContext,
        websocket: Any,
        session: ClientSession,
        reject_reason: str,
    ) -> None:
        snapshot = self.build_snapshot_payload(session, reject_reason)
        # 用 KcGs 加密 snapshot payload
        encrypted = self.encrypt_payload(
            session,
            {
                "type": TYPE_SNAPSHOT,
                "sessionId": session.session_id or "",
                "roomId": session.room_id or "",
                **snapshot,
            },
        )
        response = {
        "type": TYPE_SNAPSHOT,
        "sessionId": session.session_id or "",
        "roomId": session.room_id,
        "payloadEncrypted": True,
        "payload": encrypted,
    }
        await websocket.send(json.dumps(response, ensure_ascii=False))

    async def broadcast_snapshot(
        self: RelayServerContext,
        room_id: str,
        reject_reason_by_socket: Optional[Dict[Any, str]] = None,
    ) -> None:
        peers = list(self.rooms.get(room_id, set()))
        tasks = []
        for peer in peers:
            session = self.sessions.get(peer)
            if (
                session is None
                or session.room_id != room_id
                or session.client_id is None
            ):
                continue
            if not session.authenticated or session.kc_gs is None:
                continue
            reject_reason = ""
            if reject_reason_by_socket is not None:
                reject_reason = reject_reason_by_socket.get(peer, "")
            tasks.append(self.send_snapshot(peer, session, reject_reason))
        if not tasks:
            return
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                print(f"[SNAPSHOT SEND WARN] {result}")

    # ═══════════════════════════════════════════════════════════════
    # 游戏结束检测 / RESULT (阶段五第7步)
    # ═══════════════════════════════════════════════════════════════

    async def check_game_over(self: RelayServerContext, room_id: str) -> None:
        """检测是否仅剩 ≤1 名存活玩家，若是则广播 RESULT。"""
        if not room_id:
            return
        room_state = self.room_states.get(room_id)
        if room_state is None:
            return
        if room_state.get("status") != "PLAYING":
            return
        if room_state.get("gameOver"):
            return

        # 统计存活玩家 (stocks > 0)
        alive_players: list[ClientSession] = []
        all_players: list[ClientSession] = []
        for s in self.sessions.values():
            if s.room_id == room_id and s.client_id:
                all_players.append(s)
                if s.stocks > 0:
                    alive_players.append(s)
        # 也计入重连宽限期内的玩家
        for grace_info in self.reconnect_grace.values():
            s = grace_info["session"]
            if s.room_id == room_id and s.client_id:
                if s.stocks > 0:
                    alive_players.append(s)

        if len(alive_players) > 1:
            return  # 还有多个存活玩家，继续

        # 游戏结束
        room_state["gameOver"] = True
        room_state["status"] = "FINISHED"

        winner_user_id = 0
        reason = "DRAW"
        if alive_players:
            winner = alive_players[0]
            winner_user_id = winner.user_id or 0
            reason = "STOCK_ZERO"
        else:
            # 全员阵亡，取最后一个有分的
            for s in reversed(all_players):
                if s.user_id:
                    winner_user_id = s.user_id
                    break

        # 组装结算数据
        result_players = []
        for s in all_players:
            result_players.append(
                {
                    "userId": s.user_id or 0,
                    "clientId": s.client_id or "",
                    "stocksLeft": max(0, s.stocks),
                    "finalDamagePercent": round(s.damage_percent, 1),
                }
            )
        # 也加入重连宽限期内的玩家
        for grace_info in self.reconnect_grace.values():
            s = grace_info["session"]
            if s.room_id == room_id and s.client_id:
                result_players.append(
                    {
                        "userId": s.user_id or 0,
                        "clientId": s.client_id or "",
                        "stocksLeft": max(0, s.stocks),
                        "finalDamagePercent": round(s.damage_percent, 1),
                    }
                )

        print(
            f"[GAME OVER] room={room_id} winnerUserId={winner_user_id} reason={reason}"
        )
        await self.broadcast_result(room_id, winner_user_id, reason, result_players)

    async def broadcast_result(
        self: RelayServerContext,
        room_id: str,
        winner_user_id: int,
        reason: str,
        players: list,
    ) -> None:
        """广播 RESULT 给房间内所有在线玩家和重连宽限期内的玩家。"""
        # 在线玩家
        for peer in list(self.rooms.get(room_id, set())):
            session = self.sessions.get(peer)
            if session is None or not session.authenticated:
                continue
            result_payload = self.encrypt_payload(
                session,
                {
                    "type": TYPE_RESULT,
                    "sessionId": session.session_id or "",
                    "roomId": room_id,
                    "winnerUserId": winner_user_id,
                    "reason": reason,
                    "players": players,
                },
            )
            await self.send_json(
        peer,
        {
            "type": TYPE_RESULT,
            "sessionId": session.session_id or "",
            "roomId": room_id,
            "payloadEncrypted": True,
            "payload": result_payload,
        },
)

        # 清理当前房间的对战事件和掉落。
        # 这里不立刻删除 room_ticks / room_combats，避免 RESULT 后补发 snapshot 找不到状态。
        combat = self.get_room_combat(room_id)
        combat.clear_events()
        self.room_loots.pop(room_id, None)
        self.room_next_loot_tick.pop(room_id, None)
