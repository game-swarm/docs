# R1 Speaker 综合裁决 — Swarm 设计评审

> **Speaker**: In-session synthesis (9 评审官 → 6 有效, 3 无效)
> **评审日期**: 2026-06-16
> **评审范围**: DESIGN.md (2292行), tech-choices.md, ROADMAP.md, specs/01-09

---

## 1. 裁决概要

| 评审官 | 方向 | 模型 | Verdict | Critical | High | 状态 |
|--------|------|------|---------|----------|------|------|
| rev-dsv4-designer | 游戏设计 | DeepSeek V4 Pro | APPROVE_WITH_RESERVATIONS | 0 | 2 | ✅ |
| rev-dsv4-architect | 架构师 | DeepSeek V4 Pro | APPROVE_WITH_RESERVATIONS | 0 | 1 | ✅ |
| rev-dsv4-security | 安全审计 | DeepSeek V4 Pro | APPROVE_WITH_RESERVATIONS | 2 | 6 | ✅ |
| rev-gpt-designer | 游戏设计 | GPT-5.5 | APPROVE_WITH_RESERVATIONS | 0 | 3 | ✅ |
| rev-gpt-architect | 架构师 | GPT-5.5 | **REQUEST_MAJOR_CHANGES** | 3 | 6 | ✅ |
| rev-gpt-security | 安全审计 | GPT-5.5 | **REQUEST_MAJOR_CHANGES** | 0 | 4 | ✅ |
| rev-claude-designer | 游戏设计 | Claude Opus 4.7 | — | — | — | ❌ 截断 |
| rev-claude-security | 安全审计 | Claude Opus 4.7 | — | — | — | ❌ API错误 |
| rev-claude-architect | 架构师 | Claude Opus 4.7 | — | — | — | ❌ 超时 |

**裁决**: **APPROVE_WITH_CONDITIONS** — 4/6 APPROVE vs 2/6 MAJOR_CHANGES。设计骨架优秀，核心架构决策（Deferred Command Model、WASM 统一执行路径、FDB 权威源、Blake3 单原语）无争议。GPT 阵营的 MAJOR_CHANGES 针对的是文档合同一致性与范围管理问题，非方向性否定。在修复共识 Blocker 后可进入实现。

**收敛评估**: 中度收敛。最严重的跨文档不一致（Overload 规格、spectate_delay、输入限制）被双方阵营独立识别，说明问题真实存在。设计方向层面无分歧（0/6 REJECT）。

**Claude 批次全军覆没**: 3 位 Claude 全部失败（截断/连接错误/超时），与先前的 profile-based pipeline 验证结果矛盾（上次 9/9 完成）。可能原因：Claude API 端点不稳定或模型配额限制。R2 评审应使用 fallback 模型。

---

## 2. 共识 Blocker

### B1: Overload 攻击的信息泄露与跨文档规格冲突 ⭐⭐⭐⭐⭐

**覆盖**: 5/6 评审官 | **方向**: Security×2, Architect×2, Designer×1 | **模型**: dsv4×3, gpt×2

**问题描述**:

DESIGN.md 设计意图明确——Overload 应「返回静默结果，攻击者无法推断目标 fuel 状态」。但实现层面存在三个缺口：

1. **TargetFuelTooLow 拒绝码泄露 fuel 状态** (dsv4-security C1): specs/02 §3.12 定义了 `TargetFuelTooLow` 拒绝码，直接告诉攻击者「目标 fuel ≤ 2M」。这违反了 DESIGN 的静默返回设计合同。

2. **Per-target 全局冷却未写入 specs** (dsv4-security H1, gpt-security H-1): DESIGN 规定「同一目标每 50 tick 最多被 Overload 一次」，但 specs/02 §3.12 和 specs/08 IDL validator 均未包含此逻辑。多个攻击者可在同一 tick 协同 Overload，将目标 fuel 从 10M 打至 2M。

3. **Visibility 约束在 spec 校验中缺失** (gpt-security H-1): specs/02 Overload 校验表未包含 `visible_target` 或 `is_visible_to` 检查，允许攻击者对不可见玩家执行 Overload。

**裁决**: **Blocker** — 必须在 R2 前修复。此为 3 方向 × 2 模型的最高共识项。

**修正要求**:
- 移除 `TargetFuelTooLow` 拒绝码，Overload 始终返回 `Accepted`（对已在 fuel 下限的目标静默无效）
- 将 per-target 全局冷却（`(target_player_id, tick_applied)`, 50 tick）写入 specs/02 §3.12 和 specs/08
- 在 specs/02 Overload 校验矩阵中增加 `visible_target` 检查（基于 `is_visible_to`）
- 在 specs/08 IDL validator 中增加 `target_global_cooldown` 校验
- DESIGN.md Overload 行结果说明改为「始终返回 Accepted（静默），攻击者无法推断目标 fuel 状态」

---

### B2: spectate_delay 约束未强制执行 ⭐⭐⭐

**覆盖**: 3/6 评审官 | **方向**: Security×2, Architect×1 | **模型**: dsv4×1, gpt×2

**问题描述**:

specs/05 §3.5 声明「World 模式下若 `public_spectate = true`，`spectate_delay` 必须 ≥ 50 tick」，但：

1. DESIGN §8.3 的 `world.toml` 示例将 `spectate_delay` 默认值设为 0
2. `validate_config()` 未校验此约束
3. 服主误配置 `public_spectate = true` + `spectate_delay = 0` → 实时全图信息泄露给旁观者 → 旁观者可将信息传递给参赛者 → fog_of_war 完全失效

**裁决**: **Blocker** — 2 方向 × 2 模型共识。必须在 R2 前修复。

**修正要求**:
- 在 `validate_config()` 中增加强制校验：`if world.mode == "persistent" && visibility.public_spectate && visibility.spectate_delay < 50 → error`
- World 模式下 `spectate_delay` 默认值改为 50
- 若 `public_spectate` 启用但 `spectate_delay` 未显式设置，自动 clamp 到 50

---

### B3: 命令数量/JSON 大小限制跨文档冲突 ⭐⭐

**覆盖**: 2/6 评审官 | **方向**: Architect+Security (均为 gpt 模型) | **模型**: gpt

**问题描述**:

| 文档 | 限制 |
|------|------|
| specs/02 §1.1 | maxItems=100, 总字节 ≤ 256KB |
| specs/02 §6 | 单条 ≤ 64KB, 整批 ≤ 1MB, 每玩家 ≤ 500 条 |
| specs/04 ABI | CommandIntent JSON ≤ 256KB |

三个数字互斥：100 vs 500 条，256KB vs 1MB。实现者按不同章节落地会引发 SDK/服务端不一致。

**裁决**: **Blocker** — 虽然只有 gpt 模型标记，但两个方向（架构+安全）独立发现同一问题。

**修正要求**:
- 选择权威上限并在全仓统一：`MAX_COMMANDS_PER_PLAYER = 100/tick`, `MAX_TICK_OUTPUT_BYTES = 256KB`, `MAX_COMMAND_BYTES = 16KB`
- 其他文档只引用权威 spec，不重复写数值
- Admin bulk operation 不进入实时 tick pipeline，走独立 maintenance job

---

### B4: P0 范围膨胀 / ROADMAP 状态误导 ⭐⭐⭐

**覆盖**: 3/6 评审官 | **方向**: Architect×2, Designer×1 | **模型**: dsv4×1, gpt×2

**问题描述**:

gpt-architect A1: DESIGN/specs 覆盖了持久 MMO、Arena、锦标赛、市场、Rhai 模组、可配置类型系统、联邦宇宙、8 种特殊攻击等全部内容，但 ROADMAP 标为 100% 完成。这不是一个 P0，是一个平台级 1.0+ 扩展生态。

**裁决**: **Direction Blocker** — 不是否定设计质量，而是要求在 R2 前明确「哪些是 P0 必须实现，哪些是远期设计」。ROADMAP 应区分 `design accepted` vs `spec internally consistent` vs `implementation verified`。

**修正要求**:
- ROADMAP 增加状态粒度（设计通过 / 规格自洽 / 实现验证）
- P0 明确不含：Layer 3 world-specific SDK、Rhai 第三方模组进程隔离、市场交易、锦标赛、联邦宇宙跨世界转移
- 特殊攻击（Leech/Fabricate）标记为 Expansion RFC，P0 仅保留 6 种核心攻击

---

## 3. 方向专属 High 优先级

以下问题有方向内共识但缺少跨方向覆盖，由 Speaker 裁决处理。

### H1: Tick/ECS 系统顺序在 DESIGN vs specs 间不一致

**来源**: gpt-architect A5 (High), dsv4-architect D1 (High)
**裁决**: 两位架构师独立发现。DESIGN §3.2 的 Phase 2b 顺序与 specs/01 §3.4 的 `.chain()` 顺序不同。必须统一为单一 Tick Phase Contract。**R2 修正**。

### H2: WASM 部署签名模型混淆

**来源**: gpt-security H-3 (High)
**裁决**: 服务端签发证书 + 客户端私钥签名的边界不清。二选一：(1) 客户端生成 Ed25519 keypair，服务端只签 public key 证书；(2) 纯 bearer token + server-side audit。**R2 修正**。

### H3: MCP transport 安全边界不完全

**来源**: gpt-security H-2 (High)
**裁决**: MCP HTTP/SSE 存在 DNS rebinding / loopback 攻击面。需拆分 browser/non-browser transport contract，增加 DNS rebinding 防护测试。**R2 修正**。

### H4: World 模式长期留存问题

**来源**: dsv4-designer G1+G2 (High), gpt-designer G1 (Blocker)
**裁决**: 两位游戏设计师一致认为 World 模式雪球效应 + 缺乏激励是最大留存风险。建议增加赛季制选项、成就系统、世界事件。**R2 讨论，非 Blocker**（设计方向正确，可通过配置解决）。

### H5: 坐标/网格模型不一致（方形房间 vs 六边形 Direction）

**来源**: gpt-architect A10 (Medium)
**裁决**: DESIGN §3.1a 描述方形 50×50 网格 + N/S/E/W 出口，但 specs/02 Direction enum 是六边形方向（Top/TopRight/BottomRight...）。**R2 修正**：明确世界网格模型并统一所有文档。

### H6: FDB + Bevy 工作副本事务成本未建模

**来源**: gpt-architect A6 (High)
**裁决**: 缺少每 tick 的 entity count、FDB transaction size、commit p95/p99 等容量预算表。**Phase 1 补充**，非 R2 Blocker。

---

## 4. Medium/Low 处置

| ID | 问题 | 来源 | 处置 |
|----|------|------|------|
| M1 | Controller repair 公式歧义（容量可叠加但速率截断） | dsv4-security H6 | R2 文档澄清 |
| M2 | RNG 种子轮换周期偏长（10k tick ≈ 8h） | dsv4-security H4 | R2 缩短至 1k tick |
| M3 | WASM 预编译缓存的安全边界 | dsv4-security H5 | Phase 1 增加缓存 namespace |
| M4 | host_path_find + 公开 terrain 可能暴露全图可通行性 | dsv4-security H3 | R2 评估 terrain 是否应受 fog 约束 |
| M5 | Hack/Fortify 控制锁竞态 | dsv4-security H2 | R2 明确 Fortify 净化后的免疫窗口 |
| M6 | Rhai 进程隔离的 IPC 开销未基准测试 | dsv4-architect R2 | Phase 1 性能工程 |
| M7 | Spawn birth-tick protection 建议配置化 | dsv4-architect D3 | R2 讨论 `spawn_protection_ticks` |
| M8 | 单一资源经济（Energy-only）限制策略深度 | dsv4-designer G4 | R2 讨论 Vanilla 加入 Matter |
| M9 | 缺乏联盟/公会社交结构 | dsv4-designer G5 | P1 功能，非设计文档问题 |
| M10 | Rhai 模组 checksum 从「可选」升级为「必需」 | gpt-security M-3 | R2 修正 |
| M11 | swarm_simulate / dry-run 预算不足 | gpt-security M-2 | R2 增加 tick/entity/output 上限 |
| M12 | 术语与章节编号混乱 | gpt-architect A15 | R2 docs lint |
| M13 | 规则模组信任模型表述前后不一致 | gpt-architect A12 | R2 统一为 "semi-trusted server plugins" |

---

## 5. 文档维护项

1. **specs/p0/ 路径修复**: 6/6 评审官报告 `specs/p0/` 不存在。实际文件在 `specs/01-09*.md`。要么恢复 `specs/p0/` 目录（symlink 或 index），要么更新 AGENTS/README 中的引用路径。

2. **Claude 评审管道排查**: 3/3 Claude 失败（截断/连接错误/超时）。如果 Claude API 端点持续不稳定，R2 评审使用替代模型（如 Gemini 或 DeepSeek 替代 Claude 的安全/设计方向）。

3. **本次审查已修复项（A1/M2/M3/M4/M5/M6/M7）**: 已在 DESIGN.md 中应用，无需重复处理。但需在 specs 中同步（如 Overload spec 修复涉及 specs/02 和 specs/08）。

---

## 6. R2 入场条件

以下 Blocker 必须在 R2 评审前解决：

- [ ] **B1**: Overload 规格统一 — 移除 TargetFuelTooLow，per-target 冷却写入 specs/02+08，增加 visibility 校验
- [ ] **B2**: spectate_delay 强制校验 — validate_config() 增加约束，默认值改为 50
- [ ] **B3**: 输入大小限制统一 — 选择权威上限（100 条/256KB/16KB），全仓引用
- [ ] **B4**: ROADMAP 状态粒度 — 区分 design accepted / spec consistent / implementation verified
- [ ] **H1**: Tick/ECS 顺序统一 — 单一 Tick Phase Contract
- [ ] **H2**: WASM 签名模型澄清 — 客户端密钥 vs bearer token 二选一
- [ ] **H3**: MCP transport 安全合同 — browser/non-browser 分离
- [ ] **H5**: 坐标/网格模型统一 — 方形 vs 六边形二选一
- [ ] 文档维护项：specs/p0/ 路径修复

---

## 7. 评审统计

### Verdict 矩阵

| | Architect | Security | Designer | 合计 |
|---|:--:|:--:|:--:|:--:|
| **DeepSeek V4 Pro** | APPROVE | APPROVE | APPROVE | 3/3 |
| **GPT-5.5** | MAJOR | MAJOR | APPROVE | 1/3 |
| **Claude Opus 4.7** | ❌ | ❌ | ❌ | 0/3 |

### Severity 矩阵 (6 有效评审)

| Severity | Architect | Security | Designer | 合计 |
|----------|:--:|:--:|:--:|:--:|
| Critical / Blocker | 3 | 2 | 1 | 6 |
| High | 7 | 10 | 5 | 22 |
| Medium | 4 | 7 | 4 | 15 |
| Informational / 亮点 | 5 | 17 | 6 | 28 |

### 共识强度

- **强共识** (≥3 reviews, ≥2 directions, ≥2 models): B1 (Overload)
- **中共识** (2-3 reviews, ≥2 directions): B2, B3, B4
- **方向内共识** (2 reviews, 1 direction): H1, H4
- **单审官员** (1 review): H2, H3, H5, H6, M1-M13

**整体评估**: 设计方向无争议，文档合同一致性是核心改进领域。修复 4 个 Blocker 后进入 R2。

---

*Speaker 裁决结束。R2 入场条件共 9 项。*
