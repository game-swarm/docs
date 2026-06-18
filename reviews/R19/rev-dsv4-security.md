# R19 安全评审 (DSV4)

**评审员**: rev-dsv4-security (DeepSeek V4 Pro)
**日期**: 2026-06-18
**权威源**: `specs/reference/game_api.idl.yaml` + `specs/reference/api-registry.md`

---

## 总体 Verdict: CONDITIONAL_APPROVE

1 个安全 GAP (DA1)，2 个经济参数 CrossCheck。7 个 Consensus Blocker 全部 CLOSED。

---

## 逐项判定表

### R18 共识 Blocker

| ID | 状态 | 证据 |
|----|------|------|
| B1: YAML vs Markdown 双写不一致 | **CLOSED** | YAML IDL 声明权威源，Markdown 声明自动生成。api_version=0.3.0、19 CommandAction、35 RejectionReason、46 MCP Tools、5 Host Functions、22 TickTrace 字段 — 完全一致 |
| B2: RejectionReason 未闭合 | **CLOSED** | 35 canonical codes (Pipeline 2 / Validation 26 / MCP 3 / Runtime 6) + debug_detail 512B + detail_level enum 完整 |
| B3: MCP Tool 三套名称空间 | **CLOSED** | 46 tools × 5 安全列，7 分类，YAML 与 Markdown 一致 |
| B4: Tick/Trace/Persistence 分叉 | **CLOSED** | Deploy §10 + Persistence §11 统一。TickTrace Envelope 22 字段。terminal_state 7 variants |
| B5: 安全字段未入机器源 | **CLOSED** | YAML IDL 每 tool 含 replay_class/required_scope/subject_source/visibility_filter/rate_limit_key — 5 安全列全量入机器源 |
| B6: 经济单源未闭合 | **CLOSED** | 经济 API (swarm_get_economy/swarm_get_economy_trend) + ResourceOperation + 容量限制在 api-registry 中作为权威合同注册 |
| B7: 容量合同不可证明 | **CLOSED** | 25 容量参数在 YAML §5 和 Markdown §5 一致：worker_pool_max=256, pathfinding_budget=100000, global_storage_capacity=1000000 等 |

### R18 用户裁决

| ID | 状态 | 证据/位置 |
|----|------|-----------|
| D1: api-registry.md 全量生成 | **CLOSED** | 声明"由 game_api.idl.yaml 自动生成"，10 节完整覆盖，版本链 0.1.0→0.3.0 |
| D2: RejectionReason canonical+debug_detail | **CLOSED** | YAML `rejection_reason.debug_detail` (512B) + `detail_level` (competitive/practice/training) 完整 |
| D3: Recycle refund lifespan 10-50% | **GAP** | 普通 gameplay Recycle action (index 10) 未指定 refund 率。auth.md §13.1 账户删除 recycle=50%，不是正常游戏 drone 回收 refund |
| D4: Storage tax tiered 0/1/5/20bp | **GAP** | swarm_get_economy 输出含 `storage_tax: f64`，但无分级税率 0/1/5/20bp。分级未在授权文档中出现 |
| D5: blob 异步上传 | **CLOSED** | YAML §11 + api-registry.md §11：async_object_store_upload, fire-and-forget, exponential backoff, FDB manifest |
| D6: soft_launch 3阶段PvP | **N/A** | 不在安全授权文档范围（属 gameplay/modes.md） |
| DA1: deploy_mutation replay_class | **🔴 GAP** | 见下方详细分析 |
| DA2: f64→定点 | **N/A** | MCP 输出 schema 含 f64 (display layer)，引擎内部定点转换无法从授权文档验证；需 Architect 交叉验证 |
| DA3: worker pool 256 default | **CLOSED** | YAML §5: `worker_pool_max: 256`, `worker_pool_size: min(max_pool, active_players)` — 与 api-registry.md §5.5 一致 |

---

## GAP 详细分析

### 🔴 DA1: replay_class 不一致 — swarm_deploy 标记冲突

**冲突位置**：

| 文档 | 位置 | swarm_deploy 的 Replay Class |
|------|------|------------------------------|
| `design/auth.md` | §5.6a (Replay Class 表) | **`deploy_mutation`** — 独立行，FDB version_counter 防重放 |
| `design/auth.md` | §5.6b (授权矩阵) | **`deploy_mutation`** |
| `specs/reference/game_api.idl.yaml` | swarm_deploy 的 `replay_class` 字段 | **`idempotent_mutation`** |
| `specs/reference/api-registry.md` | Deploy category 表格 | **`idempotent_mutation`** |

**auth.md §5.6a 原始定义**（5 类 replay class）：

```
| deploy_mutation | 部署请求——防重放由 FDB version_counter 保证 | FDB version_counter |
| idempotent_mutation | 重复执行结果相同 | Dragonfly nonce + time window（除 deploy 外） |
```

auth.md 明确将 `deploy_mutation` 与 `idempotent_mutation` 分开——后者用 Dragonfly nonce（TTL 300s 窗口），前者用 FDB version_counter（严格一次性）。

**YAML IDL 中**：swarm_deploy 的 `replay_class: idempotent_mutation`，且 YAML IDL 的 replay_class 枚举中没有 `deploy_mutation` 这个值。YAML notes 说 "Uses deploy_mutation pattern"，但正式字段仍写 `idempotent_mutation`。

**安全影响**：若实现侧按 YAML IDL 的 `idempotent_mutation` 实施（Dragonfly nonce + 300s TTL），部署请求在 300s 窗口内可重放——与设计意图（FDB version_counter 严格递增，崩溃后不重放）矛盾。这直接破坏 deploy 防重放保证。

**建议修复**：
1. 在 YAML IDL 中新增 `deploy_mutation` 作为合法 replay_class 值
2. swarm_deploy 的 `replay_class` 字段改为 `deploy_mutation`
3. 重新生成 api-registry.md 后再验证一致性

---

## CrossCheck 建议

以下项目建议由对应方向评审员验证：

| # | 建议 | 目标方向 | 原因 |
|---|------|---------|------|
| 1 | **Recycle refund 率 (D3)**: 普通 gameplay Recycle action 的 refund 机制应明确写入 `gameplay.md` 或 api-registry，确认是否在 10-50% 范围内 | Game Designer | 当前仅账户删除 recycle 在 auth.md §13.1 有 50%，正常 drone 回收无定义 |
| 2 | **Storage tax 分级 (D4)**: 0/1/5/20bp 分级税率应写入经济模型文档，并确保 swarm_get_economy 的 storage_tax 反映了分级逻辑 | Economist / Game Designer | 当前 swarm_get_economy 仅有 `storage_tax: f64` 平值，无分级 |
| 3 | **f64→定点 (DA2)**: 验证引擎内部 ECS 经济/进度状态是否已从 f64 转为定点数 (fixed-point)，确保确定性复现 | Architect | MCP 输出 schema 仍见 f64 (display layer)，引擎内部无法从授权文档判断 |

---

## 评审约束遵守

- [x] 仅读取授权的 6 个文件（`auth_api.idl.yaml` 文件不存在，已记录）
- [x] 未读取 /data/swarm/ 代码仓库
- [x] 未参考旧评审或 reviews/ 目录
- [x] 以 IDL YAML 为权威源
- [x] 非安全方向项目标记 N/A
- [x] 未重新评审设计本身
- [x] 未 brainstorm

---

## 文件清单

- `/tmp/swarm-review-R19/design/README.md` — 已读
- `/tmp/swarm-review-R19/design/auth.md` — 已读 (1781 行)
- `/tmp/swarm-review-R19/specs/security/03-mcp-security.md` — 已读 (396 行)
- `/tmp/swarm-review-R19/specs/reference/api-registry.md` — 已读 (605 行)
- `/tmp/swarm-review-R19/specs/reference/game_api.idl.yaml` — 已读 (1638 行)
- `/tmp/swarm-review-R19/specs/reference/auth_api.idl.yaml` — **文件不存在** (路径不存在于 /tmp/swarm-review-R19/specs/reference/)
