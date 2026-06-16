# R5 闭合验证 — Security (Claude Opus 4.7)

**评审范围**: R4 共识 Blocker B1–B6 + 用户裁决 D-1 ~ D-4 是否在文档中闭合
**评审视角**: 安全（信任边界 / 攻击面 / 威胁穷举）
**文档版本**: /data/swarm/docs/{design, specs/01-09} @ 2026-06-16 20:38

---

## 一、总体 Verdict

**`CONDITIONAL_APPROVE`**

10 项中 9 项已**充分闭合**——合同定义清晰、具实现性、无安全歧义。唯一缺口在 D-4（Tier 2/3 spec-ready），路线已选定但增量快照确定性、跨分片身份链等关键细节仍标注为 TBD。从安全视角，B1–B6 和 D-1/D-3 涵盖的所有 Tier 1 范围攻击面均已闭合，D-4 不阻塞 Tier 1 实现，但需在 Phase 1+ 启动前补齐。

---

## 二、逐项判定

| ID | 状态 | 证据 / 缺口 |
|----|------|----------|
| B1 | CLOSED | specs/07 §5.1：inprocess 唯一生产模式（删除 out-of-process 切换）；Ed25519 强制签名（含 `.rhai` 与 `mod.toml`）；trust chain 七层（签名/版本锁/白名单/CRL/epoch/operator override/回滚不可逆）；capability 命名空间表（deduct/award/emit_event/set_world_param/set_entity_flag——逐项允许范围+禁止项+审计字段）；RuleMod 角色声明禁止伪造玩家命令、不得绕过 Command Validation Pipeline。 |
| B2 | CLOSED | specs/01 §8 统一预算表（COLLECT/EXECUTE/BROADCAST/COMPILE 全覆盖，硬/软/复用语义明确）；§8.4 跨重试 fuel 上限 = 1×MAX_FUEL（封死竞争失败放大）；specs/04 §6 path_find 按 explored_nodes + expanded_edges + cache_miss 计费 + per-tick 100k 节点总额度；§6.1 simulate 独立配额池（含并发上限 3、跨小时 fuel 上限）防止旁路 tick 预算。 |
| B3 | CLOSED | specs/01 §2.3 truncation 4 桶 + 确定性排序键 (distance, entity_id) + 玩家可预期性条款；滥用检测矩阵（实体膨胀/出口扩展/截断频率/path_find cache_miss 自动 throttle）；§3.5 完整 Resource + Component 快照清单 + FDB 故障注入 CI 测试（state_checksum 一致性断言）。Tier 1 scope 充分；Tier 2/3 演进归入 D-4。 |
| B4 | CLOSED | specs/05 §3.5 旁观者数据分级表（仅物理状态可见，玩家私有数据/代码/调试全屏蔽）；§3.0 所有 host function 经 `is_visible_to` 过滤；specs/01 §2.3 WASM tick 与 MCP query 共享同一快照（snapshot_tick 一致，无时差 oracle）；specs/05 §6 Overload 三结果等价 + Hack 双视角矩阵 + `NotVisibleOrNotFound` 统一拒绝码；§3.5 `validate_config` 强制 `public_spectate=true → spectate_delay ≥ 50`。 |
| B5 | CLOSED | specs/02 §1.1 + specs/08 §1 全 schema 默认 `additionalProperties: false`；§2.1 sequence 改为 per-(player, source) + 排序键 (player_id, shuffle_order, source, sequence)；§5.1 新增 `MainActionQuotaExceeded`；§6 field-level 七维校验穷举矩阵；specs/09 §3 Ed25519 客户端密钥+服务端证书 + deploy_nonce（128-bit、60s TTL、single-use、IP-bound、audience-bound）+ epoch bump 紧急 runbook + CRL 三检查点；§2.3 Admin 路径通过 Rust `WorldMutate` trait 编译期唯一性证明（无独立代码路径可绕过）；§7.0 transport audience 强制 `aud` 匹配（mcp/ws/rest/replay 不可互换）。 |
| B6 | CLOSED | specs/01 §3.4 `spawning_grace_system` 入主线 chain（death_mark→spawn→spawning_grace→combat→status_advance）；specs/02 §3.16 同 tick 多命中优先级 + 同类型多次行为 + 反制窗口三表；§3.17 Overload 反永久锁死数学证明（floor 始终 ≥ 2M fuel）；§3.18 Recycle 比例退还公式 + 10% 末期下限封死生命周期套利；§3.19 status_advance 调度位置；specs/01 §3.3 Phase 2a TOCTOU 合同（Hack 锁定期间原 owner 仍负责校验、per-drone main action quota = 1、fuel 耗尽不读部分输出、指令不跨 tick）。 |
| D-1 | CLOSED | specs/07 §5.1 显式声明 inprocess 为唯一生产运行模式（"不存在 `[rhai] isolation` 切换选项"）；强制 Ed25519 签名（无"允许未签名"宽松模式）；签名验证 + CRL + epoch 三层防御；安全边界由密钥白名单而非进程边界提供。 |
| D-2 | N/A | DESIGN §9 显式声明 World 模式无胜利条件（MMO 沙盒）。安全方向无专业判断——此项属游戏设计/经济决策。 |
| D-3 | CLOSED | DESIGN §3.1a + specs/01 §3.4 + specs/02 §3.8 三处一致：新生 drone 获 `SpawningGrace { remaining: 1 }`，本 tick 免疫所有伤害（含特殊攻击和衰减），下一 tick 正常参与。`spawning_grace_system` 紧随 `spawn_system` 在 combat 之前调度。安全副作用：封死"出生即斩"作为反复杀伤 DoS 模式。 |
| D-4 | GAP | tech-choices §12 已选定路线（Tier 2 增量+CoW 实体分页备选；Tier 3 按房间分片首选），但显式列出 4 项 TBD：CoW 页大小权衡、truncation 在增量模式下的确定性排序、跨分片实体引用格式、分布式 combat 结算协议、FDB 多区域分片亲和性。**安全影响**：增量快照若失去确定性，replay 验证链断裂（反作弊与审计失效）；跨分片 combat 协议未定义会导致 Overload 跨分片放大、deploy_nonce 全局唯一性、CRL 传播延迟等攻击面无合同。**修正建议**：在 Phase 1+ 启动前补齐 specs/10-incremental-snapshot.md 与 specs/11-shard-protocol.md，重点定义增量截断的 deterministic ordering 和跨分片身份/审计链。**不阻塞 Tier 1 实现**——所有 B1–B6 防护在单节点 ≤500 drone 范围内完整生效。 |

---

## 三、安全方向 R5 入场结论

R4 共识中所有跨方向重叠的安全 Blocker（B1 RuleMod 信任、B2 计算预算、B4 可见性、B5 身份链、B6 特殊攻击 oracle）均在 R5 文档中达到"实现验收级"——schema、拒绝码、审计字段、数学证明、CI 故障注入路径都已具备。Security 专属高风险项（world_seed 前向保密、TickTrace 完整性、seccomp 边界）已在 R4 §五接受为方向专属 High，不属本轮闭合范围。

D-4 的 GAP 是文档维护项而非合同矛盾——Tier 1 freeze 可进入实现，Tier 2/3 启动前补 spec 即可。
