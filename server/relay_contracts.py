from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, Set

from game_models import ClientSession, Platform, ServerLoot


class RelayServerContext(Protocol):
    sessions: Dict[Any, ClientSession]
    sessions_by_id: Dict[str, ClientSession]
    reconnect_grace: Dict[str, Dict[str, Any]]
    rooms: Dict[str, Set[Any]]
    room_states: Dict[str, Dict[str, Any]]
    room_loots: Dict[str, Dict[str, ServerLoot]]
    room_next_loot_tick: Dict[str, int]
    tick: int
    combat: Any
    next_loot_id: int
    db: Any

    def encrypt_payload(self, session: ClientSession, obj: Dict[str, Any]) -> str: ...

    def decrypt_auth(
        self, session: ClientSession, data: Dict[str, Any]
    ) -> Dict[str, Any]: ...

    def decrypt_payload(
        self, session: ClientSession, data: Dict[str, Any]
    ) -> Dict[str, Any]: ...

    def _require_session(self, websocket: Any) -> ClientSession: ...

    async def send_json(self, websocket: Any, payload: Dict[str, Any]) -> None: ...

    async def send_error(self, websocket: Any, error_message: str) -> None: ...

    async def close_and_forget_socket(
        self, websocket: Any, reason: str = "replaced"
    ) -> None: ...

    def remove_from_room(self, websocket: Any, room_id: str) -> None: ...

    async def broadcast_room_state(self, room_id: str) -> None: ...

    async def broadcast_game_start(self, room_id: str) -> None: ...

    async def broadcast_snapshot(
        self,
        room_id: str,
        reject_reason_by_socket: Optional[Dict[Any, str]] = None,
    ) -> None: ...

    async def broadcast_result(
        self, room_id: str, winner_user_id: int, reason: str, players: list[Any]
    ) -> None: ...

    async def send_snapshot(
        self, websocket: Any, session: ClientSession, reject_reason: str
    ) -> None: ...

    async def remove_player_from_room_state(
        self, websocket: Any, room_id: str
    ) -> None: ...

    async def _internal_join_room(
        self, websocket: Any, data: Dict[str, Any]
    ) -> None: ...

    def generate_room_id(self) -> str: ...

    def get_or_create_room_state(
        self, room_id: str, host_client_id: str
    ) -> Dict[str, Any]: ...

    def allocate_slot_no(
        self, room_state: Dict[str, Any], _requested: str = ""
    ) -> int: ...

    def build_room_state_payload(
        self, room_id: str, local_session: Optional[ClientSession] = None
    ) -> dict[str, Any]: ...

    def build_snapshot_payload(
        self, session: ClientSession, reject_reason: str
    ) -> dict[str, Any]: ...

    def get_room_loots(self, room_id: str) -> Dict[str, ServerLoot]: ...

    def choose_random_loot_x(self) -> float: ...

    def find_loot_landing_platform_y(
        self, x: float, previous_y: float, next_y: float
    ) -> Optional[float]: ...

    def apply_loot_to_session(
        self, session: ClientSession, loot: ServerLoot
    ) -> None: ...

    def hits_wall(self, x: float, y: float) -> bool: ...

    def step_vertical(self, session: ClientSession) -> None: ...

    def get_standing_platform(self, session: ClientSession) -> Optional[Platform]: ...

    @staticmethod
    def utc_now_iso() -> str: ...
