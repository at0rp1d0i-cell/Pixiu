# Pixiu v2 CLI & Dashboard Design (Interactive Research Console)

Purpose: Define the future interactive console (CLI + Dashboard) architecture, user positioning, and prompt steering mechanisms.
Status: planned
Audience: implementer
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-21

> 本文档取代了旧版的 `terminal-dashboard.md`，后者已归档至 `docs/archive/futures/`。
> 本设计目前属于 `futures` 阶段，不阻塞当前核心自进化管线 (Phase 4B) 的运行实验。
> 更上位的多入口产品界面设计见 `36_product-interface-topology.md`；本文聚焦 terminal / shell / dashboard 这一条交互链。

---

## 1. 用户画像与产品定位

### 1.1 核心用户：量化研究员个人 (Research Director)
Pixiu 的 CLI 设计不服务于普通散户，也不面向运维人员。它是一套专门给**量化研究总监**打造的"研究驾驶舱"。
用户的核心诉求是：
1. 监控系统自主发现 Alpha 假设的过程。
2. 随时提供**战略指导与预设注入 (Prompt Steering)**。
3. 把控最终研究成果入池的质量标准 (Human Gate)。

### 1.2 "非执行操作员" 原则
系统内已有 14 个 Agent 进行全链路挖掘，用户**不应当**成为流水线上的“操作工”。因此，CLI 的交互哲学是：
- 用户不应记住极其复杂的底层参数。
- 支持通过自然语言表达“研究意图”，交由内嵌 Agent 代理翻译为系统调用。

### 1.3 产品语言分层

CLI 需要同时兼容三层语言，而不是只用一种话术覆盖所有界面：

- **System Truth**: `A-share alpha research OS`
- **Internal Metaphor**: `LLM-native quant research team`
- **External Metaphor**: `A 股 alpha 私人农场`

因此 CLI 的文案原则应固定为：

- 关键对象、命令名、错误信息保持技术真实，不伪装成消费级荐股语言。
- 顶部标题、空状态、成功提示可以适度使用“农场 / 守仓 / 收成”表达 ownership。
- 运行态、审批、报告对象继续保留 `run / snapshot / verdict / CIO report / control plane` 等术语。

### 1.4 当前兼容约束

本设计属于 future 方向，但必须兼容当前主干现实：

1. `pixiu` 仍是唯一稳定入口，不改名。
2. 已有 `run / status / factors / approve / redirect / stop / report` 仍为稳定命令，不允许被未来 shell 取代。
3. `status / report` 优先读取 control plane，不允许直接暴露 graph internals。
4. 交互增强只在 TTY 模式启用；非 TTY 输出仍应保持脚本友好。

---

## 2. 交互三层架构

在未来的产品形态中，推荐建设三层交互平面：

| 入口层 | 定位 | 技术栈 |
|---|---|---|
| **Layer 1: CLI Commands** | CI / 脚本 / 自动化的静态子命令入口 (`pixiu run`, `pixiu status`) | Typer + bash 环境 |
| **Layer 2: CLI Shell** | 强交互的量化日常监控与指挥中心，支持动态补全和自然语言 Agent 解析 | prompt_toolkit + Rich |
| **Layer 3: Web Dashboard** | Web 端重度数据可视化（因子表现分布、Pipeline 回放监控） | NiceGUI (Python native) |

### 2.1 兼容策略

三层不是替换关系，而是叠加关系：

- **Layer 1** 是当前真相，也是 CI / 自动化 / 文档示例的默认入口。
- **Layer 2** 是未来日常使用主入口，但其 slash commands 必须一一映射到 Layer 1 已存在的稳定能力。
- **Layer 3** 只负责可视化和回放，不承载唯一控制入口。

### 2.2 当前推荐的命令树

在不破坏现有 CLI 的前提下，未来命令树建议演进为：

```text
pixiu
  run
  status
  factors
  report
  approve
  redirect
  stop
  shell
  logs tail
  data status
  data sync
  config show
```

说明：

- `shell` 是新增强交互入口，但不替代现有根命令。
- `logs / data / config` 适合作为二级命令簇补齐产品面。
- `/steer` 只在 control plane 具备稳定 memo 读写后才进入正式命令面。

---

## 3. 视觉主题与界面气质

### 3.1 主题名

推荐主题名：

`玄金守仓`

它需要同时表达三件事：

- `玄`：研究系统的后台深度与非交易时段运行感
- `金`：貔貅、alpha 产出、promoted object
- `守仓`：用户不是流水线工人，而是高杠杆值守者

### 3.2 颜色系统

建议定义一组稳定语义 token，而不是在每个命令里随意上色：

| Token | 建议色相 | 语义 |
|---|---|---|
| `ink` | 墨黑 / slate | 系统背景、辅助边框、后台运行态 |
| `gold` | 古金 / amber | 品牌主色、promoted factor、关键标题 |
| `jade` | 玉绿 | 健康、通过、增长、已收成对象 |
| `cinnabar` | 朱砂 | 风险、停止、审批等待、错误 |
| `parchment` | 米白 / paper | Markdown 报告和长文本阅读背景 |

### 3.3 文案规范

前台标题允许适度主题化，但对象名保持技术真实：

- `Pixiu Runtime Status` → `守仓总览 / Runtime`
- `Factor Leaderboard` → `收成榜 / Factor Leaderboard`
- `Human Gate` → `值守门 / Human Gate`
- `CIO Report` → `今日简报 / CIO Report`
- `Run Progress` → `耕作进度 / Run Progress`

禁止把 CLI 做成“散户看盘软件”或“神兽皮肤 DevOps 工具”。

---

## 4. 双模指令与主控 Agent (CLI Orchestrator)

CLI Shell 必须打破“全自动盲盒”的限制，提供 Human-in-the-loop 能力。

**交互模式：**
- **精确调用**：输入 `/` 开头，如 `/redirect momentum`，直接触发确定性逻辑，支持自动补全。
- **意图代理 (Natural Language Agent)**：输入纯文本如 `“接下来少用点换手率高的纯动量，多找找量价背离”`。
  - NL Agent 解析意图。
  - 若为具体命令，则翻译为 `/command` 并在执行前请求用户 `y/n` 确认。
  - 若为研究指导思想，则通过 `/steer` 将其沉淀到控制平面，供下一轮 Stage 1/2 消费。

### 4.1 现实落地顺序

双模指令不是当前第一阶段实现重点，应按以下顺序推进：

1. 先把 Layer 1 命令的输出界面、错误口径、状态读取完全收口。
2. 再引入 `pixiu shell`，先支持 slash command，不急着上 NL agent。
3. 最后再把 NL steering 挂到稳定 control plane memo 上。

---

## 5. 指令集分层设计 (Command Taxonomy)

系统自带的可用指令（通过 `/` 触发）按用户不同维度的需求划分为五层：

### Level 0: 系统控制 (Core Control)
控制实验生命周期的高优操作。
- `/run [--mode evolve|single] [--island X] [--rounds N]`：启动系统后台循环。
- `/stop`：优雅中断，当前轮次跑完后停机。
- `/exit` / `Ctrl-D`：退出终端环境。

### Level 1: 人工指导注入 (Steering & Injection)
**让用户能干预系统的核心操纵杆。**
- `/redirect <island>`：强制转移系统的探索注意力。
- `/approve`：Stage 5 人类门派，放行通过的策略。
- `/stop`：优雅停机，当前轮次完成后停止。
- `/steer <text>`：向 Control Plane 写入 `Steering Memo`，仅在控制平面落地稳定 memo 后启用。

说明：

- `approve / redirect / stop` 是当前真实存在且必须优先兼容的动作集。
- `/reject` 暂不作为基线命令进入主产品面，除非 failure-constraint 写回语义先落地。

### Level 2: 状态观测 (Observability)
- `/status`：显示当前 Run 的详细面板、当前节点、报错日志摘要。
- `/factors [--top N] [--island X]`：查看当前已入池因子榜单。
- `/report`：打印最新生成的 Markdown CIO 报告。
- `/log [tail|grep]`：直接在 CLI 分割面板中查看指定的系统流水级日志。

### Level 3: 数据基建管理 (Data Infra)
运行时数据可用性自省（Dynamic Availability）。
- `/data status`：展示所有上游数据源（Tushare/Akshare）的连接连通性及预计算因子的本地覆盖率。
- `/data sync <dataset>`：手动触发某一张表的后台下载与 Qlib BIN 库刷新。

### Level 4: 开发者与调试 (Builder & Debugging)
面向制造系统的开发者。
- `/eval <formula>`：立即在当前最新市场截面上演算单个公式，抛出夏普和 IC（极速验证工具）。
- `/probe <tool>`：试拨云端 MCP Tool 的连通性。
- `/config show`：查看全系统变量和超时设定。

---

## 6. 输出模式与屏幕原型

### 6.1 非 TTY 模式

非 TTY 输出必须优先满足脚本和 CI：

- 不依赖动画和 Live 刷新
- 错误信息简洁、可 grep
- 长报告直接输出 Markdown 或 plain text
- 后续可补 `--json` 和 `--plain`，但默认先保持现有 human-readable 输出

### 6.2 TTY 模式

TTY 模式可以启用 Rich 主题化界面，但仍要遵守“信息优先于装饰”：

- 顶部用品牌条显示运行摘要
- 中部展示关键对象状态
- 底部提供下一步动作提示
- 日志噪音与交互输入必须隔离

### 6.3 核心屏幕原型

`status`

- 三栏固定结构：`Run / Snapshot / Latest Report`
- 如等待审批，在底部显示 `approve / redirect / stop` 快捷提示

`run`

- 顶部：守仓条，显示 `run_id / mode / stage / round`
- 中部：进度主体，显示计时、snapshot、counts、slowest stage
- 底部：Human Gate 或日志文件路径提示

`factors`

- 标题使用“收成榜”，但列名保持 `Sharpe / IC / ICIR / Formula / Island`
- 空状态明确区分“无结果”和“读数据失败”

`report`

- 先展示 report metadata，再展示 Markdown 正文
- 在 TTY 下推荐后续接入 pager，避免长文顶掉上下文

`shell`

- 输入区支持 slash command 自动补全
- toolbar 显示 `run_id / stage / round / awaiting approval`
- 事件通知通过顶部 banner 或 `print_above_prompt` 弹出，不污染当前输入行

---

## 7. 日志视觉隔离机制

为防后台并发任务在打印日志时破坏用户的命令行 Prompt 对话框：
系统引入轻量且无依赖的 **EventBus (Pub-Sub)**：
1. **Producer**: Orchestrator, Qlib Runtime, Agents `logger.info("...")` → 全局重定向写向文件日志 `logs/pixiu_run_*.log`。
2. **Producer**: 只把高度抽象的信息（如 `on_stage_change`, `on_factor_passed`）作为结构化事件 Emit 到 EventBus。
3. **Consumer**: Console 的 Rich Panel 挂载监听，动态刷新上方输出区；错误抛出到顶部通知条（`print_above_prompt` 安全渲染）。

---

## 8. CLI 设计守则

实现时应遵守以下规则：

1. 帮助信息先给最常见的 3-4 个例子，再讲参数。
2. 交互增强只在 TTY 打开；脚本模式始终可预期。
3. 产品层不直读 graph internals，只读 control plane 或知识平面公共接口。
4. 主题只改变视觉和语言，不改变对象边界和真实能力。
5. 新 shell 是增量入口，不得替换现有 `pixiu <command>` 体系。

---

## 9. 演进路线规划 (Roadmap)

此重构不阻塞当前已开发的系统能力。路线图倒排如下：

- **阶段一 (当前优先)**: 收口现有 Layer 1 CLI 的信息架构、主题 token、TTY/非 TTY 输出规则和帮助文案。
- **阶段二 (Shell 落地)**: 引入 `prompt_toolkit`，先做 `pixiu shell` 的 slash command、toolbar、自动补全和事件通知。
- **阶段三 (意图注入)**: 在 control plane 具备稳定 memo 读写后，再增加 `/steer` 和 NL CLI Agent。
- **阶段四 (产品补面)**: 增补 `logs / data / config` 二级命令簇，形成较完整的研究驾驶舱。
- **阶段五 (Dashboard)**: 使用 `NiceGUI` 提供只读图表和回放，不改变 CLI 作为主控制入口的地位。
