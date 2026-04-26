import asyncio
import json
import random
import string
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

import game_simulation
from game_combat import CombatRuntime
from game_config import (
    GS_JSON_PAYLOAD_TYPES,
    HOST,
    JUMP_VELOCITY,
    MAX_JUMP_COUNT,
    MOVE_SPEED,
    PORT,
    SIM_DT,
    TYPE_CHAT,
    TYPE_INPUT,
    TYPE_JOIN_ROOM,
    TYPE_LEAVE_ROOM,
    TYPE_SERVER_BROADCAST,
    TYPE_SNAPSHOT,
    TYPE_CREATE_ROOM,
    TYPE_READY,
    TYPE_START_GAME,
    TYPE_ROOM_STATE,
    TYPE_GAME_START,
    WEAPON_DB,
    KNOCKBACK_DRAG_X,
    SPAWN_POINTS,
    RESPAWN_POINTS,
    RESPAWN_DELAY_TICKS,

)
from game_models import ClientSession, InputPayload, Platform


class RelayServer:
    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port

        # websocket -> ClientSession
        self.sessions: Dict[Any, ClientSession] = {}

        # roomId -> set(websocket)
        self.rooms: Dict[str, Set[Any]] = {}

        # roomId -> lobby state
        # {
        #   "hostClientId": "Client1",
        #   "status": "lobby" | "loading" | "playing",
        #   "players": {
        #       "Client1": {
        #           "clientId": "Client1",
        #           "slotNo": 1,
        #           "ready": False,
        #           "websocket": websocket
        #       }
        #   }
        # }
        self.room_states: Dict[str, Dict[str, Any]] = {}

        self.tick: int = 0
        self.combat = CombatRuntime()

    async def run(self) -> None:
        print("=" * 72)
        print(f"[SERVER] WebSocket 游戏服务启动: ws://{self.host}:{self.port}")
        print("[SERVER] 模式: lobby + movement + projectile + melee-hitbox + attack-effects")
        print(f"[SERVER] SIM_DT={SIM_DT} MOVE_SPEED={MOVE_SPEED}")
        print("=" * 72)

        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()

    async def handle_client(self, websocket: Any) -> None:
        remote = websocket.remote_address
        self.sessions[websocket] = ClientSession()

        print(f"[CONNECT] 新连接: remote={remote} | 当前连接数={len(self.sessions)}")

        try:
            async for raw_message in websocket:
                await self.handle_message(websocket, raw_message)
        except ConnectionClosed as close_info:
            print(f"[CLOSED ] remote={remote} | code={close_info.code} | reason={close_info.reason}")
        finally:
            await self.cleanup_client(websocket, reason="disconnect")

    async def handle_message(self, websocket: Any, raw_message: str) -> None:
        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            await self.send_error(websocket, "无效 JSON：请发送合法的 JSON 字符串")
            return

        msg_type = str(data.get("type", "")).strip()

        if not msg_type:
            await self.send_error(websocket, "缺少字段 type")
            return

        if msg_type == TYPE_CREATE_ROOM:
            await self.handle_create_room(websocket, data)
            return

        if msg_type == TYPE_JOIN_ROOM:
            await self.handle_join_room(websocket, data)
            return

        if msg_type == TYPE_READY:
            await self.handle_ready(websocket, data)
            return

        if msg_type == TYPE_START_GAME:
            await self.handle_start_game(websocket, data)
            return

        if msg_type == TYPE_INPUT:
            await self.handle_input(websocket, data)
            return

        if msg_type == TYPE_CHAT:
            await self.handle_chat(websocket, data)
            return

        if msg_type == TYPE_LEAVE_ROOM:
            await self.handle_leave_room(websocket, data)
            return

        await self.send_error(websocket, f"未知消息类型: {msg_type}")

    def parse_payload_by_type(self, msg_type: str, payload_raw: Any) -> dict:
        if payload_raw in (None, ""):
            return {}

        if msg_type in GS_JSON_PAYLOAD_TYPES:
            if isinstance(payload_raw, str):
                try:
                    return json.loads(payload_raw)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"{msg_type} payload 不是合法 JSON") from exc

            if isinstance(payload_raw, dict):
                return payload_raw

            raise ValueError(f"{msg_type} payload 类型非法")

        return {}

    # ------------------------------------------------------------------
    # Lobby / room state
    # ------------------------------------------------------------------

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
                "status": "lobby",
                "players": {},
            }

        return self.room_states[room_id]

    def allocate_slot_no(self, room_state: Dict[str, Any], requested_client_id: str = "") -> int:
        """
        只负责找空位，不判断 requested_client_id。

        requested_client_id 能不能被信任，应该由 handle_join_room()
        根据 room_status 决定，而不是在这里决定。
        """
        players = room_state["players"]

        used_slots = {
            int(p["slotNo"])
            for p in players.values()
            if "slotNo" in p
        }

        if 1 not in used_slots:
            return 1

        if 2 not in used_slots:
            return 2

        return -1

    def build_room_state_payload(
        self,
        room_id: str,
        local_session: Optional[ClientSession] = None,
    ) -> dict:
        room_state = self.room_states.get(room_id)

        if room_state is None:
            return {
                "roomId": room_id,
                "hostClientId": "",
                "status": "missing",
                "players": [],
                "canStart": False,
                "localClientId": "",
                "localSlotNo": 0,
                "localIsHost": False,
            }

        players_dict = room_state.get("players", {})
        players = []

        for player in players_dict.values():
            players.append(
                {
                    "clientId": player["clientId"],
                    "slotNo": int(player["slotNo"]),
                    "ready": bool(player["ready"]),
                    "isHost": player["clientId"] == room_state.get("hostClientId", ""),
                }
            )

        players.sort(key=lambda p: p["slotNo"])

        can_start = (
            room_state.get("status") == "lobby"
            and len(players) >= 2
            and all(p["ready"] for p in players)
        )

        local_client_id = ""
        local_slot_no = 0
        local_is_host = False

        if local_session is not None and local_session.client_id:
            local_client_id = local_session.client_id
            local_is_host = local_client_id == room_state.get("hostClientId", "")

            if local_client_id in players_dict:
                local_slot_no = int(players_dict[local_client_id]["slotNo"])

        return {
            "roomId": room_id,
            "hostClientId": room_state.get("hostClientId", ""),
            "status": room_state.get("status", "lobby"),
            "players": players,
            "canStart": can_start,
            "localClientId": local_client_id,
            "localSlotNo": local_slot_no,
            "localIsHost": local_is_host,
        }

    async def broadcast_room_state(self, room_id: str) -> None:
        for peer in list(self.rooms.get(room_id, set())):
            peer_session = self.sessions.get(peer)

            if peer_session is None:
                continue

            payload_obj = self.build_room_state_payload(room_id, peer_session)

            msg = {
                "type": TYPE_ROOM_STATE,
                "roomId": room_id,
                "clientId": peer_session.client_id or "",
                "payload": json.dumps(payload_obj, ensure_ascii=False),
            }

            await self.send_json(peer, msg)

    async def broadcast_game_start(self, room_id: str) -> None:
        peers = list(self.rooms.get(room_id, set()))

        print(
            f"[BROADCAST_GAME_START] room={room_id} peers={len(peers)}"
        )

        for peer in peers:
            peer_session = self.sessions.get(peer)

            if peer_session is None:
                print("[BROADCAST_GAME_START] skip peer: no session")
                continue

            payload_obj = self.build_room_state_payload(room_id, peer_session)
            payload_obj["sceneName"] = "MainGame"

            msg = {
                "type": TYPE_GAME_START,
                "roomId": room_id,
                "clientId": peer_session.client_id or "",
                "payload": json.dumps(payload_obj, ensure_ascii=False),
            }

            print(
                f"[SEND GAME_START] room={room_id} "
                f"to={peer_session.client_id} "
                f"localClientId={payload_obj.get('localClientId')} "
                f"slot={payload_obj.get('localSlotNo')} "
                f"scene={payload_obj.get('sceneName')}"
            )

            await self.send_json(peer, msg)

    async def handle_create_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)

        if session is None:
            await self.send_error(websocket, "服务端未找到该连接的会话")
            return

        # 如果这个连接因为自动加入/旧流程已经在某个房间里，
        # 创建新房间前必须先离开旧房间。
        if session.room_id:
            old_room_id = session.room_id

            await self.remove_player_from_room_state(websocket, old_room_id)
            self.remove_from_room(websocket, old_room_id)

            session.room_id = None
            session.client_id = None

            await self.broadcast_room_state(old_room_id)

        room_id = self.generate_room_id()

        # 创建房间的人永远是新房间的房主 Client1。
        # 这里不要继续使用客户端传来的 requested_client_id。
        join_data = {
            "type": TYPE_JOIN_ROOM,
            "clientId": "CREATE_HOST",
            "roomId": room_id,
        }

        await self.handle_join_room(websocket, join_data)

        print(f"[CREATE_ROOM] creator forced host Client1 room={room_id}")

    async def handle_join_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        requested_client_id = str(data.get("clientId", "")).strip()
        room_id = str(data.get("roomId", "")).strip()

        if not room_id:
            await self.send_error(websocket, "JOIN_ROOM 缺少 roomId")
            return

        session = self.sessions.get(websocket)

        if session is None:
            await self.send_error(websocket, "服务端未找到该连接的会话")
            return

        # ------------------------------------------------------------
        # 1) 如果当前 websocket 原来已经在某个房间，先安全移除
        # ------------------------------------------------------------

        if session.room_id:
            old_room_id = session.room_id

            await self.remove_player_from_room_state(websocket, old_room_id)
            self.remove_from_room(websocket, old_room_id)

            session.room_id = None
            session.client_id = None

        # ------------------------------------------------------------
        # 2) 获取/创建房间状态
        # ------------------------------------------------------------

        room_state = self.get_or_create_room_state(
            room_id,
            "Client1"
        )

        players = room_state["players"]
        room_status = str(room_state.get("status", "lobby"))

        # ------------------------------------------------------------
        # 3) 分配身份
        #
        # CREATE_HOST:
        #   创建房间的人，强制成为 Client1。
        #
        # lobby:
        #   普通加入，服务器按空位分配，不相信客户端带来的 Client1/Client2。
        #
        # loading/playing:
        #   MainGame 重连，才相信 requested Client1/Client2。
        # ------------------------------------------------------------

        if requested_client_id == "CREATE_HOST":
            assigned_client_id = "Client1"
            slot_no = 1

        elif room_status == "lobby":
            slot_no = self.allocate_slot_no(room_state, "")

            if slot_no < 0:
                await self.send_error(websocket, f"房间 {room_id} 已满")
                return

            assigned_client_id = f"Client{slot_no}"

        else:
            if requested_client_id in ("Client1", "Client2"):
                assigned_client_id = requested_client_id
                slot_no = 1 if assigned_client_id == "Client1" else 2
            else:
                await self.send_error(
                    websocket,
                    f"房间 {room_id} 已经开始，需要携带有效 clientId 重新加入"
                )
                return

        # ------------------------------------------------------------
        # 4) 如果同一个 ClientId 已经有旧 websocket，占位替换
        # ------------------------------------------------------------

        old_player = players.get(assigned_client_id)

        if old_player is not None:
            old_ws = old_player.get("websocket")

            if old_ws is not None and old_ws is not websocket:
                print(
                    f"[JOIN REPLACE] room={room_id} status={room_status} "
                    f"client={assigned_client_id} old websocket replaced"
                )

                old_members = self.rooms.get(room_id)
                if old_members is not None:
                    old_members.discard(old_ws)

                old_session = self.sessions.get(old_ws)
                if old_session is not None:
                    old_session.room_id = None
                    old_session.client_id = None
                    old_session.last_seq = -1

        # ------------------------------------------------------------
        # 5) 保险：清掉同房间同 ClientId 的幽灵 session
        # ------------------------------------------------------------

        for other_ws, other_session in list(self.sessions.items()):
            if other_ws is websocket:
                continue

            if (
                other_session.room_id == room_id
                and other_session.client_id == assigned_client_id
            ):
                print(
                    f"[JOIN CLEAN GHOST] room={room_id} status={room_status} "
                    f"client={assigned_client_id} remove ghost session"
                )

                other_session.room_id = None
                other_session.client_id = None
                other_session.last_seq = -1

                members = self.rooms.get(room_id)
                if members is not None:
                    members.discard(other_ws)

        # ------------------------------------------------------------
        # 6) 清掉当前 websocket 曾经占用的其他 player key
        # ------------------------------------------------------------

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

        # ------------------------------------------------------------
        # 7) 房主规则
        # ------------------------------------------------------------

        if "Client1" in players:
            room_state["hostClientId"] = "Client1"
        else:
            room_state["hostClientId"] = assigned_client_id

        # ------------------------------------------------------------
        # 8) 初始化当前 session 权威状态
        # ------------------------------------------------------------

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

        # ------------------------------------------------------------
        # 9) 出生点
        # ------------------------------------------------------------

        spawn_point = SPAWN_POINTS.get(
            assigned_client_id,
            {"x": 0.0, "y": 3.0}
        )

        session.pos_x = float(spawn_point["x"])
        session.pos_y = float(spawn_point["y"])

        # ------------------------------------------------------------
        # 10) 加入 room websocket 集合
        # ------------------------------------------------------------

        self.rooms.setdefault(room_id, set()).add(websocket)

        print(
            f"[JOIN] status={room_status} requested={requested_client_id} "
            f"assigned={assigned_client_id} room={room_id} slot={slot_no} "
            f"members={len(self.rooms.get(room_id, set()))}"
        )

        # ------------------------------------------------------------
        # 11) 回 ACK + 广播房间状态和快照
        # ------------------------------------------------------------

        ack = {
            "type": TYPE_SERVER_BROADCAST,
            "roomId": room_id,
            "fromClientId": "SERVER",
            "text": f"{assigned_client_id} 已加入房间 {room_id}",
            "timestamp": self.utc_now_iso(),
        }

        await self.send_json(websocket, ack)

        await self.broadcast_room_state(room_id)
        await self.broadcast_snapshot(room_id, reject_reason_by_socket={websocket: ""})

    async def handle_ready(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)

        if session is None or not session.room_id or not session.client_id:
            await self.send_error(websocket, "请先 JOIN_ROOM，再发送 READY")
            return

        try:
            payload = self.parse_payload_by_type(TYPE_READY, data.get("payload"))
        except ValueError as exc:
            await self.send_error(websocket, str(exc))
            return

        is_ready = bool(payload.get("ready", False))

        room_state = self.room_states.get(session.room_id)

        if room_state is None:
            await self.send_error(websocket, "房间状态不存在")
            return

        players = room_state["players"]

        if session.client_id not in players:
            await self.send_error(websocket, "玩家不在房间状态中")
            return

        players[session.client_id]["ready"] = is_ready

        print(
            f"[READY] room={session.room_id} "
            f"client={session.client_id} ready={is_ready}"
        )

        await self.broadcast_room_state(session.room_id)

    async def handle_start_game(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)

        if session is None or not session.room_id or not session.client_id:
            await self.send_error(websocket, "请先 JOIN_ROOM，再发送 START_GAME")
            return

        room_state = self.room_states.get(session.room_id)

        if room_state is None:
            await self.send_error(websocket, "房间状态不存在")
            return

        if room_state.get("hostClientId") != session.client_id:
            await self.send_error(websocket, "只有房主可以开始游戏")
            return

        players = list(room_state.get("players", {}).values())

        if len(players) < 2:
            await self.send_error(websocket, "至少需要 2 名玩家才能开始")
            return

        if not all(bool(p.get("ready", False)) for p in players):
            await self.send_error(websocket, "还有玩家没有准备")
            return

        room_state["status"] = "loading"

        print(f"[START_GAME] room={session.room_id} host={session.client_id}")

        await self.broadcast_room_state(session.room_id)
        await self.broadcast_game_start(session.room_id)

    async def handle_leave_room(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)

        if session is None:
            return

        if not session.room_id:
            print("[LEAVE_ROOM] ignored: session not in room")
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

        # 兜底：按 websocket 清理
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

    # ------------------------------------------------------------------
    # Input parsing / combat
    # ------------------------------------------------------------------

    def parse_input_payload(self, cmd: dict) -> InputPayload:
        effect_ids_raw = cmd.get("equippedEffectIds", [])
        effect_ids = [str(eid) for eid in effect_ids_raw] if isinstance(effect_ids_raw, list) else []

        return InputPayload(
            seq=int(cmd.get("seq", 0)),
            tick=int(cmd.get("tick", 0)),
            move_x=max(-1.0, min(1.0, float(cmd.get("moveX", 0.0)))),

            jump_pressed=bool(cmd.get("jumpPressed", False)),
            down_held=bool(cmd.get("downHeld", False)),
            drop_pressed=bool(cmd.get("dropPressed", False)),

            attack_pressed=bool(cmd.get("attackPressed", False)),
            attack_held=bool(cmd.get("attackHeld", False)),
            attack_released=bool(cmd.get("attackReleased", False)),

            aim_x=float(cmd.get("aimX", 0.0)),
            aim_y=float(cmd.get("aimY", 0.0)),

            client_state=str(cmd.get("clientState", "Unknown")),
            client_grounded=bool(cmd.get("clientGrounded", False)),
            client_jump_count=int(cmd.get("clientJumpCount", 0)),
            client_pos_x=float(cmd.get("clientPosX", 0.0)),
            client_pos_y=float(cmd.get("clientPosY", 0.0)),
            client_vel_x=float(cmd.get("clientVelX", 0.0)),
            client_vel_y=float(cmd.get("clientVelY", 0.0)),

            equipped_weapon_id=str(cmd.get("equippedWeaponId", "手枪")),
            equipped_effect_ids=effect_ids,
        )

    def should_execute_attack(self, session: ClientSession, cmd: InputPayload) -> bool:
        """
        服务器权威攻击节流。

        - attack_pressed：刚按下，尝试立刻攻击。
        - attack_held：按住期间，如果武器允许 auto_fire，则按 fire_interval_ticks 连续攻击。
        - melee 默认不 auto_fire，除非 WEAPON_DB 特意开启。
        """
        if session is None or session.client_id is None or session.is_dead:
            return False

        weapon_id = session.equipped_weapon_id
        weapon_cfg = WEAPON_DB.get(weapon_id)

        if weapon_cfg is None:
            print(f"[SERVER ATTACK WARN] weapon_id={weapon_id} not found, fallback=手枪")
            weapon_cfg = WEAPON_DB.get("手枪", {})

        attack_mode = weapon_cfg.get("attack_mode", "ranged")
        auto_fire = bool(weapon_cfg.get("auto_fire", attack_mode == "ranged"))
        fire_interval_ticks = int(weapon_cfg.get("fire_interval_ticks", 10))

        wants_attack = False

        if cmd.attack_pressed:
            wants_attack = True
        elif cmd.attack_held and auto_fire:
            wants_attack = True

        if not wants_attack:
            return False

        if session.last_attack_weapon_id != weapon_id:
            session.last_attack_weapon_id = weapon_id
            session.last_attack_tick = -999999

        elapsed = self.tick - session.last_attack_tick

        if elapsed < fire_interval_ticks:
            return False

        session.last_attack_tick = self.tick

        print(
            f"[SERVER ATTACK ALLOWED] "
            f"client={session.client_id} "
            f"weapon={weapon_id} "
            f"pressed={cmd.attack_pressed} "
            f"held={cmd.attack_held} "
            f"interval={fire_interval_ticks} "
            f"elapsed={elapsed}"
        )

        return True
    
    async def handle_input(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)

        if session is None or not session.room_id or not session.client_id:
            await self.send_error(websocket, "请先 JOIN_ROOM，再发送 INPUT")
            return

        try:
            cmd_dict = self.parse_payload_by_type(TYPE_INPUT, data.get("payload"))
        except ValueError as exc:
            await self.send_error(websocket, str(exc))
            return

        if not cmd_dict:
            await self.send_error(websocket, "INPUT 缺少 payload")
            return

        cmd = self.parse_input_payload(cmd_dict)

        session.last_seq = cmd.seq
        session.accepted_drop = False
        reject_reason = ""

        # ------------------------------------------------------------
        # 0) 如果玩家正在等待复活
        # ------------------------------------------------------------

        if session.is_dead and getattr(session, "respawn_at_tick", -1) > 0:
            # 死亡等待期间，不吃输入，不移动，不攻击。
            session.vel_x = 0.0
            session.vel_y = 0.0
            session.accepted_grounded = False
            session.accepted_state = "Dead"

            # 倒计时到了才复活
            if self.tick >= session.respawn_at_tick and session.stocks > 0:
                respawn_point = RESPAWN_POINTS.get(
                    session.client_id,
                    {"x": 0.0, "y": 3.0}
                )

                session.pos_x = float(respawn_point["x"])
                session.pos_y = float(respawn_point["y"])

                session.vel_x = 0.0
                session.vel_y = 0.0

                session.damage_percent = 0.0
                session.is_dead = False
                session.respawn_at_tick = -1

                session.accepted_grounded = True
                session.accepted_jump_count = 0
                session.accepted_drop = False
                session.accepted_state = "Grounded"

                session.last_knockback_x = 0.0
                session.last_knockback_y = 0.0
                session.last_hit_tick = -1
                session.hitstun_until_tick = -1

                self.combat.push_event(
                    "PLAYER_RESPAWN",
                    {
                        "clientId": session.client_id,
                        "x": session.pos_x,
                        "y": session.pos_y,
                    },
                )

                print(
                    f"[RESPAWN] client={session.client_id} "
                    f"pos=({session.pos_x:.2f},{session.pos_y:.2f}) "
                    f"stocks={session.stocks}"
                )

            # 死亡等待期间，世界上的子弹/近战还是继续模拟
            self.combat.step_projectiles(self.sessions, self.tick)
            self.combat.step_melee_hitboxes(self.sessions, self.tick)

            self.tick += 1

            await self.broadcast_snapshot(
                session.room_id,
                reject_reason_by_socket={websocket: reject_reason},
            )

            self.combat.clear_events()
            return

        # ------------------------------------------------------------
        # 1) 同步客户端携带的当前武器 / 效果 / 瞄准方向
        # ------------------------------------------------------------

        if cmd.equipped_weapon_id:
            session.equipped_weapon_id = cmd.equipped_weapon_id

        session.equipped_effect_ids = list(cmd.equipped_effect_ids)

        session.aim_x = cmd.aim_x
        session.aim_y = cmd.aim_y

        if abs(cmd.aim_x) > 0.001:
            session.facing = 1 if cmd.aim_x > 0 else -1
        elif abs(cmd.move_x) > 0.001:
            session.facing = 1 if cmd.move_x > 0 else -1

        # ------------------------------------------------------------
        # 2) 判断是否正在受击硬直
        # ------------------------------------------------------------

        in_hitstun = getattr(session, "hitstun_until_tick", -1) > self.tick

        if in_hitstun:
            session.accepted_state = "Hitstun"
            session.accepted_grounded = False

        # ------------------------------------------------------------
        # 3) 水平移动 / 横向击退
        # ------------------------------------------------------------

        if in_hitstun:
            next_x = session.pos_x + session.vel_x * SIM_DT

            if not self.hits_wall(next_x, session.pos_y):
                session.pos_x = next_x
            else:
                session.vel_x = 0.0
                reject_reason = "击退撞墙阻挡"

            session.vel_x *= KNOCKBACK_DRAG_X

            if abs(session.vel_x) < 0.03:
                session.vel_x = 0.0

        else:
            session.vel_x = cmd.move_x * MOVE_SPEED
            next_x = session.pos_x + session.vel_x * SIM_DT

            if not self.hits_wall(next_x, session.pos_y):
                session.pos_x = next_x
            else:
                session.vel_x = 0.0
                reject_reason = "撞墙阻挡"

        # ------------------------------------------------------------
        # 4) grounded refresh
        # ------------------------------------------------------------

        standing_platform = self.get_standing_platform(session)

        if standing_platform is not None and session.vel_y <= 0 and not in_hitstun:
            session.accepted_grounded = True
            session.pos_y = standing_platform.y
            session.vel_y = 0.0

            if session.accepted_state not in ("Dash", "BasicAttack", "Hitstun"):
                session.accepted_state = "Grounded"

            session.accepted_jump_count = 0
        else:
            session.accepted_grounded = False

            if session.accepted_state == "Grounded":
                session.accepted_state = cmd.client_state or "Airborne"

        # ------------------------------------------------------------
        # 5) 下穿平台 / 跳跃
        # ------------------------------------------------------------

        current_platform = self.get_standing_platform(session)

        if not in_hitstun and cmd.drop_pressed and cmd.down_held:
            if current_platform is not None and current_platform.kind == "oneway":
                session.accepted_drop = True
                session.accepted_grounded = False
                session.accepted_state = "Fall"
                session.vel_y = min(session.vel_y, -2.0)
                session.pos_y -= 0.15
            else:
                reject_reason = "当前不在可下落的单向平台上"

        elif not in_hitstun and cmd.jump_pressed:
            if session.accepted_grounded:
                session.accepted_grounded = False
                session.accepted_jump_count = 1
                session.accepted_state = "Jump"
                session.vel_y = JUMP_VELOCITY

            elif session.accepted_jump_count < MAX_JUMP_COUNT:
                session.accepted_jump_count += 1
                session.accepted_state = "Jump"
                session.vel_y = JUMP_VELOCITY

            else:
                reject_reason = "超过最大跳跃次数"

        # ------------------------------------------------------------
        # 6) attack hold tracking
        # ------------------------------------------------------------

        if in_hitstun:
            session.attack_hold_ticks = 0
        else:
            if cmd.attack_held:
                session.attack_hold_ticks += 1
            else:
                session.attack_hold_ticks = 0

        # ------------------------------------------------------------
        # 7) attack execute
        # ------------------------------------------------------------

        if not in_hitstun and self.should_execute_attack(session, cmd):
            self.combat.execute_attack(
                attacker=session,
                aim_x=cmd.aim_x,
                aim_y=cmd.aim_y,
                tick=self.tick,
                sessions=self.sessions,
            )

        # ------------------------------------------------------------
        # 8) vertical movement
        # ------------------------------------------------------------

        self.step_vertical(session)

        if in_hitstun and getattr(session, "hitstun_until_tick", -1) <= self.tick + 1:
            if session.accepted_grounded:
                session.accepted_state = "Grounded"
            else:
                session.accepted_state = "Fall"

        # ------------------------------------------------------------
        # 9) projectile / melee simulation
        # ------------------------------------------------------------

        self.combat.step_projectiles(self.sessions, self.tick)
        self.combat.step_melee_hitboxes(self.sessions, self.tick)

        # ------------------------------------------------------------
        # 10) blast zone / stock handling
        # ------------------------------------------------------------

        if game_simulation.is_out_of_bounds(session.pos_x, session.pos_y):
            # 避免同一条命在等待复活期间重复扣命
            if not session.is_dead:
                session.stocks -= 1

                self.combat.push_event(
                    "PLAYER_OUT_OF_BOUNDS",
                    {
                        "clientId": session.client_id,
                        "stocksLeft": session.stocks,
                    },
                )

                if session.stocks <= 0:
                    session.is_dead = True
                    session.respawn_at_tick = -1
                    session.accepted_state = "Dead"
                    session.vel_x = 0.0
                    session.vel_y = 0.0

                    print(
                        f"[PLAYER DEAD FINAL] client={session.client_id} "
                        f"stocks={session.stocks}"
                    )

                else:
                    # 进入死亡等待状态，延迟复活
                    session.is_dead = True
                    session.respawn_at_tick = self.tick + RESPAWN_DELAY_TICKS

                    session.accepted_state = "Dead"
                    session.accepted_grounded = False
                    session.accepted_jump_count = 0
                    session.accepted_drop = False

                    session.vel_x = 0.0
                    session.vel_y = 0.0

                    session.last_knockback_x = 0.0
                    session.last_knockback_y = 0.0
                    session.last_hit_tick = -1
                    session.hitstun_until_tick = -1

                    print(
                        f"[PLAYER OUT] client={session.client_id} "
                        f"stocksLeft={session.stocks} "
                        f"respawnAt={session.respawn_at_tick} "
                        f"delayTicks={RESPAWN_DELAY_TICKS}"
                    )

        # ------------------------------------------------------------
        # 11) tick + snapshot
        # ------------------------------------------------------------

        self.tick += 1

        print(
            f"[INPUT] client={session.client_id} seq={cmd.seq} "
            f"inputX={cmd.move_x:.2f} velX={session.vel_x:.2f} "
            f"attackPressed={cmd.attack_pressed} attackHeld={cmd.attack_held} attackReleased={cmd.attack_released} "
            f"weapon={session.equipped_weapon_id} effects={session.equipped_effect_ids} "
            f"inHitstun={in_hitstun} hitstunUntil={getattr(session, 'hitstun_until_tick', -1)} "
            f"state={session.accepted_state} grounded={session.accepted_grounded} "
            f"jumpCount={session.accepted_jump_count} drop={session.accepted_drop} "
            f"stocks={session.stocks} dead={session.is_dead} respawnAt={getattr(session, 'respawn_at_tick', -1)} "
            f"pos=({session.pos_x:.2f},{session.pos_y:.2f}) "
            f"vel=({session.vel_x:.2f},{session.vel_y:.2f}) reject={reject_reason} "
            f"deltaX={(cmd.client_pos_x - session.pos_x):.3f}"
        )

        await self.broadcast_snapshot(
            session.room_id,
            reject_reason_by_socket={websocket: reject_reason},
        )

        self.combat.clear_events()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def build_snapshot_payload(self, session: ClientSession, reject_reason: str) -> dict:
        players = []

        for s in self.sessions.values():
            if s.room_id != session.room_id or s.client_id is None:
                continue

            players.append(
                {
                    "slotNo": 1 if s.client_id == "Client1" else 2,
                    "userId": 0,
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

        events = []

        for e in self.combat.pending_events:
            events.append(
                {
                    "eventType": e.event_type,
                    "eventSeq": e.event_seq,
                    "data": e.data,
                }
            )

        return {
            "tick": self.tick,
            "lastProcessedSeq": session.last_seq,
            "rejectReason": reject_reason,
            "players": players,
            "projectiles": projectiles,
            "events": events,
        }

    async def send_snapshot(self, websocket: Any, session: ClientSession, reject_reason: str) -> None:
        snapshot = self.build_snapshot_payload(session, reject_reason)

        response = {
            "type": TYPE_SNAPSHOT,
            "roomId": session.room_id,
            "clientId": session.client_id,
            "payload": json.dumps(snapshot, ensure_ascii=False),
        }

        await self.send_json(websocket, response)

    async def broadcast_snapshot(
        self,
        room_id: str,
        reject_reason_by_socket: Optional[Dict[Any, str]] = None,
    ) -> None:
        peers = list(self.rooms.get(room_id, set()))

        for peer in peers:
            session = self.sessions.get(peer)

            if session is None or session.room_id != room_id or session.client_id is None:
                continue

            reject_reason = ""

            if reject_reason_by_socket is not None:
                reject_reason = reject_reason_by_socket.get(peer, "")

            await self.send_snapshot(peer, session, reject_reason)

    # ------------------------------------------------------------------
    # Chat / cleanup / utils
    # ------------------------------------------------------------------

    async def handle_chat(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self.sessions.get(websocket)

        if session is None or not session.room_id or not session.client_id:
            await self.send_error(websocket, "请先 JOIN_ROOM，再发送 CHAT")
            return

        try:
            chat_obj = self.parse_payload_by_type(TYPE_CHAT, data.get("payload"))
        except ValueError as exc:
            await self.send_error(websocket, str(exc))
            return

        text = str(chat_obj.get("text", "")).strip()

        if not text:
            await self.send_error(websocket, "CHAT 缺少 text")
            return

        payload = {
            "type": TYPE_SERVER_BROADCAST,
            "roomId": session.room_id,
            "fromClientId": session.client_id,
            "text": text,
            "timestamp": self.utc_now_iso(),
        }

        for peer in self.rooms.get(session.room_id, set()):
            if peer is not websocket:
                await self.send_json(peer, payload)

    async def cleanup_client(self, websocket: Any, reason: str) -> None:
        session = self.sessions.get(websocket)

        if session is None:
            return

        room_id = session.room_id
        client_id = session.client_id

        if room_id:
            await self.remove_player_from_room_state(websocket, room_id)
            self.remove_from_room(websocket, room_id)

            print(f"[LEAVE] client={client_id} room={room_id} reason={reason}")

            await self.broadcast_room_state(room_id)
            await self.broadcast_snapshot(room_id)

        self.sessions.pop(websocket, None)

    def remove_from_room(self, websocket: Any, room_id: str) -> None:
        members = self.rooms.get(room_id)

        if not members:
            return

        members.discard(websocket)

        if not members:
            self.rooms.pop(room_id, None)

    async def send_error(self, websocket: Any, error_message: str) -> None:
        await self.send_json(
            websocket,
            {
                "type": "ERROR",
                "error": error_message,
            },
        )

    async def send_json(self, websocket: Any, payload: Dict[str, Any]) -> None:
        try:
            await websocket.send(json.dumps(payload, ensure_ascii=False))
        except ConnectionClosed:
            pass

    def hits_wall(self, x: float, y: float) -> bool:
        return game_simulation.hits_wall(x, y)

    def step_vertical(self, session: ClientSession) -> None:
        game_simulation.step_vertical(session)

    def get_standing_platform(self, session: ClientSession) -> Optional[Platform]:
        return game_simulation.get_standing_platform(session)

    def is_on_platform(self, x: float, y: float, platform: Platform) -> bool:
        return game_simulation.is_on_platform(x, y, platform)

    def find_landing_platform(self, x: float, previous_y: float, next_y: float) -> Optional[Platform]:
        return game_simulation.find_landing_platform(x, previous_y, next_y)

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()