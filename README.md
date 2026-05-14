# SafetyWork — 网络安全课程项目

基于 Kerberos-like 协议的多人 WebSocket 2D 平台对战游戏系统。

## 架构概览

```
客户端 ──> AS (认证服务器)  :9000  注册/登录/改密，获取 TGT + KcTgs
客户端 ──> TGS (票据服务器) :9001  凭 TGT 换取 ServiceTicket + KcGs
客户端 ──> GS (游戏服务器)  :8765  凭 ServiceTicket 接入房间/对战/重连
              │
              ▼
         MySQL (safety_auth)
         ├── user_account       (用户账号、密码摘要、login_gen、status)
         └── security_event_log (安全审计事件)
```

GS 所有游戏状态（房间、对战、空投、快照）只在内存中维护，不写入数据库。

## 目录

| 目录 | 说明 |
|---|---|
| `as/` | AS 认证服务器 — 注册/登录/改密/TGT 签发 (RSA + DES) |
| `tgs/` | TGS 票据授权服务器 — 验证 TGT，签发 ServiceTicket |
| `server/` | GS 游戏服务器 — Kerberos 门禁、房间管理、权威对战、断线重连、空投拾取 |
| `shared_crypto/` | 共享密码学实现 — 手写 DES/RSA/PBKDF2 |
| `tests/` | 单元测试 — 安全协议、加密、代码结构检验 |
| `client/` | Unity 客户端 (C#) — 游戏表现层、网络层、输入采集 |
| `docs/` | 技术文档 — GS 消息流程详解 |

## 游戏功能

GS 实现了完整的 2D 平台对战逻辑：

- **5 种武器**：手枪（自动连发）、重机枪（高射速）、狙击枪（高伤害）、霰弹枪（散射）、短剑（近战）
- **4 种效果**：延迟爆炸 (`delayed_explosion`)、悬停分裂 (`hover_split`)、招架 (`parry`)、剑气 (`sword_wave`)
- **空投系统**：定时在平台上随机生成武器或效果道具，玩家靠近可拾取
- **碰撞系统**：基于地图平台和墙壁的简化 AABB 碰撞检测
- **击退机制**：伤害积累 `damagePercent` 越高，击退越远
- **生命/重生**：每局 3 条命，出界或死亡后延迟重生
- **受击硬直**：受到攻击后有短暂硬直（hitstun），期间不可操作
- **房间状态机**：`WAITING → STARTING → PLAYING → FINISHED`

## 快速启动

详见各子目录的 README。推荐启动顺序：

```powershell
# 1. 安装依赖
python -m pip install -r as/requirements.txt
python -m pip install -r tgs/requirements.txt
python -m pip install -r server/requirements.txt

# 2. 初始化数据库 & 生成密钥（参考 as/README.md 和 server/README.md）

# 3. 依次启动三个服务
python as/as_server.py       # 终端1: ws://0.0.0.0:9000
python tgs/tgs_server.py     # 终端2: ws://0.0.0.0:9001
python server/ws_server.py   # 终端3: ws://0.0.0.0:8765

# 4. 运行测试
python -m pytest tests/ -v
```

## 加密体系

- **AS**: RSA 加密客户端 payload，DES-CBC 加密 TGT
- **TGS**: DES-CBC 解密 TGT + 加密 ServiceTicket（用 K_TGS），DES-CBC 加密响应 payload（用 KcTgs）
- **GS**: DES-CBC 解密 ServiceTicket（用 K_GS），KcGs 会话密钥加密后续 auth/payload
- 所有手写密码学实现集中在 `shared_crypto/` 目录
- 业务消息含 `ts` 时间戳和 `nonce` 防重放（30 秒窗口）

## 认证流程 (Kerberos-like)

1. 客户端 → AS: `REGISTER_REQ` / `AS_REQ` → 获取 TGT + KcTgs
2. 客户端 → TGS: `TGS_REQ` → 获取 ServiceTicket + KcGs
3. 客户端 → GS: `GS_AUTH` → 建立游戏会话（返回 sessionId）
4. 认证后所有消息用 KcGs 加密 auth/payload，含 ts/nonce 防重放

## GS 消息类型总览

| 入站 | 出站/广播 | 说明 |
|---|---|---|
| `GS_AUTH` | `GS_AUTH_OK` | Kerberos 认证门禁 |
| `HEARTBEAT_REQ` | `HEARTBEAT_REP` | 连接保活 |
| `RECONNECT_REQ` | `RECONNECT_REP` | 断线重连（30 秒宽限期） |
| `ROOM_CREATE_REQ` | `ROOM_CREATE_REP` | 创建房间（自动加入为 Client1 房主） |
| `ROOM_JOIN_REQ` | `ROOM_JOIN_REP` | 加入已有房间 |
| — | `ROOM_STATE` | 权威房间状态广播（使用各自 KcGs 加密） |
| `ROOM_READY_REQ` | `ROOM_READY_REP` | 切换准备状态 |
| `ROOM_START_REQ` | `ROOM_START_REP` | 房主开始对战（含 matchId、倒计时） |
| `INPUT` | — | 高频输入帧（位置/伤害等权威字段由服务端判定） |
| — | `SNAPSHOT` | 权威状态快照广播（按 `SNAPSHOT_ENCRYPT_EVERY_N` 策略加密） |
| — | `RESULT` | 对局结算广播（`payloadEncrypted: true`） |
| `LEAVE_ROOM` | — | 主动离开房间 |

完整消息流程和每个消息的详细字段说明见 `docs/server-message-flow.md` 和 `网络包传输全过程.md`。

## 安全机制

- **票据链**：TGT (K_TGS 加密) → ServiceTicket (K_GS 加密)，客户端无法篡改
- **会话密钥**：KcGs 由 TGS 随机生成，经 ServiceTicket 传递，GS_AUTH_OK 后用于所有业务加密
- **防重放**：每条消息 `ts` 在 30 秒窗口内 + `nonce` 全局唯一（`{userId}/{clientId}/{nonce}` 索引）
- **seq 递增**：INPUT 的 `seq` 必须严格递增，拒绝乱序/重复
- **权威字段保护**：客户端不得上传 `damagePercent`、`stocks`、`isDead` 等服务端权威字段
- **login_gen 校验**：每次认证/重连都校验 `login_gen`，密码修改或强制下线后旧票据立即失效
- **安全审计**：认证成功/失败、票据过期、重放锁定、重连超时均写入 `security_event_log`
