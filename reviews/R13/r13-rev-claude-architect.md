# R13 架构评审 — Claude (Architect)

> 零历史上下文评审。方向：分布式架构 / 确定性 / 回放可重建性。

## VERDICT

**REJECT（需修订后重审）。**

文档在确定性回放与单进程执行模型上已相当成熟，但存在两处 **Critical** 级一致性缺陷，使「水平扩展」与「确定性回放」两大核心承诺在分布式部署下无法同时成立：

- **A1**：全局原子 tick 提交（单一 FDB 事务包全世界指令）与 per-shard 引擎实例模型直接冲突。提交粒度必须二选一——当前文档同时声明了「全局」与「per-shard」，这是吞吐量天花板，也是 sharding 路线的根本性未决问题。
- **A2**：COLLECT「仅读本地 Bevy World 内存」与「视野可覆盖相邻房间」在 sharding 下矛盾；相邻房间若在另一进程，合法可见实体会从快照丢失，分布式部署下可见性不正确。

这两项触及系统的扩展轴心，必须在进入实现前给出明确的提交粒度与跨 shard 状态同步机制。

此外 4 项 **Major（A3–A6）** 均为回放可重建性漏洞：world config 内容哈希、fuel refund credit、world_seed 轮换推导式、path_find 缓存的 fuel 计费语义，全部需要纳入 TickTrace 或在协议中固化为纯函数推导，否则 `execute_deterministic == recorded_state` 这一核心不变量不成立。2 项 **Minor（A7–A8）** 为 tick 时间预算余量与迟到指令跨 tick 重排的 sequence 冲突，建议一并澄清。

完整问题清单见 `reviews/r13-arch-findings.md`（A1–A8）。

## Strengths（值得保留的设计）

- **三段式 tick 模型（COLLECT / EXECUTE / BROADCAST）边界清晰**，把不确定的输入采集与确定的状态推进分离，为回放奠定了正确的结构基础。
- **确定性优先的工程取向**：world_seed、RawCommand、激活模组列表已被自觉纳入回放输入，TickTrace 的设计方向正确——本轮 Major 问题都是「再补几项输入」而非「推倒重来」。
- **PRNG 选型（Blake3 XOF）与种子轮换机制**思路合理，轮换基于 `Blake3(旧种子, 当前tick)` 是可推导的纯函数，只差在协议中固化推导式（A5）。
- **path_find 缓存键 `(from, to, terrain_hash, visibility_fingerprint)`** 设计周到，已把影响路径结果的全部因子纳入键，只需补一句「缓存对 fuel 透明、命中仍全额计费」即可消除确定性耦合（A6）。
- **fuel 计费模型**（per-action 成本 + refund credit）作为 WASM 执行深度的确定性闸门方向正确，credit 只需声明为 tick 边界权威状态（A4）。
- **单进程基线下整套设计自洽**——所有 Critical 问题仅在引入 sharding 时暴露，说明非分布式部署可立即落地，扩展性问题可作为独立工作项推进。
