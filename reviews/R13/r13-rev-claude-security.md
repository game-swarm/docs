# R13 安全评审 — Claude Opus (Security)

> 零历史上下文评审。Reviewer: Security / Claude Opus。

## VERDICT: CHANGES REQUESTED

存在 2 项 High 级阻断问题（S1 特殊攻击管线缺失、S2 证书生命周期脱节），二者均为"已定义行为但缺失约束"的攻击面，必须在合入前补齐 schema/validator/auth 重校验时点。其余 6 项 Medium 与 3 项 Low 不阻断合入，但应在文档迭代中逐条闭合或显式标注为已接受风险。

## 阻断项 (必须修复)

**S1 [High] 特殊攻击未进校验/来源/IDL 管线。** DESIGN §8 定义 Hack / Drain / Overload / Debilitate / Disrupt / Fortify，但 P0-2 校验矩阵、P0-8 IDL `commands`、P0-9 来源能力表中均无对应条目。这些是可改变世界状态、跨玩家、带资源消耗的指令，却无 schema、validator、cost、refund、Source Gate 定义 → 未受约束的攻击面。Hack（夺取控制权）尤其危险，缺校验即可被伪造/滥用。

**S2 [High] 证书过期与已部署 WASM 生命周期脱节。** P0-3/P0-9 证书 24h 过期、可吊销；但 gameplay WASM（source=WASM）每 tick 持续执行，auth_context 的 `cert_fingerprint` 取自部署时。规范未定义证书过期/吊销后正在运行的模块是否停跑。P0-4 §7 仅说"ban/revoke 时清除缓存条目"，但运行中模块的 auth 重校验时点缺失 → 被封禁/凭据失效玩家的模块可能继续执行。

## 非阻断项 (应处理)

**S3 [Medium] 旁观者路径是 `is_visible_to` 不变量的显式绕过。** P0-5 §1 称"无绕过"，但 §3.5 旁观者推送全地图实体（无可见性过滤），World 模式延迟仅 ≥50 tick（≈150s）。串谋向量：玩家开匿名旁观 WebSocket，把延迟全图情报喂给自己的 bot。延迟在慢节奏 World 仍有战略价值。

**S4 [Medium] 不可信字符串契约仅覆盖玩家名。** P0-3 §6.2 只对 name（32 字符白名单）加 `untrusted` 包裹。但 drone `env_vars`、memory 内容等玩家原创字符串也会进入快照/MCP 数据并交给 AI 模型，未要求 untrusted 标注或分隔符包裹 → prompt-injection 通道未闭合。

**S5 [Medium] Wasmtime 配置 API 不准确，沙箱可能未按预期生效。** P0-4 §2.2 使用 `fuel_consumed_callback`、`static_memory_maximum_size`、`table_elements_max`、`max_instances` 等并非 wasmtime 30 的真实 API；以 `panic!()` 作 fuel 耗尽执行点不安全。配置失效会使隔离假设落空，需以真实 API（Store fuel、PoolingAllocator limits、epoch deadline）核对。

**S6 [Medium] Overload 跨玩家操纵 fuel budget，账目语义未定义。** DESIGN §8 称 Overload 使目标 fuel budget -500k（下限 2M），但 fuel 每 tick 重置为 MAX_FUEL（P0-4 §6），且 refund credit 也加到下一 tick budget（P0-2 §7.2）。持续削减如何跨 tick 叠加、与 refund/重置如何交互未定义 → 账目不一致 + 持续 griefing 风险。

**S7 [Medium] FDB/Bevy 双状态一致性依赖显式 restore。** P0-1 §3.4 abandon 时需 `world.restore(snapshot)`，FDB 回滚不自动恢复 Bevy。restore 失败或遗漏即造成权威源（FDB）与内存状态分叉 → 完整性/确定性破坏，回放校验可能误报或漏报。

**S8 [Medium] Admin 来源权限过大且仅 Rollback 有双人控制。** P0-9：Admin 无限速率、全局可见、可写世界/全局存储/部署。仅 Rollback 要求两个 admin Ed25519 签名。单一 admin 凭据泄露 = 全世界沦陷，普通 Admin 写入无双控/审批门槛。

**S9 [Low] world_seed 单点机密。** 驱动 seeded_shuffle + Blake3 XOF PRNG。10k tick 轮换有助，但泄露（日志/admin 面）可预测排序与随机流直到下次轮换。需明确 seed 永不写日志/不入任何玩家可达面。

**S10 [Low] i32 坐标边界执行点未指明。** P0-2 §6 规定每房间 [-128,127]，但 Move/MoveTo/Build 的 x,y 为 i32，反序列化阶段的钳制/拒绝点未在校验矩阵明示 → 未检即有溢出/越界查询风险。

**S11 [Low] 被 Hack drone 转中立后仍跑原 owner WASM。** fuel 由谁计费、可见性归属、5 tick 内再 Hack 的判定、中立单位是否进原 owner 快照等未定义 → 资源账目与可见性边界模糊。

## 优点 (Strengths)

- **确定性安全边界清晰。** Blake3 XOF PRNG + world_seed + seeded_shuffle 构成可重放、可校验的随机源，回放校验机制为反作弊提供了一等公民支持。
- **WASM 沙箱采用纵深防御。** fuel 计量 + epoch deadline + 内存/表上限 + PoolingAllocator 的组合（即便 §2.2 API 细节需修正）方向正确，隔离假设建立在多层而非单点。
- **认证体系有强密码学基础。** Ed25519 证书 + 24h 过期 + 吊销 + Rollback 双签名，体现了对高危操作分级控制的意识；S8 指出的是覆盖面不足，而非机制缺陷。
- **可见性模型有不变量约束。** `is_visible_to` 作为单一可见性裁决点的设计意图正确，drone 感知与玩家视野分层、回放隐私分级（private/allies/world/public）展现了细粒度信息控制。
- **校验矩阵 + IDL + 来源能力表三件套** 提供了系统化的指令约束框架；S1 暴露的问题恰恰是因为这个框架足够明确，使"特殊攻击未纳入"成为可检出的缺口——框架本身是优点。
- **不可信输入有包裹契约。** P0-3 §6.2 的 untrusted 包裹机制方向对，S4 是覆盖面补全问题而非架构缺失。

## 复审重点

S1、S2 修复后需确认：(a) 6 种特殊攻击各自的 schema/cost/refund/Source Gate 已入 P0-2/P0-8/P0-9；(b) 运行中 WASM 的 auth 重校验时点（每 tick 或证书 TTL 边界）已明确定义。
