1|# MVP 反馈循环规范
2|
3|> **状态**: 当前 | **日期**: 2026-06-14 | **裁决**: D1 (UX verbs), D3 (公开 replay) | **模式**: World + Arena 双模式
4|
5|## 1. MVP 反馈循环
6|
7|玩家的体验是一个闭环。MVP 必须为人类和 AI 玩家同时闭合：
8|
9|```
10|      学习 (LEARN)    →      决策 (DECIDE)     →      行动 (ACT)
11|  "规则是什么？        "看到当前世界，          "提交本 tick
12|   我能做什么？"        我应该做什么？"           的指令"
13|        ↑                                              │
14|        │                                              │
15|        └────────── 理解 (UNDERSTAND) ←────────────────┘
16|                  "发生了什么？
17|                   我的指令成功了吗？
18|                   为什么失败？为什么输了？"
19|```
20|
21|这四步任何一步断裂，游戏就不可玩。
22|
23|## 2. 学习：上手引导
24|
25|### 2.1 人类程序员（5 分钟教程）
26|
27|```
28|1. 打开 Web 客户端 → 教程房间（独立、隔离）
29|2. 教程 bot（预写、可编辑）自动运行
30|3. 逐步引导覆盖层:
31|   - "这是你的 Spawn。你可以在这里创建 drone。"
32|   - "试试把 'spawn_count = 1' 改成 'spawn_count = 3'"
33|   - "你的 drone 在采集！看着它们收集能量。"
34|   - "在 (5,3) 放一个 Tower 来防守。"
35|4. 引导式代码修改 + 即时反馈（教程 tick 间隔 1s）
36|5. 提示: "你准备好了！部署到 World 或试试 Arena。"
37|```
38|
39|### 2.2 AI 玩家（MCP 教程）
40|
41|```
42|AI agent 连接 → swarm://docs/tutorials/basic-agent
43|返回逐步 MCP 交互指南:
44|
45|1. 调用 swarm_get_snapshot → 查看当前世界状态（相当于人类的「看地图」）
46|2. 调用 swarm_get_available_actions → 了解可用的游戏 API 函数
47|3. 调用 swarm_get_docs → 学习 API 参考和游戏规则
48|4. 生成代码（AI 用自己的能力写 WASM）→ 调用 swarm_validate_module 预检
49|5. 调用 swarm_deploy → 上传编译好的 WASM 模块
50|6. 观察世界变化（swarm_get_snapshot）→ 调试（swarm_explain_last_tick）→ 改进代码
51|7. 重复 4-6
52|
53|示例开发循环（伪代码）:
54|  snapshot = mcp.call("swarm_get_snapshot")
55|  api_docs = mcp.call("swarm_get_docs")
56|  wasm_code = generate_wasm(snapshot, api_docs, strategy)  // AI 写代码
57|  mcp.call("swarm_validate_module", {wasm: wasm_code})      // 预检
58|  mcp.call("swarm_deploy", {wasm: wasm_code, version: "v2"}) // 部署
59|  // 等待几 tick...
60|  explanation = mcp.call("swarm_explain_last_tick")          // 看结果
61|  // 改进代码，再部署
62|```
63|
64|**关键**：AI agent 不是通过 MCP 直接操作 drone——它编写 WASM 代码，drone 由代码控制。这和人类玩家完全相同。
65|
66|### 2.3 Starter Bot
67|
68|各 SDK 提供：
69|
70|| 语言 | Bot | 说明 |
71||------|-----|------|
72|| TypeScript | `basic-harvester` | 3 架 drone，采集最近源，运回能量 |
73|| TypeScript | `tower-defense` | 建造 Tower，基础防守 |
74|| TypeScript | `room-claimer` | 占领房间，升级 Controller |
75|| Rust | `basic-harvester` | 同 TS 版 |
76|| MCP (AI) | `basic-agent` | 演示 MCP tick 循环的 Python 脚本 |
77|
78|Starter bot 必须开箱即编译/运行。一键部署：
79|```
80|swarm deploy ./basic-harvester
81|```
82|
83|## 3. 决策：信息与工具
84|
85|### 3.1 MCP 发现型 Verb
86|
87|| 工具 | 用途 |
88||------|------|
89|| `swarm_get_available_actions` | "我现在能做什么？" 返回当前状态下的可能动作列表 |
90|| `swarm_get_snapshot` | 完整可见世界状态 |
91|| `swarm_dry_run_commands` | "如果我提交这些指令，会成功吗？" snapshot-bound non-authoritative dry-run（前称 validate_plan） |
92|| `swarm://docs/api-reference` | 完整 API 参考（MCP 资源） |
93|
94|### 3.2 人类 IDE 功能
95|
96|```
97|- Monaco 编辑器，内置游戏 API 的完整 TypeScript 类型
98|- 实体字段自动补全（drone.fatigue, source.energy 等）
99|- 行内校验："drone.harvest() 需要 WORK 部件，你的 drone 是 [MOVE, CARRY]"
100|- 一键部署
101|- 版本历史（回滚到之前的 bot）
102|```
103|
104|### 3.3 本地模拟
105|
106|```
107|swarm sim --ticks=5000 --speed=100x
108|```
109|
110|本地运行 5000 tick，100 倍速。无需连接服务器。
111|输出：最终状态 + 指标（采集能量、建造数、战斗结果）。
112|迭代周期：改代码 → `swarm sim`（10s）→ 看结果 → 再改。
113|
114|## 4. 行动：代码部署
115|
116|### 4.1 部署渠道
117|
118|| 玩家类型 | 渠道 |
119||---------|------|
120|| 人类 | Web UI（编辑器中一键部署）或 CLI `swarm deploy` |
121|| AI (MCP) | MCP `swarm_deploy` 工具 |
122|
123|引擎收到新 WASM 模块后，在下一 tick 自动切换到新模块。旧模块保留作为回滚目标。
124|
125|### 4.2 部署流程
126|
127|```
128|1. 编写代码（人类手写 / AI 生成）
129|2. 编译为 WASM（本地工具链 / AI 自身编译能力）
130|3. 预检（swarm_validate_module）← 可选
131|4. 上传（swarm_deploy）→ 引擎加载 → 下一 tick 生效
132|5. 观察结果 → 迭代
133|```
134|
135|没有「直接提交指令」的通道——所有游戏动作必须经过 WASM 沙箱中的代码执行。
136|
137|## 5. 理解：调试与回放
138|
139|### 5.1 每 Tick 解释
140|
141|```
142|GET /api/v1/ticks/4521/explanation?player=42
143|```
144|
145|```json
146|{
147|  "tick": 4521,
148|  "commands_submitted": 5,
149|  "commands_accepted": 4,
150|  "commands_rejected": [
151|    {
152|      "command": "attack target=1002",
153|      "reason": "OutOfRange",
154|      "detail": "你的 drone 在 (5,3)，目标在 (5,8)。距离 5，最大 1。",
155|      "suggestion": "将 drone 移至目标 1 格以内，或使用 RangedAttack（范围 3）。"
156|    }
157|  ],
158|  "state_changes": [
159|    "drone_1001: 移动 (5,3) → (5,2)",
160|    "drone_1001: 从 source_4001 采集 5 能量",
161|    "drone_1002: 在 (12,8) 建造 Extension — 15/100 进度"
162|  ],
163|  "notable_events": [
164|    "source_4001 枯竭 — 寻找新能量源",
165|    "敌方 drone_9001 在 (20,1) 进入你的房间"
166|  ]
167|}
168|```
169|
170|### 5.2 「为什么闲置？」调试
171|
172|```
173|Drone 1003 本 tick 未行动。原因:
174|- 疲劳值: 5（必须为 0 才能行动）
175|- 无 WORK 身体部件（采集/建造/维修需要）
176|- 范围内无目标（最近能量源距离 8，最大采集范围 1）
177|```
178|
179|### 5.3 回放查看器
180|
181|```
182|玩家视角:
183|  - 地图 + 时间滑块（tick 4000 → 5000）
184|  - 播放/暂停/步进控制
185|  - 覆盖层：指令箭头、采集动画、战斗效果
186|  - 侧边栏：选中实体每 tick 的状态
187|  - "分享回放" → 公开 safe view URL
188|
189|观战视角（赛后）:
190|  - 全知视角（双方可见）
191|  - Fog-of-war 切换（显示各玩家实际所见）
192|  - 解说覆盖层（在特定 tick 添加文字注释）
193|```
194|
195|### 5.4 策略指标仪表盘
196|
197|```
198|每玩家、每次部署:
199|  ┌─────────────────────────────────────┐
200|  │  能量效率:      92%                 │
201|  │  指令成功率:    85%                 │
202|  │  平均活跃 Drone: 8.2                │
203|  │  GCL 增长率:    +120/tick           │
204|  │  战斗胜率:      67%                 │
205|  │                                     │
206|  │  常见错误:                          │
207|  │    OutOfRange:    23%               │
208|  │    Fatigued:      12%               │
209|  │    CarryFull:      8%               │
210|  └─────────────────────────────────────┘
211|```
212|
213|自身可见。可选公开分享（竞技情报）。
214|
215|## 6. World 模式 与 Arena 模式
216|
217|### World 模式（持久世界）
218|
219|- 7×24 tick 循环（3s 间隔）
220|- 地图随机生成，持久殖民地、房间占领、资源经济
221|- 玩家随时加入，起点不同——**不追求公平性**
222|- PvE + PvP 共存
223|- 代码随时更新（热重载）
224|- 人类和 AI agent 在同一世界共存
225|- 趣味展示（非竞争排名）：殖民地年龄、GCL、房间数——仅供观赏
226|
227|### Arena 模式（1v1 / 团队）
228|
229|- 比赛制，固定时长（例：5000 tick ≈ 4 小时）
230|- 对称初始条件，双方公平
231|- 独立房间/地图
232|- 胜利条件：摧毁敌方 Spawn，或时限结束时分高者胜
233|- 代码在比赛开始时锁定（赛中不可改）
234|- 赛后自动发布回放
235|- 排行榜按 league 分区：Human/WASM、AI-assisted、AI tournament
236|- 锦标赛分组、赛季
237|
238|## 7. MVP 达成清单
239|
240|| 功能 | 优先级 | 状态 |
241||------|--------|------|
242|| 教程房间（人类） | P0 | ✅ |
243|| MCP 教程资源（AI） | P0 | ✅ |
244|| 3 个 starter bot（TS + Rust + MCP） | P0 | ✅ |
245|| `swarm_get_available_actions` MCP 工具 | P0 | ✅ |
246|| `swarm_dry_run_commands` MCP 工具 | P0 | ✅ |
247|| `swarm_explain_last_tick` MCP 工具 | P0 | ✅ |
248|| 每 tick 指令解释 | P0 | ✅ |
249|| 本地模拟 (`swarm sim`) | P1 | ✅ |
250|| 回放查看器（自身） | P1 | ✅ |
251|| 回放查看器（公开） | P1 | ✅ |
252|| 策略指标仪表盘 | P1 | ✅ |
253|| Arena 模式（比赛制） | P2 | ✅ |
254|| 锦标赛系统 | P2 | ✅ |
255|| 观战解说 | P2 | ✅ |
256|