# Swarm 安全审计 — Round 3

> **审计人**: Security Reviewer (DeepSeek V4 Pro)
> **审计范围**: DESIGN.md、P0-1 至 P0-9 全部规范
> **审计重点**: 确定性合同安全性、IDL 生成代码防绕过、退款策略防滥用
> **日期**: 2026-06-14

---

## Verdict: REQUEST_MAJOR_CHANGES

核心架构（单一执行器、MCP 非游戏控制器、Command Validation Pipeline、确定性合同）方向正确，安全根基扎实。但存在三项 Critical 问题——退款模型创建系统性滥用向量、IDL 与运行时代码之间缺少防御纵深、Rhai 模组安全边界未定义——必须在 Phase 1 实现前解决。

---

## Critical

### C1 — Fuel Refund Model Creates Systematic Contention Farming

**受影响规范**: P0-2 §7、P0-4 §8

**问题**:

P0-2 §7 定义：`SourceEmpty`、`TileOccupied`、`TargetFull` 退 50% fuel。理由：竞争导致——非玩家过错。

引擎无法区分「真实竞争失败」与「故意制造竞争」。攻击面：

(a) **多账号围攻 (Multi-account Contention Farming)**：主账号 A 的 drone 采集 Source S；傀儡账号 B 的 drone 也 target S。B 明知 S 在 snapshot 中即将被采空，仍提交 harvest → 必然 SourceEmpty → B 获 50% fuel 退还。B 的退还 fuel 可用于额外路径计算、额外状态分析，间接增强 A 的决策能力。若退还作用于当前 tick（见 C1b），则可实现单 tick 内计算放大。

(b) **退还时序未定义**：P0-2 §7 只写「退 50% fuel」，未指定退还作用于当前 tick 还是下一 tick 的 fuel budget。若作用于当前 tick，形成计算放大链——玩家可设计代码故意触发大量竞争失败 → fuel 退还 → 更多计算。若作用于下一 tick，形成 credit accumulation——多 tick 积累退还 credit 后集中爆发。

(c) **无退还上限**：每 tick 最多 100 条指令、1000 次 host function 调用。若全部故意失败（如对空 source 循环 harvest），退还 fuel = 指令数 × 单次成本 × 50%。以 `host_harvest` (5000 fuel × 1000 = 5M fuel) 计，退还 2.5M fuel。这 2.5M 退还 fuel 可用于 pathfinding（10 次上限，10,000+50/tile）和 `get_objects_in_range`（5 次，2000+100/entity），大幅超出正常计算预算。

(d) **"Heads I Win, Tails I Get Half Back" 元博弈**：退款使「喷洒式提交」成为严格占优策略。胜率 p 的 harvest 期望 fuel 成本 = 5000p + 2500(1-p) = 2500 + 2500p。p=0.3 时期望成本仅 3250 fuel——在任何可见 source 上提交 harvest 都是正期望行为。这破坏了「谨慎规划」的设计意图。

**建议修复**:

1. 明确退还作用于下一 tick 的 fuel budget，禁止同 tick 计算放大
2. 设置每人每 tick 退还上限 = MAX_FUEL × 10%（当前为 1M fuel）
3. 限制「连续同一 source 竞争失败」退还——同一 (player, source, rejection_reason) 在同一 tick 内仅首次退还 50%，后续退还 0%
4. 对连续 N tick 竞争失败率 > 阈值的玩家标记审查（ClickHouse `mcp_audit` 已有基础）
5. 在 `P0-2 §7` 中增加退还时序与上限的显式定义

---

### C2 — IDL-to-Engine Consistency: No Runtime Enforcement, CI-Only Gate

**受影响规范**: P0-8 §3–4、P0-4 §2.4

**问题**:

P0-8 §4 定义的 CI 检查——`cargo run -- gen-api; git diff --exit-code`——仅是构建期闸门。运行时**不存在**引擎注册的 host function 集合与 IDL 之间的交叉验证。

攻击路径：

(a) **WASM Import Whitelist Divergence**：P0-4 §2.4 检查模块导入是否在 `ALLOWED_HOST_FUNCTIONS` 白名单中。白名单的维护方式未在 IDL 规范中定义。若开发者直接在引擎中添加 host function 并手工追加白名单，该函数可被 WASM 调用但无 IDL 对应的 Validator 覆盖——即无条件通过 P0-2 校验管线。

(b) **构建管线旁路**：CI 可被 admin override 绕过（紧急热修复场景）。若绕过 CI 的二进制部署到生产环境，引擎与 IDL 之间可永久偏离。运行时无防护。

(c) **回滚窗口**：WASM 模块按 `(module_hash, wasmtime_version)` 缓存（P0-4 §7）。若引擎因回滚使用了旧版 host function 集合，而玩家 WASM 模块是基于新版 host function 编译的——旧引擎可能允许已被新版 IDL 移除的函数调用。

(d) **MCP Tool Schema 不在 IDL 中**：P0-8 的 `game_api.idl` 只定义 `commands:` 和 `host_functions:`。MCP 工具（`swarm_deploy`、`swarm_get_snapshot` 等 15 个，定义于 P0-3）**不在 IDL 覆盖范围内**。IDL 作为「单一真相来源」的原则在 MCP 层面断裂。这意味着 MCP 工具的 schema 可能与其实际行为不一致，且无 CI 强制同步。

**建议修复**:

1. 引擎启动时加载 IDL 的编译期嵌入副本，运行时断言所有注册的 host function 在 IDL 中有对应条目，所有 IDL 定义的 host function 已注册——不匹配则拒绝启动
2. 将 `ALLOWED_HOST_FUNCTIONS` 白名单加入 IDL 代码生成输出，确保 `gen-api` 同时输出白名单
3. 在 `engine/src/generated/` 中加入 `const IDL_CHECKSUM: &str = "blake3-hex..."`，git tag 与 IDL checksum 绑定
4. 将 MCP 工具 schema 纳入 IDL，或创建并行的 `mcp_tools.idl` 受相同 CI 约束
5. 在 `P0-8 §3` 代码生成表中增加 Rust 目标：`src/generated/host_whitelist.rs` 和 `src/generated/idl_checksum.rs`

---

### C3 — Rhai Mod Actions Bypass Command Validation Pipeline

**受影响规范**: DESIGN.md §8.7、P0-7 §4–8

**问题**:

P0-7 §8 声明「绝不可绕过 Command 校验管线」。但 Rhai 模组的 `actions.*` API 直接操作世界状态：

```
actions.deduct_resource(player_id, resource, amount)
actions.award_resource(player_id, resource, amount)
actions.modify_entity(entity_id, property, value)
actions.emit_event(event_type, data)
```

这些操作不经过 P0-2 的 Command Validation Pipeline。`actions.apply(world)` 中的「经校验后写入」在规范中没有具体校验内容。

具体风险：

(a) **无边界校验**：`modify_entity(entity_id, property, value)` 的合法 property 集合、value 范围未定义。一个 buggy 模组可将 `drone.hits` 设为 `u32::MAX`，或将 `controller.level` 越界。

(b) **无权限模型**：模组可以 deduct 任意玩家的任意数量任意资源——不需检查目标玩家是否有足够资源、不需经过 Command 管线中的所有权检查。虽然模组由服主声明安装（信任模型），但模组市场意味着第三方代码。若 `empire-upkeep`（487 安装量）包含隐蔽 bug 或供应链攻击，影响面极大。

(c) **无操作限额**：模组每 tick 可执行多少次 `deduct_resource` / `modify_entity`？无限制。一个死循环或迭代全量玩家的模组即使逻辑正确，也可能造成 tick 超时。

(d) **回放污染**：P0-7 说「所有 `actions` 操作被记录到 TickTrace——可回放、可审计」。但若模组逻辑本身依赖 Rhai 引擎版本或非确定行为（Rhai 的 HashMap 迭代顺序在 1.75 之前非确定），回放可能偏离记录状态，导致确定性合同破裂。

**建议修复**:

1. 定义 Rhai Action Capability System：每个模组声明所需 capability（`resource:deduct`、`entity:modify:hits` 等），引擎在安装时校验声明的 capability 是否 ≤ 模组的 manifest
2. 为 `actions.modify_entity` 定义白名单 property 集合（仅允许 `hits`、`fatigue`、`cooldown`、`energy`），每 property 有合法值域
3. `actions.deduct_resource` 必须校验目标玩家有足够资源——不足时返回错误，模组自行处理
4. 设置每模组每 tick 操作上限（建议 1000 actions/tick）
5. 在 `P0-7 §8` 中显式定义 Action Validation 的完整规则矩阵——与 P0-2 §3 的指令校验矩阵同级详细

---

## High

### H1 — world_seed Confidentiality vs Deterministic Shuffle Predictability

**受影响规范**: P0-1 §3.1、P0-5 §3、DESIGN.md §8.8

P0-1 §3.1 声称 shuffle 顺序「不可预测」。但这依赖于 `world_seed` 保持机密。P0-5 §3 将 `RNG 种子` 和 `world_seed` 列为 Admin-only 隐藏数据——方向正确。

但存在侧信道：玩家可通过多 tick 观察自己的 shuffle 位置（对比提交指令的执行结果），结合已知的 `tick_number`（公开信息），对 Blake3 输出做统计推断。若某玩家拥有多账号（在不同 shuffle 位置），可通过交叉参照推断种子空间。ChaCha12 的 256-bit 密钥空间本身安全，但若 `world_seed` 是低熵来源（如取自 world 创建时间戳），攻击面成立。

建议：明确 `world_seed` 生成方式——使用 `getrandom` 256-bit 作为 Blak3 key，而非 Blak3 input 串联；在 P0-1 中注明 world_seed 的熵要求。

---

### H2 — ResourceRegistry Uses HashMap (Non-Deterministic Iteration)

**受影响规范**: DESIGN.md §8.4、§8.8

DESIGN.md §8.8 明确「HashMap 顺序 → `indexmap`」。但 §8.4 的 `ResourceRegistry` 定义为：

```rust
struct ResourceRegistry {
    types: HashMap<String, ResourceDef>,
    action_costs: ActionCosts,
    source_types: Vec<SourceDef>,
}
```

`types: HashMap<String, ResourceDef>` 若用于 `fn cost()` 的迭代查找，在标准的 `std::collections::HashMap` 下迭代顺序非确定——当两种资源消耗相同时，扣款顺序可能导致不同结果。与确定性合同直接冲突。

建议：将 `HashMap` 替换为 `IndexMap`，确保 §8.8 的原则覆盖所有 `HashMap` 使用。

---

### H3 — Host Function Signature Type Inconsistency (i64 vs u64)

**受影响规范**: DESIGN.md §5、P0-8 §2

P0-8 IDL 定义 `ObjectId: u64`，但 DESIGN.md §5 所有 host function 使用 `object_id: i64`。虽然 WASM 线性内存中 i64/u64 的位模式相同，但在 Rust 侧的校验逻辑中，负的 `object_id` 应被拒绝——当前签名 `i64` 使得负值在类型系统层面合法。

建议：统一 host function 签名为 `u64`（ObjectId）、`u32`（PlayerId、RoomId），在 IDL 代码生成时处理 WASM ABI 的 i32/i64 约束。

---

### H4 — No Per-Player Refund Cap or Abuse Detection

**受影响规范**: P0-2 §7

与 C1 互补。即使退还模型修复，仍需：退还率监控（每玩家每 tick 的退还 fuel / 总消耗 fuel）、退还原因分布告警（SourceEmpty 占比 > 80% 标记）。P0-1 §5 健康指标表中 `command_rejection_rate > 20%` 是整体拒绝率，未按拒绝原因细分。

建议：增加 `refund_abuse_rate` 指标（退还 fuel / 总消耗 fuel > 0.5 触发告警），按拒绝原因分桶。

---

### H5 — Cached WASM Module Poisoning via Version Skew

**受影响规范**: P0-4 §7

WASM 模块按 `(module_hash, wasmtime_version)` 缓存。若玩家部署了一个在旧 wasmtime 下通过校验但在新 wasmtime 下有不同行为的模块（例如依赖未定义行为），升级 wasmtime 后模块行为改变，但模块仍被加载（新 hash 意味着重新编译，但同一二进制在不同 wasmtime 下编译结果不同）。

建议：wasmtime 版本升级时清空模块缓存；保留旧版本 wasmtime 用于回放旧 tick（双版本并存）。

---

## Medium

### M1 — Refund Timing Ambiguity (no explicit next-tick credit model)

P0-2 §7 不指定退还的时序（当前 tick vs 下一 tick fuel pool）。若退还作用于当前 tick，可能被利用为计算放大；若作用于下一 tick，则为 credit accumulation。无论哪种都需要显式建模。已在 C1 中部分覆盖，在此作为独立文档缺陷列出。

---

### M2 — Snapshot String Fields as Injection Vector within Allowed Character Set

P0-3 §6.2 限定名称为 32 字符 `[a-zA-Z0-9 _-]`。在字符集内仍可构造如 `IGNORE_PREVIOUS`、`SYSTEM_OVERRIDE`、`DISREGARD SAFETY` 等字符串。AI SDK 分隔符契约有效，但依赖 SDK 实现正确性。若某 AI agent 使用非官方 SDK（直接调 MCP），prompt injection 风险复归。

建议：官方 SDK 的分隔符模板不接受 `Accept-Language` 覆盖——始终注入英文分隔符；增加 drone name deny-list（`IGNORE`、`SYSTEM`、`DISREGARD`、`OVERRIDE` 等前缀匹配）。

---

### M3 — Pathfinding Computational Cost Not Bounded by Map Complexity

P0-2 §4.3 限制 `path_length ≤ MAX_PATH_LENGTH (100)`、每 tick 10 次。但未限制地图规模与寻路算法复杂度。若恶意构造超大障碍物迷宫（如螺旋形 Wall），A* 在找到路径或确认 NoPath 之前可能展开大量节点——远超 100 步路径的实际计算量。

建议：增加寻路节点展开上限（如 10,000 节点），超出即返回 `NoPath`；在寻路 host function 中显式扣除 fuel（P0-4 §8 已有 10,000 + 50/tile，可增加节点展开的额外扣除）。

---

### M4 — Arena Replay Delayed-Public Window Lack of Rationale

P0-5 §3.5 设 Arena 赛后「延迟 ≥100 tick 才公开」全知回放。但未解释 100 tick 的依据——为什么不是 50 或 500？若同期比赛的玩家可通过观察其他比赛的公开回放获取信息优势（如跨比赛间谍），需更长的延迟或赛后一次性公开。

建议：在规范中增加延迟窗口选择的安全论证（如「同轮次比赛全部结束后公开」），而非硬编码 100 tick。

---

### M5 — Seeded Shuffle Uses concatenation Not Domain-Separated Hash

P0-1 §3.1: `Blake3(tick_number || world_seed)`。若 `tick_number` 和 `world_seed` 均为定长，拼接安全。但规范未明确拼接方式：是 `tick_number.to_le_bytes()` 后拼接还是直接字节拼接？若 world_seed 是可变长字符串，存在 `tick=1, seed="abc"` 与 `tick=12, seed="bc"` 碰撞的可能。

建议：使用 domain-separated hash: `Blake3("swarm-shuffle-v1", tick_number.to_le_bytes(), world_seed)` 并固定 world_seed 为 32 字节。

---

## 总结 — 修复优先级

```
Phase 0 (阻塞 Phase 1 启动):
  C1: Fuel Refund Model → 定义退还时序 + 上限 + 滥用检测
  C2: IDL Runtime Enforcement → 启动时校验 + 白名单自动生成
  C3: Rhai Action Validation → 定义安全边界 + capability 模型

Phase 1 (实现中同步修复):
  H1: world_seed entropy specification
  H2: HashMap → IndexMap
  H3: Host function signature unification
  H4: Refund abuse metrics
  H5: WASM cache version-skew policy

Phase 2 (可延后):
  M1-M5: 文档补全 + 硬编码阈值论证
```

核心架构（WasmSandboxExecutor 唯一执行器、MCP 不直接操作游戏实体、Command Validation Pipeline、
单函数可见性过滤）方向正确且在文档中贯彻一致。这本身就是最强的安全决策——
控制了最大的攻击面。以上发现均属于「正确架构上的硬化工作」。
