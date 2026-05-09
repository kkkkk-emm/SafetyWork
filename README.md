# SafetyWork — 网络安全课程项目

基于 Kerberos-like 协议的多人 WebSocket 游戏对战系统。

## 架构概览

```
客户端 ──> AS (认证服务器)  :9000  注册/登录/改密，获取 TGT
客户端 ──> TGS (票据服务器) :9001  凭 TGT 换取 ServiceTicket
客户端 ──> GS (游戏服务器)  :8765  凭 ServiceTicket 接入房间/对战
              │
              ▼
         MySQL (safety_auth)
         ├── user_account
         └── security_event_log
```

## 目录

| 目录 | 说明 |
|---|---|
| `as/` | AS 认证服务器 — 注册/登录/改密/TGT 签发 (RSA + DES) |
| `tgs/` | TGS 票据授权服务器 — 验证 TGT，签发 ServiceTicket |
| `server/` | GS 游戏服务器 — Kerberos 门禁、房间管理、对战同步、断线重连 |
| `shared_crypto/` | 共享密码学实现 — 手写 DES/RSA/PBKDF2 |
| `tests/` | 单元测试 — 安全协议、加密、代码结构检验 |

## 快速启动

详见各子目录的 README。推荐启动顺序：

```powershell
# 1. 安装依赖
python -m pip install -r as/requirements.txt
python -m pip install -r tgs/requirements.txt
python -m pip install -r server/requirements.txt

# 2. 初始化数据库 & 生成密钥（参考 as/README.md）

# 3. 依次启动三个服务
python as/as_server.py       # 终端1: ws://0.0.0.0:9000
python tgs/tgs_server.py     # 终端2: ws://0.0.0.0:9001
python server/ws_server.py   # 终端3: ws://0.0.0.0:8765

# 4. 运行测试
python -m pytest tests/ -v
```

## 加密体系

- **AS**: RSA 加密客户端 payload，DES-CBC 加密 TGT
- **TGS**: DES-CBC 解密 TGT + 加密 ServiceTicket
- **GS**: DES-CBC 解密 ServiceTicket，KcGs 会话密钥加密后续通信
- 所有手写密码学实现集中在 `shared_crypto/` 目录

## 认证流程 (Kerberos-like)

1. 客户端 → AS: `REGISTER_REQ` / `AS_REQ` → 获取 TGT + KcTgs
2. 客户端 → TGS: `TGS_REQ` → 获取 ServiceTicket + KcGs
3. 客户端 → GS: `GS_AUTH` → 建立游戏会话
4. 对战阶段所有消息用 KcGs 加密，含 ts/nonce 防重放

详见 `server/README.md` 完整协议说明。
