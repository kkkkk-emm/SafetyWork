# GS 游戏服务器使用说明

本目录实现独立的 GS(Game Server) 游戏服务器。GS 通过 WebSocket 接收 JSON 报文，包含 Kerberos 认证门禁（`GS_AUTH`）、房间管理、对战同步和断线重连。

当前版本是完整实现，依赖 AS、TGS 和共享的 MySQL 认证数据库。所有游戏状态（房间、对战、空投）只在 GS 内存中维护，不写入 MySQL。数据库仅用于读取 `user_account` 校验 `login_gen`/`status`，以及写入 `security_event_log`。

## 目录文件

| 文件 | 作用 |
| --- | --- |
| `ws_server.py` | 命令行入口，创建 `RelayServer` 并启动服务。 |
| `relay_server.py` | GS 核心逻辑，处理所有 WebSocket 消息（认证、房间、对战、重连）。 |
| `gs_config.py` | 读取数据库、监听地址、密钥等环境变量配置。 |
| `gs_db.py` | MySQL DAO，只读 `user_account`，只写 `security_event_log`。 |
| `gs_protocol.py` | JSON 协议报文构造、解析和字段校验工具。 |
| `crypto_utils.py` | Base64、DES、nonce 生成等密码学工具函数。 |
| `game_models.py` | 数据模型：`ClientSession`、`InputPayload`、`Platform`、`ServerLoot` 等。 |
| `game_config.py` | 游戏常量：物理参数、武器库、空投配置、快照节流等。 |
| `game_combat.py` | 战斗系统：攻击执行、投射物推进、碰撞检测、命中判定。 |
| `game_effects.py` | 武器效果系统：爆炸、分裂弹、停留弹等特殊效果。 |
| `game_simulation.py` | 物理模拟：重力、碰撞、出界判定、平台检测。 |
| `requirements.txt` | Python 依赖列表。 |

## 运行前置条件

需要准备：

- Python 3.9+。
- MySQL 8.x 或兼容版本，已按 `as/schema_auth.sql` 初始化 `user_account` 和 `security_event_log` 表。
- 已启动 AS 服务。
- 已启动 TGS 服务。
- AS、TGS 和 GS 使用同一个认证数据库。
- 可以安装 `server/requirements.txt` 中依赖的 Python 环境。

安装依赖：

```powershell
python -m pip install -r .\server\requirements.txt
```

## 环境变量

### 必填变量

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `AUTH_DB_USER` | `root` | MySQL 用户名。 |
| `AUTH_DB_NAME` | `safety_auth` | 已初始化的认证数据库名。 |
| `K_GS_BASE64` | `yyyyyyyyyyy=` | TGS 和 GS 共享的长期 DES key，必须与 TGS 使用同一个值。解码后必须 8 字节。 |

### 可选变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTH_DB_HOST` | `127.0.0.1` | MySQL 地址。 |
| `AUTH_DB_PORT` | `3306` | MySQL 端口。 |
| `AUTH_DB_PASSWORD` | 空字符串 | MySQL 密码。 |
| `GS_HOST` | `0.0.0.0` | GS WebSocket 监听地址。 |
| `GS_PORT` | `8765` | GS WebSocket 监听端口。 |
| `AUTH_GS_SERVICE_NAME` | `game/ws@127.0.0.1:8765` | 本 GS 的服务标识，必须与 TGS 配置一致。 |
| `AUTH_AUTHENTICATOR_WINDOW_SECONDS` | `30` | Authenticator 时间戳和 nonce 防重放窗口（秒）。 |

生成 `K_GS_BASE64` 示例：

```powershell
python -c "import os,base64; print(base64.b64encode(os.urandom(8)).decode())"
```

### 游戏调参变量（可选，通常保持默认）

所有游戏常量集中在 `game_config.py` 中，核心可调参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `MOVE_SPEED` | 8.0 | 水平移动速度 (m/s)。 |
| `JUMP_VELOCITY` | 10.0 | 起跳初速度 (m/s)。 |
| `MAX_JUMP_COUNT` | 2 | 最大连跳次数。 |
| `SIM_DT` | 1/60 | 物理模拟步长 (秒)。 |
| `RECONNECT_GRACE_SECONDS` | 30 | 断线重连宽限期 (秒)。 |
| `MATCH_COUNTDOWN_MS` | 3000 | 开始对战的倒计时 (毫秒)。 |
| `SNAPSHOT_INTERVAL_TICKS` | 2 | 快照广播间隔 (tick 数)。 |
| `SNAPSHOT_THROTTLE_ENABLED` | `True` | 是否启用快照节流。 |
| `SNAPSHOT_FORCE_BROADCAST_ON_EVENTS` | `False` | 事件发生时是否强制立即广播快照。 |
| `LOOT_SPAWN_INTERVAL_TICKS` | 120 | 空投生成间隔。 |
| `LOOT_MAX_ALIVE` | 5 | 场上同时存在的最大空投数。 |
| `RESPAWN_DELAY_TICKS` | 120 | 死亡后重生等待 tick 数。 |

## 启动 GS

设置环境变量示例（与 TGS 使用同一个 `K_GS_BASE64`）：

```powershell
$env:AUTH_DB_HOST='127.0.0.1'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='root'
$env:AUTH_DB_PASSWORD='你的MySQL密码'
$env:AUTH_DB_NAME='safety_auth'

$env:K_GS_BASE64='与TGS服务相同的K_GS_BASE64'

$env:GS_HOST='0.0.0.0'
$env:GS_PORT='8765'
$env:AUTH_GS_SERVICE_NAME='game/ws@127.0.0.1:8765'
```

启动服务：

```powershell
python .\server\ws_server.py
```

启动成功会看到类似输出：

```text
====================================================================
[SERVER] GS 游戏服务启动: ws://0.0.0.0:8765
[SERVER] K_GS 已加载  gs_service=game/ws@127.0.0.1:8765
[SERVER] SIM_DT=0.016666666666666666 MOVE_SPEED=8.0
====================================================================
```

## 完整协议说明

所有 WebSocket 消息都是 UTF-8 JSON 字符串。顶层字段一般包含 `type`，已认证消息需携带 `sessionId`。

错误统一返回：

```json
{"type":"ERROR","error":"NOT_AUTHENTICATED"}
```

### 认证门禁

未认证的连接只能发送 `GS_AUTH` 或 `RECONNECT_REQ`，其他消息返回 `NOT_AUTHENTICATED`。

---

### GS_AUTH — 阶段三第 3-4 步

使用 Service Ticket 接入 GS，建立业务会话。

请求：

```json
{
  "type": "GS_AUTH",
  "clientId": "cli-a-001",
  "ticket": "Base64(DES(K_GS,ServiceTicket_JSON))",
  "auth": "Base64(DES(KcGs,{\"ts\":1776650510000,\"nonce\":\"n4\"}))"
}
```

成功响应：

```json
{
  "type": "GS_AUTH_OK",
  "sessionId": "sess-10001-a1b2c3d4",
  "payload": "Base64(DES(KcGs,{\"ts\":1776650510000,\"nonce\":\"n4\",\"exp\":1776657700100}))"
}
```

GS 验证步骤：

1. 用 `K_GS` 解密 Service Ticket。
2. 校验 `ticketType`、`clientId`、`service`、`exp`。
3. 查询 `user_account` 校验 `login_gen` 和 `status`。
4. 用 `KcGs` 解密 `auth`，校验 `ts` 窗口和 `nonce` 防重放。
5. 签发 `sessionId`，写入 `security_event_log`。

---

### ROOM_CREATE_REQ — 阶段四第 1 步

创建房间。

请求：

```json
{
  "type": "ROOM_CREATE_REQ",
  "sessionId": "sess-10001-a1b2c3d4",
  "auth": "Base64(DES(KcGs,{\"type\":\"ROOM_CREATE_REQ\",\"sessionId\":\"sess-10001-a1b2c3d4\",\"ts\":1776650520000,\"nonce\":\"n_room_create\"}))"
}
```

成功响应：

```json
{
  "type": "ROOM_CREATE_REP",
  "sessionId": "sess-10001-a1b2c3d4",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"ROOM_CREATE_REP\",\"ok\":true,\"sessionId\":\"sess-10001-a1b2c3d4\",\"roomId\":\"A7K9Q2\",\"ts\":...,\"nonce\":...}))"
}
```

---

### ROOM_JOIN_REQ — 阶段四第 4 步

加入房间。

请求：

```json
{
  "type": "ROOM_JOIN_REQ",
  "sessionId": "sess-b-9002",
  "roomId": "A7K9Q2",
  "auth": "Base64(DES(KcGs,{\"type\":\"ROOM_JOIN_REQ\",\"sessionId\":\"sess-b-9002\",\"roomId\":\"A7K9Q2\",\"ts\":1776650523000,\"nonce\":\"n_room_join\"}))"
}
```

成功响应：

```json
{
  "type": "ROOM_JOIN_REP",
  "sessionId": "sess-b-9002",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"ROOM_JOIN_REP\",\"ok\":true,\"sessionId\":\"sess-b-9002\",\"roomId\":\"A7K9Q2\",\"ts\":...,\"nonce\":\"n_room_join\"}))"
}
```

注意：`ROOM_JOIN_REP.payload.nonce` 回显 `ROOM_JOIN_REQ.auth.nonce`。

---

### ROOM_STATE — 权威房间状态广播

由 GS 主动推送，客户端不应自行推测房间成员。

```json
{
  "type": "ROOM_STATE",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"ROOM_STATE\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"state\":\"WAITING\",\"ownerUserId\":10001,\"hostClientId\":\"Client1\",\"players\":[{\"userId\":10001,\"username\":\"linhai\",\"clientId\":\"Client1\",\"slotNo\":1,\"ready\":false,\"online\":true},{\"userId\":10002,\"username\":\"xiaowang\",\"clientId\":\"Client2\",\"slotNo\":2,\"ready\":false,\"online\":true}],\"canStart\":false,\"localClientId\":\"Client1\",\"localSlotNo\":1,\"localIsHost\":true,\"ts\":...,\"nonce\":...}))"
}
```

ROOM_STATE 字段说明：

| 字段 | 说明 |
| --- | --- |
| `state` | `WAITING`（等待）、`STARTING`（开始倒计时）、`PLAYING`（对战中）、`FINISHED`（已结束） |
| `ownerUserId` | 房主的 `userId`。 |
| `hostClientId` | 房主的 `clientId`（`Client1` 或 `Client2`）。 |
| `players` | 成员列表，每项含 `userId`、`username`、`clientId`、`slotNo`、`ready`、`online`。 |
| `canStart` | 房主是否可以点击"开始游戏"。条件：`state == WAITING && 人数 >= 2 && 全部 ready`。 |
| `localClientId` | 当前接收者的 `clientId`。 |
| `localSlotNo` | 当前接收者的 `slotNo`（1 或 2）。 |
| `localIsHost` | 当前接收者是否为房主。 |

---

### ROOM_READY_REQ — 阶段四第 7/9 步

设置准备状态。

请求：

```json
{
  "type": "ROOM_READY_REQ",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"ROOM_READY_REQ\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"ready\":true,\"ts\":1776650526000,\"nonce\":\"n_ready_a\"}))"
}
```

成功响应：

```json
{
  "type": "ROOM_READY_REP",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"ROOM_READY_REP\",\"ok\":true,\"ready\":true,\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"ts\":...,\"nonce\":\"n_ready_a\"}))"
}
```

注意：`ROOM_READY_REP.payload.nonce` 回显 `ROOM_READY_REQ.payload.nonce`。

---

### ROOM_START_REQ — 阶段四第 11 步

房主发起开始游戏。

请求：

```json
{
  "type": "ROOM_START_REQ",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "auth": "Base64(DES(KcGs,{\"type\":\"ROOM_START_REQ\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"ts\":1776650530000,\"nonce\":\"n_room_start\"}))"
}
```

成功响应：

```json
{
  "type": "ROOM_START_REP",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"ROOM_START_REP\",\"ok\":true,\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"matchId\":\"match-888\",\"countdownMs\":3000,\"ts\":...,\"nonce\":...}))"
}
```

GS 校验：请求者为房主、人数 >= 2、全员 ready、房间处于 `WAITING`。

---

### INPUT — 阶段五第 1 步

上传玩家输入。每 tick 应发送一帧。

请求：

```json
{
  "type": "INPUT",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"INPUT\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"seq\":101,\"tick\":101,\"moveX\":1.0,\"jumpPressed\":false,\"downHeld\":false,\"dropPressed\":false,\"attackPressed\":true,\"attackHeld\":true,\"attackReleased\":false,\"aimX\":0.92,\"aimY\":0.38,\"clientState\":\"Player_BasicAttackState\",\"clientGrounded\":true,\"clientJumpCount\":0,\"clientPosX\":12.53,\"clientPosY\":3.0,\"clientVelX\":1.2,\"clientVelY\":0.0,\"equippedWeaponId\":\"normal_gun\",\"equippedEffectIds\":[\"delayed_explosion\"],\"ts\":1776650532000,\"nonce\":\"n_input_a_101\"}))"
}
```

INPUT 字段说明：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `seq` | int | 输入序列号，必须严格递增，GS 拒绝重复和乱序。 |
| `tick` | int | 客户端本地 tick。 |
| `moveX` | float | 水平输入 [-1.0, 1.0]。 |
| `jumpPressed` | bool | 跳跃键是否按下。 |
| `downHeld` | bool | 下键是否按住。 |
| `dropPressed` | bool | 下穿键（下+方向键）是否按下。 |
| `attackPressed` | bool | 攻击键是否按下。 |
| `attackHeld` | bool | 攻击键是否按住。 |
| `attackReleased` | bool | 攻击键是否释放（清除蓄力/连发状态）。 |
| `aimX` / `aimY` | float | 瞄准方向向量。 |
| `clientState` / `clientPosX` 等 | — | 客户端本地预测摘要，**仅供参考，不参与服务端判定**。 |

GS 安全校验：

- `seq` 必须严格递增，否则拒绝（`rejectReason="seq not increasing"`）。
- 禁止客户端上传 `damagePercent`、`stocks`、`isDead`、`damage`、`hitResult`、`killCount` 等服务端权威字段，否则拒绝。

没有对应的显式响应——GS 通过 `SNAPSHOT` 确认输入处理结果。

---

### SNAPSHOT — 阶段五第 4 步

GS 广播权威状态快照，客户端据此校正画面。

```json
{
  "type": "SNAPSHOT",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"SNAPSHOT\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"tick\":240,\"lastProcessedSeq\":101,\"rejectReason\":\"\",\"players\":[{...}],\"projectiles\":[{...}],\"loots\":[{...}],\"events\":[{...}],\"ts\":...,\"nonce\":...}))"
}
```

SNAPSHOT 核心字段：

| 字段 | 说明 |
| --- | --- |
| `tick` | 本次服务器权威 tick。 |
| `lastProcessedSeq` | 本客户端最近被确认处理的输入 seq。客户端应删除 <= 此值的未确认输入。 |
| `rejectReason` | 非空时表示本帧输入被拒绝的原因（撞墙、seq 乱序等）。 |
| `players[]` | 所有玩家权威状态（含 `posX/Y`、`velX/Y`、`damagePercent`、`stocks`、`isDead` 等）。 |
| `projectiles[]` | 飞行中的投射物。 |
| `loots[]` | 场地上的空投物。 |
| `events[]` | 本帧发生的游戏事件（`PLAYER_HIT`、`LOOT_PICKED`、`LOOT_SPAWNED` 等）。 |

快照广播策略：

- 默认每 2 tick 广播一次（`SNAPSHOT_INTERVAL_TICKS = 2`）。
- 当 `SNAPSHOT_FORCE_BROADCAST_ON_EVENTS = True` 时，有事件强制立即广播。
- 可在 `game_config.py` 中调整。

---

### HEARTBEAT_REQ / HEARTBEAT_REP — 阶段五第 5-6 步

连接保活。

请求：

```json
{
  "type": "HEARTBEAT_REQ",
  "sessionId": "sess-a-9001",
  "auth": "Base64(DES(KcGs,{\"type\":\"HEARTBEAT_REQ\",\"sessionId\":\"sess-a-9001\",\"ts\":1776650534000,\"nonce\":\"n_heartbeat_a_1\"}))"
}
```

响应：

```json
{
  "type": "HEARTBEAT_REP",
  "sessionId": "sess-a-9001",
  "payload": "Base64(DES(KcGs,{\"type\":\"HEARTBEAT_REP\",\"sessionId\":\"sess-a-9001\",\"ts\":1776650534000,\"nonce\":\"n_heartbeat_a_1\"}))"
}
```

注意：`HEARTBEAT_REP.payload.nonce` 回显 `HEARTBEAT_REQ.auth.nonce`。

---

### RESULT — 阶段五第 7 步

对局结束时 GS 广播结算结果。

```json
{
  "type": "RESULT",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"RESULT\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"winnerUserId\":10001,\"reason\":\"STOCK_ZERO\",\"players\":[{\"userId\":10001,\"stocksLeft\":2,\"finalDamagePercent\":88.5},{\"userId\":10002,\"stocksLeft\":0,\"finalDamagePercent\":126.0}],\"ts\":...,\"nonce\":...}))"
}
```

结束原因：

- `STOCK_ZERO`：对方生命数归零。
- `DRAW`：平局。

GS 广播 `RESULT` 后自动清理对战状态（投射物、空投、事件队列），房间状态变为 `FINISHED`。

---

### RECONNECT_REQ / RECONNECT_REP — 阶段六

断线后发起重连。

请求：

```json
{
  "type": "RECONNECT_REQ",
  "clientId": "cli-a-001",
  "sessionId": "sess-a-9001",
  "ticket": "Base64(ServiceTicket)",
  "auth": "Base64(DES(KcGs,{\"type\":\"RECONNECT_REQ\",\"clientId\":\"cli-a-001\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"ts\":1776650535000,\"nonce\":\"n5\"}))",
  "payload": "Base64(DES(KcGs,{\"type\":\"RECONNECT_REQ\",\"clientId\":\"cli-a-001\",\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"lastProcessedSeq\":108,\"ts\":1776650535000,\"nonce\":\"n5\"}))"
}
```

成功响应：

```json
{
  "type": "RECONNECT_REP",
  "sessionId": "sess-a-9001",
  "roomId": "A7K9Q2",
  "payload": "Base64(DES(KcGs,{\"type\":\"RECONNECT_REP\",\"ok\":true,\"sessionId\":\"sess-a-9001\",\"roomId\":\"A7K9Q2\",\"phase\":\"PLAYING\",\"lastProcessedSeq\":108,\"ts\":1776650536000,\"nonce\":\"n5\"}))"
}
```

重连机制说明：

- 对战中断线时，GS 将 session 放入重连宽限期（默认 30 秒），保留 `roomId`、`matchId`、`lastProcessedSeq`、比赛上下文。
- 在线玩家收到 `ROOM_STATE`（`online: false`）提示对方断线。
- 发起 `RECONNECT_REQ` 时，GS 重新验证 Service Ticket、`KcGs`、`auth` 和 `payload` 双重一致性。
- 重连成功后补发 `SNAPSHOT`，客户端据此恢复画面。
- 宽限期过期后 GS 清理 session 并记录 `RECONNECT_TIMEOUT` 安全事件。

---

### 其他消息类型

| 类型 | 方向 | 说明 |
| --- | --- | --- |
| `CHAT` | 双向 | 房间内聊天，GS 广播给所有成员。需要 `sessionId` + `text`。 |
| `LEAVE_ROOM` | 客户端 → GS | 主动离开房间，GS 清理玩家并广播更新后的 `ROOM_STATE`。 |

## 常见错误

| 错误码 | 含义 | 处理建议 |
| --- | --- | --- |
| `NOT_AUTHENTICATED` | 连接尚未通过 `GS_AUTH`。 | 先发 `GS_AUTH` 或 `RECONNECT_REQ`。 |
| `INVALID_TICKET` | Service Ticket 解密失败或字段错误。 | 确认 TGS/GS 使用同一个 `K_GS_BASE64`。 |
| `TICKET_EXPIRED` | Service Ticket 已过期。 | 重新走 TGS 流程获取新票据。 |
| `TICKET_INVALIDATED` | `login_gen` 不匹配（密码已改或被踢下线）。 | 重新登录。 |
| `ACCOUNT_DISABLED` | `user_account.status = 0`。 | 管理员启用账号后再试。 |
| `AUTH_EXPIRED` | Authenticator 时间戳超出窗口。 | 客户端检查本地时钟同步。 |
| `REPLAY_BLOCKED` | nonce 重复使用，疑似重放攻击。 | 确保每次请求使用新 nonce。 |
| `RECONNECT_EXPIRED` | 重连宽限期已过。 | 重新走 GS_AUTH 流程。 |
| `ROOM_FULL` | 房间已满（当前最多 2 人）。 | 等待或创建新房。 |
| `NOT_HOST` | 非房主尝试发起开始游戏。 | 只有房主可以开始。 |
| `NOT_ALL_READY` | 有玩家未准备。 | 等待全员 ready。 |
| `NEED_MORE_PLAYERS` | 人数不足（至少 2 人）。 | 等待更多玩家加入。 |
| `ROOM_NOT_WAITING` | 房间不在 `WAITING` 状态。 | 当前阶段不允许此操作。 |
| `SESSION_MISMATCH` | 顶层 `sessionId` 与加密 payload 内不一致。 | 检查客户端 session 缓存。 |
| `TYPE_MISMATCH` | 加密 payload/auth 内的 `type` 与顶层不一致。 | 检查协议实现。 |
| `KEY_NOT_CONFIGURED` | 服务端密钥未加载。 | 检查 `K_GS_BASE64` 环境变量。 |

## 安全注意事项

- `K_GS_BASE64` 是 TGS 和 GS 之间的长期共享密钥，不要提交到版本控制。
- Service Ticket 使用 `K_GS` 加密，客户端无法篡改其内容。
- 对战阶段所有 `payload` 和 `auth` 使用 `KcGs` 加密，包含 `ts` 和 `nonce` 防重放。
- GS 不信任客户端上传的位置、伤害、生命值等数据，全部以服务端权威计算为准。
- `seq` 严格递增校验防止客户端跳过帧或注入旧输入。
- 明文输入中的 `clientPosX`、`clientState` 等字段仅供参考，不参与服务端判决。
- 所有安全事件（认证成功/失败、票据过期、重放锁定、重连超时）写入 `security_event_log`。

## 推荐完整启动流程

```powershell
# ============================================
# 1. 安装所有依赖
# ============================================
python -m pip install -r .\as\requirements.txt
python -m pip install -r .\tgs\requirements.txt
python -m pip install -r .\server\requirements.txt

# ============================================
# 2. 初始化数据库（只需执行一次）
# ============================================
mysql -u root -p -e "CREATE DATABASE IF NOT EXISTS safety_auth DEFAULT CHARACTER SET utf8mb4 DEFAULT COLLATE utf8mb4_unicode_ci;"
cmd /c "mysql -u root -p safety_auth < as\schema_auth.sql"

# ============================================
# 3. 生成密钥（只需执行一次）
# ============================================
python .\as\seed_auth_keys.py
# 手动复制 as/k_tgs_base64.txt 内容，或生成 K_GS:
python -c "import os,base64; print(base64.b64encode(os.urandom(8)).decode())"

# ============================================
# 4. 设置公共环境变量（三个终端都需要）
# ============================================
$env:AUTH_DB_HOST='127.0.0.1'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='root'
$env:AUTH_DB_PASSWORD='你的MySQL密码'
$env:AUTH_DB_NAME='safety_auth'

$env:AUTH_GS_SERVICE_NAME='game/ws@127.0.0.1:8765'

# ============================================
# 5. 终端 1: 启动 AS（端口 9000）
# ============================================
$env:AS_RSA_PRIVATE_KEY_PATH='.\as\as_private_key.json'
$env:K_TGS_BASE64=(Get-Content .\as\k_tgs_base64.txt -Raw).Trim()
$env:AS_HOST='0.0.0.0'
$env:AS_PORT='9000'
python .\as\as_server.py

# ============================================
# 6. 终端 2: 启动 TGS（端口 9001）
# ============================================
$env:K_TGS_BASE64=(Get-Content .\as\k_tgs_base64.txt -Raw).Trim()
$env:K_GS_BASE64='把上面生成的K_GS Base64填到这里'
$env:TGS_HOST='0.0.0.0'
$env:TGS_PORT='9001'
python .\tgs\tgs_server.py

# ============================================
# 7. 终端 3: 启动 GS（端口 8765）
# ============================================
$env:K_GS_BASE64='与TGS相同的K_GS Base64'
$env:GS_HOST='0.0.0.0'
$env:GS_PORT='8765'
python .\server\ws_server.py
```

三个服务应该先后输出：

```text
AS server listening on ws://0.0.0.0:9000 realm=SAFETYWORK
TGS server listening on ws://0.0.0.0:9001 realm=SAFETYWORK gs=game/ws@127.0.0.1:8765
[SERVER] GS 游戏服务启动: ws://0.0.0.0:8765
```

此后客户端可依次执行：

```text
1. ws://127.0.0.1:9000 → REGISTER_REQ / AS_REQ
2. ws://127.0.0.1:9001 → TGS_REQ
3. ws://127.0.0.1:8765 → GS_AUTH
4. ws://127.0.0.1:8765 → ROOM_CREATE_REQ / ROOM_JOIN_REQ / ROOM_READY_REQ / ROOM_START_REQ
5. ws://127.0.0.1:8765 → INPUT（每帧）
6. 接收 ROOM_STATE / SNAPSHOT / RESULT
```

## 游戏战斗系统简要说明

GS 实现了简化版的大乱斗对战逻辑：

- **武器**：远程（手枪、步枪等）和近战（剑等），可配置伤害、击退、攻击间隔。
- **效果**：投射物可附加特殊效果（延迟爆炸、悬停分裂、穿透等）。
- **空投**：定时在平台上随机生成武器或效果道具，玩家靠近可拾取。
- **碰撞**：基于地图平台和墙壁的简化 AABB 碰撞检测。
- **击退**：伤害积累 `damagePercent` 越高，击退越远。
- **生命**：每局 3 条命，出界或死亡后延迟重生。
- **受击硬直**：受到攻击后有短暂硬直（`hitstun`），期间不能移动/跳跃/攻击。

所有武器、效果、地图参数可在 `game_config.py` 中配置。
# Handwritten crypto note

GS now uses project-local handwritten DES through `shared_crypto/`.
Regenerate AS RSA JSON keys with `python .\as\seed_auth_keys.py --overwrite`.
