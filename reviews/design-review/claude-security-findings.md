# Security Review — Swarm DESIGN.md (Phase 0)

**Reviewer**: Claude Opus 4.8 (Security) | **Stage 1**: 问题清单

## Verdict
架构的信任分层（WASM 不可信 / Rhai 可信 / Rust 核心）方向正确，但**两条信任边界存在结构性缺陷**：Rhai 进程内执行 + 墙钟终止破坏了作为反作弊基石的确定性；Command 校验管线是唯一收口点，其鲁棒性决定整个攻击面。条件性放行至 Stage 2。

## Critical

- **C1｜Rhai 墙钟终止破坏确定性**：§8.4 以 100ms 墙钟强制终止并回滚。墙钟在不同硬件/负载下终止于不同 AST 节点 → 同一输入产生不同世界状态。这直接违反 §1.5「确定性核心」，使回放再验证（反作弊根基）失效。攻击者可借机器负载差异制造不可复现的状态分歧。必须改为 AST 节点数/指令数等确定性预算。
- **C2｜Rhai 在引擎进程内、无隔离、持破坏性 API**：§8.1/D11，`damage_entity`/`deduct_resource`/`set_entity_flag` 运行于核心进程。"服主可信"假设在模组被分发/复用时崩塌（D12 无版本约束、无签名）。Rhai 解释器一旦存在逃逸或预算绕过，即全进程沦陷。需进程/能力隔离 + 模组签名与来源校验。
- **C3｜Command Validation Pipeline 为单点收口**：§1.4/§1.3 Phase 2a。Command JSON 完全由不可信 WASM 构造。须穷举：entity_id 越权（操控非己方实体）、u32 数量溢出/回绕、资源数量注入、坐标越界、超大/畸形 JSON 致 DoS。每条指令须对当前世界状态做**所有权绑定 + 范围 + 类型**三重校验，且校验自身不可被指令数量耗尽。

## High

- **H1｜快照序列化未计入 fuel 配额**：§1.3 COLLECT 阶段引擎为每玩家序列化可见世界 JSON 并写入线性内存。该成本由引擎承担、不受 fuel 计量。攻击者扩大可见范围/实体数 → 放大序列化与内存开销，形成非对称 DoS。需对快照大小/序列化成本设上限并计费。
- **H2｜MCP 查询工具无频率限制**：D10，`swarm_get_snapshot`/`swarm_inspect_entity` 无频控声明。高频轮询既是信息不对称（D9），也是 DoS 向量。须配额化所有查询工具。
- **H3｜Hack/Neutral 5-tick 状态机 TOCTOU**：D7。Hack 期间 drone 被 kill/Recycle、双重 Hack、中断恢复竞态 → 状态错乱或所有权丢失/复制。需形式化状态机并枚举并发边缘。
- **H4｜种子洗牌可预测**：D2，`Blake3(tick || world_seed)`。若 world_seed 已知/可推断，玩家预先计算自身执行序位并抢跑。须保证 world_seed 不可获取，或采用 commit-reveal。

## Medium

- **M1｜转换损耗整数舍入**：§5.2 transfer cost 1%/5% 对小额转账可舍入为 0 → 微额拆分规避损耗。需向上取整或设最小损耗。
- **M2｜回放/观战侧信道**：D14，`spectate_delay=0` 默认值构成共谋通道（一人观战全图、一人参赛）。竞技模式默认应 >0。
- **M3｜自定义动作组合注入**：§4.5 TOML `[[custom_actions]]` 引用 `[[special_effects]]`，缺乏组合白名单 → 服主误/恶配出免疫叠加或负冷却等破坏性组合。
- **M4｜wasmtime 版本即确定性依赖**：§8.2 自承「确定性依赖 wasmtime 版本」。版本漂移使旧回放无法复现 → 反作弊取证断裂。须锁定并记录运行时版本于回放元数据。

## Informational

- I1｜MIT 首日开源：须明确 wasmtime/Rhai CVE 跟踪与更新策略。
- I2｜TickTrace 审计日志须防篡改，并明确回放中的 PII/隐私分级落地。
- I3｜`set_entity_flag` 标志命名空间（如 `immune_*`）需防冲突与未授权赋予。
