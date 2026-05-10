"""GS 快照广播 Mixin + 游戏结束检测。

快照（SNAPSHOT）是服务端权威状态的同步载体，包含：
- players[]: 所有玩家权威状态（位置/速度/伤害/命数/硬直）
- projectiles[]: 飞行中的投射物
- loots[]: 场上的空投物
- events[]: 本帧发生的游戏事件

广播策略：默认每 2 tick 广播一次（SNAPSHOT_THROTTLE_ENABLED），
可配置每次有事件时强制广播（SNAPSHOT_FORCE_BROADCAST_ON_EVENTS）。
每个客户端用各自的 KcGs 加密 payload——并行发送（asyncio.gather）。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional

from game_config import (
    SNAPSHOT_FORCE_BROADCAST_ON_EVENTS,
    SNAPSHOT_INTERVAL_TICKS,
    SNAPSHOT_THROTTLE_ENABLED,
    SNAPSHOT_ENCRYPT_EVERY_N,
)
from game_models import ClientSession
from gs_protocol import TYPE_RESULT, TYPE_SNAPSHOT
from relay_contracts import RelayServerContext


class SnapshotBroadcastMixin:
    async def maybe_broadcast_snapshot(
        self: RelayServerContext,
        room_id: str,
        websocket: Any,
        reject_reason: str = "",  # 非空时表示本帧拒绝了当前 websocket 的输入（seq 乱序/禁止字段等）
    ) -> None:
        """按节流策略决定是否广播快照。

        节流逻辑：SNAPSHOT_THROTTLE_ENABLED=True 时每 N tick 广播一次，
        但有事件时（SNAPSHOT_FORCE_BROADCAST_ON_EVENTS=True）强制立即广播。
        """
        if not room_id:
            return
        should_broadcast = True
        if SNAPSHOT_THROTTLE_ENABLED:
            interval = max(1, int(SNAPSHOT_INTERVAL_TICKS))
            should_broadcast = self.tick % interval == 0
        if SNAPSHOT_FORCE_BROADCAST_ON_EVENTS and len(self.combat.pending_events) > 0:
            should_broadcast = True
        if not should_broadcast:
            return
        await self.broadcast_snapshot(
            room_id, reject_reason_by_socket={websocket: reject_reason}
        )
        self.combat.clear_events()

    def build_snapshot_payload(
        self: RelayServerContext, session: ClientSession, reject_reason: str
    ) -> dict:
        players = []
        for s in self.sessions.values():
            if s.room_id != session.room_id or s.client_id is None:
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
        for p in self.combat.projectiles.values():
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
        room_loots = self.get_room_loots(session.room_id or "")
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
        for e in self.combat.pending_events:
            events.append(
                {"eventType": e.event_type, "eventSeq": e.event_seq, "data": e.data}
            )
        return {
            "tick": self.tick,
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

        payload_obj = {
            "type": TYPE_SNAPSHOT,
            "sessionId": session.session_id or "",
            "roomId": session.room_id or "",
            **snapshot,
        }

        encrypt_every_n = max(0, int(SNAPSHOT_ENCRYPT_EVERY_N))

        # 0  = 全部明文
        # 1  = 每个 SNAPSHOT 都加密
        # 10 = 每 10 个 SNAPSHOT 加密一次
        payload_encrypted = (
        encrypt_every_n > 0
        and self.tick % encrypt_every_n == 0
    )

        if payload_encrypted:
            payload = self.encrypt_payload(session, payload_obj)
        else:
            payload = json.dumps(
                payload_obj,
                ensure_ascii=False,
                separators=(",", ":"),
            )

        response = {
            "type": TYPE_SNAPSHOT,
            "sessionId": session.session_id or "",
            "roomId": session.room_id,
            "payloadEncrypted": payload_encrypted,
            "payload": payload,
        }

        await websocket.send(json.dumps(response, ensure_ascii=False))

    async def broadcast_snapshot(
        self: RelayServerContext,
        room_id: str,
        reject_reason_by_socket: Optional[Dict[Any, str]] = None,  # 按 websocket 指定 reject reason
    ) -> None:
        """并行广播快照给房间内所有在线玩家，使用 asyncio.gather 并发发送。"""
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
        """检测游戏是否结束——存活玩家数 ≤ 1 时触发结算。

        同时统计在线玩家和重连宽限期内的离线玩家（断线玩家也应出现在结算中）。
        游戏结束：状态 PLAYING→FINISHED，广播 RESULT，清理投射物/空投。
        """
        if not room_id:
            return
        room_state = self.room_states.get(room_id)
        if room_state is None:
            return
        if room_state.get("status") != "PLAYING":
            return
        if room_state.get("gameOver"):
            return  # 已结束，避免重复广播 RESULT

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
                    "payload": result_payload,
                },
            )

        # 清理对战状态
        self.combat.clear_events()
        self.room_loots.pop(room_id, None)
        self.room_next_loot_tick.pop(room_id, None)

    # ═══════════════════════════════════════════════════════════════
    # Chat
    # ═══════════════════════════════════════════════════════════════
