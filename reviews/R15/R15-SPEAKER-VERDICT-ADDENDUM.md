# R15 Speaker Verdict Addendum — Phase 2 CrossCheck 补漏综合

**生成条件**: D5 裁决为 A — Phase 2 补充任务完成后追加此文档，保持 R15 可追溯闭环。

## Phase 2 总体评估

4 方向补充任务全部完成（Architect/Security/Designer/Determinism），共产生 **27 项 CrossCheck 发现**。核心结论：Phase 2 补漏**证实而非推翻** Phase 1 的 7 个共识 Blocker — 几乎每一项发现都收敛于 B1-B7 的同一根因。

### Phase 2 Verdict

| 方向 | Verdict | 新增 Blocker | 新增 High | 新增 Medium |
|------|---------|:-----------:|:---------:|:----------:|
| Architect | 2 blockers, 2 high | CX-A2 (Persistence Contract), CX-A3 (Resource Ledger) | CX-A1 (Registry), CX-A4 (Worker lifecycle) | CX-A5 (Admin管线) |
| Security | REQUEST_MAJOR_CHANGES | 0 (同源于B5/B7) | 5 (TLS措辞/sandbox relaxed/联盟滥用/seed生命周期/host budget) | 3 (safe_mode/covert channel/economy visibility) |
| Designer | — | 0 | 3 (snapshot overflow/COLLECT截断UX/MVP经济入口收敛) | 3 (opaque error/simulate命名/visibility preset) |
| Determinism | REQUEST_MAJOR_CHANGES | 0 (同源于B1-B6) | 6 (registry/simulate/ECS manifest/host ABI/budget/snapshot) | 0 |

## Blocker 升级（新共识）

Phase 2 确认以下项目达到共识 Blocker 强度（≥2 方向 Phase 1 + Phase 2 独立确认），需与原 B1-B7 并列处理：

### B8: Persistence Contract 未闭合 — FDB/TickTrace/WAL/对象存储分层

**来源**: Architect Phase 2 (CX-A2), 与 Architect GPT/DSV4, Performance GPT/DSV4 Phase 1 重叠

Phase 2 确认了更具体的断裂面：
- FDB 只提交 `tick head / state checksum / small manifest / object pointer / content hash`
- 大 TickTrace、snapshot delta、replay blob 进入对象存储或日志层
- 必须定义双写顺序、幂等 key、GC 规则、orphan recovery、commit retry 对 TickTrace hash chain 的影响
- replay verifier 输入必须以 FDB commit 的 manifest/hash 为权威

**修正要求**: 产出 Persistence Contract 文档，明确 FDB 事务与对象存储的分层职责、写入顺序、失败语义、GC 策略。

### B9: Resource Ledger 未统一 — allied transfer/PvE budget/定点费率多入口

**来源**: Architect Phase 2 (CX-A3), 与 Economy GPT/DSV4 Phase 1, B7 重叠

Phase 2 确认 `ResourceAmount: u32` 与 `0.01`/`0.5` 等浮点费率共存，allied direct transfer 可绕过 Global/Local 转换损耗。必须：
- 建立唯一 Resource Ledger / Transfer Gateway
- 所有小数费率改为 basis points / ppm 定点 schema
- PvE budget 写成确定性账本（global/zone/player/event window）

## High 优先级新增（Phase 2 特有）

### H1: CommandAction Registry 必须进入 TickTrace manifest

**来源**: Architect Phase 2 (CX-A1), Determinism Phase 2

Core CommandAction vs CustomActionRegistry 边界未冻结。Replay 必须记录 `core_idl_version`、`world_action_manifest_hash`、`validator_version`。所有 Vanilla action 必须从 World Action Manifest 生成，不得手写散落表格。

### H2: WASM Worker Pool 生命周期残留状态

**来源**: Architect Phase 2 (CX-A4), Determinism Phase 2

Long-lived worker pool + per-tick Store reset 是现实取舍，但 Store/Instance/Memory/CallerContext/HostCallCounters 的生命周期未表格化。必须产出 Sandbox Lifecycle Matrix：哪些可复用、哪些 per invocation 新建、reset 失败时 worker 销毁策略、跨 tick 残留检测 CI。

### H3: Snapshot Overflow / COLLECT 截断的 UX 公平性

**来源**: Designer Phase 2 (Items 1-2)

当前 256KB cap 在 RCL8 高密度下的静默截断即使技术上是确定性的，玩家也无法区分"系统截断"与"策略失败/脚本 bug"。必须：
- Snapshot 包含 `truncated=true` + 被截断实体类别/数量
- 区分 player-caused 与 system-caused 0-command tick
- 竞技世界禁止影响 tactical legality 的静默截断

### H4: `swarm_simulate` 必须定义为 side-effect-free fork

**来源**: Designer Phase 2 (Item 4), Determinism Phase 2

`swarm_simulate` 当前可能复用 Bevy World/worker pool/RNG stream/cache，导致后续真实 tick 污染或形成战术 oracle。必须定义为：独立 namespace seed、所有 caches 禁用/独立、不写入 TickTrace/fuel ledger、输出强制标注 `authoritative=false` + `not_predictive` badge。

### H5: Host Function ABI 确定性优先级

**来源**: Determinism Phase 2

Host function 的 memory bounds/buffer too small/visibility redaction/budget exhausted/timeout 优先级未定义，不同节点可能返回不同 error → 不同 CommandIntent。必须建立 `HostErrorPriority` 表：memory bounds > schema > per-call > per-player > per-room > global > timeout。

### H6: Global Admission Control 必须 deterministic

**来源**: Determinism Phase 2

当前 COLLECT admission 可能依赖 worker 可用性或 wall-clock race。必须改为：按 canonical active player order / fair-share budget 先裁决再执行，裁决结果记入 TickTrace。Per-player 与 global budget 冲突时定义固定优先级。

## Designer 专属 High（产品/UX 方向）

### DH1: MVP 经济入口收敛

**来源**: Designer Phase 2 (Item 5)

Market/Contracts/Merchant/allied transfer 同时进入 MVP 会稀释核心乐趣并放大 abuse 面。建议：
- allied transfer 降级为受限、延迟、带税/配额/审计的合作赠与
- Market Contracts、Merchant、P2P offer 统一标为 Future Economy RFC
- Challenge Board 先做 non-transfer 的 bounty/replay share

### DH2: Safe Hint Ladder — visibility-first error 的分层调试体验

**来源**: Designer Phase 2 (Item 3)

visibility-first error 安全目标正确但新手全 opaque 会致命。建议分层：competitive 返回安全类别 → practice/replay 提供不泄露坐标的修复建议 → training world 启用详细解释。

## 修订优先级排序

Phase 2 揭示了 B1-B9 + H1-H6 + DH1-DH2 之间的强依赖关系。按 Phase Ordering 建议：

```
1. API/IDL + Registry Manifest (B1, B4, H1) ──── 先冻结数据合同
2. Persistence Contract (B8) ───────────────────── 再冻结存储合同
3. Resource Ledger (B9, B7) ────────────────────── 再统一经济入口
4. Phase 2b System Manifest (B2) ───────────────── 再冻结执行顺序
5. Sort Key / Replay Envelope (B3, H5, H6) ───── 再冻结确定性输入
6. Authorization Matrix + Sandbox (B5, H2) ────── 再冻结安全边界
7. Capacity Budget (B6) ────────────────────────── 最后标定性能容量
8. UX / Designer contracts (H3, H4, DH1, DH2) ─── 并行推进产品合同
```

## R15 最终判决维持

Phase 2 没有发现能推翻 R15 Verdict 的新证据。**REQUEST_MAJOR_CHANGES 维持，NOT FROZEN**。

Phase 2 将 Blocker 从 7 个补充为 **9 个（B1-B9）**，High 从 7 个扩充为 **15 个（A-H1~T-H1 + H1~H6 + DH1~DH2）**，但本质上不是发现新问题，而是将 Phase 1 的跨方向疑点验证为确定性问题，并补充了具体闭合条件。
