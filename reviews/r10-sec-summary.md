# R10 安全摘要 — 供 Security Reviewer 使用

> 从 DESIGN.md、tech-choices.md、P0-02/03/04/05/09 提取的关键安全决策
> 生成日期: 2026-06-14 | Phase 0 Architecture Freeze

---

## 1. 认证与授权模型

### 1.1 三层信任模型

```
WASM 玩家代码  →  不可信 (sandbox + 进程隔离)
Rhai 规则模组  →  服主信任 (内嵌引擎, AST 解释)
Rust 引擎核心  →  不可变 (编译时安全)
```

### 1.2 认证流程

- **OAuth2** (GitHub/Google) → 服务端签发 **短期 Ed25519 证书**（24h 默认过期）
- 证书内容: `player_id` (服务端分配), `public_key`, `issued_at`, `expires_at`, `issuer_sig`
- **player_id 由服务端注入**，客户端不可自报。若客户端提供 `player_id`，服务端用自己的值覆盖
- Token: JWT，`exp = iat + 900s`，scope 控制 `swarm:deploy / swarm:read / swarm:debug / swarm:admin`
- 撤销: ban 玩家 = 吊销证书 + 清除 WASM 模块缓存条目

### 1.3 代码签名

- WASM 部署附带证书签名: 客户端用证书私钥签名 `Blake3(WASM bytes)`
- 服务端验签 → 从证书提取 `player_id` → 计算 `module_hash = Blake3(WASM bytes)`
- tick 执行阶段验证 `module_hash` 匹配已部署模块
- 证书过期/吊销时清除缓存条目（每次 tick 执行前检查 auth token 有效性）

---

## 2. WASM 沙箱安全 (P0-4)

### 2.1 多层隔离

| 层级 | 机制 | 参数 |
|------|------|------|
| OS 进程隔离 | 每玩家独立 sandbox worker 进程 | per-tick fork → 执行 → kill |
| 系统调用过滤 | seccomp(bpf) 白名单 | 仅 mmap/mprotect/futex/clone(VFORK) 等 |
| 资源控制 | cgroup v2 | memory.max=128MB, cpu.max=0.25s/3s, pids.max=32 |
| 网络隔离 | 无网络命名空间 | 仅 Unix domain socket 与引擎通信 |
| 文件系统 | 只读根文件系统 | 独立 /tmp (tmpfs, 16MB) |

### 2.2 Wasmtime 配置

| 限制 | 值 | 说明 |
|------|-----|------|
| Fuel (CPU 指令) | 10,000,000/tick | Wasmtime fuel metering |
| 线性内存 | 64 MB | static_memory_maximum_size, 不允许动态增长 |
| 执行时间 | 2500ms 墙钟 | Epoch interruption |
| 模块体积 | 5 MB | 预校验拒绝 |
| WASM 栈 | 1 MB | max_wasm_stack |
| 多线程 | 禁用 | wasm_threads(false) |
| WASI | 全禁 | 无文件/网络/时钟/随机数 |

### 2.3 模块预校验 (执行前)

1. 体积 ≤ 5MB
2. 必须导出 `tick` 函数
3. 禁止 `_start` 函数（防预执行）
4. 禁止 `__wasm_call_ctors`（防 active data segments 预执行）
5. 仅允许白名单 host function import
6. wasmparser 解析超时: 10ms

### 2.4 恶意 WASM 样本库 (CI 集成)

覆盖 8 类攻击: 资源耗尽、内存破坏、WASI 逃逸、Host 滥用、栈溢出、类型混淆、Start 函数、导入滥用。CI 断言每种恶意 WASM 被拒绝/超时/被杀，且引擎进程不崩溃。

### 2.5 Deferred Command Model

WASM 模块**不得直接调用 mutating host function**。所有状态变更通过 `tick(snapshot_json) → Command[]` JSON 延迟模型提交。允许的 host function 仅 4 个查询类（只读）: `host_get_terrain`, `host_get_objects_in_range`, `host_path_find`, `host_get_world_config`。

---

## 3. 指令校验与反作弊 (P0-2, P0-9)

### 3.1 单一校验管线

所有入口（WASM tick 输出、MCP tool、REST API、admin CLI）走同一 `校验 → 应用` 路径，无绕过。

```
Tick 输出 Schema 校验 → 反序列化 → 预校验 → 应用 → 记录 TickTrace
```

### 3.2 Tick 输出 JSON Schema

- 顶层必须为数组（非 object/null/primitive）
- 数组长度 ≤ 100
- 总字节 ≤ 256 KB
- 深度 ≤ 10
- `additionalProperties: false`
- 校验失败 → 整个 tick 输出丢弃，不计入 refund

### 3.3 Source Gate (P0-9)

12 种指令来源各有独立的能力约束矩阵。关键规则:
- **仅 `WASM` source 可提交 gameplay 指令**
- `MCP_Deploy` / `MCP_Query` 被 Source Gate 拒绝提交 gameplay 指令
- `Tutorial` 来源的指令**仅可在 `world.mode = "tutorial"` 的世界中接受**，否则静默丢弃 + 审计
- `Rollback` 需**双人审计**：两个不同 admin 的 Ed25519 签名

### 3.4 硬性边界

| 参数 | 限值 | 防御目标 |
|------|------|---------|
| MAX_BODY_PARTS | 50 | spawn 向量膨胀攻击 |
| MAX_PATH_LENGTH | 100 | 寻路计算爆炸 |
| MAX_QUERY_RANGE | 10 | 范围扫描过广 |
| MAX_COMMANDS_PER_PLAYER | 100/tick | MCP 工具滥用 |
| MAX_DRONES_PER_PLAYER | 500 | 实体膨胀 |
| JSON 深度 | 10 | serde_json 递归 DoS |
| 字符串最大长度 | 256 字符 | 通用保护 |
| i32 坐标范围 | [-128, 127]/房间 | 溢出攻击 |

### 3.5 Fuel Refund 安全模型

- 竞争导致的拒绝（SourceEmpty/TileOccupied/TargetFull）→ 退 50% fuel
- 玩家自身错误的拒绝 → 不退
- **退还仅作用于下一 tick**（禁止同 tick 内计算放大）
- 上限: `MAX_FUEL × 10%`/tick
- 同源重复失败: 仅首次退款
- 连续 3 tick 退还率 > 80% → throttle（下一 tick fuel budget 降为 50%）
- **Deploy-reset 规则**: 模块变更 → 旧 refund credit 作废（防跨模块预算转移）

---

## 4. Prompt Injection 防御 (P0-3)

### 4.1 输入约束

- 玩家名: 32 字符，仅 `[a-zA-Z0-9 _-]`。Prompt injection delimiter 必须使用此字符集之外的字符（如 `[[`/`]]` 或 Unicode），确保玩家名无法伪造系统与用户内容的边界
- 所有玩家原创字符串标注 `"untrusted": true, "source_player": N`

### 4.2 AI SDK 分隔符契约

```
‖‖‖GAME_DATA‖‖‖ ... ‖‖‖END_GAME_DATA‖‖‖
```

AI agent 的 prompt 模板用分隔符包裹游戏数据，明确标注数据不可信、不可执行。

### 4.3 事件响应

Prompt injection 检测 → 隔离 AI 玩家 → 审查快照内容 → 修补过滤规则

---

## 5. 信息泄露防护 (P0-5)

### 5.1 统一可见性函数

```rust
fn is_visible_to(entity: &Entity, player_id: PlayerId, tick: u64) -> bool;
```

所有输出面（snapshot、MCP、WebSocket、REST、replay）调用此函数。无绕过。"这只是调试数据"不是例外。

### 5.2 隐藏信息

| 数据 | 可见性 |
|------|--------|
| 其他玩家资源数量 | ❌ 隐藏 |
| 其他玩家 Controller 进度 | ❌ 隐藏 |
| 其他玩家冷却/疲劳 | ❌ 隐藏 |
| RNG 种子 | ❌ 始终隐藏 |
| 其他玩家被拒绝指令 | ❌ 隐藏 |
| 其他玩家 WASM 错误 | ❌ 隐藏 |
| 全局存储余额 | 部分公开（排行榜区间） |
| 本地存储 | 完全私有 |

### 5.3 旁观者约束

- World 模式: `public_spectate = true` 时 `spectate_delay ≥ 50 tick`，防止实时信息泄露
- 旁观者仅见世界物理状态（位置/拥有者/战斗），不可见内部状态（代码/调试/资源）
- Arena 模式赛后自动公开 (≥100 tick 延迟)

### 5.4 可见性缓存

每 tick、每玩家计算一次并缓存 `(tick, player_id) → HashSet<EntityId>`。所有输出面读取同一缓存。防「快照说隐藏但 WebSocket 增量泄露」。

---

## 6. 网络安全 (P0-3, DESIGN)

### 6.1 MCP 接口

- HTTPS + mTLS（外部）
- MCP Server 默认绑定 127.0.0.1（不对外暴露）
- nginx 网关: TLS 终止、限流、证书验证

### 6.2 HTTP 安全合同

| 约束 | 值 |
|------|-----|
| Host header 校验 | 强制，拒不匹配 Host |
| CORS Origin | 白名单，不用 `*` |
| max body size | 5 MB |
| SSE heartbeat | 30s |
| JSON-RPC batch | 禁用 |

### 6.3 限流

| 资源 | 限制 |
|------|------|
| deploy | 10/h |
| get_snapshot | 1/tick |
| 读类工具合计 | 50/tick |
| 调试工具合计 | 30/tick |
| 最大并发 MCP 连接 | 1000 |
| 每 IP 连接速率 | 10/s |

---

## 7. 确定性与防作弊

### 7.1 Determinism Contract

- PRNG: **Blake3 XOF**（与哈希同原语，纯软件 ~6 GB/s）。`blake3::Hasher::update_with_seek(seed, offset)` 替代 ChaCha keystream
- Hash: **Blake3**（统一哈希/PRNG/MAC）
- 禁 f64（跨平台非确定）。游戏引擎用 `i64 × 精度因子`。Rhai 模组同样禁用浮点，引擎侧关闭浮点运算
- HashMap → `IndexMap`（迭代顺序确定）
- ECS 执行顺序: `.chain()` 严格串行
- 种子洗牌: `Blake3(tick_number || world_seed)`

### 7.2 回放验证

- 每个 tick 产出 `state_checksum` 写入 TickTrace
- CI 对随机采样 tick 做 full replay 验证
- 回放 = 反作弊基础设施：任意房间状态可完整重现
- 异常检测：玩家 tick 间的世界变化超过物理上限 → 标记

---

## 8. Rhai 模组安全边界 (DESIGN §8.7)

### 8.1 能力限制

- 可用: `deduct_resource`, `award_resource`, `damage_entity`, `set_entity_flag`（白名单标记）, `emit_event`, `log_info/warn`
- 不可用: 文件 IO、网络、时钟、随机数（确定性要求）
- **`modify_entity` 已删除**（无属性白名单风险）

### 8.2 执行预算

| 资源 | 限制 | 超限行为 |
|------|------|---------|
| AST 节点数 | 10,000/tick | 跳过本次 tick |
| actions 调用 | 100/tick | 超出丢弃 |
| 玩家迭代 | 3,000 项 | 超出的玩家跳过 |
| 墙钟执行 | 100ms/tick | 强制终止，标记 degraded |

连续 10 tick 超限 → 自动禁用，需服主手动重新启用。所有 actions 记录到 TickTrace。

### 8.3 模组来源

- 服主自行安装/配置
- 模组市场: `swarm-mods.kagurazakalan.com`，社区 review + rating
- 模组是源码——服主可 fork、修改、提交 PR

---

## 9. Rollback 与管理操作安全 (P0-9)

- **双人审计**: Rollback 需两个不同 admin 的 Ed25519 签名，服务端在 Source Gate 前强制执行
- Admin scope: `swarm:admin`
- 全量 tick trace 仅 admin 可见
- `world_seed` 和 RNG 状态仅 admin 可见

---

## 10. 审计与监控 (P0-2, P0-3, DESIGN)

### 10.1 MCP 审计 (ClickHouse)

```sql
mcp_audit: timestamp, player_id, tool_name, parameters, scope, result, latency_ms, ip
```

不可修改，保留 90 天。

### 10.2 Fuel Refund 监控

| 指标 | 阈值 | 动作 |
|------|------|------|
| `refund_abuse_rate` | > 0.5 | 记录审计日志 |
| `source_empty_refund_pct` | > 80% | 标记可疑行为 |
| `consecutive_high_refund_ticks` | ≥ 3 | 自动 throttle |

### 10.3 Tick 审计 (FoundationDB)

```
/tick/{N}/state          — 完整世界状态
/tick/{N}/commands       — 全部玩家排序指令
/tick/{N}/rejections     — 被拒绝指令及原因
/tick/{N}/metrics        — tick 指标
/player/{id}/modules/    — WASM 模块历史
```

### 10.4 安全事件响应

| 事件 | 响应 |
|------|------|
| Token 泄露 | 撤销 jti，轮换 refresh token，审计 24h 日志 |
| 频繁部署 | 限流触发，标记玩家 |
| Prompt injection | 隔离 AI 玩家，审查快照，修补过滤 |
| 恶意 WASM | 拒绝模块，上传样本库，标记玩家 |

---

## 11. 编译器安全 (P0-4 §7)

| 资源 | 限制 | 目的 |
|------|------|------|
| 编译超时 | 30s | 防编译炸弹 |
| 编译内存 | 512 MB | 防编译 OOM |
| 编译进程 | 每次部署独立 fork | 不缓存编译中间产物 |
| 并发编译 | 最多 5 个 | 防编译阶段 DoS |
| 模块缓存 | 按 (module_hash, wasmtime_version) 缓存 | 每次 tick 执行前验证 auth token 仍有效 |

---

## 12. 全局存储反制机制 (DESIGN §8.2)

防止富有玩家垄断经济:

1. **累进存储税**: 30% 0% → 60% 0.01% → 85% 0.05% → 100% 0.20%/tick
2. **本地存储隐匿性**: 敌方无法获知建筑中资源量（需侦察/占领）
3. **全局↔本地转换需物流时间**: 10 tick (本地→全局), 5 tick (全局→本地)，运输中可被拦截

---

## 13. 安全 SLA

- 严重 CVE (CVSS ≥ 9.0): 72h 评估+补丁
- 高危 CVE (CVSS ≥ 7.0): 7 天修复
- 每季度审查 Wasmtime 安全公告
- Wasmtime 版本锁定 `=30.0`，CI 中 `cargo audit` 持续监控

---

## 14. 待安全评审的关注点

以下是从文档中识别的、需要 Security Reviewer 重点关注的领域:

1. **OAuth2 → Ed25519 证书的身份桥接**: 证书签发/吊销的正确性和时序
2. **Source Gate 实现的完整性**: 所有 12 种 source 的能力约束是否在代码中强制执行
3. **WASM 预校验的充分性**: `_start` 和 `__wasm_call_ctors` 检查是否覆盖所有 WASM 预执行向量
4. **Deferred Command Model 的一致性**: 是否所有 WASM host function import 校验强制只允许 4 个查询函数
5. **Fuel Refund 时序安全**: Deploy-reset 规则是否防止跨模块预算转移的竞态
6. **可见性缓存的正确性**: 所有输出面是否真正使用同一 `is_visible_to` 缓存
7. **Rhai actions 的 mini-validator**: 是否防止模组通过 `set_entity_flag` 绕过游戏规则
8. **Rollback 双人审计**: Ed25519 签名强制是否在 Source Gate 之前且不可绕过
9. **Tutorial 来源隔离**: Tutorial 指令在非 Tutorial 世界的静默丢弃是否影响回放一致性
10. **全局存储累进税**: 是否可能被分拆账户/多玩家协作绕过
