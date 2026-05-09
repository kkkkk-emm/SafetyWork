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


@dataclass(frozen=True)
class ServiceTicket:
    user_id: int
    username: str
    client_id: str
    login_gen: int
    exp: int
    kc_gs: Optional[bytes] = None


@dataclass(frozen=True)
class SecurityEventContext:
    event_type: str
    client_id: str
    remote_addr: Optional[str]
    user_id: Optional[int] = None
    username: Optional[str] = None


class ReplayGuard:
    def __init__(self, cache: Optional[Dict[str, int]] = None) -> None:
        self.cache: Dict[str, int] = cache if cache is not None else {}

    def prune(self, current_ms: int) -> None:
        expired = [key for key, expires_at in self.cache.items() if expires_at <= current_ms]
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
        self.prune(current_ms)
        replay_key = f"{user_id}/{client_id}/{nonce}"
        if self.cache.get(replay_key, 0) > current_ms:
            return False
        self.cache[replay_key] = current_ms + window_ms
        return True


class GsSecurityService:
    def __init__(self, dao: Any, config: Any, replay_guard: ReplayGuard) -> None:
        self.dao = dao
        self.config = config
        self.replay_guard = replay_guard

    @property
    def window_ms(self) -> int:
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
        require_service: bool,
        require_kc: bool,
    ) -> ServiceTicket:
        try:
            raw_ticket = des_decrypt_object(k_gs, encrypted_ticket)
        except CryptoError as exc:
            self.record_failure(conn, context, reason=str(exc))
            raise GsRequestError("INVALID_TICKET") from exc

        try:
            if require_string_field(raw_ticket, "ticketType") != "SERVICE_TICKET":
                raise GsRequestError("INVALID_TICKET")
            if require_service and require_string_field(raw_ticket, "service") != self.config.gs_service_name:
                raise GsRequestError("INVALID_TICKET")
            if require_string_field(raw_ticket, "clientId") != client_id:
                raise GsRequestError("INVALID_TICKET")

            user_id = read_int(raw_ticket, "userId")
            username = require_string_field(raw_ticket, "username")
            login_gen = read_int(raw_ticket, "loginGen")
            exp = read_int(raw_ticket, "exp")
            if user_id <= 0 or login_gen < 0 or exp <= 0:
                raise GsRequestError("INVALID_TICKET")

            kc_gs = None
            if require_kc:
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
        try:
            auth = des_decrypt_object(kc_gs, encrypted_auth)
        except CryptoError as exc:
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

    def decrypt_session_auth(self, session: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.decrypt_session_object(session, data, "auth")

    def decrypt_session_payload(self, session: Any, data: Dict[str, Any]) -> Dict[str, Any]:
        return self.decrypt_session_object(session, data, "payload")

    def decrypt_session_object(
        self,
        session: Any,
        data: Dict[str, Any],
        field: str,
    ) -> Dict[str, Any]:
        kc_gs = getattr(session, "kc_gs", None)
        if kc_gs is None:
            raise GsRequestError("KEY_NOT_CONFIGURED")

        decrypted = des_decrypt_object(kc_gs, require_string_field(data, field))
        timestamp = require_int_field(decrypted, "ts")
        nonce = require_string_field(decrypted, "nonce")
        current_ms = now_ms()
        if abs(current_ms - timestamp) > self.window_ms:
            raise GsRequestError("AUTH_EXPIRED")

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
        timestamp = require_int_field(payload, "ts")
        nonce = require_string_field(payload, "nonce")
        if abs(current_ms - timestamp) > self.window_ms:
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
    value = obj.get(field)
    if isinstance(value, bool):
        raise ValueError(field)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() != "":
        return int(value.strip())
    raise ValueError(field)
