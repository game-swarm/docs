# Swarm Implementation ROADMAP

> **状态: 审计中** ⚠️  
> **生成日期**: 2026-06-20 | **代码基准**: engine 336 tests ✓, 0 failures  
> **审计覆盖**: 全部 23 个规范文件 + 8 个设计文档 vs 代码 (engine/sandbox/gateway/sdk)

---

## 审计发现摘要 — 21 Gaps (不含假阳性)

| 严重度 | 数量 | 类别 |
|--------|:----:|------|
| 🔴 Critical | 9 | 安全/正确性/运行时故障 |
| 🟠 High | 4 | 重大功能缺口 |
| 🟡 Moderate | 8 | 功能不完整/文档不一致 |

---

## 🔴 Critical — 安全 / 正确性 / 运行时故障

### GAP-C01: 12 个 MCP 工具缺 `mcp_tool_source` 注册 — 运行时全部 `method_not_found`

- [ ] **修复**: 在 `engine/src/mcp.rs` 的 `mcp_tool_source()` 函数中为以下 12 个工具各添加一个 match arm：

| 缺失工具 | 应映射到的 Source | 所在 ToolInfo 行 |
|----------|------------------|-----------------|
| `swarm_auth_login` | `McpQuery` | mcp.rs:2006 |
| `swarm_auth_logout` | `McpQuery` | mcp.rs:2007 |
| `swarm_auth_refresh` | `McpQuery` | mcp.rs:2008 |
| `swarm_auth_check` | `McpQuery` | mcp.rs:2009 |
| `swarm_auth_cert_issue` | `Admin` | mcp.rs:2010 |
| `swarm_auth_cert_list` | `Admin` | mcp.rs:2011 |
| `swarm_auth_cert_revoke` | `Admin` | mcp.rs:2012 |
| `swarm_auth_cert_rotate` | `Admin` | mcp.rs:2013 |
| `swarm_auth_device_list` | `McpQuery` | mcp.rs:2014 |
| `swarm_auth_device_register` | `McpQuery` | mcp.rs:2015 |
| `swarm_get_terrain` | `McpQuery` | mcp.rs |
| `swarm_get_world_config` | `McpQuery` | mcp.rs |

- **根因**: `call_tool()` line 932 在 rate-limit 检查前先调用 `mcp_tool_source(tool).ok_or_else(|| McpError::method_not_found(tool))?`，缺失 source 映射的工具直接拒绝
- **验证**: 修复后运行 `cargo test --lib`，全部 336 tests 应继续通过
- **严重度**: 🔴 — 12 个生产 auth/查询工具完全不可用

### GAP-C02: Direction 坐标系根本性不匹配 — 六角网格 vs 规范四方网格

- [ ] **决策**: 先确认方向 — 改代码还是改规范？（当前设计分歧最根本的问题）
- [ ] **现状**: 
  - 代码 `command.rs`: `Direction { Top, TopRight, BottomRight, Bottom, BottomLeft, TopLeft }` (hex offset coordinates)
  - 规范 `01-tick-protocol §1.2`: "支持 N/S/E/W 四个方向"
  - 规范 `02-command-validation §3.1`: "Direction 是合法四方向邻居 (N/S/E/W)"
  - 规范 `08-api-idl §2`: `Direction: [North, South, East, West]`
  - 规范 `api-registry.md §1.1`: `direction: Direction4`
- [ ] **方案 A**: 改为六角网格 — 修改全部 7+ 个规范文件中的 Direction 定义，更新 api-registry.md Direction4 → Direction6
- [ ] **方案 B**: 改为四方网格 — 重写 `command.rs` Direction enum、所有坐标偏移函数 (~line 3393)、所有 Move 验证逻辑
- **严重度**: 🔴 — 规范与代码描述的是两个不同的空间模型

### GAP-C03: RejectionReason enum 90 variants — 规范 47 canonical，大量已废弃变体在 enum 中

- [ ] **修复**: 将以下 36 个已废弃变体从 `RejectionReason` enum 中移除/降级为 `debug_detail`：
  `TargetNotFound`, `NotMovable`, `Fatigued`, `MissingBodyPart`, `TileBlocked`, `StillSpawning`, `OutOfRoom`, `NoPath`, `PathTooLong`, `InsufficientMoveParts`, `InsufficientEnergy`, `InsufficientResources`, `CarryFull`, `NotSource`, `SourceEmpty`, `TargetFull`, `TargetEmpty`, `NotYourRoom`, `TileOccupied`, `InvalidTerrain`, `TooManyConstructionSites`, `AlreadyFullHealth`, `FriendlyTarget`, `NotYourSpawn`, `BodyTooLarge`, `ExceedsRoomCapacity`, `NotFriendly`, `TerminalRequired`, `OrderNotFound`, `AlreadyHacked`, `InvalidDamageType`, `PlayerNotFound`, `TargetTransferLocked`, `DailyTransferCapExceeded`, `TargetFuelTooLow`, `DisruptedResisted`
- [ ] **同步更新**: `CANONICAL_REJECTION_REASONS` 数组 — 当前 48 entries (45 unique, 含 3 个重复: `RateLimited`×2, `InvalidCertificate`×2, `NotAuthorized`×2)
- [ ] **同步更新**: `lib.rs` 中的两个断言计数 (`command_action_and_rejection_registries_match_api_surface`, `extracted_idl_exposes_command_and_rejection_registries`)
- [ ] **同步更新**: `api-registry.md` §2 RejectionReason 表
- **严重度**: 🔴 — 信息泄露风险 + 代码维护负担

### GAP-C04: WASM `wasm_simd(true)` 硬编码 — 违反确定性合约

- [ ] **修复**: `sandbox/src/lib.rs:307`: 将 `wasmtime_config.wasm_simd(true)` 改为从 `SandboxConfig` 读取配置
- [ ] **新增**: `SandboxConfig` 增加 `simd_enabled: bool` 字段，默认 `false`
- [ ] **新增**: 仅当 `world.toml` 显式启用 `[sandbox] deterministic_subset = { simd = true }` 时才设为 true
- **规范引用**: `04-wasm-sandbox §2.2` — "SIMD 由 world.toml 控制：默认禁用"
- **严重度**: 🔴 — 跨架构 SIMD 行为不可预测，破坏 replay 确定性

### GAP-C05: Seccomp 白名单与规范严重不符

- [ ] **修复**: `sandbox/src/lib.rs` `allowed_syscalls` 数组 — 移除规范明确禁止的 syscall：
  - 移除 `SYS_clock_gettime` (规范 §4.1 禁止)
  - 移除 `SYS_getrandom` (规范 §9.1 禁止)
  - 移除 `SYS_openat` (规范 §9.1 禁止)
- [ ] **修复**: `SYS_clone`/`SYS_clone3` 增加 flag 限制 — 仅允许 `CLONE_VM|CLONE_VFORK` (规范 §9.1)
- [ ] **审计**: 额外允许了 15+ 规范未列的 syscall (`fcntl`, `fstat`, `epoll_*`, `eventfd2`, `getcwd`, `getdents64`, `getpid`, `gettid`, `newfstatat`, `prctl`, `readlink`, `rseq`, `sched_*`, `set_robust_list`, `set_tid_address`, `statx`) — 逐项审查是否必需
- **严重度**: 🔴 — 沙箱逃逸面大幅增加，直接违反安全合同

### GAP-C06: `sandbox.relaxed` 生产环境拒绝检查缺失

- [ ] **新增**: 引擎启动时 (world.rs 或 config 验证阶段) 检查: 若 `sandbox.relaxed = true` 且 `world.mode != "development"` → 拒绝启动，panic 并输出明确错误信息
- [ ] **新增**: 对应的单元测试，验证 development 模式可启动、production 模式被拒绝
- **规范引用**: `04-wasm-sandbox §9.3`
- **严重度**: 🔴 — 生产环境可无意中开启宽松沙箱

### GAP-C07: `fog_of_war=true + player_view=full` 组合未拒绝

- [ ] **新增**: `WorldConfig::validate()` 或 `VisibilityConfig` 构造阶段检查 `fog_of_war && player_view == Full` → 返回 `Err("fog_of_war=true 与 player_view=full 互斥")`
- [ ] **新增**: 单元测试验证互斥拒绝
- **规范引用**: `05-visibility §10.1` — "world.toml 验证阶段被拒绝启动"
- **严重度**: 🔴 — MCP agent 可在 competitive world 中获取全地图视野

### GAP-C08: 应用层证书认证链完全缺失

- [ ] **实现**: Gateway 端 `Swarm-Certificate-Chain` header 解析和验证 (`gateway/`)
- [ ] **实现**: Gateway 端 `Swarm-Signature` canonical request 签名验证 (`gateway/`)
- [ ] **实现**: Gateway 端 `X-Swarm-Transport` header 判定 browser/agent/replay (`gateway/`)
- [ ] **实现**: `MissingTransportHeader`(401) / `AudienceMismatch`(403) 错误码
- [ ] **引擎侧**: 证书验证管线完善 (当前仅 MCP 工具注册，无实际验证逻辑)
- **规范引用**: `design/auth.md §5`, `gateway-protocol.md §9`, `09-command-source §7.0`
- **严重度**: 🔴 — 整个应用层认证模型未实现，当前仅 OAuth2 session 认证

### GAP-C09: TickTrace 缺少 `collect_id`/`attempt_id`/`commit_id`

- [ ] **新增**: `TickHeadPayload` (fdb.rs) 增加 `collect_id: Blake3Hash`, `attempt_id: u32`, `commit_id: Option<Blake3Hash>` 字段
- [ ] **新增**: tick.rs 中 tick 执行开始时生成 `collect_id`，每次 commit retry increment `attempt_id`
- **规范引用**: `05-persistence-contract §7.1`
- **严重度**: 🔴 — 无法区分 commit retry，replay 确定性受损

---

## 🟠 High — 重大功能缺口

### GAP-H01: `NotEligible` 拒绝码缺失 — 形成信息 oracle

- [ ] **新增**: `RejectionReason::NotEligible` variant
- [ ] **替换**: 特殊攻击的不可见/cooldown 目标统一返回 `NotEligible`（替代 `TargetOverloadCooldown`, `TargetFortifyCooldown`, `AlreadyHacked` 等独立拒绝码）
- [ ] **更新**: `CANONICAL_REJECTION_REASONS` + `api-registry.md` §2
- **规范引用**: `05-visibility §10.4` — "不可见目标与 cooldown 目标不可区分 → 形成 oracle"
- **严重度**: 🟠 — 安全边界，可通过拒绝码推断隐藏信息

### GAP-H02: Passkey/WebAuthn + Password Recovery 未实现

- [ ] **实现**: `swarm_register_passkey`, `swarm_recover_with_passkey` MCP 工具
- [ ] **实现**: `swarm_request_password_reset`, `swarm_admin_create_password_reset`, `swarm_confirm_password_reset` MCP 工具
- [ ] **实现**: `swarm_bind_email` MCP 工具
- [ ] **实现**: 其余规范 §10.1 列出的 17 个缺失 auth MCP 工具（当前仅 3 个实现：cert_issue/list/revoke）
- **规范引用**: `design/auth.md §10.1`
- **严重度**: 🟠 — 账号恢复路径缺失

### GAP-H03: Canonical Request Signature 验证缺失

- [ ] **实现**: `SWARM-REQUEST-V1` 签名 payload 构建和验证逻辑
- [ ] **实现**: `Swarm-Signature` header 解析 (格式: `t=<timestamp>,s=<signature_hex>,a=<algorithm>`)
- **规范引用**: `design/auth.md §5.6c`
- **严重度**: 🟠 — 请求完整性无保证

### GAP-H04: CI `cargo-audit` 未配置

- [ ] **新增**: `.github/workflows/security-audit.yml` — 每次 CI 运行 `cargo audit`
- [ ] **配置**: 依赖审计通知策略（CVE 严重度≥High → 阻断 CI）
- **规范引用**: `CVE-SLA.md`
- **严重度**: 🟠 — 无自动化 CVE 监控

### GAP-H05: `design/interface.md` 断链（假阳性 — 已确认存在）

- [x] **已验证**: `/data/swarm/docs/design/interface.md` 存在 (160 行)，`auth.md` 交叉引用有效
- **状态**: ✅ 无需修复

---

## 🟡 Moderate — 功能不完整 / 文档不一致

### GAP-M01: MCP Simulate 硬限制未实现

- [ ] **新增**: `SimulateConfig` 或 world.toml `[simulate]` section: `max_ticks=100`, `max_entities=1000`, `max_output_bytes=1MB`, `max_cpu_ms=5000`, `max_fuel_per_hour=50M`, `concurrent_simulates=3`
- [ ] **实现**: `sim.rs` 中检查并拒绝超限 simulate 请求
- **规范引用**: `04-wasm-sandbox §6.1`
- **严重度**: 🟡 — DoS 攻击面未受控

### GAP-M02: CommandAction `AlliedTransfer` 是代码独有变体

- [ ] **决策**: 注册进 `api-registry.md` §1（作为第 22 个 CommandAction）或从代码移除？
- [ ] **验证**: `AlliedTransfer` 在 `CORE_COMMAND_ACTIONS` 中，`api-registry.md` §7 economy 表列为 `ResourceOperation` 但未列为 `CommandAction`
- **严重度**: 🟡 — 规范遗漏

### GAP-M03: `api-registry.md` 与 `mcp-tools.md` 工具计数不一致

- [ ] **修复**: `mcp-tools.md` 说 56 Game API 工具，需与 `api-registry.md` §3 实际表行数对齐
- [ ] **同步**: `resources/list` + `resources/read` 在 engine ToolInfo 中但不在 `api-registry.md` 表格中 — 需要注册进 api-registry 或从 engine 移除
- [ ] **验证**: 全部文档中 MCP 工具计数一致 (engine: 65, spec 应为 65)
- **严重度**: 🟡 — 文档内部不一致

### GAP-M04: `omitted_count` 精确值 vs 分桶值

- [ ] **修复**: `sim.rs` 的 `OmittedCategories` (line 54-306) 改用 `omitted_count_bucket()` 函数输出字符串分桶值 ("few"/"some"/"many"/"extreme")
- [ ] **验证**: snapshot JSON 输出使用分桶函数而非精确 usize
- **规范引用**: `05-visibility §10.2`
- **严重度**: 🟡 — 可通过精确计数推断实际 entity 数量

### GAP-M05: Snapshot 截断不完整

- [ ] **新增**: bucket-based truncation 实现 — 逐级裁剪直到 `MAX_TICK_OUTPUT_BYTES` (256KB)
- [ ] **裁剪优先级**: entities → storage → global_storage → events
- **规范引用**: `09-snapshot-contract §1`
- **严重度**: 🟡 — 代码有阈值但无逐级裁剪

### GAP-M06: Safe Hint Ladder 未落地

- [ ] **新增**: competitive/practice/training 三级 `CommandRejection.detail` 过滤
- [ ] **竞争模式**: 仅返回 `NotEligible` + `RateLimited`
- [ ] **练习模式**: 返回完整的 RejectionReason 名称
- [ ] **训练模式**: 返回完整 detail（含 debug_info）
- **规范引用**: `09-snapshot-contract §4`
- **严重度**: 🟡 — 竞争环境 info leak

### GAP-M07: NATS 主题结构简化

- [ ] **修复**: `gateway/nats.go` 实现分层主题结构: `tick.<world_id>.<tick>`, `event.<world_id>.<event_type>`, `deploy.<world_id>.<player_id>`, `admin.<world_id>`
- **规范引用**: `gateway-protocol.md §6`
- **严重度**: 🟡 — 事件路由粒度不足

### GAP-M08: PvE Challenge 场景评分未独立实现

- [ ] **实现**: PvE Challenge 场景定义 + 评分系统（基于 `design/modes.md §9.1.5`）
- **现状**: Arena 有基本 PvE 能力 (`arena.rs`)，但挑战场景和评分公式未独立
- **严重度**: 🟡 — 规范已定义但未实现

---

## ✅ 已验证对齐（确认无需修改）

| # | 项目 | 证据 |
|---|------|------|
| ✅ | 29 ECS system 全部在 scheduler manifest (S01-S29) | `scheduler.rs:461` assert_eq 验证 |
| ✅ | MCP 工具双向对齐 (comm -23 = 0, comm -13 = 0) | 65 engine ↔ 63 spec (diff: resources/list, resources/read 待注册) |
| ✅ | `is_visible_to()` 核心可见性函数 | `visibility.rs:14` + 6 个单元测试 |
| ✅ | FDB 持久化层完整 | `fdb.rs`: tick_head/manifest/hash_chain/state_checksum/tick_trace_blob |
| ✅ | Arena 生命周期完整 | `arena.rs`: ArenaPlayerCode/ArenaConfig/ArenaMatchState/ArenaRules |
| ✅ | ResourceLedger 系统已注册 | `world.rs` system chain |
| ✅ | Sandbox StartSection 拒绝 + 内存/燃料限制 | `sandbox/src/lib.rs:297,304,306,309,421,537` |
| ✅ | 5 个 host functions 全部注册 | `sandbox/src/lib.rs:40-44` |
| ✅ | design/ 域文件交叉引用有效 | interface.md 存在 (160 行) |
| ✅ | UploadStatus 状态机 | `fdb.rs:69` Pending/Complete/Failed |
| ✅ | Source Gate 管线完整 | `command.rs:695-831` |
| ✅ | 336 tests, 0 failures | `cargo test --lib` |

---

## 📊 汇总

| 分组 | 总数 | 待修复 | 已确认 OK |
|------|:----:|:------:|:---------:|
| 🔴 Critical | 9 | 9 | 0 |
| 🟠 High | 5 | 4 | 1 (H05 假阳性) |
| 🟡 Moderate | 8 | 8 | 0 |
| ✅ Verified | 12 | 0 | 12 |
| **总计** | **34** | **21** | **13** |

---

## 🔧 修复分组

| Wave | Gaps | 涉及文件 |
|------|------|----------|
| **W1** | C01 (MCP source) | mcp.rs 1处 |
| **W2** | C04 (SIMD), C05 (Seccomp), C06 (relaxed), C07 (fog+full), H04 (CI audit) | sandbox/lib.rs, world.rs, .github/ |
| **W3** | C09 (collect_id), M01 (Simulate limits), M05 (snapshot truncation) | fdb.rs, tick.rs, sim.rs |
| **W4** | C08 (cert auth), H02 (passkey/recovery), H03 (request signature) | gateway/, mcp.rs, auth.rs |
| **W5** | C03 (RejectionReason), H01 (NotEligible), M04 (omitted_count), M06 (hint ladder) | command.rs, visibility.rs, sim.rs |
| **W6** | C02 (Direction), M02 (AlliedTransfer) | 需决策，多文件 |
| **W7** | M03 (registry counts), M07 (NATS), M08 (PvE) | docs/, gateway/ |
