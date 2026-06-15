# World Rules Engine — 世界规则配置规范

> 详见 DESIGN §8

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
market_requires_terminal = true

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
- Rhai 脚本**不能**绕过 Command Validation Pipeline（见 P0-2 §1）
- Rhai 脚本**不能**直接写入 ECS 组件——只能通过 `actions.*` API
- Rhai 脚本**不能**访问其他玩家的私有数据
- Buffer apply 阶段由引擎核心在 FDB 事务中执行，保证确定性

**进程隔离模式**（默认配置）：Rhai engine 运行于独立 sandbox 进程，通过 IPC 与核心引擎通信。Sandbox 进程受以下加固：
- **cgroup 限制**: CPU 配额与内存上限（默认 256MB），超限进程被 OOM killer 终止
- **seccomp 加固**: 仅允许 `read/write/sendmsg/recvmsg` 等 IPC 必需的系统调用，禁止 `fork/exec/open/socket` 等
- 模组崩溃或恶意行为不影响核心引擎进程——该模组本 tick 的 actions 全部丢弃，其他模组正常执行

服主可通过 `world.toml` 切换为进程内模式（`[rhai] isolation = "inprocess"`），性能优先但需信任所有模组来源。

**模组签名机制**：每个 `.rhai` 文件附带 `.sig` 文件（Ed25519 签名），引擎启动时验签：

```
empire-upkeep/
├── mod.toml
├── init.rhai
├── init.rhai.sig           # Ed25519 签名（对 init.rhai 的 SHA-256 摘要签名）
├── tick_start.rhai
├── tick_start.rhai.sig
├── tick_end.rhai
└── tick_end.rhai.sig
```

- 签名由模组开发者使用 `swarm mod sign` 生成
- 服主可配置信任的公钥列表（`world.toml` 中 `[rhai] trusted_keys = [...]`）
- 引擎启动时验签：未签名或签名无效的 `.rhai` 文件**拒绝加载**，记录安全审计日志
- `mod.toml` 也需签名（`mod.toml.sig`），防止配置篡改

#### 模组签名

模组签名确保只有经过认证的模组代码能在世界中执行。签名流程：

```
开发者侧:
  1. 编写模组（.rhai 文件 + mod.toml）
  2. swarm mod sign ./my-mod --key ~/.swarm/keys/mod-author.key
     → 为每个 .rhai 文件和 mod.toml 生成对应的 .sig 文件

服主侧:
  1. 安装模组: swarm mod install my-mod
  2. 添加信任: swarm mod trust my-mod --key <author_pubkey>
     或 world.toml 中配置:
     [rhai]
     trusted_keys = [
       "kagurazaka:ed25519:abc123...",
       "community:ed25519:def456..."
     ]
  3. 引擎启动时自动验签——未经信任密钥签名的模组拒绝加载
```

**签名验证流程**（引擎侧）：

1. 加载模组时，对每个 `.rhai` 文件计算 SHA-256 摘要
2. 读取对应的 `.sig` 文件，使用声明方公钥验证 Ed25519 签名
3. 公钥必须在 `trusted_keys` 白名单中
4. 验证通过 → 正常加载；验证失败 → 拒绝加载 + 记录 `SecurityEvent::ModSignatureInvalid`
5. `.sig` 文件缺失视为未签名 → 拒绝加载（无"允许未签名"的宽松模式）

> **设计理由**: 无"允许未签名"模式——防止服主疏忽导致恶意模组注入。开发调试时使用 `swarm dev sign` 生成临时开发密钥签名。

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

## 7. 可配置类型系统

### 9.1 身体部件类型 (`[[body_part_types]]`)

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

### 6.2 建筑类型 (`[[structure_types]]`)

与身体部件一样，建筑类型可通过 world.toml 定义。默认 12 种基础类型：

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

 ### 9.2a Controller 升级表 (RCL)

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

 ### 9.3 特殊效果类型定义 (`[[special_effects]]`)

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

### 6.4 自定义 CommandAction (`[[custom_actions]]`)

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

### 6.5 伤害类型 (`[[damage_types]]`)

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

### 6.6 Body part 伤害绑定

 Body Part | 伤害类型 | 基础伤害 | 说明 |
-----------|---------|---------|------|
 Attack | Kinetic | 30 | 近战，距离 1，低成本高伤害 |
 RangedAttack | Kinetic | 25 | 远程，距离 3，射程优势 |
 Tower（建筑） | Kinetic | 50 | 自动攻击 |
 Heal | — | 12 | 治疗量 |

### 6.7 特殊攻击方式

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
