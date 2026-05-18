# Client / Server JSON 包清单

## 约定

WebSocket 文本帧内容都是 UTF-8 JSON。当前 GS 协议顶层通常复用同一个消息结构：

```json
{
  "type": "消息类型",
  "clientId": "认证客户端ID或旧版房间客户端ID",
  "sessionId": "GS会话ID",
  "roomId": "房间ID",
  "ticket": "TGT或ServiceTicket",
  "auth": "加密后的authenticator字符串",
  "payloadEncrypted": false,
  "payload": "加密字符串或JSON字符串",
  "error": "错误码",
  "targetId": "",
  "fromClientId": "",
  "text": "",
  "timestamp": ""
}
```

加密字段说明：

- `<RSA_AS({...})>`：客户端用 AS 公钥 RSA 加密 JSON 后得到的 Base64 字符串。
- `<DES_Kuser({...})>`：用用户密码派生出的 `Kuser` DES 加密 JSON 后得到的 Base64 字符串。
- `<DES_KcTgs({...})>`：用 `KcTgs` DES 加密 JSON 后得到的 Base64 字符串。
- `<DES_KcGs({...})>`：用 `KcGs` DES 加密 JSON 后得到的 Base64 字符串。
- `<DES_Kgs({...})>`：ServiceTicket 内部由 GS 长期密钥 `K_GS` 解密，客户端只转发字符串。

`ts` 是毫秒时间戳，`nonce` 是防重放随机串。

## 当前 GS 实际路由

`server/relay_server.py` 当前实际处理这些 `type`：

| 方向 | type | 当前状态 |
| --- | --- | --- |
| Client -> GS | `GS_AUTH` | 支持，未认证也可发 |
| Client -> GS | `RECONNECT_REQ` | 支持，未认证也可发 |
| Client -> GS | `ROOM_CREATE_REQ` | 支持 |
| Client -> GS | `ROOM_JOIN_REQ` | 支持 |
| Client -> GS | `ROOM_READY_REQ` | 支持 |
| Client -> GS | `ROOM_START_REQ` | 支持 |
| Client -> GS | `INPUT` | 支持 |
| Client -> GS | `LEAVE_ROOM` | 支持，但当前服务端不解密校验 `auth`，也无显式响应 |
| GS -> Client | `GS_AUTH_OK` | 支持 |
| GS -> Client | `RECONNECT_REP` | 支持 |
| GS -> Client | `ROOM_CREATE_REP` | 支持 |
| GS -> Client | `ROOM_JOIN_REP` | 支持 |
| GS -> Client | `ROOM_READY_REP` | 支持 |
| GS -> Client | `ROOM_STATE` | 支持，广播 |
| GS -> Client | `ROOM_START_REP` | 支持，广播；客户端也兼容 `GAME_START` 别名 |
| GS -> Client | `SNAPSHOT` | 支持，广播 |
| GS -> Client | `RESULT` | 支持，广播 |
| GS -> Client | `ERROR` | 支持 |

除 `GS_AUTH` / `RECONNECT_REQ` 外，业务消息必须先通过 GS 认证，否则服务端返回：

```json
{
  "type": "ERROR",
  "error": "NOT_AUTHENTICATED"
}
```

未知 `type` 返回：

```json
{
  "type": "ERROR",
  "error": "UNSUPPORTED_TYPE: <type>"
}
```

## 认证包：Client -> GS

### GS_AUTH

客户端发送：

```json
{
  "type": "GS_AUTH",
  "clientId": "cli_xxx",
  "ticket": "<ServiceTicket>",
  "auth": "<DES_KcGs(GsAuthPayload)>",
  "payload": ""
}
```

`auth` 解密后：

```json
{
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

服务端返回：

```json
{
  "type": "GS_AUTH_OK",
  "sessionId": "sess-<userId>-<8hex>",
  "payload": "<DES_KcGs(GsAuthOkPayload)>"
}
```

`payload` 解密后，服务端当前实际返回：

```json
{
  "ts": 1710000000000,
  "nonce": "回显GS_AUTH.auth.nonce",
  "exp": 1710003600000
}
```

客户端 `GsAuthOkPayload` 类还声明了 `ok/clientId/sessionId/error`，但当前 GS 服务端没有填这些字段。

### RECONNECT_REQ
### RECONNECT_REQ

客户端发送：

```json
{
  "type": "RECONNECT_REQ",
  "clientId": "cli_xxx",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "ticket": "<ServiceTicket>",
  "auth": "<DES_KcGs(ReconnectAuthPayload)>",
  "payload": "<DES_KcGs(ReconnectPayload)>"
}
```

`auth` 解密后：

```json
{
  "type": "RECONNECT_REQ",
  "clientId": "cli_xxx",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

`payload` 解密后：

```json
{
  "type": "RECONNECT_REQ",
  "clientId": "cli_xxx",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "nonce": "必须等于auth.nonce",
  "lastProcessedSeq": 123,
  "ts": 1710000000000
}
```

服务端返回：

```json
{
  "type": "RECONNECT_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(ReconnectRepPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "RECONNECT_REP",
  "ok": true,
  "sessionId": "sess-...",
  "roomId": "AB12",
  "phase": "PLAYING",
  "lastProcessedSeq": -1,
  "ts": 1710000000000,
  "nonce": "回显RECONNECT_REQ.auth.nonce"
}
```

`phase` 可能是 `PLAYING` 或 `FINISHED`。

## 房间包：Client -> GS

### ROOM_CREATE_REQ

客户端发送：

```json
{
  "type": "ROOM_CREATE_REQ",
  "sessionId": "sess-...",
  "roomId": "",
  "auth": "<DES_KcGs(RoomAuthPayload)>",
  "payload": ""
}
```

`auth` 解密后：

```json
{
  "type": "ROOM_CREATE_REQ",
  "sessionId": "sess-...",
  "roomId": "",
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

服务端返回：

```json
{
  "type": "ROOM_CREATE_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(RoomCreateRepPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "ROOM_CREATE_REP",
  "ok": true,
  "sessionId": "sess-...",
  "roomId": "AB12"
}
```

随后服务端会广播 `ROOM_STATE`，并且 `_internal_join_room()` 里也可能先广播一次 `SNAPSHOT`。

### ROOM_JOIN_REQ

客户端发送：

```json
{
  "type": "ROOM_JOIN_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "auth": "<DES_KcGs(RoomAuthPayload)>",
  "payload": ""
}
```

`auth` 解密后：

```json
{
  "type": "ROOM_JOIN_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

服务端返回：

```json
{
  "type": "ROOM_JOIN_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(RoomJoinRepPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "ROOM_JOIN_REP",
  "ok": true,
  "sessionId": "sess-...",
  "roomId": "AB12",
  "nonce": "回显ROOM_JOIN_REQ.auth.nonce"
}
```

随后服务端会广播 `ROOM_STATE` 和一次 `SNAPSHOT`。

### ROOM_READY_REQ

客户端发送：

```json
{
  "type": "ROOM_READY_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(ReadyEncryptedPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "ROOM_READY_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "ready": true,
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

服务端返回：

```json
{
  "type": "ROOM_READY_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(RoomReadyRepPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "ROOM_READY_REP",
  "ok": true,
  "ready": true,
  "sessionId": "sess-...",
  "roomId": "AB12",
  "nonce": "回显ROOM_READY_REQ.payload.nonce"
}
```

随后服务端会广播 `ROOM_STATE`。

### ROOM_START_REQ

客户端发送：

```json
{
  "type": "ROOM_START_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "auth": "<DES_KcGs(RoomAuthPayload)>",
  "payload": ""
}
```

`auth` 解密后：

```json
{
  "type": "ROOM_START_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

服务端没有单独只发给房主的确认包。校验通过后会：

1. 广播一次 `ROOM_STATE`，状态变为 `STARTING`。
2. 广播 `ROOM_START_REP`。

### LEAVE_ROOM

当前主客户端发送：

```json
{
  "type": "LEAVE_ROOM",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "auth": "<DES_KcGs(RoomAuthPayload)>",
  "payload": ""
}
```

`auth` 解密后按客户端构造应为：

```json
{
  "type": "LEAVE_ROOM",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "ts": 1710000000000,
  "nonce": "随机串"
}
```

注意：`server/relay_room.py` 的 `handle_leave_room()` 当前没有读取、解密或校验 `data.auth`，也不会返回 `LEAVE_ROOM_REP`。它只移除房间成员并广播 `ROOM_STATE` 给剩余玩家。

## 房间广播：GS -> Client

### ROOM_STATE

服务端广播：

```json
{
  "type": "ROOM_STATE",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(RoomStatePayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "ROOM_STATE",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "hostClientId": "Client1",
  "state": "WAITING",
  "ownerUserId": 1,
  "players": [
    {
      "userId": 1,
      "username": "alice",
      "clientId": "Client1",
      "slotNo": 1,
      "ready": false,
      "isHost": true,
      "online": true
    }
  ],
  "canStart": false,
  "localClientId": "Client1",
  "localSlotNo": 1,
  "localIsHost": true
}
```

`state` 可能为 `WAITING`、`STARTING`、`PLAYING`、`FINISHED`。客户端 `RoomStatePayload` 还声明了 `status`，但服务端当前主要填 `state`。

### ROOM_START_REP

服务端广播：

```json
{
  "type": "ROOM_START_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "<DES_KcGs(GameStartPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "ROOM_START_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "hostClientId": "Client1",
  "state": "STARTING",
  "ownerUserId": 1,
  "players": [
    {
      "userId": 1,
      "username": "alice",
      "clientId": "Client1",
      "slotNo": 1,
      "ready": true,
      "isHost": true,
      "online": true
    },
    {
      "userId": 2,
      "username": "bob",
      "clientId": "Client2",
      "slotNo": 2,
      "ready": true,
      "isHost": false,
      "online": true
    }
  ],
  "canStart": true,
  "localClientId": "Client1",
  "localSlotNo": 1,
  "localIsHost": true,
  "sceneName": "MainGame",
  "matchId": "match-123",
  "countdownMs": 3000
}
```

客户端 `RelayChatClient.cs` 同时兼容收到 `GAME_START`，但当前服务端实际发送 `ROOM_START_REP`。

## 对战输入：Client -> GS

### INPUT

客户端发送：

```json
{
  "type": "INPUT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": false,
  "payload": "{\"type\":\"INPUT\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"clientId\":\"Client1\",\"ts\":1710000000000,\"nonce\":\"...\",\"seq\":1,\"tick\":1,\"moveX\":0.0,\"jumpPressed\":false,\"downHeld\":false,\"dropPressed\":false,\"attackPressed\":false,\"attackHeld\":false,\"attackReleased\":false,\"aimX\":1.0,\"aimY\":0.0,\"clientState\":\"Grounded\",\"clientGrounded\":true,\"clientJumpCount\":0,\"clientPosX\":0.0,\"clientPosY\":3.0,\"clientVelX\":0.0,\"clientVelY\":0.0,\"equippedWeaponId\":\"手枪\",\"equippedEffectIds\":[]}"
}
```

如果 `payloadEncrypted=true`，`payload` 是：

```json
"<DES_KcGs(InputPayload)>"
```

`payload` 明文结构：

```json
{
  "type": "INPUT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "clientId": "Client1",
  "ts": 1710000000000,
  "nonce": "随机串",
  "seq": 1,
  "tick": 1,
  "moveX": 0.0,
  "jumpPressed": false,
  "downHeld": false,
  "dropPressed": false,
  "attackPressed": false,
  "attackHeld": false,
  "attackReleased": false,
  "aimX": 1.0,
  "aimY": 0.0,
  "clientState": "Grounded",
  "clientGrounded": true,
  "clientJumpCount": 0,
  "clientPosX": 0.0,
  "clientPosY": 3.0,
  "clientVelX": 0.0,
  "clientVelY": 0.0,
  "equippedWeaponId": "手枪",
  "equippedEffectIds": []
}
```

服务端会拒绝客户端上传这些服务端权威字段：

```json
["damagePercent", "stocks", "isDead", "damage", "hitResult", "killCount"]
```

`INPUT` 没有逐条确认包；确认体现在后续 `SNAPSHOT.lastProcessedSeq`。

## 对战快照：GS -> Client

### SNAPSHOT 顶层

服务端发送：

```json
{
  "type": "SNAPSHOT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": false,
  "payload": "{\"type\":\"SNAPSHOT\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"tick\":1,\"lastProcessedSeq\":1,\"rejectReason\":\"\",\"players\":[],\"projectiles\":[],\"loots\":[],\"events\":[]}"
}
```

如果 `payloadEncrypted=true`：

```json
{
  "type": "SNAPSHOT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": true,
  "payload": "<DES_KcGs(SnapshotPayload)>"
}
```

`payload` 明文结构：

```json
{
  "type": "SNAPSHOT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "tick": 1,
  "lastProcessedSeq": 1,
  "rejectReason": "",
  "players": [],
  "projectiles": [],
  "loots": [],
  "events": []
}
```

### PlayerSnapshot

```json
{
  "slotNo": 1,
  "userId": 1,
  "clientId": "Client1",
  "state": "Grounded",
  "grounded": true,
  "jumpCount": 0,
  "posX": 0.0,
  "posY": 3.0,
  "velX": 0.0,
  "velY": 0.0,
  "aimX": 1.0,
  "aimY": 0.0,
  "equippedWeaponId": "手枪",
  "equippedEffectIds": [],
  "damagePercent": 0.0,
  "stocks": 3,
  "isDead": false,
  "facing": 1,
  "lastKnockbackX": 0.0,
  "lastKnockbackY": 0.0,
  "lastHitTick": -1
}
```

### ProjectileSnapshot

```json
{
  "projId": 1,
  "ownerClientId": "Client1",
  "weaponId": "手枪",
  "bulletId": "普通子弹",
  "visualId": "普通子弹",
  "posX": 1.0,
  "posY": 3.2,
  "velX": 18.0,
  "velY": 0.0,
  "rotationDeg": 0.0,
  "radius": 0.2,
  "ttl": 1.8,
  "alive": true,
  "effectIds": []
}
```

### LootSnapshot

```json
{
  "lootId": "loot_1",
  "lootType": "effect",
  "itemId": "delayed_explosion",
  "posX": 10.0,
  "posY": 6.0,
  "velY": -0.2,
  "radius": 0.75,
  "landed": false
}
```

### MatchEventSnapshot

事件统一包裹格式：

```json
{
  "eventType": "PROJECTILE_SPAWNED",
  "eventSeq": 1,
  "data": {}
}
```

当前服务端会产生这些事件。

`PROJECTILE_SPAWNED`：

```json
{
  "projId": 1,
  "ownerClientId": "Client1",
  "weaponId": "手枪",
  "bulletId": "普通子弹",
  "visualId": "普通子弹",
  "x": 1.0,
  "y": 3.2,
  "velX": 18.0,
  "velY": 0.0,
  "rotationDeg": 0.0,
  "radius": 0.2
}
```

`PROJECTILE_DESTROYED`：

```json
{
  "projId": 1,
  "reason": "ttl",
  "x": 3.0,
  "y": 3.2
}
```

`reason` 可能包括 `ttl`、`world`、`hit_player`、`hover_split`、`explosion`、`explosion_timer`、`explosion_world`、`explosion_player`。部分效果路径只填 `projId/reason`，不一定填 `x/y`。

`MELEE_HITBOX_SPAWNED`：

```json
{
  "hitboxId": 1,
  "ownerClientId": "Client1",
  "weaponId": "短剑",
  "x": 1.0,
  "y": 3.4,
  "radius": 0.8
}
```

`PLAYER_HIT`：

```json
{
  "attackerClientId": "Client1",
  "targetClientId": "Client2",
  "weaponId": "手枪",
  "damageAdded": 10.0,
  "damageBefore": 0.0,
  "newDamagePercent": 10.0,
  "percentageFactor": 0.0,
  "baseKnockback": 25.0,
  "knockbackScale": 1.0,
  "finalKnockbackForce": 25.0,
  "knockbackX": 17.67,
  "knockbackY": 17.67,
  "hitstunTicks": 10
}
```

客户端 `MatchEventData` 当前只声明了其中一部分字段，未声明字段会被 Unity `JsonUtility` 忽略。

`EXPLOSION_TRIGGERED`：

```json
{
  "projId": 1,
  "ownerClientId": "Client1",
  "x": 3.0,
  "y": 3.2,
  "radius": 2.5,
  "reason": "timer"
}
```

`PLAYER_PARRIED`：

```json
{
  "clientId": "Client1",
  "projId": 1
}
```

`PLAYER_OUT_OF_BOUNDS`：

```json
{
  "clientId": "Client2",
  "stocksLeft": 2
}
```

`PLAYER_RESPAWN`：

```json
{
  "clientId": "Client2",
  "x": 20.0,
  "y": 3.0
}
```

`LOOT_SPAWNED`：

```json
{
  "lootId": "loot_1",
  "lootType": "effect",
  "itemId": "delayed_explosion",
  "x": 10.0,
  "y": 8.0,
  "radius": 0.75
}
```

`LOOT_LANDED`：

```json
{
  "lootId": "loot_1",
  "lootType": "effect",
  "itemId": "delayed_explosion",
  "x": 10.0,
  "y": 3.4
}
```

注意：服务端会发 `LOOT_LANDED`，但当前 `ClientReceiver.cs` 没有显式 case，会走默认未处理日志；落地状态仍会通过 `snapshot.loots[].landed` 同步。

`LOOT_PICKED`：

```json
{
  "lootId": "loot_1",
  "lootType": "effect",
  "itemId": "delayed_explosion",
  "clientId": "Client1",
  "x": 10.0,
  "y": 3.4
}
```

客户端还处理 `LOOT_DESPAWNED`：

```json
{
  "lootId": "loot_1"
}
```

但当前服务端没有发现发出 `LOOT_DESPAWNED` 的路径。

## 对局结果：GS -> Client

### RESULT

服务端发送：

```json
{
  "type": "RESULT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": true,
  "payload": "<DES_KcGs(ResultPayload)>"
}
```

`payload` 解密后：

```json
{
  "type": "RESULT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "winnerUserId": 1,
  "reason": "STOCK_ZERO",
  "players": [
    {
      "userId": 1,
      "clientId": "Client1",
      "stocksLeft": 1,
      "finalDamagePercent": 80.5
    },
    {
      "userId": 2,
      "clientId": "Client2",
      "stocksLeft": 0,
      "finalDamagePercent": 160.0
    }
  ]
}
```

`reason` 当前可见路径包括 `STOCK_ZERO`、`DRAW`。

## 通用错误包：GS -> Client

```json
{
  "type": "ERROR",
  "error": "错误码或错误信息"
}
```

服务端代码中可见的常见错误包括：

```json
[
  "INVALID_JSON",
  "MISSING_TYPE",
  "NOT_AUTHENTICATED",
  "KEY_NOT_CONFIGURED",
  "INVALID_TICKET",
  "SESSION_MISMATCH",
  "TYPE_MISMATCH",
  "ROOM_MISMATCH",
  "ROOM_ID_REQUIRED",
  "ROOM_NOT_FOUND",
  "ROOM_NOT_JOINABLE",
  "ROOM_FULL",
  "NOT_IN_ROOM",
  "NO_ROOM_STATE",
  "ROOM_NOT_WAITING",
  "NOT_HOST",
  "NEED_MORE_PLAYERS",
  "NOT_ALL_READY",
  "INVALID_PAYLOAD",
  "RECONNECT_EXPIRED",
  "CLIENT_MISMATCH",
  "NONCE_MISMATCH",
  "AUTH_EXPIRED",
  "AUTH_NONCE_REPLAY",
  "UNSUPPORTED_TYPE: <type>"
]
```

## 客户端认证协议：Client -> AS/TGS

这些包来自 `client/Scripts/GBManager/网络相关/消息/AuthClient.cs`。注意：当前 `server/` 目录只实现 GS，中间的 AS/TGS 服务端实现不在 `server/` 目录内；下面响应格式以客户端解析逻辑为准。

### REGISTER_REQ / REGISTER_REP

客户端发 AS：

```json
{
  "type": "REGISTER_REQ",
  "clientId": "cli_xxx",
  "payload": "<RSA_AS(RegisterReqPayload)>"
}
```

`payload` 解密后：

```json
{
  "username": "alice",
  "password": "password"
}
```

客户端期望 AS 返回：

```json
{
  "type": "REGISTER_REP",
  "payload": "{\"ok\":true,\"userId\":1,\"error\":\"\"}"
}
```

`payload` 明文结构：

```json
{
  "ok": true,
  "userId": 1,
  "error": ""
}
```

### AS_REQ / AS_REP

客户端发 AS：

```json
{
  "type": "AS_REQ",
  "clientId": "cli_xxx",
  "payload": "<RSA_AS(AsReqPayload)>"
}
```

`payload` 解密后：

```json
{
  "username": "alice",
  "password": "password",
  "nonce": "随机串"
}
```

客户端期望 AS 返回：

```json
{
  "type": "AS_REP",
  "ticket": "<TGT>",
  "payload": "{\"salt\":\"...\",\"iter\":100000,\"part\":\"<DES_Kuser(AsRepProtectedPart)>\"}"
}
```

`payload` 外层明文结构：

```json
{
  "salt": "base64 salt",
  "iter": 100000,
  "part": "<DES_Kuser(AsRepProtectedPart)>"
}
```

`part` 解密后：

```json
{
  "userId": 1,
  "username": "alice",
  "nonce": "回显AS_REQ.payload.nonce",
  "kcTgs": "base64 DES key",
  "exp": 1710003600000,
  "loginGen": 0
}
```

### CHANGE_PASSWORD_REQ / CHANGE_PASSWORD_REP

客户端发 AS：

```json
{
  "type": "CHANGE_PASSWORD_REQ",
  "clientId": "cli_xxx",
  "payload": "<RSA_AS(ChangePasswordReqPayload)>"
}
```

`payload` 解密后：

```json
{
  "username": "alice",
  "oldPassword": "old",
  "newPassword": "new"
}
```

客户端期望 AS 返回：

```json
{
  "type": "CHANGE_PASSWORD_REP",
  "payload": "{\"ok\":true,\"error\":\"\"}"
}
```

`payload` 明文结构：

```json
{
  "ok": true,
  "error": ""
}
```

### TGS_REQ / TGS_REP

客户端发 TGS：

```json
{
  "type": "TGS_REQ",
  "clientId": "cli_xxx",
  "ticket": "<TGT>",
  "auth": "<DES_KcTgs(TgsAuthPayload)>",
  "payload": "<DES_KcTgs(TgsReqPayload)>"
}
```

`auth` 解密后：

```json
{
  "type": "TGS_REQ",
  "ts": 1710000000000,
  "nonce": "随机串A"
}
```

`payload` 解密后：

```json
{
  "type": "TGS_REQ",
  "service": "game/ws@127.0.0.1:8765",
  "nonce": "随机串B"
}
```

客户端期望 TGS 返回：

```json
{
  "type": "TGS_REP",
  "ticket": "<ServiceTicket>",
  "payload": "<DES_KcTgs(TgsRepProtectedPayload)>"
}
```

`payload` 解密后：

```json
{
  "nonce": "回显TGS_REQ.payload.nonce",
  "kcGs": "base64 DES key",
  "exp": 1710003600000
}
```

AS/TGS 错误同样按通用错误包处理：

```json
{
  "type": "ERROR",
  "error": "错误码或错误信息"
}
```

## 客户端残留/旧版协议

这些格式存在于：

- `client/Scripts/RelayChatClient.cs`
- `client/Scripts/GBManager/RelayChatClient.cs`
- `client/Scripts/GBManager/网络相关/RelayChatClient.cs` 的 `SendChat()`
- `server/game_config.py` 的旧常量

当前 `server/relay_server.py` 不路由 `JOIN_ROOM`、`CHAT`、`SERVER_BROADCAST`。如果客户端未认证就发，会先得到 `NOT_AUTHENTICATED`；即使认证后发 `JOIN_ROOM` 或 `CHAT`，也会得到 `UNSUPPORTED_TYPE: JOIN_ROOM` 或 `UNSUPPORTED_TYPE: CHAT`。

### JOIN_ROOM 旧版

```json
{
  "type": "JOIN_ROOM",
  "roomId": "demo-room",
  "clientId": "Client1"
}
```

### CHAT 旧版

旧版客户端：

```json
{
  "type": "CHAT",
  "roomId": "demo-room",
  "clientId": "Client1",
  "text": "hello"
}
```

当前主客户端 `SendChat()`：

```json
{
  "type": "CHAT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "{\"text\":\"hello\"}"
}
```

当前 GS 服务端都不处理 `CHAT`。

### LEAVE_ROOM 旧版

```json
{
  "type": "LEAVE_ROOM",
  "roomId": "demo-room",
  "clientId": "Client1"
}
```

注意：`LEAVE_ROOM` 这个 `type` 在当前 GS 服务端是支持的，但当前主客户端发送的是带 `sessionId/auth` 的新版格式。旧版格式没有 GS 认证信息。

### SERVER_BROADCAST 旧版

旧客户端期望服务端转发：

```json
{
  "type": "SERVER_BROADCAST",
  "roomId": "demo-room",
  "fromClientId": "Client1",
  "text": "hello",
  "timestamp": "2026-05-15T10:00:00Z"
}
```

当前 `server/` 没有实际发送该包的路径。

### 仅有常量或客户端兼容的类型

这些 `type` 在代码中出现，但当前没有完整互传路径：

| type | 位置 | 说明 |
| --- | --- | --- |
| `CREATE_ROOM` | `server/game_config.py` | 旧常量，当前服务端不路由 |
| `READY` | `server/game_config.py` | 旧常量，当前服务端不路由 |
| `START_GAME` | `server/game_config.py` | 旧常量，当前服务端不路由 |
| `GAME_START` | `server/game_config.py`、客户端接收 switch | 客户端兼容接收；当前服务端实际发 `ROOM_START_REP` |
| `LOOT_DESPAWNED` | `ClientReceiver.cs` | 客户端处理；当前服务端没有发出路径 |
