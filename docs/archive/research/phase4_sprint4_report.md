# Phase 4 Sprint 4: System Integration & End-to-End Evaluation Report

> Historical report. Kept for milestone traceability only.

## 1. 实验 1：单次端到端跑通 (大逃杀测试)
**目标**：测试 Researcher 提出假设 -> Validator 校验 -> Coder 沙箱执行 -> Critic 量化评分 -> FactorPool 入库的全流程通信流转。
**执行情况**：
- **测试 1.1 `deepseek-reasoner` 工具支持**：
  - 过程说明：直接使用 DeepSeek R1 的推理模型去进行多轮工具问答。由于官方 API 架构限制，`deepseek-reasoner` 模型在使用 LangChain 多轮工具注入时，会因中间件未返回隐式的 `reasoning_content` 内容而触发 HTTP 400 校验异常。
  - 决策记录：经测试确认当前框架（`LangChain` 1.x 封装级别）暂不完美兼容 Reasoning 模型的 function calling 迭代。
  - **退回至 `deepseek-chat` (V3 模型)**。
- **测试 1.2 `deepseek-chat` V3 回退测试**：
  - 过程说明：调整 prompt 强化严格 JSON 输出能力。挂载 11 个 AKShare 实时金融源。
  - 结果：`deepseek-chat` 成功主动检索 `get_northbound_flow_today` (北向资金)，提取最新热点资金偏好。随后输出了标准的基于 `volume_confirmed` 动量因子 Qlib 公式，送入沙箱并通过。
  - **结论：端到端链路完全打通，通信闭环建立**。

## 2. 实验 2 & 3：技能库装载与工具探测
**目标**：监控 `SkillLoader` 按角色注入上下文（实验3），以及深度观察大语言模型 MCP 工具意图理解能力（实验2）。
**执行情况与决策**：
- 资源池审计：`a_share_constraints.md` (A 股硬约束)、`qlib_formula_syntax.md` 等架构分离文档存在并在节点前自动组合拼接进最终的 System Prompt。
- 我们验证到大模型在失败后（沙箱传回 Python 异常 Traceback）会自动触发 C 级（Type C）上下文注入（如 `feedback_interpretation.md`），真正做到了 **动态认知反思**，没有出现早期盲猜报错的死循环。

## 3. 实验 4：Validator 硬约束静态查验
**目标**：评估引入的无代理轻量级审查节点，拦截非法的 Qlib 公式以减少沙箱交互成本。
**执行日志与测试用例验证**：
- 测试 `Ref($close, -1)` (前视未来函数)：准确拦截 `Passed=False, Msg=[Validator 拦截] 检测到 Ref() 使用负数偏移...`。
- 测试 `Mean($price, 5)` (未注册列字段假想)：准确拦截 `Passed=False, Msg=[Validator 拦截] 使用了不存在的字段...`。
- 测试 `Log($close - Ref($close, 1))` (潜在负参数输入)：准确拦截 `Passed=False, Msg=[Validator 拦截] Log() 的参数可能为负数...`。
**决策记录**：此步骤前置有效地剔除了低智商公式语法崩盘率，使得进入沙箱调试（每次 2-5 分钟等待）的因子都天然遵守金融硬逻辑。

## 4. 下阶段提议 - 实验 5：长周期演化循环评测
**测试构思**：
目前基础架构所有齿轮运转平稳，接下来拟执行 `python src/core/orchestrator.py --mode evolve --rounds 20` 投入真实算力挂机 1—2 个小时：
- 观察 FactorPool 中最优因子 (Sharpe Ratio) 指标的滚动衰变与突变。
- 测试 `IslandScheduler` （基于 Softmax 胜率轮换的遗传变调算法）是否会在 `momentum` 群陷入长期局部僵死时，主动通过退火抽样切换去 `volatility` (波动率)。
