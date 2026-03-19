# Agent Research OS 前沿参考

Purpose: Provide a precise reference memo for Pixiu's next-generation agent architecture, memory design, tool layer, and empirical research workflow.
Status: active
Audience: implementer
Canonical: no
Owner: research
Last Reviewed: 2026-03-19

> 最后更新：2026-03-19

这份文档属于长期参考资料，而不是当前实现真相。

使用方式：

- 需要重新思考 Pixiu 下一阶段的技术栈时，先看这里
- 需要知道当前代码已经实现了什么时，回到 `docs/overview/` 和 `docs/design/`
- 需要做架构取舍时，把这里当作 `adopt / borrow / watch / avoid` 参考，而不是直接当作实现规范

---

## 1. 先给结论

对 Pixiu 这种 `alpha research OS` 来说，最值得吸收的前沿不是“更会聊天的 agent”，而是四类能力：

1. `反思 / 自修正`
2. `技能沉淀 / 程序性知识管理`
3. `分层记忆 + 可审计 artifact`
4. `像经济学研究一样管理假设、识别、稳健性和负结果`

当前 Pixiu 的真正短板，不是“没有 memory”，而是：

- `Stage 2` 还没有真正具备 tool-bound 研究能力
- “智能性”还没有被严格拆分到 `model / skills / MCP / memory / evals`
- 研究流程已经像 research OS，但实验规范还不够像经济学研究

和当前代码最相关的入口：

- [AlphaResearcher](../../src/agents/researcher.py)
- [FactorPool](../../src/factor_pool/pool.py)
- [StateStore](../../src/control_plane/state_store.py)
- [PreFilter](../../src/agents/prefilter.py)

---

## 2. Pixiu 当前状态，用什么标准评估外部技术

Pixiu 现在已经不是一个简单的 RAG agent，而是三类记忆并存：

- `研究对象记忆`
  - 由 [FactorPool](../../src/factor_pool/pool.py) 管理
  - 包含因子结果、研究笔记、探索结果、失败约束、相似失败检索
- `控制平面记忆`
  - 由 [StateStore](../../src/control_plane/state_store.py) 管理
  - 包含 run、snapshot、artifact、human decision
- `提示上下文记忆`
  - 由市场上下文、skills、失败约束注入等组成

因此评估外部系统时，推荐只问四个问题：

1. 它能否扩大 `hypothesis space`，而不是把“聪明”下沉到执行层？
2. 它能否提升 `research provenance`，而不是把真相藏进不可追踪的聊天记忆？
3. 它能否增强 `runtime self-improvement`，而不是只增强表面对话体验？
4. 它是否适合 A 股研究对象，而不是只适合个人助理或通用聊天产品？

---

## 3. P0 级参考：最值得借鉴的论文与系统

### 3.1 Runtime Self-Improvement

| 项目 | 类型 | 核心贡献 | 对 Pixiu 的直接价值 | 结论 |
|---|---|---|---|---|
| [Reflexion](https://arxiv.org/abs/2303.11366) | paper | verbal RL、episodic memory、trial 后反思 | 很适合 `Stage 2 -> Stage 5 -> 下一轮 Stage 2` 的失败复盘闭环 | `Adopt pattern` |
| [Self-Refine](https://arxiv.org/abs/2303.17651) | paper | `generate -> critique -> refine` | 很适合 hypothesis、FactorResearchNote、CriticVerdict 的轻量自修正 | `Adopt pattern` |
| [Voyager](https://arxiv.org/abs/2305.16291) | paper/system | 自动课程、skill library、长期技能积累 | 最贴近 Pixiu “扩大 hypothesis space” 的精神 | `Adopt pattern` |
| [MemGPT](https://arxiv.org/abs/2310.08560) | paper/system | 分层记忆、虚拟上下文管理 | 很适合定义 working / episodic / archival memory 边界 | `Borrow architecture` |
| [A-MEM](https://arxiv.org/abs/2502.12110) | paper | 动态组织记忆、Zettelkasten 风格互联、记忆演化 | 很适合“失败约束网络”和“假设关系网络” | `Borrow architecture` |
| [Zep / Graphiti](https://arxiv.org/abs/2501.13956) | paper/system | 时间感知知识图谱记忆 | 适合 regime、因子、失败模式之间的关系检索 | `Borrow architecture` |
| [AutoGen](https://arxiv.org/abs/2308.08155) | paper/system | 多 agent 协同、工具与人类集成 | 如果后面要把 Stage 2 做成研究团队编排，很有参考价值 | `Borrow selectively` |
| [OS-Copilot](https://arxiv.org/abs/2402.07456) | paper | grounded computer agent、自改进 workflow | 对工具调用和评测设计有启发，但不是 Pixiu 核心主线 | `Watch` |

### 3.2 研究型 software / evaluator-driven evolution

| 项目 | 类型 | 核心贡献 | 对 Pixiu 的直接价值 | 结论 |
|---|---|---|---|---|
| [AlphaEvolve](https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/) | official system blog | `population + evaluator + LLM mutation` 的进化式程序搜索 | 很适合启发“候选假设族群 + evaluator 选择压力 + 自动变异” | `Borrow search pattern` |
| [AI as a research partner: Advancing theoretical computer science with AlphaEvolve](https://research.google/blog/ai-as-a-research-partner-advancing-theoretical-computer-science-with-alphaevolve/) | official research blog | 强调“先验证、再接受发现”，并把 correctness 当瓶颈管理 | 很适合 Pixiu 的 `Stage 3-5` 审稿逻辑 | `Borrow evaluation philosophy` |
| [EvoScientist](https://arxiv.org/abs/2603.08127) | paper/system | `Research Agent + Experiment Agent + Evolution Manager`，显式区分 `ideation memory` 和 `experimentation memory` | 是目前最接近 Pixiu 的“研究型 agent OS”参考之一，尤其适合启发跨轮知识蒸馏和研究演化层 | `Borrow strongly` |

对 Pixiu 来说，这一组文献共同支持一个结论：

- 优先做 `runtime loop + evaluator + memory`
- 不优先做模型微调或“更大模型替换一切”

---

## 4. 用 Skills / MCP / Memory 管理智能性的现代做法

### 4.1 MCP 应该被看成工具边界，而不是 agent runtime

Model Context Protocol 官方文档把 MCP 明确定义为：

- host / client / server 架构
- data layer + transport layer
- primitives 包括 `tools / resources / prompts / notifications`

官方架构文档：

- [MCP Architecture Overview](https://modelcontextprotocol.io/docs/learn/architecture)

对 Pixiu 的启发：

- `MCP` 负责连接数据源和工具，不负责定义研究流程
- `LangGraph / orchestrator` 负责流程
- `FactorPool / StateStore` 负责 durable truth
- `skills` 负责程序性研究知识
- `evals / hard gates` 负责保留和淘汰

换句话说，MCP 应该是 `capability plane`，不是 `reasoning plane`。

### 4.2 OpenClaw 的 skills 体系，是“管理智能性”的好参考

OpenClaw 官方 skills 文档有几个很值得学的点：

- skills 以 `SKILL.md` 目录打包
- 支持 bundled / local / workspace 三层加载与优先级
- 支持 load-time gating：按 `bins / env / config / os` 决定是否激活
- 支持 per-run env injection，并在 run 结束后恢复环境
- 明确记录 token impact，不把 skills 当成“无限免费提示词”

官方文档：

- [OpenClaw Skills](https://docs.openclaw.ai/tools/skills)

对 Pixiu 的启发：

- skills 不应只是 prompt 片段
- skills 应该显式描述：
  - 适用子空间
  - 依赖哪些工具
  - 需要哪些 secrets / binaries
  - 在什么 regime 或任务下激活
- skills 应该和 `Stage 2` 的 tool use 绑定，而不是只做静态注入

### 4.3 Letta 的 memory blocks，适合做“总在上下文里”的核心记忆

Letta 的 memory blocks 有两个特征很值得借鉴：

- `always visible`
- `agent-managed`

官方文档：

- [Introduction to Stateful Agents](https://docs.letta.com/guides/core-concepts/stateful-agents/)
- [Memory blocks](https://docs.letta.com/guides/core-concepts/memory/memory-blocks)

对 Pixiu 的启发：

- 不要让所有记忆都走检索
- 某些核心内容应该永远在上下文里，例如：
  - authority model
  - 当前轮实验边界
  - 当前 island / subspace 约束
  - 当前 run 的 hard constraints

### 4.4 官方维护生态：Anthropic 更强在插件打包，OpenAI 更强在 agent primitives

如果只看“官方维护、且和 Pixiu 相关”的技能与 MCP 生态，目前可以粗略分成两条路线：

| 生态 | 官方重心 | 对 Pixiu 最有参考价值的部分 | 结论 |
|---|---|---|---|
| Anthropic | `plugin / skills / MCP connectors / vertical workflow packaging` | 如何把领域能力打包成可安装、可配置、可治理的插件层 | `Borrow strongly for packaging` |
| OpenAI | `agents / guardrails / tracing / hosted MCP / apps` | 如何把 agent runtime、MCP、审批、trace、评测做成底层基础设施 | `Borrow strongly for runtime infrastructure` |

#### Anthropic 官方资产

1. `knowledge-work-plugins`
   - 官方把垂直工作流拆成 `plugin.json + .mcp.json + skills + commands`
   - 很适合 Pixiu 未来做 `a-share-core / narrative-mining / macro / broker / mirofish` 这类插件层
   - 来源：
     - [knowledge-work-plugins](https://github.com/anthropics/knowledge-work-plugins/tree/main)
     - [raw README](https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/README.md)

2. `finance` 插件
   - 值得借的是 workflow packaging，不是财务业务本体
   - 它的 `.mcp.json` 已预留 `bigquery / slack / microsoft365 / gmail / google-calendar` 等连接面，但 `ERP / analytics` 仍更多是类别占位符
   - 这说明它更像“高风险知识工作的插件模板”，而不是开箱即用的 finance OS
   - 来源：
     - [finance README](https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/finance/README.md)
     - [finance .mcp.json](https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/finance/.mcp.json)
     - [finance CONNECTORS](https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/finance/CONNECTORS.md)

3. `claude-plugins-official`
   - 这是 Anthropic 官方维护的 Claude Code 插件目录
   - README 明确给出标准结构：`.claude-plugin / .mcp.json / commands / agents / skills / README`
   - 这对 Pixiu 很有参考价值，因为它说明 Anthropic 不是只把 skills 当 prompt，而是把 `agents + skills + MCP` 当成同一安装单元
   - 来源：
     - [claude-plugins-official](https://github.com/anthropics/claude-plugins-official)

4. `life-sciences`
   - 这是官方垂直 marketplace 的更强样板
   - 里面不是一个插件，而是一组行业插件，可通过 `/plugin marketplace add ...` 和 `/plugin install ...` 装入
   - 对 Pixiu 的启发是：未来完全可以做“量化研究 marketplace”而不是单一大插件
   - 来源：
     - [life-sciences](https://github.com/anthropics/life-sciences)

5. `Anthropic MCP connector`
   - Claude API 现在官方支持直接通过 Messages API 连远程 MCP server
   - 当前限制是：只支持 `tool calls`
   - 对 Pixiu 的启发是，未来如果要支持远程 Researcher tool plane，这条官方路径值得关注
   - 来源：
     - [MCP connector](https://platform.claude.com/docs/en/agents-and-tools/mcp-connector)

#### OpenAI 官方资产

1. `OpenAI Agents SDK`
   - 官方重心是 agent primitives：
     - agents
     - tools
     - handoffs
     - guardrails
     - tracing
   - 这对 Pixiu 的 `Coordinator / Researcher / Evaluator / Human gate` 很有参考意义
   - 来源：
     - [Agents SDK](https://openai.github.io/openai-agents-python/)

2. `Agents SDK MCP support`
   - 官方已经明确支持多种 MCP transport
   - 同时有 Hosted MCP、tool filtering、approval policies、failure handling 等能力
   - 这比“会不会接一个 MCP server”更重要，因为它直接对应 Pixiu 的 tool governance
   - 来源：
     - [Agents SDK MCP](https://openai.github.io/openai-agents-python/mcp/)

3. `Apps SDK`
   - 官方 Help Center 明确写了 Apps SDK built on MCP
   - 这条线更偏 ChatGPT 内部 app packaging 和 UI，但对未来 Pixiu 的 dashboard/plugin 化也有启发
   - 来源：
     - [Build with the Apps SDK](https://help.openai.com/en/articles/12515353-build-with-the-apps-sdk)
     - [Apps in ChatGPT](https://help.openai.com/en/articles/12503483-apps-in-chatgpt-and-the-apps-sdk)

4. `openai-mcpkit`
   - 这是目前我看到最值得 Pixiu 认真研究的 OpenAI 官方仓库
   - 它的定位是“为企业私有数据进入 ChatGPT 提供安全的 MCP blueprint”
   - 仓库里甚至直接有 `synthetic_financial_data/`，明确把金融研究报告、expert calls、alternative data 作为样例
   - 这和 Pixiu 的未来数据平面很贴近
   - 来源：
     - [openai-mcpkit](https://github.com/openai/openai-mcpkit)

5. `金融案例页`
   - OpenAI 官方没有像 Anthropic 那样直接给出 finance plugin，但有很强的行业案例
   - 最值得看的是：
     - [Hebbia](https://openai.com/index/hebbia/)
   - 它的重点不是插件，而是“多 agent + 私有数据 + 深研究”的 workflow，这对 Pixiu 的 research OS 定位很有启发

#### 对 Pixiu 的结论

- 如果你想学“怎么组织领域能力”，优先看 Anthropic
- 如果你想学“怎么把 agent runtime、MCP、审批、trace 做扎实”，优先看 OpenAI
- Pixiu 最合理的路线不是二选一，而是：
  - `Anthropic-style domain packaging`
  - `OpenAI-style runtime primitives`

### 4.5 ARIS：更像 research workflow + skills methodology，不是完整 research OS

`Auto-claude-code-research-in-sleep` 更像一套“研究自动化 workflow 方法论 + skills 库”，而不是完整的 research OS。

一手来源：

- [ARIS GitHub](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
- [ARIS README](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/README.md)
- [research-review skill](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/skills/research-review/SKILL.md)
- [experiment-bridge skill](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/skills/experiment-bridge/SKILL.md)
- [novelty-check skill](https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/skills/novelty-check/SKILL.md)

它最值得 Pixiu 借的部分：

- `cross-model review`
  - 不让同一个模型闭环完成生成、实现、审稿，避免陷入局部最优
- `markdown-first skills`
  - 把研究 protocol 显式写成 `SKILL.md`，让研究流程可迁移、可审阅、可版本化
- `experiment bridge`
  - 在高成本实验前，先做计划、代码复审和 sanity check
- `novelty-check workflow`
  - 先抽 claim，再做多源文献或近邻工作比对，最后进入 reviewer 判断

它不适合直接拿来替代 Pixiu 的部分：

- 它没有 Pixiu 这种 `FactorPool + StateStore + hard gate` 的 durable truth 层
- 它更像研究 protocol 层，而不是研究资产操作系统

对 Pixiu 的结论：

- `Borrow workflow patterns`
- `Do not replace control plane or typed memory`

---

## 5. OpenClaw：该借什么，不该借什么

### 5.1 它是什么

OpenClaw 更像一个快速演化中的个人 AI runtime / gateway，而不是研究论文或量化研究框架。

官方一手来源：

- [OpenClaw GitHub](https://github.com/openclaw/openclaw)
- [OpenClaw Docs](https://docs.openclaw.ai/index)
- [Agent Loop](https://docs.openclaw.ai/concepts/agent-loop)
- [Memory](https://docs.openclaw.ai/concepts/memory)
- [Model Failover](https://docs.openclaw.ai/concepts/model-failover)

### 5.2 真正值得 Pixiu 借的部分

- `串行 session loop`
  - OpenClaw 明确把一次 agent run 定义成 `intake -> context assembly -> model inference -> tool execution -> streaming replies -> persistence`
  - 并按 session 做 serialized run
- `hookable lifecycle`
  - 适合给 Pixiu 的每一轮实验补 lifecycle hooks
- `model failover`
  - 适合长实验、长回合研究任务
- `skills registry + gating`
  - 适合把“研究套路”从 prompt 拼接升级成能力层

### 5.3 不该照搬的部分

- 面向 WhatsApp / Telegram / iMessage / voice 的产品层
- 个人助理式的入口和交互模型
- 将自然语言会话当成主要真相源的倾向

### 5.4 对 Pixiu 的结论

- `Borrow runtime patterns`
- `Do not adopt product shape`

---

## 6. Mem0：适合做 sidecar，不适合替代 Pixiu 当前 memory

### 6.1 Mem0 擅长什么

官方一手来源：

- [Mem0 GitHub](https://github.com/mem0ai/mem0)
- [Memory Types](https://docs.mem0.ai/core-concepts/memory-types)
- [Add Memory](https://docs.mem0.ai/core-concepts/memory-operations/add)
- [Search Memory](https://docs.mem0.ai/core-concepts/memory-operations/search)
- [Update Memory](https://docs.mem0.ai/core-concepts/memory-operations/update)
- [Delete Memory](https://docs.mem0.ai/core-concepts/memory-operations/delete)
- [Graph Memory](https://docs.mem0.ai/open-source/features/graph-memory)
- [Mem0 Research](https://mem0.ai/research)

它擅长的事情包括：

- conversation / session / user 等分层记忆
- 自动抽取 salient facts
- `add / search / update / delete` 生命周期
- graph-enhanced retrieval
- 对长会话或个体化 assistant 记忆非常友好

### 6.2 它不擅长什么

Mem0 不是：

- control plane
- typed research artifact store
- immutable provenance ledger
- 审计优先的实验数据库

也就是说，它擅长“记住重要的事”，但不擅长“成为研究真相源”。

### 6.3 为什么不应该替代 Pixiu 的现有 memory

当前 Pixiu 已经有：

- [FactorPool](../../src/factor_pool/pool.py)
  - 因子、研究笔记、探索结果、失败约束、相似失败检索
- [StateStore](../../src/control_plane/state_store.py)
  - run、snapshot、artifact、human decision
- [AlphaResearcher 失败约束注入](../../src/agents/researcher.py)
- [Stage 3 ConstraintChecker](../../src/agents/prefilter.py)

这些对象的共同特点是：

- 强结构化
- 可审计
- 可溯源
- 可被 hard gate 直接消费

而 Mem0 的 update semantics 更适合：

- 用户偏好
- 会话记忆
- 操作员偏好
- 自然语言备注的长期 recall

### 6.4 对 Pixiu 的结论

推荐的组合不是 `Mem0 instead of RAG`，而是：

- `typed artifact memory`
  - 研究真相、失败约束、实验结果
- `graph / temporal retrieval`
  - 因子、regime、失败模式、来源之间的关系
- `session / operator memory`
  - 可以考虑 Mem0 或类似系统

结论：

- `Do not replace FactorPool / StateStore`
- `Mem0 can be a sidecar`

---

## 7. 像经济学研究一样工作的 Pixiu

如果 Pixiu 真的想成为 research OS，而不是“会生成因子的 agent”，最值得借的是经济学和经验研究的方法论。

### 7.1 预分析计划 / preregistration

可参考：

- [AEA RCT Registry](https://www.socialscienceregistry.org/)
- [OSF Preregistration guidance](https://www.cos.io/initiatives/prereg)

对 Pixiu 的翻译：

- 每个实验 run 都应有 `pre-analysis plan`
- 在运行前固定：
  - research question
  - primary metrics
  - robustness checks
  - promoted / rejected threshold
  - sample split / regime split

这会把“跑完再想怎么解释”变成“先定义怎么判”。

### 7.2 Specification Curve Analysis

一手来源：

- [Specification curve analysis](https://www.nature.com/articles/s41562-020-0912-z)

对 Pixiu 的启发：

- 不要只看一个回测设定
- 对关键结论，应系统枚举合理但不同的 specification：
  - rebalancing frequency
  - transaction cost assumptions
  - subperiod split
  - universe choice
  - winsorization / normalization variants

Pixiu 未来可以把这套东西做成：

- `robustness suite`
- `specification curve report`

### 7.3 Robustness by design

一手来源：

- [Designing, not Checking, for Policy Robustness](https://www.nber.org/papers/w28098)
- [Robustness Checks in Structural Analysis](https://www.nber.org/papers/w30443)

对 Pixiu 的启发：

- 不只在结尾做 robustness checks
- 在 hypothesis design 阶段就把不确定性和 regime dependence 纳入设计

### 7.4 对 Pixiu 的具体翻译

未来更像经济学研究的运行方式，应该包含：

- `pre-analysis plan`
- `negative results archive`
- `referee-style verdict`
- `specification curve`
- `regime split / subperiod split / placebo checks`

---

## 8. 对 Pixiu 的 Adopt / Borrow / Watch / Avoid

### 8.1 Adopt Now

- `Stage 2 MCP / ReAct upgrade`
  - 让 Researcher 能主动消费 RSS / AKShare / Tushare / FRED 等工具
- `Reflexion / Self-Refine loop`
  - 用于 hypothesis drafting、post-mortem、structured output correction
- `research eval stack`
  - 预定义 metrics、robustness suite、负结果归档

### 8.2 Borrow Selectively

- `OpenClaw`
  - 借 skills、failover、serialized loop、hook model
- `EvoScientist`
  - 借 `ideation memory / experimentation memory` 分层，以及 `Evolution Manager` 风格的跨轮知识蒸馏
- `ARIS`
  - 借 cross-model review、experiment bridge、novelty-check 这类研究 protocol skills
- `Anthropic knowledge-work-plugins / claude-plugins-official`
  - 借 plugin packaging、skills/agents/MCP 一体化组织方式
- `OpenAI Agents SDK / MCPKit`
  - 借 guardrails、tracing、hosted MCP、approval policy、安全授权的数据面 blueprint
- `MemGPT / Letta`
  - 借 working memory / pinned memory / memory blocks 概念
- `Mem0 / Zep / A-MEM`
  - 借分层记忆、graph memory、temporal retrieval
- `AlphaEvolve`
  - 借 evaluator-driven mutation / population search

### 8.3 Watch

- `OSWorld`
  - 对 future operator agent / dashboard agent 的 benchmark 有意义
  - 当前对核心 alpha research loop 不是第一优先
  - 官方仓库：[OSWorld](https://github.com/xlang-ai/OSWorld)
- `OpenCUA / OSWorld-G`
  - 更偏 computer-use 与 GUI grounding
  - 可用于未来产品层 agent 评测

### 8.4 Avoid

- 用可变聊天记忆替代 typed research truth
- 把“智能性”堆到执行层
- 把 consumer assistant runtime 当作 Pixiu 主架构
- 在没有稳定 evals 前先大规模追逐 memory 新框架

---

## 9. 我对 Pixiu 下一阶段的正式建议

按优先级排序：

1. `先补 Stage 2`
   - 这是当前最大的架构缺口
2. `再补 research eval discipline`
   - 让实验流程更像经济学研究
3. `再补 evolution-manager-like synthesis`
   - 把跨轮 run 的失败、成功、边界条件蒸馏成可复用研究知识
4. `再升级 skills + pinned memory`
   - 把程序性知识和核心上下文显式化
5. `最后再决定 Mem0 / graph memory 的接入形态`
   - 作为增强层，而不是真相层

如果只能选一件最重要的事：

- 不是接 Mem0
- 不是接 OpenClaw
- 而是把 `AlphaResearcher` 升级成真正能用 `MCP tools + failure memory + skill constraints` 主动做研究的上游 agent

---

## 10. Source Index

### Papers and official research pages

- Reflexion: https://arxiv.org/abs/2303.11366
- Self-Refine: https://arxiv.org/abs/2303.17651
- Voyager: https://arxiv.org/abs/2305.16291
- MemGPT: https://arxiv.org/abs/2310.08560
- A-MEM: https://arxiv.org/abs/2502.12110
- Zep / Graphiti: https://arxiv.org/abs/2501.13956
- AutoGen: https://arxiv.org/abs/2308.08155
- OS-Copilot: https://arxiv.org/abs/2402.07456
- AlphaEvolve official overview: https://deepmind.google/discover/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/
- AlphaEvolve research write-up: https://research.google/blog/ai-as-a-research-partner-advancing-theoretical-computer-science-with-alphaevolve/
- EvoScientist paper: https://arxiv.org/abs/2603.08127
- EvoScientist repo: https://github.com/EvoScientist/EvoScientist
- EvoScientist README: https://raw.githubusercontent.com/EvoScientist/EvoScientist/main/README.md

### Tooling and runtime docs

- MCP architecture: https://modelcontextprotocol.io/docs/learn/architecture
- OpenClaw repo: https://github.com/openclaw/openclaw
- OpenClaw agent loop: https://docs.openclaw.ai/concepts/agent-loop
- OpenClaw skills: https://docs.openclaw.ai/tools/skills
- OpenClaw memory: https://docs.openclaw.ai/concepts/memory
- OpenClaw model failover: https://docs.openclaw.ai/concepts/model-failover
- Anthropic knowledge-work-plugins: https://github.com/anthropics/knowledge-work-plugins/tree/main
- Anthropic finance plugin: https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/finance/README.md
- Anthropic finance connectors: https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/finance/CONNECTORS.md
- Anthropic finance MCP config: https://raw.githubusercontent.com/anthropics/knowledge-work-plugins/main/finance/.mcp.json
- Anthropic Claude plugins official: https://github.com/anthropics/claude-plugins-official
- Anthropic life-sciences marketplace: https://github.com/anthropics/life-sciences
- Anthropic MCP connector: https://platform.claude.com/docs/en/agents-and-tools/mcp-connector
- Mem0 repo: https://github.com/mem0ai/mem0
- Mem0 memory types: https://docs.mem0.ai/core-concepts/memory-types
- Mem0 graph memory: https://docs.mem0.ai/open-source/features/graph-memory
- Mem0 research: https://mem0.ai/research
- Letta stateful agents: https://docs.letta.com/guides/core-concepts/stateful-agents/
- Letta memory blocks: https://docs.letta.com/guides/core-concepts/memory/memory-blocks
- OpenAI Agents SDK: https://openai.github.io/openai-agents-python/
- OpenAI Agents SDK MCP: https://openai.github.io/openai-agents-python/mcp/
- OpenAI Apps SDK overview: https://help.openai.com/en/articles/12515353-build-with-the-apps-sdk
- OpenAI apps in ChatGPT: https://help.openai.com/en/articles/12503483-apps-in-chatgpt-and-the-apps-sdk
- OpenAI MCPKit: https://github.com/openai/openai-mcpkit
- OpenAI Hebbia case study: https://openai.com/index/hebbia/
- ARIS repo: https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep
- ARIS README: https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/README.md
- ARIS research-review skill: https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/skills/research-review/SKILL.md
- ARIS experiment-bridge skill: https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/skills/experiment-bridge/SKILL.md
- ARIS novelty-check skill: https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/skills/novelty-check/SKILL.md

### Empirical research methodology

- AEA RCT Registry: https://www.socialscienceregistry.org/
- OSF preregistration: https://www.cos.io/initiatives/prereg
- Specification curve analysis: https://www.nature.com/articles/s41562-020-0912-z
- Designing, not Checking, for Policy Robustness: https://www.nber.org/papers/w28098
- Robustness Checks in Structural Analysis: https://www.nber.org/papers/w30443
