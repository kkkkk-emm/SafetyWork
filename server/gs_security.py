"""GS 安全服务模块。

职责：
1. Service Ticket 解密与校验（K_GS 长期密钥解密，校验 ticketType/clientId/service/exp/login_gen）
2. Authenticator 解密与校验（KcGs 会话密钥解密，校验时间窗口 + nonce 防重放）
3. 会话内 payload/auth 解密与校验（KcGs + 时间窗口 + nonce 防重放）
4. 用户账户状态校验（login_gen 匹配、status 启禁用）
5. 安全事件记录（成功/失败均写入 security_event_log）

Kerberos 安全模型：
- K_GS：TGS 与 GS 共享的长期 DES 密钥，用于加密 ServiceTicket（客户端不可读）
- KcGs：TGS 为客户端生成的会话密钥，嵌入在 ServiceTicket 中，用于客户端↔GS 通信
- Authenticator：客户端用 KcGs 加密的时间戳+nonce，证明持有 KcGs
- ReplayGuard：基于 nonce 的防重放缓存，同一 (userId, clientId, nonce) 只能用一次
- 时间窗口：默认 30 秒，防止时钟偏差过大的旧请求被重放
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from crypto_utils import (
    DES_KEY_BYTES,
    CryptoError,
    b64decode,
    des_decrypt_object,
    now_ms,
)
from gs_errors import GsRequestError
from gs_protocol import ProtocolError, require_int_field, require_string_field


# 允许客户端时钟比服务器快 1 秒，避免 NTP 小偏差导致拒绝合法请求
MAX_FUTURE_TIMESTAMP_SKEW_MS = 1000


def timestamp_in_window(timestamp: int, current_ms: int, window_ms: int) -> bool:
    """时间戳必须在 [current_ms - window_ms, current_ms + 1s] 范围内。"""
    return (
        current_ms - window_ms <= timestamp <= current_ms + MAX_FUTURE_TIMESTAMP_SKEW_MS
    )


@dataclass(frozen=True)
class ServiceTicket:
    """TGS 签发的 Service Ticket 解析结果。

    K_GS 解密后提取的字段，frozen=True 保证不可篡改。
    kc_gs 仅在 GS_AUTH 时提取（require_kc=True），重连时不提取（已从 session 获取）。
    """
    user_id: int
    username: str
    client_id: str
    login_gen: int       # 用户登录代数，与 user_account.login_gen 比对，防止密码修改后旧票据仍可用
    exp: int             # 票据过期时间 (毫秒时间戳)
    kc_gs: Optional[bytes] = None  # 会话密钥，GS_AUTH 时提取，重连时从旧 session 获取


@dataclass(frozen=True)
class SecurityEventContext:
    """安全事件上下文，统一传递给 record_success/record_failure。"""
    event_type: str          # 事件类型: GS_AUTH_FAIL / RECONNECT_FAIL / TICKET_EXPIRED 等
    client_id: str           # 客户端标识
    remote_addr: Optional[str]  # 客户端 IP:port
    user_id: Optional[int] = None
    username: Optional[str] = None


class ReplayGuard:
    """防重放缓存。

    原理：每对 (userId, clientId, nonce) 只能使用一次，过期自动清理。
    非线程安全——所有 WebSocket 回调运行在同一个 asyncio 事件循环中。
    """
    def __init__(self, cache: Optional[Dict[str, int]] = None) -> None:
        """处理 ReplayGuard.__init__ 相关的票据、会话密钥或安全审计逻辑。"""
        self.cache: Dict[str, int] = cache if cache is not None else {}

    def prune(self, current_ms: int) -> None:
        """清理已过期的 nonce 记录，防止缓存无限增长。"""
        expired = [
            key for key, expires_at in self.cache.items() if expires_at <= current_ms
        ]
        for key in expired:
            self.cache.pop(key, None)

    def check_and_store(
        self,
        *,
        user_id: int,
        client_id: str,
        nonce: str,
        current_ms: int,
        window_ms: int,
    ) -> bool:
        """检查 nonce 是否已使用，未使用则存入缓存。

        返回 True 表示首次使用，False 表示重放攻击。
        """
        self.prune(current_ms)
        replay_key = f"{user_id}/{client_id}/{nonce}"
        if self.cache.get(replay_key, 0) > current_ms:
            return False  # nonce 已存在且未过期 → 重放攻击
        # 记录过期时间 = 当前时间 + 窗口，窗口过后自动过期
        self.cache[replay_key] = current_ms + window_ms
        return True


class GsSecurityService:
    """GS 安全服务——封装票据校验、认证校验、防重放、安全事件记录。

    所有需要 DB 连接的方法接收 conn 参数，由调用方管理事务边界。
    """
    def __init__(self, dao: Any, config: Any, replay_guard: ReplayGuard) -> None:
        """处理 GsSecurityService.__init__ 相关的票据、会话密钥或安全审计逻辑。"""
        self.dao = dao
        self.config = config
        self.replay_guard = replay_guard

    @property
    def window_ms(self) -> int:
        """时间窗口转为毫秒，用于 timestamp_in_window。"""
        return int(self.config.authenticator_window_seconds) * 1000

    def validate_service_ticket(
        self,
        conn: Any,
        *,
        k_gs: bytes,
        encrypted_ticket: str,
        client_id: str,
        current_ms: int,
        context: SecurityEventContext,
        require_service: bool,  # GS_AUTH 时需要校验 service 名，重连时不需要（已从 session 获取）
        require_kc: bool,       # GS_AUTH 时需要提取 KcGs，重连时不需要
    ) -> ServiceTicket:
        """用 K_GS 解密 Service Ticket 并做多层校验。

        校验链：
        1. DES 解密 → 提取 ticketType / clientId / userId / username / loginGen / exp / kcGs
        2. require_service=True 时校验 service 名与 GS 配置一致（防止票据跨服务滥用）
        3. require_kc=True 时提取 KcGs 并校验长度
        4. 校验票据过期时间
        5. 查询 user_account 校验 login_gen 和 status（防止密码修改后旧票据仍可用）
        """
        try:
            # Service Ticket 只能由 GS 持有的 K_GS 解开，解密失败直接视为无效票据。
            raw_ticket = des_decrypt_object(k_gs, encrypted_ticket)
        except CryptoError as exc:
            self.record_failure(conn, context, reason=str(exc))
            raise GsRequestError("INVALID_TICKET") from exc

        try:
            # 逐项校验票据声明，避免客户端把其他服务或其他 clientId 的票据拿来复用。
            if require_string_field(raw_ticket, "ticketType") != "SERVICE_TICKET":
                raise GsRequestError("INVALID_TICKET")
            if (
                require_service
                and require_string_field(raw_ticket, "service") != self.config.gs_service_name
            ):
                raise GsRequestError("INVALID_TICKET")  # 票据是给其他 GS 的，拒绝
            if require_string_field(raw_ticket, "clientId") != client_id:
                raise GsRequestError("INVALID_TICKET") # 客户端 ID 不匹配

            user_id = read_int(raw_ticket, "userId")
            username = require_string_field(raw_ticket, "username")
            login_gen = read_int(raw_ticket, "loginGen")
            exp = read_int(raw_ticket, "exp")
            if user_id <= 0 or login_gen < 0 or exp <= 0:
                raise GsRequestError("INVALID_TICKET")
            
            kc_gs = None
            if require_kc:
                # GS_AUTH 必须带 KcGs；后续会话加密完全依赖这里解出的会话密钥。
                kc_gs = b64decode(require_string_field(raw_ticket, "kcGs"))
                if len(kc_gs) != DES_KEY_BYTES:
                    raise GsRequestError("INVALID_TICKET")
        except (ProtocolError, CryptoError, ValueError, GsRequestError) as exc:
            self.record_failure(conn, context, reason="INVALID_TICKET")
            raise GsRequestError("INVALID_TICKET") from exc

        ticket = ServiceTicket(
            user_id=user_id,
            username=username,
            client_id=client_id,
            login_gen=login_gen,
            exp=exp,
            kc_gs=kc_gs,
        )
        self._validate_ticket_expiry(conn, context, ticket, current_ms)
        self._validate_user_account(conn, context, ticket)
        return ticket

    def decrypt_client_authenticator(
        self,
        conn: Any,
        *,
        kc_gs: bytes,
        encrypted_auth: str,
        current_ms: int,
        context: SecurityEventContext,
        user_id: int,
        username: Optional[str],
        client_id: str,
    ) -> Dict[str, Any]:
        """解密客户端的 Authenticator（KcGs 加密的 ts + nonce）。

        用途：GS_AUTH 和 RECONNECT_REQ 时证明客户端持有正确的 KcGs。
        解密后进行时间窗口 + nonce 防重放双重校验。
        """
        try:
            auth = des_decrypt_object(kc_gs, encrypted_auth)
        except CryptoError as exc:
            # 认证器解不开时不能继续暴露更细的业务原因，只记录审计后统一拒绝。
            self.record_failure(
                conn,
                context,
                user_id=user_id,
                username=username,
                reason=f"AUTH_DECRYPT_FAILED:{exc}",
            )
            raise GsRequestError("AUTH_DECRYPT_FAILED") from exc

        self.validate_timestamp_and_nonce(
            conn,
            auth,
            current_ms=current_ms,
            context=context,
            user_id=user_id,
            username=username,
            client_id=client_id,
        )
        return auth

    def decrypt_client_payload(
        self,
        conn: Any,
        *,
        kc_gs: bytes,
        encrypted_payload: str,
        context: SecurityEventContext,
        user_id: int,
        username: Optional[str],
    ) -> Dict[str, Any]:
        """解密客户端 payload（仅做 DES 解密，不做 ts/nonce 校验）。

        与 decrypt_client_authenticator 的区别：
        - Authenticator 必须校验 ts+nonce（防重放的防线）
        - Payload 的 ts+nonce 校验在 decrypt_session_object 中完成
        """
        try:
            return des_decrypt_object(kc_gs, encrypted_payload)
        except CryptoError as exc:
            self.record_failure(
                conn,
                context,
                user_id=user_id,
                username=username,
                reason=f"PAYLOAD_DECRYPT_FAILED:{exc}",
            )
            raise GsRequestError("PAYLOAD_DECRYPT_FAILED") from exc

    def decrypt_session_auth(
        self, session: Any, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理 GsSecurityService.decrypt_session_auth 相关的票据、会话密钥或安全审计逻辑。"""
        return self.decrypt_session_object(session, data, "auth")

    def decrypt_session_payload(
        self, session: Any, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """处理 GsSecurityService.decrypt_session_payload 相关的票据、会话密钥或安全审计逻辑。"""
        return self.decrypt_session_object(session, data, "payload")

    def decrypt_session_object(
        self,
        session: Any,
        data: Dict[str, Any],
        field: str,  # "auth" 或 "payload"
    ) -> Dict[str, Any]:
        """解密会话中已认证的消息字段（auth 或 payload）。

        在业务消息中（CREATE_ROOM / JOIN_ROOM / READY / START / INPUT / HEARTBEAT）调用。
        校验链：
        1. 从 session 获取 KcGs
        2. DES 解密
        3. 时间窗口校验（ts 必须在期限内）
        4. nonce 防重放校验（同一 nonce 不可复用）
        """
        kc_gs = getattr(session, "kc_gs", None)
        if kc_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")

        decrypted = des_decrypt_object(kc_gs, require_string_field(data, field))
        timestamp = require_int_field(decrypted, "ts")
        nonce = require_string_field(decrypted, "nonce")
        current_ms = now_ms()
        if not timestamp_in_window(timestamp, current_ms, self.window_ms):
            raise GsRequestError("AUTH_EXPIRED")

        # payload/auth 中的 nonce 也走同一套重放检测，防止会话内请求被复制重放。
        user_id = getattr(session, "user_id", None)
        client_id = getattr(session, "client_id", None)
        if user_id is None or not client_id:
            raise GsRequestError("SESSION_MISMATCH")
        if not self.replay_guard.check_and_store(
            user_id=int(user_id),
            client_id=str(client_id),
            nonce=nonce,
            current_ms=current_ms,
            window_ms=self.window_ms,
        ):
            raise GsRequestError("REPLAY_BLOCKED")
        return decrypted

    def validate_timestamp_and_nonce(
        self,
        conn: Any,
        payload: Dict[str, Any],
        *,
        current_ms: int,
        context: SecurityEventContext,
        user_id: int,
        username: Optional[str],
        client_id: str,
    ) -> None:
        """校验 Authenticator 的 ts 时间窗口 + nonce 防重放。

        这是 GS_AUTH / RECONNECT_REQ 的安全入口——在还没建立 session 时也必须防重放。
        """
        timestamp = require_int_field(payload, "ts")
        nonce = require_string_field(payload, "nonce")
        if not timestamp_in_window(timestamp, current_ms, self.window_ms):
            # 时间窗口失败通常意味着旧包或明显时钟漂移，按认证过期处理并写安全日志。
            self.record_failure(
                conn,
                context,
                user_id=user_id,
                username=username,
                reason="AUTH_EXPIRED",
            )
            raise GsRequestError("AUTH_EXPIRED")

        if not self.replay_guard.check_and_store(
            user_id=user_id,
            client_id=client_id,
            nonce=nonce,
            current_ms=current_ms,
            window_ms=self.window_ms,
        ):
            # 同一用户、clientId、nonce 在窗口期内只能使用一次。
            self.record_failure(
                conn,
                context,
                event_type="REPLAY_BLOCKED",
                user_id=user_id,
                username=username,
                reason="AUTH_NONCE_REPLAY",
            )
            raise GsRequestError("REPLAY_BLOCKED")

    def record_success(
        self,
        conn: Any,
        context: SecurityEventContext,
        *,
        event_type: str,
        user_id: Optional[int],
        username: Optional[str],
    ) -> None:
        """处理 GsSecurityService.record_success 相关的票据、会话密钥或安全审计逻辑。"""
        self.dao.record_security_event(
            conn,
            user_id=user_id,
            username=username,
            event_type=event_type,
            result=True,
            client_id=context.client_id,
            remote_addr=context.remote_addr,
            reason=None,
        )

    def record_failure(
        self,
        conn: Any,
        context: SecurityEventContext,
        *,
        reason: Optional[str],
        event_type: Optional[str] = None,
        user_id: Optional[int] = None,
        username: Optional[str] = None,
    ) -> None:
        """处理 GsSecurityService.record_failure 相关的票据、会话密钥或安全审计逻辑。"""
        self.dao.record_security_event(
            conn,
            user_id=context.user_id if user_id is None else user_id,
            username=context.username if username is None else username,
            event_type=event_type or context.event_type,
            result=False,
            client_id=context.client_id,
            remote_addr=context.remote_addr,
            reason=reason,
        )
        conn.commit()

    def _validate_ticket_expiry(
        self,
        conn: Any,
        context: SecurityEventContext,
        ticket: ServiceTicket,
        current_ms: int,
    ) -> None:
        """校验 Service Ticket 是否过期。"""
        if current_ms <= ticket.exp:
            return
        self.record_failure(
            conn,
            context,
            event_type="TICKET_EXPIRED",
            user_id=ticket.user_id,
            username=ticket.username,
            reason="SERVICE_TICKET_EXPIRED",
        )
        raise GsRequestError("TICKET_EXPIRED")

    def _validate_user_account(
        self,
        conn: Any,
        context: SecurityEventContext,
        ticket: ServiceTicket,
    ) -> None:
        """校验用户账户状态。

        三重校验：
        1. user_id 是否存在于 user_account 表
        2. status 是否为 1（启用），0 表示被管理员禁用
        3. login_gen 是否匹配——每次修改密码 login_gen+1，旧票据自动失效；同时校验 username 防止同 ID 换名攻击
        """
        user = self.dao.find_user_by_id(conn, ticket.user_id)
        if user is None:
            self.record_failure(
                conn,
                context,
                user_id=ticket.user_id,
                username=ticket.username,
                reason="USER_NOT_FOUND",
            )
            raise GsRequestError("TICKET_INVALIDATED")

        username = str(user["username"])
        if int(user["status"]) != 1:
            self.record_failure(
                conn,
                context,
                user_id=ticket.user_id,
                username=username,
                reason="ACCOUNT_DISABLED",
            )
            raise GsRequestError("ACCOUNT_DISABLED")

        # login_gen 不匹配 → 密码已修改 / 被踢下线 → 旧票据作废
        if int(user["login_gen"]) != ticket.login_gen or username != ticket.username:
            self.record_failure(
                conn,
                context,
                event_type="TICKET_INVALIDATED",
                user_id=ticket.user_id,
                username=username,
                reason="LOGIN_GEN_OR_USERNAME_MISMATCH",
            )
            raise GsRequestError("TICKET_INVALIDATED")


def read_int(obj: Dict[str, Any], field: str) -> int:
    """从 JSON 字典中安全读取整数。bool 类型不会隐式转为 int（防止 True→1 的陷阱）。"""
    value = obj.get(field)
    if isinstance(value, bool):
        raise ValueError(field)  # 拒绝 bool，因为 Python 中 bool 是 int 的子类
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() != "":
        return int(value.strip())
    raise ValueError(field)
