"""GS 游戏服务器的环境变量配置读取模块。

输入:
- AUTH_DB_HOST / AUTH_DB_PORT / AUTH_DB_USER / AUTH_DB_PASSWORD / AUTH_DB_NAME
- GS_HOST / GS_PORT
- K_GS_BASE64: GS 长期 DES 密钥的 Base64 文本
"""

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
class GsConfig:
    """GS 运行配置。"""

    host: str
    port: int
    gs_service_name: str
    authenticator_window_seconds: int
    k_gs_base64: str


def _required_env(name: str) -> str:
    """读取并校验 _required_env 相关的 GS 配置。"""
    value = os.getenv(name)
    if value is None or value.strip() == "":
        raise ConfigError(f"missing required environment variable: {name}")
    return value.strip()


def _int_env(name: str, default: int) -> int:
    """读取并校验 _int_env 相关的 GS 配置。"""
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


def load_gs_config() -> GsConfig:
    """加载 GS 协议、监听地址和长期密钥配置。"""
    gs_service_name = (
        os.getenv("AUTH_GS_SERVICE_NAME", "game/ws@127.0.0.1:8765").strip()
        or "game/ws@127.0.0.1:8765"
    )
    return GsConfig(
        host=os.getenv("GS_HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=_int_env("GS_PORT", 8765),
        gs_service_name=gs_service_name,
        authenticator_window_seconds=_int_env("AUTH_AUTHENTICATOR_WINDOW_SECONDS", 30),
        k_gs_base64=_required_env("K_GS_BASE64"),
    )
