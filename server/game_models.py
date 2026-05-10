"""GS 服务端数据模型——客户端会话 / 空投 / 平台 / 投射物 / 近战判定盒 / 事件 / 输入载荷。"""

from dataclasses import dataclass, field
from typing import List, Optional, Set

from game_config import (
    DEFAULT_BASE_KNOCKBACK,
    DEFAULT_KNOCKBACK_GROWTH,
    DEFAULT_WEIGHT,
    GROUND_Y,
)


@dataclass
class ServerLoot:
    """空投物（武器或效果道具）。

    从地图上方 LOOT_SPAWN_Y 高度生成，受 LOOT_GRAVITY 重力下落，
    碰到平台时 landed=True 停止下落。
    """
    loot_id: str
    loot_type: str  # "effect" / "weapon"
    item_id: str    # effectId（如 "delayed_explosion"）或 weaponId（如 "重机枪"）
    pos_x: float
    pos_y: float    # 空投中心 y，不是 footY
    radius: float = 0.75
    alive: bool = True

    vel_y: float = 0.0
    landed: bool = False
    target_platform_y: float = 0.0  # 落地时平台的 y 坐标


@dataclass
class Platform:
    """地图平台——角色可站立的面。

    kind="solid"：不可下穿的实体地面。
    kind="oneway"：单向平台，按下+方向键可从上方穿过。
    """
    x_min: float
    x_max: float
    y: float       # 平台表面 y 坐标
    kind: str      # "solid" | "oneway"


@dataclass
class RectCollider:
    """矩形碰撞体——用于墙壁碰撞检测。"""
    x_min: float
    x_max: float
    y_min: float
    y_max: float
    kind: str  # "solid"


@dataclass
class ClientSession:
    """GS 客户端会话——贯穿整个连接生命周期的服务端权威状态。

    分为三层：
    1. Kerberos 认证状态：authenticated / session_id / user_id / kc_gs / login_gen
    2. 房间/对战状态：client_id / room_id / last_seq / accepted_*（服务端确认的状态）
    3. 战斗属性：pos_* / vel_* / damage_percent / stocks / hitstun / 武器/效果
    """
    # ── Kerberos 认证状态 ──
    authenticated: bool = False
    session_id: Optional[str] = None   # GS 签发的业务会话 ID（格式: sess-{userId}-{8hex}）
    user_id: Optional[int] = None      # user_account.user_id
    username: Optional[str] = None
    kc_gs: Optional[bytes] = None      # 与该客户端共享的 DES 会话密钥（来自 ServiceTicket）
    login_gen: int = 0                 # 登录代数，与 user_account.login_gen 比对，防止密码修改后旧 session 仍可用

    # ── 房间/对战状态 ──
    client_id: Optional[str] = None    # "Client1" 或 "Client2"（对战中的标识）
    room_id: Optional[str] = None

    last_seq: int = -1                 # 最近接收的输入序列号，用于拒绝乱序/重复输入
    accepted_state: str = "Grounded"   # 服务端确认的玩家状态：Grounded / Jump / Fall / Hitstun / Dead / Dash
    accepted_grounded: bool = True
    accepted_jump_count: int = 0       # 服务端确认的当前连跳次数
    accepted_drop: bool = False        # 是否正处于下穿平台状态

    # ── 物理状态（服务端权威）──
    pos_x: float = 0.0                 # footX
    pos_y: float = GROUND_Y            # footY
    vel_x: float = 0.0
    vel_y: float = 0.0

    facing: int = 1                    # +1 朝右，-1 朝左
    aim_x: float = 1.0                 # 瞄准方向 x（归一化）
    aim_y: float = 0.0                 # 瞄准方向 y（归一化）

    # ── 战斗属性（服务端权威）──
    stocks: int = 3                    # 剩余生命数
    is_dead: bool = False
    respawn_at_tick: int = -1          # 计划重生 tick（-1 表示不在等待重生）
    damage_percent: float = 0.0        # 伤害累积百分比（大乱斗机制：越高击飞越远）
    weight: float = DEFAULT_WEIGHT     # 体重（越大击飞越近）
    knockback_growth: float = DEFAULT_KNOCKBACK_GROWTH  # 击飞增长率（越大高伤害时击飞越远）
    base_knockback: float = DEFAULT_BASE_KNOCKBACK      # 基础击飞力

    last_knockback_x: float = 0.0      # 最近一次受击的击飞向量 x
    last_knockback_y: float = 0.0      # 最近一次受击的击飞向量 y
    last_hit_tick: int = -1            # 最近一次受击的 tick
    hitstun_until_tick: int = -1       # 受击硬直持续到 tick（硬直期间无法移动/跳跃/攻击）
    equipped_weapon_id: str = "手枪"   # 当前装备的武器
    equipped_effect_ids: List[str] = field(default_factory=list)  # 当前装备的效果道具

    attack_hold_ticks: int = 0         # 攻击键持续按住 tick 数（用于连发武器自动开火控制）
    last_attack_tick: int = -999999    # 最近一次攻击执行的 tick（用于攻击间隔控制）
    last_attack_weapon_id: str = ""    # 最近一次攻击使用的武器（切换武器时重置间隔）


@dataclass
class ServerProjectile:
    """服务端投射物——远程武器的子弹/弹丸。

    由 spawn_projectile() 从武器配置生成，每帧 step_projectiles() 推进。
    扫掠碰撞（swept AABB）检测世界碰撞和玩家碰撞，命中后 alive=False。
    """
    proj_id: int                  # 全局唯一投射物 ID
    owner_client_id: str          # 发射者 ClientId
    weapon_id: str                # 发射武器 ID
    effect_ids: List[str]         # 附加效果 ID 列表

    pos_x: float
    pos_y: float
    vel_x: float
    vel_y: float

    radius: float                 # 碰撞半径
    damage: float                 # 命中伤害
    base_knockback: float         # 基础击退力
    ttl: float                    # 存活时间（秒），到期自动销毁

    alive: bool = True
    timer: float = 0.0            # 已存活时间
    state: str = "Flying"
    bullet_id: str = ""           # 子弹类型 ID（用于 effect 判断）
    visual_id: str = ""           # 客户端渲染 ID
    rotation_deg: float = 0.0     # 旋转角度（度）
    # hover_split 效果专用状态
    hover_split_initialized: bool = False
    hover_split_start_vel_x: float = 0.0
    hover_split_start_vel_y: float = 0.0
    hover_split_start_speed: float = 0.0
    hover_split_base_dir_x: float = 1.0
    hover_split_base_dir_y: float = 0.0
    hover_split_done: bool = False


@dataclass
class ServerMeleeHitbox:
    """服务端近战判定盒——圆形区域，在攻击者前方生成，短暂存活。

    hit_once=True 时命中一个目标即销毁；False 时可命中多个目标。
    hit_targets 集合防止同一次攻击重复命中同一目标。
    """
    hitbox_id: int
    owner_client_id: str
    weapon_id: str
    effect_ids: List[str]

    center_x: float
    center_y: float
    radius: float

    damage: float
    base_knockback: float
    ttl: float                   # 存活时间

    hit_once: bool = True         # 是否命中一次即消失
    hit_targets: Set[str] = field(default_factory=set)  # 已命中的目标 clientId 集合

    alive: bool = True
    timer: float = 0.0


@dataclass
class MatchEvent:
    """一帧内发生的游戏事件，在快照中广播给客户端。"""
    event_type: str     # PLAYER_HIT / PROJECTILE_SPAWNED / EXPLOSION_TRIGGERED / LOOT_PICKED 等
    event_seq: int      # 事件序号
    data: dict          # 事件负载数据


@dataclass
class InputPayload:
    """客户端上传的输入载荷——解密后的明文结构。

    client_* 字段是客户端本地预测结果，仅供参考，不参与服务端判决（服务端权威）。
    seq 必须严格递增——服务端拒绝重复和乱序输入。
    attack_* 三个独立标志支持按住连发/单击单发/释放重置。
    """
    seq: int = 0                  # 输入序列号，必须严格递增
    tick: int = 0                 # 客户端本地 tick

    # ── 移动/跳跃/下穿 ──
    move_x: float = 0.0           # 水平移动输入 [-1.0, 1.0]
    jump_pressed: bool = False    # 跳跃键按下
    down_held: bool = False       # 下键按住
    drop_pressed: bool = False    # 下穿键（下+方向键）按下

    # ── 攻击 ──
    attack_pressed: bool = False  # 攻击键按下（单发）
    attack_held: bool = False     # 攻击键按住（连发）
    attack_released: bool = False # 攻击键释放（重置蓄力/连发状态）

    # ── 瞄准 ──
    aim_x: float = 0.0
    aim_y: float = 0.0

    # ── 客户端预测状态（仅供参考，服务端不据此判决）──
    client_state: str = "Unknown"
    client_grounded: bool = False
    client_jump_count: int = 0
    client_pos_x: float = 0.0
    client_pos_y: float = 0.0
    client_vel_x: float = 0.0
    client_vel_y: float = 0.0
    equipped_weapon_id: str = "手枪"
    equipped_effect_ids: List[str] = field(default_factory=list)
