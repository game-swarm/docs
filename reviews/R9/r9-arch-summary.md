# R9 Architecture Summary — 关键架构决策

> 来源: DESIGN.md, tech-choices.md, ROADMAP.md, P0 spec 01/02/04/08/09
> 生成: 2026-06-14, Phase 0 Architecture Freeze

---

## 1. Tick 生命周期

来源: DESIGN §3.2, P0-1

三个阶段的严格顺序:

```
阶段一 COLLECT (~2500ms 硬截止)
  ├── 对每个活跃玩家并行:
  │   ├── 按玩家可见性构建 snapshot (不是 O(P×E)，先房间序列化再过滤)
  │   ├── 在独立 sandbox worker 进程中加载 WASM
  │   ├── fuel limit = 10M 指令 / tick
  │   ├── 调用 tick(snapshot) → 收集 Vec<Command>
  │   └── 超时/崩溃 → 该玩家空指令列表 (宽容失败)
  └── 输出: Map<PlayerId, Vec<Cmd>>

阶段二 EXECUTE (~500ms)
  ├── 种子洗牌: Blake3(tick_number || world_seed) 确定玩家顺序
  ├── 对每条指令 (按洗牌后顺序 + player 内 sequence 排序):
  │   ├── Source Gate → Auth Verify → P0-2 校验管线
  │   ├── 合法 → ECS system 链式应用
  │   ├── 资源竞争 → 先到先得
  │   └── 冲突 → 拒绝 + RejectionReason
  ├── 运行 tick 内 ECS systems (build→harvest→regen→move→combat→decay→death→spawn)
  ├── FDB 原子提交 (全或无)
  └── tick_counter 推进

阶段三 BROADCAST (即时)
  ├── 计算 delta (与上 tick 快照的实体差异)
  ├── FDB 持久化完成旁, Dragonfly 缓存更新
  ├── NATS → Gateway → WebSocket 客户端推送
  └── 每 N tick 写完整快照到 FDB (回放用)
```

**失败语义**: FDB commit 失败 → tick 放弃 (state 不变, tick_counter 不递增, fuel 退还)。连续 3 次 abandon → 引擎降级 (暂停新玩家加入、禁止代码部署)。WASM timeout/crash → 只影响单玩家，世界继续。

---

## 2. 确定性合同 (Determinism Contract)

来源: DESIGN §3.3, §8.8, tech-choices §1/§3/§8

四个支柱:

| 组件 | 选择 | 理由 |
|------|------|------|
| PRNG | Blake3 XOF | 与哈希同原语，消除 ChaCha 依赖。`blake3::Hasher::update_with_seek(seed, offset)` 天然适配 per-player per-tick 随机流 |
| 哈希 | Blake3 | 禁止 std::hash / SipHash (跨版本可变) |
| 种子洗牌 | Blake3(tick_number \|\| world_seed) | 每 tick 确定但不可预测的玩家执行顺序 |
| 数值类型 | 整数 + 定点数 | 禁止 f64 (跨平台/编译器非确定)。Rhai 引擎侧关闭浮点 |
| ECS 顺序 | `.chain()` | 严格串行。未来用 `.before()/.after()` 部分并行 |
| HashMap 顺序 | `indexmap` | 禁止 std::HashMap (迭代顺序非确定) |
| 排序 key | (shuffle_order, player_id, cmd_seq) | 相同种子 + 相同指令 → 相同顺序 |

**回放保证**: tick N-1 状态 + tick N RawCommand + world_seed + 激活模组列表 → 相同 Wasmtime 版本下 `execute_deterministic == recorded_state`。CI 随机采样 tick 做 full replay 验证。`state_checksum` 写入 TickTrace。

---

## 3. Deferred Command Model

来源: P0-4 §3, DESIGN §5, P0-8

**核心合同**: `tick(snapshot_json) → Command[]`

```
引擎写入 snapshot JSON → WASM 线性内存
  → host_get_terrain / host_get_objects_in_range / host_path_find (只读查询)
  → tick() 返回指令 JSON 列表
  → 引擎统一校验 (P0-2) → 应用到世界
```

**允许的 Host Function (仅查询、只读)**:
- `host_get_terrain(x, y)` → terrain_type
- `host_get_objects_in_range(x, y, range, out_ptr, out_len)`
- `host_path_find(from_x, from_y, to_x, to_y, out_ptr, out_len)`
- `host_get_world_config(key_ptr, key_len, out_ptr, out_len)`
- `host_get_world_rules(out_ptr, out_len)`

全部返回 i32 (0=成功, 负数=错误码)。out_ptr 由 WASM 分配，host 写入后边界校验。

**禁止的 Host Function**: 所有 mutating 操作 (move/harvest/transfer/build/attack/heal/spawn) 不得作为 host function 暴露。全部通过 JSON 指令提交。

**单一管线**: 所有入口 (WASM tick 输出、MCP tool、REST API、admin CLI) 走同一 `校验 → 应用` 路径。无绕过。

---

## 4. FDB 提交语义

来源: P0-1 §3.4, tech-choices §4

```
整个 EXECUTE 阶段包裹在 FoundationDB 事务中:

txn = fdb.create_transaction()
for command in sorted_commands:
    result = validate_and_apply(txn, command, world_state)
    if result.is_err():
        record_rejection(txn, command, result)
txn.set("/tick/{tick}/complete", true)
txn.commit()  // 全提交或全回滚
```

**关键语义**:
- **严格可序列化**: FoundationDB 是唯一在分布式 KV 中提供严格可序列化的选择。每 tick 原子提交——部分成功部分失败意味着世界状态不可回放。
- **放弃语义**: `txn.commit()` 失败 → 最多重试 3 次 → 全失败则 tick 放弃。状态不变、tick_counter 不递增、CPU fuel 退还。
- **连续 3 次 abandon → 降级模式**: 暂停新玩家加入、禁止 MCP_Deploy、告警升级。连续 10 tick 正常 → 自动退出。
- **数据布局**:
  ```
  /tick/{N}/state       → tick N 后的完整世界状态
  /tick/{N}/commands    → 全部玩家的排序指令
  /tick/{N}/rejections  → 被拒绝的指令及原因
  /tick/{N}/metrics     → TickMetrics
  /player/{id}/profile  → 玩家档案
  /player/{id}/modules/ → WASM 模块历史
  ```
- **Dragonfly 缓存**: 非权威层。FDB 是权威源。缓存 miss → FDB 回填。不一致时 FDB 为准。BROADCAST 阶段失败绝不回滚已提交 tick。

---

## 5. WASM 沙箱

来源: P0-4, tech-choices §2

双层隔离: OS 层 + Wasmtime 层

### OS 隔离 (sandbox worker 进程)

| 机制 | 配置 |
|------|------|
| seccomp(bpf) | 白名单系统调用 (read/write/mmap/futex 等，禁止 open/socket/fork/execve/clock_gettime/getrandom) |
| cgroup v2 | memory.max=128MB, swap=0, cpu.max=0.25s per 3s window, pids.max=32 |
| 网络 | 无网络命名空间。与引擎通过 Unix domain socket 通信 |
| 文件系统 | 只读根文件系统，独立 /tmp (tmpfs 16MB) |

### Wasmtime 配置

| 资源 | 限制 |
|------|------|
| Fuel (CPU 指令) | 10,000,000 / tick |
| WASM 线性内存 | 64 MB (static, 禁止动态增长) |
| 保护页 | 2MB 前后 guard page |
| 栈 | 1 MB |
| 实例数 | 1 |
| SIMD | 允许，relaxed SIMD 禁止 |
| 多线程 | 禁止 |
| Epoch interruption | 2500ms 硬截止 |
| 模块体积 | 5 MB (预校验) |
| 输出 JSON | 256 KB |

### 生命周期

每 tick fork → 加载 WASM → 执行 tick() → 返回指令 → kill。tick 间无状态保留。防止跨 tick 内存泄漏、长运行进程资源累积、受感染模块持久化。

### WASI 配置

**全禁白名单模式**: 无文件系统 (wasi:cli/*)、无时钟 (wasi:clocks/*)、无随机数 (wasi:random/*)、无网络 (wasi:sockets/*, wasi:http/*)。所有功能由引擎 host function 提供。

### 模块校验 (执行前)

1. 体积检查 (≤5MB)
2. WASM 二进制解析 + 校验
3. 必须导出 `tick` 函数
4. 禁止 `_start` 函数
5. 仅允许白名单 host function 导入

---

## 6. IDL 结构

来源: P0-8

**单一真相来源**: `game_api.idl` → 生成所有绑定

```
game_api.idl
  ├──→ Rust:   host function stubs + Command enum + Validator trait
  ├──→ TS SDK: types + autocomplete
  ├──→ MCP:    tool schemas + docs resources
  ├──→ Docs:   API reference (human + AI)
  └──→ Test:   property-based test generators
```

### 核心结构

```yaml
version: "1.0.0"
abi_version: 1  # host function 签名变更时递增

types:        # PlayerId/u32, ObjectId/u64, Position{x,y,room}, ResourceName/String, ResourceCost
enums:        # Direction(六边形6向), BodyPart(8种), StructureType(12种), RejectionReason(25种)
commands:     # 14 个 gameplay command (Move/MoveTo/Harvest/Transfer/Withdraw/Build/Repair/Attack/RangedAttack/Heal/Spawn/Recycle/TransferToGlobal/TransferFromGlobal)
              # 每个 command: params + validator 列表 + cost
body_cost:    # 8 种 body part 默认成本
host_functions: # tick(export) + 5 个只读查询函数
refund_policy:  # contention_lost=0.5, self_invalid=0.0
```

### 代码生成纪律

```bash
cargo run -- gen-api   # 从 IDL 生成代码
git diff --exit-code    # 生成代码与提交代码一致 → CI 失败即阻断
```

不允许手写 Command 变体或 host function。任何 API 修改必须从 IDL 开始。

---

## 7. ECS 排序

来源: DESIGN §3.2, P0-1 §3.3, tech-choices §1

### 固定执行顺序 (Bevy `.chain()`)

```rust
app.add_systems(Update, (
    build_system,          // 1. 建筑先出现
    harvest_system,        // 2. 资源被采集
    regeneration_system,   // 3. 资源点再生
    movement_system,       // 4. 单位移动
    combat_system,         // 5. 战斗结算
    decay_system,          // 6. 疲劳/冷却递减
    death_system,          // 7. 死亡单位清除
    spawn_system,          // 8. 新单位最后创建
).chain());
```

### 确定性属性

- `.chain()` 强制串行执行 → 给定相同输入产生相同输出
- 未来优化用 `.before()/.after()` 实现部分并行，但保持正确性不变
- 规则模组 (Rhai) 注入 hook: `tick_start.rhai` 在 chain 之前、`tick_end.rhai` 在 death_system 之后

### Bevy 选择理由

- `.chain()` 原生适配确定性排序
- 纯 Rust 无 FFI —— WASM 沙箱和 Bevy 共享同一 allocator
- 活跃社区 (Rust 游戏引擎最高)

---

## 8. Source Gate

来源: P0-9

### 12 个指令来源

| Source | 描述 | gameplay | 认证 |
|--------|------|----------|------|
| WASM | drone tick() 输出 | ✅ 是 | player_id (server-injected) |
| MCP_Deploy | AI 部署代码 | ❌ 否 | player_id + token scope |
| MCP_Query | AI 查询 | ❌ 否 | player_id + token scope |
| Admin | 管理操作 | ❌ 否 | admin_id + token scope |
| Replay | 回放 | ❌ (只读) | system |
| TestHarness | 自动化测试 | ❌ 否 | test_context |
| Tutorial | 教程引导 | ⚠️ 仅教程世界 | tutorial_session + world_id |
| Deploy | 代码部署管线 | ❌ 否 | player_id |
| Rollback | 管理回滚 | ❌ 否 | admin_id + rollback_token |
| RuleMod | Rhai 模组 actions | ⚠️ 仅经济+事件 | mod_id + world_owner_id |
| Simulate | 试运行 | ❌ (snapshot copy dry-run) | player_id + snapshot_id |
| DryRun | 编译前校验 | ❌ 否 | player_id |

### Source Gate 管线

```
RawCommand (携带 auth context)
    │
    ▼
Source Gate  ← 检查 source 是否允许提交 gameplay 指令
    WASM → pass
    MCP_Deploy → reject 403 (MCP 不能提交 gameplay 指令)
    │ pass
    ▼
Auth Verify  ← player_id 与 token 的 audience 绑定
    │
    ▼
P0-2 Command Validation Pipeline
```

### 不可伪造的 Auth Context

每条 RawCommand 携带的服务端注入字段 (客户端不可自报):
- `source`: 指令来源 (WASM/MCP_Deploy/...)
- `player_id`: 服务端注入，客户端提供的被覆盖
- `cert_fingerprint`: 部署时使用的证书指纹
- `module_hash`: Blake3(WASM bytes)
- `session_id`, `tick_submitted`, `tick_target`

### 认证模型

OAuth2 (GitHub/Google) → 服务端验证身份 → 签发 Ed25519 短期证书 (24h 默认) → 部署附带证书签名 → 服务端验签。证书过期/手动吊销 = 凭据泄露可止损。

### Tutorial 隔离

Tutorial 来源指令**仅可在 `world.mode = "tutorial"` 世界中接受**。非 Tutorial 世界收到 Tutorial 指令 → 静默丢弃 + 审计日志。Tutorial 全局存储使用独立 namespace (`tutorial_{world_id}`)，不与正式世界互通。

---

## 交叉关注: Fuel Refund 安全模型

来源: P0-2 §7

- **退还时序**: tick N 拒绝 → credit 记入 `next_tick_fuel_credit` → tick N+1 预算增加 (上限 MAX_FUEL × 1.1)。禁止同 tick 内通过竞争失败刷计算预算。
- **Deploy-reset**: refund credit 与产生它的 WASM 模块绑定。若 player 重新部署不同模块，credit 作废 (防 v1 刷 refund → v2 消费的跨模块预算转移)。
- **滥用检测**: 退还率 > 80% 连续 3 tick → 下 tick fuel budget 降为 MAX_FUEL × 0.5。
- **同源重复失败**: 同一 (player, source, rejection_reason) 在同 tick 内仅首次退 50%，后续 0%。
