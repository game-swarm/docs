# 实现期决策项

> 本文档记录 R-appcert-R2 中 Speaker 明确分配至实现阶段（Phase 1/Phase 2）的决策项。
> 这些项在当前设计文档中**不冻结**——需在实现过程中根据实际代码行为最终确定。
> R3 clean-slate 重审时排除本文档中的条目。

## Phase 1 决策项

### ML4: Seed rotation epoch boundary CI

- **来源**: rev-dsv4-architect D5
- **问题**: Seed rotation 在 epoch 边界的行为需要 redb rollback 注入测试验证
- **触发时机**: 引擎 seed_rotation_system 实现完成后
- **决策**: 设计 redb rollback 注入测试，验证 seed rotation 在事务失败/重试下的确定性。测试通过后确定 seed rotation 的 epoch boundary 语义
- **当前默认**: 10,000 tick 自动轮换，Blake3(旧种子, 当前tick)

---

### ML6: redb nonce post-crash replay 窗口

- **来源**: rev-dsv4-architect D5, rev-dsv4-security M4
- **问题**: nonce 若只保存在易失热路径中，进程崩溃后 TTL 窗口内可重放。高价值操作（admin）需要更强的防重放
- **触发时机**: Auth Service 实现完成后，进行 crash-recovery 集成测试
- **决策**: 
  - 是否将 admin 操作 nonce 持久化到 redb（牺牲热路径延迟换取崩溃安全）
  - 或接受普通查询的易失 nonce 窗口风险，仅对 admin 操作额外加 challenge-response
- **当前默认**: Admin 使用 challenge-response + redb 持久化 nonce；普通 MCP 查询使用 Gateway 进程内 TTL nonce cache

---

### ML9: Code signing re-sign tooling

- **来源**: rev-gpt-security H4, rev-dsv4-security M3
- **问题**: CodeSigningCertificate 批量重签（key rotation / compromise recovery）需要工具链支持
- **触发时机**: CodeSigningCertificate 体系实现 + 首次私钥轮换测试
- **决策**:
  - batch re-sign 的 CLI/API 接口设计
  - dry-run 模式（预览重签范围，不实际提交）
  - 重签期间的部署窗口策略（暂停部署 vs 允许旧签名模块继续运行）
- **当前默认**: 旧签名模块在证书到期前继续有效（code signing 验证的是 deploy 时刻的证书有效性，非运行时刻）

---

### ML13: Replay / 社区观赏面

- **来源**: rev-dsv4-designer M1, rev-dsv4-architect D8
- **问题**: Replay 数据的社区分享、观战 UI、排行榜/精彩回放等产品化功能
- **触发时机**: TickTrace + Replay 引擎功能稳定后
- **决策**:
  - Replay 分享格式（二进制 delta vs 可读 JSON）
  - 观战 UI 的 spectate delay 默认值（World vs Arena）
  - 社区排行榜的数据提取 pipeline
- **当前默认**: Spectate delay 服主可配置（World 默认 30s，Arena 默认 10s），Replay 格式为 TickTrace JSON

---

### ML14: Arena fog-of-war 深度

- **来源**: rev-dsv4-designer G5
- **问题**: Arena 模式的战争迷雾深度——完全对称可见 vs 部分隐藏 vs 完全 fog-of-war
- **触发时机**: Arena 模式实现 + playtest 反馈
- **决策**:
  - Arena 是否使用与 World 相同的 visibility rules
  - 或引入 Arena 专用 fog-of-war 模式（如仅可见己方 + 公共区域）
- **当前默认**: Arena 继承 World 的 `is_visible_to` 规则，`fog_of_war` 默认 `true`

---

## Phase 2 决策项

### 反垄断/反操纵设计

---

## 实现期验证场景（D7 经济模拟 benchmarks）

以下场景在 Phase 1/Phase 2 中需通过经济模拟验证，R2.5 只列出清单不产出数值：

| 场景 | 验证目标 | Phase |
|---|---|---|
| 500 玩家 × 1000 tick 长期运行 | 存储税是否有效抑制无限囤积 | Phase 1 |
| 新玩家在饱和世界中的发展速度 | anti-snowball 机制是否提供可行发展窗口 | Phase 1 |
| 100 账号批量注册 | PoW 成本是否构成有效门槛 | Phase 1 |
| 大帝国 (20 rooms, 500 drones) 维护费可持续性 | O(n²) 维护费是否产生自然收敛 | Phase 2 |

---

## 不在本文档范围内的项

以下 Speaker Verdict 中的项已通过文档冻结解决，不需要实现期决策：

- B1-B5: 全部合同已冻结
- Direction-Specific High (7 项): 全部已写入设计文档
- ML1-ML3, ML5, ML7-ML8, ML10-ML12, ML15-ML16: 全部已写入文档
- D1-D7: 全部已裁决 + D3/D4 设计已写入
