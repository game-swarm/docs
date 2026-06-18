# R-appcert-R2 Clean-Slate Review — Game Designer / GPT-5.5

## Verdict

CONDITIONAL_APPROVE

R-appcert-R2 从游戏设计视角已经达到“可以继续作为实现前设计基线”的水平：它把 AI 与人类玩家统一到 WASM 部署路径，补齐了 MCP onboarding、首 tick 反馈、教程、Replay、旁观、PvE 过渡、账号/设备恢复等关键体验面。核心游戏不再只是技术展示，而是有明确的首小时循环、策略表达空间和社区传播骨架。

但仍不建议直接 APPROVE。主要风险不在认证安全本身，而在“玩家第一小时能不能稳定从注册 → 编译 → 部署 → 看懂结果 → 产生第二次迭代”这一体验链上：文档内存在 API 命名/字段示例割裂、AI MCP 资源缺少可执行学习包的完成定义，以及长期追求仍偏向指标展示而非目标系统。这些问题不必推翻架构，但需要在设计文档中收口为明确合同，否则实现阶段会制造大量 UX 断点。

## Strengths

- 人类与 AI 玩家路径一致：MCP 明确不提供 `swarm_move` / `swarm_attack` 等直接操作，AI 必须查看世界、生成代码、编译 WASM、部署模块；这保护了“代码就是军队”的核心幻想，也避免 AI 玩家拥有不同输入通道。
- 第一小时体验明显增强：5 分钟教程、starter bot、safe_mode、soft_launch、PvE 威胁、资源潮、公共事件和首次 PvP 战斗报告，形成从无压力学习到低风险冲突再到正式 PvP 的心理坡度。
- 策略深度有真实抓手：轻物流、全局/本地存储转换、Depot 补给线、drone age 维护、body 不可逆、回收试错、特殊攻击和可见性限制共同构成“写代码优化系统”的长期可玩性。
- 调试闭环对编程游戏很关键：`swarm_dry_run_commands`、`swarm_explain_last_tick`、策略指标仪表盘、Replay 查看器和部署事件能回答“为什么没动/为什么失败/下一步改什么”。
- 观战与传播有基础设施：Arena 默认公开观战、赛后公开全知回放、速度控制、视角切换、tick 定位、解说覆盖层和 share URL 都是社区传播所需的核心组件。
- 证书/设备 UX 不再只是安全附录：设备标签、证书列表、到期提醒、passkey/email/admin 恢复、账号删除 grace period、AI agent 凭据持久化要求，能支撑真实玩家长期使用。

## Concerns

### G1 — High — 入门示例与权威 Command schema 存在命名割裂，会直接破坏首小时

GETTING-STARTED 的 TypeScript 示例使用 `action: "SpawnDrone"`、`object_id`、`seq`，而 commands/reference 与 IDL 的权威模型是 `CommandIntent { sequence, action }`，Spawn 示例又写为 `{ "type": "Spawn", "spawn_id": ... }`。这不是小文档瑕疵：编程游戏的第一小时高度依赖复制 starter bot、修改、部署、观察。如果第一段示例无法通过 schema 或 dry-run，玩家/AI 会把失败归因于游戏难懂，而不是文档错误。

建议：把 `08-api-idl.md` 生成的 JSON schema 作为唯一示例来源，GETTING-STARTED、commands.md、MCP docs、starter bot 代码片段全部改为同一 envelope；新增“copy-paste smoke test”：文档中的 basic bot 必须能通过 `swarm_validate_module` 或至少通过 `swarm_dry_run_commands` 的 schema 校验。

### G2 — High — AI “仅通过 MCP resources 学会玩”仍缺少可验证完成标准

设计列出了 `swarm_get_docs`、`swarm_get_schema`、`swarm_get_available_actions`、`swarm_sdk_fetch`、`docs/auth/onboarding-ai`、`docs/tutorials/basic-agent` 等资源，但没有定义这些 resources 的目录结构、最小内容包、版本约束和学习成功判据。AI agent 能“看到工具名”不等于能独立完成从空白到第一个可运行 WASM。

建议：为 MCP resources 定义一个 AI onboarding contract：
- `swarm://docs/tutorials/basic-agent` 必须包含注册、SDK 拉取、最小 bot、编译、签名部署、首 tick 验证的完整步骤。
- `swarm_get_schema` 必须返回当前 world manifest hash 对应的 Command schema，而不是静态 Vanilla schema。
- `swarm_get_docs` 必须支持按任务检索，例如 `goal=first_deploy`、`goal=fix_rejection:OutOfRange`。
- 通过一条验收测试：全新 agent 只使用 MCP tools/resources，不读外部 repo，不访问 Web UI，能部署一个采集 bot 并用 `swarm_explain_last_tick` 证明至少一次 accepted Harvest/Transfer。

### G3 — Medium — 长期追求仍偏“观赏指标”，缺少可策划的目标系统

World 模式明确不追求公平，且不设置竞争排行榜，这是正确方向；但当前长期展示主要是殖民地年龄、GCL、房间数、drone 数、RCL/Controller、Arena/PvE 排行榜。对于持久 MMO RTS，仅靠这些指标容易让玩家把目标收敛为“扩张更多/刷效率更高”，造成老玩家压迫和新玩家无意义追赶。

建议增加非线性长期追求：
- Research/Blueprint tree：PvE、遗迹、市场、社区事件产出蓝图，解锁策略分支而非纯数值膨胀。
- Colony identity：玩家可给殖民地定义公开 doctrine、徽章、tag、外交状态，让“我是谁”可被社区识别。
- Contract reputation：运输、防御、侦察、Arena sparring 合约形成信誉分，给非顶级战斗玩家长期位置。
- Seasonal exhibitions：不重置 World 资产，只举办限时主题 Arena/PvE 展赛，给社区周期性话题。

### G4 — Medium — 反雪球机制分散，缺少“老玩家为什么不能无限压制新玩家”的统一体验合同

设计中已有 safe_mode、soft_launch、World 无竞争榜、PvE 过渡、全局存储税、物流时间、Depot 补给线、可见性限制、Arena 公平对战等反雪球元素。但它们分散在多个文档中，没有形成一个玩家可理解、AI 可查询、服主可调参的 anti-snowball contract。

建议新增一节“World Anti-Snowball Contract”：明确新手保护、扩张摩擦、补给线脆弱性、公开排名限制、老玩家攻击新手区的约束、soft_launch 结束前后的提示、被摧毁后的恢复路径。玩家心理上需要知道“失败后还能回来”，AI agent 也需要能查询保护状态与风险窗口。

### G5 — Medium — 旁观/Replay 具备底层能力，但社区传播产品面还不完整

Replay viewer 有速度控制、视角切换、tick 定位、指令展开和分享 URL；Arena 赛后公开回放也成立。但社区传播不仅是“能看”，还需要“能讲、能剪、能发现”。当前缺少 match summary、精彩片段标记、公开索引和社交上下文。

建议为 Replay 分享补齐：
- 自动生成 match card：参赛者、world/rules hash、胜负、关键指标、转折 tick。
- Clip URL：`replay?t=4200..4500&view=omniscient&note=...`，支持分享 30-120 秒片段。
- Commentary markers：玩家/观众可在 tick 上添加注释，Arena 公开回放可显示精选注释层。
- Public gallery：按 scenario、ruleset、patch version、duration、rating 检索回放。

### G6 — Low — 证书/设备管理 UX 很完整，但可能在首登时过度压迫玩家

应用层证书、CSR、PoW、Root CA fingerprint、CodeSigningCertificate、DeployPayload 对系统设计是必要的；但如果首屏把这些概念全部暴露给人类玩家，会削弱“5 分钟写 bot”的承诺。文档已有 LoginButton 草图，但还需要明确渐进披露策略。

建议：人类默认只看到“创建账号/添加设备/开始教程”，高级面板再展示证书链、fingerprint、scope、TTL；AI/MCP docs 则保留完整低层流程。安全概念应该可审计但不打断第一段乐趣。

## Missing

- 缺少“首小时黄金路径”的端到端验收脚本：人类 Web、CLI、AI MCP 三条路径都应有明确成功条件。
- 缺少 tutorial world 的完整规则包：初始资源、地图、默认 bot、允许手动操作范围、PvE 事件节奏、退出到 World/Arena 的转场。
- 缺少 AI-only MCP resource manifest：哪些 `resources/list` 条目必须存在、每个 resource 的 MIME/schema/version、与 `world.current_manifest_hash` 的关系。
- 缺少失败恢复 UX 矩阵：注册失败、PoW 慢、CSR 失败、SDK mismatch、WASM validation fail、deploy accepted 但 first tick 全拒绝、证书过期、私钥丢失分别如何提示。
- 缺少社区页面信息架构：Arena lobby、Replay gallery、public profile、contract board、tournament page 如何互相导流。
- 缺少玩家动机分层：Builder、Optimizer、Combatant、Teacher、Spectator、Server host 各自的长期目标与可见奖励。

## Fresh Ideas

- “Strategy Notebook”：每次部署自动生成一页实验记录，记录 module hash、指标变化、常见 rejection、玩家备注；可以公开成开发日志，形成编程游戏特有的社区内容。
- “Ghost Rival”：从公开 replay 中选择一个对手的历史 bot 作为本地/教程 ghost，对新手提供可重复挑战的低压目标。
- “Explain My Bot” 模式：`swarm_profile` 不只给数字，还生成三条可执行建议，例如“你的 CarryFull 占 18%，考虑增加 Transfer 优先级或扩展 storage”。
- “Contract Board as Onboarding”：老玩家发布采集/运输/防御合约，新玩家用 starter bot 接单；这是比直接 PvP 更友善的社交入口。
- “Replay-driven Docs”：API 文档中的每个 command 都链接一个 10 tick mini replay，展示命令成功、失败和修正后的差异。
- “World Rules Diff”：加入 modded world 前，以人类/AI 都可读的形式展示与 Vanilla 的差异，并给出 starter bot 需要修改的点。

## Final Recommendation

保持 CONDITIONAL_APPROVE。R-appcert-R2 已经解决了“AI 是否公平接入”“认证是否能支撑自托管/agent”“Replay/观战是否有基础设施”等大问题；下一轮设计收口应集中在可玩性合同而不是再扩展协议面。

进入实现前建议补三份短文档即可关闭本评审的 High/Medium 风险：
1. `First-Hour Acceptance Contract`：人类/CLI/AI 三条黄金路径和成功判据。
2. `MCP Resource Manifest`：AI 仅靠 resources 从注册到首个 accepted command 的完整资源目录。
3. `Progression & Community Loop`：GCL/RCL 之外的长期目标、Replay 分享、合约/声望/蓝图体系。
