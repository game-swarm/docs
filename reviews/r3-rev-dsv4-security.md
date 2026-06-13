# Security Review — DeepSeek V4 Pro (Round 3)
**Verdict**: CONDITIONAL_APPROVE — 核心架构正确，3 Critical 需 Phase 0 闭合

## Critical (C1-C3)
- **C1**: Fuel Refund Model 需定义退还时序 + 上限 + 滥用检测（否则 refund 成 DoS 向量）
- **C2**: IDL Runtime Enforcement — 启动时校验 + 白名单自动生成
- **C3**: Rhai Action Validation — 定义安全边界 + capability 模型

## High (H1-H5)
- **H1**: world_seed 熵源规范（32字节推荐，非不足 128-bit 熵的简单字符串）
- **H2**: HashMap→IndexMap 需在代码中强制执行
- **H3**: host function 签名与 P0-4/P0-8 三个文档统一
- **H4**: refund abuse 指标（连续失败率>80%触发 throttle）
- **H5**: WASM cache version-skew policy

核心判断：WasSandboxExecutor 唯一执行器、MCP 不直接操作实体、单管线校验、单函数可见性——这四个架构决策本身就是最强的安全保证。
