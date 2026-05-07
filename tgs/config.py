"""TGS 服务器的环境变量配置读取模块。"""

import os
from dataclasses import dataclass


class ConfigError(RuntimeError):
    """配置错误。"""

    pass


@dataclass(frozen=True)
class DbConfig:
    """MySQL 连接配置。"""

    host: str
    port: int
    user: str
    password: str
    database: str
    charset: str = "utf8mb4"


@dataclass(frozen=True)
class TgsConfig:
    """TGS 运行配置。"""

    host: str
    port: int
    realm: str
    tgs_service_name: str
    gs_service_name: str
    service_ticket_ttl_seconds: int
    authenticator_window_seconds: int
    k_tgs_base64: str
    k_gs_base64: str


def _required_env(name: str) -> str:
    """读取必填环境变量。"""

    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigError(f"missing required environment variable: {name}")
    return value.strip()


def _int_env(name: str, default: int) -> int:
    """读取整数环境变量。"""

    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ConfigError(f"environment variable {name} must be an integer") from exc


def load_db_config() -> DbConfig:
    """加载 MySQL 连接配置。"""

    return DbConfig(
        host=os.getenv("AUTH_DB_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int_env("AUTH_DB_PORT", 3306),
        user=_required_env("AUTH_DB_USER"),
        password=os.getenv("AUTH_DB_PASSWORD", ""),
        database=_required_env("AUTH_DB_NAME"),
    )


def load_tgs_config() -> TgsConfig:
    """加载 TGS 协议、监听地址和长期密钥配置。"""

    realm = os.getenv("AUTH_REALM", "SAFETYWORK").strip() or "SAFETYWORK"
    tgs_service_name = (
        os.getenv("AUTH_TGS_SERVICE_NAME", f"krbtgt/{realm}").strip()
        or f"krbtgt/{realm}"
    )
    gs_service_name = (
        os.getenv("AUTH_GS_SERVICE_NAME", "game/ws@127.0.0.1:8765").strip()
        or "game/ws@127.0.0.1:8765"
    )
    return TgsConfig(
        host=os.getenv("TGS_HOST", "0.0.0.0").strip() or "0.0.0.0",
        port=_int_env("TGS_PORT", 9001),
        realm=realm,
        tgs_service_name=tgs_service_name,
        gs_service_name=gs_service_name,
        service_ticket_ttl_seconds=_int_env("AUTH_SERVICE_TICKET_TTL_SECONDS", 7200),
        authenticator_window_seconds=_int_env("AUTH_AUTHENTICATOR_WINDOW_SECONDS", 30),
        k_tgs_base64=_required_env("K_TGS_BASE64"),
        k_gs_base64=_required_env("K_GS_BASE64"),
    )
