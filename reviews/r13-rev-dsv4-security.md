# R13 — Security Review (rev-dsv4-security)

**Reviewer**: DeepSeek V4 Pro (Security Direction, Primary)
**Date**: 2026-06-14
**Scope**: DESIGN.md §1–11, tech-choices.md, specs/p0/ (01–09), PLANNER-OUTPUT.md
**Profile**: Tick protocol consistency verification, data flow tracing, race condition detection
**Context**: R13 follows R12. 延续 R12 的安全审计视角：协议一致性 → 数据流追踪 → 竞态条件检测 → 信任边界审计。

---

## Verdict: REQUEST_MAJOR_CHANGES

R12 标记的 3 Critical + 4 High + 4 Medium **全部未修正**。Phase 0 Architecture Freeze 已宣布完成（2026-06-14），但这些设计级安全问题仍在。本轮新增 **2 Critical、3 High、3 Medium**，集中在：特殊攻击系统未定义校验管线、Hack 安全模型自相矛盾、伤害类型体系缺失 IDL 覆盖。

R12→R13 进度：**0 个问题解决。**

---

## R12 Issue Resolution Matrix

| R12 ID | Severity | Description | R13 Status |
|--------|----------|-------------|------------|
| C1 | Critical | RawCommand body 含 `player_id` → auth-confusion / IDOR | ❌ **UNRESOLVED** |
| C2 | Critical | Tick 原子性 — FDB 事务不覆盖 Bevy World + RuleMod + 副作用 | ❌ **UNRESOLVED** |
| C3 | Critical | Rhai RuleMod actions 绕过 Command Validation Pipeline | ❌ **UNRESOLVED** |
| H1 | High | `player_view="full"` 导致 AI MCP 获得超 WASM snapshot 的信息优势 | ❌ **UNRESOLVED** |
| H2 | High | `damage_multiplier` 类型矛盾 — 浮点 vs 定点 | ❌ **UNRESOLVED** |
| H3 | High | Rhai state API 完整世界暴露 — 可见性边界缺口 | ❌ **UNRESOLVED** |
| H4 | High | 全局存储反制机制可被多账户分拆绕过 | ❌ **UNRESOLVED** |
| M1 | Medium | Sandbox fork-per-tick 与编译模块缓存共存 | ❌ **UNRESOLVED** |
| M2 | Medium | TransferToGlobal / TransferFromGlobal 不在 P0-2 校验矩阵 | ❌ **UNRESOLVED** |
| M3 | Medium | 三重命名冲突 — MCP tool / host function / pipeline query | ❌ **UNRESOLVED** |
| M4 | Medium | Tick 放弃时的 COLLECT 数据有效性 | ❌ **UNRESOLVED** |
| I1 | Info | PLANNER-OUTPUT.md 过时内容 | ❌ **UNRESOLVED** |
| I3 | Info | Host fn visibility 修正验证 | ✅ 保留（已修正于 R11→R12） |
| I4 | Info | `sequence` 字段语义未闭合 | ❌ **UNRESOLVED** |

---

## Critical

### C4 (NEW): 6 种特殊攻击方式在 P0-2 Command Validation 和 P0-8 IDL 中完全缺失

**影响范围**: 战斗系统完整性、反作弊基础、实现正确性

DESIGN §8.2 定义了 6 种特殊攻击方式及其详细机制：

```
Hack       — Claim body part, 夺取 drone 控制权, 连续 10 tick 维持
Drain      — Carry+Work, 窃取建筑资源
Overload   — RangedAttack, 消耗目标 fuel budget
Debilitate — Work, 附加易伤状态, 抗性 ×2
Disrupt    — Attack, 打断持续动作
Fortify    — Tough, 自身/友方护盾, 抗性 ×0.5
```

但在 P0 规范层：

| 文档 | Hack | Drain | Overload | Debilitate | Disrupt | Fortify |
|------|------|-------|----------|------------|---------|---------|
| P0-2 §3 (Command Validation) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| P0-8 (IDL commands) | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ |
| P0-9 §2.3 (Source Capability) | — | — | — | — | — | — |

这些操作各自有独特的校验需求，远非现有 11 个 Command 的校验规则可覆盖：

- **Hack**: 需要校验目标 hits < max × 0.15、连续 10 tick 维持、Psionic 抗性计算、Neutral 状态转换
- **Overload**: 需要校验 fuel budget 下限 MAX_FUEL × 0.2、目标 fuel 状态
- **Disrupt**: 需要校验目标当前是否在执行持续动作（哪些动作算"持续"？Drain/Hack 之外还有吗？）
- **Debilitate/Fortify**: 需要校验状态叠加（同一实体可被多个 Debilitate 叠加吗？同一伤害类型重复 Debilitate 如何处理？）

**攻击场景**: 若实现者按 DESIGN 实现这些操作但 P0-2 无对应校验，则：
- 特殊攻击可能被应用到不存在的目标（ObjectNotFound 不检查）
- 可能跨所有权施加 Debilitate/Fortify（无 NotOwner/NotFriendly 检查）
- Hack 可能在没有 Claim body part 的 drone 上执行（无 MissingBodyPart 检查）
- Overload 可能将 fuel 降至 0（下限 2M 无校验执行）

**修复**:
- P0-2 §3 新增 §3.12–3.17 六个特殊攻击的完整校验矩阵
- P0-8 IDL commands 段新增对应六条命令定义
- P0-9 §2.3 Source Capability 矩阵中 WASM 行确认这些操作的能力范围
- 所有校验包含：ownership、body part requirement、cooldown、resistance calculation、state transition rules

---

### C5 (NEW): Hack 命令的 Neutral drone 安全模型自相矛盾

**影响范围**: 所有权模型、WASM 执行语义、整个安全架构

DESIGN §8.2 定义 Hack 的后果：

> 被 Hack 的 drone 转为中立（Neutral），不归任何玩家所有，但仍执行原 owner 部署的 WASM。5 tick 内无法被再次 Hack。

这条定义在 Swarm 的安全模型中制造了一个不可解的矛盾：

**矛盾链**:

```
1. drone.owner = Neutral (0/null)
2. WASM tick(snapshot) 仍被调用，因为 drone 仍在世界中
3. tick() 内产生 Command[]，携带 player_id = 原 owner
4. P0-2 校验: object_id.owner (Neutral) != player_id → NotOwner
5. 所有指令被拒绝
6. 原 owner 的 fuel 被消耗但无一指令执行
7. 或者 — 如果实现者特殊处理 Hack，绕过 NotOwner 检查：
   → Neutral drone 以原 owner 身份继续执行指令
   → Hack 实际上无效
```

**子问题**:

1. **Neutral 的定义是什么？** `owner = 0`？特殊标记？目前未在任何 P0 规范中定义
2. **Neutral drone 的 tick() 如何调用？**
   - 若以原 owner 身份调用 → Hack 无效，drone 行为不变
   - 若以 Neutral 身份调用 → WASM 的 `player.resources`、`snapshot.player_id` 是什么？
3. **Neutral drone 能攻击吗？** P0-2 §3.7 Attack 校验 `target_id.owner != player_id 或为中立敌对` — 这里"中立敌对"的语义未定义
4. **5 tick 冷却** — 是 per-drone 还是 per-attacker？若两个玩家同时对同一 drone Hack？

**修复**:
- 删除 "仍执行原 owner 部署的 WASM" — Neutral drone 不执行任何 WASM，进入 idle 状态
- 或：Neutral drone 执行一个内置的 "idle bot"（不提交指令，仅存在）
- 在 P0-2 中明确定义 Neutral 状态：owner 值、可见性、tick 行为、被攻击规则
- 如果 Neutral drone 保留原 owner WASM，必须在所有 ownership 检查中特殊处理 Neutral 状态

---

## High

### H5 (NEW): 伤害类型与抗性体系不在 P0-8 IDL 类型系统中

**影响范围**: IDL 单一真相来源原则、代码生成完整性、SDK/MCP schema 一致性

DESIGN §8.2 定义了完整的伤害/抗性体系：

- 6 种基础伤害类型: Kinetic, Thermal, EMP, Sonic, Corrosive, Psionic
- 2 层抗性: 组件抗性 (body part × structure) + 属性抗性 (Rh ai 动态赋予)
- 免疫机制: `set_entity_flag(entity, "immune_Thermal", true)`
- 特殊攻击的伤害类型绑定 (Hack→Psionic, Drain→EMP, etc.)

P0-8 IDL 定义了完整的类型体系：

```yaml
types: PlayerId, RoomId, ObjectId, Tick, ResourceName, ...
enums: Direction, BodyPart, StructureType, RejectionReason, ...
commands: Move, MoveTo, Harvest, Transfer, Withdraw, Build, Repair, Attack, ...
```

但 **DamageType 枚举、Resistance 类型、Damage calculation 函数签名** 完全不在 IDL 中。这是 P0-8 声明 "game_api.idl 是单一真相来源" 的直接违反——伤害体系有两个真相来源（DESIGN §8.2 和实现代码），而 IDL 不知道其中任何一个。

**影响**:
- SDK 代码生成时缺少 DamageType 类型 → TS/Rust SDK 的 autocomplete 不包含伤害相关 API
- MCP schema 不包含伤害类型 → AI 玩家无法通过 `swarm_get_schema` 了解伤害体系
- 实现中的 DamageType 可能散落在多处，与 IDL 生成代码不一致

**修复**:
- P0-8 IDL 新增 `DamageType` 枚举（6 基础类型 + 扩展接口）
- P0-8 IDL 新增 `Resistance` 类型定义
- Command 定义中 Attack/RangedAttack 增加 `damage_type` 字段
- 特殊攻击命令（C4 修复后）绑定各自伤害类型

---

### H6 (NEW): Controller 占领 drone 续期机制绕过 lifespan 且无校验定义

**影响范围**: Drone 生命周期完整性、经济平衡

DESIGN §8.2:

> 占领新 Controller 房间时，该玩家最老的 50% drone 的 age 重置为 0。冷却: 同一玩家 500 tick 内只触发一次。

这个机制作为 `drone_lifespan = 1500` 的唯一绕过路径，存在以下未定义的安全边界：

1. **"占领"的判定时机**: 是 Controller.owner 从 None→PlayerId 的那一刻？还是升级完成的那一刻？如果是 owner 变更，在 PvP 中两个玩家轮流占领/放弃同一 Controller 会怎样？
2. **"最老的 50% drone"**: 排序基准是什么？按 age 降序取前 50%？如果玩家有奇数个 drone，rounding 如何处理？
3. **跨房间**: 重置的 drone 必须在新占领的房间吗？还是全局任意位置的 drone？
4. **500 tick 冷却**: 如果 500 tick 内占领了 3 个新 Controller，只触发第一次？还是全部延迟？
5. **无 P0 规范覆盖**: 此机制仅出现在 DESIGN §8.2 表格中，不在任何 P0 规范中。P0-2 无续期校验，P0-7 无配置项，P0-8 IDL 无对应操作。

**攻击场景**: 两名玩家串通，轮流占领/放弃 Controller，保持双方 drone 永不因 age 死亡。

**修复**:
- 在 P0-2 中定义 `ControllerCapture` 事件的处理规则和校验
- 明确 drone selection 算法（确定性排序 + 取前 N）
- P0-7 world.toml 中增加 `drone_renewal_on_capture: bool` 配置开关
- 冷却机制明确为 per-player (非 per-controller)

---

### H7 (NEW): `swarm_get_docs` / `swarm_get_schema` 无限流 — 无 DoS 防护

**影响范围**: MCP Server 可用性

P0-3 §4.4 标记:

| 工具 | 限流 |
|------|------|
| `swarm_get_schema` | 无限制 |
| `swarm_get_docs` | 无限制 |

P0-3 §5.2 全局限制 "最大并发 MCP 连接 = 1000" 和 "每 IP 连接速率 = 10/秒"，但没有 per-tool per-player 的调用频率限制。

这两个工具返回静态数据，单个调用开销小。但在 500 AI 玩家的生产环境中：

- 每个 AI agent 的典型实现会每 tick 调用一次 (schema + docs) 来刷新对游戏规则的理解
- 500 × 2 = 1000 次/3s = 333 QPS 的额外负载
- 恶意 agent 可在单 tick 内调用 10,000 次 `swarm_get_docs`（因为无限制）
- 虽然返回的是缓存静态数据，但 JSON 序列化 + 网络传输 + MCP server 线程消耗不可忽略

**修复**:
- 为 `swarm_get_docs` 和 `swarm_get_schema` 设置合理限制（如 5/tick per player 或 60/h）
- 或在 MCP server 层实施响应缓存（相同请求返回 304/ETag）
- 至少标注为 "缓存静态数据，限流防滥用"

---

## Medium

### M5 (NEW): Global storage 运输拦截延期至 Phase 6 — 行为不一致窗口

**影响范围**: 经济公平性、PvP 游戏体验

DESIGN §8.2 声明:

> 转换期间资源处于"运输中"状态——可被敌方巡逻 drone 拦截（需 PvP 启用，Phase 6 战斗系统实现）

如果 Phase 1-5 实现了 `TransferToGlobal` / `TransferFromGlobal` 但不实现拦截机制：

- Phase 1-5: 全局存储运输 100% 安全，玩家建立围绕此假设的经济策略
- Phase 6: 突然引入运输拦截，破坏已有策略和玩家信任
- AI 玩家在 Phase 1-5 学到 "运输总是安全的" 后，在 Phase 6 面临策略失效

这不是安全漏洞本身，但是一个**设计契约破坏**——如果不在早期文档中标注运输的最终形态（可被拦截），玩家会在错误假设上构建帝国。

**修复**:
- 在 `TransferToGlobal` / `TransferFromGlobal` 命令的文档/API 描述中标注 "运输可被拦截（Phase 6+）"
- Phase 1-5 实现时保留拦截的接口桩（`TransportInterceptionSystem` 注册为 no-op）
- 或将运输拦截作为 world.toml 可选规则（`transport_interception_enabled`），从 Phase 1 即可配置（默认关）

---

### M6 (NEW): `body_cost` 无最小值校验 — world.toml 可设零成本 spawn

**影响范围**: 经济平衡、世界配置安全

P0-8 IDL 定义了 body_cost 默认值：

```yaml
body_cost:
  Move:         { Energy: 50 }
  Work:         { Energy: 100 }
  ...
```

但 DESIGN §8.2 / P0-7 world.toml 允许覆盖：

```toml
[actions.costs]
body_part.Move = { Energy: 60, Crystal: 10 }
```

P0-7 §7 `validate_config` 不检查 body part 成本的最小值：

```rust
fn validate_config(config: &WorldConfig) -> Result<(), Vec<String>> {
    // 无 body_cost 校验
}
```

服主可以设置 `body_part.Move = {}`（零成本）或所有 body part 成本为 0，允许 spawn 无限 drone。

**修复**:
- P0-7 §7 validate_config 增加 body_cost 总和最小值检查（每个 body part 至少消耗 1 单位任意资源）
- P0-8 IDL 中为 `body_cost` 标注 "world.toml 可覆盖但每 part 消耗 ≥ 1"

---

### M7 (NEW): 伤害体系中 `immune_X` flag 的白名单未穷举

**影响范围**: Rhai 模组权限边界

DESIGN §8.2 定义免疫机制:

> Rhai 模组可通过 `actions.set_entity_flag(entity_id, "immune_Thermal", true)` 赋予免疫

但 P0-7 §4 的 `actions.set_entity_flag` 的说 明是 "设置白名单标记（如 slow/empowered）"——这个白名单的定义在何处？`immune_Thermal` 在白名单中吗？`immune_Kinetic` 呢？`invincible` 呢？

如果没有穷举的白名单，恶意模组可以通过 `set_entity_flag(entity, "godmode", true)` 然后在战斗系统中漏过任何未识别 flag 的伤害计算。

R12 C3（Rhai 绕过校验管线）的修复应包含 `set_entity_flag` 的白名单穷举，但当前设计连白名单的轮廓都没有。

**修复**:
- P0-7 §4 中穷举 `set_entity_flag` 的合法 flag 列表
- Flag 命名规则: `immune_{DamageType}` (其中 DamageType 来自 P0-8 IDL 注册表)、`stunned`、`slow`、`empowered`、`invisible`
- 禁止: 任意字符串 flag、含特殊字符的 flag、长度 > 32 的 flag

---

## Informational

### I6: `body_cost` 默认值跨文档不一致

P0-8 IDL:

```yaml
body_cost:
  Move:         { Energy: 50 }
  Work:         { Energy: 100 }
  Carry:        { Energy: 50 }
  Attack:       { Energy: 80 }
  RangedAttack: { Energy: 150 }
  Heal:         { Energy: 250 }
  Claim:        { Energy: 600 }
  Tough:        { Energy: 10 }
```

DESIGN §8.2 world.toml 示例:

```toml
body_part.Move = { Energy: 50 }
body_part.Work = { Energy: 100 }
body_part.Attack = { Energy: 80, Matter: 20 }
body_part.Heal = { Energy: 250, Matter: 100 }
body_part.Claim = { Energy: 600 }
```

DESIGN 示例中 Attack 额外消耗 Matter:20，Heal 额外消耗 Matter:100，但 IDL 默认值无 Matter。这不是安全漏洞但会在实现时产生混淆——哪个是真实默认值？

### I7: Overload fuel 下限 2M 在头文件中无常量定义

DESIGN §8.2 定义 Overload "不会被叠加至低于 MAX_FUEL × 0.2"（2M fuel），但 P0-4 §6 的资源预算总表只有 "Fuel: 10,000,000" 没有 `MIN_FUEL_AFTER_OVERLOAD` 常量。P0-8 IDL 也没有。常量散落在 DESIGN 叙述中而非 IDL/配置。

### I8: `replay_privacy` 分级缺少 `world` 级别的旁观者过滤实现细节

P0-5 §3.5 spectator 表格中定义了 `replay_privacy` 对旁观者的影响，但 "private 时旁观者仅见地形和公开元数据" 的过滤粒度未定义。地形可见但建筑物呢？Controller 等级是公开元数据（P0-5 §2.6）但在 private replay 中如何区分"公开元数据"和"私有数据"？当前表格按信息类别列出但未给出过滤函数的伪代码。

### I9: 技术选型正面发现（持续追踪）

以下安全决策在 R13 仍保持正确性：

- Wasmtime fuel metering + epoch interruption + fork-per-tick: 纵深防御 ✓
- Blake3 统一哈希/PRNG/MAC: 审计面最小化 ✓
- FoundationDB 严格可序列化: 每 tick 原子提交基础 ✓（但 C2 指出 B evy + RuleMod 不在事务中）
- Ed25519 短期证书 + 服务端签发: 吊销可控 ✓
- Deferred Command Model: 杜绝 WASM 直接 mutating ✓
- Source Gate 单一入口 + 12 来源能力矩阵: 不可绕过 ✓
- Seeded Shuffle: 确定且公平的资源竞争 ✓
- Fuel refund anti-amplification: 防计算预算滥用 ✓
- JSON Schema 输入校验: 全面覆盖 ✓

---

## Data Flow Trace (Updated for R13)

```
COLLECT:
  Bevy World (authoritative) → visibility_filter() → Snapshot JSON → WASM tick()
  WASM tick() → host_*() calls [✅ is_visible_to filtered]
  WASM tick() → Command[] JSON → schema validation [✅ depth/size/type checks]
  ⚠️ WASM tick() → Command[] 仍含 player_id 字段 [❌ C1]
  ⚠️ Command[] 中无 TransferToGlobal/FromGlobal 校验 [❌ M2]
  ⚠️ Command[] 中无 Hack/Drain/Overload/Debilitate/Disrupt/Fortify [❌ NEW C4]

EXECUTE:
  Command[] → seeded_shuffle() [✅ deterministic]
  Command[] → validate against Bevy World [✅ TOCTOU per-command]
  Command[] → apply() in FDB transaction [❌ C2: 不覆盖 Bevy/RuleMod/副作用]
  ❌ RuleMod actions.* → 直接 apply(world)，绕过 Command Validation [❌ C3]
  ❌ FDB commit unknown → 无幂等键 [❌ C2]
  ❌ Hack → Neutral drone → 仍执行原 owner WASM → NotOwner 全部拒绝 [❌ NEW C5]

BROADCAST:
  FDB commit → Dragonfly cache [✅ stale reads documented]
  Dragonfly → NATS → WebSocket [✅ gap detection]

Rhai mod hooks:
  state API → full world access [❌ H3: no visibility filter]
  actions.* → mini-validator → world [❌ C3: bypasses Command Validation Pipeline]
  ⚠️ actions.emit_event → 无可见性标注 [❌ H3]
  ⚠️ actions.set_entity_flag → 白名单未穷举 [❌ NEW M7]

MCP:
  tools → is_visible_to() filter [✅]
  ⚠️ player_view=full → MCP 可超 WASM snapshot [❌ H1]
  ⚠️ swarm_get_docs/schema → 无限流 [❌ NEW H7]
  deploy → WASM module queue → next tick atomic switch [✅]

WASM sandbox:
  ✅ host fn visibility filtering
  ❌ tick() ABI 不安全 [R11-gpt C3]
  ❌ fork-per-tick + module cache = JIT in parent [❌ M1]
  ✅ Wasmtime config 需真实可编译版本验证

Damage system:
  ⚠️ 6 damage types defined in DESIGN §8.2 but absent from P0-8 IDL [❌ NEW H5]
  ⚠️ Special attacks defined in DESIGN §8.2 but absent from P0-2/P0-8 [❌ NEW C4]
  ⚠️ Hack Neutral drone model is contradictory [❌ NEW C5]

Controller / drone lifecycle:
  ⚠️ Drone age reset on Controller capture — no P0 spec coverage [❌ NEW H6]

Economy:
  ⚠️ body_cost no minimum validation in config [❌ NEW M6]
  ⚠️ Global storage transport interception deferred to Phase 6 [❌ NEW M5]
  ⚠️ Multi-account storage tax bypass [❌ H4]
```

---

## Review Summary

| Severity | R12 Count | R13 Count | Δ | Must-Fix Phase |
|----------|-----------|-----------|---|----------------|
| Critical | 3 | 5 | +2 (C4, C5) | Phase 2 |
| High | 4 | 7 | +3 (H5, H6, H7) | Phase 3 |
| Medium | 4 | 7 | +3 (M5, M6, M7) | Phase 4 |
| Informational | 5 | 9 | +4 (I6–I9) | — |

### R12→R13 进展

- **0 个问题解决** — R12 全部 11 个实质性发现仍未修正
- Phase 0 Architecture Freeze 已宣布完成，但 5 个 Critical 未解
- 新增问题集中在 **战斗系统安全模型缺口**: 6 种特殊攻击无校验管线、Hack Neutral 模型自相矛盾、伤害类型体系无 IDL 覆盖
- PLANNER-OUTPUT.md 的错误内容（Phase 1.6/2.2/2.5）至今未删——R11、R12、R13 三轮均指出，实施风险持续累积

### 核心建议

五项 Critical 的修正顺序：

1. **C2 (ExecutionPlan staging)** — 先设计确定性执行的数据结构，这是所有其他修复的基础
2. **C3 (RuleMod 进入 ExecutionPlan)** — 将 Rhai actions 纳入 ExecutionPlan，消除绕过路径
3. **C1 (AuthenticatedCommand 类型)** — 在 ExecutionPlan 中使用 server-injected auth context
4. **C4 (特殊攻击校验矩阵)** — 在 C1 修复后的 Command Validation 框架中增加 6 个特殊攻击
5. **C5 (Hack Neutral 模型)** — 与 C4 的 Hack 校验同步重设计

前三个形成连锁依赖（C2 → C3 → C1），C4 和 C5 可并行进行。建议在 Phase 2 实现前完成全部 5 项 Critical 的规范修正。
