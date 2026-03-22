# Pixiu Product Interface Topology Design

Purpose: Define Pixiu's future multi-surface product interface topology across CLI, shell, web dashboard, and notification surfaces, without changing the system's first-principles architecture.
Status: planned
Audience: both
Canonical: yes
Owner: core docs
Last Reviewed: 2026-03-23

> 本文档属于 `futures` 设计，不代表当前运行时已经具备这些产品界面。
> 当前真实入口仍以 `pixiu` CLI 和最小 API 为准；更重的前台形态必须建立在稳定 control plane 之上。

---

## 1. Why This Doc Exists

Pixiu 现在已经有一个可以工作的 CLI，但这并不等于它的最终产品前台已经确定。

当前存在三个并行事实：

1. **系统真相已经足够清晰**
   - Pixiu 是 `A-share alpha research OS`
   - 核心任务是持续生成、收缩、执行、淘汰并沉淀 alpha hypotheses
   - 当前最重要的架构方向是“扩大 hypothesis space，不扩大 execution power”

2. **产品表达已经开始收口**
   - 对外不再只说“多 Agent 量化系统”
   - 更适合用“属于用户自己的 A 股 alpha 私人农场”来承接 ownership

3. **产品前台仍然偏薄**
   - CLI 已经是当前最小产品入口
   - 但未来不可能长期只靠 CLI 承担所有用户体验
   - Web、通知、轻控制面迟早会进入主产品面

因此需要一篇单独文档，回答以下问题：

- Pixiu 未来到底应该有哪些用户入口
- CLI 和 Web 是什么关系，而不是谁取代谁
- 哪些动作适合 CLI，哪些动作更适合 Web
- 如何让未来前台保持和当前控制面、FactorPool、报告对象的一致性
- 如何让“私人农场 / 貔貅守仓”的产品气质落到真实可实现的界面语言上

本篇文档的角色是：

- 给未来 CLI Shell / Web Dashboard / 通知面一个共同上位设计
- 为后续页面信息架构、控制动作、API 数据模型提供统一语义
- 避免每做一个新前台就重新发明一套产品边界

---

## 2. Non-Negotiable Constraints

任何产品前台设计都必须遵守以下第一性约束。

### 2.1 System Truth Does Not Change

Pixiu 的系统本体仍然是：

`A-share alpha research OS`

它不是：

- 投顾壳
- 散户荐股终端
- 高频交易执行平台
- 靠炫酷界面包装的分析面板

因此前台的职责不是“伪装系统是什么”，而是“让用户更自然地拥有并掌控这个系统”。

### 2.2 Product Language Is Layered

Pixiu 的语言应固定分三层：

1. **System Truth**
   - `research OS`
2. **Internal Operating Metaphor**
   - `LLM-native quant research team`
3. **External Product Metaphor**
   - `alpha 私人农场`

要求：

- 前台可以用“农场 / 收成 / 守仓 / 继续培养”等语言承接 ownership
- 但对象边界仍应保留 `run / factor / report / verdict / approval / control plane` 等真实术语
- 不允许因为追求用户友好，就把研究对象改写成“今日必买股票”之类失真表达

### 2.3 Product Surfaces Must Share the Same Control Plane

无论是 CLI、Shell、Web 还是通知层，所有前台都必须建立在同一套稳定数据面上。

前台可以读：

- `RunRecord`
- `RunSnapshot`
- `ArtifactRecord`
- `HumanDecisionRecord`
- FactorPool 公共查询结果
- 报告索引与报告内容

前台不应该直接读：

- graph internals
- 胖版 AgentState
- 节点私有中间状态
- 仅供运行时存在的临时拼装对象

### 2.4 CLI Remains First-Class

未来即使有 Web，CLI 也不是“临时过渡层”。

CLI 的长期价值包括：

- 脚本化与自动化
- 本地开发与调试
- 最短路径的审批与运维动作
- 系统故障时的最低依赖入口
- 高阶用户的高密度控制入口

所以未来架构应是“多入口共享控制面”，而不是“Web 上线后抛弃 CLI”。

### 2.5 Current Roadmap Priority Still Applies

这份产品前台文档不改变当前主线优先级：

1. Stage 2 工具化和 hypothesis space 扩张仍然更重要
2. richer contracts 继续收口
3. control plane 从 MVP 走向稳定读模型
4. 之后再逐步扩前台产品面

也就是说：

- 本文是前台方向的统一 spec
- 不是要求立即暂停主线，全面转向前端实现

---

## 3. Product Thesis for the Frontstage

Pixiu 的未来产品前台不应被定义为“研究系统的可视化皮肤”。

更准确的定义应是：

`一套让用户拥有、巡视、值守并逐步塑造自己 alpha 私人农场的多入口控制面。`

这一定义意味着三件事：

### 3.1 用户每天不是来“操作流水线”，而是来“巡视产出”

他们来前台主要是为了：

- 看今天长出了什么
- 看哪些对象通过了更严的筛选
- 看系统正在研究哪里
- 决定是否继续培养某些方向
- 审批是否将成果正式收入池中

### 3.2 用户要的是 Ownership，不是菜单数量

产品体验不该追求“功能栏尽量多”，而该追求：

- 我感觉这套系统属于我
- 我每天来都能看到它在持续耕作
- 我的偏好会逐渐改变它的行为
- 我做的少数动作真的有高杠杆影响

### 3.3 产品前台要支持快控制和慢控制

Pixiu 的控制可以分两层：

**Fast Control**

- approve
- redirect
- stop
- 继续培养
- 加入观察
- 忽略

特点：

- 频率高
- 反馈快
- 常发生在日常巡视过程中

**Slow Control**

- 研究偏好
- 风格偏好
- 风险偏好
- 长期 steering memo
- 关注 island / regime 的长期倾向

特点：

- 频率低
- 影响长期行为
- 不应被塞进每次日常操作的主路径中

---

## 4. Surface Topology

Pixiu 未来的产品界面建议拆为四个互补入口，而不是一个“大而全”的单前台。

| Surface | 定位 | 主要用户 | 核心场景 | 是否当前已存在 |
|---|---|---|---|---|
| CLI Commands | 稳定、脚本友好的控制入口 | 开发者、高阶用户 | run/status/report/approve/redirect/stop | yes |
| CLI Shell | 强交互的值守控制台 | 高阶用户、重度研究用户 | 实时巡视、快捷审批、slash command | planned |
| Web Dashboard | 默认日常前台 | 大多数产品用户 | 每日浏览、阅读、筛看、轻控制 | planned |
| Notification Surface | 轻提醒与快速确认 | 所有活跃用户 | 待审批、新报告、失败告警 | planned |

### 4.1 Why Not Only CLI

只做 CLI 的问题是：

- 新用户门槛偏高
- 不适合长时间浏览与对比
- 不适合结构化展示丰富对象关系
- 不利于形成“我的农场”的 ownership 感
- 不利于未来商业化和非工程用户 onboarding

### 4.2 Why Not Only Web

只做 Web 的问题是：

- 会弱化可脚本化控制
- 不利于开发与调试
- 紧急审批和故障场景不如 CLI 可靠
- 容易把真正控制面做成“样子货”

### 4.3 Recommended Topology

长期建议固定为：

```text
CLI Commands     -> 稳定控制面
CLI Shell        -> 强交互值守面
Web Dashboard    -> 默认浏览与轻控制前台
Notifications    -> 提醒与极简确认面
```

它们共用同一控制面与公共对象层：

```text
UI Surfaces
  -> API / control plane / public query layer
  -> orchestrator + factor pool + reports + artifacts
```

---

## 5. Surface Responsibilities

这一节回答“哪个入口该承担什么”，避免未来交互层重复和边界漂移。

### 5.1 CLI Commands

CLI 命令的长期角色：

- 最稳定的真实控制入口
- 文档、CI、脚本的默认形式
- 高可预期、低装饰、强可组合
- 系统不可用时最后的兜底入口

它适合承载：

- `pixiu run`
- `pixiu status`
- `pixiu factors`
- `pixiu report`
- `pixiu approve`
- `pixiu redirect`
- `pixiu stop`
- 未来的 `pixiu logs tail`
- 未来的 `pixiu data status`
- 未来的 `pixiu config show`

它不适合承载：

- 复杂长时浏览
- 大量对象的多维筛选与对比
- 高信息密度但低命令密度的日常产品浏览

### 5.2 CLI Shell

CLI Shell 是一个“值守型终端”，不是把 Web 页面塞回终端。

它适合承载：

- slash command
- auto completion
- 顶部事件通知
- 当前 run 的持续追踪
- 快速切换 `status / factors / report / approval`
- 面向重度用户的即时 steering

它不适合承载：

- 大量表格化历史回放
- 长期归档浏览
- 新用户 onboarding

### 5.3 Web Dashboard

Web 应作为长期默认前台。

它适合承载：

- 首页总览
- 今日收成浏览
- 因子与报告详情页
- 历史 run 回放
- 轻审批动作
- 偏好设置与农场风格塑造
- 更长周期的观察与复盘

它不应一开始就承载：

- 所有开发者调试入口
- 全部数据运维入口
- 运行时底层日志全文浏览
- 图形化覆盖所有 CLI 命令

### 5.4 Notification Surface

通知层只做两件事：

- 把重要状态从“需要打开前台才知道”改成“被动触达”
- 把最关键的极少数动作做成一跳处理

它适合通知：

- 当前 run 完成
- 新 CIO report 生成
- 等待人工审批
- 本轮失败或停机
- 数据源异常

它不适合：

- 承载复杂阅读
- 做完整因子浏览
- 承载需要大量上下文的决策

---

## 6. User Types and Daily Loops

界面设计必须服务真实用户节奏，而不是只围绕工程结构组织。

### 6.1 User A: 技术型探索者

特征：

- 对系统与研究流程本身有兴趣
- 接受 CLI 或半技术化界面
- 更关心系统今天跑出了什么，以及过程是否可信

他们的日常 loop：

1. 看首页或 `status`
2. 看今天的新对象和 top factors
3. 打开最新 report
4. 做少量 approval / redirect
5. 偶尔进 CLI deeper debug

### 6.2 User B: 半专业个人投资者

特征：

- 有现实决策需求
- 不想学习复杂命令
- 希望系统持续耕作，但自己保有掌控感

他们的日常 loop：

1. 打开 Web 首页
2. 看“今天长出了什么”
3. 看待审批成果与简洁解释
4. 做“继续培养 / 加入观察 / 忽略 / 批准”这类快控制
5. 偶尔调整长期偏好

### 6.3 User C: 专业研究员或 builder

不是当前主产品优先对象，但界面仍应兼容其存在。

他们更需要：

- CLI 命令稳定
- API 稳定
- debug / config / logs / data status
- 历史 run 的更强筛选与回放

因此产品界面不应只围绕 B 用户，把所有技术真相都藏掉。

---

## 7. Information Architecture

Pixiu 的前台信息架构不应从“页面类型”出发，而应从“用户需要稳定看到哪些对象”出发。

### 7.1 Canonical Frontstage Objects

前台最重要的对象应是：

1. **Farm**
   - 用户的整个研究系统前台抽象
2. **Run**
   - 某次系统运行
3. **Snapshot**
   - 某次运行在当前时刻的稳定摘要
4. **Factor**
   - 已通过筛选或已入池的研究对象
5. **Candidate / Note**
   - 尚在过程中的研究对象
6. **Report**
   - CIO report / backtest report 等最终可阅读对象
7. **Decision**
   - 人类审批动作及其结果
8. **Preference**
   - 用户的长期控制配置

### 7.2 Frontstage Navigation Model

建议 Web 顶层导航保持稳定，不追求一开始就很多页。

推荐一级导航：

- `总览`
- `收成`
- `报告`
- `运行`
- `值守`
- `偏好`

次级入口可按实现阶段逐步补齐：

- `数据健康`
- `通知中心`
- `开发者`

### 7.3 Page Naming Principle

对外页面名可以适度产品化，但内部对象名保持技术一致。

建议：

- 首页：`农场总览`
- 因子页：`今日收成`
- 报告页：`研究简报`
- 运行页：`耕作记录`
- 审批页：`值守门`
- 偏好页：`农场偏好`

页面内部的卡片或详情字段继续保留：

- `run_id`
- `stage`
- `round`
- `report`
- `verdict`
- `factor_id`

---

## 8. Web Dashboard Detailed Design

本节定义 Web 作为默认前台时，应优先呈现哪些页面和信息结构。

### 8.1 Home: 农场总览

首页应回答用户每天最先关心的五个问题：

1. 系统现在是不是在跑
2. 今天有什么新产出
3. 有没有需要我处理的审批
4. 最新报告是什么
5. 当前研究重心在哪里

#### 8.1.1 Home Layout

建议首页布局分为四区：

**A. 顶部总览条**

- 当前 farm 名称或环境名
- 最新 run 状态
- 当前 stage / round
- 今日新增产出数
- 待审批数

**B. 今日收成**

- 新 promoted factors
- 最新高分 candidate
- 当前关注的 island / regime

**C. 最新简报**

- 最新 CIO report 摘要
- 最新 backtest report 摘要
- 一键进入全文

**D. 值守提醒**

- 当前是否 awaiting approval
- 是否有失败轮次
- 是否有数据源异常

#### 8.1.2 Home Cards

首页卡片建议固定为：

- `系统状态卡`
- `今日收成卡`
- `待审批卡`
- `最新简报卡`
- `研究重心卡`
- `运行健康卡`

### 8.2 Harvest: 今日收成

这是 Web 中最重要的浏览页之一。

它的核心不是“股票列表”，而是“研究对象收成页”。

#### 8.2.1 Harvest Goals

用户在这里要能快速回答：

- 最近有哪些因子通过了
- 它们来自哪个 island / subspace
- 大致表现如何
- 是新发现还是旧方向延续
- 哪些值得继续培养或加入观察

#### 8.2.2 Harvest Structure

建议结构：

- 顶部筛选条
  - 时间
  - island
  - regime
  - promoted / candidate
  - score / sharpe / IC 排序
- 中部结果网格或表格
- 右侧详情抽屉或详情页

#### 8.2.3 Factor Card Fields

列表卡片应优先展示：

- `factor_id`
- `formula` 简写
- `island`
- `subspace_origin`
- `sharpe`
- `ic_mean / icir`
- `latest verdict`
- `created_at`

#### 8.2.4 Actions

在 Harvest 页适合提供的动作：

- `继续培养`
- `加入观察`
- `忽略`
- `查看报告`
- `查看来源 run`

不适合在这一页直接提供：

- 大量底层配置编辑
- 数据同步
- 开发者调试

### 8.3 Reports: 研究简报

报告页要解决“结果可读性”问题，而不是只把 Markdown 文件搬上来。

#### 8.3.1 Report Types

第一阶段只需覆盖：

- `CIO report`
- `backtest report`

未来可扩：

- `run summary`
- `regime memo`
- `failure digest`

#### 8.3.2 Report List

报告列表建议包含：

- 标题
- 类型
- run_id
- 创建时间
- 关联 factor 数
- 状态标签

#### 8.3.3 Report Detail

报告详情页建议分三段：

1. 元信息头
   - report_id
   - run_id
   - created_at
   - artifact path
2. 摘要区
   - key findings
   - decision summary
   - risk summary
3. 正文区
   - markdown renderer

### 8.4 Runs: 耕作记录

用户需要看到系统不是“偶尔跑一下”，而是在持续运行和积累。

#### 8.4.1 Run List

Run 列表页应展示：

- run_id
- mode
- status
- current stage
- current round
- started_at
- finished_at
- latest error
- artifacts count

#### 8.4.2 Run Detail

Run 详情页应包含：

- 基本信息
- snapshot counters
- 阶段时间分布
- 产生的报告列表
- 人类决策记录
- 关联的新 factor / candidate

#### 8.4.3 Replay

长期来看，应支持“轻回放”而不是视频化回放：

- 每轮 stage 切换时间点
- 每轮关键事件
- 每轮产出摘要

### 8.5 Gate Center: 值守门

这是 Web 中最重要的控制页。

#### 8.5.1 Purpose

它解决两个问题：

- 我现在有哪些待我决策的事情
- 我做出的决策会产生什么后果

#### 8.5.2 Queue Items

第一阶段只需要承接：

- 当前 awaiting approval 的 run
- 最新 CIO report
- 最简必要上下文

#### 8.5.3 Visible Actions

第一阶段动作保持和当前 CLI 一致：

- `批准`
- `转向某个 island`
- `停止`

后续才考虑加入：

- `继续培养`
- `加入观察`
- `忽略`

#### 8.5.4 Decision UX

每个决策卡应包含：

- 触发对象
- 决策原因摘要
- 相关报告链接
- 预计影响说明
- 决策按钮

### 8.6 Preferences: 农场偏好

偏好页不该一开始做成一个巨大的设置中心。

它应专注于 Slow Control：

- 研究偏好
- 风格偏好
- 风险偏好
- 关注 island / regime
- 长期 steering memo

#### 8.6.1 Preference Groups

建议分为：

- `研究方向`
- `风格倾向`
- `风险边界`
- `通知偏好`
- `界面偏好`

### 8.7 Secondary Surfaces

以下页面适合作为二阶段或开发者模式：

- `数据健康`
- `日志浏览`
- `工具探针`
- `系统配置`

默认不放在大众用户的一层导航中。

---

## 9. CLI and Shell Detailed Design

Web 会成为默认前台，但 CLI 和 Shell 仍然必须有清晰的长期形态。

### 9.1 Layer 1 CLI Commands

长期保持的基础命令：

```text
pixiu run
pixiu status
pixiu factors
pixiu report
pixiu approve
pixiu redirect
pixiu stop
```

建议扩展的命令簇：

```text
pixiu shell
pixiu logs tail
pixiu data status
pixiu data sync
pixiu config show
```

### 9.2 Output Modes

CLI 输出必须区分两种模式：

**Non-TTY**

- 无动画
- 可 grep
- 简洁错误
- 适合 CI / script

**TTY**

- 可启用 Rich
- 可启用品牌主题
- 可启用 live progress
- 可启用下一步动作提示

### 9.3 CLI Shell

Shell 的目标是“值守”，不是“再造一个 REPL 框架”。

#### 9.3.1 Shell Structure

建议屏幕分三层：

- 顶部状态条
- 中部上下文区
- 底部输入区

#### 9.3.2 Default Modes

进入 shell 后，默认焦点页可在以下几种之间切换：

- `status`
- `factors`
- `report`
- `gate`

#### 9.3.3 Slash Commands

建议优先支持：

- `/status`
- `/factors`
- `/report`
- `/approve`
- `/redirect`
- `/stop`
- `/run`
- `/help`

未来可增加：

- `/steer`
- `/logs`
- `/data status`
- `/config show`

#### 9.3.4 Natural Language Mode

自然语言输入只应在后期接入。

前提条件：

- control plane 已有稳定 memo 存储
- slash command 已成熟
- 用户确认流已经清晰

否则 NL shell 很容易把“看起来聪明”做成“实际不可控”。

---

## 10. Notification and Lightweight Surfaces

通知层不一定一开始就是独立 App。

可以按成本逐步演进：

1. 站内通知
2. 邮件或 webhook
3. 手机推送或 IM bot

### 10.1 Notification Classes

建议分四类：

- `approval_required`
- `new_report`
- `run_finished`
- `run_failed`

### 10.2 Notification Payload Principle

通知内容必须足够短，且可一跳进入更完整界面。

例如：

- 标题：`新的审批等待处理`
- 摘要：`Run abc123 已生成 CIO report，等待你的决定`
- 动作：
  - `打开值守门`
  - `在 CLI 中处理`

### 10.3 Mobile Strategy

长期可以有移动端轻前台，但不建议尽早做成完整 App。

更合理的顺序是：

- 先做通知和极简确认
- 再看是否需要更完整的移动浏览

---

## 11. Shared Action Model

多入口产品最容易出问题的点，是不同入口对同一个动作有不同语义。

因此必须先定义动作模型。

### 11.1 Core Action Set

当前跨入口共享的核心动作：

- `run`
- `approve`
- `redirect`
- `stop`
- `view_status`
- `view_factors`
- `view_report`

未来扩展动作：

- `continue_cultivate`
- `add_to_watchlist`
- `ignore_candidate`
- `set_preference`
- `write_steering_memo`

### 11.2 Action Mapping by Surface

| Action | CLI | Shell | Web | Notification |
|---|---|---|---|---|
| `run` | yes | yes | maybe later | no |
| `approve` | yes | yes | yes | maybe shortcut |
| `redirect` | yes | yes | yes | no |
| `stop` | yes | yes | yes | maybe shortcut |
| `view_status` | yes | yes | yes | linked only |
| `view_factors` | yes | yes | yes | linked only |
| `view_report` | yes | yes | yes | linked only |
| `continue_cultivate` | no | maybe later | yes | no |
| `set_preference` | no | limited | yes | no |

### 11.3 Action Design Rules

每个动作都应满足：

1. 有明确目标对象
2. 有明确的结果状态
3. 可被审计
4. 可在不同前台中以同一语义复用

---

## 12. Data and API Requirements

未来多入口前台能否健康演进，取决于是否存在足够稳定的公共读写接口。

### 12.1 Minimum Read Models

前台至少需要以下稳定读模型：

- 当前最新 run
- run history
- run snapshot
- artifact list
- report list
- report detail
- pending approval queue
- factor leaderboard
- factor detail
- human decision history

### 12.2 Minimum Write Models

第一阶段写动作只要求：

- append human decision
- start run
- maybe update preference

### 12.3 Event Needs

如果要支持 Web 实时状态和 Shell 事件通知，需要结构化事件面。

推荐至少支持这些事件：

- `run_started`
- `stage_changed`
- `snapshot_updated`
- `report_generated`
- `awaiting_approval`
- `human_decision_recorded`
- `run_finished`
- `run_failed`

### 12.4 Frontend Must Not Reconstruct Runtime Truth

无论哪个前台，都不应自行推断：

- 当前是否在等待审批
- 当前 run 是否算成功
- 某个报告是否对应最新产出

这些都应由控制面或公共对象层直接提供。

---

## 13. Visual and Interaction System

本节定义 Pixiu 多入口产品界面的统一视觉气质，而不是具体像素稿。

### 13.1 Design Theme

整体推荐主题：

`貔貅守仓，农场收成，后台耕作`

这不是要把界面做成国风插画，而是要把它做成：

- 有 ownership
- 有长期积累感
- 有夜间后台持续运转的感觉
- 不廉价、不喧闹、不像散户盯盘软件

### 13.2 Visual Tone

建议的基调：

- 基础背景偏深或低饱和中性色
- 金色只用在真正重要的对象和标题
- 绿色表示健康、通过、收成
- 朱砂色表示风险和需要用户值守
- 长文本阅读区偏纸白，提升报告可读性

### 13.3 Copywriting Rules

文案要同时满足品牌感和技术真实：

- 页面标题可以写 `今日收成`
- 但详情字段仍写 `Sharpe / IC / verdict / run_id`

好的例子：

- `今日收成`
- `值守门`
- `耕作记录`
- `最新简报`

不好的例子：

- `今日暴涨机会`
- `必买信号`
- `神兽策略宝库`

### 13.4 Motion Principle

动效只应帮助理解系统状态，不应制造表演感。

适合的动效：

- 卡片加载渐入
- 运行中状态脉冲
- 审批提醒高亮
- 列表更新平滑插入

不适合的动效：

- 高频闪烁
- 复杂粒子背景
- 过度交易终端风格动画

---

## 14. Rollout Strategy

多入口前台不能一口气做完，应按控制面成熟度倒排。

### Phase 1: Strengthen Current CLI

目标：

- 继续收口现有 `pixiu` CLI
- 统一帮助文案、输出规则、TTY 主题
- 让 CLI 成为真正稳定的产品控制入口

交付：

- 更清晰的 `status / factors / report / run` 界面
- 一致的错误口径
- 更明确的 approval 提示

### Phase 2: Build Read-First Web Dashboard

目标：

- 先做 Web 浏览面，而不是一开始就做重控制面

交付：

- 首页总览
- 收成页
- 报告页
- 运行页

### Phase 3: Add Gate Center

目标：

- 把高价值快控制动作带到 Web

交付：

- 待审批队列
- `approve / redirect / stop`
- 相关上下文与简明解释

### Phase 4: Add Preferences and Slow Control

目标：

- 把长期偏好和 steering 真正做成产品能力

交付：

- 偏好页
- 长期 steering memo
- island / style / risk 倾向设定

### Phase 5: Add Shell and Notifications Maturity

目标：

- 让 power user 和普通用户都有合适入口

交付：

- `pixiu shell`
- 站内通知
- webhook / push

---

## 15. Success Metrics

一个好的多入口产品界面，不是“看起来完整”，而是要在以下维度真的变好。

### 15.1 Product Metrics

- 日活用户中打开首页或状态页的频率
- 新报告被阅读的比例
- 待审批对象的处理时延
- 用户做出快控制动作的频率
- 用户设置长期偏好的留存

### 15.2 UX Metrics

- 新用户从打开系统到看懂当前状态所需时间
- 从接到通知到完成审批所需时间
- 从首页进入报告详情的跳转成功率
- 用户能否清楚分辨“当前产出”“历史产出”“待审批产出”

### 15.3 Architecture Metrics

- 前台是否全部建立在稳定控制面之上
- 是否仍存在直接读取 graph internals 的页面
- 不同前台是否对同一动作保持统一语义

---

## 16. Anti-Patterns

未来做前台时，应明确避免以下方向。

### 16.1 Fake Trading Terminal

不要把 Pixiu 做成“专业感很强的行情终端”。

原因：

- 偏离研究系统本体
- 容易误导为盘中交易工具
- 与“后台持续耕作”的主体验不一致

### 16.2 Dashboard First, Data Plane Later

不要在控制面尚未稳定时，先大做 Web UI。

原因：

- 前台会被迫自行拼运行态真相
- 不同页面会出现语义不一致
- 后续重构代价极高

### 16.3 Replace CLI with Web

不要把 Web 当作“更高级，因此可以抛弃 CLI”。

原因：

- CLI 是真实控制入口
- 调试、开发、应急操作都离不开 CLI

### 16.4 Over-Gamification

不要为了“农场感”而把系统做成游戏化管理面板。

原因：

- 会稀释研究系统的可信度
- 会破坏专业用户对对象边界的理解

### 16.5 Too Many Controls Too Early

不要一开始把所有调优旋钮都暴露给用户。

原因：

- 违背“非执行操作员”原则
- 会让产品失去日常使用的轻感

---

## 17. Open Questions

以下问题目前应保留为开放项，而不是现在就拍板：

1. Web 前台是否先做 server-rendered Python UI，还是直接进入更完整前后端分离形态
2. 偏好页第一阶段是否允许用户写自由文本 steering，还是只提供结构化选项
3. `继续培养 / 加入观察 / 忽略` 应直接写入哪一层对象和控制面
4. 通知层第一阶段到底是站内通知、邮件还是 IM bot 更优
5. 是否需要在 Web 中暴露部分开发者模式页面，还是完全藏在 CLI 内

---

## 18. One-Sentence Summary

Pixiu 的未来产品前台不应是“把 CLI 变漂亮”，而应是：

`在同一控制面之上，建立 CLI、Shell、Web 和通知四个互补入口，让用户真正拥有、巡视、值守并逐步塑造自己的 alpha 私人农场。`
