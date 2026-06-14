# Security Review — GPT-5.5 (Round 4)

Verdict: CONDITIONAL_APPROVE — R3 的主要架构性安全 gap 大多已被补齐，可以视为 Phase 0 Architecture Freeze 的候选版本；但仍有 4 个 contract cleanup 必须在进入实现前修正，尤其是 DESIGN 与 P0 规范之间的 deferred model 不一致、`swarm_validate_plan` 残留为未定义高风险入口、Compile Budget 仍不足以抵御低成本编译 DoS。

## Strengths

1. R3 major changes 已大幅修复：MCP 不再是 gameplay 控制器

- DESIGN.md §4 明确 MCP 是 AI 的「屏幕和鼠标」，不存在 `swarm_move` / `swarm_attack` / `swarm_build` 等直接动作工具，AI 与人类都必须写 WASM。
- P0-1 §2.1 明确唯一执行器是 `WasmSandboxExecutor`，没有 `McpPlayerExecutor`。
- P0-3 §1/§4.5 再次把 MCP 定位为部署、查询、调试界面，而非实体控制面。

这修复了早期最危险的「AI 特权输入路径」问题：AI 不再绕过 fuel metering / Command Validation / replay。

2. P0-9 Source Gate 从缺失状态提升到可审计模型

P0-9 现在覆盖了 12 类 source：

- `WASM`
- `MCP_Deploy`
- `MCP_Query`
- `Admin`
- `Replay`
- `TestHarness`
- `Tutorial`
- `Deploy`
- `Rollback`
- `RuleMod`
- `Simulate`
- `DryRun`

并为它们定义了 auth_context、gameplay 权限、audit、rate_limit、visibility、budget；同时补充了 capability 矩阵。R3 我提出的 deploy/rollback/admin/tutorial/replay/test/rule-mod/simulate/dry-run 缺口基本闭合。

特别值得肯定：

- P0-9 §3 明确 Command body 中的 `player_id` 不可信，服务端覆盖。
- P0-9 §4 引入 Source Gate，默认只有 `WASM` 进入 gameplay 指令管线。
- P0-9 §2.4 将 Tutorial 绑定到 `world.mode = "tutorial"`，且使用独立 namespace，修复 R3 High #5。
- Rollback 使用双人审计，比单 admin token 安全。
- `Simulate` 被定义为 snapshot copy / snapshot-bound dry-run，不写真实世界。

3. Tick output schema 与 refund abuse 已补强

P0-2 §1.1 增加了 tick 输出 JSON schema：数组、最大 100 commands、总大小 256KB、拒绝额外字段、深度 ≤10、畸形输出整 tick 丢弃。这修复了 R3 中 `tick() → JSON` 作为 untrusted input 的关键校验缺口。

P0-2 §7 的 refund 模型现在有：

- 仅下一 tick 生效，防同 tick amplification；
- fuel credit 上限为 `MAX_FUEL × 10%`；
- 同源重复失败不累计；
- 连续高 refund rate 自动 throttle。

这已经从「可被资源竞争刷 fuel」提升为可控风险。

4. Determinism Contract 明显更成熟

DESIGN.md §8.8 明确：

- PRNG = ChaCha12；
- hash = Blake3；
- world_seed = 32 字节；
- 禁 std::hash / std HashMap iteration；
- 使用 IndexMap；
- 整数 + fixed-point；
- Rhai 禁浮点。

这修复了 R3 多个 reviewer 对 f64、Rhai、HashMap、随机性的冻结级担忧。

5. Visibility policy 有统一出口

P0-5 的 `is_visible_to(entity, player_id, tick)` 是正确方向。它把 snapshot、MCP、WebSocket、REST、replay 都纳入同一可见性策略，降低了「debug/replay 泄露隐藏状态」这类常见漏洞。

6. WASM sandbox baseline 比 R3 更安全

P0-4 现在有：

- 每 tick fork/kill，减少跨 tick 持久化风险；
- seccomp + cgroup v2 + no network namespace + read-only rootfs；
- Wasmtime pinned version；
- 禁 WASI 文件/网络/时钟/随机；
- 模块体积、内存、stack、instances、host function 调用数、path_find 次数、输出 JSON 大小预算；
- 恶意 WASM corpus 测试方向。

这是一个可实现、可测试的安全基线。

## Remaining Concerns

### Critical

1. DESIGN.md §5 仍保留 mutating host functions，与 P0-4 / P0-8 的 deferred model 冲突

DESIGN.md §5 仍列出：

- `host_move`
- `host_harvest`
- `host_transfer`
- `host_withdraw`
- `host_build`
- `host_repair`
- `host_attack`
- `host_ranged_attack`
- `host_heal`
- `host_spawn`
- `host_recycle`

但 P0-4 §3 明确禁止 mutating host function，所有游戏动作必须通过 `tick() → JSON` 返回 Command；P0-8 IDL 也把 mutating actions 建模为 commands，而 host_functions 只保留 tick 与查询类 host functions。

这是 Phase 0 Freeze 前必须修掉的合同冲突。否则实现者很容易按 DESIGN §5 暴露 mutating host function，导致 WASM 可在 collect 阶段直接修改或影响世界状态，绕过统一 Command Validation Pipeline、Source Gate、refund policy、replay ordering。

建议：

- 删除 DESIGN.md §5 中所有 mutating host function 列表；
- 改成「WASM ABI + read-only host functions + Command JSON schema」；
- 明确 DESIGN.md 中 `Command` / `RejectionReason` / host function 以 P0-8 IDL 为唯一真相。

### High

2. `swarm_validate_plan` 仍以 P0 工具身份存在，但没有纳入 P0-3 / P0-8 / P0-9 的 source contract

P0-6 §3.1 和 §7 仍把 `swarm_validate_plan` 列为 P0 MCP 工具："如果我提交这些指令，会成功吗？" 预演校验。

问题是：

- P0-3 的 MCP 工具列表没有 `swarm_validate_plan`；
- P0-8 IDL 没有它的 schema；
- P0-9 Source Model 只有 `Simulate` / `DryRun`，没有 `ValidatePlan` source；
- 它的 visibility、budget、auth_context、audit、rate_limit、是否允许传入 commands、是否绑定 snapshot_id、是否使用 snapshot copy、是否允许下一 tick current-state 预判，都未定义。

这正是 R3 我指出的「直接动作接口的影子形态」。即使它名义上是 dry-run，只要能用实时世界状态批量测试 command legality，就可能成为：

- hidden state oracle；
- action feasibility oracle；
- TOCTOU predictor；
- command validation side-channel；
- pathfinding / validation compute DoS 入口。

建议二选一：

A. 删除 `swarm_validate_plan`，P0-6 改为使用 `swarm_simulate(snapshot_id, commands, ticks)`，且沿用 P0-9 `Simulate` source：snapshot-bound、snapshot copy、5/tick、0.5× MAX_FUEL、完整 audit。

B. 保留但重命名并完整建模为 `MCP_Query` 下的 `swarm_validate_plan`：

- 输入必须带 `snapshot_id`，只能针对该玩家已获得的 snapshot；
- 只返回「在该 snapshot 上的 non-authoritative validation result」；
- 不读取 current world；
- 不保留 reservation，不保证真实 tick 成功；
- 每次最多 100 commands，总大小 256KB，深度 ≤10；
- budget 与 `Simulate` 合并计数；
- 输出只包含玩家自身可见 rejection detail；
- 全量审计。

当前文档还未达到这个清晰度。

3. Compile Budget 仍不足以抵御 500 AI 玩家持续部署场景

P0-4 §7 已新增：30s compile timeout、512MB cgroup、独立 fork、module cache、最多 5 并发、validation 10ms。这是进步，但还不够。

主要缺口：

- 没有全局 compile queue 上限与丢弃策略；
- 没有 per-player / per-IP / per-world 的 compile CPU 秒配额；
- `MCP_Deploy` 是 10/h，而 P0-9 `Deploy` 是 1/tick，两者关系不清；
- `swarm_validate_module` 在 P0-3 是 10/h，但 P0-9 `DryRun` 是 20/h，两个入口是否共享预算不清；
- 缓存只按 `(module_hash, wasmtime_version)`，缺少 compiler flags / feature set / ABI version / world API version；
- cache miss storm 没有熔断；
- 失败编译没有 exponential backoff；
- 没有 compile bomb corpus：巨量函数、巨量 locals、深 CFG、恶意 custom sections、name section 膨胀、递归 type、极端 table/global/import/export 数量；
- `module validation = 10ms` 作为目标很好，但未定义超时实现与 wasmparser streaming cap。

建议将 Compile Budget 升级为 P0 明确 contract：

- 全局 compile queue：例如 max queued = 100，超过后 429；
- per-player：deploy + validate + dryrun 共享 `compile_tokens`；
- per-world：防单世界耗尽整个 shard 编译池；
- per-IP：防 Sybil 初级滥用；
- 失败 backoff：同 player 连续失败 3 次后冷却；
- cache key = `(module_hash, wasmtime_version, abi_version, compiler_config_hash)`；
- cache admission：只缓存成功编译且低复杂度模块；
- compile bomb CI corpus；
- 指标：queue_depth、compile_cpu_seconds、compile_timeout_rate、cache_hit_rate、validation_reject_rate。

4. Admin source 仍显示 "rate_limit = 无限制"，虽然有 audit，但缺少操作级安全边界

P0-9 将 `Admin` 建模为全局可见、可写、可部署、可触发战斗，rate_limit 为无限制。对于早期实现可以理解，但安全 contract 仍过宽。

至少应补充：

- dangerous admin actions 需要 reason + ticket id；
- destructive / rollback / force-deploy 操作需要双人审计或 break-glass；
- admin action 也要有 global safety rate cap，避免误操作脚本把 shard 打爆；
- admin replay / inspect 输出必须强制标记 Admin-only，不得被 Web/MCP 缓存复用。

### Medium

5. P0-1 FDB commit 位置文档仍有轻微歧义

P0-1 状态机图在 BROADCAST 中列出 FDB 原子提交，但 §4.2 又说明 FDB commit 发生在 EXECUTE 阶段末尾，BROADCAST 不访问 FDB。文字最终解释是对的，但图仍可能误导实现。

建议：修改状态机图，把 BROADCAST 中的 "FDB 原子提交" 改为 "确认已提交 tick / 读取 committed state" 或删除。

6. P0-2 与动态资源模型仍有旧 Energy 命名残留

P0-2 多处 validator / RejectionReason 仍写 `InsufficientEnergy`、`drone.carry[Energy]`、`spawn.energy`。P0-8 已使用 `InsufficientResource { resource, required, available }` 和 registry cost，这更符合动态资源模型。

风险不是安全漏洞，而是实现漂移：某些路径可能硬编码 Energy，导致自定义资源世界绕过成本或错误扣款。

建议：P0-2 全部改成 `ResourceName` / `ResourceCost` / `InsufficientResource`，并标注错误码以 P0-8 IDL 为准。

7. Rhai RuleMod 的 trust boundary 仍需更硬

DESIGN.md 与 P0-7 说 RuleMod 是服主安装、可信；但 P0-9 又允许 `RuleMod` deduct/award/emit_event。可信不等于无限可信，尤其未来有 mod marketplace。

建议补充 Tier 模型：

- Tier 0 declarative-only：只改参数，无脚本；
- Tier 1 sandboxed Rhai：只读 state + bounded actions；
- Tier 2 privileged server mod：需签名 / admin install / prominent warning。

同时 `RuleMod` actions 应通过 capability manifest 声明，例如 `can_award_resource=false` 默认关闭。

8. MCP transport hardening 尚未进入 P0-3

P0-3 有 HTTPS+mTLS、JWT、rate limit、audit，但缺少 rmcp/HTTP/SSE 层面的硬限制：

- max request body；
- max JSON-RPC batch size 或禁 batch；
- SSE heartbeat / idle timeout；
- Origin / CORS allowlist；
- per-connection in-flight request cap；
- tool call timeout；
- response size cap；
- structured error 不回显敏感内部路径。

这属于 High/Medium 之间的供应链与协议面风险。若 P0-3 是 MCP Security Contract，建议纳入。

### Informational

9. 文档章节编号重复

DESIGN.md 有两个 "## 10"：World/Arena 与贡献指南。非安全问题，但 Phase 0 freeze 文档应整理。

10. Wasmtime version pin 需要现实校验

P0-4 pin `wasmtime = "=30.0"`。实现时应确认该版本是否存在、是否仍有公开 CVE、是否支持所列 config API。文档层面可接受，但进入代码前需 cargo check 证明。

## Fresh Ideas

1. Source Gate property tests

为 P0-9 生成矩阵驱动测试：每个 Source × 每个 capability × 每个 world mode 都有 allow/deny case。特别测试：MCP_Deploy 不能提交 gameplay command、Tutorial 不能进入 non-tutorial world、Replay 只读、RuleMod 不能触发 combat。

2. Security oracle tests for `swarm_validate_plan` / `swarm_simulate`

如果保留 dry-run，写专门测试证明它不能泄露不可见实体：对隐藏 enemy、隐藏资源、隐藏 cooldown 构造 commands，返回必须是 generic / snapshot-local，而不是通过 rejection detail 泄露真实状态。

3. Compile bomb corpus as first-class repo artifact

建立 `/sandbox/tests/wasm-bombs/`：

- huge function count；
- huge locals；
- huge custom/name sections；
- deep branch nesting；
- many imports/exports；
- recursive types；
- memory/table edge cases；
- valid but slow-to-compile modules。

CI 跑 validation timeout、compile timeout、engine survival。

4. Deployment quarantine lane

新上传 WASM 先进入 quarantine：只允许 validate + offline simulate，连续通过若干 checks 后才可进入 live next tick。对新账号、异常账号、刚触发 compile backoff 的账号默认启用。

5. Capability manifest for RuleMod

每个 mod.toml 增加：

- reads: players/entities/resources/events；
- writes: deduct/award/modify_entity/emit_event；
- max_actions_per_tick；
- max_players_iterated；
- deterministic_features_required。

World owner 安装时看到 diff："此 mod 请求 award_resource 权限"。

6. Admin break-glass ledger

Admin 操作不是只进 ClickHouse，而是写 append-only ledger，字段包括 admin_id、reason、scope、before/after checksum、approval_id。危险操作要求第二 admin approve。

7. IDL drift CI across docs

除 `cargo run -- gen-api && git diff --exit-code` 外，增加 docs lint：扫描 DESIGN/P0 中是否出现禁止的 mutating host functions、旧 RejectionReason、`player_id` in Command body 等模式，防止 DESIGN 与 P0 再次漂移。

8. Visibility taint type

在 Rust 类型层引入 `Visible<T>` / `AdminOnly<T>` / `UntrustedString`。输出面只能 serialize `Visible<T>`，避免工程师绕过 `is_visible_to` 直接返回实体。

## Bottom Line

Round 4 版本已从 R3 的 REQUEST_MAJOR_CHANGES 进入 CONDITIONAL_APPROVE。P0-9 Source Gate 的完整性显著改善，WASM-only 公平路径、Source Gate、Tick schema、refund cap、determinism contract 都已经具备冻结候选质量。

但我不建议在修复以下 4 项前宣布完全冻结：

1. 删除 DESIGN.md §5 mutating host functions，与 P0-4/P0-8 deferred model 对齐；
2. 删除或完整建模 `swarm_validate_plan`，不得留下未受 P0-3/P0-8/P0-9 约束的 shadow action API；
3. 将 Compile Budget 扩展为队列、共享配额、cache key、backoff、compile bomb corpus 的完整 DoS contract；
4. 收紧 Admin source 的危险操作边界与审计要求。

修完这些后，我会给 APPROVE_WITH_RESERVATIONS 或 APPROVE。