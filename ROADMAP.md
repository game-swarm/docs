# Swarm Implementation ROADMAP

> 仅列出待实现变更。文件互斥：同一 Wave 内任务触碰的文件集完全不相交。
> 系统编号以 `specs/core/06-phase2b-system-manifest.md` 为权威来源（S01-S29）。

---

## 当前状态

| 类别 | 数量 | 说明 |
|------|:----:|------|
| ✅ 已完成 Wave | 20 | W0-W17 (ALL) |
| ✅ Manifest 已实现 | 29 | S01-S29 (ALL) |
| ❌ 完全缺失 | 0 | — |

> **当前提交**: `36fe3d0` — ROADMAP COMPLETE.
> **测试**: 336 lib + 10 economic = 346 total, zero failures.

---

## Wave 完成清单

| Wave | Commit | 测试 | 内容 |
|------|--------|:--:|------|
| W0-W7 | … | … | 基础架构 + 经济 + 战斗 |
| W8 | `af0f48d` | … | S09+S10+S24+S26 stub 修复 |
| W9 | `fe903f2` | … | S14 special_attack_reducer + S15 damage_application |
| W10 | `fc4d66d` | 293 | body_part_match + DisruptedResisted |
| W11 | `f8c6e9f` | 299 | S16 Hack + S17 Drain + S18 Overload |
| W12 | `f8e9bc1` | 308 | S19-S21 + S22 Unique Writer |
| W13 | `bf1910a` | 314 | S23 Aging + S25 Death Cleanup |
| W14 | `7568cef` | 314 | EventLog 反馈循环基础设施 |
| W15a | `115e491` | 327 | Arena 六阶段状态机 |
| W15b | `9b73ae0` | 327 | Arena Security |
| W15c | `ec357f7` | 327 | Arena PvE + Admin |
| S29 | `3aed444` | 324 | resource_ledger ECS |
| W16b | `e5df913` | 334 | 经济平衡测试 |
| W16c | `bf8acff` | 334 | Session + Deploy + Safe Hint Ladder |
| G4 | `c11c215` | 336 | NPC 特殊攻击集成 |
| W17 | `36fe3d0` | 336 | Criterion 性能基准 |

### 架构外/已就位

| 项目 | 状态 |
|------|:--:|
| W16a WASM CDN | swarm_deploy MCP tool 已完整实现 (mcp.rs) |
| W16c CommandSource | source_gate + source_capabilities 已就位 |
| G4 NPC special | 已集成到 npc_combat_system |

---

## Milestones

| Milestone | 判定 | 
|-----------|:--:|
| **M0: Mod Ready** | ✅ |
| **M1: Core Complete** | ✅ |
| **M2: Economy** | ✅ |
| **M3: Combat Foundation** | ✅ |
| **M4: Gameplay Systems** | ✅ |
| **M5: Arena** | ✅ |
| **M6: Production Ready** | ✅ |
