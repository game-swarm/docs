# R10 Architect Review — 架构摘要

> 为 Architect Reviewer 准备。源文档: DESIGN.md, tech-choices.md, ROADMAP.md, P0-01/02/04/08/09。
> 生成日期: 2026-06-14

---

## 1. 项目定义

**Swarm** = 开源可编程 MMO RTS 引擎。Screeps 精神续作，现代技术栈从零重构。
核心理念: 玩家编写代码控制 drone，代码编译为 WASM 在沙箱中执行。人类和 AI agent 走完全相同路径——世界只认 WASM。

---

## 2. 核心架构决策 (按组件)

### 2.1 引擎: Rust + Bevy ECS

| 决策 | 细节 |
|------|------|
| 框架 | Bevy ECS，`.chain()` 强制串行 → 确定性 |
| 备选淘汰 | Legion (已归档), Flecs (FFI开销), Unity DOTS (闭源) |
| 关键约束 | 禁 f64（用 i64×精度因子定点数）；HashMap 用 IndexMap（迭代顺序确定） |
| 实体 | Drone, Structure, Resource, Source, Terrain, Controller |
| ECS 执行顺序 | build → harvest → regen → movement → combat → decay → death → spawn (.chain()) |

### 2.2 玩家沙箱: WASM + Wasmtime

| 决策 | 细节 |
|------|------|
| 运行时 | Wasmtime =30.0（锁定版本） |
| 关键特性 | fuel metering (10M 指令/tick), epoch interruption (2500ms 硬截止) |
| 生命周期 | 每 tick 新 fork → 执行 → kill，tick 间无状态保留 |
| 内存 | WASM 线性 64MB，进程总量 128MB (cgroup) |
| OS 隔离 | seccomp(bpf) 白名单 syscall, cgroup v2, 无网络 namespace |
| 备选淘汰 | Wasmer (fuel 不成熟), WasmEdge (无原生 fuel), V8 Isolate (无 fuel metering) |
| 模块校验 | 预检: 体积≤5MB, 必须有 tick 导出, 禁止 _start/__wasm_call_ctors, 仅允许白名单 import |

### 2.3 Deferred Command Model (核心合同)

```
tick(snapshot_json) → Command[]
```

- WASM 中仅有**只读查询** host function: `get_terrain`, `get_objects_in_range`, `path_find`, `get_world_config`, `get_world_rules`
- **禁止** mutating host function (move/harvest/build/attack 等)
- 所有状态变更通过 `tick() → JSON` 延迟模型提交
- 引擎统一校验 → 应用

### 2.4 模组脚本: Rhai

| 决策 | 细节 |
|------|------|
| 定位 | 服主信任层——修改世界规则，非玩家代码 |
| 三明治模型 | WASM (不可信→sandbox) / Rhai (服主信任→嵌入) / Rust (核心不可变) |
| 确定性 | AST 解释，同引擎版本完全确定；关闭浮点引擎 |
| 备选淘汰 | Lua (C依赖+JIT非确定), Python (GIL+重), WASM (太重) |
| 钩子 | `init.rhai` (加载一次), `tick_start.rhai`, `tick_end.rhai` |
| 预算 | AST 10k/tick, actions 100/tick, 墙钟 100ms; 连续 10tick 超限 → 自动禁用 |

### 2.5 数据层

| 组件 | 技术 | 角色 | 关键特性 |
|------|------|------|---------|
| 权威存储 | FoundationDB | 世界状态 | 严格可序列化, 每 tick 原子提交 |
| 热缓存 | Dragonfly | 读加速 | Redis 兼容, 多线程 ~1M QPS, 非权威 |
| 分析 | ClickHouse | 列式 OLAP | tick 级时序查询, 审计日志 |
| 实时推送 | NATS | pub/sub | 轻量单二进制, tick delta 广播 |

### 2.6 加密原语: Blake3 单原语策略

| 用途 | 算法 | 理由 |
|------|------|------|
| 哈希 | Blake3 | ~6 GB/s, Rust 一等公民 |
| PRNG | Blake3 XOF | `blake3::Hasher::update_with_seek(seed, offset)` 替代 ChaCha |
| 代码签名 | Blake3 MAC (keyed hash) | 与哈希/PRNG 同原语 |
| 证书签名 | Ed25519 | 仅此一处例外——标准非对称，纯 Rust `ed25519-dalek` |

### 2.7 认证: OAuth2 → Ed25519 短期证书

- 注册/登录: OAuth2 (GitHub/Google) → 服务端签发 Ed25519 证书 (24h)
- 部署: WASM + 证书签名 → 服务端验签, player_id 由服务端注入 (客户端不可自报)
- 吊销: 证书过期 / 手动吊销

---

## 3. Tick 协议 (P0-1)

```
每 tick (目标 3s):

阶段一 COLLECT (~2.5s)
  ├─ 并行: 对每个活跃玩家
  │   ├─ 构建可见性快照 (visibility_filter)
  │   ├─ Sandbox Worker 中执行 WASM tick(snapshot) → Command[]
  │   └─ 超时 2500ms → 空指令 (宽容失败)
  └─ 收集全部指令到队列

阶段二 EXECUTE (~0.5s, FDB 事务内)
  ├─ 种子洗牌: Blake3(tick_number || world_seed) → 确定随机玩家顺序
  ├─ 排序: (order_index, player_id, cmd_seq)
  ├─ 逐指令校验 + 应用 (先到先得)
  ├─ 运行 ECS systems (.chain())
  ├─ FDB 原子提交 (3 次重试, 失败→tick 放弃, fuel 退还)
  └─ Bevy World 内存快照 (FDB rollback 时显式 restore)

阶段三 BROADCAST (即时)
  ├─ 计算 delta (与上一 tick 实体差异)
  ├─ FDB 写入 TickTrace (/tick/{N}/state, commands, rejections, metrics)
  ├─ Dragonfly 缓存更新
  └─ NATS → Gateway → WebSocket 客户端

BROADCAST 失败不回滚已提交 tick——客户端通过 last_tick 检测 gap → 主动 fetch
```

---

## 4. 指令管线 (P0-2)

```
tick() JSON 输出
  → Tick 输出 Schema 校验 (数组, ≤100条, ≤256KB, 深度≤10)
  → 反序列化 (逐指令 schema 验证)
  → 预校验 (目标存在/归属/距离)
  → 应用 (FDB 事务内)
  → 记录 TickTrace
```

**所有入口走同一管线**: WASM tick 输出, MCP tool, REST API, admin CLI。无绕过。

**Refund 策略**: 竞争失败 (SourceEmpty/TileOccupied/TargetFull) 退 50% fuel, 自身无效不退。退还 credit 仅作用于下一 tick。跨模块部署 → refund 作废。

---

## 5. 指令来源模型 (P0-9)

12 种来源: `WASM`, `MCP_Deploy`, `MCP_Query`, `Admin`, `Replay`, `TestHarness`, `Tutorial`, `Deploy`, `Rollback`, `RuleMod`, `Simulate`, `DryRun`

**Source Gate** 在管线入口强制执行:
- `WASM` → 允许 gameplay 指令
- `MCP_Deploy` → 拒绝 gameplay 指令 (只能部署代码)
- `Tutorial` → 仅 tutorial 世界接受

Auth context 由服务端注入 (player_id, cert_fingerprint, session_id, module_hash)——客户端不可自报。

---

## 6. 世界规则引擎 (DESIGN §8)

### 可配置维度

| 类别 | 关键规则 |
|------|---------|
| 出生 | spawn_policy (RandomRoom/ManualSelect/FixedSpawn/Inherit), respawn_policy |
| 代码部署 | update_cost, update_cooldown, update_window, propagation_speed/source |
| Drone | env_vars, memory_size, lifespan (默认 1500 tick ≈ 75min), 续期: 占领新房→age重置 |
| 资源 | 动态资源类型 (任意种类), source_regeneration, build_cost, drone_decay |
| 物流 | global_storage (三层模式: 无物流/轻物流/硬核物流), transfer cost+time |
| 经济反制 | 累进存储税 (30%/60%/85% 阈值), 本地隐匿, 运输拦截 (PvP) |
| 战斗 | pvp_enabled, friendly_fire, damage_multiplier |
| 可见性 | fog_of_war (drone感知) + player_view (玩家视野) 两层模型 |
| 回放隐私 | private / allies / world / public |

### 伤害体系 (可扩展)

6 种默认伤害类型: Kinetic, Thermal, EMP, Sonic, Corrosive, Psionic
抗性两层叠加: 组件抗性 (body part/structure) × 属性抗性 (Rhai 赋予)
免疫: `actions.set_entity_flag(id, "immune_Thermal", true)`

### 特殊攻击

| 攻击 | Body Part | 效果 |
|------|-----------|------|
| Hack | Claim | 夺取 drone 控制权 (hp<30%阈值) |
| Drain | Carry+Work | 窃取资源 |
| Overload | RangedAttack | 消耗目标 fuel budget |
| Debilitate | Work | 附加易伤 (指定类型×2伤害) |
| Disrupt | Attack | 打断持续动作 |
| Fortify | Tough | 自身/友方护盾 (所有抗性×0.5) |

---

## 7. 确定性合同 (DESIGN §8.8)

| 保证 | 实现 |
|------|------|
| PRNG | Blake3 XOF, 确定种子+offset |
| 排序 | (shuffle_order, player_id, cmd_seq) |
| ECS 顺序 | `.chain()` 严格串行 |
| 数值 | 整数+定点数, 禁 f64/Rhai 浮点 |
| HashMap | IndexMap |
| 回放 | `execute_deterministic == recorded_state`, CI 随机采样验证 |
| 种子洗牌 | Blake3(tick_number \|\| world_seed) — 确定但不可预测 |

---

## 8. World vs Arena

| 维度 | World | Arena |
|------|-------|-------|
| 本质 | 有机持久世界 | 竞技比赛 |
| 起点 | 不对称 | 对称 |
| 代码 | 随时热重载 | 赛前锁定 |
| 时长 | 7×24 | 固定 (5000 tick ≈ 4h) |
| 回放 | private/allies/world/public | 赛后强制 public |
| 排行榜 | 无 (起点不同) | 有 (赛季/Elo) |

---

## 9. 仓库结构

```
swarm/
├── docs/          # 设计文档, P0 规范, 评审报告
├── engine/        # Rust 引擎 — Bevy ECS, Tick 调度, 世界模拟
├── sandbox/       # WASM 沙箱 — 编译服务, 模块管理, 安全审计
├── gateway/       # Go API 网关 — WebSocket, REST, gRPC, 认证
├── frontend/      # Web 客户端 — Monaco Editor, PixiJS 渲染
├── sdk-ts/        # TypeScript SDK
└── sdk-rust/      # Rust SDK
```

---

## 10. 路线图阶段

| Phase | 名称 | 时间 |
|-------|------|------|
| 0 | 架构冻结 | ✅ 2026-06-14 |
| 1 | 核心 MVP (单人垂直切片) | 4-6 周 |
| 2 | MCP + 多人 (AI/人类并行) | 6-8 周 |
| 3 | 持久化 + Rhai (数据落地+模组) | 6-8 周 |
| 4 | 教程 + 调试 (新手上手+回放) | 4-6 周 |
| 5 | Web 客户端 (完整产品体验) | 6-8 周 |
| 6 | 战斗 + Arena (游戏化收官) | 8-10 周 |
| 7 | 生产化 (公测标准) | 8-12 周 |

---

## 11. R9 关键发现 (供参考)

- **drone 生命周期**: 默认 1500 tick, 占领新房→age 重置 (鼓励扩张)
- **Controller 升级 (RCL)**: 8 级, 累计 progress, 存入资源升级, 失去 owner 5000 tick 后降级
- **资源模型**: 引擎不硬编码 Energy——操作 `HashMap<ResourceName, Amount>`, 资源类型由 world.toml 定义
- **全局存储反制**: 累进税 (30/60/85% 阈值) + 本地隐匿 + 运输时间 (不可瞬移)
- **伤害/抗性体系**: 像资源类型一样可配置, Rhai 可扩展
- **特殊攻击**: 6 种, 绑定 body part, 受 damage_multiplier 影响
- **可见性两层**: fog_of_war (drone 感知) vs player_view (人/AI 视野)
- **回放隐私 4 档**: private/allies/world/public
- **MCP 不做 gameplay action**: 不存在 swarm_move/attack 等工具, AI 必须写 WASM
- **Blake3 单原语**: 哈希+PRNG+代码签名统一, 消除 ChaCha 依赖
- **Phase 0 冻结**: 2026-06-14, 12 项 checklist 全部完成
