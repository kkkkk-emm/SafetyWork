"""GS 游戏服务器 — 含 Kerberos 认证门禁、KcGs 加密、session 管理。

协议流程:
1. 客户端必须先发 GS_AUTH (携带 ServiceTicket + KcGs 加密的 auth)
2. GS 用 K_GS 解密 ServiceTicket，提取 KcGs，校验 login_gen / status
3. GS 返回 GS_AUTH_OK (含 sessionId + KcGs 加密的 payload)
4. 之后所有房间/对战消息的 payload/auth 均用 KcGs 加密

P0 修复范围:
- GS_AUTH / GS_AUTH_OK 门禁
- KcGs 加密所有 payload
- sessionId 管理
- K_GS 密钥加载
- DB 连接校验 login_gen / status
- nonce / ts 防重放
- 消息类型统一为规范名称
"""

import asyncio
import json
import random
import string
import sys
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed

import game_simulation
from game_combat import CombatRuntime
from game_config import (
    HOST,
    JUMP_VELOCITY,
    MATCH_COUNTDOWN_MS,
    MAX_JUMP_COUNT,
    MOVE_SPEED,
    PORT,
    RECONNECT_GRACE_SECONDS,
    SIM_DT,
    TYPE_CHAT,
    TYPE_ERROR,
    TYPE_LEAVE_ROOM,
    WEAPON_DB,
    KNOCKBACK_DRAG_X,
    SPAWN_POINTS,
    RESPAWN_POINTS,
    RESPAWN_DELAY_TICKS,
    EFFECT_DROP_POINTS,
    EFFECT_DROP_POOL,
    WEAPON_DROP_POOL,
    LOOT_TYPE_WEIGHTS,
    LOOT_SPAWN_INTERVAL_TICKS,
    LOOT_PICKUP_RADIUS,
    LOOT_MAX_ALIVE,
    LOOT_SPAWN_Y,
    LOOT_GRAVITY,
    LOOT_FALL_SPEED_CAP,
    LOOT_HALF_HEIGHT,
    LOOT_DROP_PLATFORM_MARGIN,
    LOOT_PICKUP_ONLY_WHEN_LANDED,
    DEBUG_INPUT,
    DEBUG_ATTACK,
    DEBUG_LOOT,
    DEBUG_ROOM,
    DEBUG_CONNECTION,
    SNAPSHOT_THROTTLE_ENABLED,
    SNAPSHOT_INTERVAL_TICKS,
    SNAPSHOT_FORCE_BROADCAST_ON_EVENTS,
)
from game_models import ClientSession, InputPayload, Platform, ServerLoot
from crypto_utils import (
    DES_KEY_BYTES,
    CryptoError,
    b64decode,
    b64encode,
    des_decrypt_object,
    des_encrypt_object,
    generate_nonce,
    now_ms,
)
from gs_protocol import (
    PRE_AUTH_TYPES,
    ProtocolError,
    TYPE_GS_AUTH,
    TYPE_GS_AUTH_OK,
    TYPE_HEARTBEAT_REQ,
    TYPE_HEARTBEAT_REP,
    TYPE_INPUT,
    TYPE_RECONNECT_REQ,
    TYPE_RECONNECT_REP,
    TYPE_RESULT,
    TYPE_ROOM_CREATE_REQ,
    TYPE_ROOM_CREATE_REP,
    TYPE_ROOM_JOIN_REQ,
    TYPE_ROOM_JOIN_REP,
    TYPE_ROOM_READY_REQ,
    TYPE_ROOM_READY_REP,
    TYPE_ROOM_START_REQ,
    TYPE_ROOM_START_REP,
    TYPE_ROOM_STATE,
    TYPE_SNAPSHOT,
    loads_json,
    make_error,
    make_message,
    make_payload,
    require_fields,
    require_int_field,
    require_string_field,
)
from gs_config import ConfigError, load_db_config, load_gs_config
from gs_db import DatabaseError, GsDao


# ── 加密的 payload 类型 (接收时需先用 KcGs 解密) ────────────────
ENCRYPTED_PAYLOAD_TYPES = {
    TYPE_ROOM_READY_REQ,
    TYPE_INPUT,
}

ENCRYPTED_AUTH_TYPES = {
    TYPE_GS_AUTH,
    TYPE_HEARTBEAT_REQ,
    TYPE_RECONNECT_REQ,
    TYPE_ROOM_CREATE_REQ,
    TYPE_ROOM_JOIN_REQ,
    TYPE_ROOM_START_REQ,
}


class GsRequestError(RuntimeError):
    """GS 业务错误，最终转换成 ERROR 报文。"""
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def _read_int(obj: Dict[str, Any], field: str) -> int:
    """读取 JSON 对象中的整数，拒绝 bool。"""
    value = obj.get(field)
    if isinstance(value, bool):
        raise ValueError(field)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() != "":
        return int(value.strip())
    raise ValueError(field)


class RelayServer:
    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port

        # ── 配置 / DB / 密钥 ──
        self.db_config = load_db_config()
        self.config = load_gs_config()
        self.db = GsDao(self.db_config)
        self.k_gs: Optional[bytes] = None

        # ── session 管理 ──
        self.sessions: Dict[Any, ClientSession] = {}           # websocket -> ClientSession
        self.sessions_by_id: Dict[str, ClientSession] = {}     # sessionId -> ClientSession

        # ── 防重放缓存: key = "{userId}/{clientId}/{nonce}" -> expires_at_ms ──
        self.replay_cache: Dict[str, int] = {}

        # ── 重连宽限期: key = sessionId ──
        self.reconnect_grace: Dict[str, Dict[str, Any]] = {}

        # ── 房间 ──
        self.rooms: Dict[str, Set[Any]] = {}
        self.room_states: Dict[str, Dict[str, Any]] = {}

        # ── 对战 ──
        self.tick: int = 0
        self.combat = CombatRuntime()
        self.room_loots = {}
        self.room_next_loot_tick = {}
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
        self.db.ping()
        self.load_runtime_keys()
        print("=" * 72)
        print(f"[SERVER] GS 游戏服务启动: ws://{self.host}:{self.port}")
        print(f"[SERVER] K_GS 已加载  gs_service={self.config.gs_service_name}")
        print(f"[SERVER] SIM_DT={SIM_DT} MOVE_SPEED={MOVE_SPEED}")
        print("=" * 72)
        async with websockets.serve(self.handle_client, self.host, self.port):
            await asyncio.Future()

    # ═══════════════════════════════════════════════════════════════
    # 连接管理 (含认证门禁)
    # ═══════════════════════════════════════════════════════════════

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
                print(
                    f"[GS_AUTH_DUP] already authenticated "
                    f"userId={getattr(session, 'user_id', None)} "
                    f"client={getattr(session, 'client_id', None)} "
                    f"sessionId={getattr(session, 'session_id', None)}"
                )
                return

            try:
                await self.handle_gs_auth(websocket, data)
            except ProtocolError as exc:
                await self.send_error(websocket, exc.error_code)
            except GsRequestError as exc:
                await self.send_error(websocket, exc.error_code)
            except CryptoError as exc:
                await self.send_error(websocket, str(exc))
            except Exception as exc:
                print(f"GS_AUTH internal error: {exc}", file=sys.stderr)
                await self.send_error(websocket, "INTERNAL_ERROR")

            return

        # ------------------------------------------------------------
        # RECONNECT_REQ 特殊处理：
        # 重连可以在未认证状态下发。
        # 如果已认证连接又发 RECONNECT_REQ，也直接让专门函数处理。
        # ------------------------------------------------------------

        if msg_type == TYPE_RECONNECT_REQ:
            try:
                await self.handle_reconnect(websocket, data)
            except ProtocolError as exc:
                await self.send_error(websocket, exc.error_code)
            except GsRequestError as exc:
                await self.send_error(websocket, exc.error_code)
            except CryptoError as exc:
                await self.send_error(websocket, str(exc))
            except Exception as exc:
                print(f"RECONNECT internal error: {exc}", file=sys.stderr)
                await self.send_error(websocket, "INTERNAL_ERROR")

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

        try:
            if msg_type == TYPE_HEARTBEAT_REQ:
                await self.handle_heartbeat(websocket, data)

            elif msg_type == TYPE_ROOM_CREATE_REQ:
                await self.handle_create_room(websocket, data)

            elif msg_type == TYPE_ROOM_JOIN_REQ:
                await self.handle_join_room(websocket, data)

            elif msg_type == TYPE_ROOM_READY_REQ:
                await self.handle_ready(websocket, data)

            elif msg_type == TYPE_ROOM_START_REQ:
                await self.handle_start_game(websocket, data)

            elif msg_type == TYPE_INPUT:
                await self.handle_input(websocket, data)

            elif msg_type == TYPE_CHAT:
                await self.handle_chat(websocket, data)

            elif msg_type == TYPE_LEAVE_ROOM:
                await self.handle_leave_room(websocket, data)

            else:
                await self.send_error(websocket, f"UNSUPPORTED_TYPE: {msg_type}")

        except ProtocolError as exc:
            await self.send_error(websocket, exc.error_code)

        except GsRequestError as exc:
            await self.send_error(websocket, exc.error_code)

        except CryptoError as exc:
            await self.send_error(websocket, str(exc))

        except Exception as exc:
            print(f"GS internal error: {exc}", file=sys.stderr)
            await self.send_error(websocket, "INTERNAL_ERROR")
    # ═══════════════════════════════════════════════════════════════
    # GS_AUTH handler (阶段三第3-4步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_gs_auth(self, websocket: Any, data: Dict[str, Any]) -> None:
        """处理 GS_AUTH：验证 ServiceTicket，签发 sessionId。"""
        require_fields(data, ("clientId", "ticket", "auth"))
        client_id = require_string_field(data, "clientId")
        if self.k_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        current_ms = now_ms()

        with self.db.connection() as conn:
            # 1) 用 K_GS 解密 ServiceTicket
            try:
                ticket = des_decrypt_object(self.k_gs, require_string_field(data, "ticket"))
            except CryptoError as exc:
                self.db.record_security_event(
                    conn, user_id=None, username=None,
                    event_type="GS_AUTH_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason=str(exc),
                )
                conn.commit()
                raise GsRequestError("INVALID_TICKET") from exc

            # 2) 校验 ServiceTicket 字段
            try:
                if require_string_field(ticket, "ticketType") != "SERVICE_TICKET":
                    raise GsRequestError("INVALID_TICKET")
                if require_string_field(ticket, "service") != self.config.gs_service_name:
                    raise GsRequestError("INVALID_TICKET")
                if require_string_field(ticket, "clientId") != client_id:
                    raise GsRequestError("INVALID_TICKET")
                user_id = _read_int(ticket, "userId")
                username = require_string_field(ticket, "username")
                kc_gs_b64 = require_string_field(ticket, "kcGs")
                kc_gs = b64decode(kc_gs_b64)
                if len(kc_gs) != DES_KEY_BYTES:
                    raise GsRequestError("INVALID_TICKET")
                ticket_login_gen = _read_int(ticket, "loginGen")
                ticket_exp = _read_int(ticket, "exp")
                if user_id <= 0 or ticket_login_gen < 0 or ticket_exp <= 0:
                    raise GsRequestError("INVALID_TICKET")
            except (ProtocolError, CryptoError, ValueError) as exc:
                self.db.record_security_event(
                    conn, user_id=None, username=None,
                    event_type="GS_AUTH_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="INVALID_TICKET",
                )
                conn.commit()
                raise GsRequestError("INVALID_TICKET") from exc

            # 3) 检查票据过期
            if current_ms > ticket_exp:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="TICKET_EXPIRED", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="SERVICE_TICKET_EXPIRED",
                )
                conn.commit()
                raise GsRequestError("TICKET_EXPIRED")

            # 4) 查询 user_account 校验 login_gen / status
            user = self.db.find_user_by_id(conn, user_id)
            if user is None:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="GS_AUTH_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="USER_NOT_FOUND",
                )
                conn.commit()
                raise GsRequestError("TICKET_INVALIDATED")

            if int(user["status"]) != 1:
                self.db.record_security_event(
                    conn, user_id=user_id, username=str(user["username"]),
                    event_type="GS_AUTH_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="ACCOUNT_DISABLED",
                )
                conn.commit()
                raise GsRequestError("ACCOUNT_DISABLED")

            if int(user["login_gen"]) != ticket_login_gen or str(user["username"]) != username:
                self.db.record_security_event(
                    conn, user_id=user_id, username=str(user["username"]),
                    event_type="TICKET_INVALIDATED", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="LOGIN_GEN_OR_USERNAME_MISMATCH",
                )
                conn.commit()
                raise GsRequestError("TICKET_INVALIDATED")

            # 5) 用 KcGs 解密 auth
            try:
                auth = des_decrypt_object(kc_gs, require_string_field(data, "auth"))
            except CryptoError as exc:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="GS_AUTH_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason=f"AUTH_DECRYPT_FAILED:{exc}",
                )
                conn.commit()
                raise GsRequestError("AUTH_DECRYPT_FAILED") from exc

            # 6) 校验 auth.ts 时间窗口
            auth_ts = require_int_field(auth, "ts")
            window_ms = self.config.authenticator_window_seconds * 1000
            if abs(current_ms - auth_ts) > window_ms:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="GS_AUTH_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="AUTH_EXPIRED",
                )
                conn.commit()
                raise GsRequestError("AUTH_EXPIRED")

            # 7) 校验 auth.nonce 防重放
            auth_nonce = require_string_field(auth, "nonce")
            self.prune_replay_cache(current_ms)
            replay_key = f"{user_id}/{client_id}/{auth_nonce}"
            if self.replay_cache.get(replay_key, 0) > current_ms:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="REPLAY_BLOCKED", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="AUTH_NONCE_REPLAY",
                )
                conn.commit()
                raise GsRequestError("REPLAY_BLOCKED")
            self.replay_cache[replay_key] = current_ms + window_ms

            # 8) 生成 sessionId，激活会话
            session_id = f"sess-{user_id}-{generate_nonce()[:8]}"
            session = self.sessions.get(websocket)
            if session is None:
                session = ClientSession()
                self.sessions[websocket] = session

            session.authenticated = True
            session.session_id = session_id
            session.user_id = user_id
            session.username = username
            session.kc_gs = kc_gs
            session.login_gen = ticket_login_gen
            session.client_id = client_id

            self.sessions_by_id[session_id] = session

            # 9) 安全事件
            self.db.record_security_event(
                conn, user_id=user_id, username=username,
                event_type="GS_AUTH_SUCCESS", result=True,
                client_id=client_id, remote_addr=self.remote_ip(websocket),
                reason=None,
            )
            conn.commit()

        # 10) 返回 GS_AUTH_OK
        protected_payload = des_encrypt_object(
            kc_gs,
            {
                "ts": auth_ts,
                "nonce": auth_nonce,
                "exp": ticket_exp,
            },
        )
        await websocket.send(make_message(
            TYPE_GS_AUTH_OK,
            sessionId=session_id,
            payload=protected_payload,
        ))
        print(f"[GS_AUTH OK] client={client_id} userId={user_id} sessionId={session_id}")

    # ═══════════════════════════════════════════════════════════════
    # HEARTBEAT_REQ (阶段五第5-6步)
    # ═══════════════════════════════════════════════════════════════

    async def handle_heartbeat(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)
        require_fields(data, ("sessionId", "auth"))
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
        rep_payload = des_encrypt_object(kc_gs, {
            "type": TYPE_HEARTBEAT_REP,
            "sessionId": session.session_id or "",
            "ts": heartbeat_ts,
            "nonce": heartbeat_nonce,
        })
        await self.send_json(websocket, {
            "type": TYPE_HEARTBEAT_REP,
            "sessionId": session.session_id or "",
            "payload": rep_payload,
        })

    # ═══════════════════════════════════════════════════════════════
    # RECONNECT_REQ / RECONNECT_REP (阶段六)
    # ═══════════════════════════════════════════════════════════════

    async def handle_reconnect(self, websocket: Any, data: Dict[str, Any]) -> None:
        """处理断线重连：验证 ServiceTicket + auth + payload，恢复会话。"""
        require_fields(data, ("clientId", "sessionId", "ticket", "auth", "payload"))
        client_id = require_string_field(data, "clientId")
        session_id = require_string_field(data, "sessionId")
        if self.k_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        current_ms = now_ms()

        # 1) 查找重连宽限期中的旧会话
        grace_info = self.reconnect_grace.get(session_id)
        if grace_info is None:
            raise GsRequestError("RECONNECT_EXPIRED")
        old_session: ClientSession = grace_info["session"]
        if old_session.kc_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        kc_gs = old_session.kc_gs

        with self.db.connection() as conn:
            # 2) 用 K_GS 解密 ServiceTicket
            try:
                ticket = des_decrypt_object(self.k_gs, require_string_field(data, "ticket"))
            except CryptoError as exc:
                self.db.record_security_event(
                    conn, user_id=old_session.user_id, username=old_session.username,
                    event_type="RECONNECT_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason=str(exc),
                )
                conn.commit()
                raise GsRequestError("INVALID_TICKET") from exc

            # 3) 校验 ServiceTicket 字段
            try:
                if require_string_field(ticket, "ticketType") != "SERVICE_TICKET":
                    raise GsRequestError("INVALID_TICKET")
                if require_string_field(ticket, "clientId") != client_id:
                    raise GsRequestError("INVALID_TICKET")
                user_id = _read_int(ticket, "userId")
                username = require_string_field(ticket, "username")
                ticket_login_gen = _read_int(ticket, "loginGen")
                ticket_exp = _read_int(ticket, "exp")
                if user_id <= 0 or ticket_login_gen < 0 or ticket_exp <= 0:
                    raise GsRequestError("INVALID_TICKET")
            except (ProtocolError, CryptoError, ValueError) as exc:
                self.db.record_security_event(
                    conn, user_id=old_session.user_id, username=old_session.username,
                    event_type="RECONNECT_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="INVALID_TICKET",
                )
                conn.commit()
                raise GsRequestError("INVALID_TICKET") from exc

            # 4) 检查票据过期
            if current_ms > ticket_exp:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="TICKET_EXPIRED", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="SERVICE_TICKET_EXPIRED",
                )
                conn.commit()
                raise GsRequestError("TICKET_EXPIRED")

            # 5) 校验 login_gen / status / user_id 一致性
            user = self.db.find_user_by_id(conn, user_id)
            if user is None:
                raise GsRequestError("TICKET_INVALIDATED")
            if int(user["status"]) != 1:
                raise GsRequestError("ACCOUNT_DISABLED")
            if int(user["login_gen"]) != ticket_login_gen or str(user["username"]) != username:
                raise GsRequestError("TICKET_INVALIDATED")
            if user_id != old_session.user_id:
                raise GsRequestError("SESSION_MISMATCH")

            # 6) 用 KcGs 解密 auth
            try:
                auth = des_decrypt_object(kc_gs, require_string_field(data, "auth"))
            except CryptoError as exc:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="RECONNECT_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason=f"AUTH_DECRYPT_FAILED:{exc}",
                )
                conn.commit()
                raise GsRequestError("AUTH_DECRYPT_FAILED") from exc

            # 7) 校验 auth 字段
            if require_string_field(auth, "type") != TYPE_RECONNECT_REQ:
                raise GsRequestError("TYPE_MISMATCH")
            if require_string_field(auth, "clientId") != client_id:
                raise GsRequestError("CLIENT_MISMATCH")
            if require_string_field(auth, "sessionId") != session_id:
                raise GsRequestError("SESSION_MISMATCH")
            auth_room_id = require_string_field(auth, "roomId")
            auth_ts = require_int_field(auth, "ts")
            auth_nonce = require_string_field(auth, "nonce")

            # 8) 校验 auth.ts 时间窗口
            window_ms = self.config.authenticator_window_seconds * 1000
            if abs(current_ms - auth_ts) > window_ms:
                raise GsRequestError("AUTH_EXPIRED")

            # 9) 校验 auth.nonce 防重放
            self.prune_replay_cache(current_ms)
            replay_key = f"{user_id}/{client_id}/{auth_nonce}"
            if self.replay_cache.get(replay_key, 0) > current_ms:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="REPLAY_BLOCKED", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason="AUTH_NONCE_REPLAY",
                )
                conn.commit()
                raise GsRequestError("REPLAY_BLOCKED")
            self.replay_cache[replay_key] = current_ms + window_ms

            # 10) 用 KcGs 解密 payload
            try:
                payload = des_decrypt_object(kc_gs, require_string_field(data, "payload"))
            except CryptoError as exc:
                self.db.record_security_event(
                    conn, user_id=user_id, username=username,
                    event_type="RECONNECT_FAIL", result=False,
                    client_id=client_id, remote_addr=self.remote_ip(websocket),
                    reason=f"PAYLOAD_DECRYPT_FAILED:{exc}",
                )
                conn.commit()
                raise GsRequestError("PAYLOAD_DECRYPT_FAILED") from exc

            # 11) 校验 payload 字段与 auth 一致性
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
            last_processed_seq = _read_int(payload, "lastProcessedSeq")

            # 12) 检查旧会话是否仍在重连宽限期
            grace_info = self.reconnect_grace.pop(session_id, None)
            if grace_info is None:
                # 可能在两次检查之间被清理了
                raise GsRequestError("RECONNECT_EXPIRED")
            room_id = grace_info["room_id"]

            # 13) 恢复会话：绑定新 websocket，恢复认证状态
            old_session.last_seq = max(old_session.last_seq, last_processed_seq)
            old_session.authenticated = True
            self.sessions[websocket] = old_session
            self.sessions_by_id[session_id] = old_session

            # 14) 重新加入房间
            self.rooms.setdefault(room_id, set()).add(websocket)
            room_state = self.room_states.get(room_id)
            if room_state is not None and old_session.client_id:
                players = room_state.get("players", {})
                if old_session.client_id in players:
                    players[old_session.client_id]["websocket"] = websocket
                    players[old_session.client_id]["online"] = True

            # 15) 安全事件
            self.db.record_security_event(
                conn, user_id=user_id, username=username,
                event_type="RECONNECT_SUCCESS", result=True,
                client_id=client_id, remote_addr=self.remote_ip(websocket),
                reason=None,
            )
            conn.commit()

        # 16) 返回 RECONNECT_REP (nonce 回显 RECONNECT_REQ 的 auth_nonce)
        room_status = self.room_states.get(room_id, {}).get("status", "PLAYING") if room_id else "PLAYING"
        rep_payload = des_encrypt_object(kc_gs, {
            "type": TYPE_RECONNECT_REP,
            "ok": True,
            "sessionId": session_id,
            "roomId": room_id,
            "phase": "FINISHED" if room_status == "FINISHED" else "PLAYING",
            "lastProcessedSeq": old_session.last_seq,
            "ts": auth_ts,
            "nonce": auth_nonce,
        })
        await self.send_json(websocket, {
            "type": TYPE_RECONNECT_REP,
            "sessionId": session_id,
            "roomId": room_id,
            "payload": rep_payload,
        })
        print(f"[RECONNECT OK] client={client_id} userId={old_session.user_id} sessionId={session_id}")

        # 17) 广播更新后的房间状态
        await self.broadcast_room_state(room_id)
        await self.broadcast_snapshot(room_id)

    # ═══════════════════════════════════════════════════════════════
    # 重连宽限期管理
    # ═══════════════════════════════════════════════════════════════

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
            sid for sid, info in self.reconnect_grace.items()
            if info["expire_ms"] <= current_ms
        ]
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
                if room_state is not None and client_id in room_state.get("players", {}):
                    room_state["players"].pop(client_id, None)
            # 清理 sessionId 映射
            self.sessions_by_id.pop(sid, None)
            if old_session.user_id is not None:
                with self.db.connection() as conn:
                    self.db.record_security_event(
                        conn, user_id=old_session.user_id, username=old_session.username,
                        event_type="RECONNECT_TIMEOUT", result=False,
                        client_id=client_id or "", remote_addr=None,
                        reason="GRACE_PERIOD_EXPIRED",
                    )
                    conn.commit()
            print(f"[RECONNECT EXPIRED] sessionId={sid} client={client_id} room={room_id}")

    # ═══════════════════════════════════════════════════════════════
    # 加密 / 校验工具
    # ═══════════════════════════════════════════════════════════════

    def _require_session(self, websocket: Any) -> ClientSession:
        session = self.sessions.get(websocket)
        if session is None or not session.authenticated:
            raise GsRequestError("NOT_AUTHENTICATED")
        return session

    def _require_kc_gs(self, session: ClientSession) -> bytes:
        if session.kc_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")
        return session.kc_gs

    def decrypt_auth(self, session: ClientSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """解密 auth 字段，校验 ts 窗口和 nonce 防重放。"""
        kc_gs = self._require_kc_gs(session)
        encrypted = require_string_field(data, "auth")
        auth = des_decrypt_object(kc_gs, encrypted)
        auth_ts = require_int_field(auth, "ts")
        auth_nonce = require_string_field(auth, "nonce")

        window_ms = self.config.authenticator_window_seconds * 1000
        current_ms = now_ms()
        if abs(current_ms - auth_ts) > window_ms:
            raise GsRequestError("AUTH_EXPIRED")

        self.prune_replay_cache(current_ms)
        replay_key = f"{session.user_id}/{session.client_id}/{auth_nonce}"
        if self.replay_cache.get(replay_key, 0) > current_ms:
            raise GsRequestError("REPLAY_BLOCKED")
        self.replay_cache[replay_key] = current_ms + window_ms

        return auth

    def decrypt_payload(self, session: ClientSession, data: Dict[str, Any]) -> Dict[str, Any]:
        """解密 payload 字段，校验 ts/nonce。"""
        kc_gs = self._require_kc_gs(session)
        encrypted = require_string_field(data, "payload")
        payload = des_decrypt_object(kc_gs, encrypted)

        payload_ts = require_int_field(payload, "ts")
        payload_nonce = require_string_field(payload, "nonce")

        window_ms = self.config.authenticator_window_seconds * 1000
        current_ms = now_ms()
        if abs(current_ms - payload_ts) > window_ms:
            raise GsRequestError("AUTH_EXPIRED")

        self.prune_replay_cache(current_ms)
        replay_key = f"{session.user_id}/{session.client_id}/{payload_nonce}"
        if self.replay_cache.get(replay_key, 0) > current_ms:
            raise GsRequestError("REPLAY_BLOCKED")
        self.replay_cache[replay_key] = current_ms + window_ms

        return payload

    def encrypt_payload(self, session: ClientSession, obj: Dict[str, Any]) -> str:
        """用 KcGs 加密 payload 对象。"""
        kc_gs = self._require_kc_gs(session)
        obj.setdefault("ts", now_ms())
        obj.setdefault("nonce", generate_nonce())
        return des_encrypt_object(kc_gs, obj)

    def prune_replay_cache(self, current_ms: int) -> None:
        expired = [k for k, v in self.replay_cache.items() if v <= current_ms]
        for k in expired:
            self.replay_cache.pop(k, None)
        self._expire_reconnect_grace(current_ms)

    def remote_ip(self, websocket: Any) -> Optional[str]:
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
        if session is None or session.client_id is None or session.is_dead:
            return False
        weapon_id = session.equipped_weapon_id
        weapon_cfg = WEAPON_DB.get(weapon_id)
        if weapon_cfg is None:
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
        return True

    async def handle_input(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)
        if not session.room_id or not session.client_id:
            raise GsRequestError("NOT_IN_ROOM")

        require_fields(data, ("sessionId", "roomId", "payload"))
        if require_string_field(data, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")

        payload = self.decrypt_payload(session, data)
        if require_string_field(payload, "type") != TYPE_INPUT:
            raise GsRequestError("TYPE_MISMATCH")
        if require_string_field(payload, "sessionId") != session.session_id:
            raise GsRequestError("SESSION_MISMATCH")
        if require_string_field(payload, "roomId") != session.room_id:
            raise GsRequestError("ROOM_MISMATCH")

        # 首个 INPUT 将房间从 STARTING 切换到 PLAYING
        room_state = self.room_states.get(session.room_id)
        if room_state is not None and room_state.get("status") == "STARTING":
            room_state["status"] = "PLAYING"
            print(f"[ROOM PLAYING] room={session.room_id}")

        cmd = self.parse_input_payload(payload)

        # ── seq 连续性校验 (P0-3) ──
        if session.last_seq >= 0 and cmd.seq <= session.last_seq:
            reject_reason = f"seq not increasing: {cmd.seq} <= {session.last_seq}"
            print(f"[INPUT REJECT] client={session.client_id} {reject_reason}")
            await self.maybe_broadcast_snapshot(session.room_id, websocket, reject_reason)
            return

        # ── 拒绝客户端上传服务端权威字段 (P1-4) ──
        forbidden_keys = {"damagePercent", "stocks", "isDead", "damage", "hitResult", "killCount"}
        payload_keys = set(payload.keys())
        found_forbidden = payload_keys & forbidden_keys
        if found_forbidden:
            reject_reason = f"forbidden fields in INPUT: {sorted(found_forbidden)}"
            print(f"[INPUT REJECT] client={session.client_id} {reject_reason}")
            await self.maybe_broadcast_snapshot(session.room_id, websocket, reject_reason)
            return

        session.last_seq = cmd.seq
        reject_reason = ""

        # ── 死亡等待期间 ──
        if session.is_dead and getattr(session, "respawn_at_tick", -1) > 0:
            session.vel_x = 0.0
            session.vel_y = 0.0
            session.accepted_grounded = False
            session.accepted_state = "Dead"
            if self.tick >= session.respawn_at_tick and session.stocks > 0:
                respawn_point = RESPAWN_POINTS.get(session.client_id, {"x": 0.0, "y": 3.0})
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
                self.combat.push_event("PLAYER_RESPAWN", {
                    "clientId": session.client_id,
                    "x": session.pos_x, "y": session.pos_y,
                })
            self.combat.step_projectiles(self.sessions, self.tick)
            self.combat.step_melee_hitboxes(self.sessions, self.tick)
            self.maybe_spawn_loot_for_room(session.room_id)
            self.step_loots_for_room(session.room_id)
            self.check_loot_pickups_for_room(session.room_id)
            self.cleanup_dead_loots_for_room(session.room_id)
            self.tick += 1
            await self.maybe_broadcast_snapshot(session.room_id, websocket, reject_reason)
            return

        # ── 武器 / 瞄准方向 ──
        session.aim_x = cmd.aim_x
        session.aim_y = cmd.aim_y
        if abs(cmd.aim_x) > 0.001:
            session.facing = 1 if cmd.aim_x > 0 else -1
        elif abs(cmd.move_x) > 0.001:
            session.facing = 1 if cmd.move_x > 0 else -1

        # ── 受击硬直 ──
        in_hitstun = getattr(session, "hitstun_until_tick", -1) > self.tick
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
                # 攻击键被释放，重置蓄力/连发状态
                session.attack_hold_ticks = 0
            elif cmd.attack_held:
                session.attack_hold_ticks += 1
            else:
                session.attack_hold_ticks = 0

        # ── 攻击 ──
        if not in_hitstun and self.should_execute_attack(session, cmd):
            self.combat.execute_attack(
                attacker=session, aim_x=cmd.aim_x, aim_y=cmd.aim_y,
                tick=self.tick, sessions=self.sessions,
            )

        # ── 垂直运动 ──
        self.step_vertical(session)
        if in_hitstun and getattr(session, "hitstun_until_tick", -1) <= self.tick + 1:
            if session.accepted_grounded:
                session.accepted_state = "Grounded"
            else:
                session.accepted_state = "Fall"

        # ── 投射物 / 近战 / 空投 ──
        self.combat.step_projectiles(self.sessions, self.tick)
        self.combat.step_melee_hitboxes(self.sessions, self.tick)
        self.maybe_spawn_loot_for_room(session.room_id)
        self.step_loots_for_room(session.room_id)
        self.check_loot_pickups_for_room(session.room_id)
        self.cleanup_dead_loots_for_room(session.room_id)

        # ── 出界 / 命数 ──
        if game_simulation.is_out_of_bounds(session.pos_x, session.pos_y):
            if not session.is_dead:
                session.stocks -= 1
                self.combat.push_event("PLAYER_OUT_OF_BOUNDS", {
                    "clientId": session.client_id, "stocksLeft": session.stocks,
                })
                if session.stocks <= 0:
                    session.is_dead = True
                    session.respawn_at_tick = -1
                    session.accepted_state = "Dead"
                    session.vel_x = 0.0
                    session.vel_y = 0.0
                else:
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

        self.tick += 1
        if self.tick % 20 == 0:
            print(f"[PERF] tick={self.tick} projectiles={len(self.combat.projectiles)} "
                  f"events={len(self.combat.pending_events)} sessions={len(self.sessions)}")

        await self.check_game_over(session.room_id)
        await self.maybe_broadcast_snapshot(session.room_id, websocket, reject_reason)

    # ═══════════════════════════════════════════════════════════════
    # SNAPSHOT (阶段五第4步)
    # ═══════════════════════════════════════════════════════════════

    async def maybe_broadcast_snapshot(
        self, room_id: str, websocket: Any, reject_reason: str = "",
    ) -> None:
        if not room_id:
            return
        should_broadcast = True
        if SNAPSHOT_THROTTLE_ENABLED:
            interval = max(1, int(SNAPSHOT_INTERVAL_TICKS))
            should_broadcast = (self.tick % interval == 0)
        if SNAPSHOT_FORCE_BROADCAST_ON_EVENTS and len(self.combat.pending_events) > 0:
            should_broadcast = True
        if not should_broadcast:
            return
        await self.broadcast_snapshot(room_id, reject_reason_by_socket={websocket: reject_reason})
        self.combat.clear_events()

    def build_snapshot_payload(self, session: ClientSession, reject_reason: str) -> dict:
        players = []
        for s in self.sessions.values():
            if s.room_id != session.room_id or s.client_id is None:
                continue
            players.append({
                "slotNo": 1 if s.client_id == "Client1" else 2,
                "userId": s.user_id or 0,
                "clientId": s.client_id,
                "state": s.accepted_state,
                "grounded": s.accepted_grounded,
                "jumpCount": s.accepted_jump_count,
                "posX": s.pos_x, "posY": s.pos_y,
                "velX": s.vel_x, "velY": s.vel_y,
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
            })
        projectiles = []
        for p in self.combat.projectiles.values():
            if not p.alive:
                continue
            projectiles.append({
                "projId": p.proj_id,
                "ownerClientId": p.owner_client_id,
                "weaponId": p.weapon_id,
                "bulletId": getattr(p, "bullet_id", ""),
                "visualId": getattr(p, "visual_id", ""),
                "posX": p.pos_x, "posY": p.pos_y,
                "velX": p.vel_x, "velY": p.vel_y,
                "rotationDeg": getattr(p, "rotation_deg", 0.0),
                "radius": p.radius, "ttl": p.ttl, "alive": p.alive,
                "effectIds": list(p.effect_ids),
            })
        loots = []
        room_loots = self.get_room_loots(session.room_id)
        for loot in room_loots.values():
            if not loot.alive:
                continue
            loots.append({
                "lootId": loot.loot_id, "lootType": loot.loot_type,
                "itemId": loot.item_id,
                "posX": loot.pos_x, "posY": loot.pos_y,
                "velY": loot.vel_y, "radius": loot.radius, "landed": loot.landed,
            })
        events = []
        for e in self.combat.pending_events:
            events.append({"eventType": e.event_type, "eventSeq": e.event_seq, "data": e.data})
        return {
            "tick": self.tick,
            "lastProcessedSeq": session.last_seq,
            "rejectReason": reject_reason,
            "players": players,
            "projectiles": projectiles,
            "loots": loots,
            "events": events,
        }

    async def send_snapshot(self, websocket: Any, session: ClientSession, reject_reason: str) -> None:
        snapshot = self.build_snapshot_payload(session, reject_reason)
        # 用 KcGs 加密 snapshot payload
        encrypted = self.encrypt_payload(session, {
            "type": TYPE_SNAPSHOT,
            "sessionId": session.session_id or "",
            "roomId": session.room_id or "",
            **snapshot,
        })
        response = {
            "type": TYPE_SNAPSHOT,
            "sessionId": session.session_id or "",
            "roomId": session.room_id,
            "payload": encrypted,
        }
        await websocket.send(json.dumps(response, ensure_ascii=False))

    async def broadcast_snapshot(
        self, room_id: str,
        reject_reason_by_socket: Optional[Dict[Any, str]] = None,
    ) -> None:
        peers = list(self.rooms.get(room_id, set()))
        tasks = []
        for peer in peers:
            session = self.sessions.get(peer)
            if session is None or session.room_id != room_id or session.client_id is None:
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

    async def check_game_over(self, room_id: str) -> None:
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
            result_players.append({
                "userId": s.user_id or 0,
                "clientId": s.client_id or "",
                "stocksLeft": max(0, s.stocks),
                "finalDamagePercent": round(s.damage_percent, 1),
            })
        # 也加入重连宽限期内的玩家
        for grace_info in self.reconnect_grace.values():
            s = grace_info["session"]
            if s.room_id == room_id and s.client_id:
                result_players.append({
                    "userId": s.user_id or 0,
                    "clientId": s.client_id or "",
                    "stocksLeft": max(0, s.stocks),
                    "finalDamagePercent": round(s.damage_percent, 1),
                })

        print(f"[GAME OVER] room={room_id} winnerUserId={winner_user_id} reason={reason}")
        await self.broadcast_result(room_id, winner_user_id, reason, result_players)

    async def broadcast_result(
        self, room_id: str, winner_user_id: int, reason: str, players: list,
    ) -> None:
        """广播 RESULT 给房间内所有在线玩家和重连宽限期内的玩家。"""
        # 在线玩家
        for peer in list(self.rooms.get(room_id, set())):
            session = self.sessions.get(peer)
            if session is None or not session.authenticated:
                continue
            result_payload = self.encrypt_payload(session, {
                "type": TYPE_RESULT,
                "sessionId": session.session_id or "",
                "roomId": room_id,
                "winnerUserId": winner_user_id,
                "reason": reason,
                "players": players,
            })
            await self.send_json(peer, {
                "type": TYPE_RESULT,
                "sessionId": session.session_id or "",
                "roomId": room_id,
                "payload": result_payload,
            })

        # 清理对战状态
        self.combat.clear_events()
        self.room_loots.pop(room_id, None)
        self.room_next_loot_tick.pop(room_id, None)

    # ═══════════════════════════════════════════════════════════════
    # Chat
    # ═══════════════════════════════════════════════════════════════

    async def handle_chat(self, websocket: Any, data: Dict[str, Any]) -> None:
        session = self._require_session(websocket)
        if not session.room_id or not session.client_id:
            raise GsRequestError("NOT_IN_ROOM")

        text = str((data.get("payload") or {}).get("text", data.get("text", ""))).strip()
        if not text:
            return

        msg = {
            "type": "CHAT",
            "roomId": session.room_id,
            "fromClientId": session.client_id,
            "text": text,
            "timestamp": self.utc_now_iso(),
        }
        for peer in list(self.rooms.get(session.room_id, set())):
            await self.send_json(peer, msg)

    # ═══════════════════════════════════════════════════════════════
    # Cleanup / utils
    # ═══════════════════════════════════════════════════════════════

    async def cleanup_client(self, websocket: Any, reason: str) -> None:
        session = self.sessions.get(websocket)
        if session is None:
            return
        room_id = session.room_id
        client_id = session.client_id

        # 已认证的断线进入重连宽限期，不完全清理
        if session.authenticated and session.session_id and room_id:
            room_state = self.room_states.get(room_id)
            is_playing = room_state is not None and room_state.get("status") in ("PLAYING", "STARTING")
            if is_playing:
                self.remove_from_room(websocket, room_id)
                self.sessions.pop(websocket, None)
                self._enter_reconnect_grace(session)
                print(f"[DISCONNECT] client={client_id} room={room_id} => reconnect grace (sessionId={session.session_id})")
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
        print(f"[CLEANUP] client={client_id} room={room_id} reason={reason} sessions={len(self.sessions)}")

    async def close_and_forget_socket(self, websocket: Any, reason: str = "replaced") -> None:
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
        except Exception:
            pass
        print(f"[FORGET SOCKET] reason={reason} oldClient={old_client_id} sessions={len(self.sessions)}")

    def remove_from_room(self, websocket: Any, room_id: str) -> None:
        members = self.rooms.get(room_id)
        if not members:
            return
        members.discard(websocket)
        if not members:
            self.rooms.pop(room_id, None)

    async def send_error(self, websocket: Any, error_message: str) -> None:
        await self.send_json(websocket, {"type": "ERROR", "error": error_message})

    async def send_json(self, websocket: Any, payload: Dict[str, Any]) -> None:
        try:
            await websocket.send(json.dumps(payload, ensure_ascii=False))
        except ConnectionClosed:
            pass

    # ═══════════════════════════════════════════════════════════════
    # Loot methods (unchanged)
    # ═══════════════════════════════════════════════════════════════

    def get_room_loots(self, room_id: str) -> dict:
        if room_id not in self.room_loots:
            self.room_loots[room_id] = {}
        return self.room_loots[room_id]

    def choose_random_loot_x(self) -> float:
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
        roll = random.random() * total_weight
        chosen = candidates[-1]
        for c in candidates:
            roll -= c["weight"]
            if roll <= 0:
                chosen = c
                break
        return random.uniform(chosen["left"], chosen["right"])

    def find_loot_landing_platform_y(self, x: float, previous_y: float, next_y: float) -> Optional[float]:
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

    def maybe_spawn_loot_for_room(self, room_id: str) -> None:
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
        roll = random.random() * total_weight
        if roll < effect_weight and EFFECT_DROP_POOL:
            loot_type = "effect"
            item_id = random.choice(EFFECT_DROP_POOL)
        elif WEAPON_DROP_POOL:
            loot_type = "weapon"
            item_id = random.choice(WEAPON_DROP_POOL)
        elif EFFECT_DROP_POOL:
            loot_type = "effect"
            item_id = random.choice(EFFECT_DROP_POOL)
        else:
            return
        loot_id = f"loot_{self.next_loot_id}"
        self.next_loot_id += 1
        loot = ServerLoot(
            loot_id=loot_id, loot_type=loot_type, item_id=item_id,
            pos_x=float(x), pos_y=float(LOOT_SPAWN_Y),
            radius=LOOT_PICKUP_RADIUS, alive=True,
            vel_y=0.0, landed=False, target_platform_y=0.0,
        )
        loots[loot_id] = loot
        self.combat.push_event("LOOT_SPAWNED", {
            "lootId": loot.loot_id, "lootType": loot.loot_type,
            "itemId": loot.item_id, "x": loot.pos_x, "y": loot.pos_y,
            "radius": loot.radius,
        })
        self.room_next_loot_tick[room_id] = self.tick + LOOT_SPAWN_INTERVAL_TICKS

    def step_loots_for_room(self, room_id: str) -> None:
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
            landing_y = self.find_loot_landing_platform_y(x=loot.pos_x, previous_y=previous_y, next_y=next_y)
            if landing_y is not None:
                loot.pos_y = landing_y
                loot.vel_y = 0.0
                loot.landed = True
                loot.target_platform_y = landing_y
                self.combat.push_event("LOOT_LANDED", {
                    "lootId": loot.loot_id, "lootType": loot.loot_type,
                    "itemId": loot.item_id, "x": loot.pos_x, "y": loot.pos_y,
                })
            else:
                loot.pos_y = next_y

    def check_loot_pickups_for_room(self, room_id: str) -> None:
        if not room_id:
            return
        loots = self.get_room_loots(room_id)
        if not loots:
            return
        for session in list(self.sessions.values()):
            if session.room_id != room_id or session.client_id is None or session.is_dead:
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
                self.combat.push_event("LOOT_PICKED", {
                    "lootId": loot.loot_id, "lootType": loot.loot_type,
                    "itemId": loot.item_id, "clientId": session.client_id,
                    "x": loot.pos_x, "y": loot.pos_y,
                })

    def apply_loot_to_session(self, session, loot) -> None:
        if loot.loot_type == "effect":
            if not hasattr(session, "equipped_effect_ids") or session.equipped_effect_ids is None:
                session.equipped_effect_ids = []
            if loot.item_id not in session.equipped_effect_ids:
                session.equipped_effect_ids.append(loot.item_id)
        elif loot.loot_type == "weapon":
            session.equipped_weapon_id = loot.item_id

    def cleanup_dead_loots_for_room(self, room_id: str) -> None:
        loots = self.get_room_loots(room_id)
        dead_ids = [lid for lid, loot in loots.items() if not loot.alive]
        for lid in dead_ids:
            loots.pop(lid, None)

    # ═══════════════════════════════════════════════════════════════
    # Physics delegates (unchanged)
    # ═══════════════════════════════════════════════════════════════

    def hits_wall(self, x: float, y: float) -> bool:
        return game_simulation.hits_wall(x, y)

    def step_vertical(self, session: ClientSession) -> None:
        game_simulation.step_vertical(session)

    def get_standing_platform(self, session: ClientSession) -> Optional[Platform]:
        return game_simulation.get_standing_platform(session)

    @staticmethod
    def utc_now_iso() -> str:
        return datetime.now(timezone.utc).isoformat()
