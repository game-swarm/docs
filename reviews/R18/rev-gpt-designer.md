# R18 游戏设计评审（GPT-5.5）

Reviewer: rev-gpt-designer  
Scope: Phase 1 Clean-Slate / Game Design + UX + Community Dynamics  
Read-only inputs: 指定 9 个文件；未读取 `/data/swarm/` 代码仓库、旧 reviews 或列表外文档。

## 1. Verdict

**CONDITIONAL_APPROVE（偏工程闭合，通过；偏产品/AI onboarding，仍需修正）**

R18 的核心目标是验证「YAML IDL 作为唯一机器事实源，api-registry.md 由 YAML 生成且无漂移」。就 `game_api.idl.yaml ↔ api-registry.md` 两个文件本身而言，主要机器表面已经基本闭合：CommandAction 19 个、active MCP tools 46 个、Host Functions 5 个在 YAML 与 Markdown 中一致；RejectionReason 的 35 canonical code 也与 Markdown 一致，额外的 `InvalidJson` / `SchemaViolation` 明确是 pipeline-level，不计入 canonical enum。

但从游戏设计评审视角，**“生成式单源”尚未产品化闭合**：AI 玩家和人类新手真正会读到的 `design/interface.md`、`06-feedback-loop.md`、`08-api-idl.md` 仍保留多处旧工具名、旧错误码、旧 IDL 示例。结果是：机器源和生成参考文档闭合了，但 onboarding 文档、教程路径和开发者 mental model 尚未闭合。AI agent 仅靠 MCP resources 学玩法时，仍可能学习到不存在的工具或过期错误码。

## 2. 发现问题（severity）

### G1 — HIGH — AI onboarding 文档引用的关键 MCP 工具不在 YAML active tools 中

`game_api.idl.yaml` 的 active MCP tools 为 46 个，但 `design/interface.md` 与 `specs/gameplay/06-feedback-loop.md` 仍把以下工具作为核心学习/调试路径：

- `swarm_get_schema`
- `swarm_get_docs`
- `swarm_get_available_actions`
- `swarm_explain_last_tick`
- `swarm_dry_run_commands`

这些名称均不在 YAML active tool list 中。YAML 当前提供的是如 `swarm_get_info`、`swarm_get_snapshot`、`swarm_validate_module`、`swarm_deploy`、`swarm_get_tick_trace`、`swarm_dry_run`、`swarm_sdk_fetch` 等工具。

设计影响：
- AI agent 的第一小时会失败在“照教程调用不存在工具”。
- 人类读文档会以为存在 explain/docs/schema/action-discovery 这些高层 UX 工具，但机器源没有。
- `swarm_dry_run_commands` 与 YAML 的 `swarm_dry_run` 命名不一致，尤其容易导致 SDK / MCP resource 示例失效。

建议：
- 要么把这些工具正式加入 YAML；
- 要么将所有教程、interface、feedback-loop 中的引用迁移到 YAML 已注册名称；
- 若 `swarm_get_docs` / `swarm_get_schema` 预期是 MCP resources 而非 tools，应在文档中明确区分“tool”和“resource URI”，不要混写。

### G2 — HIGH — `08-api-idl.md` 仍内嵌旧 IDL 示例，削弱“唯一事实源”承诺

`specs/gameplay/08-api-idl.md` 开头声明目标是 host functions / Command / Validator / SDK / MCP schema 单一真相来源，但正文仍保留大量与 YAML v0.3.0 冲突的示例：

- 旧 RejectionReason：`NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`NoPath`、`PathTooLong`、`AlreadyHacked`、`InvalidDamageType` 等；这些都不在 YAML 35 canonical codes 中。
- 旧 Command 参数模型：示例仍使用 `object_id`、`spawn_id`、`controller_id` 等较旧 envelope 风格，而 YAML 的 `CommandAction` 参数已收敛到每个 action 的 canonical 参数集合，例如 `Move(direction)`、`Harvest(target_id)`、`Spawn(body_parts, spawn_id)`。
- Host function 示例使用短名 `get_terrain` / `path_find`，而权威 registry 使用 `host_get_terrain` / `host_path_find` 及完整 ABI 签名。

设计影响：
- 对 AI agent 尤其危险：模型会把旧 enum 当作可用错误码，把旧 command shape 当作 SDK schema。
- 对贡献者也危险：标题和原则说“单一真相”，但正文给了第二套示例事实。

建议：
- `08-api-idl.md` 应降级为“IDL 设计原则 + 指向 registry/YAML 的链接”，删除或自动生成所有可能漂移的 enum/table/schema 示例。
- 若保留示例，必须从 YAML 生成，且 CI 检查 `08-api-idl.md` 中的 symbol 集合不得超出 YAML registry。

### G3 — MEDIUM — `interface.md` 的工具目录总数/分类和 YAML v0.3.0 不一致

`design/interface.md` 写“权威工具清单见 API Registry §3 — 46 工具，含 Economy/SDK/Resources 分类”，但其本地工具表仍列出一套不同的分类与名称，例如：

- 认证类仍出现 `swarm_get_server_trust`、`swarm_register_challenge`、`swarm_submit_csr`、`swarm_token_refresh` 等；YAML v0.3.0 active auth tools 是 `swarm_auth_login`、`swarm_auth_refresh`，并无这些工具。
- 调试类写 `swarm_inspect_entity`、`swarm_profile`、`swarm_get_replay`、`swarm_explain_last_tick`；YAML active debug/play 表面是 `swarm_get_tick_trace`、`swarm_get_engine_stats`、`swarm_get_sandbox_profile`、`swarm_list_errors`、`swarm_dry_run` 等。

设计影响：
- 玩家心理上，MCP 被描述成“屏幕和鼠标”，但屏幕上到底有哪些按钮不稳定。
- 这会直接破坏“AI 玩家能不能仅通过 MCP resources 学会怎么玩”的验收。

建议：
- `interface.md` 不应复制工具表，只保留产品语义分类；具体工具名从 `api-registry.md` 引用或自动生成片段。
- onboarding profile 的最小可用闭环应被重新定义为 YAML 中真实存在的调用序列。

### G4 — MEDIUM — Feedback loop 的“理解/调试”体验目标强，但 registry 暴露的工具粒度偏底层

`06-feedback-loop.md` 中的理想体验是：“为什么我的 drone idle？”、“我的上一 tick 做了什么？”、“修复建议是什么？”。这很适合第一小时，也适合 AI agent 迭代。但 YAML 当前更偏底层：`swarm_get_tick_trace`、`swarm_list_errors`、`swarm_get_sandbox_profile`、`swarm_dry_run`。这些足以构建调试器，但不等价于一个 bot-friendly explanation API。

设计影响：
- 人类 UI 可以在前端聚合解释，但 AI agent 仅靠 MCP tools 会得到较底层 trace，需要自己推理。
- 第一小时从“看到资源增长”到“修 bug”之间仍有 cognitive gap。

建议：
- 如果不新增 `swarm_explain_last_tick`，则至少在 `swarm_get_tick_trace` / `swarm_list_errors` 的 output schema 中加入 bot-facing summary、common_fix_hint 或 explanation resource 链接。
- 对 AI onboarding 来说，底层 trace + docs 不是替代品；需要一个“解释器”层，哪怕是 generated read-only resource。

### G5 — MEDIUM — 经济边界仍存在产品文案漂移：Market/Contracts/P2P/Merchant 的 MVP 归属不稳定

`09-snapshot-contract.md` 明确 Market Orders、Contract Settlement、Merchant NPC、Drone P2P Offer 等为 Future RFC，不在 MVP 范围；`gameplay.md` 也多处标注 Market 为 RFC。但 `06-feedback-loop.md` 的 first-hour 低风险社交冲突仍列出 `Market Contracts`，并描述“老玩家发布资源运输/防御 bot challenge，新玩家接单获得安全奖励”。这与 MVP economic boundary 的 Future RFC 定位冲突。

设计影响：
- 第一小时的社交钩子很需要，但如果用 Market/Contracts 命名，会让 MVP 范围重新膨胀。
- 玩家期待“任务板/合约板”，但经济规范禁止 Challenge Board 发资源奖励。

建议：
- 把 first-hour 的 `Market Contracts` 改名为非经济的 `Challenge Board` / `Mentor Challenges`，奖励限定为称号、replay showcase、bounty points，不注入资源。
- 如确需资源奖励，必须走 `PvEAward` ledger，而不是 contract settlement。

### G6 — LOW — World / Arena 胜利条件和 replay 社区化仍有两套产品表述

`design/modes.md` 的 Arena 终止条件是“一方 drone=0 > 认输 > tick 上限按剩余资产判定（drone数→建筑数→资源量）> 平局”；`06-feedback-loop.md` 的 Arena 小结写“摧毁敌方 Spawn，或时限结束时分高者胜”。两者不完全冲突，但会造成教学和观战叙事差异。

Replay 方面，Arena 回放公开、World replay privacy、观战延迟已有基础；但分享 URL、战报卡、自动摘要、社区 replay 排行榜仍标为 RFC。作为传播设计这可以接受，但若 MVP 目标包括社区增长，最小 share card 应前移。

建议：
- 统一 Arena 胜利条件文案，最好以 `modes.md` 为准。
- MVP 至少定义 replay permalink + safe-view privacy，不必做完整排行榜。

## 3. 亮点

### S1 — YAML ↔ generated registry 的核心闭合明显进步

本轮最重要的改进是：`game_api.idl.yaml` 和 `api-registry.md` 在核心机器表面基本一致。CommandAction 19、active MCP tools 46、Host Functions 5、Direction4、TickTrace 22 字段、Deploy/Persistence contract 都能从 registry 对齐到 YAML。这说明 R15-R17 的“不要手写 API 表格”方向是正确的。

### S2 — MCP 不直接做游戏动作的边界清晰，公平性更好

`interface.md` 明确不存在 `swarm_move` / `swarm_attack` / `swarm_build` 等工具，AI 必须写 WASM，与人类同路径。这是本设计最强的公平性基础：AI 玩家不是 privileged executor，而是另一种编辑器用户。

### S3 — 第一小时体验有完整情绪曲线

`gameplay.md` 的 10 分钟 Golden Path、`06-feedback-loop.md` 的 safe_mode → soft_launch → PvE → PvP 渐进曲线，都能有效降低 Screeps-like 游戏的“开局空窗”。尤其是 first_tick_executed 事件、drone idle 调试、资源曲线可视化，对 AI 与人类都很关键。

### S4 — Replay / Spectate / Privacy 的方向正确

World 默认私有、Arena 默认公开、spectate_delay、防 fog-of-war 泄露、Arena 赛后 replay，这些规则能兼顾竞技诚信与传播。`OverloadPressure` 也有 replay/trace 出口，利于观战解释。

### S5 — 长期追求不再只靠 GCL/RCL

设计已加入 Arena 段位、PvE 里程碑、replay 声誉、殖民地年龄、世界事件、蓝图、外交关系等非单轴目标。对长期留存比纯 room level 更健康。

## 4. Missing / Fresh Ideas

### M1 — 需要一个“AI 可学性验收脚本”，而不只是文档承诺

建议新增 CI smoke test：给一个空白 agent 只提供 MCP resources + YAML-generated schema，要求完成：发现世界 → 拉 SDK → 编译 starter bot → validate → deploy → 收到 first_tick_executed → 查询 last tick explanation。这个验收应禁止读取手写 gameplay docs，以验证机器资源本身足够。

### M2 — 增加 `onboarding_recipe` 生成物

从 YAML 生成一个稳定资源，例如：

`swarm://docs/onboarding/first-bot?profile=ai-agent`

内容不是散文，而是机器可执行 recipe：步骤、工具名、输入 schema、期望输出字段、失败时下一步。这样 AI 不必从长篇设计文档中抽取流程。

### M3 — Replay 最小传播包前移到 MVP

不必做社区 replay 排行榜，但应把以下最小传播包列入 MVP：

- replay permalink
- safe-view privacy preset
- 30 秒 highlight tick range
- 自动生成战报摘要（胜因、关键 tick、最高价值 action）

这对“旁观者模式？Replay 分享？社区传播怎么做？”是最低成本高收益项。

### M4 — First-hour 社交钩子避免经济合约，改为“挑战板 + 非资源奖励”

把当前 `Market Contracts` 改成 `Challenge Board`：老玩家发布 replay challenge、starter bot 改进题、PvE scenario seed；奖励是称号、展示位、bounty points、mentor badge，不直接发资源。这样既保留社交牵引，又不冲撞 MVP economic boundary。

### M5 — 为错误提示定义 bot-facing taxonomy

`debug_detail` 很好，但 AI agent 更需要结构化 actionability：

```json
{
  "code": "OutOfRange",
  "fix_class": "move_closer_or_use_ranged",
  "retry_after_ticks": null,
  "requires_code_change": true,
  "suggested_docs": ["swarm://docs/actions/Move", "swarm://docs/actions/RangedAttack"]
}
```

这比自然语言 suggestion 更适合自动修复循环。

## 5. CrossCheck

### 5.1 YAML ↔ api-registry.md 机器表面核对

我用脚本在允许文件范围内抽取 YAML 与 Markdown 的核心符号，结果：

- CommandAction：YAML 声明 19，抽取 19；Markdown 抽取 19；差集为空。
- RejectionReason：YAML 抽取 37 个 code，其中 35 个 canonical + 2 个 pipeline (`InvalidJson`, `SchemaViolation`)；Markdown canonical 抽取 35；canonical 差集为空。
- MCP active tools：YAML 声明 46，抽取 46；Markdown active tool names 覆盖 YAML 46；未发现 YAML 工具缺失于 registry。
- Host Functions：YAML 声明 5，抽取 5；Markdown 抽取 5；差集为空。

结论：**YAML ↔ api-registry.md 的生成式闭合基本成立。**

### 5.2 Cross-document drift 核对

发现以下跨文档漂移：

- `swarm_get_available_actions`：出现在 `interface.md` / `06-feedback-loop.md`，不在 YAML active tools。
- `swarm_get_docs`：出现在 `interface.md` / `06-feedback-loop.md`，不在 YAML active tools。
- `swarm_get_schema`：出现在 `interface.md` / `06-feedback-loop.md`，不在 YAML active tools。
- `swarm_explain_last_tick`：出现在 `interface.md` / `06-feedback-loop.md`，不在 YAML active tools。
- `swarm_dry_run_commands`：出现在 `interface.md` / `06-feedback-loop.md`，不在 YAML active tools；YAML 中是 `swarm_dry_run`。
- `swarm_register_challenge`、`swarm_submit_csr`、`swarm_token_refresh`：出现在 `interface.md`，不在 YAML active tools。
- `08-api-idl.md` 仍出现非 canonical rejection terms：`NotMovable`、`Fatigued`、`MissingBodyPart`、`TileBlocked`、`CarryFull`、`NoPath`、`PathTooLong`、`AlreadyHacked`、`InvalidDamageType` 等。

结论：**R18 的单源闭合只覆盖 YAML 与生成 registry；尚未覆盖玩家/AI 实际阅读路径。** 下一轮应把“所有 API 名称、错误码、host function 名称不得在手写文档中漂移”纳入 CI。