# Security Review — DeepSeek V4 Pro (Round 4)

**Verdict**: APPROVE_WITH_RESERVATIONS — 6 Freeze Blocker + 1 Gap 已闭合，10 项遗留问题（0 Critical / 5 High / 5 Medium）

**评审范围**: DESIGN.md + P0-1 至 P0-9 全部
**焦点**: C1-C3 闭合验证 / Fuel Refund 安全模型 / P0-9 Source Gate 矩阵完整性 / IDL runtime enforcement

---

## 一、C1-C3 闭合验证

### C1: Fuel Refund 安全模型 → **已闭合 ✅**

R3 要求三项，P0-2 §7 全部满足：

| R3 要求 | 当前状态 | 位置 |
|---------|---------|------|
| 退还时序 (tick 内 vs tick 间) | tick N 被拒 → credit 记入 `next_tick_fuel_credit`，tick N+1 生效，禁止同 tick 放大 | P0-2 §7.2 |
| 退还上限 (绝对值 + 比例) | 每人每 tick 退还不超过 `MAX_FUEL × 10%` (1M fuel)；退还不超过 `MAX_FUEL × 1.1` 总量 | P0-2 §7.3 |
| 滥用检测 (连续失败率 >80%) | 退还率 >80% 连续 3 tick → 触发 throttle (budget × 0.5) | P0-2 §7.3 |

**剩余 remark** (见下方 Concern H1)：throttle 后无恢复路径定义。

### C2: IDL Runtime Enforcement → **已闭合 ✅**

| R3 要求 | 当前状态 | 位置 |
|---------|---------|------|
| 启动时校验 | 通过 CI 强制执行：`cargo run -- gen-api` → `git diff --exit-code`，CI 失败阻断 merge | P0-8 §4 |
| 白名单自动生成 | IDL → Rust `Command` enum + `host function stubs` 自动生成，手写不允许 | P0-8 §3 |
| WASM module import 校验 | `validate_module()` 检查 imports 只在 `ALLOWED_HOST_FUNCTIONS` 白名单内 | P0-4 §2.4 |

**评估**: 非 runtime 检查而是 build-time + CI 强制执行——等价于 runtime enforcement，因为错误的 build 无法通过 CI 进入生产。组合 `gen-api + git diff --exit-code + ALLOWED_HOST_FUNCTIONS` 形成闭合链。

**剩余 remark** (见下方 Concern M1)：P0-4 §8 仍列有 mutating host functions 的 fuel 成本，已与该文档 §3.3 矛盾。

### C3: Rhai Action Validation → **已闭合 ✅**

| R3 要求 | 当前状态 | 位置 |
|---------|---------|------|
| 安全边界 | Rhai API 仅 5 个 actions：deduct_resource / award_resource / modify_entity / emit_event / log。禁止 IO/网络/时钟/随机 | DESIGN §8.7 |
| Capability 模型 | AST 10K/tick、actions 100/tick、迭代 3000 项、墙钟 100ms/tick。超限 10 tick 自动禁用 | DESIGN §8.7 |
| Source Gate 归位 | RuleMod 作为独立 source 纳入 P0-9，有明确 capability/budget 约束 | P0-9 §2.1 |

**剩余 remark** (见下方 Concern H4)：P0-9 §2.3 中 RuleMod 的能力约束与 Rhai API 实际能力不一致。

---

## 二、Fuel Refund 安全模型深度审视

### 整体评价：健壮

三层防护设计合理：
1. **时序隔离**（tick N → N+1）消除同 tick 放大
2. **双上限**（绝对值 10% + 总量 1.1×）防止单 tick 溢出
3. **行为检测**（连续 3 tick >80% → throttle）对抗系统性 abuse

特别肯定「同源重复失败仅首次退 50%」——精确针对「10 架 drone 同时采同一枯竭 Source」的 abuse 场景。

### 发现的缺口

**H1 — Throttle 恢复路径缺失** (High)

P0-2 §7.3 定义触发条件但未定义恢复条件。玩家被 throttle 后如何回到正常 budget？选项：
- 连续 N tick 退还率 < X% → 自动恢复
- 仅手动 admin 解除
- 永不过期（过于严厉）

推荐：连续 5 tick 退还率 < 20% 自动恢复至 `MAX_FUEL × 0.8`，再 5 tick → 完全恢复。写入 P0-2 §7.3。

**H2 — IDL refund_policy 未映射到具体 RejectionReason** (High)

P0-8 IDL 定义：
```yaml
refund_policy:
  contention_lost: 0.5    # SourceEmpty, TileOccupied, TargetFull
  self_invalid: 0.0
```

P0-2 §7.1 枚举了具体 refund 规则（SourceEmpty→50%, TileOccupied→50%, TargetFull→50%, 其余 0%）。

两处一致但 IDL 的注释列举不完整：`contention_lost` 注释说三个 rejection reason，但 P0-2 恰好也是这三个。问题是——未来新增 rejection reason 时，开发者在 IDL 中该把它归入 `contention_lost` 还是 `self_invalid`？IDL 缺少明确的归类规则。

推荐：在 P0-8 `refund_policy` 下增加 `contention_lost_reasons: [SourceEmpty, TileOccupied, TargetFull]` 显式列表，令归类无歧义。

---

## 三、P0-9 Source Gate 矩阵完整性

### 整体评价：显著改善

R3 时 P0-9 缺失 9 个 source。当前版本覆盖 12 sources：WASM / MCP_Deploy / MCP_Query / Admin / Replay / TestHarness / Tutorial / Deploy / Rollback / RuleMod / Simulate / DryRun。

矩阵维度完整：source × (auth_context / gameplay / audit / rate_limit / visibility / budget) + source × (写入世界 / 读写全局存储 / 部署代码 / 查询世界 / 触发战斗)。

### 发现的缺口

**H3 — Source Gate §4 管线未覆盖全部 12 sources** (High)

P0-9 §4 校验管线图只显式列出 WASM 和 MCP_Deploy：
```
│  Source Gate     │  ← 检查 source 是否允许提交 gameplay 指令
│  WASM → pass    │
│  MCP_Deploy →   │    ← 拒绝（MCP 不能提交 gameplay 指令）
```

但 Section 4 未说明 Admin / Tutorial / RuleMod / TestHarness 通过 Source Gate 的行为。Admin 的 gameplay 允许是特殊路径还是也走 Source Gate？Tutorial 的 `⚠️ 仅教程世界` 在 Source Gate 中如何体现？

推荐：Source Gate 逻辑扩展为全矩阵决策表——12 source × (gameplay? / deploy? / query?) 三联判定。

**H4 — RuleMod 能力约束与 Rhai API 不一致** (High)

P0-9 §2.3：
```
| RuleMod | ⚠️ deduct/award/emit_event | ❌ | ❌ | ❌ | ❌ |
```
→ 查询世界: ❌

但 DESIGN §8.7 Rhai API 明确允许：
```rust
state.players()          → Iterator<Player>
player.drones()          → Iterator<Drone>
player.rooms()           → Iterator<Room>
```

这是**查询世界状态**。P0-9 标注为 ❌ 是错误的。RuleMod 需要 query 才能决策 deduct 多少。正确标注应为 `✅ (规则作用域)`。

同时 P0-9 说 RuleMod 写入世界仅 `deduct/award/emit_event`，但 DESIGN §8.7 Rhai API 包含 `actions.modify_entity(entity_id, property, value)`——这是扩展性写入。如果 Phase 1 开放此 API，P0-9 需更新。建议此时明确约束：`modify_entity` 仅限修改非 gameplay-critical 属性（如 cosmetic 标记），或直接移除该 API 直至有明确的 use case。

**H5 — Source Gate 缺少 Deploy source 的认证机制** (High)

P0-9 §2.2 新增 `Deploy` source："代码部署管线（非 MCP 入口）"，auth_context = `player_id`。但 `MCP_Deploy` 有 `player_id + token scope`，`Deploy` 只有 `player_id`。区分两者的认证机制是什么？如果 Web UI 上传 WASM 和 MCP swarm_deploy 走同一后端路径，如何区分 source？

推荐：明确 `Deploy` 与 `MCP_Deploy` 的区分机制——通过网关注入 `source` 字段（Web UI → source=Deploy, MCP → source=MCP_Deploy），并在 P0-9 §2.2 表中注明。

**M1 — Tutorial source 与 `world.mode` 的绑定** (Medium)

P0-9 §2.4 说 Tutorial 指令仅可在 `world.mode = "tutorial"` 的世界中接受。但 World/Arena 差异表（§7）显示 Tutorial 在 Arena 中为 ❌。这是正确的。但 DESIGN §8.7 提到 tutorial 世界独立运行。需要明确：tutorial 世界是否也走完整 Tick 引擎 + FDB 持久化？还是轻量独立实例？如果是后者，Source Gate 在不同部署形态下的行为需区分。

---

## 四、IDL Runtime Enforcement

### 整体评价：CI-enforced，build-time 等价 runtime

P0-8 §4 的 `gen-api + git diff --exit-code` 在 CI 中确保任何手写 Command 或 host function 签名会被阻断。这是正确的工程实践。

### 发现的缺口

**M2 — P0-4 §8 Host Function 成本表仍包含 mutating functions** (Medium)

P0-4 §3.3 明确禁止 `host_move`、`host_harvest`、`host_transfer`、`host_build`、`host_attack`、`host_heal` 作为 host function 暴露。但 §8 成本表仍列出它们的 fuel 成本（1,000 ~ 20,000）。这是 R3 FB-6 (deferred model 一致性) 未彻底清理的残余。

应删除 §8 表中除 `host_get_terrain`、`host_get_objects_in_range`、`host_path_find`、`host_get_world_config`、`host_get_world_rules` 外的所有行，或将这些旧行标记为 `[REMOVED — use JSON command]`。

**M3 — Snapshot JSON 注入 WASM tick() 缺乏转义保证** (Medium)

P0-3 §6.2 限制名称字符集为 `[a-zA-Z0-9 _-]`，标注 `untrusted`。但快照 JSON 由引擎序列化后写入 WASM 线性内存——如果引擎在 JSON 序列化时未显式转义用户字符串，理论上玩家可通过精心构造的名称（尽管受限于该字符集）导致 tick() 解析快照时行为异常。

当前字符集足够安全（不含 `"` `\` `{` `}` 等 JSON 特殊字符），但规范中应添加一行："引擎必须使用 JSON 序列化库（serde_json）的默认转义行为序列化所有用户提供字符串，不依赖字符集白名单做安全假设。"

**M4 — `swarm_validate_plan` 不在 MCP 工具列表中但在 P0-6 中被引用** (Medium)

P0-6 §3.1 列出 `swarm_validate_plan` 作为 MCP 工具，但 P0-3 MCP 工具表中无此工具。R3 FB-5 决议说 "改为 snapshot-bound non-authoritative dry-run，或删除"。当前看来已被删除但 P0-6 未更新。如果确认删除，从 P0-6 §3.1 移除。

**M5 — Global storage transfer 运输中状态的攻击面** (Medium)

DESIGN §8.4 说 transfer 期间资源处于"运输中"状态——"可被敌方巡逻 drone 拦截（需 PvP 启用）"。这是一个有趣的 PvP 机制，但拦截的具体实现未定义。如果实现不当，可能成为 griefing 向量：对手可无限拦截你的补给线。

这更多是 gameplay balance 而非安全，但在 Phase 6 战斗系统实现前应明确：拦截是否需要战斗结算？拦截方是否需要特定 body part？被拦截的资源是销毁还是被掠夺？

---

## 五、Strengths（架构安全亮点）

1. **WasSandboxExecutor 唯一执行器** — AI/人类同走 WASM 沙箱，天然公平。MCP 不直接操作游戏实体。这是整个设计中最强的安全决策。

2. **Deferred Command Model** — `tick() → JSON` 延迟模型使所有 mutating 操作经过引擎统一校验，无法绕过。P0-4 §3 与 DESIGN §8.5 一致。

3. **单管线校验** — 所有入口走同一 `Source Gate → Validation → Apply` 路径，P0-2 §1 明确 "无绕过"。

4. **单函数可见性** — `is_visible_to(entity, player_id, tick)` 统一所有输出面的可见性过滤。P0-5 §5 缓存机制防止不同输出面间的泄露。

5. **Fuel Refund 三层防护** — 时序隔离 + 双上限 + 行为检测，设计完整。同源重复失败去重规则尤其精确。

6. **OS 级进程隔离** — seccomp + cgroup v2 + 无网络 ns + 只读 rootfs。WASM 逃逸后仍被 OS 沙箱限制。P0-4 §4。

7. **确定性合同** — 固定 PRNG (ChaCha12)、固定 Hash (Blake3)、IndexMap、禁 f64、ECS `.chain()`。P0-8 §8.8 / DESIGN §8.8 充分覆盖。

8. **不可信字段标注** — 所有玩家原创字符串标 `untrusted + source_player`，防止 AI agent 被 prompt 注入。P0-3 §6.2。

9. **Tick Failure Semantics** — 完整失败模式矩阵 (P0-1 §6)，含降级模式、回放协议、NATS fallback。

10. **全局存储反制机制** — 累进税 + 隐匿性 + 运输时间，三项反制防止富有玩家垄断。DESIGN §8.4。

---

## 六、Remaining Concerns（遗留问题）

### High (5)

| ID | 问题 | 位置 | 建议 |
|----|------|------|------|
| H1 | Fuel Refund throttle 恢复路径缺失 | P0-2 §7.3 | 定义自动恢复条件：连续 5 tick <20% → 逐步恢复 |
| H2 | IDL refund_policy 未显式映射 RejectionReason | P0-8 §2 | 增列 `contention_lost_reasons` 显式列表 |
| H3 | Source Gate §4 管线仅覆盖 WASM/MCP_Deploy | P0-9 §4 | 扩展为全 12 source 决策表 |
| H4 | RuleMod 能力约束与 Rhai API 不一致 — P0-9 标记为无法查询世界但 API 允许 state.players() | P0-9 §2.3 | 修正为允许查询（规则作用域），评估 modify_entity 是否保留 |
| H5 | Deploy 与 MCP_Deploy 的认证区分机制未定义 | P0-9 §2.2 | 明确网关注入 source 字段的机制 |

### Medium (5)

| ID | 问题 | 位置 | 建议 |
|----|------|------|------|
| M1 | Tutorial world 是否走完整引擎栈未定义 | P0-9 §2.4 | 明确 tutorial 部署形态 |
| M2 | P0-4 §8 仍列 mutating host function 燃料成本 | P0-4 §8 | 删除或标记为 [REMOVED] |
| M3 | Snapshot JSON 注入缺乏序列化转义保证 | P0-3 §6 | 添加强制 serde 转义声明 |
| M4 | `swarm_validate_plan` 残留引用 | P0-6 §3.1 | 移除或对齐 P0-3 |
| M5 | 运输中资源的拦截机制未定义 | DESIGN §8.4 | Phase 6 前明确拦截语义 |

---

## 七、Fresh Ideas

### FI-1: Source Gate 编译期强制执行 ★★★

当前 Source Gate 是运行时检查（P0-9 §4）。建议将 source × capability 矩阵编译为 match 语句，Rust 编译器保证穷尽性——新增 source 而不更新矩阵 → 编译错误。比运行时 403 更强。

```rust
match command.source {
    Source::WASM => { /* gameplay: allow, deploy: deny */ }
    Source::MCP_Deploy => { /* gameplay: deny, deploy: allow */ }
    // 新增 Source::NewThing → 编译错误：non-exhaustive match
}
```

### FI-2: Fuel Refund 可审计性证明 ★★☆

当前 refund 记录在 TickTrace（P0-2 §7.4）。建议对外发布每 tick 的 refund Merkle proof，让玩家可以独立验证引擎是否正确计算 refund。这对竞技公平性（尤其是 Arena）有重大意义，防止引擎作弊偏袒特定玩家。

### FI-3: WASM Host Function 白名单的二进制签名 ★★☆

P0-4 §2.4 的 `ALLOWED_HOST_FUNCTIONS` 是代码级常量。建议在 WASM 模块部署时，引擎计算 `hash(allowed_host_functions_signatures)` 并存储在模块元数据中。回放时验证该 hash 与当前引擎一致——防止 wasmtime 版本升级导致 host function ABI 变化时静默破坏回放兼容性。

### FI-4: 本地模拟的 Sanboxing 一致性 ★☆☆

P0-6 §3.3 提到 `swarm sim` 本地模拟。本地模拟可能不在 seccomp/cgroup 下运行（用户体验考量）。建议 `swarm sim` 默认开启轻量 sandbox（至少 wasmtime fuel metering + memory limit），并提供 `--unsafe` flag 给高级用户关闭。防止玩家在本地开发时依赖沙箱外的能力（如更大内存），部署到服务器后因沙箱限制而失败。

---

*Reviewer: rev-dsv4-security (DeepSeek V4 Pro)*
*Date: 2026-06-14*
*R3 baseline: /data/swarm/docs/reviews/r3-rev-dsv4-security.md*
*R3 Speaker: /data/swarm/docs/reviews/R3-SPEAKER-VERDICT.md*
