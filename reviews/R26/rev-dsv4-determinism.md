# R26 Closure Verification — Determinism Reviewer (rev-dsv4-determinism)

> R26 窄闭合验证轮次：验证 R25 REOPEN/WEAK 项是否已闭合。

## Verdict

**CONDITIONAL_APPROVE**

理由：8 项验证中 3 项完全闭合（CLOSED），2 项部分闭合（PARTIAL），3 项存在残差（GAP）。B3 和 R3 的残差涉及跨文档算法不一致（tick-protocol truncation vs snapshot-contract），构成确定性风险。B4 和 R5 为文档标注计数/数值漂移。R7 为 auth.md 内部自相矛盾。所有问题均不阻塞实现，但需在 Freeze 前修复。

---

## REOPEN 项（R25 — 已修复 → 逐项验证闭合）

### B3: Tick budget — tick-protocol EXECUTE 500ms → 硬超时天花板引用 engine.md budget

**Verdict: GAP**

| 检查项 | 文件 | 位置 | 状态 |
|--------|------|------|:---:|
| engine.md EXECUTE budget | engine.md §3.4.1 | L295 | `≤400ms` ✅ |
| tick-protocol.md EXECUTE timeout | tick-protocol.md §2 | **L74** | **`500ms`** ❌ |
| tick-protocol 引用 engine.md | tick-protocol.md | — | **无引用** ❌ |

**残差**：tick-protocol.md L74 仍保留旧值 500ms，未引用 engine.md §3.4.1 为权威 budget table。engine.md 已对齐到 400ms，但 tick-protocol 作为核心规范未同步。

**所需修复**：tick-protocol.md L74 `超时: 500ms` → `超时: 400ms（权威 budget 见 design/engine.md §3.4.1）`

---

### B4: MCP 工具清单 — (54)→(56); security spec Authority note 替代"已移除"

**Verdict: PARTIAL**

| 检查项 | 文件 | 位置 | 状态 |
|--------|------|------|:---:|
| security spec 指向 API Registry 权威 | 03-mcp-security.md | L223-227 | ✅ 正确引用 56 工具 |
| security spec 不再声称"已移除但仍 active" | 03-mcp-security.md | §4 | ✅ 通过 Capability Profile 限制替代删除 |
| API Registry 实际工具数 | api-registry.md §3.2 | 表格 | **56** 个 game_api 工具 ✅ |
| API Registry §3 头部计数标注 | api-registry.md §3 | L209 | **"54"** ❌ |

**残差**：api-registry.md §3 头部标注 "共计 54 个活跃工具 (game_api)"，但实际表格枚举 56 个工具（Onboarding 10 + Auth 2 + Play 16 + Deploy 7 + Debug 8 + Admin 6 + SDK 1 + Arena 4 + Resources 2 = 56）。头部计数与表格内容不一致。

security spec 的 Authority delegation 已正确：03-mcp-security.md §4 声明 "MCP 工具权威清单见 API Registry §3.2 — 56 工具"，不再重复声明工具列表，不再出现 "已移除但仍 active" 矛盾。

**所需修复**：api-registry.md L209 `共计 54 个活跃工具` → `共计 56 个活跃工具`

---

## WEAK 项（R25 WEAK_CONFIRMED — 验证残留已清理）

### R3: tick-protocol snapshot truncation → 纯引用 snapshot-contract

**Verdict: GAP**

| 检查项 | 文件 | 状态 |
|--------|------|:---:|
| tick-protocol truncation 算法 | tick-protocol.md §2.3 | **自有一组截断算法** ❌ |
| snapshot-contract truncation 算法 | snapshot-contract.md §1 | **另一组截断算法** ❌ |
| tick-protocol 引用 snapshot-contract | tick-protocol.md | **无引用** ❌ |

**两组不兼容的截断算法并存**：

| 维度 | tick-protocol.md §2.3 | snapshot-contract.md §1 |
|------|----------------------|------------------------|
| 桶数 | 4（关键/高优先/中优先/低优先） | 6 距离桶（0-6） |
| 排序键 | (distance, entity_id) | (distance_bucket, entity_id 字典序) |
| 关键实体保护 | 列出但未形式化 | 明确定义不可截断前缀 |

tick-protocol.md §2.3 定义了自己的截断算法（分桶权重截断），与 snapshot-contract.md §1（唯一权威）的 6 距离桶 + 字典序排序不同。两处算法均声称确定性，但排序键差异导致相同输入产出不同截断结果——这是 **replay determinism 风险**。

**所需修复**：tick-protocol.md §2.3 删除内联截断算法，改为纯引用：`截断行为见 Snapshot Contract §1（唯一权威）。`

---

### R4: sandbox/IDL host function ABI → api-registry 权威签名

**Verdict: CLOSED**

| 检查项 | 文件 | 位置 | 状态 |
|--------|------|------|:---:|
| host-functions.md 声明权威源 | host-functions.md | L3-7 | ✅ 声明 api-registry.md 为权威 |
| 08-api-idl.md 声明权威源 | 08-api-idl.md | L239-242 | ✅ "权威定义见 API Registry §4" |
| api-registry.md 5 个 host function 签名 | api-registry.md | §4.1 | ✅ 完整 canonical ABI |
| 04-wasm-sandbox.md 引用链路 | 04-wasm-sandbox.md | L3 | 引用 design/interface.md（间接正确） |

host-functions.md 和 08-api-idl.md 均已指向 api-registry.md §4 为权威签名来源。api-registry.md 包含 5 个 host function 的完整 ABI 签名。sandbox 规范通过 design 层间接引用，链路闭合。

---

### R5: 08-api-idl RangedAttack 100→150, Recycle→lifespan-proportional

**Verdict: PARTIAL**

| 检查项 | 文件 | 位置 | 当前值 | 期望值 | 状态 |
|--------|------|------|--------|--------|:---:|
| RangedAttack body cost | economy.idl.yaml | L329 | 150 | 150 | ✅ |
| RangedAttack body cost | 08-api-idl.md | L230 | **100** | 150 | ❌ |
| Recycle 退还公式 | economy.idl.yaml | §2.1 | lifespan-proportional 10%-50% | lifespan-proportional | ✅ |
| Recycle 退还公式 | 08-api-idl.md | L322 | **"退还 50%"** | lifespan-proportional | ❌ |

economy.idl.yaml 已正确更新（RangedAttack=150，Recycle=lifespan-proportional），但 08-api-idl.md 中的 body_cost 表和 Recycle 描述仍保留旧值：
- L230: `RangedAttack: { Energy: 100 }` — 应为 150
- L322: `回收 drone，退还 50% body part 资源` — 应为 lifespan-proportional 10%-50%

08-api-idl.md 第 §5 表（L320）独立于 body_cost 表（L225-233），两处均未更新。

**所需修复**：
1. 08-api-idl.md L230 `RangedAttack: { Energy: 100 }` → `RangedAttack: { Energy: 150 }`
2. 08-api-idl.md L322 `退还 50% body part 资源` → `退还 lifespan-proportional 10%–50%（权威公式见 economy.idl.yaml §RecycleRefund）`

---

### R6: D2-A leaderboard→Arena, world_stats→Play

**Verdict: CLOSED**

| 检查项 | 文件 | 位置 | 状态 |
|--------|------|------|:---:|
| World 无竞争榜单 | modes.md | §9.1 L24 | ✅ "World 不设竞争榜单" |
| World 非竞争展示 | feedback-loop.md | §6 L327 | ✅ "趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏" |
| leaderboard 工具在 Play profile | api-registry.md §3.2 | L256 | Play 分类（World 玩家可用） |
| leaderboard 非 Arena 独占 | api-registry.md §3.4 | L369 | Play profile → World 玩家 + Arena spectator |

设计意图已满足：modes.md 明确 World 无竞争排名，feedback-loop.md 明确 World 仅非竞争展示。leaderboard 工具位于 Play profile（World 玩家可调用），但 modes.md 的设计约束高于工具 availability——World 模式下排行榜为空或仅展示非竞争统计。工具分类位置不影响核心设计意图。Arena 的 leaderboard 通过 Arena spectator 获得 Play profile 访问。

---

### R7: CodeSigning default 7d→30d

**Verdict: GAP**

| 检查项 | 文件 | 位置 | 当前值 | 期望值 | 状态 |
|--------|------|------|--------|--------|:---:|
| 证书类型表 CodeSigningCertificate TTL | auth.md §5.3 | L274 | **7d** | 30–180d | ❌ |
| 多设备表 常用设备 TTL | auth.md §5.5 | L296 | 30–180 days | 30–180d | ✅ |

auth.md 内部自相矛盾：
- §5.3 证书类型表（主表）：CodeSigningCertificate TTL = **7d**
- §5.5 多设备证书生命周期表：常用设备 CodeSigningCertificate TTL = **30–180 days**

R25 B6 已闭合为 "CodeSigningCertificate TTL 30–180d 单一区间"，但 §5.3 主表未被更新。§5.5 的设备级别表正确反映了新值。

**所需修复**：auth.md §5.3 L274 `CodeSigningCertificate TTL: 7d` → `30–180 days`（与 §5.5 L296 一致）

---

### R8: feedback-loop Tournament/MVP → 房间制+非竞争展示

**Verdict: CLOSED**

| 检查项 | 文件 | 位置 | 状态 |
|--------|------|------|:---:|
| Arena 房间制 | modes.md | §9.1 L88 | ✅ "Arena 采用房间制——玩家创建比赛房间" |
| 无自动匹配/天梯/赛季 | modes.md | §9.1 L88 | ✅ 明确排除 |
| World 非竞争展示 | feedback-loop.md | §6 L327 | ✅ "趣味展示（非竞争排名）" |
| Arena Tournament/League 为 P1+ | modes.md | §9.1 L88 | ✅ |
| Arena 排行榜分 league | feedback-loop.md | §6 L337 | ✅ "排行榜按 league 分区" |

feedback-loop.md §6 已将 World 模式定位为 "趣味展示（非竞争排名）"，Arena 模式为 "比赛制"+"排行榜按 league 分区"。modes.md 明确 Arena 房间制、无自动匹配。Tournament 被列为 P1+ 扩展。设计意图完全闭合。

---

## 状态汇总

| ID | 描述 | 类型 | 状态 |
|----|------|------|:---:|
| B3 | Tick budget EXECUTE 500ms→400ms | REOPEN | **GAP** |
| B4 | MCP 工具清单 54→56 + Authority note | REOPEN | **PARTIAL** |
| R3 | tick-protocol snapshot truncation→纯引用 | WEAK | **GAP** |
| R4 | sandbox/IDL host function ABI→api-registry | WEAK | **CLOSED** |
| R5 | 08-api-idl RangedAttack 100→150, Recycle | WEAK | **PARTIAL** |
| R6 | leaderboard→Arena, world_stats→Play | WEAK | **CLOSED** |
| R7 | CodeSigning default 7d→30d | WEAK | **GAP** |
| R8 | Tournament/MVP→房间制+非竞争展示 | WEAK | **CLOSED** |

**闭合率**：3/8 (37.5%) 完全闭合 | 5/8 (62.5%) 存在残差

---

## 确定性专项评估

以下为基于确定性评审视角的额外验证：

| 检查项 | 状态 | 备注 |
|--------|:---:|------|
| **R3 截断算法双轨** | ⚠️ | tick-protocol §2.3 vs snapshot-contract §1 使用不同排序键 → 相同输入不同截断 → replay 确定性风险 |
| B3 EXECUTE timeout 双轨 | ⚠️ | tick-protocol 500ms vs engine 400ms → 硬超时行为分歧 |
| f64 禁止 | ✅ | 全定点 bp/MilliUnits/micro_cost |
| host function ABI 统一 | ✅ | 全委托 api-registry.md §4 |
| ECS 调度确定性 | ✅ | 29 systems serial spine（06-phase2b-system-manifest.md） |
| 种子洗牌确定性 | ✅ | Blake3 XOF from world_seed + tick |
| 快照一次性构建 | ✅ | O(entities) not O(players × entities) |
| COLLECT 跨重试缓存 | ✅ | collect_id/attempt_id/commit_id |

**新增确定性风险**（本次发现）：
- **DET-R3**：截断算法双轨 — tick-protocol.md §2.3 和 snapshot-contract.md §1 定义了不同的确定性排序键。若实现者按 tick-protocol 实现，replay 将产出与 snapshot-contract 不同的截断结果。

---

## 修复建议

### FIX-B3: tick-protocol.md EXECUTE timeout
**文件**: `specs/core/01-tick-protocol.md` L74
```diff
- 超时: 500ms
+ 超时: 400ms（权威 budget 见 design/engine.md §3.4.1）
```

### FIX-B4: api-registry.md 工具计数
**文件**: `specs/reference/api-registry.md` L209
```diff
- 共计 54 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)
+ 共计 56 个活跃工具 (game_api) + 11 个 Auth API 工具 (auth_api)
```

### FIX-R3: tick-protocol.md 截断引用
**文件**: `specs/core/01-tick-protocol.md` §2.3
删除 §2.3 中的内联截断算法（关键桶/高优先/中优先/低优先），改为：
```
快照截断行为见 Snapshot Contract §1（唯一权威）。
```

### FIX-R5: 08-api-idl.md 数值对齐
**文件**: `specs/gameplay/08-api-idl.md`
- L230: `RangedAttack: { Energy: 100 }` → `RangedAttack: { Energy: 150 }`
- L322: `退还 50% body part 资源` → `退还 lifespan-proportional 10%–50%（权威公式见 economy.idl.yaml §RecycleRefund）`

### FIX-R7: auth.md CodeSigningCertificate TTL
**文件**: `design/auth.md` L274
```diff
- | `CodeSigningCertificate` | WASM/module deploy 签名 | 7d | 只能签 `module_hash + metadata` |
+ | `CodeSigningCertificate` | WASM/module deploy 签名 | 30–180 days | 只能签 `module_hash + metadata` |
```

---

*评审日期: 2026-06-20 | 评审员: rev-dsv4-determinism (DeepSeek V4 Pro)*