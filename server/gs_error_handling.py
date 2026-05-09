from __future__ import annotations

import sys
from typing import Any, Awaitable

from crypto_utils import CryptoError
from gs_errors import GsRequestError
from gs_protocol import ProtocolError


class GsErrorHandlingMixin:
    async def run_with_error_response(
        self,
        websocket: Any,
        label: str,
        action: Awaitable[Any],
    ) -> bool:
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
