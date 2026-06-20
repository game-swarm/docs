# World Rules Engine — 世界规则配置规范

> 详见 design/gameplay.md

## 1. 定位

Swarm 不是「一个游戏」，是「游戏引擎平台」。规则模组是**可安装的 Rhai 脚本 + 声明式配置**——轻量、确定、可组合。

```
玩家代码:  WASM → 控制 drone     (不可信 → sandbox)
规则模组:  Rhai → 修改世界规则    (服主声明 → 引擎嵌入)
引擎核心:  Rust → 确定性模拟      (不可变)
```

每个世界通过 `world.toml` 启用一组模组，每模组有独立的参数配置。模组通过 `actions` 请求引擎操作——不能绕过 Command Validation Pipeline。

## 2. 配置 Schema

```toml
# world.toml

[world]
name = "World of Swarm"
mode = "persistent"               # persistent | arena
tick_interval_ms = 3000

[spawn]
policy = "RandomRoom"
respawn = "NewRoom"
cooldown = 0

[code]
update_cost = {}
update_cooldown = 0
update_window = { every = 0, duration = 0 }
propagation_speed = 0
propagation_source = "Spawn"

# ═════════════════════════════════════
# 自定义资源类型
# ═════════════════════════════════════

[[resource_types]]
name = "Energy"
display_name = "能量"
category = "energy"
starting_amount = 1000
max_storage = 100000
decay_rate = 0.0
tradeable = true

[[resource_types]]
name = "Matter"
display_name = "物质"
category = "mineral"
starting_amount = 500
max_storage = 50000
decay_rate = 0.001
tradeable = true

# 各动作资源消耗（键名来自 resource_types.name）
[actions.costs]
spawn = { Energy = 200, Matter = 50 }
build.Extension = { Energy = 50 }
build.Tower = { Energy = 100, Matter = 25 }
body_part.Move = { Energy = 50 }
body_part.Work = { Energy = 100 }
body_part.Attack = { Energy = 80, Matter = 20 }
body_part.Heal = { Energy = 250, Matter = 100 }
code_update = { Energy = 500 }

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

# ═════════════════════════════════════

[drone]
lifespan = 1500                 # drone 基础存活 tick 数
env_vars = true
memory_size = 1024
memory_spawn_cost = {}          # 每 byte 孵化成本
memory_upkeep_cost = {}         # 每 byte 每 tick 维护费
max_body_parts = 50
max_drones_per_player = 500

[resources]
source_regeneration_rate = 10000   # fixed<u32,4>: 1.0
build_cost_multiplier = 10000       # fixed<u32,4>: 1.0
drone_decay_rate = 10000            # fixed<u32,4>: 1.0

# 物流配置
global_storage_enabled = true
transfer_to_global_cost = { Energy = 0.01 }
transfer_from_global_cost = { Energy = 0.05 }

[combat]
pvp_enabled = true
friendly_fire = false
damage_multiplier = 1.0

[visibility]
fog_of_war = true

# ═════════════════════════════════════
# 已安装模组
# ═════════════════════════════════════

[[mods]]
name = "empire-upkeep"
version = "1.2.0"
[mods.config]
drone_cost = 5
room_superlinear = 2    # fixed<u32,4>: 0.0002
onshortfall = "damage"

[[mods]]
name = "resource-decay"
version = "0.3.0"
[mods.config]
decay_rate = 0.001

```

## 3. ECS Plugin 注册

```rust
// engine/src/world_rules.rs

pub struct WorldConfig {
    pub world: WorldSettings,
    pub spawn: SpawnConfig,
    pub code: CodeConfig,
    pub drone: DroneConfig,
    pub resources: ResourceConfig,
    pub combat: CombatConfig,
    pub visibility: VisibilityConfig,
}

impl WorldConfig {
    /// 根据配置注册可选的 ECS System
    pub fn register_systems(&self, app: &mut App) {
        // 注入资源注册表——核心组件
        let registry = ResourceRegistry::from_config(self);
        app.insert_resource(registry);

        // 基础系统始终注册（Phase 2b: Inline 命令执行后的系统链）
        app.add_systems(Update, (
            death_mark_system,       // 标记待死亡 entity，释放 room cap
            spawn_system,            // 统一创建校验通过的 drone
            regeneration_system,     // 资源点再生
            combat_system,           // 战斗结算（damage 先 → heal 后）
            decay_system,            // 疲劳/冷却递减
            death_cleanup_system,    // 实际 despawn
        ).chain());

        // === 孵化规则 ===
        if self.spawn.policy == SpawnPolicy::ManualSelect {
            app.add_systems(Update, manual_spawn_system.before(spawn_system));
        }

        // === 代码部署规则 ===
        if self.code.update_cost != ResourceCost::default() {
            app.add_systems(Update, code_update_cost_system);
        }
        if self.code.update_window.every > 0 {
            app.add_systems(Update, code_update_window_system);
        }
        if self.code.propagation_speed > 0 {
            app.add_systems(Update, code_propagation_system.before(spawn_system));
        }

        // === Drone 控制 ===
        if self.drone.env_vars {
            app.add_systems(Update, drone_env_var_system);
        }
        if !self.drone.memory_upkeep_cost.is_empty() {
            app.add_systems(Update, memory_upkeep_system.before(decay_system));
        }

        // === 可见性 ===
        if !self.visibility.fog_of_war {
            // 无 fog of war → 跳过可见性过滤
            app.insert_resource(VisibilityMode::FullInformation);
        }

        // === 战斗 ===
        if !self.combat.pvp_enabled {
            app.add_systems(Update, pvp_block_system.before(combat_system));
        }
    }
}
```

> **R27 ML-3 — ECS Entity Iteration Determinism**: Bevy ECS 不保证 archetype/table 内部存储的遍历顺序。引擎在所有遍历中必须显式排序（按 `entity_id` 字典序），确保相同世界状态 → 相同遍历顺序 → 相同输出。CI 增加 `randomized-entity-iteration` test mode：通过 feature flag 随机化 Bevy 内部存储顺序，运行确定性 replay 场景并断言 `state_checksum` 一致。此测试不改变生产行为，仅验证排序假设未被隐式依赖打破。

## 4. 规则 System 示例

### 代码传播速度

```rust
/// 当 code_propagation_speed > 0 时，代码更新从传播源向外扩散
fn code_propagation_system(
    config: Res<WorldConfig>,
    mut drones: Query<(Entity, &Position, &Owner, &mut CodeVersion)>,
    spawns: Query<(&Position, &Owner), With<Spawn>>,
) {
    let speed = config.code.propagation_speed;
    if speed == 0 { return; }  // 即时传播，跳过后面的计算

    for (entity, pos, owner, mut version) in drones.iter_mut() {
        // 找到该玩家最近的传播源
        let nearest_source = spawns.iter()
            .filter(|(_, o)| o.0 == owner.0)
            .map(|(p, _)| distance(pos, p))
            .min();

        if let Some(dist) = nearest_source {
            // 计算传播延迟：距离 / 速度 = tick 数
            let propagation_delay = dist / speed;
            // 如果版本太新还没传播到，保持旧版本
            if version.updated_at + propagation_delay > current_tick() {
                version.fallback_to_previous();
            }
        }
    }
}
```

### 内存维护费

```rust
/// 当 memory_upkeep_cost 不为空时，每 tick 按使用量扣资源
fn memory_upkeep_system(
    config: Res<WorldConfig>,
    mut players: Query<(&mut PlayerResources, &PlayerMemory)>,
) {
    let upkeep = &config.drone.memory_upkeep_cost;
    if upkeep.is_empty() { return; }

    for (mut resources, memory) in players.iter_mut() {
        let used_bytes = memory.used_bytes();
        for (res_name, cost_per_byte) in upkeep {
            let total_cost = (used_bytes * cost_per_byte) / FIXED_SCALE;
            if total_cost > 0 {
                resources.deduct(res_name, total_cost);
                // 资源不足 → drone 随机失忆（减少存储）
                if resources.get(res_name) < 0 {
                    memory.truncate_to_fit(resources);
                }
            }
        }
    }
}
```

## 5. WASM 侧 API

```rust
// host function: 读取世界配置
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
```

```typescript
// TypeScript SDK
interface WorldConfig {
    spawn: { policy: string; respawn: string; cooldown: number };
    code: {
        update_cost: Record<string, number>;
        update_cooldown: number;
        update_window: { every: number; duration: number };
        propagation_speed: number;
    };
    drone: { env_vars: boolean; memory_size: number };
    combat: { pvp_enabled: boolean; friendly_fire: boolean };
}

// 用法
const cfg = Game.world.config();

// 根据规则调整策略
if (cfg.code.propagation_speed > 0) {
    // 分阶段部署：先更新近处 drone，再逐步扩散
    deployByDistance(cfg.code.propagation_speed);
}

if (cfg.code.update_window.every > 0) {
    // 在窗口期内批量更新
    scheduleUpdate(cfg.code.update_window);
}

if (cfg.drone.env_vars) {
    // 使用环境变量做角色标注
    drone.set("role", "harvester");
}

if (cfg.drone.memory_upkeep_cost.Energy > 0) {
    // 内存有维护费——只在必要时存储状态
    drone.memory.compact();
}
```

## 5.1 Rhai 事务性执行模型

规则模组的 Rhai 脚本在每 tick 的规则注入阶段执行。所有 `actions.*` 调用（如 `actions.deduct`、`actions.award`、`actions.emit_event`）**不直接修改世界状态**，而是遵循事务性语义：

```
Rhai 脚本执行
    │
    ▼
┌─────────────────────────────────┐
│  RhaiActionBuffer (内存缓存)     │  ← 所有 actions.* 调用写入此 buffer
│  - deducts: Vec<DeductAction>   │
│  - awards:  Vec<AwardAction>    │
│  - events:  Vec<GameEvent>      │
│  - effects: Vec<WorldEffect>    │
└────────────┬────────────────────┘
             │ 脚本执行完毕
             ▼
┌─────────────────────────────────┐
│  钩子执行完毕检查                 │  ← 所有注册的 Rhai 钩子均已返回
│  (on_tick / on_command / etc.)  │
└────────────┬────────────────────┘
             │ 全部成功
             ▼
┌─────────────────────────────────┐
│  统一 Apply                      │  ← 按顺序将 buffer 内容写入世界状态
│  1. deduct（扣资源）              │     FDB 事务内 atomic commit
│  2. award（发资源）               │
│  3. emit_event（发事件）          │
│  4. effect（世界效果）            │
└────────────┬────────────────────┘
             │
             ▼
       世界状态已更新
```

**超时回滚**：若任一 Rhai 脚本超过确定性节点预算（默认 100,000 AST 节点），整个 `RhaiActionBuffer` 丢弃，世界状态不变。AST 节点是确定性度量——同一输入在任何硬件上终止于相同节点，保证回放/重模拟一致性。墙钟仅用于运维告警（如单模组 >2s 触发告警），不作为状态决定因素。隔离脚本副作用——一个脚本超限不影响其他脚本或核心引擎。

**部分失败处理**：
- 单个 `actions.*` 调用失败（如 deduct 资源不足）→ 该 action 被跳过，不影响 buffer 中其他 action
- 脚本 panic / 语法错误 → 该脚本的全部 buffer 丢弃，其他脚本 buffer 保留
- 所有脚本执行完毕后，buffer 中有效的 action 一次性 apply

**隔离保证**：
- Rhai 脚本**不能**绕过 Command Validation Pipeline（见 specs/core/02-command-validation §1）
- Rhai 脚本**不能**直接写入 ECS 组件——只能通过 `actions.*` API
- Rhai 脚本**不能**访问其他玩家的私有数据
- Buffer apply 阶段由引擎核心在 FDB 事务中执行，保证确定性

**RuleMod 角色声明**：RuleMod 是**世界规则系统**——通过声明式钩子（`on_tick`、`on_command`、`on_event`）修改世界参数和行为，不是玩家命令旁路。RuleMod 不能：(a) 为特定玩家创建或销毁实体；(b) 绕过 Command Validation Pipeline 注入 RawCommand；(c) 直接修改玩家私有数据（如 WASM 内存、部署历史）。RuleMod 的生效范围是**世界级**（全局资源税率、事件触发、环境效果），不得降级为**玩家级作弊通道**。

**能力命名空间**：`actions.*` API 是 RuleMod 修改世界状态的唯一渠道。每个能力有明确的读写范围和审计要求：

| API | 能力 | 允许范围 | 禁止项 | 审计字段 |
|-----|------|---------|--------|---------|
| `actions.deduct(resource, amount, reason)` | 扣除全局资源 | 全局资源池（Energy、Crystal 等） | 禁止扣到负数；禁止扣除玩家私有资源 | `mod_id, tick, resource, amount, reason` |
| `actions.award(resource, amount, reason)` | 发放全局资源 | 全局资源池 | 禁止超过 `world.toml` 中 `max_award_per_tick` 上限 | `mod_id, tick, resource, amount, reason` |
| `actions.emit_event(event_type, data)` | 发射世界事件 | 预定义事件类型（`ResourceCrisis`, `Invasion`, `WeatherChange` 等） | 禁止伪造玩家命令事件；禁止包含玩家私有数据 | `mod_id, tick, event_type` |
| `actions.set_world_param(key, value)` | 修改世界参数 | `world.toml` 中标记 `mutable = true` 的参数 | 禁止修改 `mutable = false` 的参数（如 tick_interval_ms） | `mod_id, tick, key, old_value, new_value` |
| `actions.set_entity_flag(entity_id, flag, value)` | 设置实体 flag | 仅全局实体（Source、Controller）；flag 必须在 `allowed_flags` 白名单中 | 禁止设置玩家 drone 的 flag；禁止 `immune_*` 以外的 combat 修改 | `mod_id, tick, entity_id, flag, value` |

能力扩展（如 `actions.spawn_npc`）需通过 `mod.toml` 声明 `required_capabilities = ["spawn_npc"]`，服主在 `world.toml` 中显式授权。

**信任链**：模组的完整生命周期受以下信任链约束：

| 阶段 | 机制 | 说明 |
|------|------|------|
| **签名** | Ed25519 签名（blake3 摘要，整个 `.swarm-mod` 包） | `.swarm-mod` 归档附带 `.swarm-mod-signature`；签名无效 → 拒绝加载 |
| **作者身份** | `mod.toml` 中 `[meta] author_pubkey` | 模组作者自行声明公钥。服主通过选择信任的 `.swarm-mod` 来源表达信任——下载即信任 |
| **版本锁定** | `mod.toml` 声明 `version = "1.2.3"` + `engine = ">=0.8"` | 引擎检查版本兼容性；不兼容版本拒绝加载 |
| **吊销 (CRL)** | `.swarm-mod` 签名通过 `author_pubkey` 验证 | 若作者密钥泄露，作者发布新版本模组（新 pubkey）+ 社区公告。无中心化 CRL——去中心化信任模型 |
| **Operator Override** | `swarm mod disable <mod_id> --world <world>` | 运行时禁用指定模组（不卸载，仅暂停执行）。下次 tick 不再调用该模组钩子 |
| **回滚策略** | 模组禁用后，其历史 effects 不回滚（已持久化到 FDB） | 世界状态不可逆——effects 一旦 apply 即永久生效。服主需通过新模组或手动修复纠正 |

**进程内模式**（唯一生产运行模式）：Rhai engine 在核心引擎进程内执行。安全边界由 Ed25519 数字签名验证保证——所有模组必须签名，不存在"允许未签名"的宽松模式。

- 签名验证在引擎启动时一次性完成，运行时无额外开销
- 信任决策由服主在安装 `.swarm-mod` 时做出（选择从哪个 URL 下载）——签名验证的是"代码确实来自声明的作者"，而非"作者是否在白名单中"。消除了中心化信任列表的维护负担
- 模组超时（确定性 AST 节点预算超限）仅丢弃该模组本 tick 的 actions，不影响核心引擎或其他模组。AST 节点预算是确定性度量，同一输入在任何硬件上终止于相同节点，保证回放/重模拟一致性
- 墙钟仅用于运维告警（如单模组 >2s 触发告警），不作为状态决定因素
- RuleMod **禁止** inprocess 模式之外的其他执行模式——不存在 `[rhai] isolation` 切换选项

**模组签名机制**：整个模组作为一个 `.swarm-mod` tar.gz 归档分发，附带单个 Ed25519 签名。引擎安装时验签，启动时再次验签：

```
empire-upkeep-1.2.0.swarm-mod        # tar.gz 归档，标准命名: {name}-{version}.swarm-mod
├── mod.toml                          # 含 author_pubkey 字段
├── init.rhai
├── tick_start.rhai                   # 可选
└── tick_end.rhai                     # 可选

empire-upkeep-1.2.0.swarm-mod-signature  # Ed25519 签名文件（与归档并行分发）
```

- 签名算法：`blake3(tar.gz归档)` → `Ed25519_sign(author_privkey, package_hash)`
- `author_pubkey` 在 `mod.toml` 的 `[meta]` 中声明——**由模组作者自行声明，而非服主配置白名单**。服主通过选择信任哪个 `.swarm-mod` 来源来表达信任
- 签名由模组开发者使用 `swarm mod pack` 生成，与打包一步完成
- `.swarm-mod-signature` 与 `.swarm-mod` 归档并行分发（同一目录或 HTTP `Link` 头指向签名 URL）
- 引擎安装时验签两次：`swarm mod add` 下载后立即验签 + 引擎启动时再次验签。任一失败 → `ModIntegrityError`，拒绝加载

#### 模组签名

模组签名确保模组代码来自声明的作者且未被篡改。签名流程：

```
开发者侧:
  1. 编写模组（.rhai 文件 + mod.toml，含 author_pubkey）
  2. swarm mod pack --key ~/.swarm/keys/author.ed25519
     → 产出 {name}-{version}.swarm-mod + {name}-{version}.swarm-mod-signature
  3. 上传两个文件到 GitHub Releases / CDN

服主侧:
  1. 安装模组: swarm mod add https://releases.example.com/mods/empire-upkeep-1.2.0.swarm-mod
     → 自动下载 .swarm-mod + .swarm-mod-signature → 验证签名 → 解包到 ~/.swarm/mods/
  2. world.toml 中引用（source = .swarm-mod URL, version = semver）
  3. 引擎启动时再次验签（防止安装后文件被篡改）——验证失败拒绝启动
```

**签名验证流程**（引擎侧）：

1. 引擎启动时读取 `mods.lock`，获取每个模组的 `author_pubkey`、`package_hash`、`signature`
2. 对 `~/.swarm/mods/{name}/` 下的文件重新打包为 tar.gz → 计算 `blake3`
3. 校验 `blake3 == mods.lock 中的 package_hash` — 不匹配 → 文件已被篡改 → `ModIntegrityError`
4. 校验 `Ed25519_verify(author_pubkey, package_hash, signature)` — 不匹配 → 签名无效 → `ModIntegrityError`
5. 验证通过 → 正常加载

> **设计理由**：签名绑定到作者身份而非服主白名单（`trusted_keys`）。服主的信任决策体现在选择从哪个 URL 下载 `.swarm-mod`——若信任该作者，下载其发布的包；若不信任，不安装。这消除了中心化信任列表的维护负担，且与"无中心化市场"的设计一致。

### 5.1a 国际化

模组的 `description` 和配置参数的 `description` 字段支持多语言。每个 `[[mods]]` 条目可在 `[mods.i18n]` 下按语言代码提供本地化描述：

```toml
[[mods]]
name = "empire-upkeep"
description = "Empire upkeep — drones and rooms cost energy per tick"
[mods.i18n.zh]
description = "帝国维护费——drone 和房间每 tick 消耗能量"
[mods.i18n.ja]
description = "帝国維持費——ドローンと部屋が毎tickエネルギーを消費"
```

引擎根据请求的 `Accept-Language` 头或 MCP 客户端的 `locale` 参数返回对应语言。缺少翻译时回退到 `en`，再回退到顶层 `description` 字段。

## 6. World vs Arena 默认值

 规则 | World | Arena |
------|-------|-------|
 `spawn.policy` | RandomRoom | FixedSpawn |
 `code.update_cost` | {} | {} |
 `code.update_window` | 无限制 | 赛前锁定 |
 `code.propagation_speed` | 0 | 0 |
 `drone.env_vars` | true | true |
 `combat.pvp_enabled` | true | true |
 `visibility.fog_of_war` | true | false（全场可见） |

## 7. 可配置类型系统

### 7.1 身体部件类型 (`[[body_part_types]]`)

与资源类型一样，身体部件可通过 world.toml 定义。默认世界提供 8 种基础类型：

```toml
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
cost = { Energy = 80 }

[[body_part_types]]
name = "RangedAttack"
description = "远程攻击——距离 3，每 part 25 伤害"
action = "RangedAttack"
damage_type = "Kinetic"
base_damage = 25
range = 3
cost = { Energy = 100 }

[[body_part_types]]
name = "Heal"
description = "治疗——每 part 恢复 12 HP"
action = "Heal"
base_heal = 12
range = 1
cost = { Energy = 250 }

[[body_part_types]]
name = "Claim"
description = "占领——夺取敌方建筑/Controller"
action = "ClaimController"
range = 1
cost = { Energy = 600 }

[[body_part_types]]
name = "Tough"
description = "韧性——被动 HP 加成，每 part +100 hits_max"
passive = { hits_per_part = 100 }
cost = { Energy = 10 }
```

**字段说明**：

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | 唯一标识符 |
 `description` | string | ✅ | 人类可读描述 |
 `action` | string \| string[] | 条件 | 绑定的 CommandAction。`passive` 类型可省略。数组表示支持多种 action |
 `passive` | map | 条件 | 被动效果配置。与 action 互斥 |
 `damage_type` | string | 条件 | 攻击类型的伤害类型，引用 `[[damage_types]]` 中的 name |
 `base_damage` | u32 | 条件 | 每 part 的基础伤害值。`damage_type` 存在时必需 |
 `base_heal` | u32 | 条件 | 每 part 的基础治疗量。action=Heal 时必需 |
 | `range` | u32 | ✅ | 生效距离。注：CommandAction 的 `in_range()` 校验可覆盖此值（如 Heal body part range=1 但实际命令有效距离=3） |
 | `age_modifier` | i32 | 否 | 对 drone lifespan 的修正（正=延寿，负=折寿）。TOUGH +100，ATTACK -80 等 |
 | `cost` | `{String: u32}` | ✅ | 生成该 body part 的资源消耗，key 为资源名 |

**Body part → CommandAction 绑定**：

- 一个 CommandAction 可被多个 body part 触发（如 `Attack` 可由 `Claw`/`Bite` 触发）
- 新 body part 绑定到已有 CommandAction 时，只需定义不同的 damage_type/base_damage/cost，引擎复用该 action 的校验和应用逻辑
- 引入新 CommandAction 时需在引擎中注册变体 + validate/apply handler + IDL 暴露

**Rhai 模组扩展**：

```rust
actions.add_body_part_type("Leech", #{
    action: "Leech",
    damage_type: "Corrosive",
    base_damage: 15,
    range: 1,
    cost: #{ Energy: 300 },
    special: "heal_self_50pct"
});
```

### 7.2 建筑类型 (`[[structure_types]]`)

与身体部件一样，建筑类型可通过 world.toml 定义。默认 13 种基础类型：

```toml
[[structure_types]]
name = "Spawn"
description = "出生点——生成 drone"
category = "core"
hits = 5000
rcl_required = 1
cost = { Energy = 200 }

[[structure_types]]
name = "Extension"
description = "扩展——存储能量，最多 60 个"
category = "storage"
hits = 1000
rcl_required = 2
max_per_room = 60
cost = { Energy = 50 }

[[structure_types]]
name = "Tower"
description = "防御塔——自动攻击射程内敌方"
category = "defense"
hits = 3000
rcl_required = 3
attack = { damage = 50, damage_type = "Kinetic", range = 5, cooldown = 10 }
cost = { Energy = 200 }

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
cost = { Energy = 300 }

[[structure_types]]
name = "Extractor"
description = "萃取器——从资源点采集矿物"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 800 }

[[structure_types]]
name = "Lab"
description = "实验室——化学反应/资源合成"
category = "production"
hits = 5000
rcl_required = 6
cost = { Energy = 1000 }

[[structure_types]]
name = "Terminal"
description = "终端——市场交易接口"
category = "logistics"
hits = 3000
rcl_required = 5
cost = { Energy = 500 }

[[structure_types]]
name = "Observer"
description = "观察者——扩展视野范围"
category = "intel"
hits = 500
rcl_required = 5
sight_range = 10
cost = { Energy = 300 }

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
maintenance = { Energy = 10 }
repair_capacity = 10
repair_range = 1
repair_aging = 5
cost = { Energy = 5000 }
```

**字段说明**：

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | 唯一标识符 |
 `description` | string | ✅ | 人类可读描述 |
 `category` | enum | ✅ | `core` / `storage` / `defense` / `production` / `logistics` / `intel` |
 `hits` | u32 | ✅ | 最大 HP |
 `rcl_required` | u8 | ✅ | 需要的最低 RCL 等级（1-8） |
 `max_per_room` | u32 | 否 | 每房间最大数量 |
 `capacity` | u32 | 否 | 资源存储容量 |
 `attack` | map | 否 | 自动攻击 `{damage, damage_type, range, cooldown}` |
 `sight_range` | u32 | 否 | 提供的额外视野范围 |
 | `cost` | `{String: u32}` | ✅ | 建造成本 |

### 7.3 Controller 升级表 (RCL)

 Controller 是房间的核心建筑，决定可用建筑、维修容量和 drone 上限。通过向 Controller 存入资源升级。

 | Level | 累计 progress | 解锁建筑 | 最大房间 drone | 维修容量 | 维修距离 | 说明 |
 |-------|-------------|---------|---------------|---------|---------|------|
 | 1 | 0 | Spawn | 50 | 5/tick | 1 格 | 初始状态 |
 | 2 | 200 | Extension (5), Road, Container | 100 | 10/tick | 1 格 | 储能起步 |
 | 3 | 400 | Extension (10), Tower, Storage, Depot | 200 | 20/tick | 2 格 | 防御+前线维修 |
 | 4 | 800 | Extension (20), Link | 300 | 30/tick | 2 格 | 能源网络 |
 | 5 | 1,500 | Extension (30), Terminal, Observer | 400 | 40/tick | 3 格 | 市场交易 |
 | 6 | 3,000 | Extension (40), Extractor, Lab, Factory | 500 | 50/tick | 3 格 | 制造系统 |
 | 7 | 6,000 | Extension (50), PowerSpawn | 500 | 60/tick | 4 格 | 晚期产能 |
 | 8 | 12,000 | Extension (60), Nuker | 500 | 80/tick | 5 格 | 终极武器 |

 **升级**: 每 tick 自动将存入的资源转换为 progress。`progress >= progress_total` 时升级。

 **降级**: Controller 失去 owner 超过 `downgrade_timer`（默认 5000 tick）后降一级，progress 重置。

 **维修硬上限**: 多个 Controller 的总 age 回退量不超过每 tick 自然增长的 50%（`max(0, age + 1 - min(0.5, controller_count × 0.5))`），不可完全抵消寿命流逝。

### 7.4 特殊效果类型定义 (`[[special_effects]]`)

与 body_part_types 和 damage_types 一样，特殊效果可通过 world.toml 定义和扩展。每个条目定义一种可由 `[[custom_actions]]` 引用的效果：

```toml
[[special_effects]]
name = "hack"
description = "夺取目标 drone——5 tick 控制锁后转为 Neutral"
handler = "hack"
target = "enemy_drone"
duration = 5
resistance = "Psionic"

[[special_effects]]
name = "drain"
description = "从目标建筑/存储窃取资源"
handler = "drain"
target = "enemy_structure"
duration = 0
resistance = "EMP"

[[special_effects]]
name = "overload"
description = "消耗目标 fuel budget -500k"
handler = "overload"
target = "enemy_player"
duration = 0
resistance = "EMP"

[[special_effects]]
name = "debilitate"
description = "易伤——指定伤害类型抗性×2，持续 50 tick"
handler = "debilitate"
target = "enemy_any"
duration = 50
resistance = "Corrosive"

[[special_effects]]
name = "disrupt"
description = "打断目标持续动作，不造成 HP 伤害"
handler = "disrupt"
target = "enemy_drone"
duration = 0
resistance = "Sonic"

[[special_effects]]
name = "fortify"
description = "护盾+净化——所有抗性×0.5，清除负面状态"
handler = "fortify"
target = "self_or_ally"
duration = 100

[[special_effects]]
name = "leech"
description = "吸血——造成伤害的 50% 治疗自身"
handler = "leech"
target = "enemy_any"
duration = 0
resistance = "Corrosive"

[[special_effects]]
name = "fabricate"
description = "转化敌方 drone 为己方建筑"
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
description = "随机重排目标下 tick 指令执行顺序"
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

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | 唯一标识符，被 `[[custom_actions]].special_effect` 引用 |
 `description` | string | ✅ | 人类可读描述 |
 `handler` | string | ✅ | 引擎内置处理器。内置：`hack`, `drain`, `overload`, `debilitate`, `disrupt`, `fortify`, `leech`, `fabricate`, `heal_self`, `scramble_commands`, `convert_to_structure` |
 `target` | enum | ✅ | 目标类型：`enemy_drone`, `enemy_structure`, `enemy_player`, `enemy_any`, `self`, `ally`, `self_or_ally`, `any` |
 `duration` | u32 | ✅ | 持续 tick 数（0 = 即时） |
 `resistance` | string | 否 | 目标抗性检查，引用 `[[damage_types]]`。无此字段 = 不检查抗性 |

**注册流程**：

```
1. world.toml 声明 [[special_effects]] → 引擎解析注册到 SpecialEffectRegistry
2. [[custom_actions]] 通过 special_effect = "name" 引用 → 引擎绑定 handler
3. 引擎内置所有 handler — 无需 Rhai 即可使用
4. 服主新增 [[custom_actions]] 引用已有 [[special_effects]] → 无需改 Rust 代码
5. 需全新 handler 时通过 Rhai 模组注册
```

### 7.5 自定义 CommandAction (`[[custom_actions]]`)

当新 body part 需要的动作无法映射到已有 CommandAction 时使用。通过 world.toml 声明 `[[custom_actions]]` 条目并引用 `[[special_effects]]` 中定义的效果类型：

```toml
# 以下 8 个特殊攻击在所有世界中预注册
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

**字段说明**：

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | 唯一标识符 |
 `description` | string | ✅ | 人类可读描述 |
 `damage_type` | string | 否 | 伤害类型，引用 `[[damage_types]]` |
 `base_damage` | u32 | 否 | 基础伤害值 |
 `range` | u32 | ✅ | 生效距离 |
 `special_effect` | string | 否 | 特殊效果标识符，引用 `[[special_effects]]` 中定义的 name |
 `special_param` | float | 否 | 特殊效果参数 |
 `cooldown` | u32 | 否 | 冷却时间（tick） |
 `cost` | `{String: u32}` | 否 | 每次使用消耗（body part spawn 成本在 `[[body_part_types]]` 中独立定义） |

**Rhai handler 注册**（全新效果，TOML 无法表达时）：

```rust
actions.register_action_handler("MindControl", |entity, target, params| {
    actions.set_entity_flag(target, "mind_controlled", true);
    actions.schedule_flag_removal(target, "mind_controlled", 50);
});
```

### 7.6 伤害类型 (`[[damage_types]]`)

伤害类型和抗性体系是**世界规则的一部分**——像资源类型一样可扩展：

```toml
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
```

**字段说明**：

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | 唯一标识符 |
 `description` | string | ✅ | 人类可读描述 |
 `default_resistance` | float | ✅ | 默认抗性倍率（1.0 = 无减免） |

**抗性机制**：两层叠加——组件抗性 × 属性抗性 = 最终倍率。

```toml
[resistances.Tough]
Kinetic = 0.5     # Tough 对动能减半
Sonic = 0.5       # 减震

[resistances.Structure]
EMP = 2.0         # 建筑弱电磁
Corrosive = 1.5   # 建筑怕腐蚀
```

**免疫**：Rhai 模组通过 `actions.set_entity_flag(id, "immune_Thermal", true)` 赋予免疫（倍率 = 0）。

**模组扩展**：

```rust
actions.add_damage_type("Fire", 1.0);
actions.set_resistance("Tough", "Fire", 0.3);
actions.set_attribute(entity_id, "Flaming", true);
```

### 7.7 Body part 伤害绑定

 Body Part | 伤害类型 | 基础伤害 | 说明 |
-----------|---------|---------|------|
 Attack | Kinetic | 30 | 近战，距离 1，低成本高伤害 |
 RangedAttack | Kinetic | 25 | 远程，距离 3，射程优势 |
 Tower（建筑） | Kinetic | 50 | 自动攻击 |
 Heal | — | 12 | 治疗量 |

### 7.8 特殊攻击方式

所有特殊攻击通过 `[[special_effects]]` + `[[custom_actions]]` 可配置注册。

 攻击 | body part | 效果 | 冷却 | 消耗 | 抗性 |
------|----------|------|------|------|------|
 Hack | Claim | 夺取 drone 转 Neutral | 200 tick | 1000E | Psionic |
 Drain | Carry+Work | 窃取资源，每 tick transfer | 50 tick | 200E/tick | EMP |
 Overload | RangedAttack | 目标 fuel -500k | 200 tick | 300E | EMP |
 Debilitate | Work | 指定伤害类型抗性 ×2, 50 tick | 150 tick | 200E | Corrosive |
 Disrupt | Attack | 打断目标动作 | 50 tick | 100E | Sonic |
 Fortify | Tough | 护盾 ×0.5 + 清除负面状态 | 300 tick | 400E | — |

**通用规则**：
- 特殊攻击与 HP 伤害互斥——同一 body part 同一 tick 只能执行一种
- 持续型攻击在 drone 移动或被 Disrupt 时中断
- 所有特殊攻击受 `damage_multiplier` 世界规则影响

## 8. 模组结构 (mod.toml)

每个模组仓库根目录下的 `mod.toml` 是模组的声明式元数据——描述身份、依赖、兼容性和可配置参数。

### 8.1 完整示例

```toml
# mod.toml — 模组元数据与可配置参数声明

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

### 8.2 字段说明

#### [meta]

 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一标识符，在 world.toml `[[mods]].name` 中引用 |
| `version` | string | ✅ | 语义化版本，git tag 必须匹配 |
| `description` | string | ✅ | 人类可读描述 |
| `author` | string | ✅ | 作者标识 |
| `license` | string | ✅ | 开源许可证（MIT/Apache-2.0 等） |

#### [dependencies]

声明此模组依赖的其他模组。引擎启动时解析依赖图：

- 每个条目为 `"<mod_name>" = "<version_req>"`，version_req 语法兼容 semver
- 依赖解析在引擎启动时完成——缺失依赖 → 世界启动失败
- 循环依赖 → 启动失败
- 依赖的配置参数可通过 `deps.<mod_name>.<param>` 访问

#### [compatibility]

声明模组对引擎和 ABI 的版本要求：

 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `engine` | string | ✅ | 支持的引擎版本范围（semver），如 `">=0.8, <1.0"` |
| `swarm_abi` | u32 | ✅ | 最低 ABI 版本。引擎 ABI 版本 >= 此值 → 兼容 |

引擎启动时校验：
- `engine` 不匹配 → 警告，模组仍加载（允许服主自行承担风险）
- `swarm_abi` 不满足 → **拒绝加载**（ABI 不兼容必然导致 WASM 崩溃）

#### conflicts

与此模组互斥的模组名列表。引擎启动时若检测到同世界启用了冲突模组，**拒绝启动**并列出冲突对。

#### [config]

模组可配置参数的声明式定义。每项为一个 `TOML 内联表`：

 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `type` | string | ✅ | `u32` / `u64` / `f64` / `fixed<u32,N>` / `bool` / `string` / `enum` / `[u32]` |
| `default` | 对应 type | ✅ | 默认值 |
| `min` / `max` | 对应 type | 否 | 范围约束 |
| `values` | string[] | enum 时必需 | 枚举可选值 |
| `description` | string | ✅ | 人类可读描述 |

服主在 world.toml 的 `[[mods]].config` 中覆盖这些值。引擎启动时将配置注入 Rhai 脚本的全局变量。

### 8.3 多语言描述

`[meta.description]` 和每个 config 参数的 `description` 支持多语言：

```toml
[meta.description_i18n]
zh = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大。维护费不足时效率下降。"
en = "Empire upkeep — more drones and rooms cost more per tick. Shortfall degrades efficiency."
ja = "帝国維持費——ドローンと部屋が多いほど毎 tick のコストが増加。不足時は効率低下。"

[config.onshortfall.description_i18n]
zh = "资源不足时的处理方式：degrade=效率下降, damage=建筑受损, despawn=单位消亡"
en = "Behavior on resource shortfall: degrade=slow, damage=hurt buildings, despawn=lose units"
```

引擎根据请求的 `Accept-Language` 头或 MCP 客户端的 `locale` 参数返回对应语言。缺少翻译时回退到 `en`，再回退到顶层 `description` 字段。

## 9. 配置校验

```rust
fn validate_config(config: &WorldConfig) -> Result<(), Vec<String>> {
    let mut errors = vec![];

    if config.tick_interval_ms < 1000 { errors.push("tick_interval_ms too short"); }
    if config.code.propagation_speed > 0 && config.code.propagation_speed > 100 {
        errors.push("propagation_speed too high");
    }
    if config.drone.memory_size > 65536 {
        errors.push("memory_size exceeds 64KB");
    }
    if config.combat.damage_multiplier < 1 {
        errors.push("damage_multiplier must be positive");
    }

    if errors.is_empty() { Ok(()) } else { Err(errors) }
}
```

## 10. 与核心引擎的边界

核心引擎**不知道规则的存在**。规则 System 是外挂的：

```
核心引擎职责:
  - Tick 调度 (Collect → Execute → Broadcast)
  - Command 校验与执行
  - ECS 基础 Systems (移动、采集、战斗、死亡)
  - 确定性保证
  - 持久化

规则 System 职责:
  - 在执行前后附加逻辑
  - 不修改核心引擎代码
  - 按配置启用/禁用
```

规则 System 只能：
1. 在 Command 执行**前**拦截（如代码传播检查）
2. 在 Command 执行**后**补充（如手动控制追加）
3. 修改 ECS 资源/组件（如传播系统修改 CodeVersion）
4. 绝不可绕过 Command 校验管线

---
