"""GS 游戏服务器 — 含 Kerberos 认证门禁、KcGs 加密、session 管理。

协议流程:
1. 客户端必须先发 GS_AUTH (携带 ServiceTicket + KcGs 加密的 auth)
2. GS 用 K_GS 解密 ServiceTicket，提取 KcGs，校验 login_gen / status
3. GS 返回 GS_AUTH_OK (含 sessionId + KcGs 加密的 payload)
4. 之后所有房间/对战消息的 payload/auth 均用 KcGs 加密
"""

import asyncio
import json
import math
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

import game_simulation
from game_combat import CombatRuntime
from game_config import (
    JUMP_VELOCITY,
    MAX_JUMP_COUNT,
    MOVE_SPEED,
    RECONNECT_GRACE_SECONDS,
    SIM_DT,
    TYPE_LEAVE_ROOM,
    WEAPON_DB,
    KNOCKBACK_DRAG_X,
    RESPAWN_POINTS,
    RESPAWN_DELAY_TICKS,
)
from game_models import ClientSession, InputPayload, Platform, ServerLoot
from crypto_utils import (
    DES_KEY_BYTES,
    b64decode,
    des_encrypt_object,
    generate_nonce,
    now_ms,
)
from gs_protocol import (
    TYPE_GS_AUTH,
    TYPE_GS_AUTH_OK,
    TYPE_HEARTBEAT_REQ,
    TYPE_HEARTBEAT_REP,
    TYPE_INPUT,
    TYPE_RECONNECT_REQ,
    TYPE_RECONNECT_REP,
    TYPE_ROOM_CREATE_REQ,
    TYPE_ROOM_JOIN_REQ,
    TYPE_ROOM_READY_REQ,
    TYPE_ROOM_START_REQ,
    make_message,
    require_int_field,
    require_string_field,
)
from gs_config import ConfigError, load_db_config, load_gs_config
from gs_error_handling import GsErrorHandlingMixin
from gs_db import GsDao
from gs_errors import GsRequestError
from gs_security import GsSecurityService, ReplayGuard, SecurityEventContext, read_int
from relay_loot import LootManagerMixin
from relay_room import RoomLifecycleMixin
from relay_snapshot import SnapshotBroadcastMixin


class RelayServer(
    GsErrorHandlingMixin, RoomLifecycleMixin, SnapshotBroadcastMixin, LootManagerMixin
):
    """处理 RelayServer 相关的 GS 中继服务流程。"""
    def __init__(self, host: Optional[str] = None, port: Optional[int] = None) -> None:
        # ── 配置 / DB / 密钥 ──
        """处理 RelayServer.__init__ 相关的 GS 中继服务流程。"""
        self.db_config = load_db_config()
        self.config = load_gs_config()
        self.host = host if host is not None else self.config.host
        self.port = port if port is not None else self.config.port
        self.db = GsDao(self.db_config)
        self.k_gs: Optional[bytes] = None

        # ── session 管理 ──
        self.sessions: Dict[Any, ClientSession] = {}  # websocket -> ClientSession
        self.sessions_by_id: Dict[str, ClientSession] = {}  # sessionId -> ClientSession

        # ── 防重放缓存: key = "{userId}/{clientId}/{nonce}" -> expires_at_ms ──
        self.replay_cache: Dict[str, int] = {}
        self.replay_guard = ReplayGuard(self.replay_cache)
        self.security = GsSecurityService(self.db, self.config, self.replay_guard)

        # ── 重连宽限期: key = sessionId ──
        self.reconnect_grace: Dict[str, Dict[str, Any]] = {}

        # ── 房间 ──
        self.rooms: Dict[str, Set[Any]] = {}
        self.room_states: Dict[str, Dict[str, Any]] = {}

        # ── 对战 ──
        # 兼容旧字段：不要再把它们作为正式对战运行态使用。
        # 正式逻辑使用 room_ticks / room_combats，按 roomId 隔离。
        self.tick: int = 0
        self.combat = CombatRuntime()

        # 每个房间独立一套 tick 和 CombatRuntime，避免多房间同时战斗互相串状态。
        self.room_ticks: Dict[str, int] = {}
        self.room_combats: Dict[str, CombatRuntime] = {}

        self.room_loots: Dict[str, Dict[str, ServerLoot]] = {}
        self.room_next_loot_tick: Dict[str, int] = {}
        self.next_loot_id = 1

    # ═══════════════════════════════════════════════════════════════
    # 启动 / 密钥加载
    # ═══════════════════════════════════════════════════════════════

    def load_runtime_keys(self) -> None:
        """加载并校验 K_GS。"""
        k_gs = b64decode(self.config.k_gs_base64)
        if len(k_gs) != DES_KEY_BYTES:
            raise ConfigError("K_GS_BASE64 must decode to exactly 8 bytes")
        self.k_gs = k_gs

    async def run(self) -> None:
        """处理 RelayServer.run 相关的 GS 中继服务流程。"""
        self.db.ping()
        self.load_runtime_keys() # 加载K_gs
        print("=" * 72)
        print(f"[SERVER] GS 游戏服务启动: ws://{self.host}:{self.port}")
        print(f"[SERVER] K_GS 已加载  gs_service={self.config.gs_service_name}")
        print(f"[SERVER] SIM_DT={SIM_DT} MOVE_SPEED={MOVE_SPEED}")
        print("=" * 72)
        maintenance_task = asyncio.create_task(self.maintenance_loop())
        try:
            async with websockets.serve(self.handle_client, self.host, self.port):
                await asyncio.Future()
        finally:
            maintenance_task.cancel()
            try:
                await maintenance_task
            except asyncio.CancelledError:
                pass

    async def maintenance_loop(self) -> None:
        while True:
            await asyncio.sleep(5)
            self.prune_replay_cache(now_ms())

    # ═══════════════════════════════════════════════════════════════
    # 连接管理 (含认证门禁)
    # ═══════════════════════════════════════════════════════════════

    async def handle_client(self, websocket: Any) -> None:
        """处理 RelayServer.handle_client 相关的 GS 中继服务流程。"""
        remote = websocket.remote_address
        self.sessions[websocket] = ClientSession()
        print(f"[CONNECT] 新连接: remote={remote} | 当前连接数={len(self.sessions)}")
        try:
            async for raw_message in websocket:
                await self.handle_message(websocket, raw_message)
        except ConnectionClosed as close_info:
            print(
                f"[CLOSED ] remote={remote} | code={close_info.code} | reason={close_info.reason}"
            )
        finally:
            await self.cleanup_client(websocket, reason="disconnect")

    async def handle_message(self, websocket: Any, raw_message: str) -> None:
        """处理 RelayServer.handle_message 相关的 GS 中继服务流程。"""
        session = self.sessions.get(websocket)

        if session is None:
            return

        try:
            data = json.loads(raw_message)
        except json.JSONDecodeError:
            await self.send_error(websocket, "INVALID_JSON")
            return

        msg_type = str(data.get("type", "")).strip()

        if not msg_type:
            await self.send_error(websocket, "MISSING_TYPE")
            return

        # ------------------------------------------------------------
        # GS_AUTH 特殊处理：
        # 1. 未认证时：正常走 handle_gs_auth
        # 2. 已认证时：说明客户端重复发了 GS_AUTH，直接忽略，避免进入已认证路由后报 UNSUPPORTED_TYPE
        # ------------------------------------------------------------

        if msg_type == TYPE_GS_AUTH:
            if session.authenticated:
                # 客户端重复发送了 GS_AUTH 消息
                print(
                    f"[GS_AUTH_RENEW_REQ] "
                    f"oldSessionId={getattr(session, 'session_id', None)} "
                    f"client={getattr(session, 'client_id', None)}"
                )

                await self.invalidate_current_session(
                    websocket,
                    reason="renew_gs_auth",
                )

            await self.run_with_error_response(
                websocket,
                "GS_AUTH",
                self.handle_gs_auth(websocket, data),
            )
            return

        # ------------------------------------------------------------
        # RECONNECT_REQ 特殊处理：
        # 重连可以在未认证状态下发。
        # 如果已认证连接又发 RECONNECT_REQ，也直接让专门函数处理。
        # ------------------------------------------------------------

        if msg_type == TYPE_RECONNECT_REQ:
            await self.run_with_error_response(
                websocket,
                "RECONNECT",
                self.handle_reconnect(websocket, data),
            )
            return

        # ------------------------------------------------------------
        # 认证门禁：
        # 除 GS_AUTH / RECONNECT_REQ 之外，未认证连接不能发业务消息。
        # ------------------------------------------------------------

        if not session.authenticated:
            await self.send_error(websocket, "NOT_AUTHENTICATED")
            return

        # ------------------------------------------------------------
        # 已认证消息路由
        # ------------------------------------------------------------

        await self.run_with_error_response(
            websocket,
            "GS",
            self.dispatch_authenticated_message(websocket, data, msg_type),
        )

    async def dispatch_authenticated_message(
        self,
        websocket: Any,
        data: Dict[str, Any],
        msg_type: str,
    ) -> None:
        """处理 RelayServer.dispatch_authenticated_message 相关的 GS 中继服务流程。"""
        if msg_type == TYPE_HEARTBEAT_REQ:
            # 处理心跳请求
            await self.handle_heartbeat(websocket, data)
        elif msg_type == TYPE_ROOM_CREATE_REQ:
            # 处理创建房间请求
            await self.handle_create_room(websocket, data)
        elif msg_type == TYPE_ROOM_JOIN_REQ:
            # 处理加入房间请求
            await self.handle_join_room(websocket, data)
        elif msg_type == TYPE_ROOM_READY_REQ:
            # 处理房间准备请求
            await self.handle_ready(websocket, data)
        elif msg_type == TYPE_ROOM_START_REQ:
            # 处理房间开始请求
            await self.handle_start_game(websocket, data)
        elif msg_type == TYPE_INPUT:
            # 处理输入请求
            await self.handle_input(websocket, data)
        elif msg_type == TYPE_LEAVE_ROOM:
            # 处理离开房间请求
            await self.handle_leave_room(websocket, data)
        else:
            await self.send_error(websocket, f"UNSUPPORTED_TYPE: {msg_type}")

    # ═══════════════════════════════════════════════════════════════
    # GS_AUTH handler (阶段三第3-4步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_gs_auth(self, websocket: Any, data: Dict[str, Any]) -> None:
        # GS_AUTH 是客户端进入游戏服务器的第一道门禁。
        # 这里要做三件事：校验票据、解密客户端认证器、创建已认证会话。
        client_id = require_string_field(data, "clientId")
        if self.k_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        current_ms = now_ms()
        context = SecurityEventContext(
            event_type="GS_AUTH_FAIL",
            client_id=client_id,
            remote_addr=self.remote_ip(websocket),
        )

        with self.db.connection() as conn:
            # 先验证 ServiceTicket 是否可信，并从中取出本次会话要用的 KcGs。
            ticket = self.security.validate_service_ticket(
                conn,
                k_gs=self.k_gs,
                encrypted_ticket=require_string_field(data, "ticket"),
                client_id=client_id,
                current_ms=current_ms,
                context=context,
                require_service=True,
                require_kc=True,
            )
            if ticket.kc_gs is None:
                raise GsRequestError("INVALID_TICKET")

            # 再用 KcGs 解密客户端的 authenticator，确认它是同一个用户、同一台客户端发来的。
            auth = self.security.decrypt_client_authenticator(
                conn,
                kc_gs=ticket.kc_gs,
                encrypted_auth=require_string_field(data, "auth"),
                current_ms=current_ms,
                context=context,
                user_id=ticket.user_id,
                username=ticket.username,
                client_id=ticket.client_id,
            )
            auth_ts = require_int_field(auth, "ts")
            auth_nonce = require_string_field(auth, "nonce")
            self._expire_reconnect_grace(current_ms)

            session_id = f"sess-{ticket.user_id}-{generate_nonce()[:8]}"
            session = self.sessions.get(websocket)
            if session is None:
                session = ClientSession()
                self.sessions[websocket] = session

            session.authenticated = True
            session.session_id = session_id
            session.user_id = ticket.user_id
            session.username = ticket.username
            session.kc_gs = ticket.kc_gs
            session.login_gen = ticket.login_gen
            session.client_id = client_id

            self.sessions_by_id[session_id] = session
            self.security.record_success(
                conn,
                context,
                event_type="GS_AUTH_SUCCESS",
                user_id=ticket.user_id,
                username=ticket.username,
            )
            conn.commit()

        # 回给客户端一个用 KcGs 加密的响应，证明服务端也完成了认证流程。
        protected_payload = des_encrypt_object(
            ticket.kc_gs,
            {
                "ts": auth_ts,
                "nonce": auth_nonce,
                "exp": ticket.exp,
            },
        )
        await websocket.send(
            make_message(
                TYPE_GS_AUTH_OK,
                sessionId=session_id,
                payload=protected_payload,
            )
        )
        print(
            f"[GS_AUTH OK] client={client_id} userId={ticket.user_id} sessionId={session_id}"
        )

    async def handle_heartbeat(self, websocket: Any, data: Dict[str, Any]) -> None:
        """处理 RelayServer.handle_heartbeat 相关的 GS 中继服务流程。"""
        session = self._require_session(websocket)
        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        auth = self.decrypt_auth(session, data)
        if require_string_field(auth, "type") != TYPE_HEARTBEAT_REQ:
            raise GsRequestError("TYPE_MISMATCH")
        if require_string_field(auth, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")
        heartbeat_nonce = require_string_field(auth, "nonce")
        heartbeat_ts = require_int_field(auth, "ts")

        # HEARTBEAT_REP: payload 中 nonce 回显 HEARTBEAT_REQ 的 nonce
        kc_gs = self._require_kc_gs(session)
        rep_payload = des_encrypt_object(
            kc_gs,
            {
                "type": TYPE_HEARTBEAT_REP,
                "sessionId": session.session_id or "",
                "ts": heartbeat_ts,
                "nonce": heartbeat_nonce,
            },
        )
        await self.send_json(
            websocket,
            {
                "type": TYPE_HEARTBEAT_REP,
                "sessionId": session.session_id or "",
                "payload": rep_payload,
            },
        )

    # ═══════════════════════════════════════════════════════════════
    # RECONNECT_REQ / RECONNECT_REP (阶段六)
    # ═══════════════════════════════════════════════════════════════

    async def handle_reconnect(self, websocket: Any, data: Dict[str, Any]) -> None:
        """处理客户端重连请求。
        
        重连流程：
        1. 客户端在连接断开后，有有限时间窗口可以用旧 sessionId 重新连接
        2. 需要重新校验 ticket，但这次不需要 ServiceTicket 中的 service 和 kc 字段
        3. 用保存在重连宽限期内的 KcGs 来解密新传入的 auth 和 payload
        4. 校验客户端上报的 lastProcessedSeq，防止数据不一致
        5. 将旧 session 转移到新 websocket，玩家重新上线
        """
        # ── 参数校验 ──
        client_id = require_string_field(data, "clientId")
        session_id = require_string_field(data, "sessionId")
        if self.k_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        current_ms = now_ms()

        # ── 从重连宽限期查询旧会话 ──
        # 如果 sessionId 不在重连宽限期内，说明重连窗口已过期，拒绝重连。
        grace_info = self.reconnect_grace.get(session_id)
        if grace_info is None:
            raise GsRequestError("RECONNECT_EXPIRED")
        old_session: ClientSession = grace_info["session"]
        if old_session.kc_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        # 复用旧会话的 KcGs 来解密这次重连请求中的 auth 和 payload。
        kc_gs = old_session.kc_gs
        context = SecurityEventContext(
            event_type="RECONNECT_FAIL",
            client_id=client_id,
            remote_addr=self.remote_ip(websocket),
            user_id=old_session.user_id,
            username=old_session.username,
        )

        with self.db.connection() as conn:
            # ── 验证 ServiceTicket ──
            # 重连时 require_service=False, require_kc=False，因为我们已经有旧会话中保存的 KcGs，
            # 不需要从 ticket 中重新提取。这里只是校验 ticket 本身的有效性和用户身份匹配。
            ticket = self.security.validate_service_ticket(
                conn,
                k_gs=self.k_gs,
                encrypted_ticket=require_string_field(data, "ticket"),
                client_id=client_id,
                current_ms=current_ms,
                context=context,
                require_service=False,
                require_kc=False,
            )
            if ticket.user_id != old_session.user_id:
                raise GsRequestError("SESSION_MISMATCH")

            # ── 解密 auth（认证信息） ──
            # 用旧会话的 KcGs 来解密客户端发来的 auth，验证这次重连请求确实来自同一用户。
            auth = self.security.decrypt_client_authenticator(
                conn,
                kc_gs=kc_gs,
                encrypted_auth=require_string_field(data, "auth"),
                current_ms=current_ms,
                context=context,
                user_id=ticket.user_id,
                username=ticket.username,
                client_id=client_id,
            )
            if require_string_field(auth, "type") != TYPE_RECONNECT_REQ:
                raise GsRequestError("TYPE_MISMATCH")
            if require_string_field(auth, "clientId") != client_id:
                raise GsRequestError("CLIENT_MISMATCH")
            if require_string_field(auth, "sessionId") != session_id:
                raise GsRequestError("SESSION_MISMATCH")
            auth_room_id = require_string_field(auth, "roomId")
            auth_ts = require_int_field(auth, "ts")
            auth_nonce = require_string_field(auth, "nonce")
            self._expire_reconnect_grace(current_ms)

            # ── 解密 payload（业务数据） ──
            # payload 中包含客户端最后一次成功处理的 INPUT seq，
            # 用来防止在重连过程中丢失或重复处理消息。
            payload = self.security.decrypt_client_payload(
                conn,
                kc_gs=kc_gs,
                encrypted_payload=require_string_field(data, "payload"),
                context=context,
                user_id=ticket.user_id,
                username=ticket.username,
            )
            if require_string_field(payload, "type") != TYPE_RECONNECT_REQ:
                raise GsRequestError("TYPE_MISMATCH")
            if require_string_field(payload, "clientId") != client_id:
                raise GsRequestError("CLIENT_MISMATCH")
            if require_string_field(payload, "sessionId") != session_id:
                raise GsRequestError("SESSION_MISMATCH")
            if require_string_field(payload, "roomId") != auth_room_id:
                raise GsRequestError("ROOM_MISMATCH")
            if require_string_field(payload, "nonce") != auth_nonce:
                raise GsRequestError("NONCE_MISMATCH")
            # 客户端上报它已经处理到了哪一个 INPUT seq，用这个来同步服务端。
            last_processed_seq = read_int(payload, "lastProcessedSeq")

            # ── 会话恢复：从重连宽限期弹出旧会话并关联到新 websocket ──
            grace_info = self.reconnect_grace.pop(session_id, None)
            if grace_info is None:
                raise GsRequestError("RECONNECT_EXPIRED")
            room_id = grace_info["room_id"]

            # 同步客户端上报的 seq，确保服务端知道客户端已处理到哪一帧。
            old_session.last_seq = -1
            old_session.authenticated = True
            # 把旧会话关联到新的 websocket（新连接）。
            self.sessions[websocket] = old_session
            self.sessions_by_id[session_id] = old_session

            # ── 更新房间状态：玩家重新上线 ──
            self.rooms.setdefault(room_id, set()).add(websocket)
            room_state = self.room_states.get(room_id)
            if room_state is not None and old_session.client_id:
                players = room_state.get("players", {})
                if old_session.client_id in players:
                    # 把玩家的 websocket 指向新连接，标记为在线。
                    players[old_session.client_id]["websocket"] = websocket
                    players[old_session.client_id]["online"] = True

            # 记录重连成功事件。
            self.security.record_success(
                conn,
                context,
                event_type="RECONNECT_SUCCESS",
                user_id=ticket.user_id,
                username=ticket.username,
            )
            conn.commit()

        # ── 生成并发送重连响应 ──
        # 告诉客户端重连成功，并通知游戏当前是什么状态（PLAYING 还是 FINISHED）。
        room_status = (
            self.room_states.get(room_id, {}).get("status", "PLAYING")
            if room_id
            else "PLAYING"
        )
        rep_payload = des_encrypt_object(
            kc_gs,
            {
                "type": TYPE_RECONNECT_REP,
                "ok": True,
                "sessionId": session_id,
                "roomId": room_id,
                "phase": "FINISHED" if room_status == "FINISHED" else "PLAYING",
                "lastProcessedSeq": old_session.last_seq,
                "ts": auth_ts,
                "nonce": auth_nonce,
            },
        )
        await self.send_json(
            websocket,
            {
                "type": TYPE_RECONNECT_REP,
                "sessionId": session_id,
                "roomId": room_id,
                "payload": rep_payload,
            },
        )
        print(
            f"[RECONNECT OK] client={client_id} userId={old_session.user_id} sessionId={session_id}"
        )

        # ── 广播房间状态和快照给所有在线玩家 ──
        # 让房间内其他玩家知道这个玩家已经重新上线。
        await self.broadcast_room_state(room_id)
        await self.broadcast_snapshot(room_id)

    def _enter_reconnect_grace(self, session: ClientSession) -> None:
        """将断线会话放入重连宽限期。"""
        if not session.session_id or not session.authenticated:
            return
        grace_seconds = max(5, int(RECONNECT_GRACE_SECONDS))
        self.reconnect_grace[session.session_id] = {
            "session": session,
            "disconnect_ms": now_ms(),
            "room_id": session.room_id or "",
            "client_id": session.client_id or "",
            "expire_ms": now_ms() + grace_seconds * 1000,
        }
        # 标记房间内玩家为离线
        if session.room_id and session.client_id:
            room_state = self.room_states.get(session.room_id)
            if room_state is not None:
                players = room_state.get("players", {})
                if session.client_id in players:
                    players[session.client_id]["online"] = False

    def _expire_reconnect_grace(self, current_ms: int) -> None:
        """清理过期的重连宽限期。"""
        expired_ids = [
            sid
            for sid, info in self.reconnect_grace.items()
            if info["expire_ms"] <= current_ms
        ] # 找出所有过期的 sessionId
        for sid in expired_ids:
            info = self.reconnect_grace.pop(sid, None)
            if info is None:
                continue
            old_session: ClientSession = info["session"]
            room_id = info["room_id"]
            client_id = info["client_id"]
            # 从房间中移除玩家
            if room_id and client_id:
                room_state = self.room_states.get(room_id)
                if room_state is not None and client_id in room_state.get(
                    "players", {}
                ):
                    room_state["players"].pop(client_id, None)
                    # 房主重连超时 → host 顺延给剩余 slot 最小的玩家
                    if room_state.get("hostClientId") == client_id:
                        remaining = list(room_state["players"].values())
                        if remaining:
                            remaining.sort(key=lambda p: int(p["slotNo"]))
                            room_state["hostClientId"] = remaining[0]["clientId"]
                    # 房间空就删除，避免幽灵房间残留
                    if not room_state["players"]:
                        self.room_states.pop(room_id, None)
            # 清理 sessionId 映射
            self.sessions_by_id.pop(sid, None)
            if old_session.user_id is not None:
                with self.db.connection() as conn:
                    self.db.record_security_event(
                        conn,
                        user_id=old_session.user_id,
                        username=old_session.username,
                        event_type="RECONNECT_TIMEOUT",
                        result=False,
                        client_id=client_id or "",
                        remote_addr=None,
                        reason="GRACE_PERIOD_EXPIRED",
                    )
                    conn.commit()
            print(
                f"[RECONNECT EXPIRED] sessionId={sid} client={client_id} room={room_id}"
            )

    # ═══════════════════════════════════════════════════════════════
    # 加密 / 校验工具
    # ═══════════════════════════════════════════════════════════════

    def _require_session(self, websocket: Any) -> ClientSession:
        """处理 RelayServer._require_session 相关的 GS 中继服务流程。"""
        session = self.sessions.get(websocket)
        if session is None or not session.authenticated:
            raise GsRequestError("NOT_AUTHENTICATED")
        return session

    def _require_kc_gs(self, session: ClientSession) -> bytes:
        """处理 RelayServer._require_kc_gs 相关的 GS 中继服务流程。"""
        if session.kc_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        return session.kc_gs

    def decrypt_auth(
        self, session: ClientSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Decrypt and validate a session auth object."""
        auth = self.security.decrypt_session_auth(session, data)
        self._expire_reconnect_grace(now_ms())
        return auth

    def decrypt_payload(
        self, session: ClientSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Decrypt and validate a session payload object."""
        payload = self.security.decrypt_session_payload(session, data)
        self._expire_reconnect_grace(now_ms())
        return payload

    def encrypt_payload(self, session: ClientSession, obj: Dict[str, Any]) -> str:
        """用 KcGs 加密 payload 对象。"""
        kc_gs = self._require_kc_gs(session)
        obj.setdefault("ts", now_ms())
        obj.setdefault("nonce", generate_nonce())
        return des_encrypt_object(kc_gs, obj)

    def prune_replay_cache(self, current_ms: int) -> None:
        """处理 RelayServer.prune_replay_cache 相关的 GS 中继服务流程。"""
        self.replay_guard.prune(current_ms)
        self._expire_reconnect_grace(current_ms)

    def remote_ip(self, websocket: Any) -> Optional[str]:
        """处理 RelayServer.remote_ip 相关的 GS 中继服务流程。"""
        remote = getattr(websocket, "remote_address", None)
        if remote is None:
            return None
        if isinstance(remote, tuple):
            if len(remote) >= 2:
                return f"{remote[0]}:{remote[1]}"
            if len(remote) == 1:
                return str(remote[0])
        return str(remote)

    # ═══════════════════════════════════════════════════════════════
    # Lobby / room state
    # ═══════════════════════════════════════════════════════════════

    @staticmethod
    def _read_float(cmd: Dict[str, Any], field: str, default: float) -> float:
        """处理 RelayServer._read_float 相关的 GS 中继服务流程。"""
        try:
            value = float(cmd.get(field, default))
        except (TypeError, ValueError) as exc:
            raise GsRequestError("INVALID_INPUT") from exc
        if not math.isfinite(value):
            raise GsRequestError("INVALID_INPUT")
        return value

    @classmethod
    def _read_unit_float(cls, cmd: Dict[str, Any], field: str, default: float) -> float:
        """处理 RelayServer._read_unit_float 相关的 GS 中继服务流程。"""
        value = cls._read_float(cmd, field, default)
        return max(-1.0, min(1.0, value))

    @staticmethod
    def _config_int(value: Any, default: int) -> int:
        """处理 RelayServer._config_int 相关的 GS 中继服务流程。"""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    def get_room_tick(self, room_id: str) -> int:
        if not room_id:
            return 0
        return int(self.room_ticks.get(room_id, 0))

    def set_room_tick(self, room_id: str, tick: int) -> None:
        if not room_id:
            return
        self.room_ticks[room_id] = int(tick)

    def advance_room_tick(self, room_id: str) -> int:
        tick = self.get_room_tick(room_id) + 1
        self.set_room_tick(room_id, tick)
        return tick

    def get_room_combat(self, room_id: str) -> CombatRuntime:
        combat = self.room_combats.get(room_id)
        if combat is None:
            combat = CombatRuntime()
            self.room_combats[room_id] = combat
        return combat

    def get_room_sessions(self, room_id: str) -> Dict[Any, ClientSession]:
        result: Dict[Any, ClientSession] = {}
        if not room_id:
            return result

        for ws in list(self.rooms.get(room_id, set())):
            session = self.sessions.get(ws)
            if session is None:
                continue
            if session.room_id != room_id:
                continue
            if session.client_id is None:
                continue
            result[ws] = session

        return result

    def reset_room_runtime_state(self, room_id: str) -> None:
        if not room_id:
            return

        self.room_ticks[room_id] = 0
        self.room_combats[room_id] = CombatRuntime()
        self.room_loots.pop(room_id, None)
        self.room_next_loot_tick.pop(room_id, None)

        for session in self.get_room_sessions(room_id).values():
            session.last_seq = -1

            session.is_dead = False
            session.respawn_at_tick = -1
            session.damage_percent = 0.0
            session.stocks = 3

            respawn_point = RESPAWN_POINTS.get(
                session.client_id or "", {"x": 0.0, "y": 3.0}
            )
            session.pos_x = float(respawn_point.get("x", 0.0))
            session.pos_y = float(respawn_point.get("y", 3.0))

            session.vel_x = 0.0
            session.vel_y = 0.0
            session.accepted_grounded = True
            session.accepted_jump_count = 0
            session.accepted_drop = False
            session.accepted_state = "Grounded"

            session.last_attack_tick = -999999
            session.last_attack_weapon_id = ""
            session.attack_hold_ticks = 0

            session.last_knockback_x = 0.0
            session.last_knockback_y = 0.0
            session.last_hit_tick = -1
            session.hitstun_until_tick = -1

        print(f"[ROOM RUNTIME RESET] room={room_id} tick=0")

    def cleanup_room_runtime_state(self, room_id: str) -> None:
        if not room_id:
            return

        self.room_ticks.pop(room_id, None)
        self.room_combats.pop(room_id, None)
        self.room_loots.pop(room_id, None)
        self.room_next_loot_tick.pop(room_id, None)

        print(f"[ROOM RUNTIME CLEANUP] room={room_id}")

    def parse_input_payload(self, cmd: dict) -> InputPayload:
        """处理 RelayServer.parse_input_payload 相关的 GS 中继服务流程。"""
        effect_ids_raw = cmd.get("equippedEffectIds", [])
        # 客户端传入的效果列表只接受 list，其他类型直接降级为空列表。
        effect_ids = (
            [str(eid) for eid in effect_ids_raw]
            if isinstance(effect_ids_raw, list)
            else []
        )
        return InputPayload(
            seq=int(cmd.get("seq", 0)),
            tick=int(cmd.get("tick", 0)),
            move_x=self._read_unit_float(cmd, "moveX", 0.0),
            jump_pressed=bool(cmd.get("jumpPressed", False)),
            down_held=bool(cmd.get("downHeld", False)),
            drop_pressed=bool(cmd.get("dropPressed", False)),
            attack_pressed=bool(cmd.get("attackPressed", False)),
            attack_held=bool(cmd.get("attackHeld", False)),
            attack_released=bool(cmd.get("attackReleased", False)),
            aim_x=self._read_unit_float(cmd, "aimX", 0.0),
            aim_y=self._read_unit_float(cmd, "aimY", 0.0),
            client_state=str(cmd.get("clientState", "Unknown")),
            client_grounded=bool(cmd.get("clientGrounded", False)),
            client_jump_count=int(cmd.get("clientJumpCount", 0)),
            client_pos_x=self._read_float(cmd, "clientPosX", 0.0),
            client_pos_y=self._read_float(cmd, "clientPosY", 0.0),
            client_vel_x=self._read_float(cmd, "clientVelX", 0.0),
            client_vel_y=self._read_float(cmd, "clientVelY", 0.0),
            equipped_weapon_id=str(cmd.get("equippedWeaponId", "手枪")),
            equipped_effect_ids=effect_ids,
        )

    def should_execute_attack(
        self,
        session: ClientSession,
        cmd: InputPayload,
        tick: int,
    ) -> bool:
        if session is None or session.client_id is None or session.is_dead:
            return False

        weapon_id = session.equipped_weapon_id
        weapon_cfg = WEAPON_DB.get(weapon_id)
        if weapon_cfg is None:
            # 如果武器表里找不到当前武器，就退回到默认武器配置，避免配置缺失导致逻辑中断。
            weapon_cfg = WEAPON_DB.get("手枪", {})

        attack_mode = weapon_cfg.get("attack_mode", "ranged")
        auto_fire = bool(weapon_cfg.get("auto_fire", attack_mode == "ranged"))

        # fire_interval_ticks 是攻击冷却间隔，单位是 tick。
        # 数值越大，同一把武器两次攻击之间的最小等待时间越长。
        fire_interval_ticks = self._config_int(
            weapon_cfg.get("fire_interval_ticks", 10), 10
        )

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

        elapsed = tick - session.last_attack_tick
        if elapsed < fire_interval_ticks:
            return False

        session.last_attack_tick = tick
        return True

    async def handle_input(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)

        if not session.room_id or not session.client_id:
            raise GsRequestError("NOT_IN_ROOM")

        room_id = session.room_id

        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        if require_string_field(data, "roomId") != room_id:
            raise GsRequestError("ROOM_MISMATCH")

        # ------------------------------------------------------------
        # 高频 INPUT payload 兼容两种格式：
        #
        # payloadEncrypted=true:
        #   payload 是 Base64(DES-CBC-PKCS7(JSON))
        #
        # payloadEncrypted=false:
        #   payload 是明文 JSON 字符串，或者直接是 dict
        #
        # 没传 payloadEncrypted 时默认 true，兼容旧客户端。
        # ------------------------------------------------------------

        payload_encrypted = self.read_bool(data.get("payloadEncrypted"), True)

        if payload_encrypted:
            payload = self.decrypt_payload(session, data)
        else:
            raw_payload = data.get("payload")

            if isinstance(raw_payload, dict):
                payload = raw_payload
            elif isinstance(raw_payload, str) and raw_payload.strip() != "":
                try:
                    payload = json.loads(raw_payload)
                except json.JSONDecodeError as exc:
                    raise GsRequestError("INVALID_PAYLOAD") from exc
            else:
                raise GsRequestError("INVALID_PAYLOAD")

            if not isinstance(payload, dict):
                raise GsRequestError("INVALID_PAYLOAD")

        if require_string_field(payload, "type") != TYPE_INPUT:
            raise GsRequestError("TYPE_MISMATCH")

        if require_string_field(payload, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        if require_string_field(payload, "roomId") != room_id:
            raise GsRequestError("ROOM_MISMATCH")

        # 首个 INPUT 将房间从 STARTING 切换到 PLAYING。
        # 这里也重置该房间自己的 tick / CombatRuntime，避免第二局或多房间串状态。
        room_state = self.room_states.get(room_id)

        if room_state is not None and room_state.get("status") == "STARTING":
            if not room_state.get("runtime_reset_done", False):
                room_state["runtime_reset_done"] = True
                self.reset_room_runtime_state(room_id)

            room_state["status"] = "PLAYING"

            print(
                f"[ROOM PLAYING] room={room_id} "
                f"tick={self.get_room_tick(room_id)}"
            )

        tick = self.get_room_tick(room_id)
        combat = self.get_room_combat(room_id)
        room_sessions = self.get_room_sessions(room_id)

        cmd = self.parse_input_payload(payload)

        # ── seq 连续性校验 (P0-3) ──
        if session.last_seq >= 0 and cmd.seq <= session.last_seq:
            reject_reason = f"seq not increasing: {cmd.seq} <= {session.last_seq}"

            print(
                f"[INPUT REJECT] room={room_id} "
                f"client={session.client_id} {reject_reason}"
            )

            await self.maybe_broadcast_snapshot(room_id, websocket, reject_reason)
            return

        # ── 拒绝客户端上传服务端权威字段 (P1-4) ──
        forbidden_keys = {
            "damagePercent",
            "stocks",
            "isDead",
            "damage",
            "hitResult",
            "killCount",
        }

        payload_keys = set(payload.keys())
        found_forbidden = payload_keys & forbidden_keys

        if found_forbidden:
            reject_reason = f"forbidden fields in INPUT: {sorted(found_forbidden)}"

            print(
                f"[INPUT REJECT] room={room_id} "
                f"client={session.client_id} {reject_reason}"
            )

            await self.maybe_broadcast_snapshot(room_id, websocket, reject_reason)
            return

        session.last_seq = cmd.seq
        reject_reason = ""

        # ── 死亡等待期间 ──
        if session.is_dead and getattr(session, "respawn_at_tick", -1) > 0:
            session.vel_x = 0.0
            session.vel_y = 0.0
            session.accepted_grounded = False
            session.accepted_state = "Dead"

            if tick >= session.respawn_at_tick and session.stocks > 0:
                respawn_point = RESPAWN_POINTS.get(
                    session.client_id,
                    {"x": 0.0, "y": 3.0},
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

                combat.push_event(
                    "PLAYER_RESPAWN",
                    {
                        "clientId": session.client_id,
                        "x": session.pos_x,
                        "y": session.pos_y,
                    },
                )

            combat.step_projectiles(room_sessions, tick)
            combat.step_melee_hitboxes(room_sessions, tick)

            self.maybe_spawn_loot_for_room(room_id)
            self.step_loots_for_room(room_id)
            self.check_loot_pickups_for_room(room_id)
            self.cleanup_dead_loots_for_room(room_id)

            tick = self.advance_room_tick(room_id)

            if tick % 20 == 0:
                print(
                    f"[PERF] room={room_id} tick={tick} "
                    f"projectiles={len(combat.projectiles)} "
                    f"events={len(combat.pending_events)} "
                    f"sessions={len(room_sessions)}"
                )

            await self.maybe_broadcast_snapshot(room_id, websocket, reject_reason)
            return

        # ── 武器 / 瞄准方向 ──
        session.aim_x = cmd.aim_x
        session.aim_y = cmd.aim_y

        if abs(cmd.aim_x) > 0.001:
            session.facing = 1 if cmd.aim_x > 0 else -1
        elif abs(cmd.move_x) > 0.001:
            session.facing = 1 if cmd.move_x > 0 else -1

        # ── 受击硬直 ──
        in_hitstun = getattr(session, "hitstun_until_tick", -1) > tick

        if in_hitstun:
            session.accepted_state = "Hitstun"
            session.accepted_grounded = False

        # ── 水平移动 ──
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

        # ── 着地检测 ──
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

        # ── 下穿 / 跳跃 ──
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

        # ── attack hold tracking ──
        if in_hitstun:
            session.attack_hold_ticks = 0
        else:
            if cmd.attack_released:
                session.attack_hold_ticks = 0
            elif cmd.attack_held:
                session.attack_hold_ticks += 1
            else:
                session.attack_hold_ticks = 0

        # ── 攻击 ──
        if not in_hitstun and self.should_execute_attack(session, cmd, tick):
            combat.execute_attack(
                attacker=session,
                aim_x=cmd.aim_x,
                aim_y=cmd.aim_y,
                tick=tick,
                sessions=room_sessions,
            )

        # ── 垂直运动 ──
        self.step_vertical(session)

        if in_hitstun and getattr(session, "hitstun_until_tick", -1) <= tick + 1:
            if session.accepted_grounded:
                session.accepted_state = "Grounded"
            else:
                session.accepted_state = "Fall"

        # ── 投射物 / 近战 / 空投 ──
        combat.step_projectiles(room_sessions, tick)
        combat.step_melee_hitboxes(room_sessions, tick)

        self.maybe_spawn_loot_for_room(room_id)
        self.step_loots_for_room(room_id)
        self.check_loot_pickups_for_room(room_id)
        self.cleanup_dead_loots_for_room(room_id)

        # ── 出界 / 命数 ──
        if game_simulation.is_out_of_bounds(session.pos_x, session.pos_y):
            if not session.is_dead:
                session.stocks -= 1

                combat.push_event(
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
                else:
                    session.is_dead = True
                    session.respawn_at_tick = tick + RESPAWN_DELAY_TICKS
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

        tick = self.advance_room_tick(room_id)

        if tick % 20 == 0:
            print(
                f"[PERF] room={room_id} tick={tick} "
                f"projectiles={len(combat.projectiles)} "
                f"events={len(combat.pending_events)} "
                f"sessions={len(room_sessions)}"
            )

        await self.check_game_over(room_id)
        await self.maybe_broadcast_snapshot(room_id, websocket, reject_reason)

    # ═══════════════════════════════════════════════════════════════
    # Cleanup / utils
    # ═══════════════════════════════════════════════════════════════
    async def invalidate_current_session(
        self,
        websocket: Any,
        reason: str = "invalidate",
    ) -> None:
        """
        废弃当前 websocket 上的旧 session，但不关闭 websocket。
        用于同一个连接重新 GS_AUTH，重新申请 sessionId。
        """
        old_session = self.sessions.get(websocket)

        if old_session is None:
            self.sessions[websocket] = ClientSession()
            return

        old_room_id = old_session.room_id
        old_client_id = old_session.client_id
        old_session_id = old_session.session_id

        room_empty = False

        if old_room_id:
            try:
                await self.remove_player_from_room_state(websocket, old_room_id)
            except Exception as exc:
                print(
                    f"[SESSION INVALIDATE WARN] "
                    f"remove_player_from_room_state failed: {exc}"
                )

            self.remove_from_room(websocket, old_room_id)
            room_empty = old_room_id not in self.rooms or not self.rooms.get(old_room_id)

        if room_empty:
            self.cleanup_room_runtime_state(old_room_id)
            try:
                await self.broadcast_room_state(old_room_id)
            except Exception as exc:
                print(
                    f"[SESSION INVALIDATE WARN] "
                    f"broadcast_room_state failed: {exc}"
                )

        if old_session_id:
            self.sessions_by_id.pop(old_session_id, None)
            self.reconnect_grace.pop(old_session_id, None)

        self.sessions[websocket] = ClientSession()

        print(
            f"[SESSION INVALIDATED] reason={reason} "
            f"oldSessionId={old_session_id} "
            f"oldClient={old_client_id} "
            f"oldRoom={old_room_id}"
        )
    async def cleanup_client(self, websocket: Any, reason: str) -> None:
        """处理 RelayServer.cleanup_client 相关的 GS 中继服务流程。"""
        session = self.sessions.get(websocket)
        if session is None:
            return
        room_id = session.room_id
        client_id = session.client_id

        # 已认证的断线进入重连宽限期，不完全清理
        if session.authenticated and session.session_id and room_id:
            room_state = self.room_states.get(room_id)
            is_playing = room_state is not None and room_state.get("status") in (
                "PLAYING",
                "STARTING",
            )
            if is_playing:
                # 对局中断线保留 sessionId，给客户端重连窗口；非对局状态则直接清房间。
                self.remove_from_room(websocket, room_id)
                self.sessions.pop(websocket, None)
                self._enter_reconnect_grace(session)
                print(
                    f"[DISCONNECT] client={client_id} room={room_id} => reconnect grace (sessionId={session.session_id})"
                )
                await self.broadcast_room_state(room_id)
                await self.broadcast_snapshot(room_id)
                return

        if room_id:
            await self.remove_player_from_room_state(websocket, room_id)
            self.remove_from_room(websocket, room_id)
            print(f"[LEAVE] client={client_id} room={room_id} reason={reason}")
            await self.broadcast_room_state(room_id)
            await self.broadcast_snapshot(room_id)
        # 清理 sessionId 映射
        if session.session_id:
            self.sessions_by_id.pop(session.session_id, None)
            self.reconnect_grace.pop(session.session_id, None)
        self.sessions.pop(websocket, None)
        print(
            f"[CLEANUP] client={client_id} room={room_id} reason={reason} sessions={len(self.sessions)}"
        )

    async def close_and_forget_socket(
        self, websocket: Any, reason: str = "replaced"
    ) -> None:
        """处理 RelayServer.close_and_forget_socket 相关的 GS 中继服务流程。"""
        if websocket is None:
            return
        old_session = self.sessions.get(websocket)
        old_room_id = old_session.room_id if old_session is not None else None
        old_client_id = old_session.client_id if old_session is not None else None
        old_session_id = old_session.session_id if old_session is not None else None
        if old_room_id:
            self.remove_from_room(websocket, old_room_id)
            room_state = self.room_states.get(old_room_id)
            if room_state is not None:
                # 被替换的旧 socket 必须从 room_state.players 中解绑，避免幽灵玩家占位。
                players = room_state.get("players", {})
                for cid in list(players.keys()):
                    if players[cid].get("websocket") is websocket:
                        players.pop(cid, None)
        if old_session is not None:
            old_session.room_id = None
            old_session.client_id = None
            old_session.last_seq = -1
        if old_session_id:
            self.sessions_by_id.pop(old_session_id, None)
        self.sessions.pop(websocket, None)
        try:
            await websocket.close(code=4000, reason=reason)
        except Exception as exc:
            print(f"[FORGET SOCKET WARN] close failed: {exc}")
        print(
            f"[FORGET SOCKET] reason={reason} oldClient={old_client_id} sessions={len(self.sessions)}"
        )
    @staticmethod
    def read_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default

        if isinstance(value, bool):
            return value

        if isinstance(value, str):
            v = value.strip().lower()

            if v in ("true", "1", "yes", "y", "on"):
                return True

            if v in ("false", "0", "no", "n", "off"):
                return False

            return default

        return bool(value)
    def remove_from_room(self, websocket: Any, room_id: str) -> None:
        """处理 RelayServer.remove_from_room 相关的 GS 中继服务流程。"""
        members = self.rooms.get(room_id)

        if not members:
            return

        members.discard(websocket)

        if not members:
            self.rooms.pop(room_id, None)

            # 注意：
            # 不要在这里 cleanup_room_runtime_state。
            # 因为 PLAYING / STARTING 断线时还可能进入 reconnect grace，
            # runtime 要保留给重连。
            print(f"[ROOM MEMBERS EMPTY] room={room_id}, runtime kept")

    async def send_error(self, websocket: Any, error_message: str) -> None:
        """处理 RelayServer.send_error 相关的 GS 中继服务流程。"""
        await self.send_json(websocket, {"type": "ERROR", "error": error_message})

    async def send_json(self, websocket: Any, payload: Dict[str, Any]) -> None:
        """处理 RelayServer.send_json 相关的 GS 中继服务流程。"""
        try:
            await websocket.send(json.dumps(payload, ensure_ascii=False))
        except ConnectionClosed:
            pass

    # ═══════════════════════════════════════════════════════════════
    # Loot methods (unchanged)
    # ═══════════════════════════════════════════════════════════════

    def hits_wall(self, x: float, y: float) -> bool:
        """处理 RelayServer.hits_wall 相关的 GS 中继服务流程。"""
        return game_simulation.hits_wall(x, y)

    def step_vertical(self, session: ClientSession) -> None:
        """处理 RelayServer.step_vertical 相关的 GS 中继服务流程。"""
        game_simulation.step_vertical(session)

    def get_standing_platform(self, session: ClientSession) -> Optional[Platform]:
        """处理 RelayServer.get_standing_platform 相关的 GS 中继服务流程。"""
        return game_simulation.get_standing_platform(session)

    @staticmethod
    def utc_now_iso() -> str:
        """处理 RelayServer.utc_now_iso 相关的 GS 中继服务流程。"""
        return datetime.now(timezone.utc).isoformat()
