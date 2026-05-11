from __future__ import annotations

from typing import Any, Dict, Optional, Protocol, Set

from game_models import ClientSession, Platform, ServerLoot


class RelayServerContext(Protocol):
    """声明各个 Relay mixin 依赖的 RelayServer 属性和方法契约。"""

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

    def encrypt_payload(self, session: ClientSession, obj: Dict[str, Any]) -> str:
        """使用会话密钥加密要返回给该客户端的业务载荷。"""
        ...

    def decrypt_auth(
        self, session: ClientSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解密并校验请求中的认证字段。"""
        ...

    def decrypt_payload(
        self, session: ClientSession, data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """解密客户端发送的业务载荷。"""
        ...

    def _require_session(self, websocket: Any) -> ClientSession:
        """从 websocket 查找已认证会话，缺失时抛出业务错误。"""
        ...

    async def send_json(self, websocket: Any, payload: Dict[str, Any]) -> None:
        """向指定 websocket 发送 JSON 消息。"""
        ...

    async def send_error(self, websocket: Any, error_message: str) -> None:
        """向客户端发送明文错误消息。"""
        ...

    async def close_and_forget_socket(
        self, websocket: Any, reason: str = "replaced"
    ) -> None:
        """关闭连接并清理服务器端 socket 关联状态。"""
        ...

    def remove_from_room(self, websocket: Any, room_id: str) -> None:
        """把 socket 从指定房间成员集合中移除。"""
        ...

    async def broadcast_room_state(self, room_id: str) -> None:
        """向房间成员广播最新房间状态。"""
        ...

    async def broadcast_game_start(self, room_id: str) -> None:
        """向房间成员广播游戏开始消息。"""
        ...

    async def broadcast_snapshot(
        self,
        room_id: str,
        reject_reason_by_socket: Optional[Dict[Any, str]] = None,
    ) -> None:
        """向房间成员广播当前游戏快照。"""
        ...

    async def broadcast_result(
        self, room_id: str, winner_user_id: int, reason: str, players: list[Any]
    ) -> None:
        """向房间成员广播对局结果。"""
        ...

    async def send_snapshot(
        self, websocket: Any, session: ClientSession, reject_reason: str
    ) -> None:
        """向单个客户端发送当前快照。"""
        ...

    async def remove_player_from_room_state(
        self, websocket: Any, room_id: str
    ) -> None:
        """从房间状态中移除指定玩家并处理相关广播。"""
        ...

    async def _internal_join_room(
        self, websocket: Any, data: Dict[str, Any]
    ) -> None:
        """执行创建房间和加入房间共用的入房逻辑。"""
        ...

    def generate_room_id(self) -> str:
        """生成新的房间 ID。"""
        ...

    def get_or_create_room_state(
        self, room_id: str, host_client_id: str
    ) -> Dict[str, Any]:
        """获取已有房间状态或创建初始状态。"""
        ...

    def allocate_slot_no(
        self, room_state: Dict[str, Any], _requested: str = ""
    ) -> int:
        """为玩家分配房间内座位号。"""
        ...

    def build_room_state_payload(
        self, room_id: str, local_session: Optional[ClientSession] = None
    ) -> dict[str, Any]:
        """构造可发送给客户端的房间状态载荷。"""
        ...

    def build_snapshot_payload(
        self, session: ClientSession, reject_reason: str
    ) -> dict[str, Any]:
        """构造可发送给客户端的游戏快照载荷。"""
        ...

    def get_room_loots(self, room_id: str) -> Dict[str, ServerLoot]:
        """获取指定房间当前存活的道具集合。"""
        ...

    def choose_random_loot_x(self) -> float:
        """选择一个用于生成道具的随机横坐标。"""
        ...

    def find_loot_landing_platform_y(
        self, x: float, previous_y: float, next_y: float
    ) -> Optional[float]:
        """计算道具下落路径上会落到的平台高度。"""
        ...

    def apply_loot_to_session(
        self, session: ClientSession, loot: ServerLoot
    ) -> None:
        """把道具效果应用到玩家会话。"""
        ...

    def hits_wall(self, x: float, y: float) -> bool:
        """判断坐标是否与地图墙体或阻挡物碰撞。"""
        ...

    def step_vertical(self, session: ClientSession) -> None:
        """推进玩家竖直方向的物理状态。"""
        ...

    def get_standing_platform(self, session: ClientSession) -> Optional[Platform]:
        """查找玩家当前站立的平台。"""
        ...

    @staticmethod
    def utc_now_iso() -> str:
        """返回当前 UTC 时间的 ISO 字符串。"""
        ...
