# Pixiu v2 杂项待办清单

Status: active
Owner: coordinator
Last Reviewed: 2026-03-19

> 更新时间：2026-03-18
> 说明：本文件只保留当前代码仍然存在的工程债。随 Phase 3 重构一起消失的旧文件问题，已不再保留在 active 清单中。

---

## 🔴 Current

### D1. Researcher 环境变量校验仍然偏隐式

**文件**：`src/agents/researcher.py:141-145`

当前 `ChatOpenAI` 初始化直接读取环境变量：

```python
model=os.getenv("RESEARCHER_MODEL", "deepseek-chat")
base_url=os.getenv("RESEARCHER_BASE_URL", os.getenv("OPENAI_API_BASE"))
api_key=os.getenv("RESEARCHER_API_KEY", os.getenv("OPENAI_API_KEY"))
```

问题：

- 缺失时可能静默传入 `None`
- 配置错误定位不够直接
- 仍缺统一的 config/validation 入口

建议：

- 为 Researcher 增加集中配置校验
- 对关键环境变量缺失给出明确错误信息

### D2. IslandScheduler 调度参数仍是模块级硬编码常量

**文件**：`src/factor_pool/scheduler.py:18-28`

当前温度退火和重置阈值仍是模块级常量：

- `T_INIT`
- `T_MIN`
- `ANNEAL_EVERY`
- `ANNEAL_FACTOR`
- `RESET_MIN_RUNS`
- `RESET_SHARPE_THRESHOLD`
- `VIRGIN_ISLAND_SHARPE`

问题：

- 调参与运行时配置没有统一入口
- 参数约束没有显式验证
- 实验与生产口径难以切换

建议：

- 收敛到集中配置对象
- 为关键参数增加不变量校验

## 🟡 Follow-up

### D3. Researcher 内部仍有过宽的异常捕获

**文件**：`src/agents/researcher.py:312-315`, `src/agents/researcher.py:341-342`

当前对符号变异失败和 FailureConstraint 查询失败采用宽泛 `except Exception`。

问题：

- 容易吞掉真正的实现错误
- 诊断粒度不足

建议：

- 区分“预期降级”和“真实异常”
- 对可恢复错误保留 fallback，对不可恢复错误提高日志等级或直接暴露

## 约定

- 新的工程债只记录当前仍存在的代码问题
- 已删除文件的问题不继续留在 active 清单中
- 纯历史债务应移动到 `docs/archive/`
