# R4 Clean-Slate Architecture Review — rev-claude-architect

**评审员**: rev-claude-architect (Claude Opus 4.7)
**视角**: 系统架构 / 模块划分 / 数据流 / 边界定义 / 扩展性
**评审范围**: DESIGN.md + tech-choices.md + ROADMAP.md + 9 specs (01-09)
**评审时间**: 2026-06-16

---

## Verdict: **CONDITIONAL_APPROVE**

R4 文档体在 R2/R3 评审基础上有显著收敛。R3 的两个 BLOCKER（ECS RW 矩阵 / Bevy↔FDB 双权威源回滚不对称）已闭合：specs/01 §3.4 给出清晰的并行安全 RW 矩阵，specs/01 §3.5 显式声明 Phase 2a 前 `world.snapshot()` + commit 失败 `world.restore(snapshot)` + COLLECT 跨重试缓存。可见性单一函数（specs/05 §1）覆盖到 host function（§3.0），堵住了 R3 的 WASM 查询绕过。TOCTOU 合同（specs/01 §3.3）显式列出 5 条规则。Source Gate + Ed25519 部署证书 + nonce/CRL/epoch（specs/09）+ Browser/Agent transport 拆分（specs/03 §2）—— B4/B5 落地完整。

但新发现的关切中 A1 是 Critical（tick 预算合计超过 tick interval 目标），A2/A3 是 High（Phase 顺序文档不一致 + Bevy snapshot 性能与 "10k 玩家" 声明冲突）。这些可在 spec 修订内闭合，不要求重新设计核心架构——故为 CONDITIONAL_APPROVE 而非 REQUEST_MAJOR_CHANGES。

---

## Strengths（架构亮点）

### S1. 三层信任模型清晰，权限随运行时降级
WASM（不可信，进程隔离 + fuel/epoch + cgroup）→ Rhai（服主信任，AST 节点预算 + 能力白名单 + 进程隔离 + Ed25519 模组签名）→ Rust 核心（不可变）。每层的隔离机制与信任等级匹配，没有"信任下沉"的反向耦合。

### S2. Deferred Command Model 从 ABI 层切断 mutating host function
DESIGN §5.2 + specs/04 §3.3 + IDL 一致声明：`host_move`/`host_attack`/`host_build` 等不得作为 host function 暴露。所有变更走 `tick() → JSON` 延迟模型 → Source Gate → validate_and_apply()。这是单一管线的 ABI 强制，比"代码约定不调用"强得多。

### S3. Determinism Contract（DESIGN §8.8）覆盖完整
Blake3 全栈（Hash + PRNG + MAC）+ IndexMap + 整数/定点数 + .chain() + seeded shuffle + indexmap 替代 std::HashMap。confidence-of-replay 链路：state checksum + mods_lock + world_config + commands → execute_deterministic == recorded_state。tech-choices.md §8 给出"为什么是 Blake3"的清晰理由（一原语三用途）。

### S4. Source Gate + 不可伪造 Auth Context
specs/09 §2 来源矩阵覆盖 10 类 source，每类的 auth_context / gameplay / audit / rate_limit / visibility / budget 全部显式建模。CommandIntent（仅 sequence + action）→ RawCommand（服务端注入 player_id/source/tick）→ ValidatedCommand 三层升级清晰。配合 Ed25519 部署证书 + 60s nonce + CRL + epoch（§3），客户端无法伪造身份或重放。

### S5. TOCTOU 合同明确化（specs/01 §3.3）
5 条规则：
1. Spawn pending 不可见（同 tick 后续命令看不到新 drone）
2. Hack 状态下原 owner 仍以原始 owner 身份校验
3. Per-drone per-tick action quota（防 Transfer chain amplification）
4. fuel/wall-clock 耗尽 → 完整输出丢弃，不读取部分输出
5. 指令队列不跨 tick

这把"inline 模型 + 玩家先到先得"的边界条件写成强保证。

### S6. 可见性单一函数贯穿全输出面
`is_visible_to(entity, player, tick)` 覆盖：snapshot、host function、MCP tool、WebSocket 增量、REST API、replay、spectator view。specs/05 §3.0 显式说明 host function 的 `get_objects_in_range` / `path_find` 也走同一过滤——这是 R3 评审反馈的良好落地。

### S7. Bevy↔FDB 双权威源回滚对称
specs/01 §3.5：Phase 2a 前 `snapshot = world.snapshot()` 深拷贝（含完整 Resource + Component 清单）→ FDB commit 失败 → `world.restore(snapshot)` + COLLECT 缓存复用 → 跨重试 fuel 上限 = 1×MAX_FUEL → 连续 3 次失败降级。FDB 故障注入 CI 测试（§3.5）验证 state_checksum 一致性。这是 R3 BLOCKER A2 的完整回应。

### S8. MCP Browser/Agent Transport 拆分（specs/03 §2）
Browser 走 Origin/CSRF + SameSite=Strict + Sec-Fetch-* 头校验；Agent 走 mTLS 或 Ed25519 signed request；token audience 三方绑定（gateway_origin + world_id + browser/cli）；拒绝跨协议混淆。配合 §2.3 的 6 种 DNS rebinding 防御措施——攻击面几乎无遗漏。

### S9. Three-tier Vanilla Ruleset / Layer Model（DESIGN §8.2）
Layer 1（Core IDL，编译期冻结）/ Layer 2（world.toml 调参）/ Layer 3（实验性 schema 扩展）+ target_manifest_hash 编译期绑定。Vanilla World 固定 hash `vanilla-v1` 跨世界兼容，模组世界标 `[MOD]` 不参与官方排名。多世界 SDK 错配从设计层防止。

### S10. 三种结果等价合同显式建模信息泄露（specs/02 §3.12 Overload）
"成功 / 触地板 / 已在地板"返回相同 Ok + 相同 cost + 相同 cooldown。这把"信息泄露不应可观测"从行为约定上升为合同。同类设计可推广到其他特殊攻击。

---

## Concerns（关切，按 severity 排序）

### A1. **Tick 三阶段总预算超过 3000ms tick interval 目标** [Critical]

文档声明：
- DESIGN §3.2 / specs/01 §1.4：tick interval 目标 3000ms
- specs/01 §2.2：COLLECT 超时 = 2500ms
- specs/01 §1.4：EXECUTE 超时 = 500ms
- BROADCAST 时长无预算

简单加法：2500 + 500 + BROADCAST = **至少 3000ms**，已经把 tick interval 吃满。但 EXECUTE 内含：
- Phase 2a inline 应用（500 条/玩家 × 玩家数）
- Phase 2b ECS systems（部分串行）
- FDB 原子提交（最多 3 次重试，**每次失败后 1s 等待**）

specs/01 §3.5 + §6.1：FDB commit 失败 → 等 1s 重试 → 连续 3 次失败 → 引擎降级。**单 tick 实际墙钟可达 2500 + 500 + 3×1000 + 3×500 = 6500ms**。

**问题**：
- tick interval 是"目标"还是"硬上限"？
- 单 tick 跑超时是否阻塞下一 tick？还是丢 tick？文档无定义
- `tick_duration_p99 > 2800ms` 仅是 warning（specs/01 §5），但常态加法已超

**建议**：
1. 明确 tick interval 与各阶段超时的关系（是否分离调度循环 vs 实际计算预算）
2. FDB 重试是否应放在 tick 之外（异步重试 + tick 跳过）
3. 重新评估 COLLECT 2500ms 是否合理——这意味着 COLLECT 占 83% tick 预算

---

### A2. **Phase 2b 系统调度顺序文档前后不一致** [High]

| 文档位置 | 主线顺序 |
|---------|---------|
| DESIGN §3.2 | death_mark → spawn → combat → regen/decay → death_cleanup |
| specs/01 §3.4 | (death_mark, spawn, combat).chain() + (regen, decay).before(death_cleanup) |
| specs/07 §3（world_rules.rs 示例） | (death_mark, spawn, **regeneration**, combat, decay, death_cleanup).chain() |

specs/07 §3 把 `regeneration_system` 放在 `combat_system` 之前的 chain（串行），而 DESIGN/specs/01 是并行 + 仅约束 before death_cleanup。

**影响**：
- 实现者读 specs/07 会得到不同的 Bevy 调度图
- 语义差别：能源点先恢复再被战斗后的 drone harvest？还是先 combat 结算再 regenerate？
- regeneration 是否需要在 combat 之后（确保被攻击的 source/structure 不再生）？

**建议**：以 specs/01 §3.4 为唯一来源，修正 DESIGN §3.2 + specs/07 §3 的示例代码使三处统一。

---

### A3. **Bevy World snapshot 模型不支持声明的 10k 玩家规模** [High]

specs/01 §3.5：每 tick Phase 2a 前 `snapshot = world.snapshot()` 深拷贝完整 Bevy World（所有 Resource + 所有实体的所有 Component）。

DESIGN §3.1a 扩展声明：
| Tier | 玩家数 | 架构 |
|------|--------|------|
| 1 | 500 | 单 Engine + 单 FDB（MVP） |
| 2 | 1k–5k | 单 Engine + FDB 分层缓存 |
| 3 | 不限 | 水平分片（远期） |

**问题**：
- Tier 2 上限 5k 玩家 × 平均 50 drone × 多 component = 数百万 entity 的 snapshot/restore
- 每 tick 一次深拷贝 + restore 在 3s 周期内不可能完成（仅复制就可能 >1s）
- specs/01 §3.5 没有给出 snapshot 预算或性能目标
- 没有讨论 copy-on-write / 增量 snapshot / persistent data structures 等替代方案

**建议**：
1. 明确 snapshot 模型的实体规模上限和墙钟预算
2. 探索 Bevy 的 `Resource<EntityHashMap>` + 修改集（modification set）模式：只快照本 tick 触及的实体
3. 或：声明 Tier 1（500 玩家）下 snapshot 模型有效，Tier 2 需要替换为 incremental snapshot——但此 spec 缺失则 Tier 2 实际不可达

---

### A4. **代码传播 system 与 spawn 的时序边界未定义** [Medium]

specs/07 §3：`code_propagation_system.before(spawn_system)`

specs/07 §4 实现示例：
```
if version.updated_at + propagation_delay > current_tick() {
    version.fallback_to_previous();
}
```

**边界**：
- spawn 在 propagation 之后——新 drone 没有 propagation_delay 历史
- 玩家在 tick N 部署 v2 → tick N+1 spawn 一个 drone，此 drone 用 v1 还是 v2？
- 如果用 v2：spawn 点等同于"零距离传播"，新 drone 立即获得新代码
- 如果用 v1：fallback_to_previous 在没有"previous"时如何 fallback？

文档未明确"出生时的代码版本归属"逻辑。

**建议**：spawn_system 中显式定义 `new_drone.code_version = code_propagation_at(spawn_position)`，把 spawn 视为 propagation 在出生地的"瞬时查询"。

---

### A5. **MCP_Query swarm_get_snapshot 与 WASM tick() 的快照视图存在 1 tick 时差** [Medium]

specs/03 §4.2：`swarm_get_snapshot` 限流 1/tick，"获取玩家可见的世界快照（同 WASM tick() 接收的输入）"。

但执行时序：
- COLLECT 阶段（tick N 起点）：WASM 接收 tick N-1 的快照
- BROADCAST 后（tick N 末）：MCP 查询返回 tick N 的快照（已 commit 到 FDB）

**影响**：
- AI agent 通过 MCP 决策 + WASM 执行 → 信息源时差 1 tick
- 这本身不是漏洞但应显式建模在文档中
- AI 可能基于 tick N 的 snapshot 生成 WASM v2 部署，但 tick N+1 时世界已是 N+1 状态——和 WASM 看到的（N）不一致

**建议**：specs/03 + specs/05 明确 MCP query 与 WASM snapshot 的时间关系。考虑增加 `snapshot_tick` 字段让 AI 知道自己看的是哪个 tick。

---

### A6. **Refund Credit 的 deploy-reset 例外条款存在滚动 refund 利用空间** [Medium]

specs/02 §7.2：refund credit 跨 session 不得转移；deploy 触发清零。**例外**："同一 session 内的迭代部署（同 session_id）不清除 credit"。

**攻击场景**：
1. 玩家保持长 session（30s 心跳续期，session 永不超时）
2. 部署 v1 → 故意触发大量 SourceEmpty 拒绝 → 累积 refund credit
3. 同 session 部署 v2 → credit 保留 → v2 直接获得放大 fuel budget
4. 重复

**问题**：
- 例外条款的安全模型未定义（"正常迭代"和"攻击模式"如何区分）
- specs/02 §7.3 退还上限 `MAX_FUEL × 10%/tick` 仅约束单 tick，跨 tick 累积可达多倍 MAX_FUEL
- 连续 3 tick 高退还率 throttle（§7.3）触发条件是 "退还率 > 80%"，但攻击者可保持 50% 退还率绕过

**建议**：
1. 移除"同 session 不清除 credit"例外，改为：每次 deploy 重置（无论 session）+ 提供"deploy 后宽限期"补偿正常迭代
2. 或：累积 refund credit 上限 = `MAX_FUEL × 10%`（跨 tick），不只单 tick 限

---

### A7. **跨房间移动时的视野扩展未定义** [Medium]

DESIGN §3.1a：drone 跨房间移动需到达出口格 + 穿越 cost +1 fatigue。
specs/05 §2.2：drone 视野范围 3。

**边界未定义**：
- drone 在出口格的瞬间，视野是否同时扩展到相邻房间？
- 如果是，那么"侦察 drone 站在出口"可获得 9 房间×视野范围的视野——单 drone 提供超出 §3.1a "默认可见 = 当前房间 + 相邻房间（最多 9 个分片）"的覆盖
- 如果不是，跨房间移动的过渡 tick 视野如何处理？

**影响**：
- specs/01 §2.3 的快照构建按"可见房间分片"拼接——视野计算的边界条件直接影响快照大小和 256KB 截断决策
- 攻击：构造大量 drone 在出口附近 → 快照膨胀 → 触发截断 → 关键实体被丢弃（虽然分桶截断保护了 Spawn/Controller）

**建议**：specs/05 §2 增加"跨房间过渡视野规则"——明确出口格的特殊性（如：仅当前房间视野，跨入新房间的 tick 才扩展）。

---

### A8. **Per-drone per-tick action quota 的拒绝码与退还策略缺失** [Medium]

specs/01 §3.3 第 3 条："每 drone 每 tick 最多执行 1 个 main action（Move/Attack/Harvest/Build/Heal 及其特殊攻击变体）。Transfer/Withdraw 不计入此配额但受 carry 容量约束。"

但 specs/02 §3 校验矩阵中：
- 没有 `MainActionQuotaExceeded` 拒绝码
- 没有说明：drone 的 cmd 1 是 Move（应用成功），cmd 2 是 Attack（也是 main action）→ cmd 2 是被拒还是覆盖 cmd 1？
- 退还策略：被拒的 main action 退还吗？specs/02 §7.1 没有此情况

**建议**：
1. 在 specs/02 §3 添加 `MainActionQuotaExceeded` 拒绝码
2. 在 §3.X 每个 main action 的校验表加入"per-drone main action quota"检查
3. 在 §7.1 明确：quota exceeded 不退还（玩家应自我管理）

---

### A9. **Hack 状态机的 system 归属不明** [Medium]

specs/02 §3.10：Hack tick 1-2 减速 50%, tick 3-4 无法移动, tick 5 转 Neutral, 5 tick 后自动恢复。

这个状态机包含：
- tick 计数（HackControlLock.stage 递增）
- 减速效果（影响 Move 校验）
- 转 Neutral（owner 切换）
- 自动恢复（5 tick 后切回原 owner）

但 specs/01 §3.4 主线 ECS 系统列表是：death_mark → spawn → combat → death_cleanup + 并行 regen/decay。

**问题**：
- 哪个 system 推进 HackControlLock.stage？
- 哪个 system 在 stage=5 时切换 owner？
- 哪个 system 在 5 tick 后切回？
- 这些 system 在 Phase 2a 还是 Phase 2b？

**TOCTOU 影响**：
- specs/01 §3.3 第 2 条声明"Hack 控制锁施加后，原 owner 命令仍以原始 owner 身份校验"——这要求 owner 切换发生在 Phase 2b 末
- 但 stage 推进必须在 Phase 2a 之前（否则同 tick 多个 Hack 命令的 stage 计数错乱）

**建议**：
1. 在 specs/01 §3.4 主线显式增加 `status_advance_system`（Phase 2b 主线，combat 之后 death_cleanup 之前）
2. 在 specs/02 §3.10 说明 stage 推进 + owner 切换在哪个 system

---

### A10. **降级模式下 in-flight 部署的语义未定义** [Low]

specs/01 §6.2：连续 3 次 tick abandon → 降级模式 → 暂停 MCP_Deploy。

但 specs/09 §7.4 状态机中，部署有多个 in-flight 状态：
- `nonce_issued`（已签发 nonce 但未提交 payload）
- `compiling`（已提交 payload，编译中，30min TTL）

**未定义**：
- 进入降级模式时，已在 `compiling` 状态的部署是 graceful 完成还是强制取消？
- 已签发但未消费的 nonce 是 immediately invalidate 还是允许 60s 自然过期？

**建议**：specs/01 §6.2 + specs/09 §7.4 增加降级模式对 in-flight 部署的处理规则。

---

### A11. **Wasmtime ≥30 fuel API 变更对 host function 计费的影响未明** [Low — 实现可行性]

specs/04 §2.2 注释："Wasmtime ≥30 移除了 fuel_consumed_callback API；燃料检查改为在 Store 层通过 get_fuel() 轮询"。

specs/04 §8 单次 host function fuel cost 表已定义（如 path_find: `500 × explored_nodes + 200 × expanded_edges + cache_miss_penalty`）。

**问题**：
- host function 内的 fuel 扣除点在哪里？
- 是在 host function entry 一次性扣（按上限）？还是按实际工作量动态扣？
- 如果是动态扣，Wasmtime ≥30 的 fuel state 如何在 host 侧改变？
- specs/04 §3 ABI 没有定义 host function 调用前后的 fuel 同步点

**建议**：specs/04 增加"Host function fuel 扣费协议"小节，明确：
1. WASM → host function 调用入口：Store::set_fuel(fuel - estimated_max)
2. host function 实际工作完成后：Store::set_fuel(fuel - actual_consumed)
3. host function 返回前 fuel 不足 → 返回错误码 + 不执行实际工作

---

### A12. **CommandIntent 的 sequence 跨 source 协调缺失** [Low]

specs/02 §2.1：CommandIntent 仅含 `sequence` + `action`，sequence 由 WASM 提供，"每玩家每 tick 单调递增"。

但 specs/09 §2.1 来源矩阵中，同一 player_id 可能有多个 source：
- `WASM`（drone tick 输出）
- `MCP_Deploy`（部署，无 sequence）
- `Admin`（管理操作，可写入世界）
- `Tutorial`（教程，仅教程世界）

**未定义**：
- WASM 与 Admin 来源对同一玩家发的命令，sequence 如何全局排序？
- 是否每个 source 独立 sequence 空间？还是共享 sequence？
- specs/01 §3.1 排序 key 是 `(shuffle_order, player_id, cmd_seq)`——cmd_seq 不区分 source

**建议**：
1. 明确 sequence 是 per-(player_id, source) 还是 per-player_id
2. 排序 key 增加 source 维度：`(shuffle_order, player_id, source_priority, cmd_seq)`
3. 定义 source_priority（如 Admin > WASM > Tutorial）

---

## Missing（缺失内容）

### M1. **多实例分片架构无 spec** [Critical 长期]
DESIGN §3.1a 声明 Tier 3（水平分片）"为远期方向，数据模型和 API 设计预留了分片扩展接口"。但**没有任何 spec 涉及分片**：
- 分片键是什么？（房间 ID？玩家 ID？）
- 跨分片移动协议
- 分片间可见性拼接
- FDB 单一事务如何拆分到多分片
- 跨分片 PRNG 同步

**风险**：水平扩展是 MMO 的核心需求。当未来真要分片时，FDB 单一事务模型必须重设计，所有 spec 中的"严格可序列化提交"假设全部失效。这是阻塞性架构债务。

**建议**：至少补一份 `10-sharding-roadmap.md` 大纲，声明分片键、跨分片协议、FDB 事务模型的演进路径。可以是"远期"，但需要存在。

### M2. **MCP 工具间并发协调缺失** [Medium]
specs/03 §5 限流是 per-player + global，但跨 tool 之间无锁定模型：
- deploy 进行中 + 同时调 swarm_simulate 是否互斥？
- swarm_get_replay 大范围（100k tick）查询的 IO 是否阻塞 tick 调度？
- swarm_dry_run_commands 与 swarm_simulate 是否共用资源池？

**建议**：specs/03 增加 "Tool concurrency model" 小节。

### M3. **运维 runbook 多处占位但无具体规范** [Medium]
- specs/09 §3.4 "Auth Service 私钥泄露 → bump epoch → 所有客户端重新签发"
- specs/04 §2.1 "每季度审查 Wasmtime 安全公告"
- specs/01 §6.2 "需管理员介入"

这些是关键运维路径，但具体步骤、责任方、SLA 在 spec 中只是占位。设计完成度需要 runbook 至少到大纲级。

**建议**：增加 `11-operations-runbook.md` 大纲。

### M4. **客户端断线 → 已部署 WASM 的执行语义未定** [Low]
specs/09 §7.1：session 断连 60s 内 pending_close。但 WASM 已部署在 sandbox 中，断线不会停止已部署的 tick() 调用。

- 玩家断线 → 已部署的 WASM 继续 tick() → 直到 session timeout → kill sandbox？
- 这是常态行为还是异常？
- 长 session 心跳续期下，客户端永不"断线"——sandbox 永远运行？

**建议**：specs/09 §7.1 明确"已部署 WASM 的运行不依赖 session 状态，session 仅控制 deploy/query 接口"。

### M5. **Bevy↔FDB 启动恢复路径无 spec** [Medium]
specs/01 §6.4 末尾声明"启动/恢复时从 FDB 重建 Bevy World"，但具体协议缺失：
- FDB 的 keyframe + delta 链如何重组装？
- 大世界（万级实体）的恢复时间预算？
- 恢复期间的玩家请求如何处理（拒绝？排队？）
- partial recovery（FDB 数据损坏）的策略

**建议**：specs/01 增加 "§8 Engine startup & recovery" 小节。

### M6. **Determinism Contract 的版本依赖矩阵缺失** [Low]
specs/01 §7 列出确定性合同的依赖：Blake3 + IndexMap + Wasmtime pinned + ...

但模组层（Rhai）的版本固定策略未定义：
- Rhai 版本升级 → AST 节点计数可能变化
- 模组的 .rhai 脚本固定到 git commit + checksum，但 Rhai engine 本身？

**建议**：specs/07 增加 Rhai version pinning + 跨版本 AST 兼容性策略。

---

## Phase Ordering（阶段依赖关系评估）

### Phase 2a (Inline Apply) 设计

✅ **正确**：
- 玩家提交的 main action 命令（Move/Harvest/Build/Transfer/Attack/Heal）按 (shuffle_order, player_id, cmd_seq) 排序后逐条应用到 Bevy World
- 校验基于当前 Bevy World 状态（非快照），保证"先到先得"竞争公平
- Spawn 命令"只校验不入队"——避免同 tick 后续命令依赖未创建 drone（TOCTOU 合同 §3.3.1）

⚠️ **需澄清（A8 / A11）**：
- main action quota 的拒绝码与退还策略
- host function fuel 扣费协议

### Phase 2b (ECS Systems) 主线依赖

声明的主线（specs/01 §3.4）：
```
death_mark → spawn → combat → death_cleanup
```

并行（同 Update schedule）：
```
regeneration ─┐
decay ────────┤ 在 death_cleanup 之前完成（before 约束）
```

✅ **正确性证明**（specs/01 §3.4 RW 矩阵）：
- death_mark 写 RoomCap/DeathMark，spawn 读 RoomCap → 必须串行 ✅
- spawn 写 Position/HitPoints/Owner，combat 读 Position → spawn 必须在 combat 前 ✅
- combat 写 HitPoints，death_cleanup 写 DeathMark → combat 必须在 death_cleanup 前 ✅
- regeneration 写 Energy/Carry，主线不读写此字段 → 并行安全 ✅
- decay 写 Fatigue/Cooldown，主线不读写此字段 → 并行安全 ✅
- regeneration 与 decay 写不同字段 → 彼此并行安全 ✅
- 所有系统在 death_cleanup 前完成（before 约束）→ 不操作已 despawn entity ✅

❌ **A2 暴露的不一致**：
- DESIGN §3.2 与 specs/01 §3.4 ：regen/decay 与主线并行（before death_cleanup）
- specs/07 §3：regeneration 在 combat 之前的 chain（串行）

**修正建议**：以 specs/01 §3.4 为唯一真相，修正其他两处文档。

### Phase 2a → Phase 2b 衔接

✅ Spawn 命令在 2a 校验通过后入"pending_spawns"队列，在 2b spawn_system 中统一创建。
✅ death_mark 在 spawn 之前——释放 room cap 槽位后再 spawn，正确处理"同 tick 死一个生一个"边界。
✅ 新 spawn 的 drone 在同 tick 参与 combat（"出生即投入战斗"，DESIGN §3.2 明确为有意设计）。

### 哪些系统可并行？

specs/01 §3.4 给出的并行集合是 {regeneration, decay}，其他主线 4 系统串行。

**架构师视角的进一步建议**：
- death_mark 仅写 RoomCap/DeathMark（标记），不操作 Position/HitPoints —— 理论上可与 regeneration/decay 并行
- 但 spawn 读 RoomCap，必须在 death_mark 之后
- combat 读 Position/Owner，必须在 spawn 之后
- 实际可并行度：(death_mark, regeneration, decay) ∥ → spawn → combat → death_cleanup

但当前设计将 death_mark 也放在主线 chain（与 spawn/combat 串行）——保守但损失约 1/4 并行度。在 10k 玩家规模下这个差异显著。

**建议**：明确探索 death_mark 是否可与 regen/decay 并行（仅约束 before spawn）。

### 跨 Phase 的有序事件

| 事件 | Phase | system / handler |
|------|-------|-----------------|
| spawn 命令校验 | 2a | validate_and_apply |
| death 命令（Recycle）校验 | 2a | validate_and_apply |
| Attack 命令应用（damage） | 2a | validate_and_apply（先 damage） |
| Heal 命令应用 | 2a | validate_and_apply（damage 后） |
| Tower 自动攻击 | 2b | combat_system |
| DoT/状态结算 | 2b | combat_system |
| 标记待死亡 | 2b | death_mark_system |
| 创建 drone | 2b | spawn_system |
| 资源点再生 | 2b | regeneration_system（并行） |
| 疲劳/冷却递减 | 2b | decay_system（并行） |
| 实际 despawn | 2b | death_cleanup_system |
| **状态机推进（Hack/Debilitate/Fortify）** | **2b？** | **A9 缺失** |
| 代码传播 | 2b | code_propagation_system（before spawn） |
| 内存维护费 | 2b | memory_upkeep_system（before decay） |

**A9 强调的缺口**：HackControlLock / Debilitated / Fortified 等持续状态的"stage 推进 + 到期清除"system 没有显式定义。这些必须在 Phase 2b 主线 combat 之后、death_cleanup 之前——但目前文档没有这个 system 的位置。

**建议**：specs/01 §3.4 增加 `status_advance_system`：
```rust
app.add_systems(Update, (
    death_mark_system,
    spawn_system,
    combat_system,
    status_advance_system,  // 新增：推进所有持续状态的 stage
    death_cleanup_system,
).chain());
```

---

## 总评

R4 文档体在 R3 基础上完成了主要 BLOCKER 收敛——A1（ECS RW 矩阵）和 A2（Bevy↔FDB 双权威源）显式闭合。可见性单一函数全输出面、Source Gate 不可伪造、TOCTOU 合同明确化、Browser/Agent transport 拆分——这些是高质量架构文档应有的硬骨头。

剩余的 Critical / High 关切都是"边界条件未明"或"文档前后不一致"，不要求重新设计核心架构。建议在下一轮修订中：
- **必须解决**：A1（tick 预算）、A2（Phase 顺序文档统一）、A3（snapshot 性能上限）
- **应解决**：A4–A12 中的 Medium 项（A4/A5/A6/A7/A8/A9）
- **建议补充**：M1（分片大纲）、M3（运维 runbook 大纲）、M5（启动恢复 spec）

具备 CONDITIONAL_APPROVE 的条件：上述 A1/A2/A3 在下一轮 patch 中给出明确响应（不必完全实现，但需要 spec 层面的明确路径）。

---

**Reviewer signature**: rev-claude-architect / R4 / 2026-06-16
