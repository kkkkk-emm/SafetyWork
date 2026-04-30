"""TGS WebSocket 基本链路 smoke test。

本脚本先通过 AS 注册并登录一个随机用户，拿到 TGT 和 KcTgs，再向 TGS
申请 Service Ticket，并解密校验 TGS_REP。

运行前置条件:
- 已启动 AS 服务。
- 已启动 TGS 服务。
- 已初始化 as/schema_auth.sql 中的两张表。
- 已设置 K_GS_BASE64，脚本会用它解密 Service Ticket 做断言。
"""

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import secrets
from typing import Any

import websockets

from crypto_utils import b64decode, des_decrypt_object, des_encrypt_object
from protocol import TYPE_ERROR, TYPE_TGS_REP, TYPE_TGS_REQ, loads_json, make_message
from tgs_server import now_ms


AS_URL = os.getenv("AS_URL", "ws://127.0.0.1:9000")
TGS_URL = os.getenv("TGS_URL", "ws://127.0.0.1:9001")
GS_SERVICE_NAME = os.getenv("AUTH_GS_SERVICE_NAME", "game/ws@127.0.0.1:8765")
PUBLIC_KEY_PATH = Path(
    os.getenv(
        "AS_PUBLIC_KEY_PATH",
        str(Path(__file__).resolve().parents[1] / "as" / "as_public_key.pem"),
    )
)


def load_as_crypto() -> Any:
    """以独立模块名加载 as/crypto_utils.py。"""

    as_crypto_path = Path(__file__).resolve().parents[1] / "as" / "crypto_utils.py"
    spec = importlib.util.spec_from_file_location("as_crypto_utils_for_tgs", as_crypto_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load AS crypto utils from {as_crypto_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_public_key() -> bytes:
    """读取 AS 公钥 PEM。"""

    if not PUBLIC_KEY_PATH.exists():
        raise FileNotFoundError(
            f"AS public key not found: {PUBLIC_KEY_PATH}. Run as/seed_auth_keys.py first."
        )
    return PUBLIC_KEY_PATH.read_bytes()


async def request(ws: Any, message: str, service_name: str) -> dict:
    """发送一条请求并要求返回非 ERROR 响应。"""

    await ws.send(message)
    raw = await ws.recv()
    msg = loads_json(raw)
    if msg.get("type") == TYPE_ERROR:
        raise AssertionError(f"{service_name} returned ERROR: {msg.get('error')}")
    return msg


def encrypted_as_message(
    as_crypto: Any,
    public_key: bytes,
    msg_type: str,
    client_id: str,
    payload: dict,
) -> str:
    """构造带 RSA 加密 payload 的 AS 请求。"""

    return make_message(
        msg_type,
        clientId=client_id,
        payload=as_crypto.rsa_encrypt_object(public_key, payload),
    )


def decode_as_part(as_crypto: Any, password: str, response: dict) -> dict:
    """解密 AS_REP.payload.part。"""

    payload = json.loads(response["payload"])
    salt = as_crypto.b64decode(payload["salt"])
    iterations = int(payload["iter"])
    kuser = as_crypto.derive_kuser(password, salt, iterations)
    return as_crypto.des_decrypt_object(kuser, payload["part"])


async def main() -> None:
    """执行完整 AS -> TGS smoke test。"""

    as_crypto = load_as_crypto()
    public_key = load_public_key()
    suffix = secrets.token_hex(5)
    username = f"tgs_smoke_{suffix}"
    password = "SmokePass1"
    client_id = f"cli-tgs-smoke-{suffix}"

    k_gs_base64 = os.getenv("K_GS_BASE64", "").strip()
    if not k_gs_base64:
        raise EnvironmentError("K_GS_BASE64 is required to verify the Service Ticket")
    k_gs = b64decode(k_gs_base64)

    async with websockets.connect(AS_URL) as as_ws:
        register_response = await request(
            as_ws,
            encrypted_as_message(
                as_crypto,
                public_key,
                "REGISTER_REQ",
                client_id,
                {"username": username, "password": password},
            ),
            "AS",
        )
        if register_response.get("type") != "REGISTER_REP":
            raise AssertionError(f"expected REGISTER_REP, got {register_response}")

        as_nonce = f"as-{suffix}"
        login_response = await request(
            as_ws,
            encrypted_as_message(
                as_crypto,
                public_key,
                "AS_REQ",
                client_id,
                {"username": username, "password": password, "nonce": as_nonce},
            ),
            "AS",
        )
        if login_response.get("type") != "AS_REP":
            raise AssertionError(f"expected AS_REP, got {login_response}")

    as_part = decode_as_part(as_crypto, password, login_response)
    if as_part.get("nonce") != as_nonce:
        raise AssertionError("AS_REP nonce mismatch")

    kc_tgs = b64decode(str(as_part["kcTgs"]))
    auth_nonce = f"auth-{suffix}"
    payload_nonce = f"payload-{suffix}"
    auth = des_encrypt_object(
        kc_tgs,
        {
            "ts": now_ms(),
            "nonce": auth_nonce,
        },
    )
    payload = des_encrypt_object(
        kc_tgs,
        {
            "service": GS_SERVICE_NAME,
            "nonce": payload_nonce,
        },
    )

    async with websockets.connect(TGS_URL) as tgs_ws:
        tgs_response = await request(
            tgs_ws,
            make_message(
                TYPE_TGS_REQ,
                clientId=client_id,
                ticket=login_response["ticket"],
                auth=auth,
                payload=payload,
            ),
            "TGS",
        )

    if tgs_response.get("type") != TYPE_TGS_REP:
        raise AssertionError(f"expected TGS_REP, got {tgs_response}")

    protected_payload = des_decrypt_object(kc_tgs, tgs_response["payload"])
    if protected_payload.get("nonce") != payload_nonce:
        raise AssertionError("TGS_REP payload nonce mismatch")
    if not protected_payload.get("kcGs"):
        raise AssertionError("TGS_REP payload missing kcGs")

    service_ticket = des_decrypt_object(k_gs, tgs_response["ticket"])
    checks = {
        "ticketType": "SERVICE_TICKET",
        "realm": os.getenv("AUTH_REALM", "SAFETYWORK"),
        "clientId": client_id,
        "service": GS_SERVICE_NAME,
        "kcGs": protected_payload["kcGs"],
    }
    for key, expected in checks.items():
        if service_ticket.get(key) != expected:
            raise AssertionError(
                f"Service Ticket {key} mismatch: {service_ticket.get(key)} != {expected}"
            )

    if int(service_ticket["userId"]) != int(as_part["userId"]):
        raise AssertionError("Service Ticket userId mismatch")
    if int(service_ticket["loginGen"]) != int(as_part["loginGen"]):
        raise AssertionError("Service Ticket loginGen mismatch")
    if int(service_ticket["exp"]) != int(protected_payload["exp"]):
        raise AssertionError("Service Ticket exp mismatch")
    if int(service_ticket["exp"]) > int(as_part["exp"]):
        raise AssertionError("Service Ticket exp exceeds TGT exp")

    print("TGS smoke test passed")


if __name__ == "__main__":
    asyncio.run(main())
