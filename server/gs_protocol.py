"""GS 游戏服务器的协议报文工具。

统一报文约定:
- WebSocket 文本帧内容是 UTF-8 JSON。
- 顶层必须包含 type。
- payload 在协议层始终是字符串 (加密后为 Base64 文本)。
- ERROR 报文格式固定为 {"type":"ERROR","error":"错误码"}。
"""

import json
from typing import Any, Dict


# ── 规范定义的 GS 消息类型 ──────────────────────────────────────────
TYPE_GS_AUTH = "GS_AUTH"
TYPE_GS_AUTH_OK = "GS_AUTH_OK"

TYPE_ROOM_CREATE_REQ = "ROOM_CREATE_REQ"
TYPE_ROOM_CREATE_REP = "ROOM_CREATE_REP"

TYPE_ROOM_JOIN_REQ = "ROOM_JOIN_REQ"
TYPE_ROOM_JOIN_REP = "ROOM_JOIN_REP"

TYPE_ROOM_STATE = "ROOM_STATE"

TYPE_ROOM_READY_REQ = "ROOM_READY_REQ"
TYPE_ROOM_READY_REP = "ROOM_READY_REP"

TYPE_ROOM_START_REQ = "ROOM_START_REQ"
TYPE_ROOM_START_REP = "ROOM_START_REP"

TYPE_INPUT = "INPUT"
TYPE_SNAPSHOT = "SNAPSHOT"


TYPE_RESULT = "RESULT"

TYPE_RECONNECT_REQ = "RECONNECT_REQ"
TYPE_RECONNECT_REP = "RECONNECT_REP"

TYPE_LEAVE_ROOM = "LEAVE_ROOM"
TYPE_ERROR = "ERROR"

# ── GS_AUTH 前允许的消息类型 ────────────────────────────────────────
class ProtocolError(ValueError):
    """协议层错误，业务层会转换成 ERROR 报文。"""

    def __init__(self, error_code: str) -> None:
        """处理 ProtocolError.__init__ 相关的协议校验错误。"""
        super().__init__(error_code)
        self.error_code = error_code


def dumps_json(obj: Any) -> str:
    """把 Python 对象编码成紧凑 JSON 字符串。"""
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def make_message(msg_type: str, **fields: Any) -> str:
    """构造普通成功响应报文。"""
    msg = {"type": msg_type}
    for key, value in fields.items():
        if value is not None:
            msg[key] = value
    return dumps_json(msg)


def require_string_field(obj: Dict[str, Any], field: str) -> str:
    """读取必需字符串字段。"""
    value = obj.get(field)
    if not isinstance(value, str) or value.strip() == "":
        raise ProtocolError("MISSING_FIELD")
    return value.strip()


def require_int_field(obj: Dict[str, Any], field: str) -> int:
    """读取必需整数字段。"""
    value = obj.get(field)
    if isinstance(value, bool):
        raise ProtocolError("MISSING_FIELD")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip() != "":
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ProtocolError("MISSING_FIELD") from exc
    raise ProtocolError("MISSING_FIELD")
