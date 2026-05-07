# TGS 票据授权服务器使用说明

本目录实现独立的 TGS(Ticket Granting Server)。TGS 通过 WebSocket 接收 `TGS_REQ`，验证 AS 签发的 `TGT`，然后签发访问 GS 的 `Service Ticket` 和 `KcGs`。

当前实现只新增 `tgs/`，不修改现有 `server/` 游戏服务。GS 暂时不会消费 Service Ticket，后续可以在 GS 中单独实现 `GS_AUTH`。

## 目录文件

| 文件 | 作用 |
| --- | --- |
| `tgs_server.py` | TGS WebSocket 服务入口，处理 `TGS_REQ`。 |
| `config.py` | 读取数据库、监听地址、票据参数和长期密钥环境变量。 |
| `db.py` | MySQL DAO，只读取 `user_account`，只写 `security_event_log`。 |
| `crypto_utils.py` | Base64、DES、随机会话密钥等工具函数。 |
| `protocol.py` | JSON 协议报文构造、解析和字段校验工具。 |
| `smoke_test_tgs.py` | AS -> TGS 基本链路测试脚本。 |
| `requirements.txt` | Python 依赖列表。 |

## 环境变量

### 必填变量

| 变量 | 示例 | 说明 |
| --- | --- | --- |
| `AUTH_DB_USER` | `root` | MySQL 用户名。 |
| `AUTH_DB_NAME` | `safety_auth` | 已初始化的认证数据库名。 |
| `K_TGS_BASE64` | `xxxxxxxxxxx=` | AS 和 TGS 共享的长期 DES key，必须与 AS 使用同一个值。 |
| `K_GS_BASE64` | `yyyyyyyyyyy=` | TGS 和未来 GS 共享的长期 DES key，解码后必须 8 字节。 |

### 可选变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `AUTH_DB_HOST` | `127.0.0.1` | MySQL 地址。 |
| `AUTH_DB_PORT` | `3306` | MySQL 端口。 |
| `AUTH_DB_PASSWORD` | 空字符串 | MySQL 密码。 |
| `TGS_HOST` | `0.0.0.0` | TGS WebSocket 监听地址。 |
| `TGS_PORT` | `9001` | TGS WebSocket 监听端口。 |
| `AUTH_REALM` | `SAFETYWORK` | 必须与 AS 写入 TGT 的 realm 一致。 |
| `AUTH_TGS_SERVICE_NAME` | `krbtgt/{realm}` | 必须与 AS 写入 TGT 的 service 一致。 |
| `AUTH_GS_SERVICE_NAME` | `game/ws@127.0.0.1:8765` | 允许签发 Service Ticket 的 GS 服务标识。 |
| `AUTH_SERVICE_TICKET_TTL_SECONDS` | `7200` | Service Ticket TTL，最终过期时间不会超过 TGT 过期时间。 |
| `AUTH_AUTHENTICATOR_WINDOW_SECONDS` | `30` | Authenticator 时间戳和 nonce 防重放窗口。 |

生成 `K_GS_BASE64` 示例：

```powershell
python -c "import os,base64; print(base64.b64encode(os.urandom(8)).decode())"
```

## 启动 TGS

安装依赖：

```powershell
python -m pip install -r .\tgs\requirements.txt
```

设置环境变量示例：

```powershell
$env:AUTH_DB_HOST='127.0.0.1'
$env:AUTH_DB_PORT='3306'
$env:AUTH_DB_USER='root'
$env:AUTH_DB_PASSWORD='你的MySQL密码'
$env:AUTH_DB_NAME='safety_auth'

$env:K_TGS_BASE64=(Get-Content .\as\k_tgs_base64.txt -Raw).Trim()
$env:K_GS_BASE64='把上面生成的8字节Base64填到这里'

$env:TGS_HOST='0.0.0.0'
$env:TGS_PORT='9001'
$env:AUTH_GS_SERVICE_NAME='game/ws@127.0.0.1:8765'
```

启动服务：

```powershell
python .\tgs\tgs_server.py
```

启动成功会看到类似输出：

```text
TGS server listening on ws://0.0.0.0:9001 realm=SAFETYWORK gs=game/ws@127.0.0.1:8765
```

## 协议

`TGS_REQ`：

```json
{
  "type": "TGS_REQ",
  "clientId": "cli-a-001",
  "ticket": "Base64(DES(K_TGS,TGT_JSON))",
  "auth": "Base64(DES(KcTgs,{\"ts\":1776650500000,\"nonce\":\"n2\"}))",
  "payload": "Base64(DES(KcTgs,{\"service\":\"game/ws@127.0.0.1:8765\",\"nonce\":\"n3\"}))"
}
```

`TGS_REP`：

```json
{
  "type": "TGS_REP",
  "ticket": "Base64(DES(K_GS,ServiceTicket_JSON))",
  "payload": "Base64(DES(KcTgs,{\"nonce\":\"n3\",\"kcGs\":\"...\",\"exp\":1776657700100}))"
}
```

Service Ticket 明文字段：

- `ticketType`: 固定为 `SERVICE_TICKET`。
- `realm`: 认证域。
- `userId` / `username` / `clientId`: 来自已验证的 TGT。
- `service`: `AUTH_GS_SERVICE_NAME`。
- `kcGs`: Base64 后的客户端-GS 会话 DES key。
- `loginGen`: 与当前数据库 `user_account.login_gen` 一致。
- `iat` / `exp`: 签发和过期时间，Unix 毫秒。

错误统一返回：

```json
{"type":"ERROR","error":"SERVICE_NOT_ALLOWED"}
```

## Smoke Test

运行前需要同时启动 AS 和 TGS，并确保使用同一个 `K_TGS_BASE64`。

```powershell
$env:AS_URL='ws://127.0.0.1:9000'
$env:TGS_URL='ws://127.0.0.1:9001'
$env:AS_PUBLIC_KEY_PATH='.\as\as_public_key.pem'
$env:AUTH_GS_SERVICE_NAME='game/ws@127.0.0.1:8765'
$env:K_GS_BASE64='与TGS服务相同的K_GS_BASE64'
python .\tgs\smoke_test_tgs.py
```

通过时输出：

```text
TGS smoke test passed
```
