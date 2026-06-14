# R5 最终检查 — rev-gpt-security

Reviewer: R5 / Security Reviewer — GPT-5.5
Date: 2026-06-14
Scope:
- `/data/swarm/docs/design/DESIGN.md`
- `/data/swarm/docs/specs/p0/01-tick-protocol-spec.md`
- `/data/swarm/docs/specs/p0/02-command-validation-spec.md`
- `/data/swarm/docs/specs/p0/03-mcp-security-contract.md`
- `/data/swarm/docs/specs/p0/04-wasm-sandbox-baseline.md`
- `/data/swarm/docs/specs/p0/05-unified-visibility-policy.md`
- `/data/swarm/docs/specs/p0/06-mvp-feedback-loop.md`
- `/data/swarm/docs/specs/p0/07-world-rules-engine.md`
- `/data/swarm/docs/specs/p0/08-game-api-idl.md`
- `/data/swarm/docs/specs/p0/09-command-source-model.md`

## Verdict

CONDITIONAL_APPROVE

Phase 0 设计已经把 R5 关心的主要安全边界拉齐：

- MCP 不直接执行 gameplay action；AI 与人类同走 WASM 部署路径。
- Source Gate 明确区分 WASM/MCP/Admin/Replay/Tutorial/RuleMod/Simulate/DryRun 等来源，并要求 auth context 服务端注入。
- Deferred Command Model 将 mutating 操作收敛到统一 Command Validation Pipeline。
- WASM 沙箱有 fuel、epoch interruption、cgroup、seccomp、模块 import 白名单、体积限制、输出 JSON schema 限制。
- 统一可见性策略要求所有输出面调用 `is_visible_to`，覆盖 snapshot/MCP/WS/REST/replay。
- Fuel refund 已有 anti-amplification 时序、上限与滥用检测。
- Determinism contract 指定 ChaCha12、Blake3、禁浮点、IndexMap、固定 ECS 顺序与 replay checksum。

未发现必须阻断架构冻结的 Critical/High 级漏洞。以下条件项主要是实现前必须消除的规范矛盾和 DoS/权限边界细化；若不处理，会在实现阶段变成典型安全缺陷。

## Critical

None.

## High

None.

## Medium — 条件项

### M1. RuleMod 能力边界仍有一处规范矛盾：`actions` 可绕过 Command Pipeline 的表述需要收敛

位置：
- DESIGN.md §8.7 / Rhai API：`actions.deduct_resource`, `actions.award_resource`, `actions.modify_entity`, `actions.emit_event`
- DESIGN.md §8.7 / 引擎集成：`actions.apply(world);  // 经校验后写入`
- P0-7 §1：模组通过 `actions` 请求引擎操作，不能绕过 Command Validation Pipeline
- P0-7 §8：规则 System 可修改 ECS 资源/组件，但绝不可绕过 Command 校验管线
- P0-9 §2.3：RuleMod 允许 `deduct/award/emit_event`，不允许读写全局存储，不允许触发战斗

风险：
RuleMod 是服主安装的“可信但可出错/可被供应链污染”的脚本，不应获得等同 Admin 的任意 `modify_entity` 能力。当前文本同时出现：

1. RuleMod actions 只能经济 + 事件。
2. Rule System 可修改 ECS 资源/组件。
3. Rhai API 示例暴露 `modify_entity(entity_id, property, value)`。

这会在实现时诱导出“规则模组直接写世界状态”的后门式能力，绕过 P0-2 的归属、范围、资源、可见性与 Source Gate 校验。典型攻击/事故模式：恶意市场模组直接修改敌方 hits/position/owner，或通过 `award_resource`/`deduct_resource` 操纵全局经济。

条件：
- 将 RuleMod action API 改为显式 capability whitelist，不提供通用 `modify_entity`。
- P0-9 的 RuleMod 能力矩阵应成为权威边界：默认仅 `deduct_resource`, `award_resource`, `emit_event`, `log_*`，且资源操作必须限定为当前 world/local namespace 与被规则授权的资源类型。
- 若未来需要修改实体，应按动作类型拆成受限 API，例如 `apply_status_effect`, `set_rule_tag`, `adjust_decay_timer`，每个 API 单独定义作用域、可影响实体类型、审计字段、预算成本和 replay 表示。
- 在 P0-7/DESIGN 中删除或降级 `actions.modify_entity` 示例，避免实现者按通用反射写入。

### M2. `ManualSelect` spawn policy 与“手动控制不开放”需要命名/边界澄清

位置：
- DESIGN.md §8.2：manual_control 已删除，正式世界不开放手动控制；Tutorial 例外隔离。
- DESIGN.md §8.6：`manual_control = false`。
- P0-7 §2：`spawn.policy = "RandomRoom"`，枚举里包含 `ManualSelect`。
- P0-7 §3：`manual_spawn_system.before(spawn_system)`。
- P0-7 §8：规则 System 示例中出现“手动控制追加”。

风险：
“ManualSelect/manual_spawn_system/手动控制追加”在安全语义上容易被实现成正式世界的直接控制通道，破坏“代码就是军队”和“gameplay 指令只来自 WASM”的 Source Gate 原则。即使设计意图只是“加入时选择出生点”，当前命名也会制造歧义。

条件：
- 将 `ManualSelect` 明确重命名或注释为 `ManualSpawnLocationSelect`，仅允许在玩家首次加入/重生阶段选择出生坐标，不允许提交任何 tick gameplay action。
- 删除 P0-7 §8 中“手动控制追加”的表述，改为“出生/重生策略前置校验”或“规则前置约束”。
- 在 P0-9 Source Gate 中增加断言：正式 World/Arena 中不存在 ManualControl source；Tutorial source 仅 tutorial namespace 且不能与正式世界互通。

### M3. MCP docs/schema/get_available_actions 的无限制或高频读取需要与全局 DoS 策略对齐

位置：
- P0-3 §4.4：`swarm_get_schema` / `swarm_get_docs` 标为“无限制”或开发辅助工具 20/tick。
- P0-3 §5：开发辅助工具 20/tick；全局最大 MCP 连接 1000。
- P0-6 §3.1：MCP docs/API reference 是核心反馈循环。

风险：
docs/schema 看似静态，但在 MCP/SSE 场景中是高放大响应面：大文档、schema 生成、i18n、压缩、缓存穿透都可能形成低成本请求 → 高服务端带宽/CPU 的 DoS。若“无限制”被照实实现，会成为最便宜的滥用入口。

条件：
- 把 `swarm_get_schema` / `swarm_get_docs` 从“无限制”改成“强缓存 + 低成本限流”：按 content hash/ETag/CDN 缓存，未命中才生成；每 IP/每 token 有速率限制。
- 明确最大响应体、分页或按资源路径读取，禁止一次返回全量大型文档树。
- MCP 工具层记录 cache hit/miss 与响应字节数，纳入 DoS 监控。

### M4. WASM host function 与 IDL 的命名/集合有轻微不一致，需要以 P0-8 为单一真相

位置：
- DESIGN.md §5.1：包含 `host_get_world_rules`。
- P0-4 §3.2：列出 `host_get_world_config`，正文未列出 `host_get_world_rules`，但 §8 成本表包含 `host_get_world_rules`。
- P0-8 §2：IDL 同时列出 `get_world_config` 与 `get_world_rules`。

风险：
Host import 白名单如果由人工列表维护，命名/集合不一致会导致两类问题：

1. 误开放不该开放的 import。
2. SDK/文档声称可用但 sandbox 拒绝，诱导实现者绕过白名单。

条件：
- 明确 P0-8 `game_api.idl` 是唯一权威，P0-4 的 `ALLOWED_HOST_FUNCTIONS` 必须由 IDL 生成，禁止手写。
- 修正文档列表，使 `get_world_rules` 是否是 WASM host function 得到一致答案。
- CI 增加“文档 host function 表与 IDL diff”或至少“生成白名单与 committed 白名单一致”的检查。

### M5. `Simulate` / `swarm_simulate` 的资源上限需要更硬

位置：
- P0-3 §4.4：`swarm_simulate` “按需”。
- P0-9 §2.2/§2.3：Simulate 为 snapshot-bound dry-run，5/tick，0.5× MAX_FUEL。
- P0-6 §3.3：本地模拟 `swarm sim --ticks=5000 --speed=100x`。

风险：
模拟是典型 DoS 放大器。即使 snapshot-bound，不写世界，也可能消耗大量 CPU/内存，尤其当攻击者提交复杂 WASM、复杂路径查询或大 tick 数预测。P0-9 给了 per-tick 限流和 0.5× fuel，但 P0-3 的“按需”与 P0-6 的 5000 tick 示例容易被误用于服务器端 MCP simulate。

条件：
- 区分本地 CLI `swarm sim` 与服务器 MCP `swarm_simulate`：5000 tick 只应默认本地执行；服务器端必须小 tick 上限、队列化、按玩家并发限制。
- 为 `swarm_simulate` 定义最大 ticks、最大实体数、最大 snapshot bytes、最大 wall-clock、最大并发、取消语义与审计指标。
- 明确 simulate 不能访问隐藏实体；只能使用已绑定 snapshot_id 的可见副本。

## Informational

### I1. P0-1 Tick 状态机图仍把 FDB commit 放在 BROADCAST 步骤，正文已改为 EXECUTE

P0-1 状态机图 §1 的 BROADCAST 框中写有“FDB 原子提交”，但 §3.4 与 §4.2 明确表示 FDB commit 在 EXECUTE 完成，BROADCAST failure 不回滚 committed tick。正文语义正确，建议修图，避免实现者把持久化放到广播阶段。

### I2. P0-2 仍有若干 `Energy` 硬编码示例，与动态资源模型不完全一致

例如 Build/Repair/Spawn 使用 `drone.carry[Energy]`、`InsufficientEnergy`，而 P0-8 已把错误收敛为 `InsufficientResource { resource, required, available }`，DESIGN §8 也要求核心引擎不硬编码 Energy。建议将 P0-2 的示例改为 `registry.*_cost` 与资源名参数化，避免实现阶段回退到单资源假设。

### I3. seccomp syscall 白名单需要按 Wasmtime/平台实际最小集验证

P0-4 的 seccomp 白名单方向正确，但 Wasmtime/JIT/信号/线程在不同 Linux、glibc、版本下可能需要额外 syscall。建议 P1 prototype 用 strace/seccomp notify 生成实测最小集，并把 Wasmtime 版本 pin 入 replay/安全矩阵。否则容易在上线后为“修运行问题”临时放宽到过大白名单。

### I4. Admin 与 Rollback 权限已有审计，但建议补充双人审批的失效模式

P0-9 对 Rollback 标注“双人审计”，这是好的。但建议明确：审批 token 有 TTL、绑定具体 rollback target、不可复用、审批人与执行人不同、所有 admin writes 带 reason code。这样可以避免“万能 rollback_token”演化为高权限后门。

## 最终结论

CONDITIONAL_APPROVE。

R5 不要求重新召开架构评审；上述 Medium 条件项可作为 Phase 1 实现前的文档修订任务处理。只要完成 M1–M5，当前 Phase 0 安全架构可以进入实现阶段。
