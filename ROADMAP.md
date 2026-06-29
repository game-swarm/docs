# Swarm R40 实施 ROADMAP

> R39→R40 CV APPROVE。双模型审计 + 2 轮 Codex 实施。**已完成。**

## 实施结果

| 轮次 | 模型 | Commit | 变更 | Tests |
|------|------|--------|------|-------|
| Codex R1 | GPT-5.5 | `ecc6293` | 25 files, +705/-109 | 336 ✓ |
| Codex R2 | GPT-5.5 | `468e7ed` | 44 files, +1336/-660 | 336 ✓ |
| **合计** | | **2 commits** | **+2041/-769** | **336 ✓** |

## 已完成的 GAP

### ✅ Batch A: DAG 基础
- [x] C1: scheduler 29→31 systems, v2→v3
- [x] C2: world.rs chain 重排对齐 manifest spine
- [x] C5: status_advance_system 注册到 world.rs

### ✅ Batch B: Status Buffer 架构
- [x] C3: 8 个 typed buffer 系统新建 (hack_buf ~ fabricate_buf)
- [x] C3: 8 个 Buffer 组件 + LeechState/FabricateState 组件
- [x] C3: Buffer 系统注册到 world.rs Parallel Set B
- [x] H3: reducer priority chain 扩展到 8 种
- [x] H3: status_advance 处理 Leech/Fabricate

### ✅ Batch C: HP Writer 合同
- [x] C4: regen→PendingHeal, combat→PendingDamage/PendingHeal
- [x] H1: S15 damage_application canonical reduce + death guard

### ✅ Batch D: 实体生命周期
- [x] C6: PendingEntityCreation 定义 + build/spawn 改为写 queue
- [x] H2: MarkedForDeath→DeathMark 全局重命名

### ✅ Batch E: ActionRegistry
- [x] C9: (Codex 做了部分 — 需后续确认 Action { type, payload })

### ✅ Batch F: Snapshot/Persistence
- [x] C7: WorldSnapshot capture/restore 8 StatusState + 8 Buffer + ResourceLedger
- [x] H4: TickTrace system_manifest_hash + action_manifest_hash
- [x] H6: WorldDelta entity_changes tracking 实现
- [x] H5: FDB/snapshot sync (部分)

### ✅ Batch G: Security/Auth
- [x] C8: MCP per-tool auth_mode 枚举定义
- [x] H7: mcp_tool_source 完备
- [x] H8: MCP auth 工具名称对齐

### ✅ Batch H: Docs/Naming
- [x] M1: RejectionReason 去重
- [x] M3: MarkedForDeath→DeathMark, SpecialAttackIntent→StatusActionIntent

## 遗留项（需人工确认）

- [ ] C9: CommandAction 是否仍有 Attack/RangedAttack/Heal enum variants？
- [ ] M2: 额外系统 (starting_resources, cargo_in_transit, global_storage 等) 是否列入 manifest？

## 验收

- [x] `cargo build` 成功
- [x] `cargo test --lib` 336 passed, 0 failed
- [x] manifest system count = 31
- [x] grep `drone.hits = ` 不在 regen/combat 中（仅 S15）
- [x] grep `MarkedForDeath` src/ = 0
- [x] git push origin main