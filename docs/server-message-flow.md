# Server 消息流程说明

本文档基于 `server/` 目录下当前 Python 实现整理，重点说明 WebSocket 消息路由、输入层解密、状态变更和服务端回包。行内保留原英文变量名、函数名和 message `type`。

## 0. 总览

<!-- HEARTBEAT 已移除：此小节已在代码与文档中弃用 -->
│  ├─ 已认证: invalidate_current_session() 废弃旧session → 重新执行 handle_gs_auth()
│  └─ 未认证: run_with_error_response("GS_AUTH", handle_gs_auth())
├─ if msg_type == RECONNECT_REQ
│  └─ run_with_error_response("RECONNECT", handle_reconnect())
├─ if not session.authenticated
│  └─ send_error("NOT_AUTHENTICATED")
└─ run_with_error_response("GS", dispatch_authenticated_message())
   ├─ ROOM_CREATE_REQ -> handle_create_room()
   ├─ ROOM_JOIN_REQ -> handle_join_room()
   ├─ ROOM_READY_REQ -> handle_ready()
   ├─ ROOM_START_REQ -> handle_start_game()
   ├─ INPUT -> handle_input()
   ├─ LEAVE_ROOM -> handle_leave_room()
   └─ else -> send_error("UNSUPPORTED_TYPE: ...")
```

统一错误处理在 `server/gs_error_handling.py`：

```text
run_with_error_response()
├─ ProtocolError -> {"type":"ERROR","error": exc.error_code}
├─ GsRequestError -> {"type":"ERROR","error": exc.error_code}
├─ CryptoError -> {"type":"ERROR","error": str(exc)}
└─ Exception -> stderr 打印内部错误, 返回 {"type":"ERROR","error":"INTERNAL_ERROR"}
```

### 0.3 WebSocket 连接生命周期

```text
connect
└─ handle_client()
   ├─ 创建临时 ClientSession(authenticated=False)
   └─ 等待客户端消息

auth
└─ GS_AUTH
   ├─ K_GS 解密 ServiceTicket
   ├─ KcGs 解密 authenticator
   ├─ 校验 ticket / timestamp / nonce / user_account
   ├─ session.authenticated = True
   ├─ 分配 session.session_id
   └─ 返回 GS_AUTH_OK

room
├─ ROOM_CREATE_REQ
│  └─ 创建 room_state, 房主作为 Client1 加入
├─ ROOM_JOIN_REQ
│  └─ 加入已有房间, 分配 Client1/Client2 slot
├─ ROOM_READY_REQ
│  └─ 修改 ready
└─ ROOM_START_REQ
   └─ WAITING -> STARTING, 广播开局

playing
└─ INPUT
   ├─ 首个 INPUT: STARTING -> PLAYING
   ├─ 服务端权威更新位置、跳跃、攻击、投射物、掉落物、生命数

handle_message()
├─ 如果 session.authenticated
│  └─ invalidate_current_session(websocket, reason="renew_gs_auth")
│     ├─ remove_player_from_room_state()
│     ├─ remove_from_room()
│     ├─ 若房间变空: cleanup_room_runtime_state() + broadcast_room_state()
│     ├─ sessions_by_id.pop(old_session_id)
│     ├─ reconnect_grace.pop(old_session_id)
│     └─ self.sessions[websocket] = ClientSession()  # 回退为未认证
└─ run_with_error_response("GS_AUTH", handle_gs_auth())
   └─ handle_gs_auth()
      ├─ require_string_field(data, "clientId")
      ├─ self.db.connection()
      │  ├─ self.security.validate_service_ticket()
      │  │  ├─ des_decrypt_object(k_gs, encrypted_ticket)
      │  │  ├─ require ticketType == SERVICE_TICKET
      │  │  ├─ require service == self.config.gs_service_name
      │  │  ├─ require ticket.clientId == data.clientId
      │  │  ├─ b64decode(ticket.kcGs)
      │  │  ├─ _validate_ticket_expiry()
      │  │  └─ _validate_user_account()
      │  │     └─ gs_db.find_user_by_id()
      │  ├─ self.security.decrypt_client_authenticator()
      │  │  ├─ des_decrypt_object(kc_gs, encrypted_auth)
      │  │  └─ validate_timestamp_and_nonce()
      │  │     ├─ timestamp_in_window()
      │  │     └─ replay_guard.check_and_store()
      │  ├─ self._expire_reconnect_grace(current_ms)
      │  ├─ 创建 session_id = "sess-{userId}-{nonce8}"
      │  ├─ 写入 self.sessions[websocket] 的 ClientSession
      │  ├─ self.sessions_by_id[session_id] = session
      │  ├─ self.security.record_success(event_type="GS_AUTH_SUCCESS")
      │  └─ conn.commit()
      ├─ des_encrypt_object(ticket.kc_gs, response_payload)
      └─ websocket.send(make_message(TYPE_GS_AUTH_OK, ...))
```

<!-- HEARTBEAT 已移除：协议中已弃用 HEARTBEAT_REQ/REP，文档中不再保留实现示例 -->
<!-- HEARTBEAT 已移除：协议中已弃用 HEARTBEAT_REQ/REP，文档中不再保留实现示例 -->

### 1.3 `ROOM_CREATE_REQ`（旧名 `CREATE_ROOM`）

#### 触发条件

实际路由 type 是 `ROOM_CREATE_REQ`：

```json
{
  "type": "ROOM_CREATE_REQ",
  "sessionId": "sess-...",
  "auth": "Base64(DES_KcGs({\"sessionId\":\"sess-...\",\"ts\":...,\"nonce\":\"...\"}))"
}
```

顶层必需字段：`sessionId`、`auth`。

注意：`handle_create_room()` 只校验 `auth.sessionId`，当前不要求 `auth.type == ROOM_CREATE_REQ`。

#### 调用链

```text
handle_message()
└─ dispatch_authenticated_message()
   └─ handle_create_room()
      ├─ self._require_session(websocket)
      ├─ require_fields(data, ("sessionId", "auth"))
      ├─ self.decrypt_auth(session, data)
      ├─ require auth.sessionId == session.session_id
      ├─ 如果 session.room_id 存在
      │  ├─ remove_player_from_room_state(websocket, old_room_id)
      │  ├─ remove_from_room(websocket, old_room_id)
      │  ├─ session.room_id = None
      │  ├─ session.client_id = None
      │  └─ broadcast_room_state(old_room_id)
      ├─ room_id = generate_room_id()
      ├─ join_data = {"type": ROOM_JOIN_REQ, "clientId": "CREATE_HOST", "roomId": room_id}
      ├─ _internal_join_room(websocket, join_data)
      │  ├─ get_or_create_room_state(room_id, "Client1")
      │  ├─ assigned_client_id = "Client1", slot_no = 1
      │  ├─ close_and_forget_socket() 清理同 ClientId 旧连接
      │  ├─ 清理 ghost session
      │  ├─ room_state.players["Client1"] = {...}
      │  ├─ 初始化 session 游戏状态和出生点
      │  ├─ self.rooms[room_id].add(websocket)
      │  ├─ broadcast_room_state(room_id)
      │  └─ broadcast_snapshot(room_id, reject_reason_by_socket={websocket: ""})
      ├─ encrypt_payload(session, ROOM_CREATE_REP payload)
      ├─ send_json(ROOM_CREATE_REP)
      └─ broadcast_room_state(room_id)
```

#### 状态变更

- 如玩家原本在旧房间，会先从旧 `self.rooms[old_room_id]` 和旧 `self.room_states[old_room_id]["players"]` 移除。
- 新增 `self.room_states[room_id]`：

```python
{
    "hostClientId": "Client1",
    "status": "WAITING",
    "players": {}
}
```

- `room_state["players"]["Client1"]` 写入 `clientId`、`slotNo=1`、`ready`、`websocket`。
- `session.client_id="Client1"`，`session.room_id=room_id`。
- 重置 `session.last_seq`、位置、速度、跳跃、伤害、stocks、武器、效果、攻击冷却等对局字段。
- `self.rooms[room_id]` 新增当前 websocket。

#### 广播/响应

单播 `ROOM_CREATE_REP`：

```json
{
  "type": "ROOM_CREATE_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "Base64(DES_KcGs({\"type\":\"ROOM_CREATE_REP\",\"ok\":true,\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",...}))"
}
```

房间广播：

- `_internal_join_room()` 内广播一次 `ROOM_STATE`（使用各自 KcGs 加密 payload）。
- `_internal_join_room()` 内广播一次 `SNAPSHOT`。
- `handle_create_room()` 末尾再次广播 `ROOM_STATE`（使用各自 KcGs 加密 payload）。

### 1.4 `ROOM_JOIN_REQ`（旧名 `JOIN_ROOM`）

#### 触发条件

```json
{
  "type": "ROOM_JOIN_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "auth": "Base64(DES_KcGs({\"type\":\"ROOM_JOIN_REQ\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"ts\":...,\"nonce\":\"...\"}))"
}
```

顶层必需字段：`sessionId`、`roomId`、`auth`。

#### 调用链

```text
handle_message()
└─ dispatch_authenticated_message()
   └─ handle_join_room()
      ├─ self._require_session(websocket)
      ├─ require_fields(data, ("sessionId", "roomId", "auth"))
      ├─ require data.sessionId == session.session_id
      ├─ self.decrypt_auth(session, data)
      ├─ require auth.sessionId == session.session_id
      ├─ require auth.roomId == data.roomId
      ├─ require auth.type == ROOM_JOIN_REQ
      ├─ join_auth_nonce = auth.nonce
      ├─ data["clientId"] = session.client_id
      ├─ _internal_join_room(websocket, data)
      │  ├─ 如 session.room_id 存在，先离开旧房间
      │  ├─ get_or_create_room_state(room_id, "Client1")
      │  ├─ 如果 room_state.status == WAITING
      │  │  ├─ allocate_slot_no(room_state)
      │  │  └─ assigned_client_id = "Client{slot_no}"
      │  ├─ 否则必须指定 Client1 / Client2
      │  ├─ close_and_forget_socket() 清理同 ClientId 旧连接
      │  ├─ 清理 ghost session
      │  ├─ 写 room_state.players[assigned_client_id]
      │  ├─ 设置 hostClientId
      │  ├─ 初始化 session 对局状态和出生点
      │  ├─ self.rooms[room_id].add(websocket)
      │  ├─ broadcast_room_state(room_id)
      │  └─ broadcast_snapshot(room_id, reject_reason_by_socket={websocket: ""})
      ├─ encrypt_payload(session, ROOM_JOIN_REP payload)
      └─ send_json(ROOM_JOIN_REP)
```

#### 状态变更

- 如玩家在旧房间，先从旧房间移除。
- `room_state.players` 新增或覆盖本玩家：

```python
{
    "clientId": "Client1" or "Client2",
    "slotNo": 1 or 2,
    "ready": old_ready,
    "websocket": websocket
}
```

- `room_state.hostClientId` 优先保持为 `Client1`；若无 `Client1`，使用当前分配的 `assigned_client_id`。
- `session.client_id`、`session.room_id`、位置、速度、生命、武器、效果等对局字段被初始化。
- `self.rooms[room_id]` 加入 websocket。
- 若房间满员，抛出 `ROOM_FULL`。

#### 广播/响应

单播 `ROOM_JOIN_REP`，payload 中回显 `nonce`：

```json
{
  "type": "ROOM_JOIN_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "Base64(DES_KcGs({\"type\":\"ROOM_JOIN_REP\",\"ok\":true,\"nonce\":\"...\",...}))"
}
```

房间广播：

- `ROOM_STATE`
- `SNAPSHOT`

### 1.5 `ROOM_READY_REQ`（旧名 `READY`）

#### 触发条件

```json
{
  "type": "ROOM_READY_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "Base64(DES_KcGs({\"type\":\"ROOM_READY_REQ\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"ready\":true,\"ts\":...,\"nonce\":\"...\"}))"
}
```

顶层必需字段：`sessionId`、`roomId`、`payload`。

#### 调用链

```text
handle_message()
└─ dispatch_authenticated_message()
   └─ handle_ready()
      ├─ self._require_session(websocket)
      ├─ require session.room_id and session.client_id
      ├─ require_fields(data, ("sessionId", "roomId", "payload"))
      ├─ require data.sessionId == session.session_id
      ├─ self.decrypt_payload(session, data)
      │  ├─ self.security.decrypt_session_payload()
      │  │  └─ decrypt_session_object(session, data, "payload")
      │  │     ├─ des_decrypt_object(session.kc_gs, data.payload)
      │  │     ├─ timestamp_in_window()
      │  │     └─ replay_guard.check_and_store()
      │  └─ self._expire_reconnect_grace(now_ms())
      ├─ require payload.type == ROOM_READY_REQ
      ├─ require payload.sessionId == session.session_id
      ├─ require payload.roomId == session.room_id
      ├─ room_state = self.room_states[session.room_id]
      ├─ require session.client_id in room_state.players
      ├─ require room_state.status == WAITING
      ├─ room_state.players[session.client_id]["ready"] = bool(payload.ready)
      ├─ encrypt_payload(session, ROOM_READY_REP payload)
      ├─ send_json(ROOM_READY_REP)
      └─ broadcast_room_state(session.room_id)
```

#### 状态变更

- `room_state["players"][session.client_id]["ready"]` 被设置为客户端传入的 `ready`。
- 只有 `WAITING` 状态允许 ready，`STARTING`、`PLAYING`、`FINISHED` 会返回 `ROOM_NOT_WAITING`。
- `self.replay_cache` 新增 payload nonce。
- 可能触发过期重连窗口清理。

#### 广播/响应

单播 `ROOM_READY_REP`：

```json
{
  "type": "ROOM_READY_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "Base64(DES_KcGs({\"type\":\"ROOM_READY_REP\",\"ok\":true,\"ready\":true,\"nonce\":\"...\",...}))"
}
```

然后向房间内在线成员广播 `ROOM_STATE`。`ROOM_STATE` 的 `canStart` 条件是：

- `room_state.status == "WAITING"`
- `len(players) >= 2`
- 所有 `players[*].ready == True`

### 1.6 `ROOM_START_REQ`

#### 触发条件

```json
{
  "type": "ROOM_START_REQ",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "auth": "Base64(DES_KcGs({\"type\":\"ROOM_START_REQ\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"ts\":...,\"nonce\":\"...\"}))"
}
```

顶层必需字段：`sessionId`、`roomId`、`auth`。

#### 调用链

```text
handle_message()
└─ dispatch_authenticated_message()
   └─ handle_start_game()
      ├─ self._require_session(websocket)
      ├─ require session.room_id and session.client_id
      ├─ require_fields(data, ("sessionId", "roomId", "auth"))
      ├─ require data.sessionId == session.session_id
      ├─ self.decrypt_auth(session, data)
      ├─ require auth.type == ROOM_START_REQ
      ├─ require auth.sessionId == session.session_id
      ├─ require auth.roomId == session.room_id
      ├─ room_state = self.room_states[session.room_id]
      ├─ require room_state.hostClientId == session.client_id
      ├─ require room_state.status == WAITING
      ├─ require len(players) >= 2
      ├─ require all(players.ready)
      ├─ room_state["status"] = "STARTING"
      ├─ broadcast_room_state(session.room_id)
      └─ broadcast_game_start(session.room_id)
         ├─ match_id = "match-{random}"
         ├─ 对每个 peer 构造 build_room_state_payload()
         ├─ payload 添加 sceneName="MainGame"
         ├─ payload 添加 matchId / countdownMs
         ├─ encrypt_payload(peer_session, payload)
         └─ send_json(ROOM_START_REP)
```

#### 状态变更

- `room_state["status"]` 从 `WAITING` 变为 `STARTING`。
- 不在这里创建 `room_ticks` 或 `room_combats` 的新运行时；真正重置发生在首个 `INPUT` 到达时。
- `self.replay_cache` 新增 auth nonce。

#### 广播/响应

没有单独只发给房主的 ack。成功后广播：

1. `ROOM_STATE`：房间状态变为 `STARTING`。
2. `ROOM_START_REP`：发给房间每个已认证在线成员。

`ROOM_START_REP` 顶层（使用每个客户端各自 `KcGs` 加密）：

```json
{
  "type": "ROOM_START_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "Base64(DES_KcGs({\"type\":\"ROOM_START_REP\",\"sceneName\":\"MainGame\",\"matchId\":\"match-123\",\"countdownMs\":3000,...}))"
}
```

### 1.7 `INPUT`

#### 触发条件

客户端已在房间中，发送高频输入：

```json
{
  "type": "INPUT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": true,
  "payload": "Base64(DES_KcGs(InputPayload JSON))"
}
```

顶层必需字段：`sessionId`、`roomId`、`payload`。

`payloadEncrypted` 可省略，默认 `true`。当 `payloadEncrypted=false` 时，`payload` 可以是 dict 或 JSON 字符串；这种兼容路径不会执行 DES 解密，也不会执行 `ts/nonce` 防重放校验。

加密 payload 至少要求：

```json
{
  "type": "INPUT",
  "sessionId": "sess-...",
  "roomId": "AB12",
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
  "clientPosY": 0.0,
  "clientVelX": 0.0,
  "clientVelY": 0.0,
  "equippedWeaponId": "weapon-id",
  "equippedEffectIds": [],
  "ts": 1710000000000,
  "nonce": "..."
}
```

#### 调用链

```text
handle_message()
└─ dispatch_authenticated_message()
   └─ handle_input()
      ├─ self._require_session(websocket)
      ├─ require session.room_id and session.client_id
      ├─ require_fields(data, ("sessionId", "roomId", "payload"))
      ├─ require data.sessionId == session.session_id
      ├─ require data.roomId == session.room_id
      ├─ payloadEncrypted 默认 true
      ├─ if payloadEncrypted
      │  └─ self.decrypt_payload(session, data)
      ├─ else
      │  ├─ payload 是 dict: 直接使用
      │  └─ payload 是 str: json.loads(payload)
      ├─ require payload.type == INPUT
      ├─ require payload.sessionId == session.session_id
      ├─ require payload.roomId == room_id
      ├─ if room_state.status == STARTING
      │  ├─ if not runtime_reset_done
      │  │  └─ reset_room_runtime_state(room_id)
      │  │     ├─ self.room_ticks[room_id] = 0
      │  │     ├─ self.room_combats[room_id] = CombatRuntime()
      │  │     ├─ 清理 room_loots / room_next_loot_tick
      │  │     └─ 重置房间内所有 session 对局字段
      │  └─ room_state["status"] = "PLAYING"
      ├─ tick = get_room_tick(room_id)
      ├─ combat = get_room_combat(room_id)
      ├─ room_sessions = get_room_sessions(room_id)
      ├─ cmd = parse_input_payload(payload)
      ├─ seq 校验
      │  └─ cmd.seq <= session.last_seq: maybe_broadcast_snapshot(rejectReason) 后 return
      ├─ 禁止客户端上传权威字段
      │  └─ damagePercent/stocks/isDead/damage/hitResult/killCount: snapshot 后 return
      ├─ session.last_seq = cmd.seq
      ├─ 如果 session.is_dead 且等待 respawn
      │  ├─ 到 tick 后复活，push PLAYER_RESPAWN
      │  ├─ combat.step_projectiles()
      │  ├─ combat.step_melee_hitboxes()
      │  ├─ maybe_spawn_loot_for_room()
      │  ├─ step_loots_for_room()
      │  ├─ check_loot_pickups_for_room()
      │  ├─ cleanup_dead_loots_for_room()
      │  ├─ advance_room_tick()
      │  └─ maybe_broadcast_snapshot()
      ├─ 更新 aim / facing
      ├─ 计算 hitstun
      ├─ 水平移动或击退移动
      ├─ get_standing_platform()
      ├─ 处理 drop / jump
      ├─ attack_hold_ticks 更新
      ├─ should_execute_attack()
      │  └─ combat.execute_attack()
      │     ├─ ranged: spawn_projectile()
      │     │  ├─ _spawn_one_projectile()
      │     │  ├─ self.projectiles[projId] = ServerProjectile
      │     │  ├─ push_event(PROJECTILE_SPAWNED)
      │     │  └─ apply_effects_on_projectile_spawned()
      │     ├─ melee: spawn_melee_hitbox()
      │     └─ apply_effects_on_attack_execute()
      ├─ step_vertical(session)
      ├─ combat.step_projectiles()
      │  ├─ TTL / before_move effects
      │  ├─ world collision
      │  ├─ player collision
      │  ├─ apply_hit()
      │  ├─ push_event(PLAYER_HIT / PROJECTILE_DESTROYED / EXPLOSION_TRIGGERED)
      │  └─ 清理 dead projectiles
      ├─ combat.step_melee_hitboxes()
      │  ├─ 查找 hitbox 范围内玩家
      │  ├─ apply_hit()
      │  └─ 清理 dead hitboxes
      ├─ maybe_spawn_loot_for_room()
      ├─ step_loots_for_room()
      ├─ check_loot_pickups_for_room()
      ├─ cleanup_dead_loots_for_room()
      ├─ is_out_of_bounds()
      │  ├─ stocks -= 1
      │  ├─ is_dead / respawn_at_tick
      │  └─ push_event(PLAYER_OUT_OF_BOUNDS)
      ├─ advance_room_tick(room_id)
      ├─ check_game_over(room_id)
      │  └─ 可能 broadcast_result()
      └─ maybe_broadcast_snapshot(room_id, websocket, reject_reason)
         ├─ 按 SNAPSHOT_INTERVAL_TICKS 节流（默认 1，即每 tick 广播）
         ├─ 若 SNAPSHOT_FORCE_BROADCAST_ON_EVENTS 且有事件，强制广播
         ├─ broadcast_snapshot()
         └─ combat.clear_events()
```

#### 状态变更

房间状态：

- 首个 `INPUT` 会将 `room_state["status"]` 从 `STARTING` 改为 `PLAYING`。
- 首个 `INPUT` 还会设置 `room_state["runtime_reset_done"]=True`，并重置房间运行时。
- `check_game_over()` 可能将 `room_state["gameOver"]=True`、`room_state["status"]="FINISHED"`。

玩家状态：

- `session.last_seq` 更新为 `cmd.seq`。
- `session.pos_x`、`session.pos_y`、`session.vel_x`、`session.vel_y` 按服务端物理更新。
- `session.accepted_state`、`accepted_grounded`、`accepted_jump_count`、`accepted_drop` 更新。
- `session.facing`、`aim_x`、`aim_y` 更新。
- 攻击时更新 `attack_hold_ticks`、`last_attack_tick`、`last_attack_weapon_id`。
- 命中时更新目标的 `damage_percent`、`last_knockback_x/y`、`last_hit_tick`、`hitstun_until_tick`、`accepted_state="Hitstun"`。
- 出界时扣 `stocks`，设置 `is_dead` 和 `respawn_at_tick`；复活时恢复位置、速度、伤害、状态。
- 拾取掉落物时更新 `session.equipped_weapon_id` 或 `session.equipped_effect_ids`。

运行时状态：

- `self.room_ticks[room_id]` 每处理有效帧后递增。
- `self.room_combats[room_id]` 内的 `projectiles`、`melee_hitboxes`、`pending_events` 变化。
- `self.room_loots[room_id]` 增删掉落物。
- `self.room_next_loot_tick[room_id]` 更新下一次掉落物生成时间。

拒绝路径：

- `cmd.seq <= session.last_seq` 时不推进输入，只通过 `SNAPSHOT.rejectReason` 告知。
- payload 中包含 `damagePercent`、`stocks`、`isDead`、`damage`、`hitResult`、`killCount` 会被拒绝，因为这些是服务端权威字段。

#### 广播/响应

`INPUT` 没有直接 ack。主要输出是房间 `SNAPSHOT`（带 `payloadEncrypted` 标记）：

```json
{
  "type": "SNAPSHOT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": true,
  "payload": "Base64(DES_KcGs({\"type\":\"SNAPSHOT\",\"tick\":...,\"players\":[],\"projectiles\":[],\"loots\":[],\"events\":[],...}))"
}
```

`payloadEncrypted` 取值规则（由 `SNAPSHOT_ENCRYPT_EVERY_N` 配置控制）：
- `SNAPSHOT_ENCRYPT_EVERY_N = 0`：全部明文（`payloadEncrypted: false`，`payload` 为明文字符串）。
- `SNAPSHOT_ENCRYPT_EVERY_N = 1`：每条都加密（`payloadEncrypted: true`）。
- `SNAPSHOT_ENCRYPT_EVERY_N = N (N>1)`：每 N 条加密一次，其余明文。当前默认值 `100`。

如果对局结束，`check_game_over()` 会广播 `RESULT`（带 `payloadEncrypted: true`）：

```json
{
  "type": "RESULT",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payloadEncrypted": true,
  "payload": "Base64(DES_KcGs({\"type\":\"RESULT\",\"winnerUserId\":...,\"reason\":\"STOCK_ZERO\",\"players\":[...]}))"
}
```

### 1.8 `CHAT`（已从当前代码中移除）

`CHAT` 消息类型已从当前代码中完全移除：
- `server/gs_protocol.py` 中无 `TYPE_CHAT` 定义。
- `server/game_config.py` 中无 `TYPE_CHAT` 导入。
- `RelayServer.dispatch_authenticated_message()` 中无 `CHAT` 分支。

客户端发送 `type: "CHAT"` 会进入 `else` 分支，收到：

```json
{"type":"ERROR","error":"UNSUPPORTED_TYPE: CHAT"}
```

### 1.9 `LEAVE_ROOM`

#### 触发条件

客户端必须已认证。当前 `handle_leave_room()` 不校验 `auth` 或 `payload`，也不检查顶层 `sessionId`/`roomId`：

```json
{
  "type": "LEAVE_ROOM"
}
```

即使携带额外字段，当前实现也不读取。

#### 调用链

```text
handle_message()
└─ dispatch_authenticated_message()
   └─ handle_leave_room()
      ├─ session = self.sessions.get(websocket)
      ├─ 如果 session is None 或没有 session.room_id: return
      ├─ room_id = session.room_id
      ├─ remove_player_from_room_state(websocket, room_id)
      │  ├─ 从 room_state.players 移除当前 client_id
      │  ├─ 清理绑定到同 websocket 的其他 player key
      │  ├─ 如果离开者是 hostClientId
      │  │  ├─ 有剩余玩家: hostClientId 交给 slotNo 最小玩家
      │  │  └─ 无剩余玩家: self.room_states.pop(room_id)
      ├─ remove_from_room(websocket, room_id)
      │  ├─ self.rooms[room_id].discard(websocket)
      │  └─ 如果 members 为空: self.rooms.pop(room_id)
      ├─ session.room_id = None
      ├─ session.client_id = None
      └─ broadcast_room_state(room_id)
```

#### 状态变更

- `self.room_states[room_id]["players"]` 移除当前玩家。
- 若房主离开，`hostClientId` 顺延给剩余玩家中 `slotNo` 最小者。
- 若房间无人，`self.room_states.pop(room_id)` 删除房间状态，同时调用 `cleanup_room_runtime_state(room_id)` 清理 `room_ticks`、`room_combats`、`room_loots`、`room_next_loot_tick`。
- `self.rooms[room_id]` 移除当前 websocket；空集合时删除 `self.rooms[room_id]`。
- `session.room_id=None`，`session.client_id=None`。
- 当前实现不清理 `self.sessions_by_id`，因为 socket 仍保持认证连接。

#### 广播/响应

- 没有单播 ack。
- 对剩余房间成员广播 `ROOM_STATE`。
- 如果房间已被删除，`broadcast_room_state(room_id)` 遍历不到 peers，通常不会发出消息。
- 若房间因无人而删除，同时清理房间运行时状态（ticks/combat/loots）。

### 1.10 `RECONNECT_REQ`

#### 触发条件

`RECONNECT_REQ` 可以在未认证的新 websocket 上发送，因为旧会话保存在 `self.reconnect_grace` 中。

```json
{
  "type": "RECONNECT_REQ",
  "clientId": "Client1",
  "sessionId": "sess-...",
  "ticket": "Base64(DES_K_GS(ServiceTicket JSON))",
  "auth": "Base64(DES_oldKcGs({\"type\":\"RECONNECT_REQ\",\"clientId\":\"Client1\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"ts\":...,\"nonce\":\"...\"}))",
  "payload": "Base64(DES_oldKcGs({\"type\":\"RECONNECT_REQ\",\"clientId\":\"Client1\",\"sessionId\":\"sess-...\",\"roomId\":\"AB12\",\"lastProcessedSeq\":10,\"nonce\":\"...\"}))"
}
```

顶层必需字段：`clientId`、`sessionId`、`ticket`、`auth`、`payload`。

#### 调用链

```text
handle_message()
└─ run_with_error_response("RECONNECT", handle_reconnect())
   └─ handle_reconnect()
      ├─ require_fields(data, ("clientId", "sessionId", "ticket", "auth", "payload"))
      ├─ grace_info = self.reconnect_grace.get(session_id)
      ├─ old_session = grace_info["session"]
      ├─ kc_gs = old_session.kc_gs
      ├─ self.db.connection()
      │  ├─ self.security.validate_service_ticket()
      │  │  ├─ des_decrypt_object(k_gs, encrypted_ticket)
      │  │  ├─ require_service=False
      │  │  ├─ require_kc=False
      │  │  ├─ 校验 ticketType/clientId/userId/loginGen/exp
      │  │  └─ _validate_user_account()
      │  ├─ require ticket.user_id == old_session.user_id
      │  ├─ self.security.decrypt_client_authenticator()
      │  │  ├─ des_decrypt_object(old_session.kc_gs, data.auth)
      │  │  └─ validate_timestamp_and_nonce()
      │  ├─ require auth.type == RECONNECT_REQ
      │  ├─ require auth.clientId == client_id
      │  ├─ require auth.sessionId == session_id
      │  ├─ auth_room_id = auth.roomId
      │  ├─ self._expire_reconnect_grace(current_ms)
      │  ├─ self.security.decrypt_client_payload()
      │  │  └─ des_decrypt_object(old_session.kc_gs, data.payload)
      │  ├─ require payload.type == RECONNECT_REQ
      │  ├─ require payload.clientId/sessionId/roomId 匹配 auth
      │  ├─ require payload.nonce == auth.nonce
      │  ├─ last_processed_seq = read_int(payload, "lastProcessedSeq")
      │  ├─ self.reconnect_grace.pop(session_id)
      │  ├─ old_session.last_seq = max(old_session.last_seq, last_processed_seq)
      │  ├─ old_session.authenticated = True
      │  ├─ self.sessions[websocket] = old_session
      │  ├─ self.sessions_by_id[session_id] = old_session
      │  ├─ self.rooms[room_id].add(websocket)
      │  ├─ room_state.players[clientId].websocket = websocket
      │  ├─ room_state.players[clientId].online = True
      │  ├─ record_success(event_type="RECONNECT_SUCCESS")
      │  └─ conn.commit()
      ├─ des_encrypt_object(kc_gs, RECONNECT_REP payload)
      ├─ send_json(RECONNECT_REP)
      ├─ broadcast_room_state(room_id)
      └─ broadcast_snapshot(room_id)
```

#### 状态变更

- `self.reconnect_grace[session_id]` 被弹出。
- 旧 `ClientSession` 被绑定到新 websocket：`self.sessions[websocket] = old_session`。
- `self.sessions_by_id[session_id]` 恢复到旧 session。
- `self.rooms[room_id]` 重新加入新 websocket。
- `room_state.players[client_id]["websocket"]` 指向新 websocket。
- `room_state.players[client_id]["online"] = True`。
- `old_session.last_seq` 至少推进到客户端上报的 `lastProcessedSeq`。
- `self.replay_cache` 记录 reconnect auth nonce。
- `security_event_log` 写入 `RECONNECT_SUCCESS`；失败会写 `RECONNECT_FAIL` 或相关事件。

#### 广播/响应

单播 `RECONNECT_REP`：

```json
{
  "type": "RECONNECT_REP",
  "sessionId": "sess-...",
  "roomId": "AB12",
  "payload": "Base64(DES_KcGs({\"type\":\"RECONNECT_REP\",\"ok\":true,\"phase\":\"PLAYING\",\"lastProcessedSeq\":10,\"ts\":...,\"nonce\":\"...\"}))"
}
```

随后广播：

- `ROOM_STATE`：通知房间成员该玩家 `online=True`。
- `SNAPSHOT`：同步当前对局权威状态。

常见错误：`RECONNECT_EXPIRED`、`SESSION_MISMATCH`、`CLIENT_MISMATCH`、`ROOM_MISMATCH`、`TYPE_MISMATCH`、`NONCE_MISMATCH`、`AUTH_EXPIRED`、`REPLAY_BLOCKED`。

### 1.11 断线和重连超时清理流程

#### 触发条件

`handle_client()` 的 websocket 循环结束或抛出 `ConnectionClosed` 后，`finally` 必定执行：

```text
cleanup_client(websocket, reason="disconnect")
```

`close_and_forget_socket()` 也会用于 join 时替换同 `ClientId` 的旧连接。

#### 调用链：对局中断线

```text
handle_client()
└─ finally cleanup_client(websocket, reason="disconnect")
   ├─ session = self.sessions.get(websocket)
   ├─ room_state = self.room_states.get(session.room_id)
   ├─ is_playing = room_state.status in ("PLAYING", "STARTING")
   ├─ remove_from_room(websocket, room_id)
   │  ├─ self.rooms[room_id].discard(websocket)
   │  └─ 如果 members 为空，只删除 self.rooms[room_id]，保留 runtime
   ├─ self.sessions.pop(websocket)
   ├─ _enter_reconnect_grace(session)
   │  ├─ self.reconnect_grace[session.session_id] = {
   │  │     "session": session,
   │  │     "disconnect_ms": now_ms(),
   │  │     "room_id": session.room_id,
   │  │     "client_id": session.client_id,
   │  │     "expire_ms": now_ms() + RECONNECT_GRACE_SECONDS * 1000
   │  │  }
   │  └─ room_state.players[clientId].online = False
   ├─ broadcast_room_state(room_id)
   └─ broadcast_snapshot(room_id)
```

#### 调用链：非对局中断线或不可重连清理

```text
cleanup_client()
├─ remove_player_from_room_state(websocket, room_id)
├─ remove_from_room(websocket, room_id)
├─ broadcast_room_state(room_id)
├─ broadcast_snapshot(room_id)
├─ self.sessions_by_id.pop(session.session_id)
├─ self.reconnect_grace.pop(session.session_id)
└─ self.sessions.pop(websocket)
```

#### 调用链：重连超时

`_expire_reconnect_grace(current_ms)` 会在以下路径被调用：

- `prune_replay_cache()`，由 `maintenance_loop()` 每 5 秒触发。
- `handle_gs_auth()` 成功验证 authenticator 后。
- `handle_reconnect()` 验证 reconnect auth 后。
- `decrypt_auth()` 和 `decrypt_payload()` 之后。

```text
_expire_reconnect_grace(current_ms)
├─ 找出 expire_ms <= current_ms 的 sessionId
├─ self.reconnect_grace.pop(sessionId)
├─ 如果 room_id/client_id 有效
│  └─ room_state.players.pop(client_id)
├─ self.sessions_by_id.pop(sessionId)
├─ 如果 old_session.user_id 存在
│  ├─ self.db.connection()
│  ├─ self.db.record_security_event(event_type="RECONNECT_TIMEOUT")
│  └─ conn.commit()
└─ print("[RECONNECT EXPIRED] ...")
```

#### 状态变更

- 对局中断线不会立即删除 `ClientSession`，而是从 `self.sessions` 移到 `self.reconnect_grace[sessionId]["session"]`。
- `self.rooms` 只保存在线 websocket，因此断线后该 websocket 会被移除。
- `self.room_states[room_id]["players"][clientId]` 在宽限期内保留，但 `online=False`。
- 超时后从 `room_state.players` 删除该 `clientId`，并清理 `self.sessions_by_id`。
- `_expire_reconnect_grace()` 当前是同步函数，不会主动广播 `ROOM_STATE`；下一次业务广播或快照才会让客户端看到最终变化。

#### 广播/响应

- 对局中断线：广播 `ROOM_STATE` 和 `SNAPSHOT`。
- 非对局清理：广播 `ROOM_STATE` 和 `SNAPSHOT`。
- 重连超时：当前只清理状态和写 DB 审计，不直接广播。

## 2. 输入层解密流程

### 2.1 顶层 JSON 和加密字段

WebSocket 上传的最外层始终是 UTF-8 JSON 字符串，`type` 必须明文存在。加密只发生在字段值中：

- `ticket`：`Base64(IV + DES-CBC(K_GS, ServiceTicket JSON))`
- `auth`：`Base64(IV + DES-CBC(KcGs, Authenticator JSON))`
- `payload`：`Base64(IV + DES-CBC(KcGs, Payload JSON))`

`crypto_utils.des_decrypt_object()` 的固定流程：

```text
des_decrypt_object(key, ciphertext_b64)
├─ 校验 key 长度 == DES_KEY_BYTES
├─ b64decode(ciphertext_b64)
├─ 校验 raw 长度 > DES_BLOCK_BYTES
├─ iv = raw[:DES_BLOCK_BYTES]
├─ ciphertext = raw[DES_BLOCK_BYTES:]
├─ cbc_decrypt(key, iv, ciphertext)
└─ json.loads(plaintext)
```

`crypto_utils.des_encrypt_object()` 反向执行，并为每个响应随机生成 `iv`。

### 2.2 `K_GS` 的用途

`K_GS` 是 GS 与 TGS 共享的长期 DES key：

- 来源：`load_runtime_keys()` 从环境变量 `K_GS_BASE64` 读取并 base64 解码。
- 长度：必须等于 `DES_KEY_BYTES`，也就是 8 bytes。
- 用途：只用于 `validate_service_ticket()` 解密 `ServiceTicket`。
- 客户端不可读取 `ServiceTicket` 内容，只有 GS 能用 `K_GS` 解开。

`GS_AUTH` 中 `validate_service_ticket(require_service=True, require_kc=True)` 会：

- 校验 `ticketType == "SERVICE_TICKET"`。
- 校验 `service == self.config.gs_service_name`。
- 校验 `ticket.clientId == data.clientId`。
- 读取并校验 `userId`、`username`、`loginGen`、`exp`。
- 读取 `kcGs` 并 base64 解码为本次会话 DES key。
- 检查 ticket 是否过期。
- 查询 `user_account`，校验用户存在、`status == 1`、`login_gen` 和 `username` 匹配。

`RECONNECT_REQ` 中 `validate_service_ticket(require_service=False, require_kc=False)` 仍使用 `K_GS` 校验 ticket 真实性和用户状态，但不从 ticket 中取新的 `KcGs`，而是继续使用旧 `ClientSession.kc_gs`。

### 2.3 `KcGs` 的用途

`KcGs` 是客户端与 GS 的会话 DES key：

- `GS_AUTH` 时从 `ServiceTicket.kcGs` 提取。
- `RECONNECT_REQ` 时从旧 `ClientSession.kc_gs` 读取。
- 业务消息中 `auth` 和 `payload` 都使用 `KcGs` 解密。
- 服务端所有加密回包 payload 也使用对应客户端自己的 `KcGs` 加密。

不同消息使用的 key：

| 消息/字段 | 解密 key | 说明 |
| --- | --- | --- |
| `GS_AUTH.ticket` | `K_GS` | 解密 TGS 签发的 `ServiceTicket` |
| `GS_AUTH.auth` | `KcGs` from ticket | 证明客户端持有 `KcGs` |
| `RECONNECT_REQ.ticket` | `K_GS` | 重新确认用户身份和 ticket 有效性 |
| `RECONNECT_REQ.auth` | old `session.kc_gs` | 证明重连者持有旧会话 key |
| `RECONNECT_REQ.payload` | old `session.kc_gs` | 上报 `lastProcessedSeq` 等重连数据 |
| `ROOM_CREATE_REQ.auth` | current `session.kc_gs` | 会话内 auth |
| `ROOM_JOIN_REQ.auth` | current `session.kc_gs` | 会话内 auth |
| `ROOM_READY_REQ.payload` | current `session.kc_gs` | 会话内 payload |
| `ROOM_START_REQ.auth` | current `session.kc_gs` | 会话内 auth |
| `INPUT.payload` | current `session.kc_gs` | `payloadEncrypted=true` 时 |
| 服务端响应 `payload` | target session `kc_gs` | 每个客户端各自加密 |

### 2.4 时间窗和 nonce 防重放

`gs_security.timestamp_in_window(timestamp, current_ms, window_ms)` 要求：

```text
current_ms - window_ms <= timestamp <= current_ms + MAX_FUTURE_TIMESTAMP_SKEW_MS
```

其中 `window_ms = config.authenticator_window_seconds * 1000`，默认配置来自 `AUTH_AUTHENTICATOR_WINDOW_SECONDS`，默认 30 秒。

防重放由 `ReplayGuard` 实现：

```text
ReplayGuard.check_and_store(user_id, client_id, nonce, current_ms, window_ms)
├─ prune(current_ms)
├─ replay_key = "{userId}/{clientId}/{nonce}"
├─ 如果 replay_key 仍未过期: return False
└─ self.cache[replay_key] = current_ms + window_ms
```

失败时抛出 `REPLAY_BLOCKED`。

会触发防重放的路径：

- `GS_AUTH.auth`：`decrypt_client_authenticator()`
- `RECONNECT_REQ.auth`：`decrypt_client_authenticator()`
- 会话内 `auth`：`decrypt_session_object(..., "auth")`
- 会话内加密 `payload`：`decrypt_session_object(..., "payload")`

不会触发防重放的路径：

- `RECONNECT_REQ.payload`：只 DES 解密，不做 ts/nonce 时间窗校验，但要求 `payload.nonce == auth.nonce`。
- `INPUT` 且 `payloadEncrypted=false`：当前兼容路径不执行 DES、ts、nonce 校验。
- `LEAVE_ROOM`：当前不解密 `auth` 或 `payload`。

### 2.5 DB 安全审计

`GsSecurityService` 在认证相关路径写 `security_event_log`：

- `GS_AUTH_SUCCESS`
- `GS_AUTH_FAIL`
- `RECONNECT_SUCCESS`
- `RECONNECT_FAIL`
- `REPLAY_BLOCKED`
- `TICKET_EXPIRED`
- `TICKET_INVALIDATED`
- `RECONNECT_TIMEOUT`

用户状态校验通过 `gs_db.GsDao.find_user_by_id()` 查询 `user_account`：

```sql
SELECT user_id, username, login_gen, status
FROM user_account
WHERE user_id = %s
```

写审计通过 `gs_db.GsDao.record_security_event()` 插入 `security_event_log`。

## 3. 关键数据结构

### 3.1 `RelayServer` 内存状态

| 结构 | 类型 | 用途 |
| --- | --- | --- |
| `self.sessions` | `Dict[Any, ClientSession]` | 在线 websocket 到 `ClientSession` 的映射。刚连接时先放未认证 session；认证后承载用户和对局状态。 |
| `self.sessions_by_id` | `Dict[str, ClientSession]` | `sessionId` 到 `ClientSession` 的映射，用于会话管理、清理和重连恢复。 |
| `self.replay_cache` | `Dict[str, int]` | 防重放缓存，key 是 `{userId}/{clientId}/{nonce}`，value 是过期时间戳。 |
| `self.reconnect_grace` | `Dict[str, Dict[str, Any]]` | 断线重连宽限期，key 是 `sessionId`，value 保存旧 session、room、client、expire_ms。 |
| `self.rooms` | `Dict[str, Set[Any]]` | 房间到在线 websocket 集合的映射；断线进入 grace 后 websocket 会从这里移除。 |
| `self.room_states` | `Dict[str, Dict[str, Any]]` | 房间生命周期状态，保存 `hostClientId`、`status`、`players`、`runtime_reset_done`、`gameOver` 等。 |
| `self.room_ticks` | `Dict[str, int]` | 每个房间独立 tick。 |
| `self.room_combats` | `Dict[str, CombatRuntime]` | 每个房间独立战斗运行时，避免多房间串状态。 |
| `self.room_loots` | `Dict[str, Dict[str, ServerLoot]]` | 每个房间的掉落物。 |
| `self.room_next_loot_tick` | `Dict[str, int]` | 每个房间下一次掉落物生成 tick。 |
| `self.tick` | `int` | 旧兼容字段；正式对局逻辑应以 `room_ticks` 为准。 |
| `self.combat` | `CombatRuntime` | 旧兼容字段；正式对局逻辑应以 `room_combats` 为准。 |

### 3.2 `room_state`

新房间由 `get_or_create_room_state()` 创建：

```python
{
    "hostClientId": "Client1",
    "status": "WAITING",
    "players": {}
}
```

对局中可能增加：

- `runtime_reset_done=True`：首个 `INPUT` 已经重置本房间运行时。
- `gameOver=True`：`check_game_over()` 已结算。
- `status` 的主要流转：`WAITING -> STARTING -> PLAYING -> FINISHED`。

`players` 结构：

```python
{
    "Client1": {
        "clientId": "Client1",
        "slotNo": 1,
        "ready": True,
        "websocket": websocket,
        "online": True
    },
    "Client2": {
        "clientId": "Client2",
        "slotNo": 2,
        "ready": True,
        "websocket": websocket,
        "online": True
    }
}
```

`online` 只在断线进入重连宽限期和重连成功时显式维护；普通 join 写入时未显式设置，`build_room_state_payload()` 会按默认 `True` 输出。

### 3.3 `ClientSession`

`ClientSession` 同时保存认证状态、房间身份和服务端权威对局状态。

认证相关：

- `authenticated`
- `session_id`
- `user_id`
- `username`
- `kc_gs`
- `login_gen`

房间相关：

- `client_id`：`Client1` 或 `Client2`
- `room_id`
- `last_seq`

移动和输入接受状态：

- `accepted_state`
- `accepted_grounded`
- `accepted_jump_count`
- `accepted_drop`
- `pos_x`、`pos_y`
- `vel_x`、`vel_y`
- `facing`
- `aim_x`、`aim_y`

战斗状态：

- `stocks`
- `is_dead`
- `respawn_at_tick`
- `damage_percent`
- `weight`
- `knockback_growth`
- `base_knockback`
- `last_knockback_x`
- `last_knockback_y`
- `last_hit_tick`
- `hitstun_until_tick`
- `equipped_weapon_id`
- `equipped_effect_ids`
- `attack_hold_ticks`
- `last_attack_tick`
- `last_attack_weapon_id`

### 3.4 `CombatRuntime`

每个房间通过 `get_room_combat(room_id)` 获得独立 `CombatRuntime`：

```python
{
    "projectiles": Dict[int, ServerProjectile],
    "melee_hitboxes": Dict[int, ServerMeleeHitbox],
    "next_projectile_id": int,
    "next_melee_hitbox_id": int,
    "next_event_seq": int,
    "pending_events": List[MatchEvent]
}
```

主要职责：

- `execute_attack()`：根据武器配置分发 ranged / melee。
- `spawn_projectile()` / `_spawn_one_projectile()`：创建 `ServerProjectile` 并 push `PROJECTILE_SPAWNED`。
- `spawn_melee_hitbox()`：创建近战判定框。
- `step_projectiles()`：推进投射物，处理 TTL、碰撞、效果、命中、销毁。
- `step_melee_hitboxes()`：推进近战命中。
- `apply_hit()`：服务端权威结算伤害、击退、硬直和 `PLAYER_HIT` 事件。
- `pending_events` 会进入 `SNAPSHOT.events`，广播后由 `maybe_broadcast_snapshot()` 清空。

### 3.5 `ServerProjectile`

`ServerProjectile` 表示服务端权威投射物：

- `proj_id`
- `owner_client_id`
- `weapon_id`
- `effect_ids`
- `pos_x`、`pos_y`
- `vel_x`、`vel_y`
- `radius`
- `damage`
- `base_knockback`
- `ttl`
- `alive`
- `timer`
- `state`
- `bullet_id`
- `visual_id`
- `rotation_deg`
- `hover_split_*` 运行时字段

它会在 `SNAPSHOT.projectiles` 中广播给客户端。

### 3.6 `ServerLoot`

`ServerLoot` 表示房间内掉落物：

- `loot_id`
- `loot_type`：`effect` 或 `weapon`
- `item_id`
- `pos_x`、`pos_y`
- `radius`
- `alive`
- `vel_y`
- `landed`
- `target_platform_y`

掉落物流程：

```text
maybe_spawn_loot_for_room()
└─ 创建 ServerLoot, 写入 self.room_loots[room_id], push LOOT_SPAWNED

step_loots_for_room()
└─ 应用 LOOT_GRAVITY, 落到平台后 push LOOT_LANDED

check_loot_pickups_for_room()
└─ 玩家接近后 apply_loot_to_session(), loot.alive=False, push LOOT_PICKED

cleanup_dead_loots_for_room()
└─ 从 self.room_loots[room_id] 删除非 alive 掉落物
```

`SNAPSHOT.loots` 会广播当前 alive 掉落物。
