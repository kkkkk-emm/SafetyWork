"""GS 物理模拟——重力 / 碰撞 / 平台检测 / 出界判定。

坐标系约定：
- pos_x/pos_y 是角色 foot 位置（脚底）
- 平台 y 是其表面坐标
- 玩家碰撞体：半宽 0.46m，全高 0.84m（footY 到顶部）
"""

from typing import List, Optional

from game_config import (
    BLAST_X_MAX,
    BLAST_X_MIN,
    BLAST_Y_MAX,
    BLAST_Y_MIN,
    FALL_SPEED_CAP,
    GRAVITY,
    GROUND_EPSILON,
    GROUND_Y,
    OFFSET_Y,
    PLAYER_HALF_HEIGHT,
    PLAYER_HALF_WIDTH,
    SIM_DT,
)
from game_models import ClientSession, Platform, RectCollider


# ── 地图定义：6 个平台 + 2 面墙壁 ──
# solid 平台：不可穿过，脚踏实地
# oneway 平台：单向，可从下方跳上，可按"下+方向键"从上方穿过
MAP_PLATFORMS: List[Platform] = [
    Platform(x_min=-9, x_max=29, y=GROUND_Y, kind="solid"),       # 地面（全场宽）
    Platform(x_min=-1.2, x_max=1.2, y=1.0 + OFFSET_Y, kind="oneway"),     # 左中平台
    Platform(x_min=8.8, x_max=11.2, y=1.0 + OFFSET_Y, kind="oneway"),     # 中间平台
    Platform(x_min=18.8, x_max=21.2, y=1.0 + OFFSET_Y, kind="oneway"),    # 右中平台
    Platform(x_min=3.8, x_max=6.2, y=2.5 + OFFSET_Y, kind="oneway"),      # 左上平台
    Platform(x_min=13.8, x_max=16.2, y=2.5 + OFFSET_Y, kind="oneway"),    # 右上平台
]

MAP_WALLS: List[RectCollider] = [
    RectCollider(x_min=-9.5, x_max=-8.5, y_min=GROUND_Y, y_max=GROUND_Y + 1.5, kind="solid"),  # 左墙
    RectCollider(x_min=28.5, x_max=29.5, y_min=GROUND_Y, y_max=GROUND_Y + 1.5, kind="solid"),  # 右墙
]


def hits_wall(x: float, y: float) -> bool:
    """检测角色在 (x,y) 位置是否与地图墙壁重叠。AABB 重叠检测。"""
    # 计算角色覆盖范围
    player_left = x - PLAYER_HALF_WIDTH
    player_right = x + PLAYER_HALF_WIDTH
    player_bottom = y
    player_top = y + PLAYER_HALF_HEIGHT * 2.0

    for wall in MAP_WALLS:
        overlap_x = player_right > wall.x_min and player_left < wall.x_max
        overlap_y = player_top > wall.y_min and player_bottom < wall.y_max
        if overlap_x and overlap_y:
            return True

    return False


def step_vertical(session: ClientSession) -> None:
    """垂直运动一帧：如果着地则站在平台上，否则施加重力下落。

    着陆检测使用 swept 方式：检测 footY 是否在上一帧↔下一帧之间穿过了平台表面。
    """
    standing = get_standing_platform(session)
    if standing is not None and session.accepted_grounded and session.vel_y <= 0.0:
        session.pos_y = standing.y
        session.vel_y = 0.0
        return

    # 施加重力并限制最大下落速度（终端速度）
    session.vel_y += GRAVITY
    if session.vel_y < FALL_SPEED_CAP:
        session.vel_y = FALL_SPEED_CAP

    previous_y = session.pos_y
    next_y = session.pos_y + session.vel_y * SIM_DT

    # swept 着陆检测：footY 从 previous 到 next 是否穿过平台表面
    landing = find_landing_platform(session.pos_x, previous_y, next_y)
    if landing is not None and session.vel_y <= 0:
        session.pos_y = landing.y
        session.vel_y = 0.0
        session.accepted_grounded = True
        if session.accepted_state not in ("Dash", "BasicAttack", "Hitstun"):
            session.accepted_state = "Grounded"
    else:
        session.pos_y = next_y
        session.accepted_grounded = False
        if session.vel_y < 0 and session.accepted_state not in (
            "Jump",
            "Dash",
            "BasicAttack",
            "Hitstun",
        ):
            session.accepted_state = "Fall"


def get_standing_platform(session: ClientSession) -> Optional[Platform]:
    """返回角色当前站立所在的平台（footY 在平台表面容差内），无则 None。"""
    for platform in MAP_PLATFORMS:
        if is_on_platform(session.pos_x, session.pos_y, platform):
            return platform
    return None


def is_on_platform(x: float, y: float, platform: Platform) -> bool:
    """角色 foot 是否在平台表面上（x 范围内 + y 在 GROUND_EPSILON 容差内）。"""
    within_x = (x + PLAYER_HALF_WIDTH) >= platform.x_min and (
        x - PLAYER_HALF_WIDTH
    ) <= platform.x_max
    close_y = abs(y - platform.y) <= GROUND_EPSILON
    return within_x and close_y


def find_landing_platform(
    x: float, previous_y: float, next_y: float
) -> Optional[Platform]:
    """swept 着陆检测：footY 从 previous_y 降到 next_y 的过程中是否穿过某平台表面。

    返回 y 最高的穿越平台（防止同时穿过多个平台时选错的平台）。
    """
    candidates: List[Platform] = []

    for platform in MAP_PLATFORMS:
        within_x = (x + PLAYER_HALF_WIDTH) >= platform.x_min and (
            x - PLAYER_HALF_WIDTH
        ) <= platform.x_max
        crossed_y = previous_y >= platform.y >= next_y  # foot 穿过了平台表面
        if within_x and crossed_y:
            candidates.append(platform)

    if not candidates:
        return None

    # 多个平台同时穿越时，取最高的（最大的 y）
    candidates.sort(key=lambda p: p.y, reverse=True)
    return candidates[0]


def is_out_of_bounds(x: float, y: float) -> bool:
    """角色是否出界（被击出场外）。触发出界 → 扣一条命。"""
    return x < BLAST_X_MIN or x > BLAST_X_MAX or y < BLAST_Y_MIN or y > BLAST_Y_MAX
