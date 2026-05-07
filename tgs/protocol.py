"""TGS 服务的 JSON 报文工具。

本文件只处理外层协议壳，不做加密、不访问数据库。

统一报文约定:
- WebSocket 文本帧内容是 UTF-8 JSON。
- 顶层必须包含 type。
- TGS_REQ 必须携带 clientId、ticket、auth、payload。
- ERROR 报文格式固定为 {"type":"ERROR","error":"错误码"}。
"""

import json
from typing import Any, Dict, Iterable


TYPE_TGS_REQ = "TGS_REQ"
TYPE_TGS_REP = "TGS_REP"
TYPE_ERROR = "ERROR"

SUPPORTED_TGS_TYPES = {
    TYPE_TGS_REQ,
}


class ProtocolError(ValueError):
    """协议层错误，业务层会转换成 ERROR 报文。"""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def dumps_json(obj: Any) -> str:
    """把 Python 对象编码成紧凑 JSON 字符串。"""

    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def loads_json(raw: str) -> Dict[str, Any]:
    """解析客户端发来的顶层 JSON 报文。"""

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("INVALID_JSON") from exc

    if not isinstance(data, dict):
        raise ProtocolError("INVALID_MESSAGE")

    return data


def make_message(msg_type: str, **fields: Any) -> str:
    """构造普通响应报文。"""

    msg = {"type": msg_type}
    for key, value in fields.items():
        if value is not None:
            msg[key] = value
    return dumps_json(msg)


def make_error(error_code: str, **fields: Any) -> str:
    """构造统一 ERROR 报文。"""

    msg = {"type": TYPE_ERROR, "error": error_code}
    for key, value in fields.items():
        if value is not None:
            msg[key] = value
    return dumps_json(msg)


def require_fields(msg: Dict[str, Any], fields: Iterable[str]) -> None:
    """校验顶层必需字段是否存在。"""

    for field in fields:
        if field not in msg or msg[field] in (None, ""):
            raise ProtocolError("MISSING_FIELD")


def require_string_field(obj: Dict[str, Any], field: str) -> str:
    """读取必需字符串字段。"""

    value = obj.get(field)
    if not isinstance(value, str) or value.strip() == "":
        raise ProtocolError("MISSING_FIELD")
    return value.strip()


def require_int_field(obj: Dict[str, Any], field: str) -> int:
    """读取必需整数字段。

    JSON 数字和纯数字字符串都接受，便于不同客户端实现互通。
    """

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
