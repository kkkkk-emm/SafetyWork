"""TGS 数据访问层。

两表化边界:
- 只读取 user_account 的账号状态和 login_gen。
- 只写入 security_event_log 的低频安全事件。
"""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Iterator, Optional

from config import DbConfig

try:
    import pymysql
    from pymysql.cursors import DictCursor
except ImportError as exc:  # pragma: no cover - 仅依赖缺失时触发。
    pymysql = None
    DictCursor = None
    _PYMYSQL_IMPORT_ERROR = exc
else:
    _PYMYSQL_IMPORT_ERROR = None


class DatabaseError(RuntimeError):
    """数据库访问错误。"""

    pass


@dataclass(frozen=True)
class SecurityEvent:
    """security_event_log 的一条待写入事件。"""

    user_id: Optional[int]
    username: Optional[str]
    event_type: str
    result: int
    client_id: Optional[str]
    remote_addr: Optional[str]
    reason: Optional[str]


class AuthDao:
    """认证库 DAO。"""

    def __init__(self, config: DbConfig) -> None:
        self.config = config

    def _ensure_driver(self) -> None:
        """确认 pymysql 已安装。"""

        if pymysql is None:
            raise DatabaseError(
                "pymysql is required; install dependencies from tgs/requirements.txt"
            ) from _PYMYSQL_IMPORT_ERROR

    @contextmanager
    def connection(self) -> Iterator[Any]:
        """创建一个 MySQL 连接。"""

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
        """检查数据库是否可连接。"""

        with self.connection() as conn:
            conn.ping(reconnect=False)

    def find_user_by_id(self, conn: Any, user_id: int) -> Optional[Dict[str, Any]]:
        """按 user_id 查询 TGS 校验所需的用户状态。"""

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

        event = SecurityEvent(
            user_id=user_id,
            username=_truncate(username, 64),
            event_type=_truncate(event_type, 32) or event_type,
            result=1 if result else 0,
            client_id=_truncate(client_id, 64),
            remote_addr=_truncate(remote_addr, 128),
            reason=_truncate(reason, 128),
        )
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO security_event_log
                    (user_id, username, event_type, result,
                     client_id, remote_addr, reason)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.user_id,
                    event.username,
                    event.event_type,
                    event.result,
                    event.client_id,
                    event.remote_addr,
                    event.reason,
                ),
            )


def _truncate(value: Optional[str], limit: int) -> Optional[str]:
    """把审计文本截断到表字段允许长度。"""

    if value is None:
        return None
    return value[:limit]
