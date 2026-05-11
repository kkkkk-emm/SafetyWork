"""GS 统一错误处理 Mixin。

所有业务 handler 的异常在此统一捕获，转换为 ERROR 报文回复客户端：
- ProtocolError → 协议层错误（字段缺失/类型错误）→ JSON 层直接返回对应 errorCode
- GsRequestError → 业务错误（认证失败/房间满等）→ 返回对应错误码
- CryptoError → 密码学错误（解密失败/B64 无效）→ 返回错误信息
- 未预期 Exception → 打印堆栈，返回 INTERNAL_ERROR（不泄露内部细节给客户端）
"""

from __future__ import annotations

import sys
from typing import Any, Awaitable

from crypto_utils import CryptoError
from gs_errors import GsRequestError
from gs_protocol import ProtocolError
from relay_contracts import RelayServerContext


class GsErrorHandlingMixin:
    """封装 GsErrorHandlingMixin 相关的 GS 错误响应和审计逻辑。"""
    async def run_with_error_response(
        self: RelayServerContext,
        websocket: Any,
        label: str,
        action: Awaitable[Any],
    ) -> bool:
        """执行 handler，捕获所有异常并转为 ERROR 报文。"""
        try:
            await action
            return True
        except ProtocolError as exc:
            await self.send_error(websocket, exc.error_code)
        except GsRequestError as exc:
            await self.send_error(websocket, exc.error_code)
        except CryptoError as exc:
            await self.send_error(websocket, str(exc))
        except Exception as exc:
            print(f"{label} internal error: {exc}", file=sys.stderr)
            await self.send_error(websocket, "INTERNAL_ERROR")
        return True
