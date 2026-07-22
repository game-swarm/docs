# World Rules Engine — 世界规则配置规范

> 详见 design/gameplay.md

## 1. 定位

Swarm 不是「一个游戏」，是「游戏引擎平台」。规则模组是**Bevy Plugin 静态编译 + 声明式配置**——确定、可审计、可组合。

```
玩家代码:  WASM → 控制 drone     (不可信 → sandbox)
规则模组:  signed Plugin → fixed hooks/typed buffers (编译进 Engine → 服主声明启用)
引擎核心:  Rust → 确定性模拟      (不可变)
```

每个部署通过 `mods.lock` 启用并锁定已编译进 Engine 的模组版本、来源、hash 与签名；`world.toml [mods.<plugin_id>]` 提供严格 typed gameplay 参数，缺省字段使用 versioned design-profile 默认值。模组通过 fixed plugin hooks、typed intent buffers、World Action Manifest 和 ActionRegistry 接入引擎；不得注册 gameplay ECS system、改变 schedule 或绕过 Command Validation Pipeline。

## 2. 配置 Schema

```toml
# world.toml

[world]
name = "World of Swarm"
mode = "persistent"               # persistent | arena | tutorial
tick_interval_ms = 3000
hint_level = "competitive"        # competitive | practice | training；客户端不可覆盖
tutorial_recycle_refund_full_ticks = 500  # Tutorial profile；其他模式忽略

[sharding]
shard_size = { width = 50, height = 50 }       # 固定 protocol geometry
shard_cap = { max_active_players = 500 }
routing = "fixed-grid-v1"
deployed_shards = [{ shard_id = "0:0", origin_room = [0, 0] }]

[spawn]
policy = "RandomRoom"
respawn_policy = "NewRoom"           # 默认复活策略 (NewRoom | OriginalRoom)
# respawn = "NewRoom"                # [Deprecated] serde 别名，仅用于后向兼容
cooldown = 0

[code]
update_cost = {}
update_cooldown = 5
update_window = { every = 0, duration = 0 }
propagation_speed = 0
propagation_source = "Spawn"

# ═════════════════════════════════════
# Vanilla 资源类型
# ═════════════════════════════════════

[[resource_types]]
name = "Energy"
display_name = "能量"
category = "energy"
starting_amount = 5000
max_storage = 100000
decay_rate_ppm = 0
tradeable = true

# 各动作资源消耗（键名来自 resource_types.name）
[actions.costs]
# SpawnCost 来自 body_part_types.cost；BuildCost 来自 structure_types.cost。
body_part.Move = { Energy = 50 }
body_part.Work = { Energy = 100 }
body_part.Attack = { Energy = 80 }
body_part.RangedAttack = { Energy = 150 }
body_part.Heal = { Energy = 250 }
# code_update 默认免费；付费部署世界可显式覆盖，例如：
# code_update = { Energy = 500 }

# 资源点类型
[[source_types]]
name = "EnergyField"
produces = { Energy = 1 }
capacity = 3000
regeneration = 300

# ═════════════════════════════════════

[drone]
lifespan = 1500                 # drone 基础存活 tick 数
min_lifespan = 100              # body modifiers 后的硬下限
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
global_storage_capacity = 1000000

# 物流配置
global_storage_enabled = true
transfer_to_global_fee_bp = 100
global_deposit_delay = 10
transfer_from_global_fee_bp = 100
global_withdraw_delay = 100
build_cost_burn_fee_bp = 500

[combat]
pvp_enabled = true
friendly_fire = false
damage_multiplier = 10000           # fixed<u32,4> = 1.0
repair_hp_per_work_part = 5          # u32, > 0; max HP restored per active Work part
repair_energy_per_hp = 1             # u32, > 0; Vanilla Energy charged per accepted HP

[visibility]
fog_of_war = true
player_view = "drone"               # human display only
public_spectate = false
spectate_delay = 100
replay_privacy = "private"

[retention]
rich_artifact_retention_ticks = 864000
keyframe_acceleration_retention_ticks = 5184000
keyframe_backup_copies = 2

# mods.lock controls enable/version/source/hash/signature.
# world.toml [mods.<plugin_id>] carries strict typed gameplay parameters only.
# Startup applies design-profile defaults, validates schema, then records resolved_config_hash.

[mods.fog-of-war]
design_profile = "World"            # Tutorial | World | Arena | plugin-defined profile
fog_of_war = true

[mods.special-attacks]
design_profile = "World"
special_attacks_enabled = true

```

`mods.lock` 只控制插件启用、版本、来源、hash 与签名；所有特殊 gameplay 参数必须是 engine-owned `world.toml` 字段或严格 typed 的 `[mods.<plugin_id>]` 参数。启动时按 design profile 填充默认值，拒绝未知键/错误类型，并把 resolved config hash 写入 `world_config_hash`。

`[combat].repair_hp_per_work_part` 与 `[combat].repair_energy_per_hp` 都是 required-positive `u32` typed values；缺省时使用 Vanilla defaults `5`/`1`，显式 `0`、负数、溢出或错误类型必须在启动时 fail closed。默认填充后的 resolved values 进入 replay-critical `world_config_hash`。

Vanilla/Standard 默认资源集合只有 `Energy`。`Crystal`/`Gas`、矿物、多资源 build cost 或多资源 action cost 属于 advanced/modded world 示例，必须在对应 mod 的 `[[resource_types]]`、`[[source_types]]` 与 action cost schema 中显式声明。

```toml
# advanced/modded world example — not Vanilla
[[resource_types]]
name = "Crystal"
display_name = "水晶矿"
category = "mineral"
starting_amount = 0
max_storage = 50000
decay_rate_ppm = 1000
tradeable = true

[[source_types]]
name = "CrystalDeposit"
produces = { Crystal = 1 }
capacity = 2000
regeneration = 10

[actions.costs]
spawn = { Energy = 200, Crystal = 50 }
build.Tower = { Energy = 100, Crystal = 25 }
body_part.Attack = { Energy = 80, Crystal = 20 }
body_part.Heal = { Energy = 250, Crystal = 100 }
```

## 3. ECS Plugin 配置边界

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
    /// 固定 schedule 已由 System Manifest 注册；配置只能注入 typed inputs。
    pub fn configure_fixed_schedule_inputs(&self, app: &mut App) {
        app.insert_resource(ResourceRegistry::from_config(self));
        app.insert_resource(ResolvedRuleConfig::from_typed_world_config(self));
        app.insert_resource(ActionRegistry::from_manifest_and_config(self));
        app.insert_resource(PluginHookBuffers::from_declared_hooks(self));
        app.insert_resource(VisibilityMode::from_config(&self.visibility));
    }
}
```

Plugin/config 不得调用 `add_systems` 增加或重排 gameplay schedule。可选行为通过固定 S01-S29 schedule slots，以及独立的 A01 ActionRegistry dispatch hook，使用 handler registries、typed buffers 与 enable flags 实现。S01-S29 进入 `system_manifest_hash`；A01/custom handlers 进入 `world_action_manifest_hash`。

> **— ECS Entity Iteration Determinism**: Bevy ECS 不保证 archetype/table 内部存储的遍历顺序。引擎在所有遍历中必须显式排序（按 `entity_id` 字典序），确保相同世界状态 → 相同遍历顺序 → 相同输出。CI 增加 `randomized-entity-iteration` test mode：通过 feature flag 随机化 Bevy 内部存储顺序，运行确定性 replay 场景并断言 `state_checksum` 一致。此测试不改变生产行为，仅验证排序假设未被隐式依赖打破。

## 4. 固定 Schedule Hook 示例

### 代码传播速度

```rust
/// 固定 code-propagation hook：只读 snapshot，写 typed intent。
fn code_propagation_hook(
    snapshot: &HookSnapshot,
    config: &WorldConfig,
    out: &mut CodePropagationIntentBuffer,
) {
    for drone in snapshot.drones_sorted_by_entity_id() {
        let delay = canonical_propagation_delay(drone, snapshot, config.code.propagation_speed);
        out.push(CodePropagationIntent { drone_id: drone.id, delay });
    }
}
```

### 内存维护费

```rust
/// 固定 upkeep hook：不直接改资源或 memory。
fn memory_upkeep_hook(
    snapshot: &HookSnapshot,
    config: &WorldConfig,
    ledger: &mut ResourceLedgerBuffer,
    effects: &mut MemoryEffectIntentBuffer,
) {
    for player in snapshot.players_sorted_by_id() {
        let charge = canonical_memory_upkeep(player, &config.drone.memory_upkeep_cost);
        ledger.push(charge.resource_debit);
        if charge.shortfall {
            effects.push(MemoryEffectIntent::TruncateToAffordable { player_id: player.id });
        }
    }
}
```

上述 buffers 由固定 schedule slots 的 committer 按 canonical key 应用；hook 不持有 `Query<&mut ...>`/`ResMut` gameplay access。

## 5. WASM 侧 API

```rust
// host function: 读取世界配置
fn host_get_world_config(key_ptr: i32, key_len: i32, out_ptr: i32, out_len: i32) -> i32;
```

```typescript
// TypeScript SDK
interface WorldConfig {
    spawn: { policy: string; respawn_policy: string; cooldown: number };
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

## 5.1 Bevy Plugin 静态规则模型

World rules are defined via Bevy Plugins, statically compiled into the Engine binary. See design/engine.md §3 and design/tech-choices.md §3.

## 6. World vs Arena 默认值

 规则 | Tutorial | World | Arena |
------|----------|-------|-------|
 `spawn.policy` | RandomRoom | RandomRoom | FixedSpawn |
 `code.update_cost` | {} | {} | {} |
 `code.update_window` | 无限制 | 无限制 | 赛前锁定 |
 `code.propagation_speed` | 0 | 0 | 0 |
 `drone.env_vars` | true | true | true |
 `combat.pvp_enabled` | false | true | true |
 `visibility.fog_of_war` | false | true | true（参与者使用 drone fog-of-war；观众/回放可延迟全图） |

## 7. 可配置类型系统

### 7.1 身体部件类型（`[[body_part_types]]`）

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
cost = { Energy = 150 }

[[body_part_types]]
name = "Heal"
description = "治疗——每 part 恢复 12 HP"
action = "Heal"
base_heal = 12
range = 1
cost = { Energy = 250 }

[[body_part_types]]
name = "Claim"
description = "占领——夺取无主或敌方 Controller"
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
 `action` | string \| string[] | 条件 | 绑定的 ActionRegistry action。`passive` 类型可省略。数组表示支持多种 action |
 `passive` | map | 条件 | 被动效果配置。与 action 互斥 |
 `damage_type` | string | 条件 | 攻击类型的伤害类型，引用 `[[damage_types]]` 中的 name |
 `base_damage` | u32 | 条件 | 每 part 的基础伤害值。`damage_type` 存在时必需 |
 `base_heal` | u32 | 条件 | 每 part 的基础治疗量。action=Heal 时必需 |
 | `range` | u32 | ✅ | 生效距离。ActionRegistry 的 validator 可覆盖此值（如 body part 默认 range 与 action range 不同） |
 | `age_modifier` | i32 | 否 | 对 drone lifespan 的修正（正=延寿，负=折寿）。TOUGH +100，ATTACK -80 等 |
 | `cost` | `{String: u32}` | ✅ | 生成该 body part 的资源消耗，key 为资源名 |

**Body part → ActionRegistry 绑定**：

- 一个 ActionRegistry action 可被多个 body part 触发（如 `Attack` 可由 `Claw`/`Bite` 触发）
- 新 body part 绑定到已有 action 时，只需定义不同的 damage_type/base_damage/cost，引擎复用该 action 的校验和应用逻辑
- 引入新 combat/effect action 时需在 ActionRegistry 注册 schema + validate/apply handler；内部 IDL 继续使用通用 `CommandAction::Action { action_type, payload }`

**Typed body-part config 扩展**：

```toml
[[body_part_types]]
name = "Leech"
action = "Leech"
damage_type = "Kinetic"
base_damage = 15
range = 1
cost = { Energy = 300 }
```

启动时由 typed schema validator 构造 immutable `BodyPartRegistry`；Plugin 不得通过 `resource_mut` 在运行期增改 registry。需要自定义行为时，ActionRegistry handler 仍只能写 fixed hook intent buffer。

### 7.2 建筑类型（`[[structure_types]]`）

与身体部件一样，建筑类型可通过 world.toml 定义。默认世界提供 `design/gameplay.md` 定义的 13 个 core structure types；本文件与 economy IDL 下沉相同成本。`Road`、`Wall`、`Rampart`、`Container` 为可选结构类型，只有在 `world.toml optional_structure_types` 显式列出时注册；默认值为空数组。

```toml
optional_structure_types = []
# optional_structure_types = ["Road", "Wall", "Rampart", "Container"]

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
cost = { Energy = 1200 }

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
cost = { Energy = 5000 }

[[structure_types]]
name = "Depot"
description = "前线维护节点——消耗资源为附近 drone 降低 age；不可转移所有权"
category = "logistics"
hits = 2500
rcl_required = 2
capacity = 50000
maintenance = { Energy = 10 }
repair_capacity = 10
repair_range = 1
repair_aging = 5
cost = { Energy = 600 }
```

Optional structure catalogue (registered only when named by `optional_structure_types`):

```toml
[[structure_types]]
name = "Road"
description = "道路——降低移动疲劳"
category = "logistics"
hits = 500
rcl_required = 2
cost = { Energy = 10 }

[[structure_types]]
name = "Wall"
description = "墙——阻挡移动"
category = "defense"
hits = 10000
rcl_required = 2
cost = { Energy = 50 }

[[structure_types]]
name = "Rampart"
description = "壁垒——保护己方实体"
category = "defense"
hits = 10000
rcl_required = 2
cost = { Energy = 100 }

[[structure_types]]
name = "Container"
description = "容器——小型本地资源存储"
category = "storage"
hits = 2500
rcl_required = 2
capacity = 200000
cost = { Energy = 100 }
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
| 2 | 200 | Extension (5) | 100 | 10/tick | 1 格 | Road/Container 仅在 optional_structure_types 显式启用时可用 |
 | 3 | 400 | Extension (10), Tower, Storage, Depot | 200 | 20/tick | 2 格 | 防御+前线维修 |
 | 4 | 800 | Extension (20), Link | 300 | 30/tick | 2 格 | 能源网络 |
 | 5 | 1,500 | Extension (30), Terminal, Observer | 400 | 40/tick | 3 格 | 跨世界身份同步/日志交换 |
 | 6 | 3,000 | Extension (40), Extractor, Lab, Factory | 500 | 50/tick | 3 格 | 制造系统 |
 | 7 | 6,000 | Extension (50), PowerSpawn | 500 | 60/tick | 4 格 | 晚期产能 |
 | 8 | 12,000 | Extension (60), Nuker | 500 | 80/tick | 5 格 | 终极武器 |

 **升级**: 每 tick 按 `controller_upgrade_energy_per_progress = 1` 将存入的 Energy 转换为 progress（1 Energy = 1 progress，整数 floor）。`progress >= progress_total` 时升级。

 **降级**: Controller 失去 owner 超过 `downgrade_timer`（默认 5000 tick）后降一级，progress 重置。

 **维修约束**: age repair 不存在额外全局 cap；维修能力只受物理范围、每设施容量、队列和 Depot 本地资源约束。权威模型见 design/engine.md §3.4.5 与 specs/core/resource-ledger.md §2.4。

### 7.4 特殊效果注册边界

Vanilla 8 个 special action 的保留名称、wire action identity、handler kind 与 intent/committer ownership 由 `design/gameplay.md` 固定，并通过 ActionRegistry manifest 下沉；不得覆盖这些名称或替换 handler 语义。`enabled`、body parts、damage type/resistance、cost、cooldown、range、channel time、effect magnitude 与 counterplay 参数必须由 strict typed `world.toml [mods.special-attacks.actions.<Name>]` schema 提供，Vanilla profile 填充本设计默认值；resolved values 进入 `world_config_hash`。Plugin 只能注册非保留 action/effect 名称；handler 只能写预定义 intent buffer，由固定 schedule committer 应用。

### 7.5 自定义 Action（signed Plugin World Action Manifest）

Vanilla `Attack`/`RangedAttack`/`Heal` 与 8 个 special attack 均由 ActionRegistry 预注册；WASM wire `type` 使用具体 action 名称。扩展 action 只能由 `mods.lock` 启用且签名验证通过的 `.swarm-mod` package 在 World Action Manifest 中声明，并由匹配的 compiled Plugin 通过 A01 fixed hook 注册 handler。`world.toml [mods.<plugin_id>]` 只提供 strict typed 参数，不能创建或重绑定 action/effect identity、payload schema 或 handler。Vanilla special action 的 typed `enabled` 与数值参数由 `design/gameplay.md` 的 profile defaults 决定，并下沉到 [special-attack-table.md](../reference/special-attack-table.md)。

```toml
# .swarm-mod/mod.toml: signed package World Action Manifest declaration
[[actions]]
name = "Scramble"
description = "Deterministically scramble target command order through a fixed effect handler"
body_parts = ["Work"]
handler = "scramble_commands"
payload_schema = "schema/actions/scramble.idl.yaml"
config_schema = "schema/actions/scramble-config.toml"

# world.toml: typed parameters only, after mods.lock enables scramble-actions
[mods.scramble-actions.actions.Scramble]
enabled = true
range = 3
cooldown = 100
cost = { Energy = 250 }
special_param_bps = 5000
```

**字段说明**：

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | signed manifest 中的唯一标识符 |
 `description` | string | ✅ | 人类可读描述 |
 `body_parts` | string[] | ✅ | 执行该 action 所需 body part |
 `handler` | string | ✅ | 同一 signed package 中 compiled Plugin 注册的 A01 fixed-hook handler identity |
 `payload_schema` | path | ✅ | closed IDL schema；生成 concrete `ActionPayload` Swarm codec，禁止 JSON/free-form map |
 `config_schema` | path | ✅ | `[mods.<plugin_id>]` 可接受的 strict typed 参数 schema |

**Bevy Plugin handler 注册**（每个 manifest action 必需）：

```rust
pub struct MindControlPlugin;

impl Plugin for MindControlPlugin {
    fn build(&self, app: &mut App) {
        FixedHookInstaller::from_manifest(app).install_action_handler(
            FixedHook::A01ActionDispatch,
            ActionHandlerDeclaration::from_typed_custom_action("MindControl"),
            mind_control_handler,
        );
    }
}

fn mind_control_handler(
    action: &ValidatedAction,
    out: &mut CustomEffectIntentBuffer,
) -> Result<(), ActionError> {
    out.push(CustomEffectIntent::TimedFlag {
        target: action.target,
        flag: "mind_controlled",
        duration: 50,
    });
    Ok(())
}
```

### 7.6 伤害类型（`[[damage_types]]`）

伤害类型和抗性体系是**世界规则的一部分**——像资源类型一样可扩展：

```toml
[[damage_types]]
name = "Kinetic"
description = "动能冲击——碰撞、钝击、爆炸"
default_resistance_bps = 10000

[[damage_types]]
name = "Thermal"
description = "热能——火焰、激光、等离子"
default_resistance_bps = 10000

[[damage_types]]
name = "EMP"
description = "电磁脉冲——电击、过载、电子干扰"
default_resistance_bps = 10000

[[damage_types]]
name = "Sonic"
description = "声波——振动、共振、超声波"
default_resistance_bps = 10000

[[damage_types]]
name = "Corrosive"
description = "腐蚀——酸液、纳米分解、生化"
default_resistance_bps = 10000

[[damage_types]]
name = "Psionic"
description = "心灵——精神攻击、认知干扰、AI 劫持"
default_resistance_bps = 10000
```

**字段说明**：

 字段 | 类型 | 必需 | 说明 |
------|------|------|------|
 `name` | string | ✅ | 唯一标识符 |
 `description` | string | ✅ | 人类可读描述 |
 `default_resistance_bps` | BasisPoints | ✅ | 默认抗性倍率（10000 = 无减免） |

**抗性机制**：两层叠加——组件抗性 × 属性抗性 = 最终倍率。

```toml
[resistances.Tough]
Kinetic = 5000     # Tough 对动能减半
Sonic = 5000       # 减震

[resistances.Structure]
EMP = 20000        # 建筑弱电磁
Corrosive = 15000  # 建筑怕腐蚀
```

**免疫**：Plugin 可注册 typed attribute definition/intent handler（如 `immune_Thermal`），由固定 Status/Attribute committer 写入 ECS flag（倍率 = 0）。Plugin 不得新增 flag-writing system；handler/buffer access 必须进入对应的 `system_manifest_hash` 或 `world_action_manifest_hash`、R/W contract 与 TickTrace audit。

**模组扩展**：

```rust
actions.add_damage_type("Fire", 10000);
actions.set_resistance("Tough", "Fire", 3000);
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

所有 vanilla combat/effect action 通过 ActionRegistry 注册；参数由 `design/gameplay.md` 定义，并下沉到 `specs/reference/special-attack-table.md`。本文只列名称完整性，避免重复定义数值。

| 攻击 | 说明 |
|------|------|
| Hack | special attack，参数见 canonical table |
| Drain | special attack，参数见 canonical table |
| Overload | special attack，参数见 canonical table |
| Debilitate | special attack，参数见 canonical table |
| Disrupt | special attack，参数见 canonical table |
| Fortify | special attack，参数见 canonical table |
| Leech | special attack，参数见 canonical table |
| Fabricate | special attack；Vanilla 成本为纯 Energy，参数见 canonical table |

**通用规则**：
- 特殊攻击与 HP 伤害互斥——同一 body part 同一 tick 只能执行一种
- 持续型攻击在 drone 移动或被 Disrupt 时中断
- `damage_multiplier` 作用于所有 actual HP damage（basic Attack/RangedAttack/Tower 与 special Leech）；不得改变状态命中/持续、healing/self-heal 比率、resource transfer、fuel pressure、channel time 或 counterplay

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
"base-economy" = ">=1.0, <2.0"      # 需要基础经济模组

# 兼容性声明
[compatibility]
engine = ">=0.8, <1.0"              # 支持的引擎版本范围
swarm_abi = 1                        # 最低 ABI 版本

# 冲突声明
conflicts = ["no-upkeep"]            # 与此模组互斥

# 可配置参数——每项在插件配置资源中可用
[config]
drone_cost = { type = "u32", default = 2, min = 0, max = 100, description = "每 drone 每 tick 维护费" }
room_base = { type = "u32", default = 10, min = 0, max = 1000, description = "每房间基础维护费" }
room_superlinear = { type = "fixed<u32,4>", default = 10000, min = 0, max = 1000000, description = "超线性系数（10000 = 1.0）" }
onshortfall = { type = "enum", default = "degrade", values = ["degrade", "damage", "despawn"], description = "资源不足时的处理方式" }
```

### 8.2 字段说明

#### [meta]

 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | ✅ | 唯一 plugin_id；作为 `mods.lock [mods.<plugin_id>]` 与 `world.toml [mods.<plugin_id>]` 的 key |
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
| `type` | string | ✅ | `u32` / `u64` / `i64` / `fixed<u32,N>` / `bool` / `string` / `enum` / `[u32]` |
| `default` | 对应 type | ✅ | 默认值 |
| `min` / `max` | 对应 type | 否 | 范围约束 |
| `values` | string[] | enum 时必需 | 枚举可选值 |
| `description` | string | ✅ | 人类可读描述 |

这些声明形成 plugin typed config schema。`mods.lock` 只控制启用、版本、来源、hash 与签名；运行时参数来自 `world.toml [mods.<plugin_id>]`。启动时拒绝未知 plugin/key、未启用 plugin 的参数、错误类型或越界值；缺省字段使用 versioned design-profile 默认值，resolved config hash 写入 TickTrace。

### 8.3 多语言描述

`[meta.description]` 和每个 config 参数的 `description` 支持多语言：

```toml
[meta.description_i18n]
zh = "帝国规模维护费——drone 和房间越多，每 tick 消耗越大。维护费不足时效率下降。"
en = "Empire upkeep — more drones and rooms cost more per tick. Shortfall reduces drone efficiency."
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
    if config.combat.repair_hp_per_work_part == 0 {
        errors.push("repair_hp_per_work_part must be positive");
    }
    if config.combat.repair_energy_per_hp == 0 {
        errors.push("repair_energy_per_hp must be positive");
    }

    if errors.is_empty() { Ok(()) } else { Err(errors) }
}
```

## 10. 与核心引擎的边界

核心引擎拥有固定 schedule、validation 与 committer；规则/plugin 只提供 typed config、registry handlers 和 hook buffers：

```
核心引擎职责:
  - Tick 调度 (Collect → Execute → Broadcast)
  - Command 校验与执行
  - ECS 基础 Systems (移动、采集、战斗、死亡)
  - 确定性保证
  - 持久化

规则/plugin 职责:
  - 向预定义 S01-S29 schedule hooks 或 A01 ActionRegistry dispatch hook 注册 handler
  - 只读 HookSnapshot，写 typed intent/buffer
  - 按配置启用/禁用 handler，不增删 schedule node
```

规则/plugin 只能：
1. 在 manifest 预定义的 validation/hook slot 读取授权 snapshot
2. 写预定义 typed intent/buffer，由固定 committer 修改 ECS
3. 通过 typed config enable/disable handler
4. 绝不可绕过 Command 校验管线、追加 manual-control command、直接 mutate ECS 或改变 schedule

---
