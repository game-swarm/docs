# Swarm — 实现路线图

> **基于 R21 FROZEN 文档的代码对齐路线图。** DESIGN.md = 目标架构, ROADMAP.md = 实现追踪。

**更新日期**: 2026-06-18 | **状态**: ✅ 第一轮对齐完成
**测试基线**: engine 206 | sandbox 14 | gateway 16 | sdk-rust 8 | sdk-ts 11 | frontend 13

---

## 实现进度

| 模块 | 状态 | 说明 |
|------|------|------|
| MCP 工具 | ✅ 64/64 | 代码 ToolInfo 与 api-registry.md 完全对齐 |
| RejectionReason | ✅ 79 variants | 含 47 canonical + 32 debug_detail |
| Legacy MCP 清理 | ✅ | 12 个遗留工具已移除 |
| CommandAction | ⚠️ | `SpawnDrone`→`Spawn` enum 已统一，tutorial.rs 仍有 6 处引用 |
| Auth 模块 | ✅ | src/auth/mod.rs 77 行 |
| Economy 模块 | ✅ | src/economy.rs 688 行 |
| API 文档 | ✅ | commands.md + mcp-tools.md 已刷新 |

---

## 遗留项

### SpawnDrone tutorial.rs 残留 (6 处)

`src/tutorial.rs` 仍使用 `SpawnDrone` 字面量。非关键路径（tutorial 模式），低优先级。

### Empire Upkeep

设计声明领土维护成本系统（protocol hook + Vanilla 公式）。代码仅有 drone 级 `memory_upkeep`，无领土级 empire upkeep。

---

## 设计 vs 实现差距

| ID | 设计需求 | DESIGN § | 状态 |
|----|---------|----------|------|
| G1 | Empire Upkeep（领土维护成本） | gameplay §8.2 | ❌ 未实现 |
| G2 | Leech SpecialEffect | gameplay §8.5 | ✅ 已实现 |
| G3 | Fabricate CustomAction | gameplay §8.5 | ✅ 已实现 |
