"""GS 数据访问层。

只读 user_account 的 login_gen 和 status。
只写 security_event_log。
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from gs_config import DbConfig

_PYMYSQL_IMPORT_ERROR: Optional[BaseException]

try:
    import pymysql  # type: ignore[import-untyped]
    from pymysql.cursors import DictCursor  # type: ignore[import-untyped]
except ImportError as exc:
    pymysql = None
    DictCursor = None
    _PYMYSQL_IMPORT_ERROR = exc
else:
    _PYMYSQL_IMPORT_ERROR = None


class DatabaseError(RuntimeError):
    """数据库访问错误。"""

    pass


class GsDao:
    """GS 数据访问对象。"""

    def __init__(self, config: DbConfig) -> None:
        self.config = config

    def _ensure_driver(self) -> None:
        if pymysql is None:
            raise DatabaseError(
                "pymysql is required; install dependencies"
            ) from _PYMYSQL_IMPORT_ERROR

    @contextmanager
    def connection(self) -> Iterator[Any]:
        self._ensure_driver()
        conn = pymysql.connect(
            host=self.config.host,
            port=self.config.port,
            user=self.config.user,
            password=self.config.password,
            database=self.config.database,
            charset=self.config.charset,
            autocommit=False,
            cursorclass=DictCursor,
        )
        try:
            yield conn
        finally:
            conn.close()

    def ping(self) -> None:
        with self.connection() as conn:
            conn.ping(reconnect=False)

    def find_user_by_id(self, conn: Any, user_id: int) -> Optional[Dict[str, Any]]:
        """按 user_id 查询 login_gen 和 status。"""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id, username, login_gen, status
                FROM user_account
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return cur.fetchone()

    def record_security_event(
        self,
        conn: Any,
        *,
        user_id: Optional[int],
        username: Optional[str],
        event_type: str,
        result: bool,
        client_id: Optional[str],
        remote_addr: Optional[str],
        reason: Optional[str],
    ) -> None:
        """写入 security_event_log。"""
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO security_event_log
                    (user_id, username, event_type, result,
                     client_id, remote_addr, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    user_id,
                    _truncate(username, 64),
                    _truncate(event_type, 32) or event_type,
                    1 if result else 0,
                    _truncate(client_id, 64),
                    _truncate(remote_addr, 128),
                    _truncate(reason, 128),
                ),
            )


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    if value is None:
        return None
    return value[:limit]
