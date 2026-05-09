from __future__ import annotations

import random
import string
from typing import Any, Dict, Optional

from game_config import MATCH_COUNTDOWN_MS, SPAWN_POINTS
from game_models import ClientSession
from gs_errors import GsRequestError
from gs_protocol import (
    TYPE_ROOM_CREATE_REP,
    TYPE_ROOM_JOIN_REQ,
    TYPE_ROOM_JOIN_REP,
    TYPE_ROOM_READY_REQ,
    TYPE_ROOM_READY_REP,
    TYPE_ROOM_START_REQ,
    TYPE_ROOM_START_REP,
    TYPE_ROOM_STATE,
    require_fields,
    require_string_field,
)


class RoomLifecycleMixin:
    def generate_room_id(self) -> str:
        alphabet = string.ascii_uppercase + string.digits
        for _ in range(100):
            room_id = "".join(random.choice(alphabet) for _ in range(4))
            if room_id not in self.room_states:
                return room_id
        return "".join(random.choice(alphabet) for _ in range(6))

    def get_or_create_room_state(self, room_id: str, host_client_id: str) -> Dict[str, Any]:
        if room_id not in self.room_states:
            self.room_states[room_id] = {
                "hostClientId": host_client_id,
                "status": "WAITING",
                "players": {},
            }
        return self.room_states[room_id]

    def allocate_slot_no(self, room_state: Dict[str, Any], _requested: str = "") -> int:
        players = room_state["players"]
        used_slots = {int(p["slotNo"]) for p in players.values() if "slotNo" in p}
        if 1 not in used_slots:
            return 1
        if 2 not in used_slots:
            return 2
        return -1

    def build_room_state_payload(
        self, room_id: str, local_session: Optional[ClientSession] = None,
    ) -> dict:
        room_state = self.room_states.get(room_id)
        if room_state is None:
            return {
                "roomId": room_id, "hostClientId": "", "state": "missing",
                "ownerUserId": 0,
                "players": [], "canStart": False,
                "localClientId": "", "localSlotNo": 0, "localIsHost": False,
            }
        players_dict = room_state.get("players", {})
        host_client_id = room_state.get("hostClientId", "")
        owner_user_id = 0
        players = []
        for player in players_dict.values():
            cid = player["clientId"]
            # 查找对应该玩家的 session 获取 username/userId
            player_user_id = 0
            player_username = ""
            ws = player.get("websocket")
            if ws is not None:
                player_session = self.sessions.get(ws)
                if player_session is not None:
                    player_user_id = player_session.user_id or 0
                    player_username = player_session.username or ""
            players.append({
                "userId": player_user_id,
                "username": player_username,
                "clientId": cid,
                "slotNo": int(player["slotNo"]),
                "ready": bool(player["ready"]),
                "isHost": cid == host_client_id,
                "online": bool(player.get("online", True)),
            })
            if cid == host_client_id:
                owner_user_id = player_user_id
        players.sort(key=lambda p: p["slotNo"])
        can_start = (
            room_state.get("status") == "WAITING"
            and len(players) >= 2
            and all(p["ready"] for p in players)
        )
        local_client_id = ""
        local_slot_no = 0
        local_is_host = False
        if local_session is not None and local_session.client_id:
            local_client_id = local_session.client_id
            local_is_host = local_client_id == host_client_id
            if local_client_id in players_dict:
                local_slot_no = int(players_dict[local_client_id]["slotNo"])
        return {
            "roomId": room_id,
            "hostClientId": host_client_id,
            "state": room_state.get("status", "WAITING"),
            "ownerUserId": owner_user_id,
            "players": players,
            "canStart": can_start,
            "localClientId": local_client_id,
            "localSlotNo": local_slot_no,
            "localIsHost": local_is_host,
        }

    async def broadcast_room_state(self, room_id: str) -> None:
        """广播 ROOM_STATE，每个客户端使用各自的 KcGs 加密 payload。"""
        for peer in list(self.rooms.get(room_id, set())):
            peer_session = self.sessions.get(peer)
            if peer_session is None or not peer_session.authenticated:
                continue
            payload_obj = self.build_room_state_payload(room_id, peer_session)
            payload_obj.setdefault("type", TYPE_ROOM_STATE)
            payload_obj.setdefault("sessionId", peer_session.session_id or "")
            payload_obj.setdefault("roomId", room_id)
            encrypted = self.encrypt_payload(peer_session, payload_obj)
            msg = {
                "type": TYPE_ROOM_STATE,
                "sessionId": peer_session.session_id or "",
                "roomId": room_id,
                "payload": encrypted,
            }
            await self.send_json(peer, msg)

    async def broadcast_game_start(self, room_id: str) -> None:
        match_id = f"match-{random.randint(100, 999)}"
        peers = list(self.rooms.get(room_id, set()))
        print(f"[BROADCAST_GAME_START] room={room_id} matchId={match_id} peers={len(peers)}")
        for peer in peers:
            peer_session = self.sessions.get(peer)
            if peer_session is None or not peer_session.authenticated:
                continue
            payload_obj = self.build_room_state_payload(room_id, peer_session)
            payload_obj["sceneName"] = "MainGame"
            payload_obj["matchId"] = match_id
            payload_obj["countdownMs"] = MATCH_COUNTDOWN_MS
            payload_obj.setdefault("type", TYPE_ROOM_START_REP)
            payload_obj.setdefault("sessionId", peer_session.session_id or "")
            encrypted = self.encrypt_payload(peer_session, payload_obj)
            msg = {
                "type": TYPE_ROOM_START_REP,
                "sessionId": peer_session.session_id or "",
                "roomId": room_id,
                "payload": encrypted,
            }
            print(
                f"[SEND GAME_START] room={room_id} "
                f"to={peer_session.client_id} slot={payload_obj.get('localSlotNo')}"
            )
            await self.send_json(peer, msg)

    # ═══════════════════════════════════════════════════════════════
    # ROOM_CREATE_REQ (阶段四第1步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_create_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)

        # 解密并校验 auth
        require_fields(data, ("sessionId", "auth"))
        auth = self.decrypt_auth(session, data)
        if require_string_field(auth, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        # 离开旧房间
        if session.room_id:
            old_room_id = session.room_id
            await self.remove_player_from_room_state(websocket, old_room_id)
            self.remove_from_room(websocket, old_room_id)
            session.room_id = None
            session.client_id = None
            await self.broadcast_room_state(old_room_id)

        room_id = self.generate_room_id()
        # 内部走 JOIN 流程分配 Client1
        join_data = {
            "type": TYPE_ROOM_JOIN_REQ,
            "clientId": "CREATE_HOST",
            "roomId": room_id,
        }
        await self._internal_join_room(websocket, join_data)
        print(f"[ROOM_CREATE_REQ] creator=Client1 room={room_id}")

        # 返回 ROOM_CREATE_REP
        rep_payload = self.encrypt_payload(session, {
            "type": TYPE_ROOM_CREATE_REP,
            "ok": True,
            "sessionId": session.session_id or "",
            "roomId": room_id,
        })
        await self.send_json(websocket, {
            "type": TYPE_ROOM_CREATE_REP,
            "sessionId": session.session_id or "",
            "roomId": room_id,
            "payload": rep_payload,
        })
        await self.broadcast_room_state(room_id)

    # ═══════════════════════════════════════════════════════════════
    # ROOM_JOIN_REQ (阶段四第4步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_join_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)

        require_fields(data, ("sessionId", "roomId", "auth"))
        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        auth = self.decrypt_auth(session, data)
        if require_string_field(auth, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")
        if require_string_field(auth, "roomId") != require_string_field(data, "roomId"):
            raise GsRequestError("ROOM_MISMATCH")
        if require_string_field(auth, "type") != TYPE_ROOM_JOIN_REQ:
            raise GsRequestError("TYPE_MISMATCH")

        join_auth_nonce = require_string_field(auth, "nonce")
        data["clientId"] = session.client_id  # 使用已认证的 clientId
        await self._internal_join_room(websocket, data)

        # 返回 ROOM_JOIN_REP (nonce 回显 ROOM_JOIN_REQ 的 auth.nonce)
        room_id = require_string_field(data, "roomId")
        rep_payload = self.encrypt_payload(session, {
            "type": TYPE_ROOM_JOIN_REP,
            "ok": True,
            "sessionId": session.session_id or "",
            "roomId": room_id,
            "nonce": join_auth_nonce,
        })
        await self.send_json(websocket, {
            "type": TYPE_ROOM_JOIN_REP,
            "sessionId": session.session_id or "",
            "roomId": room_id,
            "payload": rep_payload,
        })

    async def _internal_join_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        """内部 JOIN 逻辑（被 CREATE_ROOM 和 JOIN_ROOM 共用）。"""
        requested_client_id = str(data.get("clientId", "")).strip()
        room_id = str(data.get("roomId", "")).strip()
        if not room_id:
            raise GsRequestError("MISSING_ROOM_ID")

        session = self.sessions.get(websocket)
        if session is None:
            raise GsRequestError("NO_SESSION")

        # 离开旧房间
        if session.room_id:
            old_room_id = session.room_id
            await self.remove_player_from_room_state(websocket, old_room_id)
            self.remove_from_room(websocket, old_room_id)
            session.room_id = None
            session.client_id = None

        room_state = self.get_or_create_room_state(room_id, "Client1")
        players = room_state["players"]
        room_status = str(room_state.get("status", "WAITING"))

        if requested_client_id == "CREATE_HOST":
            assigned_client_id = "Client1"
            slot_no = 1
        elif room_status == "WAITING":
            slot_no = self.allocate_slot_no(room_state, "")
            if slot_no < 0:
                raise GsRequestError("ROOM_FULL")
            assigned_client_id = f"Client{slot_no}"
        else:
            if requested_client_id in ("Client1", "Client2"):
                assigned_client_id = requested_client_id
                slot_no = 1 if assigned_client_id == "Client1" else 2
            else:
                raise GsRequestError("REJOIN_NEEDS_VALID_CLIENT_ID")

        # 替换同一 ClientId 的旧 websocket
        old_player = players.get(assigned_client_id)
        if old_player is not None:
            old_ws = old_player.get("websocket")
            if old_ws is not None and old_ws is not websocket:
                print(f"[JOIN REPLACE] room={room_id} client={assigned_client_id}")
                await self.close_and_forget_socket(old_ws, reason=f"replaced by {assigned_client_id}")

        # 清理幽灵 session
        for other_ws, other_session in list(self.sessions.items()):
            if other_ws is websocket:
                continue
            if (other_session.room_id == room_id
                    and other_session.client_id == assigned_client_id):
                print(f"[JOIN CLEAN GHOST] client={assigned_client_id}")
                await self.close_and_forget_socket(other_ws, reason=f"ghost {assigned_client_id}")

        # 清理当前 websocket 的其他 player key
        for cid in list(players.keys()):
            if players[cid].get("websocket") is websocket and cid != assigned_client_id:
                players.pop(cid, None)

        old_ready = bool(players.get(assigned_client_id, {}).get("ready", False))
        players[assigned_client_id] = {
            "clientId": assigned_client_id,
            "slotNo": slot_no,
            "ready": old_ready,
            "websocket": websocket,
        }

        if "Client1" in players:
            room_state["hostClientId"] = "Client1"
        else:
            room_state["hostClientId"] = assigned_client_id

        # 初始化 session 状态
        session.client_id = assigned_client_id
        session.room_id = room_id
        session.last_seq = -1
        session.accepted_state = "Grounded"
        session.accepted_grounded = True
        session.accepted_jump_count = 0
        session.accepted_drop = False
        session.vel_x = 0.0
        session.vel_y = 0.0
        session.damage_percent = 0.0
        session.stocks = 3
        session.is_dead = False
        session.respawn_at_tick = -1
        session.facing = 1
        session.aim_x = 1.0
        session.aim_y = 0.0
        session.last_knockback_x = 0.0
        session.last_knockback_y = 0.0
        session.last_hit_tick = -1
        session.hitstun_until_tick = -1
        session.equipped_weapon_id = "手枪"
        session.equipped_effect_ids = []
        session.attack_hold_ticks = 0
        session.last_attack_tick = -999999
        session.last_attack_weapon_id = ""

        spawn_point = SPAWN_POINTS.get(assigned_client_id, {"x": 0.0, "y": 3.0})
        session.pos_x = float(spawn_point["x"])
        session.pos_y = float(spawn_point["y"])

        self.rooms.setdefault(room_id, set()).add(websocket)
        print(
            f"[JOIN] status={room_status} assigned={assigned_client_id} "
            f"room={room_id} slot={slot_no} members={len(self.rooms.get(room_id, set()))}"
        )

        # 广播房间状态
        await self.broadcast_room_state(room_id)
        await self.broadcast_snapshot(room_id, reject_reason_by_socket={websocket: ""})

    # ═══════════════════════════════════════════════════════════════
    # ROOM_READY_REQ (阶段四第7/9步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_ready(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)
        if not session.room_id or not session.client_id:
            raise GsRequestError("NOT_IN_ROOM")

        require_fields(data, ("sessionId", "roomId", "payload"))
        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        payload = self.decrypt_payload(session, data)
        if require_string_field(payload, "type") != TYPE_ROOM_READY_REQ:
            raise GsRequestError("TYPE_MISMATCH")
        if require_string_field(payload, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")
        if require_string_field(payload, "roomId") != session.room_id:
            raise GsRequestError("ROOM_MISMATCH")
        is_ready = bool(payload.get("ready", False))
        ready_nonce = require_string_field(payload, "nonce")

        room_state = self.room_states.get(session.room_id)
        if room_state is None:
            raise GsRequestError("NO_ROOM_STATE")
        players = room_state["players"]
        if session.client_id not in players:
            raise GsRequestError("NOT_IN_ROOM")
        if room_state.get("status") != "WAITING":
            raise GsRequestError("ROOM_NOT_WAITING")

        players[session.client_id]["ready"] = is_ready
        print(f"[READY] room={session.room_id} client={session.client_id} ready={is_ready}")

        # ROOM_READY_REP (nonce 回显 ROOM_READY_REQ 的 payload.nonce)
        rep_payload = self.encrypt_payload(session, {
            "type": TYPE_ROOM_READY_REP,
            "ok": True,
            "ready": is_ready,
            "sessionId": session.session_id or "",
            "roomId": session.room_id,
            "nonce": ready_nonce,
        })
        await self.send_json(websocket, {
            "type": TYPE_ROOM_READY_REP,
            "sessionId": session.session_id or "",
            "roomId": session.room_id,
            "payload": rep_payload,
        })
        await self.broadcast_room_state(session.room_id)

    # ═══════════════════════════════════════════════════════════════
    # ROOM_START_REQ (阶段四第11步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_start_game(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)
        if not session.room_id or not session.client_id:
            raise GsRequestError("NOT_IN_ROOM")

        require_fields(data, ("sessionId", "roomId", "auth"))
        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        auth = self.decrypt_auth(session, data)
        if require_string_field(auth, "type") != TYPE_ROOM_START_REQ:
            raise GsRequestError("TYPE_MISMATCH")
        if require_string_field(auth, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")
        if require_string_field(auth, "roomId") != session.room_id:
            raise GsRequestError("ROOM_MISMATCH")

        room_state = self.room_states.get(session.room_id)
        if room_state is None:
            raise GsRequestError("NO_ROOM_STATE")
        if room_state.get("hostClientId") != session.client_id:
            raise GsRequestError("NOT_HOST")
        if room_state.get("status") != "WAITING":
            raise GsRequestError("ROOM_NOT_WAITING")

        players = list(room_state.get("players", {}).values())
        if len(players) < 2:
            raise GsRequestError("NEED_MORE_PLAYERS")
        if not all(bool(p.get("ready", False)) for p in players):
            raise GsRequestError("NOT_ALL_READY")

        room_state["status"] = "STARTING"
        print(f"[ROOM_START_REQ] room={session.room_id} host={session.client_id}")

        # 广播 ROOM_STATE (loading)
        await self.broadcast_room_state(session.room_id)
        # 广播 GAME_START
        await self.broadcast_game_start(session.room_id)

    # ═══════════════════════════════════════════════════════════════
    # LEAVE_ROOM
    # ═══════════════════════════════════════════════════════════════

    async def handle_leave_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)
        if session is None or not session.room_id:
            return
        room_id = session.room_id
        await self.remove_player_from_room_state(websocket, room_id)
        self.remove_from_room(websocket, room_id)
        session.room_id = None
        session.client_id = None
        await self.broadcast_room_state(room_id)

    async def remove_player_from_room_state(self, websocket: Any, room_id: str) -> None:
        session = self.sessions.get(websocket)
        room_state = self.room_states.get(room_id)
        if session is None or room_state is None:
            return
        client_id = session.client_id
        if client_id in room_state["players"]:
            if room_state["players"][client_id].get("websocket") is websocket:
                room_state["players"].pop(client_id, None)
        for cid in list(room_state["players"].keys()):
            if room_state["players"][cid].get("websocket") is websocket:
                room_state["players"].pop(cid, None)
        if room_state.get("hostClientId") == client_id:
            remaining_players = list(room_state["players"].values())
            if remaining_players:
                remaining_players.sort(key=lambda p: int(p["slotNo"]))
                room_state["hostClientId"] = remaining_players[0]["clientId"]
            else:
                self.room_states.pop(room_id, None)

    # ═══════════════════════════════════════════════════════════════
    # INPUT (阶段五第1步)
    # ═══════════════════════════════════════════════════════════════

