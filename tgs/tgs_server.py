"""TGS 票据授权服务器主程序。

本服务实现 TGS_REQ -> TGS_REP:
- 使用 K_TGS 解密并验证 AS 签发的 TGT。
- 查询 user_account 校验账号状态和 login_gen。
- 使用 TGT 内的 KcTgs 校验 Authenticator 与服务请求 payload。
- 使用 K_GS 签发 Service Ticket，并用 KcTgs 返回 KcGs。

持久化边界:
- 只读取 user_account。
- 只写入 security_event_log。
- 不保存 TGT、Service Ticket、KcGs 或业务会话状态。
"""

import asyncio
import sys
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

try:
    import websockets
except ImportError as exc:  # pragma: no cover - 仅依赖缺失时触发。
    websockets = None
    _WEBSOCKETS_IMPORT_ERROR = exc
else:
    _WEBSOCKETS_IMPORT_ERROR = None

from config import ConfigError, load_db_config, load_tgs_config
from crypto_utils import (
    DES_KEY_BYTES,
    CryptoError,
    b64decode,
    b64encode,
    des_decrypt_object,
    des_encrypt_object,
    generate_des_key,
)
from db import AuthDao, DatabaseError
from protocol import (
    SUPPORTED_TGS_TYPES,
    ProtocolError,
    TYPE_TGS_REP,
    TYPE_TGS_REQ,
    loads_json,
    make_error,
    make_message,
    require_fields,
    require_int_field,
    require_string_field,
)


@dataclass(frozen=True)
class TgtContext:
    """TGT 解密校验后的业务上下文。"""

    user_id: int
    username: str
    client_id: str
    kc_tgs: bytes
    login_gen: int
    exp_ms: int


class TgsRequestError(RuntimeError):
    """TGS 业务错误，最终会转换成 ERROR 报文。"""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def now_ms() -> int:
    """返回当前 Unix 时间戳毫秒数。"""

    return int(time.time() * 1000)


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


class TgsServer:
    """TGS WebSocket 服务对象。"""

    def __init__(self) -> None:
        self.db_config = load_db_config()
        self.config = load_tgs_config()
        self.db = AuthDao(self.db_config)
        self.k_tgs: Optional[bytes] = None
        self.k_gs: Optional[bytes] = None
        self.replay_cache: Dict[str, int] = {}

    def load_runtime_keys(self) -> None:
        """加载并校验 TGS 运行所需长期密钥。"""

        k_tgs = b64decode(self.config.k_tgs_base64)
        if len(k_tgs) != DES_KEY_BYTES:
            raise ConfigError("K_TGS_BASE64 must decode to exactly 8 bytes")

        k_gs = b64decode(self.config.k_gs_base64)
        if len(k_gs) != DES_KEY_BYTES:
            raise ConfigError("K_GS_BASE64 must decode to exactly 8 bytes")

        if self.config.service_ticket_ttl_seconds <= 0:
            raise ConfigError("AUTH_SERVICE_TICKET_TTL_SECONDS must be positive")
        if self.config.authenticator_window_seconds <= 0:
            raise ConfigError("AUTH_AUTHENTICATOR_WINDOW_SECONDS must be positive")

        self.k_tgs = k_tgs
        self.k_gs = k_gs

    async def run(self) -> None:
        """启动 TGS WebSocket 服务。"""

        if websockets is None:
            raise ConfigError(
                "websockets is required; install dependencies from tgs/requirements.txt"
            ) from _WEBSOCKETS_IMPORT_ERROR

        self.db.ping()
        self.load_runtime_keys()
        print(
            f"TGS server listening on ws://{self.config.host}:{self.config.port} "
            f"realm={self.config.realm} gs={self.config.gs_service_name}"
        )
        async with websockets.serve(
            self.handle_socket,
            self.config.host,
            self.config.port,
        ):
            await asyncio.Future()

    async def handle_socket(self, websocket: Any, path: Optional[str] = None) -> None:
        """处理单个 WebSocket 连接。"""

        async for raw in websocket:
            response = self.handle_message(websocket, raw)
            await websocket.send(response)

    def handle_message(self, websocket: Any, raw: str) -> str:
        """解析并路由一条 TGS 协议消息。"""

        try:
            msg = loads_json(raw)
            msg_type = msg.get("type")
            if msg_type not in SUPPORTED_TGS_TYPES:
                raise ProtocolError("UNSUPPORTED_TYPE")
            if msg_type == TYPE_TGS_REQ:
                return self.handle_tgs_req(websocket, msg)
            raise ProtocolError("UNSUPPORTED_TYPE")
        except ProtocolError as exc:
            return make_error(exc.error_code)
        except TgsRequestError as exc:
            return make_error(exc.error_code)
        except CryptoError as exc:
            return make_error(str(exc))
        except Exception as exc:
            print(f"TGS internal error: {exc}", file=sys.stderr)
            return make_error("INTERNAL_ERROR")

    def handle_tgs_req(self, websocket: Any, msg: Dict[str, Any]) -> str:
        """处理 TGS_REQ 并签发 Service Ticket。"""

        require_fields(msg, ("clientId", "ticket", "auth", "payload"))
        client_id = require_string_field(msg, "clientId")

        if self.k_tgs is None or self.k_gs is None:
            raise TgsRequestError("KEY_NOT_CONFIGURED")

        current_ms = now_ms()

        with self.db.connection() as conn:
            try:
                ticket = self.require_encrypted_field_or_fail(
                    conn,
                    websocket,
                    msg,
                    "ticket",
                    client_id,
                    reason="MISSING_TICKET",
                )
                tgt = self.decrypt_tgt_or_fail(conn, websocket, ticket, client_id)
                ctx = self.validate_tgt_or_fail(conn, websocket, tgt, client_id)

                if current_ms > ctx.exp_ms:
                    self.fail(
                        conn,
                        websocket,
                        error_code="TICKET_EXPIRED",
                        event_type="TICKET_EXPIRED",
                        user_id=ctx.user_id,
                        username=ctx.username,
                        client_id=client_id,
                        reason="TGT_EXPIRED",
                    )

                user = self.db.find_user_by_id(conn, ctx.user_id)
                if user is None:
                    self.fail(
                        conn,
                        websocket,
                        error_code="TICKET_INVALIDATED",
                        event_type="TICKET_INVALIDATED",
                        user_id=ctx.user_id,
                        username=ctx.username,
                        client_id=client_id,
                        reason="USER_NOT_FOUND",
                    )

                db_username = str(user["username"])
                if int(user["status"]) != 1:
                    self.fail(
                        conn,
                        websocket,
                        error_code="ACCOUNT_DISABLED",
                        event_type="TGS_ISSUE_FAIL",
                        user_id=ctx.user_id,
                        username=db_username,
                        client_id=client_id,
                        reason="ACCOUNT_DISABLED",
                    )

                if int(user["login_gen"]) != ctx.login_gen or db_username != ctx.username:
                    self.fail(
                        conn,
                        websocket,
                        error_code="TICKET_INVALIDATED",
                        event_type="TICKET_INVALIDATED",
                        user_id=ctx.user_id,
                        username=db_username,
                        client_id=client_id,
                        reason="LOGIN_GEN_OR_USERNAME_MISMATCH",
                    )

                auth = self.decrypt_with_kc_tgs_or_fail(
                    conn,
                    websocket,
                    ctx,
                    client_id,
                    msg["auth"],
                    "AUTH_DECRYPT_FAILED",
                )
                auth_ts, auth_nonce = self.validate_authenticator_or_fail(
                    conn,
                    websocket,
                    ctx,
                    client_id,
                    auth,
                    current_ms,
                )
                self.mark_nonce_or_fail(
                    conn,
                    websocket,
                    ctx,
                    client_id,
                    auth_nonce,
                    current_ms,
                )

                payload = self.decrypt_with_kc_tgs_or_fail(
                    conn,
                    websocket,
                    ctx,
                    client_id,
                    msg["payload"],
                    "PAYLOAD_DECRYPT_FAILED",
                )
                service, payload_nonce = self.validate_payload_or_fail(
                    conn,
                    websocket,
                    ctx,
                    client_id,
                    payload,
                )

                service_ticket_ttl_ms = self.config.service_ticket_ttl_seconds * 1000
                exp_ms = min(current_ms + service_ticket_ttl_ms, ctx.exp_ms)
                kc_gs = generate_des_key()
                kc_gs_b64 = b64encode(kc_gs)

                service_ticket = des_encrypt_object(
                    self.k_gs,
                    {
                        "ticketType": "SERVICE_TICKET",
                        "realm": self.config.realm,
                        "userId": ctx.user_id,
                        "username": ctx.username,
                        "clientId": ctx.client_id,
                        "service": service,
                        "kcGs": kc_gs_b64,
                        "loginGen": ctx.login_gen,
                        "iat": current_ms,
                        "exp": exp_ms,
                    },
                )
                protected_payload = des_encrypt_object(
                    ctx.kc_tgs,
                    {
                        "nonce": payload_nonce,
                        "kcGs": kc_gs_b64,
                        "exp": exp_ms,
                    },
                )

                self.record_event(
                    conn,
                    websocket,
                    user_id=ctx.user_id,
                    username=ctx.username,
                    event_type="TGS_ISSUE_SUCCESS",
                    result=True,
                    client_id=client_id,
                    reason=None,
                )
                conn.commit()
            except (ProtocolError, TgsRequestError, CryptoError):
                raise
            except Exception:
                conn.rollback()
                raise

        return make_message(
            TYPE_TGS_REP,
            ticket=service_ticket,
            payload=protected_payload,
        )

    def decrypt_tgt_or_fail(
        self,
        conn: Any,
        websocket: Any,
        ticket: str,
        client_id: str,
    ) -> Dict[str, Any]:
        """用 K_TGS 解密 TGT，失败时记录审计并返回 INVALID_TGT。"""

        try:
            return des_decrypt_object(self.require_k_tgs(), ticket)
        except CryptoError as exc:
            self.record_event(
                conn,
                websocket,
                user_id=None,
                username=None,
                event_type="TGS_ISSUE_FAIL",
                result=False,
                client_id=client_id,
                reason=str(exc),
            )
            conn.commit()
            raise TgsRequestError("INVALID_TGT") from exc

    def require_encrypted_field_or_fail(
        self,
        conn: Any,
        websocket: Any,
        msg: Dict[str, Any],
        field: str,
        client_id: str,
        reason: str,
    ) -> str:
        """读取顶层加密字段，类型错误时记录审计。"""

        value = msg.get(field)
        if isinstance(value, str) and value.strip() != "":
            return value.strip()

        self.record_event(
            conn,
            websocket,
            user_id=None,
            username=None,
            event_type="TGS_ISSUE_FAIL",
            result=False,
            client_id=client_id,
            reason=reason,
        )
        conn.commit()
        raise ProtocolError("MISSING_FIELD")

    def validate_tgt_or_fail(
        self,
        conn: Any,
        websocket: Any,
        tgt: Dict[str, Any],
        client_id: str,
    ) -> TgtContext:
        """校验 TGT 明文字段。"""

        try:
            if require_string_field(tgt, "ticketType") != "TGT":
                raise TgsRequestError("INVALID_TGT")
            if require_string_field(tgt, "realm") != self.config.realm:
                raise TgsRequestError("INVALID_TGT")
            if require_string_field(tgt, "service") != self.config.tgs_service_name:
                raise TgsRequestError("INVALID_TGT")
            if require_string_field(tgt, "clientId") != client_id:
                raise TgsRequestError("INVALID_TGT")

            user_id = _read_int(tgt, "userId")
            username = require_string_field(tgt, "username")
            kc_tgs_b64 = require_string_field(tgt, "kcTgs")
            kc_tgs = b64decode(kc_tgs_b64)
            if len(kc_tgs) != DES_KEY_BYTES:
                raise TgsRequestError("INVALID_TGT")

            login_gen = _read_int(tgt, "loginGen")
            exp_ms = _read_int(tgt, "exp")
            if user_id <= 0 or login_gen < 0 or exp_ms <= 0:
                raise TgsRequestError("INVALID_TGT")

            return TgtContext(
                user_id=user_id,
                username=username,
                client_id=client_id,
                kc_tgs=kc_tgs,
                login_gen=login_gen,
                exp_ms=exp_ms,
            )
        except TgsRequestError as exc:
            self.record_event(
                conn,
                websocket,
                user_id=None,
                username=None,
                event_type="TGS_ISSUE_FAIL",
                result=False,
                client_id=client_id,
                reason=exc.error_code,
            )
            conn.commit()
            raise
        except (ProtocolError, CryptoError, ValueError) as exc:
            self.record_event(
                conn,
                websocket,
                user_id=None,
                username=None,
                event_type="TGS_ISSUE_FAIL",
                result=False,
                client_id=client_id,
                reason="INVALID_TGT",
            )
            conn.commit()
            raise TgsRequestError("INVALID_TGT") from exc

    def decrypt_with_kc_tgs_or_fail(
        self,
        conn: Any,
        websocket: Any,
        ctx: TgtContext,
        client_id: str,
        encrypted: Any,
        reason_prefix: str,
    ) -> Dict[str, Any]:
        """使用 KcTgs 解密 auth 或 payload。"""

        if not isinstance(encrypted, str) or encrypted.strip() == "":
            self.fail(
                conn,
                websocket,
                error_code="MISSING_FIELD",
                event_type="TGS_ISSUE_FAIL",
                user_id=ctx.user_id,
                username=ctx.username,
                client_id=client_id,
                reason=reason_prefix,
            )

        try:
            return des_decrypt_object(ctx.kc_tgs, encrypted)
        except CryptoError as exc:
            self.record_event(
                conn,
                websocket,
                user_id=ctx.user_id,
                username=ctx.username,
                event_type="TGS_ISSUE_FAIL",
                result=False,
                client_id=client_id,
                reason=f"{reason_prefix}:{exc}",
            )
            conn.commit()
            raise

    def validate_authenticator_or_fail(
        self,
        conn: Any,
        websocket: Any,
        ctx: TgtContext,
        client_id: str,
        auth: Dict[str, Any],
        current_ms: int,
    ) -> Tuple[int, str]:
        """校验 Authenticator 的 ts 和 nonce。"""

        try:
            auth_ts = require_int_field(auth, "ts")
            auth_nonce = require_string_field(auth, "nonce")
        except ProtocolError as exc:
            self.record_event(
                conn,
                websocket,
                user_id=ctx.user_id,
                username=ctx.username,
                event_type="TGS_ISSUE_FAIL",
                result=False,
                client_id=client_id,
                reason=exc.error_code,
            )
            conn.commit()
            raise

        window_ms = self.config.authenticator_window_seconds * 1000
        if abs(current_ms - auth_ts) > window_ms:
            self.fail(
                conn,
                websocket,
                error_code="AUTH_EXPIRED",
                event_type="TGS_ISSUE_FAIL",
                user_id=ctx.user_id,
                username=ctx.username,
                client_id=client_id,
                reason="AUTH_EXPIRED",
            )

        return auth_ts, auth_nonce

    def mark_nonce_or_fail(
        self,
        conn: Any,
        websocket: Any,
        ctx: TgtContext,
        client_id: str,
        nonce: str,
        current_ms: int,
    ) -> None:
        """检查并记录短期 replay cache。"""

        self.prune_replay_cache(current_ms)
        key = f"{ctx.user_id}/{client_id}/{nonce}"
        expires_at = self.replay_cache.get(key)
        if expires_at is not None and expires_at > current_ms:
            self.fail(
                conn,
                websocket,
                error_code="REPLAY_BLOCKED",
                event_type="REPLAY_BLOCKED",
                user_id=ctx.user_id,
                username=ctx.username,
                client_id=client_id,
                reason="AUTH_NONCE_REPLAY",
            )

        self.replay_cache[key] = (
            current_ms + self.config.authenticator_window_seconds * 1000
        )

    def validate_payload_or_fail(
        self,
        conn: Any,
        websocket: Any,
        ctx: TgtContext,
        client_id: str,
        payload: Dict[str, Any],
    ) -> Tuple[str, str]:
        """校验 TGS_REQ.payload 中的目标服务和响应 nonce。"""

        try:
            service = require_string_field(payload, "service")
            nonce = require_string_field(payload, "nonce")
        except ProtocolError as exc:
            self.record_event(
                conn,
                websocket,
                user_id=ctx.user_id,
                username=ctx.username,
                event_type="TGS_ISSUE_FAIL",
                result=False,
                client_id=client_id,
                reason=exc.error_code,
            )
            conn.commit()
            raise

        if service != self.config.gs_service_name:
            self.fail(
                conn,
                websocket,
                error_code="SERVICE_NOT_ALLOWED",
                event_type="TGS_ISSUE_FAIL",
                user_id=ctx.user_id,
                username=ctx.username,
                client_id=client_id,
                reason="SERVICE_NOT_ALLOWED",
            )

        return service, nonce

    def prune_replay_cache(self, current_ms: int) -> None:
        """清理过期 replay cache 项。"""

        expired_keys = [
            key for key, expires_at in self.replay_cache.items() if expires_at <= current_ms
        ]
        for key in expired_keys:
            self.replay_cache.pop(key, None)

    def fail(
        self,
        conn: Any,
        websocket: Any,
        *,
        error_code: str,
        event_type: str,
        user_id: Optional[int],
        username: Optional[str],
        client_id: Optional[str],
        reason: Optional[str],
    ) -> None:
        """记录失败安全事件并抛出业务错误。"""

        self.record_event(
            conn,
            websocket,
            user_id=user_id,
            username=username,
            event_type=event_type,
            result=False,
            client_id=client_id,
            reason=reason,
        )
        conn.commit()
        raise TgsRequestError(error_code)

    def record_event(
        self,
        conn: Any,
        websocket: Any,
        *,
        user_id: Optional[int],
        username: Optional[str],
        event_type: str,
        result: bool,
        client_id: Optional[str],
        reason: Optional[str],
    ) -> None:
        """写入 security_event_log。"""

        self.db.record_security_event(
            conn,
            user_id=user_id,
            username=username,
            event_type=event_type,
            result=result,
            client_id=client_id,
            remote_addr=self.remote_ip(websocket),
            reason=reason,
        )

    def remote_ip(self, websocket: Any) -> Optional[str]:
        """提取 WebSocket 远端地址。"""

        remote = getattr(websocket, "remote_address", None)
        if remote is None:
            return None
        if isinstance(remote, tuple):
            if len(remote) >= 2:
                return f"{remote[0]}:{remote[1]}"
            if len(remote) == 1:
                return str(remote[0])
        return str(remote)

    def require_k_tgs(self) -> bytes:
        """返回已加载的 K_TGS。"""

        if self.k_tgs is None:
            raise TgsRequestError("KEY_NOT_CONFIGURED")
        return self.k_tgs


def main() -> None:
    """命令行入口。"""

    try:
        server = TgsServer()
        asyncio.run(server.run())
    except (ConfigError, DatabaseError, CryptoError) as exc:
        print(f"TGS startup failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("TGS server stopped")


if __name__ == "__main__":
    main()
