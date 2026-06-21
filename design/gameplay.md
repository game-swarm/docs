# 游戏机制

> 游戏机制域文件。从 design/README.md 拆分。Vanilla Ruleset、身体部件、伤害系统、特殊攻击、经济模型。详见 [World Rules](specs/core/07-world-rules.md)、[Resource Ledger](specs/core/08-resource-ledger.md)、[Feedback Loop](specs/gameplay/06-feedback-loop.md)、[API IDL](specs/gameplay/08-api-idl.md)。

## 1. 10 分钟 Golden Path

新玩家从零到完成第一个 PvE 挑战的标准路径：

```
登录 → 获取 SDK → 编译 → 部署 → 观察反馈 → 调试 → 首个 PvE 挑战
  │        │         │       │         │          │           │
  ▼        ▼         ▼       ▼         ▼          ▼           ▼
 T+0     T+30s    T+90s   T+2min    T+3min    T+5-7min    T+8-10min
```

| 步骤 | 耗时 | 操作 | 验证点 |
|---|---|---|---|
| 1. 登录 | < 30s | Web UI 登录 → 选择 Tutorial 世界 → 自动获得初始 Energy | 看到出生房间和初始 drone |
| 2. 获取 SDK | < 30s | CLI: `swarm sdk fetch tutorial` 或 Web UI 下载 SDK bundle | `swarm sdk build` 成功 |
| 3. 编译 | < 1min | 编辑 `main.ts`（harvester 模板）→ `swarm sdk build` | WASM 产出，无编译错误 |
| 4. 部署 | < 30s | `swarm deploy tutorial` → WASM 上传到 Tutorial 世界 | 返回 `DeployResult::Ok` |
| 5. 观察反馈 | 1-2min | Web UI 查看 drone 采集 Energy、建筑进度、资源增长 | Energy 曲线上升，drone 正常工作 |
| 6. 调试 | 2-3min | 若 drone idle → MCP: `swarm_trace_command(entity_id, tick)` 查原因 → 修改代码重部署 | 所有 drone 非 idle |
| 7. 首个 PvE 挑战 | 2-3min | 中立 NPC drone 出现在视野 → 编写攻击/规避逻辑 → 完成首次 PvE 击杀 | NPC 被击杀，获得 PvE drop |

> **设计目标**：从登录到完成首个 PvE 挑战 ≤ 10 分钟。Tutorial 世界默认：`fog_of_war = false`（全图可见）、`code_update_cost = 0`（免费部署）、`new_player_transfer_lock_ticks = 0`（无经济限制）。

## 2. World Rules Engine — 可配置的游戏规则

Swarm 不是「一个游戏」，而是「一个可配置的游戏引擎平台」。每个世界实例可以有不同的规则集。详见 [World Rules](specs/core/07-world-rules.md) 和 [Resource Ledger](specs/core/08-resource-ledger.md)。

### 2.1 核心理念

Screeps 的问题是**规则硬编码**——出生点逻辑、代码更新成本、drone 控制权限都是引擎的一部分，社区服主无法修改。Swarm 把这些做成**世界级配置**。

**所有游戏内容都是 world.toml 中默认启用的官方扩展**——身体部件类型、建筑类型、伤害类型、特殊攻击、资源类型，全部通过 `[[body_part_types]]` / `[[structure_types]]` / `[[damage_types]]` / `[[special_effects]]` / `[[custom_actions]]` / `[[resource_types]]` 定义。引擎核心只提供 validation + execution pipeline，不硬编码任何游戏内容。服主可禁用、修改、或从头定义自己的世界规则。

```
世界配置 (WorldConfig)          ECS Plugin (System 注入)
┌─────────────────────┐        ┌──────────────────────┐
│ spawn_policy         │        │ SpawnPolicySystem    │
│ code_update_cost     │   →    │ CodeUpdateCostSystem │
│ code_propagation     │        │ PropagationSystem    │
│ drone_env_vars       │        │ DroneEnvVarSystem    │
│ ...                  │        │ ...                  │
└─────────────────────┘        └──────────────────────┘
         │                              │
         └──────────┬───────────────────┘
                    ▼
            引擎启动时加载
```

### 2.2 规则分类

#### 出生与加入

| 规则 | 类型 | 说明 |
|------|------|------|
| `spawn_policy` | enum | `RandomRoom`（默认） \| `ManualSelect`（玩家选坐标，仅在首次加入/重生时） \| `FixedSpawn`（固定出生点） \| `Inherit`（从已有殖民地出生——需该房间存在玩家的 Controller 且 level ≥ 1） |
| `spawn_cooldown` | u32 | 新玩家加入后多少 tick 才能开始操作（默认 0；world.toml 示例使用 100） |
| `respawn_policy` | enum | 殖民地全灭后的处理：`NewRoom` \| `SameRoom` \| `Spectate` \| `Ban` |

#### 代码部署

| 规则 | 类型 | 说明 |
|------|------|------|
| `code_update_cost` | ResourceCost | 部署新 WASM 消耗的资源（默认 `{Energy: 0}` — 免费） |
| `code_update_cooldown` | u32 | 两次部署间的最小 tick 间隔（默认 5，World 模式最小 5，防止 re-deploy refund 滥用；world.toml 示例使用 100） |
| `code_update_window` | (u32, u32) | 部署窗口期：每 N tick 开放 M tick（默认无限制） |
| `code_propagation_speed` | u32 | 代码更新传播速度：0=全局即时，>0=每 tick 传播 N 格 |
| `code_propagation_source` | enum | 传播源：`Spawn`（从出生点传播）\| `Controller`（从控制器传播）\| `AnyDrone` |

**swarm_deploy 幂等性**：部署操作按 `module_hash` 去重——相同 `module_hash` 的重复部署仅首次收取 `code_update_cost` 并重置 `code_update_cooldown`；后续相同 hash 的重试请求返回 `DeployResult::AlreadyDeployed`，不扣费、不刷新 cooldown。此设计防止玩家因网络重试或 SDK 误操作被多重扣费。

#### Drone 控制

| 规则 | 类型 | 说明 |
|------|------|------|
| `env_vars` | bool | 是否允许给 drone 设置环境变量（`drone.set("role", "harvester")`） |
| `memory_size` | u32 | 每 drone 最大环境变量存储（bytes，默认 1024） |
| `memory_spawn_cost` | `{String: u32}` | 每 byte 内存的孵化成本 × 精度因子（默认 `{}` = 免费） |
| `memory_upkeep_cost` | `{String: u32}` | 每 byte 内存的每 tick 维护费 × 精度因子（默认 `{}` = 免费） |

**手动控制不开放**：manual_control 与「代码就是军队」的核心哲学冲突，不在设计范围内。唯一例外是 Tutorial 专用世界中的受限引导操作——但 Tutorial 世界独立运行，不与正式世界互通。

#### 资源与经济

| 规则 | 类型 | 说明 |
|------|------|------|
| `source_regeneration_rate` | `fixed<u32,4>` | 资源点再生速率倍率 × 10000（默认 10000 = 1.0） |
| `build_cost_multiplier` | `fixed<u32,4>` | 建筑成本倍率 × 10000（默认 10000 = 1.0） |
| `drone_decay_rate` | `fixed<u32,4>` | drone 衰减倍率 × 10000（默认 10000 = 1.0） |

#### Drone 生命周期

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `drone_lifespan` | u32 | 1500 | drone 基础存活 tick 数。实际 `age_max = max(MIN_LIFESPAN, BASE_AGE + sum(每个 body part 的 age_modifier))`。`MIN_LIFESPAN` 默认 100 tick（world.toml 可配置），防止 body part 配置出负数 lifespan。`age_modifier` 定义在 `[[body_part_types]]` 中（如 TOUGH +100 延寿、ATTACK -80 折寿）。达到 age_max 后自动死亡。`MIN_LIFESPAN` 权威值见 Resource Ledger §2 统一参数表。 |
| `idle_aging` | — | 100% | idle drone 按正常速率衰老 |
| `active_aging` | — | 110%（即 +10%） | 每 tick 执行命令的 drone 以 110% 速率衰老（正常速率的 1.1 倍），防止挂机囤兵 |

**Age 恢复**: drone 必须**移动到 Controller 或 Forward Depot 维修范围内**才能降低 age。Controller 维修距离随 RCL 增长（RCL1=1 格，RCL8=5 格），免费，每 tick 服务上限由 RCL 决定。Forward Depot 固定 range=1，消耗存储资源。相邻格只有 6 个——大量 drone 需要排队，形成物流拥挤决策。**Controller 续期硬上限：无论拥有多少个 Controller，每 tick 总 age 回退不超过自然增长（+1/tick）的 50%（即 `max(0, age + 1 - min(0.5, controller_count * 0.5))`）。此上限防止玩家通过堆叠多个 Controller 实现永久 drone，保留 lifespan 的核心约束意义。**Healer body part 只能恢复 HP，不能降低 age。

#### Drone 身体规划

**body 不可逆**: 一旦 spawn，body part 组成不可更改。但可通过 `Recycle` 回收 drone 获得 lifespan-proportional 比例退还（最高 50%，随剩余 lifespan 递减至 10%；权威公式见 Resource Ledger §2.5），重新 spawn 更优 body。

**新手保护**: Tutorial 世界前 `tutorial_recycle_refund_full_ticks` tick 回收退还 100%（新人可以试错）。标准世界回收退还 lifespan-proportional 10%–50%。

#### 自定义建筑类型（`[[structure_types]]`）

与资源类型一样，建筑类型可通过 world.toml 定义。默认世界提供以下 13 种基础类型：

```toml
# world.toml — 建筑类型定义（可扩展）

[[structure_types]]
name = "Spawn"
description = "出生点——生成 drone"
category = "core"
hits = 5000
rcl_required = 1
cost = { Energy = 300 }

[[structure_types]]
name = "Extension"
description = "扩展——存储能量，最多 60 个"
category = "storage"
hits = 1000
rcl_required = 2
max_per_room = 60
cost = { Energy = 200 }

[[structure_types]]
name = "Tower"
description = "防御塔——自动攻击射程内敌方"
category = "defense"
hits = 3000
rcl_required = 3
attack = { damage = 50, damage_type = "Kinetic", range = 5, cooldown = 10 }
cost = { Energy = 800 }

[[structure_types]]
name = "Storage"
description = "仓库——大容量本地资源存储"
category = "storage"
hits = 10000
rcl_required = 3
capacity = 1000000
cost = { Energy = 500 }

[[structure_types]]
name = "Link"
description = "链接——短距离能量传输"
category = "logistics"
hits = 1000
rcl_required = 4
cost = { Energy = 400 }

[[structure_types]]
name = "Extractor"
description = "萃取器——从资源点采集矿物"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 600 }

[[structure_types]]
name = "Lab"
description = "实验室——化学反应/资源合成"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 1000 }

[[structure_types]]
name = "Terminal"
description = "终端——跨世界身份同步与日志交换节点"
category = "logistics"
hits = 3000
rcl_required = 5
cost = { Energy = 1200 }

[[structure_types]]
name = "Observer"
description = "观察者——扩展视野范围"
category = "intel"
hits = 500
rcl_required = 5
sight_range = 10
cost = { Energy = 500 }

[[structure_types]]
name = "PowerSpawn"
description = "强化出生点——处理高等级 drone body"
category = "core"
hits = 5000
rcl_required = 7
cost = { Energy = 5000 }

[[structure_types]]
name = "Factory"
description = "工厂——批量生产商品"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 1500 }

[[structure_types]]
name = "Nuker"
description = "核弹发射井——终极武器"
category = "defense"
hits = 10000
rcl_required = 8
cost = { Energy = 100000 }

[[structure_types]]
name = "Depot"
description = "前线维护节点——消耗资源为附近 drone 降低 age，可被占领"
category = "logistics"
hits = 2500
rcl_required = 2
capacity = 50000
maintenance = { Energy = 10 }      # 每 tick 维持消耗（资源耗尽停止维修）
repair_capacity = 10               # 每 tick 可服务的最大 drone 数
repair_range = 1                   # 维修距离（固定 1 格）
repair_aging = 5                   # 每 drone 降低的 age 量
cost = { Energy = 5000 }
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符 |
| `description` | string | ✅ | 人类可读描述 |
| `category` | enum | ✅ | `core` / `storage` / `defense` / `production` / `logistics` / `intel` |
| `hits` | u32 | ✅ | 最大 HP |
| `rcl_required` | u8 | ✅ | 需要的最低 RCL 等级（1-8） |
| `max_per_room` | u32 | 否 | 每房间最大数量（无限制则省略） |
| `capacity` | u32 | 否 | 资源存储容量 |
| `attack` | map | 否 | 自动攻击配置 `{damage, damage_type, range, cooldown}` |
| `sight_range` | u32 | 否 | 提供的额外视野范围 |
| `cost` | `{String: u32}` | ✅ | 建造成本 |
| `maintenance` | `{String: u32}` | 否 | 每 tick 维持消耗。资源耗尽时建筑停止功能（如 Depot 停止维修） |
| `repair_capacity` | u32 | 否 | 每 tick 可服务的最大 drone 数（Depot 专用） |
| `repair_range` | u32 | 否 | 维修距离（Depot 固定 1 格，Controller 由 RCL 决定） |
| `repair_aging` | u32 | 否 | 每 drone 降低的 age 量（Depot 专用） |

建筑类型像资源一样可扩展——服主可添加自定义建筑（如 `ShieldGenerator`、`Teleporter`），模组可通过 Rhai 赋予特殊行为。

#### 后勤网络：Controller vs Depot

drone age 维护由两层设施构成：

| | Controller | Forward Depot |
|---|-----------|---------------|
| 功能 | 领土主权 + age 维修 | 前线 age 维修 |
| 领土 | ✅ 宣称主权 | ❌ 不宣称 |
| 建筑解锁 | ✅ RCL 决定 | ❌ 无 |
| 降 age | ✅ 免费（容量由 RCL 决定） | ✅ 消耗本地存储资源 |
| 存储 | ❌ 只接收升级进贡 | ✅ 独立本地仓库 |
| 可占领 | ✅ Claim | ✅ Claim 或摧毁重建 |
| 可摧毁 | ❌ 降级 | ✅ 破坏 + 掉落部分资源 |
| 建造限制 | 每房间 1 个 | 任意（但有维护成本） |
| 维持消耗 | 无 | `maintenance` 字段定义 |

**战术含义**：
- **推进前线**: 在敌方领地边缘建 Depot，远征 drone 不用跑回主基地
- **补给线**: Depot 需要 CARRY drone 持续运输资源来维持运转——物流是玩法，不是免费午餐
- **打击后勤**: 摧毁敌方 Depot → 前线 drone 全部断粮，被迫撤退或等死
- **夺取节点**: 攻占敌方 Depot 获取其中资源，并为自己前线服务

#### 自定义资源类型

世界可以定义任意种类和数量的资源。默认世界只有 `Energy` 一种资源——但服主可以定义 `Crystal + Gas`（星际争霸风格）、`Food + Wood + Stone + Gold`（帝国时代风格）、或 `CPU + Memory + Bandwidth`（赛博朋克主题）。

| 规则 | 类型 | 说明 |
|------|------|------|
| `resource_types` | `[ResourceDef]` | 世界中的资源类型列表，默认 `[{name: "Energy"}]` |

#### 资源存储模型：全局 vs 本地

玩家的资源分为两层：

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

**默认行为**：
- drone 采集资源 → 先进入**世界本地存储**（就近的 Storage/Extension/Spawn）
- 世界本地存储的资源可通过 Terminal 在市场交易（需物流可达）
- 玩家可将本地存储转为全局存储（消耗能量 + 时间 = 物流成本）
- 全局存储的资源在部署代码、支付维护费时自动扣除
- 全局存储不能直接用于本地建造——需先转回本地

**可配置参数**：

| 规则 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `global_storage_enabled` | bool | true | 是否启用全局存储。false = 纯本地物流 |
| `global_storage_capacity` | u32 | 1000000 | 全局存储上限（1,000,000 单位，world.toml 可调） |
| `transfer_to_global_cost` | ResourceCost | `{Energy: 0.01}` | 本地→全局每单位资源的转换成本（默认 1%） |
| `transfer_to_global_time` | u32 | 10 | 转换所需的 tick 数（不可为 0，防止瞬移补给） |
| `transfer_from_global_cost` | ResourceCost | `{Energy: 0.05}` | 全局→本地每单位资源的转换成本（默认 5%） |
| `transfer_from_global_time` | u32 | 5 | 全局→本地转换所需 tick 数（不可为 0） |

**三种物流模式**：

```
模式 A: 无物流 (global_storage_enabled=true, transfer_cost=0)
  drone采集 → 即时进入全局存储 → 任何地方可用
  最简单，适合新手和快节奏 Arena

模式 B: 轻物流 (默认)
  drone采集 → 本地存储 → 付1%转全局 → 全局付部署费
  全局→本地付5% → 本地建造
  有策略深度但不过度惩罚

模式 C: 硬核物流 (global_storage_enabled=false)
  所有资源物理存在，必须用 Carry drone 运输
  类似 Factorio——物流本身就是核心玩法
```

#### 全局存储反制机制（Anti-Dominant-Strategy）

为防止富有玩家通过囤积全局存储垄断经济、操纵市场价格、阻断新玩家供给，设计以下三项内置反制：

**1. 累进存储税（Progressive Storage Tax）**

玩家全局存储总量超过阈值后，超出部分按累进税率征收每 tick 维护费：

| 存储量（占容量上限） | 税率（basis points, ×10000） |
|---|---|
| 0–30% | 0 bp（免税） |
| 30–60% | 1 bp（每万单位 1 单位） |
| 60–85% | 5 bp |
| 85–100% | 20 bp |

> 税率由世界规则配置 `global_storage_tax_tiers` 控制。Arena 模式默认免税（竞技公平）。

**2. 本地存储隐匿性（Stealth Advantage）**

- **全局存储余额**：部分公开——`showcase/world_stats` 可显示排名区间，市场挂单暴露部分余额
- **本地存储**：完全私有——敌方无法获知你的建筑中存了多少资源，直到发起侦察或占领

这使得囤积本地存储成为战略优势：敌方不知道你的真实经济实力。

**3. 全局↔本地转换需物流运输（No Teleport）**

- `transfer_to_global_time`：本地→全局转换需 N tick（默认 10 tick）。资源在运输期间不可用。
- `transfer_from_global_time`：全局→本地转换需 N tick（默认 5 tick）。大型帝国需提前规划补给线。
- 转换期间资源处于"运输中"状态——可被敌方巡逻 drone 拦截（需 PvP 启用）。

> 运输时间使全局存储不能作为"战斗中的即时补给"——这是一种非平凡的策略权衡。

| 规则 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `global_storage_tax_tiers` | `[(u32, u32)]` | `[(30,0),(60,1),(85,5),(100,20)]` | 累进税率：(容量%, 税率 bp) |
| `transfer_to_global_time` | u32 | 10 | 本地→全局转换所需 tick 数（不可为 0） |
| `transfer_from_global_time` | u32 | 5 | 全局→本地转换所需 tick 数（不可为 0） |
| `global_storage_public` | bool | false | （计划中）全局存储是否完全公开 |

#### 经济治理合同 (Economic Governance Contract)

##### PoW 经济治理

注册/CSR PoW 难度可配置，默认 `difficulty_bits = 24`。目标预算：

| 指标 | 值 | 说明 |
|---|---|---|
| P50 注册耗时（Rust） | ~150ms | 常规客户端 |
| P95 注册耗时（WASM） | ~1.5s | AI agent 浏览器端 |
| 单核批量注册成本 | ~$0.0001/次（CPU time） | 不计电费 |
| 每 1000 账号攻击成本 | ~$0.10（最低） | 仅 CPU，不含 IP 限流 |

难度自适应调整输入：近期注册速率、失败率、IP 多样性。调整上限 `difficulty_bits_max = 32`（约 4s WASM），下限 `difficulty_bits_min = 20`（约 100ms WASM）。PoW challenge TTL 5min，一次性消费。

##### 存储默认值与安全下限

| 规则 | 默认值 | 最小安全下限 | 说明 |
|---|---|---|---|
| `global_storage_tax_tiers` | `[(30,0),(60,1),(85,5),(100,20)]` | 最高税率 ≥ 10 bp | 防止无限囤积 |
| `transfer_to_global_time` | 10 tick | 不可为 0 | 无即时补给 |
| `transfer_from_global_time` | 5 tick | 不可为 0 | 需物流规划 |
| `global_storage_capacity` | 1,000,000 单位/玩家 | 无硬上限（税制抑制） | 服主可调 |

##### Vanilla 经济分类账

每条经济规则按其在资源总量中的影响分类，并标注目标日增长率范围：

| 规则 | 分类 | 目标日均资源增长 | 说明 |
|---|---|---|---|
| Source 再生 | Faucet | +3,000 ~ + 10,000 / 玩家 / 天 | 主要资源注入点。服主可通过 `source_regeneration_rate` 倍率调节 |
| drone 采集 (Work harvest) | Transfer | 0（资源从 Source → 本地存储） | 纯转移，不创造也不销毁资源 |
| Spawn drone | Sink | -200 ~ -5,000 / drone（取决于 body 复杂度） | 一次性沉没成本 |
| 建筑建造 | Lockup | 0（资源锁定在建筑中） | 可回收 50%（摧毁时返还） |
| Controller 升级 (RCL 进贡) | Lockup | 0（资源锁定） | 不可回收——永久锁定在 Controller 中 |
| 帝国维护费 (empire-upkeep) | Sink | 超线性（见 Resource Ledger §Empire Upkeep + Balance Sheet） | 默认启用的 anti-snowball 机制；前 1 controller + 3 drone 在 free_upkeep_ticks 内免维护费 |
| 全局存储税 | Sink | 0 ~ 20 bp / tick（按存储利用率阶梯） | 防止无限囤积 |
| 资源衰减 (resource-decay) | Sink | 按 decay_rate × 存储量 / tick | 可选模组，默认禁用 |
| 代码部署费 | Sink | 0 ~ 500 Energy / 次 | 默认免费，服主可配置 |
| drone 回收 (Recycle) | Unlock | lifespan-proportional 10%–50% 原 spawn 成本 | 沉没成本部分回收（Resource Ledger §2.5） |
| 全局↔本地转换损耗 | Sink | 1% ~ 5% / 次 | 物流模式 B 默认损耗 |
| 市场交易 | RFC 占位 | — | 不在当前设计范围内 |

> **分类定义**：**Faucet** = 净注入资源（从世界引擎创建，不取自任何玩家）；**Sink** = 净销毁资源（从玩家账户扣除，不转移给任何玩家）；**Transfer** = 资源从 A 移到 B（总量不变）；**Lockup** = 暂时锁定（可回收）；**Unlock** = 释放锁定资源（如 drone 回收、建筑摧毁）。

##### 新玩家资源门 (New Player Resource Gate)

为防止刷号/小号经济滥用，新玩家在前 N tick 内受以下经济限制：

| 限制 | 参数 | 默认值 | 说明 |
|---|---|---|---|
| 禁止资源 transfer（player↔player） | `new_player_transfer_lock_ticks` | 500 tick | 新玩家在前 N tick 不得向其他玩家 transfer 资源 |
| PvE drop 绑定 | `new_player_pve_drop_bound` | true | 前 N tick PvE 掉落绑定到账号，不可交易/转移 |
| 同源账号组配额 | `same_origin_account_group_quota` | 5 | 同一 IP/device fingerprint 的账号组共享此配额，超限账号标记为受限（R30: deferred anti-abuse config） |

> 所有限制参数由服主在 `world.toml` 中配置。Tutorial 世界默认关闭所有限制（`new_player_transfer_lock_ticks = 0`）。

##### 实体膨胀归因

实体膨胀（drone/建筑过多导致 snapshot/path_find/visibility 成本上升）的成本不外部化——每个玩家的 snapshot 大小与其自身 drone 数量成正比（per-player 256KB cap 内），不随其他玩家膨胀而增长。全局 path_find 和 visibility 由引擎统一承担，不计入 per-player budget。若全局实体数 > 50,000 hard cap，新 Spawn 被拒（`WorldEntityCapReached`），而非让现有玩家承担膨胀惩罚。

##### 反雪球合同 (Anti-Snowball Contract)

World 模式不追求竞技公平——先入者、大帝国拥有资源优势是接受的设计。以下机制保护生态可持续性，不保证个体公平：

| 机制 | 效果 | 目标 |
|---|---|---|
| 累进存储税 | 大存储量 → 高税率 → 自然天花板 | 防止无限囤积垄断 |
| 维护费 (O(n²) rooms) | 大帝国维护成本非线性增长 | 收益递减，自然收敛 |
| Controller 老化 | age 增长 → 修缮成本上升 → 硬上限 50% | 防止永续扩张 |
| soft_launch 1500 tick | 新玩家独立保护期 | 给予初始发展窗口 |
| 安全区出生 | 密度优先 + 反包围 | 新玩家不被堵死 |
| SpawnGrace 1 tick | 新生 drone 无敌帧 | 防止出生即斩 |
| Room drone cap (50→500) | 单房间兵力上限 | 防止局部兵力碾压 |

所有反雪球参数由服主通过 `world.toml` 调参——vanilla 提供合理默认值，不内置硬性公平保证。Arena 模式独立——对称初始资源 + 免税 + 短时长，追求竞技公平。

##### 长期目标系统

以下系统形成非线性追求，不依赖单一扩张指标：

| 目标 | 机制 | 说明 |
|---|---|---|
| **殖民地年龄** | tick 累计，解锁 tier/建筑/科技 | 时间沉淀产生差异化价值 |
| **GCL (Global Control Level)** | 多房间 Controller 平均等级 | 鼓励横向扩张而非单房间堆叠 |
| **RCL (Room Control Level)** | 单房间 Controller 等级 (1-8) | 纵向深度，解锁高级建筑 |
| **Arena 段位** | 竞技排名 + 赛季 | PvP 成就独立于 World 资产 |
| **PvE 里程碑** | 世界事件、NPC 据点攻克 | 合作/单人挑战目标 |
| **Replay/观战** | 社区分享最佳策略 | 非资产型声誉 |

#### 资源定义

```toml
[[resource_types]]
name = "Crystal"              # 资源名（标识符）
display_name = "水晶矿"        # 显示名
category = "mineral"          # mineral | gas | organic | energy
starting_amount = 0           # 新玩家初始拥有量
max_storage = 100000          # 单玩家最大储量
decay_rate = 10               # 每 tick 衰减比例 × 10000（0 = 不衰减）
tradeable = true              # 是否可在市场交易
```

定义了资源类型后，可以给不同的动作指定不同的资源消耗：

```toml
[actions.costs]

# Spawn drone 消耗：水晶 + 高能瓦斯
spawn = { Crystal = 200, Gas = 50 }

# 建造建筑
build.Extension = { Crystal = 50 }
build.Tower = { Crystal = 100, Gas = 25 }

# 生成 body part
body_part.Move = { Crystal = 50 }
body_part.Work = { Crystal = 100 }
body_part.Attack = { Crystal = 80, Gas = 20 }
body_part.Heal = { Crystal = 250, Gas = 100 }
body_part.Claim = { Crystal = 600 }

# 代码部署
code_update = { Crystal = 500 }

# 维修
repair_per_hit = { Crystal = 1 }
```

资源点可以产出多种资源：

```toml
[[source_types]]
name = "CrystalField"
produces = { Crystal = 1 }     # 每 tick 产出
capacity = 3000
regeneration = 300             # 每 tick 再生量

[[source_types]]
name = "GasVent"
produces = { Gas = 1 }
capacity = 2000
regeneration = 10
```

### Official Vanilla Swarm Ruleset（官方默认规则集）

Swarm 是一个**可配置的游戏引擎平台**——每个世界实例（world instance）可以通过 `world.toml` 自定义资源体系、身体部件、建筑类型、伤害类型、特殊攻击等几乎所有游戏内容。然而，为了让新手**无需任何配置即可开始游戏**，Swarm 官方提供一套**强默认规则集（Vanilla Ruleset）**，所有可配置项在此规则集中均有固定默认值。

本节汇总 Vanilla Ruleset 的核心默认值，作为所有官方世界（包括 Tutorial、World 模式默认世界、Arena 模式默认世界）的基线。

#### 核心默认值一览

| 类别 | 默认值 | 说明 |
|------|--------|------|
| **资源** | 单一 `Energy` | 所有操作消耗 Energy，简化经济模型。世界可通过 `[[resource_types]]` 扩展 |
| **身体部件** | 8 种标准件：`MOVE`, `CARRY`, `WORK`, `ATTACK`, `RANGED_ATTACK`, `HEAL`, `CLAIM`, `TOUGH` | 每种部件的 cost/age_modifier/能力 见 `[[body_part_types]]` 默认定义 |
| **伤害类型** | 6 种：`Kinetic`, `Thermal`, `EMP`, `Sonic`, `Corrosive`, `Psionic` | 默认抗性均为 1.0，详见 §8 伤害与武器类型定义 |
| **物流模式** | **模式 B（轻物流）** | 全局传输 1% 损耗，本地建造 5% 损耗。模式 A（无损耗）和模式 C（重物流）为可选项 |
| **特殊攻击** | 包含 8 种核心目标设计：`Hack`, `Drain`, `Overload`, `Debilitate`, `Disrupt`, `Fortify`, `Leech`, `Fabricate`。全部 8 种为 Standard+ 核心能力——不存在 Tier 2/Phase/Future 语义。Tutorial/Novice 默认禁用，Standard/Arena 全量启用。服主可通过 `world.toml` 的 `vanilla.special_attacks_enabled` 列表覆盖 | 冷却时间与资源消耗见 §8 特殊攻击方式表格 |
| **Controller 维修** | 硬上限：每 tick 总 age 回退 ≤ 自然增长的 50% | 详见 §3.1 Controller 结构定义 |
| **可见性** | `fog_of_war = true`，`player_view = drone`，`public_spectate = false` | 玩家仅可见自己 drone 视野内的内容；公开观战默认关闭 |
| **核心数值** | Work harvest: 1 unit/tick；Spawn cooldown: 5 tick；Tower attack: 50 dmg/10 tick cooldown/range 5；Source capacity: 3000/tick regen 300 | 编码前必需的最小默认值，确保 MVP feedback loop 可平衡 |
| **展示/世界统计** | World 模式无公开排行榜，仅提供非竞争统计（`swarm_get_world_stats`）；Arena 模式通过 `swarm_get_world_stats` 提供段位统计 | 持久世界天然不公平（老玩家先发优势），竞技场模式为有限时间窗口的公平竞争 |
| **新玩家保护** | 首次 spawn 后 **500 tick safe_mode** | 房间内无敌，不可被攻击/Claim/Hack，详见 §3.1a 新手房间分配策略 |
| **新手过渡期 (soft_launch)** | safe_mode 结束后 1500 tick `soft_launch_duration` | 仅 PvE 威胁（中立 NPC、资源潮、公共事件）。PvP 不可用。结束后 50 tick 前广播警告 |

#### soft_launch 后 PvP 渐进过渡 (D6/B)

> **D6/B 裁决**：soft_launch 结束后不是 PvP 的硬开关，而是分阶段渐进过渡，防止玩家在保护期结束瞬间被老玩家清场。

##### 过渡阶段定义

```
soft_launch 结束 (tick T):
  │
  ├─ Phase 1: First-Attack Insurance (T ~ T+200 tick, "缓冲期")
  │   ├─ PvP 启用但受限：
  │   │   ├─ 攻击者首次攻击某玩家时，目标获得 50 tick 无敌盾（First-Attack Shield）
  │   │   ├─ 无敌盾期间：所有来自该攻击者的 damage × 0，特殊攻击免疫
  │   │   ├─ 无敌盾结束后 100 tick 冷却方可再次触发（防止盾牌循环）
  │   │   └─ 玩家的被动行为（采集/建造/移动）不受限制
  │   ├─ 被攻击者可见攻击来源（`attack_exposure = true`）
  │   └─ 全局公告：`"Player <X> has initiated PvP combat — first-attack shield active for target"`
  │
  ├─ Phase 2: Soft PvP (T+200 ~ T+500 tick, "适应期")
  │   ├─ First-Attack Shield 降级为 25 tick（半盾）
  │   ├─ 伤害倍率：`damage_multiplier = 5000 bp`（50% 伤害）
  │   └─ 玩家可主动声明 `pvp_ready`（通过 Controller 操作）提前进入全 PvP
  │
  └─ Phase 3: Full PvP (T+500 tick 后)
      ├─ 标准 PvP 规则全部生效
      └─ `pvp_enabled = true`，无额外保护
```

##### First-Attack Shield 详细规则

| 属性 | 值 | 说明 |
|------|-----|------|
| shield_duration | 50 tick（Phase 1）/ 25 tick（Phase 2） | 被首次攻击触发 |
| shield_cooldown | 100 tick | 同一攻击者-目标对的盾牌冷却 |
| shield_scope | per-attacker | 仅免疫触发盾牌的攻击者；其他攻击者正常造成伤害 |
| damage_reduction | 100%（Phase 1）/ 50%（Phase 2）+ 伤害倍率 50% | 完全免伤 / 部分免伤 |
| special_attack_immune | true（Phase 1）/ false（Phase 2） | Phase 1 免疫 Hack/Drain/Disrupt 等 |
| attacker_visible | true | 被攻击者获得攻击者 entity_id + 位置（即使超出正常视野） |

##### 过渡阶段配置参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `soft_launch_duration` | 1500 tick | safe_mode 结束后的 PvE-only 期 |
| `soft_launch_warning_ticks` | 50 tick | 提前警告时间 |
| `first_attack_shield_phase1_duration` | 200 tick | Phase 1 全盾持续时间 |
| `first_attack_shield_phase2_duration` | 300 tick | Phase 2 半盾持续时间 |
| `first_attack_shield_duration` | 50 tick | 单次盾牌持续时间（Phase 1） |
| `first_attack_shield_cooldown` | 100 tick | 盾牌冷却 |
| `phase2_damage_multiplier` | 5000 bp | Phase 2 伤害倍率 (50%) |

所有参数由服主在 `world.toml` 的 `[soft_launch]` 段中配置。Tutorial 世界默认 Phase 1/2 持续时间 = 0（直接进入全 PvP，因为 Tutorial 无 PvP）。

#### Rhai 规则模组合同

Rhai 模组必须遵守以下确定性合同，违反合同的模组在 CI 校验阶段被拒绝：

**Deterministic action log model**：模组通过 `state` 获取只读 snapshot → 产出 `action log`（`actions.deduct_resource` 等的序列化记录）→ 引擎在模组执行完毕后 validate logs（校验 player_id 合法性、resource 存在性、amount 非溢出）→ 所有模组的 action logs 经 deterministic merge（按模组声明顺序合并，同 target 的先后 action 保留顺序）→ apply once（在 death_cleanup 之后一次性写入 ECS）。模组不得直接修改 World 状态——所有变更必须通过 actions 接口进入 action log 管线。

**Mod order 确定性**：模组执行顺序 = dependency topo sort + stable name tie-break（当多个模组无依赖关系时按 `mod.toml` 的 `name` 字段字典序）。依赖解析在引擎启动时完成，`mods.lock` 中记录的版本视为已解析的固定图。引入了新模组或变更版本时需重新计算 topo 顺序。

**State iterator order fixed**：`state.players()`、`player.drones()`、`player.rooms()` 的迭代顺序固定——`players()` 按 `player_id` 字典序；`drones()` 按 `(room_id, entity_id)` 元组序；`rooms()` 按 `room_id` 字典序。使用 `indexmap` 确保跨平台一致。

**Rollback 范围**：单模组超限时的 rollback 包含该模组本 tick 的完整 action log + 已 emit 的 events + 已记录的 metrics + `deduct_resource` 等资源扣除。回滚引擎确保原子性——该模组所有 actions 全部撤销或全部保留，无中间态。

**RuleMod global view vs PlayerVisibleScript filtering**：Rhai 模组以 **global view** 运行——`state` 包含该世界所有实体的完整状态，不受 player fog-of-war 限制。但**经济/维护类模组（empire-upkeep、resource-decay、storage-tax 等）不受 PlayerVisibleScript 过滤影响**——即使用户的 WASM 代码使用 `PlayerVisibleScript` 仅看见局部地图，这些模组仍能正确扣除全局资源。PlayerVisibleScript 仅作用于 WASM 的 `tick()` snapshot，不影响 Rhai 模组的 state 视图。

**mods.lock 完整性强制**：`mods.lock` 必须包含不可变 commit hash（`rev` 字段）+ content hash（`checksum` 字段，sha256）。引擎启动时校验：若 content hash 与实际文件内容不匹配 → **拒绝加载该模组并终止世界启动**（不是 warn），返回 `ModIntegrityError`。`checksum` 字段为必需——无 checksum 的 `mods.lock` 条目视为配置错误，等同于 hash 不匹配。

#### SDK 生成与分发

不同世界加载不同模组 → 不同的 API 面 → 不同的 SDK。玩家必须获取与目标世界匹配的 SDK 才能编写正确的代码。

**SDK 生成流程**：

```
引擎启动
    │
    ├─ 解析 world.toml + 加载 mods/
    ├─ 计算 mod_manifest_hash = Blake3(world.toml || mods.lock || engine_abi_version)
    │
    ├─ 生成 SDK artifacts:
    │   ├─ sdk-rust:  Rust crate (types + host function stubs)
    │   ├─ sdk-ts:    npm package (types + autocomplete)
    │   └─ sdk.json:  machine-readable manifest (供 MCP/CLI 查询)
    │
    ├─ 暴露下载端点:
    │   ├─ MCP:  swarm_sdk_fetch(world_id)
    │   ├─ CLI:  swarm sdk fetch <world_id>
    │   └─ Web:  世界详情页 SDK 下载链接
    │
    └─ 缓存: 按 (mod_manifest_hash, sdk_target) 缓存，相同 hash 复用
```

**WASM 模块声明**：

每个 WASM 模块在编译时嵌入目标世界标识：

```toml
# Cargo.toml (Rust) / package.json (TS)
[package.metadata.swarm]
target_manifest_hash = "abc123..."   # 编译时从 swarm sdk fetch 获取
engine_abi_version = 1
```

**部署验证**：

```
玩家部署 WASM
    │
    ▼
引擎校验:
  module.target_manifest_hash == world.current_manifest_hash ?
    ├─ 是 → 接受部署
    └─ 否 → 拒绝，返回错误:
         "SDK mismatch: module built for hash X, world currently at hash Y.
          Run `swarm sdk fetch` to update."
```

**版本兼容性**：

| 变更 | manifest_hash 变化 | 已部署 WASM |
|------|-------------------|------------|
| world.toml 调参（cost/cooldown） | 不变 | ✅ 兼容 |
| 新增 mod（新 handler） | 变化 | ❌ 需重新编译 |
| 移除 mod | 变化 | ❌ 需重新编译 |
| engine ABI 升级 | 变化 | ❌ 需重新编译 |
| Vanilla world（无 mods） | 固定 hash `vanilla-v1` | ✅ 跨世界兼容 |

**离线开发支持**：

```
swarm sdk fetch world_v1          # 拉取 SDK
swarm sdk build --target world_v1 # 编译 WASM（离线）
swarm sdk publish world_v1        # 部署到目标世界（在线）
```

本地开发时 SDK 缓存到 `~/.swarm/sdks/{hash}/`，相同 hash 复用。

#### 模组世界标识

任何使用 Layer 3 扩展（自定义 body part / damage type / Command）的世界实例**标记为非官方世界**：
- 在世界列表中显示 `[MOD]` 标识
- **不参与官方排名**（World 模式无公开排行榜，仅非竞争统计；Arena 模式仅 Vanilla 世界计入 `showcase/world_stats`）
- 玩家加入时显示明确警告：「此世界使用非标准规则集，可能与官方 SDK 不兼容。请确认已安装对应的世界 SDK。」

#### 战斗与 PvP

| 规则 | 类型 | 说明 |
|------|------|------|
| `pvp_enabled` | bool | 是否允许 PvP（默认 true） |
| `friendly_fire` | bool | 是否允许攻击同阵营（默认 false） |
| `damage_multiplier` | `fixed<u32,4>` | 伤害倍率 × 10000（默认 10000 = 1.0） |

#### 伤害与武器类型

伤害类型和抗性体系是**世界规则的一部分**——像资源类型一样可由 world.toml 定义和模组扩展。默认世界提供以下基础类型：

```toml
# world.toml — 伤害类型定义（可扩展）
[[damage_types]]
name = "Kinetic"
description = "动能冲击——碰撞、钝击、爆炸"
default_resistance = 1.0

[[damage_types]]
name = "Thermal"
description = "热能——火焰、激光、等离子"
default_resistance = 1.0

[[damage_types]]
name = "EMP"
description = "电磁脉冲——电击、过载、电子干扰"
default_resistance = 1.0

[[damage_types]]
name = "Sonic"
description = "声波——振动、共振、超声波"
default_resistance = 1.0

[[damage_types]]
name = "Corrosive"
description = "腐蚀——酸液、纳米分解、生化"
default_resistance = 1.0

[[damage_types]]
name = "Psionic"
description = "心灵——精神攻击、认知干扰、AI 劫持"
default_resistance = 1.0

# 抗性：按 body part / structure / 属性叠加
# 抗性倍率相乘: final_multiplier = body_resistance × attribute_resistance
[resistances.Tough]
Kinetic = 0.5          # 肉盾：动能减半
Sonic = 0.5            # 减震

[resistances.Structure]
EMP = 2.0              # 建筑弱电磁
Corrosive = 1.5        # 建筑怕腐蚀

# 属性级抗性（Rhai 模组可为实体动态赋予）
# 例如: actions.set_attribute(entity_id, "Shielded", true)
#       → 所有伤害 × 0.7 (需在 world.toml 定义 attribute_multipliers)
```

**Body part 伤害绑定**（完整定义见 `[[body_part_types]]`）：

| Body Part | 默认伤害类型 | 基础伤害值 | 说明 |
|-----------|------------|----------|------|
| Attack | Kinetic | 30 | 近战（距离 1），低成本高伤害 |
| RangedAttack | Kinetic | 25 | 远程（距离 3），射程优势 |
| Tower（建筑自动攻击） | Kinetic | 50 | — |
| Heal | —（反向治疗） | 12 | 每 tick 可缩短一个负面状态 10 tick 持续时间 |

**抗性机制**: 分两层叠加——**组件抗性**（body part / structure 的固定倍率）+ **属性抗性**（由模组/规则动态赋予的倍率，如 `Shielded = 0.7`）。最终倍率 = 组件倍率 × 属性倍率。

**免疫机制**: Rhai 模组可通过 `actions.set_entity_flag(entity_id, "immune_Thermal", true)` 赋予免疫（倍率 = 0）。适用于 Boss 单位、世界事件、特殊建筑。

**模组扩展**: Rhai 模组可注册新伤害类型（`actions.add_damage_type("Fire", 1.0)`）、设置抗性（`actions.set_resistance("Tough", "Fire", 0.3)`）、赋予属性（`actions.set_attribute(entity_id, "Flaming", true)`）。

#### 特殊攻击方式

除了 HP 伤害，以下特殊攻击方式作为 Command 或 body part 能力存在：

| 攻击方式 | 触发 body part | 效果 | 冷却 | 资源消耗 | 抗性 |
|---------|--------------|------|------|---------|------|
| **Hack** | Claim | 夺取目标 drone：施加"控制锁"逐步建立控制——tick 1-2 目标减速 50%，tick 3-4 目标无法移动，tick 5 夺取成功（drone 转为 Neutral，停止执行 WASM，进入 idle）。5 tick 后自动恢复。idle 期间不消耗 lifespan。目标可通过 Disrupt 打断或 Fortify 净化控制锁 | 200 tick | 1000 Energy | 目标 `Psionic` 抗性 |
| **Drain** | Carry + Work | 从目标建筑/存储中窃取资源，每 tick 转移 `carry_capacity` 单位 | 50 tick | 200 Energy/tick | 目标 `EMP` 抗性 |
| **Overload** | RangedAttack | 消耗目标计算配额。目标 `fuel budget` 减少 500k（默认 MAX_FUEL=10M 的 5%）。**下限 MAX_FUEL × 0.2**。**必须满足 `is_visible_to(target, attacker)`——不可攻击不可见玩家。全局冷却：同一目标每 50 tick 最多被 Overload 一次（不限来源）。Overload 反馈通过 `OverloadPressure` 组件暴露（详见 §Overload 反馈透明度） | 200 tick（drone 冷却） | 300 Energy | 目标 `EMP` 抗性 |
| **Debilitate** | Work | 给目标附加易伤状态。指定伤害类型抗性 ×2，持续 50 tick | 150 tick | 200 Energy | 目标 `Corrosive` 抗性 |
| **Disrupt** | Attack | 打断目标当前动作（Drain/Hack 等持续动作立即终止）。不造成 HP 伤害 | 50 tick | 100 Energy | 目标 `Sonic` 抗性 |
| **Fortify** | Tough | 自身/友方获得护盾（所有抗性 ×0.5）。**同时清除目标所有负面状态**（Debilitate/Drain/Overload/Hack控制锁），持续 100 tick | 300 tick | 400 Energy | 无——增益+净化 |
| **Leech** | Attack | 吸血攻击。通过 `[[custom_actions]]` 注册 | — | — | — |
| **Fabricate** | Work | drone→建筑转化。通过 `[[custom_actions]]` 注册 | — | — | — |

**渐进解锁 (Progressive Unlock)**：特殊攻击依据世界难度层级渐进解锁——

| 世界层级 | 可用特殊攻击 | 说明 |
|---|---|---|
| Tutorial | 全部禁用 | 新手引导阶段不需要特殊攻击 |
| Novice | 全部禁用 | 低强度世界，专注基础经济/物流 |
| Standard | 全部 8 种可用（Hack, Drain, Overload, Debilitate, Disrupt, Fortify, Leech, Fabricate） | 标准体验 |
| Advanced | 全部 8 种 + 服主自定义 `[[custom_actions]]` | 完全开放的模组世界 |

> 服主可通过 `world.toml` 中的 `vanilla.special_attacks_enabled` 列表覆盖默认解锁策略（如 Standard 世界禁用 Leech 和 Fabricate）。

**通用规则**：
- 特殊攻击与 HP 伤害互斥——同一 body part 在同一 tick 只能执行一种
- 特殊攻击的"命中判定"取决于 body part 数量与目标防御的差值，非简单的命中/未命中
- 持续型攻击（Drain/Hack）在 drone 移动或被 Disrupt 时中断
- 所有特殊攻击受 `damage_multiplier` 世界规则影响（倍率作用于成功率/效果量）

**Neutral 状态**（Hack 夺取后）:
- `owner = Neutral (0)`——不归任何玩家所有
- 停止执行 WASM（进入 idle 状态，不提交指令）
- 不消耗 lifespan、不消耗 fuel
- 5 tick 后自动恢复原 owner（Hack 自然到期）
- 恢复前免疫再次 Hack
- 可见性：对原 owner 保持可见（ally 级），对其他玩家为 enemy 级

#### Overload 反馈透明度

Overload 的反馈通过 ECS 组件 `OverloadPressure` 暴露，不再使用静默结果模型。

##### OverloadPressure 组件

每个实体（drone/structure/controller）可挂载 `OverloadPressure`：

```
OverloadPressure {
    total: u32,                        // 当前累积压力值
    contributions: Vec<Contribution>,  // 每个攻击者的贡献
    tick_snapshot: u64,                // 上次更新的 tick
}

Contribution {
    source_entity_id: EntityId,
    amount: u32,
}
```

##### 累积规则

- 每 tick EXECUTE 阶段，所有指向同一 target 的 Overload action 合并写入 `OverloadPressure`
- 只保留最新一次 snapshot tick 的数据（覆盖式，不追加历史）
- target 实体销毁后组件自动清除

##### 可见性模型

| 角色 | 可见内容 | 约束 |
|---|---|---|
| 攻击者 | 自己的 contribution + 总压力 | 始终可见 |
| 被攻击者 | 总压力 + 每个可见 source 的 contribution | 仅限 `is_visible(source, target)` 返回 true 的来源 |
| 第三方 | 可见实体的 `OverloadPressure` | 受 visibility rules 约束 |

不可见的攻击者不在 contribution 列表中暴露，防止通过 Overload 反馈反向定位隐身单位。

##### 数据出口

| 出口 | 说明 |
|---|---|
| **TickSnapshot** | 每个 entity 的 `OverloadPressure` 进入 snapshot |
| **TickTrace / Replay** | 完整 OverloadPressure 包含在 TickTrace 中，可回溯 |
| **MCP `swarm_get_entity`** | entity status 包含 `overload_pressure` 字段 |
| **WebSocket 推送** | 可见性变更事件中附带 `overload_pressure` 增量 |

##### 设计决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 历史存储 | 只保留当前 tick | 历史由 TickTrace/replay 覆盖，不增加状态存储 |
| contribution 精度 | `u32`，不暴露小数 | 攻击公式内部使用 BasisPoints 定点（见 economy.idl.yaml §type_registry），对外只暴露整数 |
| 隐藏攻击者 | 不可见则不出现在 contribution 列表 | 防止反向定位 |
| 总压力是否区分来源 | 是，完整保留 contribution 列表 | 不区分来源则无法做反制决策 |

#### 身体部件类型定义（`[[body_part_types]]`）

与资源类型和伤害类型一样，身体部件可通过 world.toml 定义和模组扩展。默认世界提供以下 8 种基础类型：

```toml
# world.toml — 身体部件类型定义（可扩展）

[[body_part_types]]
name = "Move"
description = "移动——每 part 每 tick 可消除 1 fatigue"
action = "Move"
range = 1
cost = { Energy = 50 }

[[body_part_types]]
name = "Work"
description = "工作——采集资源、建造建筑、维修"
action = ["Harvest", "Build"]
range = 1
cost = { Energy = 100 }

[[body_part_types]]
name = "Carry"
description = "运输——携带资源，容量 = parts × 50"
action = ["Transfer", "Withdraw"]
passive = { carry_capacity_per_part = 50 }
cost = { Energy = 50 }

[[body_part_types]]
name = "Attack"
description = "近战攻击——距离 1，每 part 30 伤害"
action = "Attack"
damage_type = "Kinetic"
base_damage = 30
range = 1
age_modifier = -80
cost = { Energy = 80 }

[[body_part_types]]
name = "RangedAttack"
description = "远程攻击——距离 3，每 part 25 伤害"
action = "RangedAttack"
damage_type = "Kinetic"
base_damage = 25
range = 3
age_modifier = -50
cost = { Energy = 150 }

[[body_part_types]]
name = "Heal"
description = "治疗——每 part 恢复 12 HP"
action = "Heal"
base_heal = 12
range = 1
age_modifier = -30
cost = { Energy = 250 }

[[body_part_types]]
name = "Claim"
description = "占领——夺取敌方建筑/Controller"
action = "ClaimController"
range = 1
age_modifier = -50
cost = { Energy = 600 }

[[body_part_types]]
name = "Tough"
description = "韧性——被动 HP 加成，每 part +100 hits_max"
passive = { hits_per_part = 100 }
age_modifier = 100
cost = { Energy = 10 }
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符 |
| `description` | string | ✅ | 人类可读描述 |
| `action` | string \| string[] | 条件 | 绑定的 CommandAction。`passive` 类型可省略。数组表示支持多种 action |
| `passive` | map | 条件 | 被动效果配置（如 Tough 的 hits_per_part）。与 action 互斥 |
| `damage_type` | string | 条件 | 攻击类型的伤害类型，引用 `[[damage_types]]` 中的 name |
| `base_damage` | u32 | 条件 | 每 part 的基础伤害值。`damage_type` 存在时必需 |
| `base_heal` | u32 | 条件 | 每 part 的基础治疗量。action=Heal 时必需 |
| `range` | u32 | ✅ | 生效距离（被动类型填 0） |
| `cost` | `{String: u32}` | ✅ | 生成该 body part 的资源消耗，key 为资源名 |
| `age_modifier` | i32 | 否 | 对 drone age_max 的修改量（TOUGH +100 延寿、ATTACK -80 折寿）。默认 0 |

**Body part → CommandAction 绑定规则**：
- 一个 CommandAction 可被多个 body part 触发
- 新 body part 绑定到**已有 CommandAction** 时，只需定义不同的 damage_type/base_damage/cost——引擎自动复用该 action 的校验和应用逻辑
- 引入**新 CommandAction** 时（如 `Leech`），需在引擎中注册新的 `CommandAction` 变体 + 对应的 validate/apply handler + 在 IDL 中暴露给 SDK

**模组扩展**：Rhai 模组可通过以下 API 注册新 body part：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符 |
| `description` | string | ✅ | 人类可读描述 |
| `action` | string \| string[] | 条件 | 绑定的 CommandAction。`passive` 类型可省略。数组表示支持多种 action（如 Work→Harvest+Build） |
| `passive` | map | 条件 | 被动效果配置（如 Tough 的 hits_per_part、Carry 的 carry_capacity_per_part）。与 action 互斥 |
| `damage_type` | string | 条件 | 攻击类型的伤害类型，引用 `[[damage_types]]` 中的 name |
| `base_damage` | u32 | 条件 | 每 part 的基础伤害值。`damage_type` 存在时必需 |
| `base_heal` | u32 | 条件 | 每 part 的基础治疗量。action=Heal 时必需 |
| `range` | u32 | ✅ | 生效距离（被动类型填 0） |
| `cost` | `{String: u32}` | ✅ | 生成该 body part 的资源消耗，key 为资源名 |
| `age_modifier` | i32 | 否 | 对 drone age_max 的修改量（TOUGH +100 延寿、ATTACK -80 折寿）。不指定则默认为 0 |

**Body part → CommandAction 绑定规则**：

```
┌──────────────────┐      ┌─────────────────────┐
│ BodyPart.name     │ ──▶  │ CommandAction        │
│ + damage_type     │      │ + damage 计算         │
│ + base_damage     │      │ + 校验 (body part 存在) │
│ + range           │      │ + 消耗 (冷却/资源)     │
│ + cost            │      └─────────────────────┘
└──────────────────┘
```

- 一个 CommandAction 可被多个 body part 触发（如 `Move` 只能由 `Move` part 触发，但 `Attack` 在未来可由 `Claw`/`Bite` 等多个 part 触发）
- 新 body part 绑定到**已有 CommandAction** 时，只需定义不同的 damage_type/base_damage/cost ——引擎自动复用该 action 的校验和应用逻辑
- 引入**新 CommandAction** 时（如 `Leech`），需在引擎中注册新的 `CommandAction` 变体 + 对应的 validate/apply handler + 在 IDL 中暴露给 SDK

**模组扩展**：Rhai 模组可通过以下 API 注册新 body part：

```rust
// Rhai API（远期扩展——MVP阶段通过world.toml [[custom_actions]]声明式配置）
actions.add_body_part_type("Leech", #{
    action: "Leech",           // 新 CommandAction
    damage_type: "Corrosive",
    base_damage: 15,
    range: 1,
    cost: #{ Energy: 300 },
    special: "heal_self_50pct" // 特殊效果：伤害的 50% 治疗自身
});
```

#### 调试 Command 溯源 (Debug Command Provenance)

Move、Attack、Harvest 等每个 action 在 snapshot 和 replay 中保留完整溯源链：**command → state diff → code line**。引擎在每 tick 应用 command 后，将 `(command, entity_id, state_diff)` 三元组写入 `TickTrace`。前端和 MCP 调试工具可通过 `swarm_trace_command(entity_id, tick)` 查询该实体在指定 tick 的指令及其导致的全部状态变更，并关联到 WASM 源码行（需编译时嵌入 debug symbol section）。此溯源链对 AI agent 调试特别关键——agent 可通过 MCP 执行「为什么我的 drone 在 tick 542 没有采集？」并得到完整因果链。

#### 自定义 CommandAction（`[[custom_actions]]`）

当新 body part 需要的动作无法映射到已有 CommandAction 时，需注册新的 CommandAction 变体：

```toml
# world.toml — 自定义 CommandAction（需引擎编译时注册）

[[custom_actions]]
name = "Leech"
description = "吸血攻击——造成伤害并治疗自身 50%"
damage_type = "Corrosive"
base_damage = 15
range = 1
special_effect = "heal_self"
special_param = 0.5

[[custom_actions]]
name = "Scramble"
description = "扰乱——随机重排目标下一 tick 的指令执行顺序"
range = 3
special_effect = "scramble_commands"
cooldown = 100
cost = { Energy = 400 }

[[custom_actions]]
name = "Fabricate"
description = "转化——将敌方 drone 转化为己方建筑"
range = 1
special_effect = "convert_to_structure"
cooldown = 500
cost = { Energy = 2000, Matter = 500 }
```

**注册流程**：

```
1. world.toml 中声明 [[custom_actions]]
   → 引擎启动时解析，动态注册 CommandAction 变体
2. 每个 custom action 需提供对应的 validate/apply handler：
   - 已有 special_effect 的（如 heal_self, scramble_commands）引擎内置
   - 全新效果的需通过 Rhai 模组提供 handler
3. IDL 自动生成——新 CommandAction 自动暴露给 SDK 和 MCP
4. WASM 模块通过 tick() → Command[] 使用新 action（与内置 action 语法一致）
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符，生成 `CommandAction::{name}` 变体 |
| `description` | string | ✅ | 人类可读描述 |
| `damage_type` | string | 否 | 伤害类型，引用 `[[damage_types]]` |
| `base_damage` | u32 | 否 | 基础伤害值 |
| `range` | u32 | ✅ | 生效距离 |
| `special_effect` | string | 否 | 特殊效果标识符，引用 `[[special_effects]]` 中定义的 name。内置默认效果见下方 |
| `special_param` | float | 否 | 特殊效果的参数 |
| `cooldown` | u32 | 否 | 冷却时间（tick） |
| `cost` | `{String: u32}` | 否 | 每次使用的资源消耗（body part spawn 成本在 `[[body_part_types]]` 中独立定义） |

#### 特殊效果类型定义（`[[special_effects]]`）

与 body_part_types 和 damage_types 一样，特殊效果可通过 world.toml 定义和扩展。每个 `[[special_effects]]` 条目定义一个可由 `[[custom_actions]]` 引用的效果类型：

```toml
# world.toml — 特殊效果类型定义（可扩展）

[[special_effects]]
name = "hack"
description = "夺取目标 drone——施加控制锁逐步建立控制，5 tick 后目标转为 Neutral"
handler = "hack"               # 引擎内置 handler 名
target = "enemy_drone"         # enemy_drone | enemy_structure | self | ally | any
duration = 5                   # 持续 tick 数（0 = 即时）
resistance = "Psionic"          # 目标抗性检查（引用 [[damage_types]]）

[[special_effects]]
name = "drain"
description = "从目标建筑/存储中窃取资源，每 tick 转移 carry_capacity 单位"
handler = "drain"
target = "enemy_structure"
duration = 0                   # 持续型，手动中断
resistance = "EMP"

[[special_effects]]
name = "overload"
description = "消耗目标计算配额——fuel budget -500k，下限 MAX_FUEL×0.2"
handler = "overload"
target = "enemy_player"
duration = 0                   # 即时
resistance = "EMP"

[[special_effects]]
name = "debilitate"
description = "给目标附加易伤状态——指定伤害类型抗性×2"
handler = "debilitate"
target = "enemy_any"
duration = 50
resistance = "Corrosive"

[[special_effects]]
name = "disrupt"
description = "打断目标当前持续动作（Drain/Hack/Debilitate 等），不造成 HP 伤害"
handler = "disrupt"
target = "enemy_drone"
duration = 0                   # 即时
resistance = "Sonic"

[[special_effects]]
name = "fortify"
description = "自身/友方获得护盾（所有抗性×0.5）+ 清除所有负面状态"
handler = "fortify"
target = "self_or_ally"
duration = 100
# 无 resistance — 增益效果不检查抗性

[[special_effects]]
name = "leech"
description = "吸血——造成伤害的 50% 治疗自身"
handler = "leech"
target = "enemy_any"
duration = 0
resistance = "Corrosive"
# special_param = 0.5 → 治疗比例，在 [[custom_actions]] 中指定

[[special_effects]]
name = "fabricate"
description = "将敌方 drone 转化为己方建筑"
handler = "fabricate"
target = "enemy_drone"
duration = 0
resistance = "Psionic"

[[special_effects]]
name = "heal_self"
description = "造成伤害的指定比例治疗自身"
handler = "heal_self"
target = "enemy_any"
duration = 0

[[special_effects]]
name = "scramble_commands"
description = "随机重排目标下 tick 的指令执行顺序"
handler = "scramble_commands"
target = "enemy_drone"
duration = 0

[[special_effects]]
name = "convert_to_structure"
description = "将目标 drone 转化为己方建筑"
handler = "convert_to_structure"
target = "enemy_drone"
duration = 0
resistance = "Psionic"
```

**字段说明**：

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符，被 `[[custom_actions]].special_effect` 引用 |
| `description` | string | ✅ | 人类可读描述 |
| `handler` | string | ✅ | 引擎内置处理器名。内置：`hack`, `drain`, `overload`, `debilitate`, `disrupt`, `fortify`, `leech`, `fabricate`, `heal_self`, `scramble_commands`, `convert_to_structure` |
| `target` | enum | ✅ | 目标类型：`enemy_drone`, `enemy_structure`, `enemy_player`, `enemy_any`, `self`, `ally`, `self_or_ally`, `any` |
| `duration` | u32 | ✅ | 持续 tick 数（0 = 即时生效） |
| `resistance` | string | 否 | 目标抗性检查，引用 `[[damage_types]]` 中的 name。无此字段 = 不检查抗性 |

**注册流程**：

```
1. world.toml 中声明 [[special_effects]]
   → 引擎启动时解析，注册到 SpecialEffectRegistry
2. [[custom_actions]] 中通过 special_effect = "name" 引用
   → 引擎在 CommandAction 注册时自动绑定 handler
3. 引擎内置所有 handler（hack/drain/overload/…）— 无需 Rhai 即可使用
4. 服主只需在 world.toml 中声明 [[custom_actions]] + 引用已有 [[special_effects]]
   → 新特殊攻击只需 TOML 配置，无需改 Rust 代码
5. 如需全新 handler（TOML 配置无法表达的效果），通过 Rhai 模组注册
```

**默认 world.toml 中的特殊攻击注册**：

```toml
# 以下 8 个特殊攻击在默认 world.toml 中预注册
# 服主可禁用（注释/删除）或修改参数

[[custom_actions]]
name = "Hack"
description = "夺取 drone——5 tick 控制锁后转为 Neutral"
special_effect = "hack"
cooldown = 200
cost = { Energy = 1000 }

[[custom_actions]]
name = "Drain"
description = "从目标建筑窃取资源"
special_effect = "drain"
cooldown = 50
cost = { Energy = 200 }

[[custom_actions]]
name = "Overload"
description = "消耗目标 fuel budget 500k"
special_effect = "overload"
cooldown = 200
cost = { Energy = 300 }

[[custom_actions]]
name = "Debilitate"
description = "施加易伤——指定伤害类型抗性×2，持续 50 tick"
special_effect = "debilitate"
special_param = 2.0
cooldown = 150
cost = { Energy = 200 }

[[custom_actions]]
name = "Disrupt"
description = "打断目标持续动作"
special_effect = "disrupt"
cooldown = 50
cost = { Energy = 100 }

[[custom_actions]]
name = "Fortify"
description = "护盾+净化——所有抗性×0.5，清除负面状态"
special_effect = "fortify"
special_param = 0.5
cooldown = 300
cost = { Energy = 400 }

[[custom_actions]]
name = "Leech"
description = "吸血攻击——伤害 50% 治疗自身，Corrosive 15 dmg"
damage_type = "Corrosive"
base_damage = 15
range = 1
special_effect = "leech"
special_param = 0.5
cost = { Energy = 300 }

[[custom_actions]]
name = "Fabricate"
description = "将敌方 drone 转化为己方建筑"
range = 1
special_effect = "fabricate"
cooldown = 500
cost = { Energy = 2000, Matter = 500 }
```

#### 可见性与观战

可见性分两层：**drone 感知**（影响游戏公平性）和**玩家视野**（影响观战体验）。

##### Drone 感知（进入 snapshot）

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `fog_of_war` | bool | true | drone 的 WASM `tick()` snapshot 是否受可见性限制。true = drone 只能"看到"感知范围内的实体（视觉/听觉/嗅觉分层）；false = snapshot 包含全地图（合作/教学世界） |

##### 玩家视野（人类屏幕 / AI MCP 查看）

| 规则 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `player_view` | enum | `"drone"` | `"drone"` = 玩家只能看到自己 drone 所见；`"full"` = 玩家实时看到全地图（无论 drone 感知范围）；`"allied"` = 看到所有同阵营 drone 的聚合视野 |
| `public_spectate` | bool | false | 是否允许未登录用户实时旁观（只读 WebSocket）。World 默认关，Arena 默认开 |
| `spectate_delay` | u32 | 0 | 旁观延迟（tick 数）。0 = 实时；>0 = 延迟回放，防止观众信息泄露给参赛者 |
| `replay_privacy` | enum | `"private"` | 回放可见性：`"private"` = 仅自身；`"allies"` = 同阵营可看；`"world"` = 同世界玩家可看；`"public"` = 任何人（含未登录）。Arena 模式赛后强制 `"public"` |

| `replay_with_source` | bool | `false` | **默认 replay 不含源码**：回放只包含指令序列和状态变更，不包含 WASM 模块源码或 source map。玩家可通过 `replay_with_source = true` 主动公开（需在 world config 中开启此选项，服主可禁止）。`"public"` 世界服主可强制 `replay_with_source = true` 以实现完全透明。source map / code line provenance 需编译时嵌入 debug symbol section（opt-in） |

**组合示例**：

| 场景 | fog_of_war | player_view | 效果 |
|------|-----------|-------------|------|
| 标准 World | true | drone | drone 感知有限，玩家只看自己 drone 所见 |
| 教学世界 | false | full | 新手看到全地图，drone 也能感知全图 |
| 竞技观战 | true | drone | drone 公平受限，但观众通过 `public_spectate` + `spectate_delay=100` 看延迟全图 |
| 合作 PvE | true | allied | drone 各自感知，但玩家看到所有友方聚合视野 |

### 2.3 配置格式

```toml
# world.toml — 每个世界实例的配置文件

[world]
name = "World of Swarm"
mode = "persistent"              # persistent | arena

[spawn]
policy = "RandomRoom"
respawn = "NewRoom"
cooldown = 100                   # 示例值；默认值为 0

[code]
update_cost = { Energy = 500 }   # 部署消耗 500 能量
update_cooldown = 100            # 示例值；World 模式最小值为 5
update_window = { every = 1000, duration = 100 }  # 每 1000 tick 开放 100 tick 窗口
propagation_speed = 3            # 每 tick 传播 3 格
propagation_source = "Spawn"     # 从出生点向外传播

[drone]
env_vars = true                  # 允许环境变量
memory_size = 2048               # 每 drone 2KB 存储
lifespan = 1500                  # drone 存活 tick 数上限
memory_spawn_cost = { Energy = 0.5 }     # 每 byte 孵化成本
memory_upkeep_cost = { Energy = 100 }   # 每 byte 每 tick 维护费 (basis points, ×10000)

[visibility]
fog_of_war = true                # drone 感知受可见性限制
player_view = "drone"            # 玩家只看自己 drone 所见
public_spectate = false          # World 模式默认不公开旁观
spectate_delay = 0               # 回放无延迟

[resources]
source_regeneration_rate = 10000     # ×10000 精度，默认 1.0
build_cost_multiplier = 10000
drone_decay_rate = 10000

# 物流配置
global_storage_enabled = true
global_storage_capacity = 100000
transfer_to_global_cost = { Energy = 0.01 }    # 1% 损耗
transfer_from_global_cost = { Energy = 0.05 }   # 5% 损耗

# 自定义资源类型
[[resource_types]]
name = "Energy"
display_name = "能量"
category = "energy"
starting_amount = 1000
max_storage = 100000

[[resource_types]]
name = "Matter"
display_name = "物质"
category = "mineral"
starting_amount = 500
max_storage = 50000

# 各动作资源消耗
# 注意: body part spawn 成本在 [[body_part_types]].cost 中定义，此处不重复
[actions.costs]
spawn = { Energy = 200, Matter = 50 }
build.Extension = { Energy = 50 }
build.Tower = { Energy = 100, Matter = 25 }
code_update = { Energy = 500 }
repair_per_hit = { Energy = 1 }

# 资源点类型
[[source_types]]
name = "EnergyField"
produces = { Energy = 1 }
capacity = 3000
regeneration = 300

[[source_types]]
name = "MatterDeposit"
produces = { Matter = 1 }
capacity = 2000
regeneration = 10

[combat]
pvp_enabled = true
friendly_fire = false
damage_multiplier = 10000
```

### 2.4 ECS 集成方式

每个规则类别对应一个可选的 ECS System。引擎启动时读取 `world.toml`，有选择地注册 System：

```rust
// engine 启动时
fn register_rule_systems(app: &mut App, config: &WorldConfig) {
    // 基础系统始终注册
    // 主线（必须串行，有数据依赖）
    app.add_systems(Update, (
        death_mark_system,       // 标记待死亡 entity，释放 room cap
        spawn_system,            // 统一创建校验通过的 drone
        combat_system,           // 战斗结算（damage 先 → heal 后）
        death_cleanup_system,    // 实际 despawn
    ).chain());

    // 无依赖系统（与主线并行，仅需在 death_cleanup 前完成）
    app.add_systems(Update, (
        regeneration_system,     // 资源点再生
        decay_system,            // 疲劳/冷却递减
    ).after(death_mark_system).before(death_cleanup_system));

    // 注入资源注册表——所有 System 通过它查询资源类型和消耗
    let resource_registry = ResourceRegistry::from_config(&config);
    app.insert_resource(resource_registry);

    // 规则系统按配置注册
    if config.code.propagation_speed > 0 {
        app.add_systems(Update, code_propagation_system.before(spawn_system));
    }
    if config.drone.memory_upkeep_cost.len() > 0 {
        app.add_systems(Update, memory_upkeep_system.before(decay_system));
    }
    // ...
}

// ResourceRegistry 是运行时的资源类型字典
struct ResourceRegistry {
    types: IndexMap<String, ResourceDef>,  // IndexMap 保证迭代顺序确定
    action_costs: ActionCosts,       // spawn, build.*, body_part.*, ...
    source_types: Vec<SourceDef>,
}

impl ResourceRegistry {
    /// 查询某个动作的资源消耗
    fn cost(&self, action: &str, detail: Option<&str>) -> HashMap<String, u32> {
        // action = "build", detail = "Tower"
        // → { "Energy": 100, "Matter": 25 }
    }
}
```

关键是：**核心引擎不硬编码 Energy**。它只操作 `HashMap<ResourceName, Amount>`。资源名是配置决定的字符串。

```rust
// 之前（硬编码）
struct Resource { energy: u32 }

// 之后（动态）
struct Resource {
    amounts: IndexMap<String, u32>,  // IndexMap 保证迭代顺序确定
}
struct ResourceDef {
    name: String,
    display_name: String,
    category: ResourceCategory,
    starting_amount: u32,
    max_storage: u32,
    decay_rate: u32,  // 每 tick 衰减比例 × 精度因子（0 = 不衰减）
    tradeable: bool,
}
```

### 2.5 WASM 侧感知（Deferred 模型）

WASM 模块通过 `tick(snapshot_json) → commands_json` 延迟模型运作：
- 引擎将快照 JSON 写入 WASM 线性内存，调用 `tick()`
- WASM 模块通过**查询 host function**（get_terrain、get_objects_in_range、path_find、get_world_config）读取世界状态
- `tick()` 返回指令 JSON 列表，引擎在校验后统一应用

```typescript
// TypeScript SDK — tick() 接收 Snapshot，返回 Command[]
function tick(snapshot: WorldSnapshot): Command[] {
    // 查询世界配置（只读 host function）
    const registry = snapshot.resourceRegistry;

    // 查看世界中定义了哪些资源
    for (const [name, def] of registry.types) {
        console.log(`${name} (${def.display_name}): max ${def.maxStorage}`);
    }

    // 查询动作消耗
    const spawnCost = registry.cost("spawn");
    // → { Energy: 200, Matter: 50 }

    // 生成指令列表
    const commands: Command[] = [];

    // 检查资源 → 决定指令
    if (snapshot.player.resources.has(spawnCost)) {
        commands.push({ cmd: "spawn", body: [...] });
    }

    // 采集指令
    commands.push({ cmd: "harvest", target: sourceId, resource: "Matter" });

    // 传输指令
    commands.push({ cmd: "transfer", target: targetId, resources: { Energy: 100, Matter: 50 } });

    // 返回指令 JSON — 引擎统一校验后执行
    return commands;
}
```

> **设计合同**: WASM 模块通过 `tick() → JSON` 延迟模型运作。所有 mutating 操作以 JSON 指令形式返回，引擎统一校验和应用。不得通过 host function 直接修改世界状态。

### 2.6 World 与 Arena 的默认规则

| 规则 | World 默认值 | Arena 默认值 |
|------|------------|------------|
| `spawn_policy` | `RandomRoom` | `FixedSpawn`（对称） |
| `code_update_cost` | 0（免费） | 0 |
| `code_update_window` | 无限制 | 赛前锁定 |
| `code_propagation_speed` | 0（即时） | 0（即时） |
| `drone_env_vars` | true | true |
| `pvp_enabled` | true | true（必须） |

### 2.7 Rule Module System — 可安装的游戏模组

规则模组是**可安装的 Rhai 脚本 + 声明式配置**——轻量、确定、可组合。

```
玩家代码:  WASM → 控制 drone     (不可信 → sandbox)
规则模组:  Rhai → 修改世界规则    (服主声明 → 引擎嵌入)
引擎核心:  Rust → 确定性模拟      (不可变)
```

#### 为什么不是 WASM

| | WASM（玩家） | Rhai（规则） |
|------|-------------|------------|
| 信任模型 | 不可信，需要进程隔离 | 服主自行安装，可信 |
| 编译步骤 | 需要外部工具链 | 无，引擎直接执行源码 |
| 确定性 | 依赖 wasmtime 版本 | 同引擎版本完全确定 |
| 语言复杂度 | 取决于源语言 | 极简，类似 Rust/JS |
| 性能 | JIT | AST 解释（规则场景足够） |

#### 模组结构

一个模组是一个目录：

```
empire-upkeep/
├── mod.toml          # 模组元数据 + 可配置参数声明
├── init.rhai         # 加载时执行一次
├── tick_start.rhai   # 每 tick 开始时执行
└── tick_end.rhai     # 每 tick 结束时执行
```

##### mod.toml

```toml
[meta]
name = "empire-upkeep"
version = "1.2.0"
description = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大"
author = "kagurazaka"
license = "MIT"

# 依赖声明：依赖解析在引擎启动时完成
[dependencies]
"rhai-std" = ">=0.4, <1.0"          # Rhai 标准库
"base-economy" = ">=1.0, <2.0"      # 需要基础经济模组

# 兼容性声明
[compatibility]
engine = ">=0.8, <1.0"              # 支持的引擎版本范围
swarm_abi = 1                        # 最低 ABI 版本

# 冲突声明
conflicts = ["no-upkeep"]            # 与此模组互斥

# 可配置参数——每项在脚本中作为全局变量可用
[config]
drone_cost = { type = "u32", default = 2, min = 0, max = 100, description = "每 drone 每 tick 维护费" }
room_base = { type = "u32", default = 10, min = 0, max = 1000, description = "每房间基础维护费" }
room_superlinear = { type = "fixed<u32,4>", default = 1, min = 0, max = 100, description = "超线性系数（定点数，4位小数精度）" }
onshortfall = { type = "enum", default = "degrade", values = ["degrade", "damage", "despawn"], description = "资源不足时的处理方式" }
```

##### init.rhai

```rust
// 模组加载时执行一次——验证配置、初始化内部状态
fn init(config, actions) {
    actions.log_info(`empire-upkeep v${MOD_VERSION} loaded`);
    actions.log_info(`  drone_cost=${config.drone_cost}`);
    actions.log_info(`  room_superlinear=${config.room_superlinear}`);
    actions.log_info(`  onshortfall=${config.onshortfall}`);
}
```

##### tick_end.rhai

```rust
// 每 tick 结束时执行——计算维护费并扣除
fn on_tick_end(state, events, config, actions) {
    for player in state.players() {
        let drones = player.drones().len();
        let rooms = player.rooms().len();

        // 超线性：房间越多，每房间成本越高
        // room_superlinear 为 fixed<u32,4> 定点数（4位小数精度）
        let room_penalty = rooms * (config.room_base +
            rooms * config.room_superlinear / FIXED_SCALE);

        let total_cost = drones * config.drone_cost + room_penalty;

        actions.deduct_resource(player.id, "Energy", total_cost);
        actions.emit_event("upkeep_charged", #{
            player: player.id,
            drones: drones,
            rooms: rooms,
            cost: total_cost
        });
    }
}
```

#### Rhai API：模组可用的函数

```rust
// 状态查询（经可见性过滤——模组不能看到隐藏实体）
state.players()          → Iterator<Player>        // 聚合统计，不暴露具体玩家
state.tick()             → u64
player.drones()          → Iterator<Drone>          // 仅该玩家的 drone（owner=player_id）
player.rooms()           → Iterator<Room>           // 仅该玩家有视野的房间
player.resources()       → Map<String, u64>         // 仅该玩家的资源
drone.body_parts()       → Vec<BodyPart>
drone.position()         → (x, y, room_id)

// 世界修改（通过 actions，不进命令管线但经 mini-validator）
actions.deduct_resource(player_id, resource, amount)   // 扣除资源
actions.award_resource(player_id, resource, amount)    // 奖励资源
actions.damage_entity(entity_id, amount, reason)       // 对实体造成伤害
actions.set_entity_flag(entity_id, flag, value)        // 设置白名单标记（如 slow/empowered）
actions.emit_event(event_type, data)                   // 发出事件
actions.log_info(message)                              // 日志
actions.log_warn(message)

// 不可用: modify_entity（不在能力白名单中）
// 不可用: 文件 IO、网络、时钟、随机数（确定性要求）
```

#### Rhai 执行预算

每个模组每次 `tick_start` / `tick_end` 钩子的执行预算：

| 资源 | 限制 | 超限行为 |
|------|------|---------|
| AST 节点数（软限制） | 10,000/tick | 该模组本次 tick 跳过，记录警告 |
| actions 调用次数 | 100/tick | 超出部分丢弃 |
| `state.players()` 迭代 | 3,000 项 | 超出的玩家跳过 |
| 确定性节点预算（硬限制） | 100,000 AST 节点/tick | 强制终止当前模组，**该模组本 tick 的所有 actions 全部回滚**（事务性隔离）。超限模组记录警告，连续 10 tick 超限自动禁用。AST 节点数是确定性度量——同一输入在任何硬件上终止于相同节点，保证 state_checksum 可复现。墙钟仅用于告警监控（如单模组 >2s 触发运维告警），不作为状态决定因素。 |

> 连续 10 tick 超限的模组自动禁用，需服主手动重新启用。防止恶意/错误模组拖垮引擎。

所有 `actions` 操作被记录到 TickTrace——可回放、可审计。

#### Rhai 安全隔离

Rhai 模组在**引擎进程内**运行——服主安装的模组是受信代码。不引入进程隔离的复杂性和性能开销。

**安全模型**：

| 层级 | 机制 | 说明 |
|------|------|------|
| **源码完整性** | `mods.lock` pin 到 git commit + `checksum`（sha256） | 服主审查过的模组版本不可变，重现代码审计 |
| **执行预算** | AST 节点预算 + action 次数上限 | 防止死循环或资源耗尽（见上表） |
| **能力白名单** | 所有 `actions.*` 调用经引擎白名单校验 | 未注册的 action 被拒绝 + 审计日志。当前白名单：deduct_resource/award_resource/damage_entity/set_entity_flag/emit_event/log_info/log_warn |
| **事务隔离** | 单模组超限 → 该模组本 tick 所有 actions 回滚 | 不影响其他模组和玩家 |
| **引擎稳定性** | 超限模组连续 10 tick 自动禁用 | 需服主手动重新启用 |

**能力白名单**（引擎启动时构建，运行时所有 `actions.*` 调用经白名单校验）：

| Action | Handler | 说明 |
|--------|---------|------|
| `deduct_resource` | `engine::rule::handler::deduct_resource` | 扣除玩家资源 |
| `award_resource` | `engine::rule::handler::award_resource` | 奖励玩家资源 |
| `damage_entity` | `engine::rule::handler::damage_entity` | 对实体造成伤害 |
| `set_entity_flag` | `engine::rule::handler::set_entity_flag` | 设置白名单标记（如 slow/empowered/immune_Thermal） |
| `emit_event` | `engine::rule::handler::emit_event` | 发出世界事件 |
| `log_info` / `log_warn` | `engine::rule::handler::log` | 日志输出 |

> 扩展新 action 需在引擎中注册 handler + 加入白名单。未注册的 action 在运行时被拒绝并记录安全审计日志。所有 actions 操作被记录到 TickTrace——可回放、可审计。

#### 安装与配置

模组分发模型：**一个模组 = 一个 git 仓库**（开发）+ **一个 `.swarm-mod` 签名包**（发布）。无中心化市场或注册表。

```
开发阶段（作者）:
  git 仓库 → 打 tag → swarm mod pack → .swarm-mod + Ed25519 签名
                                            ↓
分发阶段（服主）:                      任意 HTTP/CDN
  swarm mod add <url-to-.swarm-mod>   → 下载 → 验证签名 → 解包
```

**Vanilla 内置模组**：官方维护的默认规则集模组（empire-upkeep、fog-of-war、resource-decay 等）各自独立 git 仓库，engine 通过 git submodule 引用固定版本。CI 对每个 submodule 执行 `swarm mod pack` 产出签名 `.swarm-mod`，随 engine release 一起发布。

```bash
# 安装模组（从 .swarm-mod 签名包）
swarm mod add https://releases.example.com/mods/empire-upkeep-1.2.0.swarm-mod

# 安装指定版本（从 GitHub Releases）
swarm mod add https://github.com/swarm-mods/empire-upkeep/releases/download/v1.2.0/empire-upkeep-1.2.0.swarm-mod

# 一键安装所有 vanilla 默认模组（随 engine release 发布的签名包集合）
swarm mod install-vanilla

# 查看已安装模组
swarm mod list

# 查看模组的可配置项
swarm mod config empire-upkeep

# 设置参数
swarm mod config empire-upkeep drone_cost 5
swarm mod config empire-upkeep onshortfall "damage"

# 在世界中启用（引用已安装的模组名）
swarm world add-mod empire-upkeep

# 更新模组（下载新版本 .swarm-mod，校验签名，替换旧版本）
swarm mod update empire-upkeep
```

**版本锁定**：`world.toml` 和 `mods.lock` 分离——前者由服主编辑（表达意图），后者由工具自动生成（记录解析结果 + 签名信息）。

```
world.toml              mods.lock
──────────              ─────────
服主手写                 自动生成，不应手改
version = "1.2"         package = "empire-upkeep-1.2.0.swarm-mod"
"我要这个版本"          "已解析为这个包 + 签名已验证"
提交到 git               提交到 git
```

- `swarm mod add <url>` 下载 `.swarm-mod` → 验证 Ed25519 签名 → 解包到 `~/.swarm/mods/{name}/` → 写入 `mods.lock`
- engine 启动时以 `mods.lock` 为准；若 `package` 引用文件不存在或签名校验失败，**拒绝启动**（不是 warn），返回 `ModIntegrityError`
- `author_pubkey`：模组作者声明的 Ed25519 公钥（十六进制），由 `mod.toml` 中的 `[meta] author_pubkey` 带出
- `package_hash`：整个 `.swarm-mod` 文件的 blake3 hash（hex）
- `signature`：作者私钥对 `package_hash` 的 Ed25519 签名（hex）
- 签名验证在 `swarm mod add` 和引擎启动时各执行一次——两次校验防止安装后文件被篡改

世界配置中引用（`world.toml`，仅表达意图）：

```toml
# world.toml — 服主编辑，表达意图
[world]
name = "Survival World"

[[mods]]
name = "empire-upkeep"
source = "https://releases.swarm.io/mods/empire-upkeep-1.2.0.swarm-mod"
version = "1.2.0"
[mods.config]
drone_cost = 5
room_superlinear = 2            # fixed<u32,4>: 0.0002 超线性系数
onshortfall = "damage"

[[mods]]
name = "resource-decay"
source = "https://github.com/swarm-mods/resource-decay/releases/download/v0.3.0/resource-decay-0.3.0.swarm-mod"
version = "0.3.0"
[mods.config]
decay_rate = 0.001
```

```toml
# mods.lock — 工具自动生成，记录解析结果 + 签名，与 world.toml 一并提交
[[mods]]
name = "empire-upkeep"
source = "https://releases.swarm.io/mods/empire-upkeep-1.2.0.swarm-mod"
version = "1.2.0"
author_pubkey = "ed25519:d75a...2f3c"                    # 作者 Ed25519 公钥（来自 mod.toml）
package_hash = "blake3:91e4...a7f2"                      # .swarm-mod 文件 blake3 hash
signature = "ed25519:d5a3...8b1e"                        # 作者对 package_hash 的 Ed25519 签名

[[mods]]
name = "resource-decay"
source = "https://github.com/swarm-mods/resource-decay/releases/download/v0.3.0/resource-decay-0.3.0.swarm-mod"
version = "0.3.0"
author_pubkey = "ed25519:a1b2...c3d4"
package_hash = "blake3:fe9a...6d2c"
signature = "ed25519:e4f5...9a0b"
```

#### 引擎集成

```rust
fn register_mod_systems(app: &mut App, world_config: &WorldConfig) {
    // world_config.mods 中的每个条目已解析为本地路径：
    //   所有模组（vanilla + 第三方）→ ~/.swarm/mods/{name}/
    //   （安装时已通过 .swarm-mod 签名包解包，签名已在校验阶段验证）
    for mod_def in &world_config.mods {
        let mut module = load_mod_from_path(&mod_def.path);
        module.configure(&mod_def.config);                // 注入参数
        module.run_init();                                 // init.rhai

        // 注册 tick 钩子
        let tick_end = module.tick_end_script.clone();
        app.add_systems(Update, move |world: &mut World| {
            let state = WorldState::from_world(world);
            let mut actions = RuleActions::new();
            let events = TickEvents::current();
            tick_end.call(&state, &events, &module.config, &mut actions);
            actions.apply(world);  // 经校验后写入
        }.after(death_cleanup_system));
    }
}
```

#### 模组分发

**一个模组 = 一个 git 仓库（开发）+ 一个 `.swarm-mod` 签名包（发布）**。Swarm 不运营中心化模组市场或注册表。

```
分发模型（开发 → 发布 → 消费）:

  开发仓库 (git)                 发布包 (.swarm-mod)              服主安装
  ┌──────────────────┐       ┌──────────────────────┐       ┌─────────────────┐
  │ swarm-mods/      │       │ empire-upkeep-1.2.0  │       │ swarm mod add   │
  │   empire-upkeep/ │  pack │   .swarm-mod          │  HTTP │   <url>         │
  │   fog-of-war/    │ ────→ │     mod.toml          │ ────→ │     ↓           │
  │   resource-decay/│       │     *.rhai            │       │ 验证 Ed25519 签名│
  │   ...            │       │     Ed25519 signature │       │ 解包到本地       │
  └──────────────────┘       └──────────────────────┘       │ world.toml 引用  │
   独立 git 仓库                 单文件分发                    └─────────────────┘
```

**Vanilla 内置模组**：官方维护的默认规则集模组各自独立 git 仓库。engine 仓库通过 git submodule 引用固定版本（仅开发/CI 用）。CI 对每个 submodule 执行 `swarm mod pack` 产出签名 `.swarm-mod`，随 engine release 一起发布。服主通过 `swarm mod install-vanilla` 一键安装所有默认模组，引擎启动时从 `~/.swarm/mods/` 加载（与第三方模组完全相同的路径和流程）。

**第三方模组**：作者维护自己的 git 仓库 → 打 tag → `swarm mod pack` 产出 `.swarm-mod` → 上传到 GitHub Releases / CDN / IPFS。服主 `swarm mod add <url>` 下载 `.swarm-mod`，引擎验证 Ed25519 作者签名后解包安装。更新通过 `swarm mod update`（下载新 `.swarm-mod` + 重新验证签名）。

**签名验证**：`.swarm-mod` 中的 `mod.toml` 声明 `author_pubkey`（Ed25519 公钥），签名文件包含作者私钥对整个包的 blake3 hash 的签名。引擎安装时校验签名——伪造签名的 `.swarm-mod` 直接拒绝，不写入本地文件系统。签名的存在也防止了 HTTPS 中间人替换包内容。

**发现**：不提供中心化搜索。模组通过社区渠道分发——文档 wiki、论坛、社交网络。模组仓库的 README 即为"商店页面"。

#### .swarm-mod 签名包格式

`.swarm-mod` 是一个 **tar.gz 归档 + Ed25519 签名的单文件分发格式**。既是分发载体，也是完整性/身份验证的凭证。

##### 内部结构

```
empire-upkeep-1.2.0.swarm-mod     # tar.gz 归档，标准命名: {name}-{version}.swarm-mod
├── mod.toml                       # 模组元数据（含 author_pubkey）
├── init.rhai                      # 加载时执行一次
├── tick_start.rhai                # 每 tick 开始钩子（可选）
├── tick_end.rhai                  # 每 tick 结束钩子（可选）
└── .swarm-mod-signature           # Ed25519 签名文件（不在归档内，与归档并行分发）
```

##### mod.toml 扩增字段

```toml
[meta]
name = "empire-upkeep"
version = "1.2.0"
description = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大"
author = "kagurazaka"
author_pubkey = "ed25519:d75a8b1c3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b"  # 必需：作者 Ed25519 公钥
license = "MIT"
# ... 其余字段不变
```

##### 签名算法

```
package = tar.gz(mod.toml, init.rhai, tick_start.rhai?, tick_end.rhai?)
package_hash = blake3(package)
signature = Ed25519_sign(author_privkey, package_hash)

验证:
  Ed25519_verify(author_pubkey, package_hash, signature) → true/false
```

- `.swarm-mod-signature` 文件包含 hex 编码的 64-byte Ed25519 签名
- 签名和 `.swarm-mod` 归档可放在同一目录（本地文件）或并行分发（HTTP `Link` 头指向签名 URL）
- `swarm mod pack` 工具自动完成：读取 `mod.toml` → 收集 .rhai 文件 → tar.gz → blake3 → Ed25519 签名
- `swarm mod verify <file>` 独立验证命令：检查签名是否与 `mod.toml` 声明的 `author_pubkey` 匹配

##### 工具链

```bash
# 作者侧：从 git 仓库产出签名包
swarm mod pack                         # 在当前目录生成 {name}-{version}.swarm-mod + 签名
swarm mod pack --key ~/.swarm/keys/author.ed25519   # 指定私钥路径

# 服主侧：验证 + 安装
swarm mod verify empire-upkeep-1.2.0.swarm-mod      # 纯验证，不安装
swarm mod add empire-upkeep-1.2.0.swarm-mod          # 验证签名 → 解包 → 写入 mods.lock
swarm mod add https://releases.example.com/mods/empire-upkeep-1.2.0.swarm-mod  # 下载 + 验证 + 安装

# CI 侧：批量打包所有 vanilla 模组（在 engine 仓库中使用 submodule 路径）
swarm mod pack-all                                # 遍历 engine/mods/ 下所有 submodule，逐个 pack

#### 规则可见性与 i18n

世界的活跃规则对所有玩家（人类和 AI）完全可见。每个配置项都有多语言描述。

##### mod.toml 中的 i18n

```toml
[meta]
name = "empire-upkeep"
version = "1.2.0"
description = "帝国规模维护费"

# 多语言描述
[meta.description_i18n]
zh = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大。维护费不足时效率下降。"
en = "Empire upkeep — more drones and rooms cost more per tick. Shortfall degrades efficiency."
ja = "帝国維持費——ドローンと部屋が多いほど毎 tick のコストが増加。不足時は効率低下。"

[config]

[config.drone_cost]
type = "u32"
default = 2
min = 0
max = 100
[config.drone_cost.description_i18n]
zh = "每架 drone 每 tick 消耗的能量"
en = "Energy consumed per drone per tick"
ja = "ドローン1機あたりの毎 tick エネルギー消費"

[config.room_superlinear]
type = "fixed<u32,4>"
default = 1
min = 0
max = 100
[config.room_superlinear.description_i18n]
zh = "超线性系数——房间越多，每间房的单位成本越高"
en = "Superlinear factor — more rooms increase per-room cost"
ja = "超線形係数——部屋が増えるほど1部屋あたりのコストが上昇"

[config.onshortfall]
type = "enum"
default = "degrade"
values = ["degrade", "damage", "despawn"]
[config.onshortfall.description_i18n]
zh = "资源不足时的处理方式：degrade=效率下降, damage=建筑受损, despawn=单位消亡"
en = "Behavior on resource shortfall: degrade=slow, damage=hurt buildings, despawn=lose units"
ja = "リソース不足時の動作：degrade=効率低下, damage=建物損傷, despawn=ユニット消滅"
[config.onshortfall.values_i18n]
degrade = { zh = "效率下降", en = "Efficiency degradation", ja = "効率低下" }
damage = { zh = "建筑受损", en = "Building damage", ja = "建物損傷" }
despawn = { zh = "单位消亡", en = "Unit despawn", ja = "ユニット消滅" }
```

##### 玩家可见的世界规则

人类玩家在 Web UI 中看到：

```
┌─────────────────────────────────────────────┐
│  世界规则 — Survival World                    │
│                                               │
│  🔧 empire-upkeep v1.2.0                      │
│  帝国规模维护费——drone 和房间越多，每 tick    │
│  消耗越大。维护费不足时效率下降。               │
│                                               │
│  当前参数:                                     │
│    drone_cost = 5        每架 drone 每 tick   │
│                          消耗的能量             │
│    room_superlinear = 0.2                     │
│                          超线性系数             │
│    onshortfall = damage  资源不足时的处理方式    │
│                                               │
│  🍂 resource-decay                          │
│  资源腐败衰减——储存的资源随时间缓慢减少。        │
│                                               │
│  当前参数:                                     │
│    decay_rate = 0.001   每 tick 衰减比例        │
└─────────────────────────────────────────────┘
```

AI 玩家通过 MCP 查询：

```
mcp.call("swarm_get_world_rules")
→ {
  "mods": [
    {
      "name": "empire-upkeep",
      "version": "1.2.0",
      "description": "帝国规模维护费——drone 和房间越多...",
      "config": {
        "drone_cost": { "value": 5, "type": "u32", "min": 0, "max": 100,
                        "description": "每架 drone 每 tick 消耗的能量" },
        "room_superlinear": { "value": 2, "type": "fixed<u32,4>",
                              "description": "超线性系数——房间越多..." },
        "onshortfall": { "value": "damage", "type": "enum",
                         "values": ["degrade","damage","despawn"],
                         "description": "资源不足时的处理方式" }
      }
    }
  ]
}
```

##### WASM 侧查询

玩家的 drone 代码可以查询当前世界规则：

```typescript
// TypeScript SDK
const rules = Game.world.rules();

for (const mod of rules.active_mods) {
    console.log(`${mod.name} v${mod.version}`);
    console.log(`  ${mod.description}`);
    for (const [key, param] of mod.config) {
        console.log(`  ${key} = ${param.value}  // ${param.description}`);
    }
}

// 根据规则调整策略
if (rules.get("empire-upkeep").config.onshortfall.value === "damage") {
    // 维护费不足会损坏建筑——必须保持能量正流入
    strategy.prioritize_energy_income();
}
```

##### 语言选择

引擎根据请求的 `Accept-Language` 头或 MCP 客户端的 `locale` 参数返回对应语言的描述。缺少翻译时回退到 `en`，再回退到 `description` 字段。

#### 帝国维护费示例效果

**默认启用**：empire-upkeep 模组通过 protocol hook + Vanilla 公式默认启用。服主可通过 `world.toml` 关闭或替换为自定义维护费公式。

> 以下数值由 Resource Ledger §Empire Upkeep 公式 `upkeep = base_upkeep × rooms × (1 + rooms / room_soft_cap)` 派生，Standard 默认 `base_upkeep=50, room_soft_cap=10`。**权威数值见 [Economy Balance Sheet](economy-balance-sheet.md) §1 Maintenance Curve**。

```
小帝国（1 房）: 维护费 ≈ 55/tick     — 新手阶段（前 2000 tick 免维护费）
中帝国（5 房）: 维护费 ≈ 375/tick   — 可承受
大帝国（20 房）: 维护费 ≈ 3,000/tick — 需要高效经济
巨帝国（50 房）: 维护费 ≈ 15,000/tick — 硬上限
```

> **免维护费（R23 D1/A）**：前 1 controller + 3 drone 在 `free_upkeep_ticks`（默认 2000）内免维护费。新玩家初始资源 `{Energy: 5000, Minerals: 2000}`。详见 Resource Ledger §2.3。

### 2.8 Determinism Contract — 确定性合同

> 确定性保证的完整合同见 [Tick Protocol §7](specs/core/01-tick-protocol.md#7-确定性保证与反作弊)。

#### 固定算法

| 组件 | 算法 | 说明 |
|------|------|------|
| PRNG | **Blake3 XOF** | 确定种子 + offset → 随机流。与哈希同原语，消除 ChaCha 依赖，纯软件 ~6 GB/s。XOF 模式：`blake3::Hasher::update_with_seek(seed, offset)` |
| 种子 | world_seed = Blake3(32随机字节) | 32 字节熵（256-bit），编码为 hex 字符串。不可从 tick_number 推导。**每 10,000 tick 自动轮换**（Blake3(旧种子, 当前tick)），防止长期观察推断种子空间 |
| Hash | **Blake3** | 固定实现。不用 std::hash / SipHash（跨版本可变）。 |
| 种子洗牌 | `Blake3("shuffle" \\|\\| world_seed \\|\\| tick.to_le_bytes())` | 每 tick 确定但不可预测的玩家顺序。shuffle 后 TickTrace 记录 seed epoch + 活跃玩家集快照以支持回放。域名分离前缀 `"shuffle"` 防止与其他 Blake3 用途碰撞 |
| ECS 顺序 | `.chain()` + `.before()/.after()` | 有数据依赖的串行（death→spawn→combat→death_cleanup），无依赖的并行（regeneration, decay）。Bevy 依赖图保证偏序不变，确定性不依赖并行度 |
| 数值 | 整数 + 定点数 | 禁浮点（f64 跨平台/编译器非确定）。所有游戏引擎数值使用定点整数类型（ResourceRate_i64, BasisPoints, EfficiencyBps, ConfidenceBps, MilliUnits 等，见 game_api.idl.yaml §type_registry 和 economy.idl.yaml §type_registry）。Rhai 模组脚本同样禁用浮点——所有模组参数必须声明为 `u32`/`i64`/`fixed<u32,N>` 定点类型，Rhai 引擎侧关闭浮点运算能力。 |
| 排序 | `(priority_class, shuffle_index, sequence, source)` | 分层排序键——相同 seed + 相同玩家集 + 相同指令 → 相同顺序。详见 `01-tick-protocol.md` §9.1 |
| HashMap 顺序 | `indexmap` | 不用 std::HashMap（迭代顺序非确定） |

#### 回放保证

给定 tick N-1 状态 + tick N RawCommand + world_seed + world_config（世界规则快照）+ mods_lock（模组版本快照）→ 相同 Wasmtime pinned 版本下 `execute_deterministic == recorded_state`。每个 tick 产出 `state_checksum` 写入 TickTrace。CI 对随机采样 tick 做 full replay 验证——包括恢复对应 `world_config` 规则集 + checkout 到对应 `mods_lock` 记录的精确模组 commit。

### 2.9 Drone 间消息机制

Drone 可以通过消息系统进行点对点通信，实现去中心化的资源交换协议。

**消息模型**：Drone 在 `tick()` 中返回 `Command` 的同时可附带 `Message[]`。消息为点对点——从一个 drone 到另一个 drone，仅在发送方和接收方处于同一 room 或互相可见时投递成功。

**确定性**：消息按 tick 顺序投递——同一 tick 内，消息按 `(sender_id, recipient_id)` 字典序排列后按序投递到接收方 WASM 的下一 tick `snapshot.messages` 中。消息传递结果完全由世界状态决定，保证 replay 一致性。

**点对点资源交换协议**：消息 payload 可用于实现 peer-to-peer 资源交换协议——例如 drone A 向 drone B 发送"请求 100 Energy，我用 50 Crystal 交换"的 offer，drone B 在下 tick 收到消息后决定是否接受。此类协议完全在 WASM 层实现，引擎不提供内置撮合/担保。

**不可信协议（Game Theory Element）**：消息协议不强制诚实——drone 可以选择发送虚假 offer、收到资源后不履约、或发送恶意 payload 试探对方代码逻辑。引擎不校验 payload 语义，仅保证消息已投递。这使得 peer-to-peer 交换成为博弈论问题——玩家必须设计可信协议或依赖声誉系统。

**消息格式**：

| 字段 | 类型 | 说明 |
|---|---|---|
| `sender_id` | EntityId | 发送方 drone 的实体 ID |
| `recipient_id` | EntityId | 目标 drone 的实体 ID（必须可见或在同 room） |
| `payload` | `[u8; 256]` | 不透明字节 payload，最大 256B |

**WASM 接口**：WASM `tick()` 返回的 JSON 中包含可选的 `messages` 字段：

```typescript
// TypeScript SDK — tick() 返回 commands + messages
function tick(snapshot: WorldSnapshot): TickResult {
    const commands: Command[] = [...];
    const messages: Message[] = [];
    
    // 向附近 drone 发送交换请求
    for (const drone of snapshot.visible_drones) {
        messages.push({
            recipient_id: drone.id,
            payload: encodeOffer({ action: "trade", offer: { Energy: 50 }, want: { Crystal: 100 } })
        });
    }
    
    return { commands, messages };
}
```

引擎在 EXECUTE 阶段处理 commands 的同时处理 messages——消息写入接收方实体的 `PendingMessages` 组件，在下一 tick snapshot 中暴露给接收方 WASM。

**可见性约束**：消息投递需满足 `is_visible_to(sender, recipient)` 或 `sender.room == recipient.room`。若约束不满足，消息静默丢弃（不报错——防止通过消息投递失败探测隐藏单位）。

---

## 3. 表现层：Drone 人格、外交、行为可视化与经济反馈

本节定义 Swarm 的非核心玩法表现层——不影响 tick 确定性，但决定玩家体验的"可读性"和"情感连接"。

### 3.1 Drone 人格系统

每个 drone 在创建时获得确定性人格，由 `Blake3(player_id || spawn_tick || spawn_sequence || world_seed)` 生成。人格不影响 gameplay 数值——纯表现和行为微调。

#### 人格维度

| 维度 | 范围 | 效果 |
|---|---|---|
| **aggression** | 0.0–1.0 | 影响 idle 动画（焦躁↔平静）、移动路径微抖动幅度 |
| **curiosity** | 0.0–1.0 | 影响探索倾向——idle 时在出生点附近小范围随机游走（半径 `curiosity × 5` 格） |
| **loyalty** | 0.0–1.0 | 影响跟随距离（近↔远）、优先保护高 loyalty 的 drone |
| **efficiency** | 0.0–1.0 | 影响动画速度（利落↔慵懒），不影响实际 tick 执行速度 |

#### 确定性与回放

人格种子完全确定性——同一 drone 在所有 replay 中表现出相同动画和行为。前端根据人格参数渲染动画，不改变网络同步的游戏状态。

#### 人格可视化

```
高 aggression:   drone 微微抖动，攻击时前冲幅度大
低 aggression:   drone 平稳移动，攻击时保持距离
高 curiosity:    idle 时更大范围游走，频繁转向
低 curiosity:    idle 时几乎静止，只在有指令时移动
高 efficiency:   采集动画利落，一次抓取动作完成
低 efficiency:   采集动画慵懒，抓取后停顿片刻
```

#### 玩家经济中的角色

人格维度可选作为市场/社交信号：高 efficiency drone 在交易中可能溢价（尽管不影响实际性能——纯品牌/社区价值）。服主可禁用或扩增人格维度。

### 3.2 外交系统

玩家间正式关系由 on-chain 外交协议管理，所有操作记录在 FDB 中，可回放审计。

#### 外交状态机

```
                 propose ──────────────────────────────┐
                    │                                   │
    neutral ────────┤                                   │
                    │                                   ▼
                    └── propose ──→ pending ──→ accept ──→ allied
                                        │
                                        └── reject ──→ neutral
                                        └── timeout (72h) ──→ neutral

    allied ──→ break ──→ neutral (cooldown: 24h 不可重新提议)
```

| 状态 | 发起方 | 目标方行为 | 解除方式 |
|---|---|---|---|
| `neutral` | 初始状态 | 标准 visibility rules 适用 | — |
| `pending` | A 向 B 提议 | B 可 accept/reject | timeout 72h 自动 reject |
| `allied` | 双方同意 | 见下方 allied 特权 | 任一方 break，24h cooldown |
| `broken` | 曾 allied | 等同 neutral | 24h 后恢复 neutral |

#### Allied 特权与限制

| 权限 | neutral | allied |
|---|---|---|
| 可见性 | `is_visible_to` 标准规则 | ally 级可见性（资源/建筑/HP 额外可见） |
| 攻击 | 可攻击（受 PvP 规则约束） | 禁止——攻击 ally 返回 `FriendlyTarget` |
| Overload/Hack/Drain 特殊攻击 | 可攻击 | 禁止——等同攻击 |
| 资源 transfer | 仅 global↔local | 可直接 player↔player transfer，免 convert 延迟 |
| 共享 intel | 不可见 | ally 的 snapshot 包含友方 drone 位置标注 |
| 穿行 | 标准碰撞 | ally drone 不阻挡彼此移动（无碰撞） |
| Heal | 仅 self | 可 Heal ally drone |

#### 外交安全

- **间谍保护**：allied 状态不暴露对方 WASM 代码——仅暴露 drone 位置和资源状态
- **叛变冷却**：break alliance 后 24h cooldown，防止"结盟→偷袭→立刻重结盟"循环
- **外交 audit**：所有 propose/accept/reject/break 事件写入 `diplomacy/{world_id}/{tick}` 日志
- **多联盟上限**：每玩家最多同时 5 个 active alliance

#### 跨世界 Federation

Swarm 支持跨世界 identity federation——同一身份可在多个世界中使用。**当前仅 identity-only**：资源、排名、GCL、RCL 等游戏内资产和进度不跨世界同步——每个世界是独立的经济体和排名域。跨世界资源转移、统一排名、跨世界 alliance 等特性不在当前设计范围内。

### 3.3 行为可视化

所有 drone 状态和特殊效果通过前端渲染可见——不依赖额外 MCP 查询。

#### Drone 状态指示器

| 状态 | 视觉表现 |
|---|---|
| idle | 人格驱动的微动画（游走/静止），淡色光圈 |
| moving | 移动轨迹线（可选显示/隐藏），方向箭头 |
| harvesting | 采集光束动画（drone → source），粒子飞向 drone |
| building | 建筑脚手架动画，进度条（tick 完成百分比） |
| attacking | 攻击光束/弹道（颜色按 damage_type），命中闪光 |
| damaged | HP 条闪烁红色，低 HP 时冒烟 |
| dying | 解体动画（1 tick），零件飞散 |
| spawning | 出生粒子特效（2 tick） |
| SpawningGrace | 金色护盾光环（1 tick 无敌帧） |

#### 特殊效果可视化

| 效果 | 目标表现 | 施加者表现 |
|---|---|---|
| Overload | 🔵 蓝色电流环绕，总压力值浮字显示 | 自己的 contribution 高亮闪烁 |
| Hack | 🟣 紫色控制锁链（stage 递增加粗），被控制 drone 变紫色轮廓 | 链接着与被控制 drone |
| Drain | 🟢 绿色资源流线（target → attacker） | 资源流入动画 |
| Debilitate | 🔴 红色易伤标记（骷髅图标） | 施加时闪红 |
| Disrupt | ⚡ 黄色闪电打断当前动画 | 一击即散 |
| Fortify | 🛡️ 白色护盾光环，清除所有负面特效 | 施加时圆形扩散波 |
| Leech | 🩸 深红吸血特效 | target → attacker |
| Fabricate | 🏗️ 建筑变形动画（drone → structure） | 持续至完成 |

#### 经济状态可视化

建筑和房间级别经济状态：

| 元素 | 视觉 |
|---|---|
| 建筑 HP | HP 条（绿→黄→红），低 HP 时闪烁 |
| Controller 等级 | RCL 数字 + 光环颜色（1灰→8金） |
| 全局存储利用率 | 房间边缘颜色深度（白→红，按 storage_tax tier） |
| 资源点剩余 | 资源节点大小/亮度随剩余量衰减 |
| 帝国势力范围 | 盟友可见 room 边框颜色（自己的颜色标识） |

### 3.4 玩家经济反馈循环

> 反馈循环的完整设计见 [Feedback Loop](specs/gameplay/06-feedback-loop.md)。

为人类和 AI 玩家提供经济健康可见性——通过 MCP 和 Web UI 双通道。

#### 经济仪表板（Web UI）

```
┌─ 经济总览 ─────────────────────────────────┐
│ Energy 净流量:  +1,245/tick  (收入 3,200 - 支出 1,955)    │
│ 全局存储:      45,230 / 1,000,000 (4.5%)  [████░░░░░░]  │
│ 税率:          0% (30% 以内免税)                         │
│                                                    │
│ ⚠️ 预测: 以当前速率，240 tick 后全局存储将进入 1% 税率区间 │
│                                                    │
│ 📊 效率:                                           │
│   Harvest:  92% (45/49 drones harvesting)           │
│   Build:    100% (3/3 drones building)              │
│   Idle:     1 drone (d3 — 无可用 Source)           │
│                                                    │
│ 📈 趋势 (最近 100 tick):                           │
│   Energy:  ████████░░  +8%                         │
│   Drones:  ██████░░░░  +5 (30→35)                  │
│   Rooms:   ████░░░░░░  +1 (2→3)                    │
└────────────────────────────────────────────────────┘
```

#### MCP 经济查询

| 工具 | 返回 | 说明 |
|---|---|---|
| `swarm_get_economy` | `EconomySnapshot` | 当前 tick 经济全貌（收入/支出分项、storage、税率、预测） |
| `swarm_get_drone_efficiency` | `Vec<DroneEfficiency>` | 每 drone 最近 N tick 的效率（harvest 量、idle 比例） |
| `swarm_get_economy_trend` | `EconomyTrend` | 最近 K tick 的趋势线（energy、drones、rooms、storage） |

这些工具不修改世界状态——纯读取，不计入 MCP rate limit 的写操作配额。AI agent 可利用此数据做出宏观策略决策（"我应该扩展还是优化效率？"）。

#### 告警与通知

| 条件 | 通知方式 | 目标 |
|---|---|---|
| storage 将进入下一税率区间（30 tick 预警） | WebSocket push + Web UI toast | 人类玩家 |
| drone 连续 10 tick idle | Web UI 警告图标 | 人类玩家 |
| Energy 净流入为负且持续 50 tick | `economy_warning` MCP 事件 | AI agent |
| WASM 代码在最近 100 tick 中效率低于世界 P50 | `efficiency_benchmark` MCP 事件 | AI agent |
| 建筑 HP < 20% | Web UI 闪烁 + MCP `structure_damaged` 事件 | 双通道 |

### 3.5 设计决策

| 决策 | 结论 | 理由 |
|---|---|---|
| 人格是否影响 gameplay | 否，纯表现 | 维护确定性；避免"roll 到好人格=优势"的彩票效应 |
| 人格种子 | 确定性 Blake3 | 同 replay 保证相同动画 |
| 外交是否 on-chain | 是，FDB 持久化 | 可审计、可回放、防作弊 |
| Allied 可见性增强 | ally 级（非完全透明） | 保留战术深度；不透传 WASM 代码 |
| 经济仪表板实时性 | 每个 BROADCAST 后更新 | 与 tick 同步，无额外轮询 |
| 行为可视化是否影响 tick | 否，前端纯渲染 | 引擎不计算动画——前端从 snapshot 推导状态 |
| MCP 经济查询 rate limit | 独立配额 10/tick | 不挤占 gameplay MCP 配额 |
