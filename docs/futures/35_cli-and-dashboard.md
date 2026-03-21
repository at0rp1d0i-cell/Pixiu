# Pixiu v2 CLI & Dashboard Design (Interactive Research Console)

Purpose: Define the future interactive console (CLI + Dashboard) architecture, user positioning, and prompt steering mechanisms.
Status: planned
Audience: implementer
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-21

> 本文档取代了旧版的 `terminal-dashboard.md`，后者已归档至 `docs/archive/futures/`。
> 本设计目前属于 `futures` 阶段，不阻塞当前核心自进化管线 (Phase 4B) 的运行实验。

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

---

## 2. 交互三层架构

在未来的产品形态中，推荐建设三层交互平面：

| 入口层 | 定位 | 技术栈 |
|---|---|---|
| **Layer 1: CLI Commands** | CI / 脚本 / 自动化的静态子命令入口 (`pixiu run`, `pixiu status`) | Typer + bash 环境 |
| **Layer 2: CLI Shell** | 强交互的量化日常监控与指挥中心，支持动态补全和自然语言 Agent 解析 | prompt_toolkit + Rich |
| **Layer 3: Web Dashboard** | Web 端重度数据可视化（因子表现分布、Pipeline 回放监控） | NiceGUI (Python native) |

---

## 3. 双模指令与主控 Agent (CLI Orchestrator)

CLI Shell 必须打破“全自动盲盒”的限制，提供 Human-in-the-loop 能力。

**交互模式：**
- **精确调用**：输入 `/` 开头，如 `/redirect momentum`，直接触发确定性逻辑，支持自动补全。
- **意图代理 (Natural Language Agent)**：输入纯文本如 `“接下来少用点换手率高的纯动量，多找找量价背离”`。
  - NL Agent 解析意图。
  - 若为具体命令，则翻译为 `/command` 并在执行前请求用户 `y/n` 确认。
  - 若为研究指导思想，则通过 `/steer` 将其沉淀到控制平面，供下一轮 Stage 1/2 消费。

---

## 4. 指令集分层设计 (Command Taxonomy)

系统自带的可用指令（通过 `/` 触发）按用户不同维度的需求划分为五层：

### Level 0: 系统控制 (Core Control)
控制实验生命周期的高优操作。
- `/run [--mode evolve|single] [--island X] [--rounds N]`：启动系统后台循环。
- `/stop`：优雅中断，当前轮次跑完后停机。
- `/exit` / `Ctrl-D`：退出终端环境。

### Level 1: 人工指导注入 (Steering & Injection)
**让用户能干预系统的核心操纵杆。**
- `/steer <text>`：向 Control Plane 写入 `Steering Memo`，下一轮 Agent 启动时作为 System Prompt 读取。
- `/redirect <island>`：强制转移系统的探索注意力。
- `/approve`：Stage 5 人类门派，放行通过的策略。
- `/reject <reason>`：否决 CIO Report，原因自动提炼为长期失败约束 (Failure Constraint)。

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

## 5. 日志视觉隔离机制

为防后台并发任务在打印日志时破坏用户的命令行 Prompt 对话框：
系统引入轻量且无依赖的 **EventBus (Pub-Sub)**：
1. **Producer**: Orchestrator, Qlib Runtime, Agents `logger.info("...")` → 全局重定向写向文件日志 `logs/pixiu_run_*.log`。
2. **Producer**: 只把高度抽象的信息（如 `on_stage_change`, `on_factor_passed`）作为结构化事件 Emit 到 EventBus。
3. **Consumer**: Console 的 Rich Panel 挂载监听，动态刷新上方输出区；错误抛出到顶部通知条（`print_above_prompt` 安全渲染）。

---

## 6. 演进路线规划 (Roadmap)

此重构不阻塞当前已开发的系统能力。路线图倒排如下：

- **阶段一 (当前优先)**: 保持旧版单一 Typer 模型，完成 Phase 4B 完全自进化的核心实验验收。
- **阶段二 (CLI 升级)**: 引入 `prompt_toolkit`，落地 `EventBus`，实现 Level 0, Level 2 指令集（`status`, `factors`），确立输入/输出相分离的 TTY 环境。
- **阶段三 (意图注入)**: 增加 `/steer` 和 NL CLI Agent 解析，打通 Human -> Control Plane -> Agent System Prompt 的意图注入闭环。
- **阶段四 (Dashboard)**: 使用 `NiceGUI` (一套不需要写 JS 的 Python 解决方案) ，起后端服务，提供只读的可视化图表面板。
