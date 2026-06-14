# R12 Architect 评审发现（Stage 1）

> 零上下文架构评审。仅列问题，不含结论与优点。

## Critical

### A1. Rhai 模组墙钟预算破坏确定性
DESIGN §8.7 / ROADMAP 3.7 规定模组钩子 `墙钟执行时间 100ms/tick` 超限即强制终止并标记 degraded。墙钟是非确定量——同一 tick 在不同机器/负载下会在不同 AST 节点处被截断，产生不同的 `actions` 副作用，进而 `state_checksum` 分叉。这与 §8.8 Determinism Contract 和 P0-1 §6.3 回放保证直接冲突。模组 actions 进入世界状态，必须用确定性预算（AST 节点数 / op 计数）作为唯一终止条件，墙钟只能做监控告警、不能改变状态。

### A2. ResourceRegistry 仍用 HashMap
DESIGN §8.4（line 907）`types: HashMap<String, ResourceDef>`、`action_costs` 未声明确定性容器。Determinism Contract 明令 `HashMap 顺序 → indexmap`。任何对资源类型/消耗的迭代（扣费、衰减、税）顺序非确定，跨进程回放分叉。需全面改为 IndexMap，并加 CI 静态检查禁止 std::HashMap 出现在模拟路径。

## High

### A3. 全量世界状态每 tick 落 FDB 与"每 N tick 快照"矛盾
P0-1 §6.3.1 写 `/tick/{N}/state → tick 后完整世界状态`（每 tick）；DESIGN §2.1/§3.2 写"每隔 N tick 记录完整世界快照"。二者不一致。若真每 tick 全量落盘，存储无界增长且 EXECUTE 500ms 预算难容纳序列化+提交。需明确：commands+rejections 每 tick、full state 周期快照（回放由 snapshot+commands 重建）。

### A4. Sandbox "每 tick fork" 与模块缓存/epoch/gRPC 三处冲突
P0-4 §1 "每 tick fork→执行→kill"，但 §7 "编译一次多 tick 复用"、§2.2 `epoch_interruption` 需常驻后台线程递增 epoch、§4.3 经 Unix socket 长连 gRPC。fork-per-tick 的短命进程无法持有缓存模块、无法维持 epoch 驱动线程、每 tick 重建 socket 开销巨大。500 玩家 ×每 3s fork/kill 的进程风暴未做可行性核算。需统一为常驻 per-player worker（实例级重置）还是真 fork，并据此重写生命周期。

### A5. 分片（Phase 7）与全局种子洗牌不可调和
P0-1 §3.1 种子洗牌对"全部 active_players"排序以保证公平+确定；Phase 7.2 按房间分片到不同引擎进程。跨分片如何取得全局玩家顺序、跨房间指令（移动/运输拦截）如何在分片边界保持单一 FDB 事务原子性与确定排序，均未定义。这是冻结架构里的隐藏断点。

### A6. Bevy World 快照/恢复成本与机制未定义
P0-1 §3.4 要求 EXECUTE 前对 Bevy World 做内存快照、FDB 回滚时 `world.restore(snapshot)`。全量克隆整个 ECS World 每 tick 一次的成本、实现方式（组件级 diff？双缓冲？）、以及与 §4.1 delta 计算所需 before/after 的关系都未规定，可能成为 tick 预算杀手。

## Medium

### A7. 按房间序列化再过滤的可见性假设站不住
P0-1 §2.3 称快照"按房间序列化一次再按玩家过滤"，但 P0-5 §4 可见性含"R 及相邻房间"的视野并集，按玩家视野源动态决定。无法靠单次按房间序列化廉价复用，过滤复杂度被低估。

### A8. Host function 调用预算两处不一致
P0-4 §6 "Host function 调用 1000/tick"，P0-2 §4 限 `get_objects_in_range` 5/tick、`path_find` 10/tick。总额与分项关系（1000 是否含查询类、其余 985 是什么）未说明。
