# P0-7: World Rules Engine — 世界规则配置规范

> **状态**: Phase 1 设计基础 | **关联**: DESIGN.md §8

## 1. 定位

Swarm 不是「一个游戏」，是「游戏引擎平台」。每个世界实例有独立的规则集，由服主通过 `world.toml` 配置。引擎根据配置动态注册 ECS System。

## 2. 配置 Schema

```toml
# world.toml

[world]
name = "World of Swarm"
mode = "persistent"               # persistent | arena
tick_interval_ms = 3000           # tick 间隔（默认 3000）
max_players = 500                 # 最大玩家数

[spawn]
policy = "RandomRoom"             # RandomRoom | ManualSelect | FixedSpawn | Inherit
respawn = "NewRoom"               # NewRoom | SameRoom | Spectate | Ban
cooldown = 0                      # 加入后等待 tick 数

[code]
update_cost = {}                  # 部署消耗资源，如 { Energy = 500 }
update_cooldown = 0               # 两次部署最小间隔 (tick)
update_window = { every = 0, duration = 0 }  # 0 = 无限制
propagation_speed = 0             # 0 = 全局即时
propagation_source = "Spawn"      # Spawn | Controller | AnyDrone
max_wasm_size = 5242880           # 5MB

[drone]
manual_control = false            # 允许手动指令？
manual_control_limit = 0          # 每 tick 最大手动指令数
env_vars = true                   # 允许 drone 环境变量？
memory_size = 1024                # 每 drone 最大存储 (bytes)
max_body_parts = 50               # 最大身体部件数
max_drones_per_player = 500       # 单玩家最大 drone 数

[resources]
source_regeneration_rate = 1.0    # 资源再生速率倍率
build_cost_multiplier = 1.0       # 建筑成本倍率
drone_decay_rate = 1.0            # drone 衰减倍率

[combat]
pvp_enabled = true                # 允许 PvP？
friendly_fire = false             # 允许攻击友军？
damage_multiplier = 1.0           # 伤害倍率

[visibility]
fog_of_war = true                 # 启用 fog of war？
observer_range = 10               # Observer 建筑视野
tower_range_powered = 6           # 充能 Tower 视野
controller_vision = 1             # Controller 视野
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
        // 基础系统始终注册
        app.add_systems(Update, (
            build_system,
            harvest_system,
            regeneration_system,
            movement_system,
            combat_system,
            decay_system,
            death_system,
            spawn_system,
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
            app.add_systems(Update, code_propagation_system.before(movement_system));
        }

        // === Drone 控制 ===
        if self.drone.manual_control {
            app.add_systems(Update, manual_control_system.after(combat_system));
        }
        if self.drone.env_vars {
            app.add_systems(Update, drone_env_var_system);
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

### 手动控制

```rust
/// 当 manual_control = true 时，玩家可对指定 drone 发直接指令
fn manual_control_system(
    config: Res<WorldConfig>,
    mut manual_commands: ResMut<ManualCommandQueue>,
    mut drones: Query<(&Drone, &Owner)>,
) {
    let limit = config.drone.manual_control_limit;
    for (player_id, commands) in manual_commands.drain_by_player() {
        let mut count = 0;
        for cmd in commands {
            if count >= limit { break; }
            // 手动指令跳过 WASM 输出，直接进入 Command 队列
            if let Ok((drone, owner)) = drones.get(cmd.object_id) {
                if owner.0 == player_id {
                    command_queue.push(cmd);
                    count += 1;
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
    drone: { manual_control: boolean; env_vars: boolean; memory_size: number };
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
```

## 6. World vs Arena 默认值

| 规则 | World | Arena |
|------|-------|-------|
| `spawn.policy` | RandomRoom | FixedSpawn |
| `code.update_cost` | {} | {} |
| `code.update_window` | 无限制 | 赛前锁定 |
| `code.propagation_speed` | 0 | 0 |
| `drone.manual_control` | false | false |
| `drone.env_vars` | true | true |
| `combat.pvp_enabled` | true | true |
| `visibility.fog_of_war` | true | false（全场可见） |

## 7. 配置校验

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
    if config.combat.damage_multiplier < 0.0 {
        errors.push("damage_multiplier must be positive");
    }

    if errors.is_empty() { Ok(()) } else { Err(errors) }
}
```

## 8. 与核心引擎的边界

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
