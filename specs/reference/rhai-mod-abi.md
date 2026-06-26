# Rhai RuleMod ABI 合同

> **权威合同**：本文档是 Rhai RuleMod 的可实现 ABI 合同。所有引擎实现者（Rhai engine 嵌入层、hooks dispatcher、capability gate）、模组开发者（`.swarm-mod` 打包与签名）和服主（`world.toml` 授权）必须一致遵守。
> 引擎详细规范见 `specs/core/07-world-rules.md` §5.1-5.1f。

## 1. 执行模型

RuleMod 是**世界规则系统**——通过声明式钩子修改世界参数和行为，不是玩家命令旁路。

```
玩家代码:  WASM → 控制 drone     (不可信 → sandbox)
规则模组:  Rhai → 修改世界规则    (服主声明 → 引擎嵌入)
引擎核心:  Rust → 确定性模拟      (不可变)
```

### 1.1 事务性语义

Rhai 脚本在每 tick 的规则注入阶段执行。所有 `actions.*` 调用**不直接修改世界状态**，而是写入 `RhaiActionBuffer`：

```
Rhai 脚本执行 → RhaiActionBuffer (内存缓存)
    所有 hooks 执行完毕 → 全部成功 → Buffer apply (FDB 事务内)
                       任一失败   → Buffer 丢弃 (世界状态不变)
```

### 1.2 隔离保证

- Rhai **不能绕过** Command Validation Pipeline
- Rhai **默认不能直接写入** ECS 组件——只能通过 `actions.*` API；唯一例外是显式授权的 `direct_ecs_writer` capability，且必须通过 CI unique writer gate
- Rhai **不能访问** 其他玩家的私有数据
- Buffer apply 由引擎核心在 FDB 事务中执行，保证确定性
- RuleMod 不得降级为**玩家级作弊通道**

### 1.3 执行模式

**进程内模式**（唯一生产运行模式）：Rhai engine 在核心引擎进程内执行。不存在 `isolation` 切换选项。

**超时度量**：确定性 AST 节点预算（默认 100,000 AST 节点/模组/tick）。墙钟仅用于运维告警（>2s 触发 WARN），不作为状态决定因素。

## 2. Hook 表面

模组在 `mod.toml` 中声明 `hooks = [...]`，引擎按固定调度顺序调用。

### 2.1 完整 Hook 清单

| Hook | 触发点 | 频率 | 签名 | 返回值 |
|------|--------|:----:|------|--------|
| `on_world_init` | 世界启动（tick 0 前） | 1次 | `fn(world_cfg, mod_cfg)` | void |
| `on_tick_start` | COLLECT 阶段前 | 每 tick | `fn(world_cfg, tick, mod_state)` | void |
| `on_tick_end` | BROADCAST 后 | 每 tick | `fn(world_cfg, tick, events, mod_state)` | void |
| `on_command_validated` | Phase 2a 校验通过后 | 每命令 | `fn(cmd, world_cfg, mod_state) → bool` | `true`=允许, `false`=拒绝 (RejectionReason → ModBlocked) |
| `on_command_applied` | Phase 2a 命令应用成功后 | 每命令 | `fn(cmd, result, world_cfg)` | void |
| `on_spawn` | Phase 2b spawn_system | 每 drone | `fn(drone_id, body, room, mod_state)` | void |
| `on_death` | Phase 2b death_mark_system | 每 drone | `fn(drone_id, cause, killer_id?, mod_state)` | void |
| `on_room_claim` | Controller owner 变更 | 每事件 | `fn(room_id, old_owner, new_owner, mod_state)` | void |
| `on_deploy` | WASM 模块部署成功 | 每部署 | `fn(player_id, module_hash, slot, mod_state)` | void |

### 2.2 Hook 执行调度

```
tick N:
  on_tick_start (所有注册模组)
  → COLLECT → EXECUTE Phase 2a
    → on_command_validated (注册模组, 每命令)
    → on_command_applied (注册模组, 每命令)
  → EXECUTE Phase 2b
    → on_spawn (注册模组, 每 drone)
    → on_death (注册模组, 每 drone)
  → on_room_claim (注册模组, 本 tick 变更的 room)
  → on_deploy (注册模组, 本 tick 的新部署)
  → BROADCAST
  → on_tick_end (所有注册模组)
```

引擎按固定调度顺序调用——`mod.toml` 中声明顺序无关。未声明的 hook 不调用（零开销）。

### 2.3 Hook 注册

```toml
[mod]
name = "empire-upkeep"
version = "1.2.0"
hooks = ["on_tick_start", "on_tick_end", "on_death"]
```

## 3. Helper API

所有 `query.*` 为只读，`actions.*` 为写入（通过 RhaiActionBuffer）。Rhai 只能通过这两个命名空间与世界交互。

### 3.1 查询 Helper

| Helper | 签名 | 返回 | 说明 |
|--------|------|------|------|
| `query.world_config()` | `() → WorldConfig` | 世界配置只读快照 | tick 开始时快照，本 tick 内不变 |
| `query.active_players()` | `() → Array<PlayerId>` | 本 tick 活跃玩家列表 | 有 ≥1 alive drone 或 pending spawn |
| `query.player_drones(player_id)` | `(PlayerId) → Array<EntityId>` | 该玩家所有 alive drone | 不含 death_marked |
| `query.room_state(room_id)` | `(RoomId) → RoomState` | 房间详情 | owner, rcl, structures, controller progress |
| `query.global_resource(name)` | `(string) → u64` | 全局资源池余额 | Energy/Crystal 等全局 pool |
| `query.entity_flag(entity_id, flag)` | `(EntityId, string) → bool` | 实体 flag 值 | 如 `query.entity_flag(id, "immune_Thermal")` |
| `query.tick()` | `() → u64` | 当前 tick 编号 | |
| `query.world_seed_epoch()` | `() → u64` | 当前 seed epoch | 不可见实际 seed |

**性能约束**：
- 单次 `query.*` = 1 AST 节点（计入 100,000 预算）
- `active_players()` 最多 1000 条——超过截断
- `player_drones()` 最多 500 条——超过截断
- RoomState 不含其他玩家私有数据

### 3.2 Actions API

| API | 能力 | 允许范围 | 禁止项 | 审计字段 |
|-----|------|---------|--------|---------|
| `actions.deduct(resource, amount, reason)` | 扣除全局资源 | 全局资源池 | 禁止扣到负数；禁止扣除玩家私有资源 | `mod_id, tick, resource, amount, reason` |
| `actions.award(resource, amount, reason)` | 发放全局资源 | 全局资源池 | 禁止超过 max_award_per_tick | `mod_id, tick, resource, amount, reason` |
| `actions.emit_event(event_type, data)` | 发射世界事件 | 预定义事件类型 | 禁止伪造玩家命令事件 | `mod_id, tick, event_type` |
| `actions.set_world_param(key, value)` | 修改世界参数 | mutable=true 的参数 | 禁止修改 mutable=false 的参数 | `mod_id, tick, key, old_value, new_value` |
| `actions.set_entity_flag(entity_id, flag, value)` | 设置实体 flag | 仅全局实体；flag 在 allowed_flags 白名单中 | 禁止设置玩家 drone flag | `mod_id, tick, entity_id, flag, value` |

## 4. Capability 白名单

扩展能力需在 `mod.toml` 中声明 `required_capabilities`，服主在 `world.toml` 中按模组授权。**默认所有 capability 需显式授权（default-deny）**——不写 `capabilities` 则零授权。仅服主显式列入的 capability 生效。

### 4.1 完整 Capability 清单

| Capability | 风险 | 说明 | 默认授权 |
|-----------|:----:|------|:-------:|
| `spawn_npc` | 🔴 High | 创建 NPC entity | ❌ 需服主显式授权 |
| `modify_terrain` | 🔴 High | 修改地形类型 | ❌ |
| `broadcast_world_event` | 🟡 Medium | 向所有玩家发送世界事件 | ❌ |
| `award_global` | 🟡 Medium | 超 max_award_per_tick 注入资源 | ❌ |
| `tax_resource` | 🟡 Medium | 施加全局资源税率 | ❌ |
| `set_resistance` | 🟡 Medium | 修改实体抗性值 | ❌ |
| `add_body_part_type` | 🟢 Low | 注册新 body part | ❌ |
| `add_structure_type` | 🟢 Low | 注册新建筑类型 | ❌ |
| `add_damage_type` | 🟢 Low | 注册新伤害/抗性类型 | ❌ |
| `register_action_handler` | 🟡 Medium | 注册新 Rhai action handler | ❌ |
| `set_entity_flag` | 🟢 Low | 设置全局实体 flag | ❌ |
| `set_world_param` | 🟢 Low | 修改 mutable=true 参数 | ❌ |
| `direct_ecs_writer` | 🔴 Critical | 直接写入 ECS 组件（绕过 RhaiActionBuffer） | ❌ 需服主显式授权 + CI unique writer gate |

### 4.2 授权语法

```toml
# world.toml
[[mods]]
name = "empire-upkeep"
version = "1.2.0"
capabilities = ["tax_resource", "set_entity_flag"]
```

不写 `capabilities` = 仅授权 `default=true` 的能力（默认安全——最小权限原则）。全部已声明 capability 授权需显式 `capabilities = ["all_declared"]`。未声明 capability 即使授权也不可调用。

### 4.3 Direct ECS Writer Capability（D8 B+）

`direct_ecs_writer` 是高风险 capability，是默认禁止直接写 ECS 规则的显式例外：只有服主授权、manifest 声明通过、且 CI unique writer gate 确认不与核心系统写入冲突时，模组才可绕过 `RhaiActionBuffer` 直接写入声明范围内的 ECS 组件。每个 `direct_ecs_writer` 必须在 `mod.toml` 中声明受影响的组件和资源范围。

#### 声明格式（mod.toml）

```toml
# mod.toml — direct_ecs_writer capability 声明
[[capabilities]]
name = "direct_ecs_writer"
engine_version = ">=0.9, <1.0"     # 引擎版本兼容范围（必填）
abi_version = 1                      # Direct ECS writer ABI 版本（必填）
affected_components = [              # 可写入的 ECS 组件白名单（必填，至少一个）
    "HitPoints",
    "Position",
]
affected_resources = [               # 可修改的资源类型（必填，至少一个）
    "Energy",
]
manifest_hash = "sha256:..."         # 组件/资源集合的完整性 hash（CI 自动生成）
```

#### 授权格式（world.toml）

```toml
# world.toml — 服主显式授权 direct_ecs_writer
[[mods]]
name = "custom-combat-mod"
version = "2.0.0"
capabilities = ["direct_ecs_writer"]
[mods.capability_config.direct_ecs_writer]
allow_components = ["HitPoints"]      # 服主可进一步限制组件范围
allow_resources = ["Energy"]          # 服主可进一步限制资源范围
max_writes_per_tick = 100             # 每 tick 最大写入次数
```

#### CI 校验要求

| # | 校验项 | 说明 |
|---|--------|------|
| 1 | `engine_version` 有效性 | CI 解析 semver 约束，验证当前引擎版本在允许范围内 |
| 2 | `abi_version` 匹配 | Direct writer ABI 版本必须与引擎内置版本匹配；不匹配 → `ModEngineVersionMismatch` |
| 3 | `affected_components` 白名单 | 所有声明的组件名必须在引擎 ECS component registry 中存在；未知组件 → CI reject |
| 4 | `affected_resources` 白名单 | 所有声明的资源名必须在资源注册表中存在；未知资源 → CI reject |
| 5 | Unique writer gate | 同一组件的 direct writer 不得与核心 engine system 的 unique writer 冲突；冲突 → CI reject |
| 6 | `manifest_hash` 完整性 | CI 根据 `affected_components` + `affected_resources` 的排序 JSON 自动计算 hash，与声明值比对 |
| 7 | `manifest_hash` 纳入 TickInputEnvelope | `manifest_hash` 计入 `world_action_manifest_hash`，参与 replay 确定性 |
| 8 | R/W matrix 注册 | Direct writer 的 component set 登记到 `06-phase2b-system-manifest.md` system R/W matrix |
| 9 | 授权检查 | 服主 `world.toml` 中未显式授权 `direct_ecs_writer` → 模组加载时拒绝（capability denied） |
| 10 | 运行时审计 | 每次 direct write 记录 TickTrace audit entry：`(mod_id, tick, component, entity_id, field, old_value, new_value)` |

## 5. 错误传播与降级

### 5.1 错误层次

| 错误类别 | 触发条件 | 本 tick 行为 | 后续 |
|---------|---------|------------|------|
| Action 失败 | 单个 `actions.*` 返回错误 | 跳过该 action，buffer 保留其余 | 无影响 |
| Script 超时 | AST > 100,000 或墙钟 > 2s | 该脚本 buffer 全部丢弃 | 记录 ModTimeout |
| Script panic | Rhai 运行时错误 | 该脚本 buffer 全部丢弃 | 记录 ModPanic |
| 连续失败 | 同模组连续 3 tick panic/timeout | 本 tick buffer 丢弃 | **自动降级**：禁用 1000 tick |
| 安全违规 | 绕过 sandbox | buffer 丢弃 + WARN | **永久禁用**，需服主手动恢复 |
| 完整性失败 | 签名验证失败 | 模组拒绝加载 | ModIntegrityError，启动中止 |

### 5.2 降级通知

```
自动降级 → WARN 日志 + ModDegraded 事件
  { mod_id, event: "degraded", reason: "consecutive_failures", until_tick: N+1000 }
服主可通过 swarm mod enable 提前恢复（需确认修复）
```

降级期间模组 hooks 不调用（零 CPU），`mod.state` 保持不变。恢复时从上次 state 继续。

## 6. 版本策略与兼容性

### 6.1 Semver 语义

| 版本变更 | 含义 | 兼容性 |
|---------|------|:-----:|
| MAJOR (X.0.0) | Breaking: hook 签名变更、actions API 移除/重命名、capability 语义变更 | ❌ 需服主手动迁移 |
| MINOR (0.X.0) | 新增: 新 hook、新 helper、新 capability、新 param | ✅ 向后兼容 |
| PATCH (0.0.X) | 修复: bug fix、性能优化、文档更新 | ✅ 完全兼容 |

### 6.2 Engine 兼容约束

```toml
[mod]
engine = ">=0.8, <1.0"
```

引擎加载时检查约束——不匹配 → `ModEngineVersionMismatch`，拒绝加载。

### 6.3 弃用窗口

- API 弃用需在 `mod.toml` 声明 `deprecations = [{api, since, removal, migration_guide}]`
- 弃用→移除 ≥ 2 个 MINOR 版本
- 弃用期间：WARN 日志（不阻止执行）
- 移除后：调用 → Script panic（正常错误路径）

### 6.4 更新与回滚

| 操作 | 行为 |
|------|------|
| `swarm mod upgrade` | 下一 tick 新版本 hook 生效 |
| `swarm mod downgrade` | 旧版本立即恢复 |

## 7. 模组签名与信任

### 7.1 签名流程

模组作为 `.swarm-mod` tar.gz 归档分发，附带单个 Ed25519 签名：

```
{name}-{version}.swarm-mod          # tar.gz 归档
{name}-{version}.swarm-mod-signature # Ed25519 签名文件
```

签名算法：`blake3(tar.gz归档)` → `Ed25519_sign(author_privkey, package_hash)`

### 7.2 验证流程（引擎侧）

1. 引擎启动时读取 `mods.lock`，获取 `author_pubkey`、`package_hash`、`signature`
2. 对 `~/.swarm/mods/{name}/` 重新打包 → `blake3`
3. 校验 `blake3 == mods.lock.package_hash` — 不匹配 → `ModIntegrityError`
4. 校验 `Ed25519_verify(author_pubkey, package_hash, signature)` — 不匹配 → `ModIntegrityError`
5. 验证通过 → 正常加载

### 7.3 信任模型

- `author_pubkey` 由模组作者在 `mod.toml` `[meta]` 中自行声明
- 服主通过选择从哪个 URL 下载 `.swarm-mod` 来表达信任——下载即信任
- 无中心化 CRL——去中心化信任模型
- 签名验证的是「代码确实来自声明的作者」，而非「作者是否在白名单中」

## 8. 模组文件结构

```
empire-upkeep-1.2.0.swarm-mod       # tar.gz 归档
├── mod.toml                         # 含 [mod] (name/version/hooks/engine) + [meta] (author_pubkey)
├── init.rhai                        # 入口脚本
├── on_tick_start.rhai               # 可选——按 hook 拆分
├── on_tick_end.rhai                 # 可选
├── on_death.rhai                    # 可选
├── helpers/                         # 可选——辅助函数
│   └── utils.rhai
└── MIGRATION.md                     # 跨 MAJOR 升级步骤
```

## 9. 实现清单

实现者必须满足以下合同：

| # | 要求 | 章节 |
|---|------|------|
| 1 | RhaiActionBuffer 事务性语义（全部成功 → apply / 任一失败 → 丢弃） | §1.1 |
| 2 | 9 个 hook 全部支持，固定调度顺序 | §2 |
| 3 | 8 个 query helper 全部可用，遵守性能约束 | §3.1 |
| 4 | 5 个 actions API 全部可用，遵守权限约束 | §3.2 |
| 5 | 12 个 capability 全部可授权，默认值如白名单 | §4 |
| 6 | 6 级错误层次 + 自动降级（连续 3 tick → 1000 tick） | §5 |
| 7 | Semver 引擎兼容检查 + 2 MINOR 弃用窗口 | §6 |
| 8 | Ed25519 签名验证（启动时 + 安装时） | §7 |
| 9 | AST 节点预算 100,000/模组/tick（确定性度量） | §1.3 |
| 10 | 进程内执行模式（唯一），无 isolation 切换 | §1.3 |