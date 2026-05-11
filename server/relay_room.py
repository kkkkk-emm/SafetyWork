"""GS 房间生命周期 Mixin。

房间状态机：
    WAITING → (房主发起+>=2人+全员ready) → STARTING → (首个INPUT到达) → PLAYING → (仅剩≤1人存活) → FINISHED

slot 分配规则：最多 2 人，Client1=slot1（房主），Client2=slot2（加入者）。
hostClientId 始终指向 Client1，房主离开时顺延给剩余玩家。
"""

from __future__ import annotations

import secrets
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
from relay_contracts import RelayServerContext

class RoomLifecycleMixin:
    """处理 RoomLifecycleMixin 相关的房间生命周期逻辑。"""
    def generate_room_id(self: RelayServerContext) -> str:
        """生成 4 位随机房间 ID（大写字母+数字）
        使用 secrets.choice 确保密码学安全的随机性，防止预测房间 ID 导致的未授权加入。
        """
        alphabet = string.ascii_uppercase + string.digits
        room_id = "".join(secrets.choice(alphabet) for _ in range(4))
        while room_id in self.room_states:
            room_id = "".join(secrets.choice(alphabet) for _ in range(4))
        return room_id

    def get_or_create_room_state(
        self: RelayServerContext, room_id: str, host_client_id: str
    ) -> Dict[str, Any]:
        """处理 RoomLifecycleMixin.get_or_create_room_state 相关的房间生命周期逻辑。"""
        if room_id not in self.room_states:
            # 房间状态只保存最小必要字段，玩家详情在 JOIN 时再补齐。
            self.room_states[room_id] = {
                "hostClientId": host_client_id,
                "status": "WAITING",
                "players": {},
            }
        return self.room_states[room_id]

    def allocate_slot_no(
        self: RelayServerContext, room_state: Dict[str, Any], _requested: str = ""
    ) -> int:
        """在 WAITING 状态分配空闲 slot（1 或 2），先到先得。满员返回 -1。

        不在 WAITING 状态时（重连等场景）走 _internal_join_room 的独立分支。
        """
        players = room_state["players"]
        used_slots = {int(p["slotNo"]) for p in players.values() if "slotNo" in p}
        if 1 not in used_slots:
            return 1
        if 2 not in used_slots:
            return 2
        return -1

    def build_room_state_payload(
        self: RelayServerContext,
        room_id: str,
        local_session: Optional[ClientSession] = None,  # 当前接收客户端 session，用于填入 local* 字段
    ) -> dict:
        """构建 ROOM_STATE 广播的原始 payload（不含加密/type 包装）。

        每个客户端收到的是个性化 payload：localClientId / localSlotNo / localIsHost 不同。
        canStart 条件：WAITING + 人数>=2 + 全员ready。
        players 列表按 slotNo 升序排列。
        """
        room_state = self.room_states.get(room_id)
        if room_state is None:
            return {
                "roomId": room_id,
                "hostClientId": "",
                "state": "missing",
                "ownerUserId": 0,
                "players": [],
                "canStart": False,
                "localClientId": "",
                "localSlotNo": 0,
                "localIsHost": False,
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
            players.append(
                {
                    "userId": player_user_id,
                    "username": player_username,
                    "clientId": cid,
                    "slotNo": int(player["slotNo"]),
                    "ready": bool(player["ready"]),
                    "isHost": cid == host_client_id,
                    "online": bool(player.get("online", True)),
                }
            )
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

    async def broadcast_room_state(self: RelayServerContext, room_id: str) -> None:
        """广播 ROOM_STATE 给房间内所有已认证的在线成员。

        每个客户端使用各自的 KcGs 加密 payload（不可共享加密结果），
        所以必须逐个构造、加密、发送。
        在以下时机触发：创建房间、加入房间、准备状态变更、离开房间、断线重连。
        """
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

    async def broadcast_game_start(self: RelayServerContext, room_id: str) -> None:
        """处理 RoomLifecycleMixin.broadcast_game_start 相关的房间生命周期逻辑。"""
        match_id = f"match-{100 + secrets.randbelow(900)}"
        peers = list(self.rooms.get(room_id, set()))
        print(
            f"[BROADCAST_GAME_START] room={room_id} matchId={match_id} peers={len(peers)}"
        )
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
    # 流程：先自动离开旧房间 → 生成新 roomId → 内部 JOIN 为 Client1（房主） → 返回 ROOM_CREATE_REP → 广播 ROOM_STATE
    # ═══════════════════════════════════════════════════════════════

    async def handle_create_room(
        self: RelayServerContext, websocket: Any, data: Dict[str, Any]
    ) -> None:
        """处理 RoomLifecycleMixin.handle_create_room 相关的房间生命周期逻辑。"""
        session = self._require_session(websocket)

        # 解密并校验 auth
        require_fields(data, ("sessionId", "auth"))
        auth = self.decrypt_auth(session, data)
        if require_string_field(auth, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        # 一个 session 只能在一个房间，先退出旧房间
        if session.room_id:
            old_room_id = session.room_id
            await self.remove_player_from_room_state(websocket, old_room_id)
            self.remove_from_room(websocket, old_room_id)
            session.room_id = None
            session.client_id = None
            await self.broadcast_room_state(old_room_id)

        room_id = self.generate_room_id()
        # 房主自动以 Client1 身份加入，共用 _internal_join_room 逻辑
        join_data = {
            "type": TYPE_ROOM_JOIN_REQ,
            "clientId": "CREATE_HOST",
            "roomId": room_id,
        }
        await self._internal_join_room(websocket, join_data)
        print(f"[ROOM_CREATE_REQ] creator=Client1 room={room_id}")

        # 返回 ROOM_CREATE_REP
        rep_payload = self.encrypt_payload(
            session,
            {
                "type": TYPE_ROOM_CREATE_REP,
                "ok": True,
                "sessionId": session.session_id or "",
                "roomId": room_id,
            },
        )
        await self.send_json(
            websocket,
            {
                "type": TYPE_ROOM_CREATE_REP,
                "sessionId": session.session_id or "",
                "roomId": room_id,
                "payload": rep_payload,
            },
        )
        await self.broadcast_room_state(room_id)

    # ═══════════════════════════════════════════════════════════════
    # ROOM_JOIN_REQ (阶段四第4步)
    # 流程：auth 双重校验（sessionId + roomId 必须一致）→ 内部 JOIN 分配 slot → 返回 ROOM_JOIN_REP（nonce 回显） → 广播 ROOM_STATE
    # 安全：auth 内的 roomId 必须与顶层 roomId 一致，防止客户端用不同房间的 auth 跨房间加入
    # ═══════════════════════════════════════════════════════════════

    async def handle_join_room(
    self: RelayServerContext, websocket: Any, data: Dict[str, Any]
) -> None:
        """处理 ROOM_JOIN_REQ：只能加入服务器内存中已经存在的指定房间。"""
        session = self._require_session(websocket)

        require_fields(data, ("sessionId", "roomId", "auth"))

        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        # 顶层 roomId：客户端输入的目标房间号
        room_id = require_string_field(data, "roomId").strip().upper()

        if not room_id:
            raise GsRequestError("ROOM_ID_REQUIRED")

        # 规范化，后续 _internal_join_room 也使用这个 roomId
        data["roomId"] = room_id

        auth = self.decrypt_auth(session, data)

        if require_string_field(auth, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        auth_room_id = require_string_field(auth, "roomId").strip().upper()

        # 安全：auth 内 roomId 必须与顶层一致
        if auth_room_id != room_id:
            raise GsRequestError("ROOM_MISMATCH")

        if require_string_field(auth, "type") != TYPE_ROOM_JOIN_REQ:
            raise GsRequestError("TYPE_MISMATCH")

        # ============================================================
        # 关键新增：
        # 手动加入指定房间时，房间必须已经存在于服务器内存。
        # 不允许 _internal_join_room 通过 get_or_create_room_state 自动创建。
        # ============================================================
        if room_id not in self.rooms or room_id not in self.room_states:
            print(
                f"[JOIN REJECT] ROOM_NOT_FOUND "
                f"room={room_id} "
                f"client={session.client_id} "
                f"sessionId={session.session_id}"
            )
            raise GsRequestError("ROOM_NOT_FOUND")

        room_state = self.room_states.get(room_id)
        members = self.rooms.get(room_id)

        if room_state is None or members is None:
            print(
                f"[JOIN REJECT] ROOM_NOT_FOUND incomplete state "
                f"room={room_id}"
            )
            raise GsRequestError("ROOM_NOT_FOUND")

        status = str(room_state.get("status", "WAITING")).upper()

        # 已经开始/结算的房间不允许普通 JOIN
        if status != "WAITING":
            print(
                f"[JOIN REJECT] ROOM_NOT_JOINABLE "
                f"room={room_id} status={status}"
            )
            raise GsRequestError("ROOM_NOT_JOINABLE")

        # 你的规则是最多 2 人
        if len(members) >= 2:
            print(f"[JOIN REJECT] ROOM_FULL room={room_id}")
            raise GsRequestError("ROOM_FULL")

        join_auth_nonce = require_string_field(auth, "nonce")

        # 使用已认证 session 的 clientId，不相信客户端上传的 clientId
        data["clientId"] = session.client_id

        await self._internal_join_room(websocket, data)

        # 返回 ROOM_JOIN_REP
        rep_payload = self.encrypt_payload(
            session,
            {
                "type": TYPE_ROOM_JOIN_REP,
                "ok": True,
                "sessionId": session.session_id or "",
                "roomId": room_id,
                "nonce": join_auth_nonce,
            },
        )

        await self.send_json(
            websocket,
            {
                "type": TYPE_ROOM_JOIN_REP,
                "sessionId": session.session_id or "",
                "roomId": room_id,
                "payload": rep_payload,
            },
        )

    async def _internal_join_room(
        self: RelayServerContext, websocket: Any, data: Dict[str, Any]
    ) -> None:
        """内部 JOIN 逻辑（被 CREATE_ROOM 和 JOIN_ROOM 共用）。

        核心流程：
        1. 退出旧房间（如有）
        2. 创建或获取房间状态（首次创建时 host=Client1）
        3. 分配 slot/ClientId：
           - CREATE_HOST → Client1, slot=1（房主）
           - WAITING 状态 → 分配空闲 slot（1 或 2），满员返回 ROOM_FULL
           - 非 WAITING 状态（重连） → 必须明确指定 Client1 或 Client2
        4. 清理旧 websocket/幽灵 session（同一 ClientId 的旧连接被踢出）
        5. 初始化 session 的游戏状态（位置、命数、武器等）
        6. 广播房间状态 + 快照
        """
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

        # JOIN 不存在的房间直接拒绝，防止用 JOIN 变相创建房间
        is_create_host = requested_client_id == "CREATE_HOST"
        if not is_create_host and room_id not in self.room_states:
            raise GsRequestError("ROOM_NOT_FOUND")

        room_state = self.get_or_create_room_state(room_id, "Client1")
        players = room_state["players"]
        room_status = str(room_state.get("status", "WAITING"))

        # ClientId 是客户端协议里的玩家身份，slotNo 是房间座位；两者在 1v1 中固定对应。
        # ── ClientId 分配策略 ──
        if requested_client_id == "CREATE_HOST":
            # 房主创建房间 → 固定 Client1, slot=1
            assigned_client_id = "Client1"
            slot_no = 1
        elif room_status == "WAITING":
            # WAITING 状态 → 自动分配空闲 slot（先到先得）
            slot_no = self.allocate_slot_no(room_state, "")
            if slot_no < 0:
                raise GsRequestError("ROOM_FULL")
            assigned_client_id = f"Client{slot_no}"
        else:
            # 非 WAITING 状态（重连/STARTING/PLAYING）→ 必须明确指定 Client1 或 Client2
            if requested_client_id in ("Client1", "Client2"):
                assigned_client_id = requested_client_id
                slot_no = 1 if assigned_client_id == "Client1" else 2
            else:
                raise GsRequestError("REJOIN_NEEDS_VALID_CLIENT_ID")

        # 同一 ClientId 只能有一个活跃 websocket——旧连接被踢出（reason="replaced"）
        old_player = players.get(assigned_client_id)
        if old_player is not None:
            old_ws = old_player.get("websocket")
            if old_ws is not None and old_ws is not websocket:
                # 新连接占用同一个 ClientId 时，旧连接必须先踢下线以保持房间状态唯一。
                print(f"[JOIN REPLACE] room={room_id} client={assigned_client_id}")
                await self.close_and_forget_socket(
                    old_ws, reason=f"replaced by {assigned_client_id}"
                )

        # 防御：清理同一 room+clientId 的幽灵 session（异常断线遗留的旧连接）
        for other_ws, other_session in list(self.sessions.items()):
            if other_ws is websocket:
                continue
            if (
                other_session.room_id == room_id
                and other_session.client_id == assigned_client_id
            ):
                print(f"[JOIN CLEAN GHOST] client={assigned_client_id}")
                await self.close_and_forget_socket(
                    other_ws, reason=f"ghost {assigned_client_id}"
                )

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
    # 流程：payload 解密校验 → 状态检查（WAITING） → 设置 ready 标记 → 返回 ROOM_READY_REP（nonce 回显） → 广播 ROOM_STATE
    # 注意：仅在 WAITING 状态可切换准备，STARTING/PLAYING 后拒绝
    # ═══════════════════════════════════════════════════════════════

    async def handle_ready(
        self: RelayServerContext, websocket: Any, data: Dict[str, Any]
    ) -> None:
        """处理 RoomLifecycleMixin.handle_ready 相关的房间生命周期逻辑。"""
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
        print(
            f"[READY] room={session.room_id} client={session.client_id} ready={is_ready}"
        )

        # ROOM_READY_REP (nonce 回显 ROOM_READY_REQ 的 payload.nonce)
        rep_payload = self.encrypt_payload(
            session,
            {
                "type": TYPE_ROOM_READY_REP,
                "ok": True,
                "ready": is_ready,
                "sessionId": session.session_id or "",
                "roomId": session.room_id,
                "nonce": ready_nonce,
            },
        )
        await self.send_json(
            websocket,
            {
                "type": TYPE_ROOM_READY_REP,
                "sessionId": session.session_id or "",
                "roomId": session.room_id,
                "payload": rep_payload,
            },
        )
        await self.broadcast_room_state(session.room_id)

    # ═══════════════════════════════════════════════════════════════
    # ROOM_START_REQ (阶段四第11步)
    # 流程：auth 校验 → 房主权限检查 → WAITING 状态检查 → 人数+ready 检查 → 状态切换 WAITING→STARTING → 广播 ROOM_STATE + GAME_START
    # 状态机：WAITING → STARTING（此后首个 INPUT 会将房间切换为 PLAYING）
    # 权限：仅房主（hostClientId == session.client_id）可发起
    # ═══════════════════════════════════════════════════════════════

    async def handle_start_game(
        self: RelayServerContext, websocket: Any, data: Dict[str, Any]
    ) -> None:
        """处理 RoomLifecycleMixin.handle_start_game 相关的房间生命周期逻辑。"""
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
            raise GsRequestError("NOT_HOST")  # 只有房主能开始游戏
        if room_state.get("status") != "WAITING":
            raise GsRequestError("ROOM_NOT_WAITING")  # 已经开始或已结束

        # 开局前要求双人到齐且全部 ready，避免客户端单方面跳过大厅状态。
        players = list(room_state.get("players", {}).values())
        if len(players) < 2:
            raise GsRequestError("NEED_MORE_PLAYERS")
        if not all(bool(p.get("ready", False)) for p in players):
            raise GsRequestError("NOT_ALL_READY")

        # WAITING → STARTING 状态切换，真正的 PLAYING 在首个 INPUT 到达时触发
        room_state["status"] = "STARTING"
        print(f"[ROOM_START_REQ] room={session.room_id} host={session.client_id}")

        # 广播 ROOM_STATE (loading)
        await self.broadcast_room_state(session.room_id)
        # 广播 GAME_START
        await self.broadcast_game_start(session.room_id)

    # ═══════════════════════════════════════════════════════════════
    # LEAVE_ROOM — 主动离开房间
    # 房主离开时 hostClientId 顺延给剩余的 slot 最小的玩家，无人则删除房间
    # ═══════════════════════════════════════════════════════════════

    async def handle_leave_room(
        self: RelayServerContext, websocket: Any, data: Dict[str, Any]
    ) -> None:
        """处理 RoomLifecycleMixin.handle_leave_room 相关的房间生命周期逻辑。"""
        session = self.sessions.get(websocket)
        if session is None or not session.room_id:
            return
        room_id = session.room_id
        await self.remove_player_from_room_state(websocket, room_id)
        self.remove_from_room(websocket, room_id)

        room_empty = room_id not in self.rooms or not self.rooms.get(room_id)

        if room_empty:
            self.cleanup_room_runtime_state(room_id)

        session.room_id = None
        session.client_id = None

        await self.broadcast_room_state(room_id)

    async def remove_player_from_room_state(
        self: RelayServerContext, websocket: Any, room_id: str
    ) -> None:
        """从房间状态中移除玩家，处理 host 顺延和空房间清理。"""
        session = self.sessions.get(websocket)
        room_state = self.room_states.get(room_id)
        if session is None or room_state is None:
            return
        client_id = session.client_id
        if client_id in room_state["players"]:
            if room_state["players"][client_id].get("websocket") is websocket:
                room_state["players"].pop(client_id, None)
        # 防御：清理该 websocket 可能挂载的其他 clientId（异常状态残留）
        for cid in list(room_state["players"].keys()):
            if room_state["players"][cid].get("websocket") is websocket:
                room_state["players"].pop(cid, None)
        # 房主离开时 host 顺延给剩余 slot 最小的玩家
        if room_state.get("hostClientId") == client_id:
            remaining_players = list(room_state["players"].values())
            if remaining_players:
                remaining_players.sort(key=lambda p: int(p["slotNo"]))
                room_state["hostClientId"] = remaining_players[0]["clientId"]
        # 不管谁离开，只要 players 空了就删除房间（防止幽灵房间残留）
        if not room_state["players"]:
            self.room_states.pop(room_id, None)
