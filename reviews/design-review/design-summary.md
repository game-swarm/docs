# Swarm 设计摘要 — 多方向评审输入文档

> **源文档**: `/data/swarm/docs/design/DESIGN.md` (Phase 0 Architecture Freeze, 2026-06-14)
> **目标读者**: Designer（体验评审）、Architect（架构评审）、Security（安全评审）
> **语言**: 中文叙述 + 英文术语保留

---

## 1. 核心游戏循环与玩家体验 (Core Game Loop & Player Experience)

### 1.1 游戏本质

Swarm 是一个**编程竞技场** (programming arena) —— 玩家编写真实代码控制自主单位 (drone)，在持久共享世界中运行。胜负不由手速决定，而取决于**算法思维、系统设计、资源优化**。

### 1.2 两种玩家，一条路径

```
人类：Monaco 编辑器 → 编译 WASM → 上传 ─┐
                                       ├─→ WasmSandboxExecutor → 世界
AI：  MCP 看世界 → 生成 WASM → 部署 ───┘
```

世界只认 WASM。不论代码是谁写的。AI agent 通过 MCP (Model Context Protocol) 查看世界、生成代码、部署 WASM，**与人类走完全相同路径**。MCP 中不存在 `swarm_move`、`swarm_attack` 等直接游戏动作工具——AI 必须编写 WASM 代码来实现策略。

### 1.3 Tick 驱动的游戏循环

每 tick 目标 3 秒，三个阶段：

```
阶段一：收集 (COLLECT) — 并行, ~2.5s
  ├── 对每个活跃玩家: 加载 WASM → 序列化可见世界快照(JSON)
  ├── 在 sandbox worker 进程中实例化 WASM，fuel limit = CPU 配额
  ├── 调用 tick(snapshot) → 收集 Vec<Command>
  └── 过滤无效指令

阶段二：执行 (EXECUTE) — 串行, ~0.5s
  ├── 玩家顺序种子洗牌 (seed = hash(tick_number, world_seed))
  ├── Phase 2a: 逐条 inline 应用指令（对照当前世界状态校验）
  ├── Phase 2b: ECS Systems 统一运行 (.chain())
  │   ├── death_mark_system → spawn_system → combat_system → ...
  ├── FDB 原子提交（全或无）
  └── tick_counter 推进

阶段三：广播 (BROADCAST) — 即时
  ├── 增量更新 → Dragonfly 缓存 → NATS → Gateway → WebSocket 客户端
  └── 每隔 N tick 记录完整世界快照到 FDB（回放用）
```

### 1.4 Deferred Command Model

WASM 模块通过 **延迟指令模型** 与引擎交互：

```
tick(snapshot_json) → Command[]
```

- 引擎将世界快照 JSON 写入 WASM 线性内存
- 调用 `tick(ptr, len)`，WASM 模块返回指令 JSON 列表
- 引擎校验所有指令（P0-2 Command Validation Pipeline）→ 应用到世界
- WASM 内**仅可调用查询类 host function**（只读：`get_terrain`, `get_objects_in_range`, `path_find`, `get_world_config`）
- **禁止**直接 mutating host function（无 `host_move`, `host_attack` 等）

### 1.5 核心设计原则

1. **语言无关**：一切编译为 WASM
2. **确定性核心**：相同初始状态 + 相同指令 → 相同世界状态（支撑回放、调试、反作弊）
3. **公平资源核算**：CPU 配额度量为 WASM 指令数（fuel metering），非墙钟
4. **可组合架构**：ECS 允许新增机制时无需触碰既有代码
5. **开源首日**：MIT 许可证

---

## 2. Drone 生命周期与身体规划系统 (Drone Lifecycle & Body Planning)

### 2.1 Drone 实体核心属性

```rust
struct Drone {
    owner: PlayerId,
    body: Vec<BodyPart>,       // MOVE, WORK, CARRY, ATTACK 等 — 不可逆
    fatigue: u32,              // 疲劳值，0 才能行动
    hits: u32, hits_max: u32,
    spawning: bool,
    age: u32,                  // 创建后经过的 tick 数。达到 lifespan 后死亡
}
```

### 2.2 生命周期关键规则

| 规则 | 默认值 | 说明 |
|------|--------|------|
| `drone_lifespan` | 1500 tick | drone 最大存活 tick 数 |
| **续期机制** | 每 Controller 每 tick 回退 age 0.5 tick | 多 Controller 可叠加，上限为完全抵消自然 age 增长。不再依赖一次性占领事件 |
| **冷却** | 无 | 改为持续维持模型，消除"占领-放弃-再占领"的 farming 策略 |

### 2.3 Body Planning 系统

- **Body 不可逆**：一旦 spawn，body part 组成不可更改
- **回收机制**：通过 `Recycle` 回收 drone 获得 50% 资源退还，重新 spawn 更优 body
- **新手保护**：Tutorial 世界前 500 tick 回收退还 100%

**默认 8 种基础 Body Part**：

| Body Part | 作用 | 被动效果 | 成本 (Energy) |
|-----------|------|----------|---------------|
| Move | 移动（消除 fatigue） | — | 50 |
| Work | 采集/建造/维修 | — | 100 |
| Carry | 运输资源 | 容量 = parts × 50 | 50 |
| Attack | 近战攻击（距离 1，伤害 30/part） | — | 80 |
| RangedAttack | 远程攻击（距离 3，伤害 25/part） | — | 100 |
| Heal | 治疗（恢复 12 HP/part） | — | 250 |
| Claim | 占领敌方建筑/Controller | — | 600 |
| Tough | 韧性 | +100 hits_max/part | 10 |

### 2.4 Body Part → CommandAction 绑定

- 一个 CommandAction 可被多个 body part 触发（未来 `Attack` 可由 `Claw`/`Bite` 等多 part 触发）
- 新 body part 绑定到已有 CommandAction 时，只需定义不同的 damage_type/base_damage/cost
- 引入新 CommandAction（如 `Leech`）需在引擎中注册 + IDL 暴露给 SDK
- **模组扩展**：Rhai 可通过 API 注册新 body part

---

## 3. Controller RCL 升级体系 (Controller Room Control Level)

### 3.1 Controller 实体

```rust
struct Controller {
    owner: Option<PlayerId>,
    level: u8,                    // 1–8
    progress: u32, progress_total: u32,
    downgrade_timer: u32,         // 降级倒计时（无 owner 时递减）
    safe_mode: u32,               // 安全模式剩余 tick
    safe_mode_available: u32,
    safe_mode_cooldown: u32,
}
```

### 3.2 升级表 (RCL 1-8)

| Level | 累计 progress | 解锁建筑 | 最大房间 drone | 说明 |
|-------|-------------|---------|---------------|------|
| 1 | 0 | Spawn | 50 | 初始状态 |
| 2 | 200 | Extension(5), Road, Container | 100 | 开始储能 |
| 3 | 500 | Extension(10), Tower, Storage | 200 | 防御可用 |
| 4 | 1,500 | Extension(20), Link | 300 | 能源网络 |
| 5 | 5,000 | Extension(30), Terminal, Observer | 400 | 市场交易 |
| 6 | 15,000 | Extension(40), Extractor, Lab, Factory | 500 | 制造时代 |
| 7 | 50,000 | Extension(50), PowerSpawn | 500（硬上限） | 晚期产能 |
| 8 | 150,000 | Extension(60), Nuker | 500 | 终极武器 |

### 3.3 升级与降级

- **升级**：向 Controller 存入资源（Transfer 指令），每 tick 自动转换为 progress。progress >= progress_total 时升级
- **降级**：Controller 失去 owner 超过 `downgrade_timer`（默认 5000 tick），降一级，progress 重置为 0

---

## 4. 战斗系统 (Combat System)

### 4.1 伤害类型体系 (Damage Types)

6 种默认基础伤害类型，可扩展：

| 伤害类型 | 描述 | 默认抗性倍率 |
|---------|------|-------------|
| Kinetic | 动能冲击 | 1.0 |
| Thermal | 热能（火焰/激光/等离子） | 1.0 |
| EMP | 电磁脉冲 | 1.0 |
| Sonic | 声波 | 1.0 |
| Corrosive | 腐蚀（酸液/纳米） | 1.0 |
| Psionic | 心灵（精神攻击/AI劫持） | 1.0 |

### 4.2 抗性机制 (Resistance)

**两层叠加**：
- **组件抗性** (body part / structure 固定倍率) — 例：`Tough` 对 Kinetic ×0.5
- **属性抗性** (模组动态赋予) — 例：`Shielded = 0.7`

最终倍率 = 组件倍率 × 属性倍率

**免疫机制**：Rhai 模组可通过 `set_entity_flag(entity_id, "immune_Thermal", true)` 赋予免疫（倍率 = 0）

### 4.3 特殊攻击方式

| 攻击 | 触发 Body Part | 效果 | 冷却 | 抗性 |
|------|---------------|------|------|------|
| **Hack** | Claim | 夺取目标 drone：5 tick 控制锁后转为 Neutral | 200 tick | Psionic |
| **Drain** | Carry + Work | 从目标建筑窃取资源 | 50 tick | EMP |
| **Overload** | RangedAttack | 消耗目标 fuel budget 500k（下限 MAX_FUEL×0.2） | 200 tick | EMP |
| **Debilitate** | Work | 给目标附加易伤（指定伤害类型抗性×2，持续 50 tick） | 150 tick | Corrosive |
| **Disrupt** | Attack | 打断目标当前持续动作（不造成 HP 伤害） | 50 tick | Sonic |
| **Fortify** | Tough | 护盾+净化：所有抗性×0.5，清除所有负面状态（持续 100 tick） | 300 tick | 无（增益） |

**通用规则**：
- 特殊攻击与 HP 伤害互斥（同一 body part 同一 tick 只能执行一种）
- 命中判定取决于 body part 数量与目标防御的差值
- 持续型攻击（Drain/Hack）在 drone 移动或被 Disrupt 时中断
- 所有特殊攻击受 `damage_multiplier` 世界规则影响

### 4.4 Neutral 状态（Hack 夺取后）

- `owner = Neutral (0)` — 不归任何玩家
- 停止执行 WASM（idle 状态，不提交指令）
- 不消耗 lifespan、不消耗 fuel
- 5 tick 后自动恢复原 owner
- 恢复前免疫再次 Hack
- 可见性：对原 owner 保持可见（ally 级），对其他玩家为 enemy 级

### 4.5 自定义特殊攻击扩展

新的特殊攻击可通过 TOML 配置声明（`[[custom_actions]]` + 引用已有 `[[special_effects]]`），无需修改 Rust 代码。引擎内置 11 种 handler：`hack`, `drain`, `overload`, `debilitate`, `disrupt`, `fortify`, `leech`, `fabricate`, `heal_self`, `scramble_commands`, `convert_to_structure`。

---

## 5. 经济系统 (Economic System)

### 5.1 资源类型——完全动态可配置

核心引擎**不硬编码 Energy**。它只操作 `HashMap<ResourceName, Amount>`。资源名是配置决定的字符串。

```rust
struct Resource {
    amounts: IndexMap<String, u32>,  // 如 {"Energy": 500, "Matter": 200}
}
struct ResourceDef {
    name: String, display_name: String, category: ResourceCategory,
    starting_amount: u32, max_storage: u32,
    decay_rate: u32,       // 每 tick 衰减比例 × 精度因子（0 = 不衰减）
    tradeable: bool,
}
```

默认世界只有 `Energy` 一种资源。服主可定义任意组合（星际争霸风、帝国时代风、赛博朋克主题等）。

### 5.2 全局 vs 本地双层存储模型

```
全局存储 (Player Storage)          本地存储 (World Storage)
┌─────────────────────┐           ┌──────────────────────┐
│ 抽象经济力量          │           │ 物理存在于建筑中        │
│ 不依赖建筑            │  物流成本  │ 需要 Storage/Extension │
│ 可市场交易            │ ←──────→ │ drone 采集先到这里     │
│ 可支付部署费          │           │ 跨房间运输需要 Carry    │
│ 有容量上限（研究升级）  │           │ 可被敌方掠夺/摧毁      │
└─────────────────────┘           └──────────────────────┘
```

关键参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `global_storage_enabled` | true | 是否启用全局存储 |
| `global_storage_capacity` | 100000 | 全局存储上限 |
| `transfer_to_global_cost` | 1% | 本地→全局损耗 |
| `transfer_from_global_cost` | 5% | 全局→本地损耗 |
| `transfer_to_global_time` | 10 tick | 本地→全局转换时间（不可为0） |
| `transfer_from_global_time` | 5 tick | 全局→本地转换时间（不可为0） |

### 5.3 三种物流模式

- **模式 A (无物流)**: `global_storage_enabled=true`, `transfer_cost=0` — 即时全局可用，适合新手和 Arena
- **模式 B (轻物流 — 默认)**: drone采集→本地→付1%转全局→全局付部署费
- **模式 C (硬核物流)**: `global_storage_enabled=false` — 纯物理运输，类似 Factorio

### 5.4 累进存储税 (Progressive Storage Tax) —— 反垄断机制

| 存储量（占容量上限） | 税率（每 tick） |
|---|---|
| 0–30% | 0%（免税） |
| 30–60% | 0.01% |
| 60–85% | 0.05% |
| 85–100% | 0.20% |

- Arena 模式默认免税（竞技公平）
- 本地存储完全私有（敌方无法获知真实经济实力）
- 全局↔本地转换需物流运输时间（不可瞬移补给，可被敌方拦截）

---

## 6. 可见性与观战系统 (Visibility & Spectator System)

### 6.1 两层可见性

**Drone 感知**（进入 snapshot）：
| 规则 | 默认 | 说明 |
|------|------|------|
| `fog_of_war` | true | drone 只能"看到"感知范围内的实体 |

**玩家视野**（人类屏幕 / AI MCP 查看）：
| 规则 | 默认 | 说明 |
|------|------|------|
| `player_view` | `"drone"` | `"drone"`=只看自己 drone 所见；`"full"`=全地图；`"allied"`=同阵营聚合视野 |
| `public_spectate` | false (World) / true (Arena) | 是否允许未登录旁观 |
| `spectate_delay` | 0 | 旁观延迟（tick 数）。>0 防止观众信息泄露 |
| `replay_privacy` | `"private"` | 回放可见性：`private`/`allies`/`world`/`public` |

### 6.2 典型场景组合

| 场景 | fog_of_war | player_view | 效果 |
|------|-----------|-------------|------|
| 标准 World | true | drone | drone 感知有限，玩家只看自己 drone |
| 教学世界 | false | full | 全图可见 |
| 竞技观战 | true | drone | drone 公平受限，观众看延迟全图 (`spectate_delay=100`) |
| 合作 PvE | true | allied | 友方聚合视野 |

---

## 7. World vs Arena 双模式

| 维度 | World（持久世界） | Arena（比赛） |
|------|-----------------|-------------|
| **本质** | 有机世界，类似 Minecraft 服务器 | 竞技比赛，类似围棋对局 |
| **地图** | 随机生成，不同起点 | 对称初始条件 |
| **加入时机** | 随时，先来后到 | 同时开始，代码赛前锁定 |
| **公平性** | 不追求——天然不对称 | 核心追求——对称起点 |
| **运行方式** | 7×24 tick 循环 | 固定时长（例：5000 tick ≈ 4h） |
| **代码部署** | 随时更新 | 赛前锁定 |
| **排行榜** | 无意义 | 赛季排名、锦标赛 |
| **回放** | 隐私分级控制 | 赛后自动公开 |
| **旁观** | 默认关闭 | 默认公开 |
| **玩家** | 人类 + AI agent 共存 | 1v1 或团队对决 |
| `global_storage_tax` | 累进税率 | 免税 |
| `spawn_policy` | `RandomRoom` | `FixedSpawn`（对称） |

---

## 8. 模组系统 — Rhai 规则引擎 (Rhai Rule Engine)

### 8.1 三层信任模型

```
玩家代码:  WASM → 控制 drone     (不可信 → sandbox 进程隔离)
规则模组:  Rhai → 修改世界规则    (服主声明 → 引擎嵌入)
引擎核心:  Rust → 确定性模拟      (不可变)
```

### 8.2 为什么 Rhai 而非 WASM？

| | WASM（玩家） | Rhai（规则） |
|---|-------------|------------|
| 信任模型 | 不可信，需进程隔离 | 服主安装，可信 |
| 编译步骤 | 需外部工具链 | 引擎直接执行源码 |
| 确定性 | 依赖 wasmtime 版本 | 同引擎版本完全确定 |
| 性能 | JIT | AST 解释（规则场景足够） |

### 8.3 模组结构

```
empire-upkeep/
├── mod.toml          # 元数据 + 可配置参数声明（含 i18n）
├── init.rhai         # 加载时执行一次
├── tick_start.rhai   # 每 tick 开始时执行
└── tick_end.rhai     # 每 tick 结束时执行
```

### 8.4 Rhai 执行预算与安全边界

| 资源 | 限制 | 超限行为 |
|------|------|---------|
| AST 节点数 | 10,000/tick | 该模组本次 tick 跳过 |
| actions 调用次数 | 100/tick | 超出部分丢弃 |
| `state.players()` 迭代 | 3,000 项 | 超出的玩家跳过 |
| 墙钟时间 | 100ms/tick | **强制终止 + 全部 actions 回滚**（事务性隔离） |

- 连续 10 tick 超限 → 自动禁用
- 所有 actions 记录到 TickTrace，可回放、可审计
- Rhai 禁用浮点（确定性要求）
- Rhai 不可用：文件 IO、网络、时钟、随机数

### 8.5 Rhai 可见性

- 世界活跃规则对**所有玩家完全可见**（人类通过 Web UI，AI 通过 MCP `swarm_get_world_rules`）
- 所有配置项支持多语言描述（zh/en/ja，回退链 en → description 字段）
- WASM 代码可通过 `Game.world.rules()` 查询当前规则并据此调整策略

---

## 9. 设计张力与未解决问题 (Design Tensions & Open Issues)

以下为 DESIGN.md 中隐含或显式的设计张力点，供评审员重点关注。

### 9.1 确定性与性能的张力

- **D1**: Tick 执行阶段串行化（Phase 2a 逐条 inline + Phase 2b `.chain()`）是确定性的保证，但限制了并行度。f64 禁用、IndexMap 替代 HashMap、Rhai 浮点禁用——这些确定性约束持续增加摩擦成本。
- **D2**: 种子洗牌 `Blake3(tick_number || world_seed)` 保证了公平，但玩家无法通过任何手段影响排序。这是设计意图（"不是手速/运气"），但可能限制某些策略深度。

### 9.2 全局存储模型的复杂性

- **D3**: 三模式物流（A/B/C）增加了服务器配置负担和玩家学习曲线。大部分玩家可能只理解模式 A 或 B。模式 C 的"硬核物流"适合小众硬核社区。
- **D4**: 累进存储税是优雅的经济反垄断设计，但参数（30/60/85/100%）未经实际运行验证。税率过高可能惩罚中型玩家，过低则无法阻止大玩家垄断。
- **D5**: 全局→本地转换需要时间（默认 5 tick），"运输中"资源可被拦截。拦截机制的具体实现（谁、如何、什么条件）尚未详细定义。

### 9.3 战斗系统的深度风险

- **D6**: 6 种伤害类型 + 2 层抗性 + 6 种特殊攻击 + 11 种特殊效果 handler + 自定义扩展——系统极其灵活，但平衡难度呈指数增长。服主可能配置出不可玩的战斗环境。
- **D7**: Hack/Neutral 机制引入了"临时中立"状态——5 tick 内 drone 对原 owner 可见但不执行代码。这是创新，但可能引发复杂的状态管理 bug（如 Hack 期间 drone 被 kill/Recycle、Hack 中断恢复等边缘情况）。
- **D8**: Overload 攻击直接削减 target fuel budget 500k（默认 MAX_FUEL=10M 的 5%）——这是对 AI agent 的定向压制。需要验证下限保护（MAX_FUEL×0.2）在极端情况下是否充分。

### 9.4 MCP 安全边界

- **D9**: MCP 界面与人类 Web UI "完全同级"，但 MCP 提供 24 个工具。AI agent 通过 MCP 可以高频采样世界、快速迭代策略、自动化部署。虽然 AI 同样走 WASM 沙箱，但其**信息优势**（持续监控、批量分析）可能超越人类玩家。
- **D10**: AI agent 部署频率受 `code_update_cooldown` 约束（默认 5 tick），但 MCP 的查询工具（`swarm_get_snapshot`、`swarm_inspect_entity`）无频率限制声明。高频查询可能构成信息不对称。

### 9.5 模组系统的安全表面

- **D11**: Rhai 模组运行在引擎进程内（非 sandbox 隔离），拥有 `damage_entity`、`deduct_resource`、`set_entity_flag` 等破坏性 API。虽然执行有预算限制，但**恶意的服主配置**可能通过 Rhai 模组制造不公平的游戏环境。
- **D12**: 模组依赖/冲突声明（`dependencies`/`conflicts`）是声明式的——没有自动解析或版本约束引擎。组合爆炸风险：随着模组数量增长，交叉兼容性保证将变得困难。

### 9.6 回放与隐私

- **D13**: 全量回放 (`replay_privacy`) 需要完整世界状态 + 所有玩家 Command。Arena 赛后强制公开——这意味着参赛者的 WASM 策略（虽可反编译阅读但非源码）被完全暴露。可能抑制创新——玩家不愿在公开比赛中展示最优策略。
- **D14**: `spectate_delay` 参数防止观众信息泄露给参赛者，但延迟时长（默认 0）需要根据竞技级别校准。实时观战 (`0`) 存在信息泄露风险（多人共谋：一人观战，一人参赛）。

### 9.7 架构冻结的遗留

- **D15**: Phase 0 冻结确认了 24 个 MCP 工具、12 个 Command Source、Determinism Contract。但部分系统参数（如 `drone_lifespan=1500`、`MAX_FUEL=10M`、累进税率阈值）标注为"默认值"——这些游戏平衡参数可能在后续 Phase 被大幅调整，影响已冻结的架构假设。
- **D16**: Body part 不可逆 + 回收退 50% 是精妙设计，但"控制器续期"机制（每 Controller 每 tick 回退 age 0.5 tick）使多 Controller 玩家可获得永久 drone——可能打破 drone 生命周期的自然约束。

---

## 附录：评审方向建议

| 评审方向 | 重点关注维度 |
|---------|-------------|
| **Designer** | §1 核心循环体验、§2 生命周期/身体规划、§3 RCL 升级节奏、§4 战斗深度/平衡、§5 经济策略空间、§7 双模式差异化、§9 D4/D6/D7/D16 |
| **Architect** | §1.3 Tick 生命周期（ECS 调度/Phase 2a/2b）、§2 数据模型、§5 双层存储（FDB+Dragonfly 一致性）、§8 Rhai 引擎集成、§9 D1/D2/D11/D12/D15 |
| **Security** | §1.4 Deferred Command Model 审计面、§4 伤害+Hack 状态安全、§6 可见性边界、§8 Rhai 沙箱与预算、§9 D8/D9/D10/D11/D13/D14 |

---

*生成时间: 2026-06-15 | 源文档版本: DESIGN.md (2026-06-14, Phase 0 Architecture Freeze R14 终审通过)*
