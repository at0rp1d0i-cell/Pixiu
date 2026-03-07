# EvoQuant v2 杂项待办清单

> 创建：2026-03-07
> 来源：代码审计（src/ 全量扫描）
> 执行方：Gemini（与 v2 Spec 实施同步进行）

---

## 🔴 Critical（必须在任何新代码合并前修复）

### C1. 删除硬编码 API Key

**问题**：源码中包含真实 API Key，任何 git push 都会泄露。

| 文件 | 行 | 问题代码 |
|---|---|---|
| `src/sandbox/claude_code_adapter.py` | 26 | `os.environ.get("ANTHROPIC_API_KEY", "sk-sp-0dac...")` |
| `src/data_pipeline/news_sentiment_spider.py` | 25 | `os.environ.get("ANTHROPIC_API_KEY", "sk-746...")` |
| `src/agents/researcher.py` | 60 | `os.environ.get("RESEARCHER_API_KEY", os.environ.get(..., "sk-746..."))` |

**修复**：删除所有 fallback 字符串，改为缺失时 raise：
```python
api_key = os.environ.get("ANTHROPIC_API_KEY")
if not api_key:
    raise ValueError("ANTHROPIC_API_KEY 未设置，请检查 .env 文件")
```

### C2. 硬编码阈值 magic number 分散在各处

**问题**：`2.67`、`0.02`、`0.3`、`0.5` 散落在 orchestrator、pool、critic 等多个文件，与 `THRESHOLDS` 配置不一致（v2 已定义集中配置，旧代码未迁移）。

**修复**：统一从 `src/schemas/thresholds.py` 的 `THRESHOLDS` 对象读取，删除所有 literal 数值。

### C3. 静默异常吞噬

**文件**：`src/agents/critic.py:46`
```python
except Exception:
    pass  # 降级到正则 ← 没有日志，调试时完全不知道发生了什么
```
**修复**：
```python
except Exception as e:
    logger.warning("JSON 解析失败，降级到正则: %s", e)
```

---

## 🟠 High（影响可维护性和可移植性）

### H1. 15+ 处 print() 替换为 logging

**涉及文件**：

| 文件 | 数量 |
|---|---|
| `src/data_pipeline/data_downloader.py` | ~7 处 |
| `src/data_pipeline/format_to_qlib.py` | ~7 处 |
| `src/data_pipeline/news_sentiment_spider.py` | ~6 处 |

**修复模板**：
```python
import logging
logger = logging.getLogger(__name__)
# print("...") → logger.info("...")
# print(f"错误: {e}") → logger.error("错误: %s", e)
```

### H2. 硬编码 Docker 镜像名

**文件**：`src/sandbox/claude_code_adapter.py:87`（v2 中此文件将被删除，但新 `src/execution/docker_runner.py` 不应重蹈覆辙）

**v2 修复**（在 docker_runner.py 中）：
```python
IMAGE = os.environ.get("CODER_DOCKER_IMAGE", "evoquant-coder:latest")
```

### H3. 硬编码 IP 地址和代理

**文件**：`src/data_pipeline/news_sentiment_spider.py`

```python
# 问题
LLM_API_BASE = os.environ.get("ANTHROPIC_BASE_URL", "http://172.30.128.1:8045/v1")  # WSL IP
PROXIES = {"http": "http://127.0.0.1:17890", ...}  # 本地代理端口

# 修复
LLM_API_BASE = os.environ.get("ANTHROPIC_BASE_URL")
if not LLM_API_BASE: raise ValueError("ANTHROPIC_BASE_URL 未设置")

HTTP_PROXY = os.environ.get("HTTP_PROXY", "")
PROXIES = {"http": HTTP_PROXY, "https": HTTP_PROXY} if HTTP_PROXY else {}
```

---

## 🟡 Medium（影响健壮性）

### M1. API 调用无重试

**文件**：`src/data_pipeline/news_sentiment_spider.py:67,99`

HTTP 请求单次失败即崩溃，无重试逻辑。

**修复**：
```python
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=Retry(total=3, backoff_factor=1.0)))
```

### M2. Docker subprocess 超时硬编码

**文件**：`src/sandbox/claude_code_adapter.py:100`（和新 `docker_runner.py`）

```python
# 问题
subprocess.run(..., timeout=300)

# v2 修复（在 docker_runner.py 中已按 spec 处理）
timeout_seconds=int(os.environ.get("BACKTEST_TIMEOUT_SECONDS", "600"))
```

### M3. os.getenv 不验证必填项

**文件**：`src/agents/researcher.py:59-61`、多处

目前代码假设所有 env var 存在，缺失时会传 `None` 给 LLM 客户端，导致难以诊断的错误。

**修复**：统一使用 `src/core/config.py` 中的验证函数：
```python
def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value:
        raise EnvironmentError(f"必填环境变量 {key} 未设置，请检查 .env 文件")
    return value
```

### M4. IslandScheduler 参数无验证

**文件**：`src/factor_pool/scheduler.py`

```python
# 修复：在 __init__ 中添加断言
assert 0 < t_min < t_init, f"需满足 0 < T_MIN({t_min}) < T_INIT({t_init})"
assert 0 < anneal_factor < 1.0, f"ANNEAL_FACTOR({anneal_factor}) 必须在 (0,1) 之间"
assert reset_min_runs > 0, "RESET_MIN_RUNS 必须 > 0"
```

---

## 🔵 Low（代码整洁，不影响功能）

### L1. 路径存在性验证

**文件**：`src/agents/researcher.py:31-34`

```python
if not DICTIONARY_PATH.exists():
    raise FileNotFoundError(f"因子字典文件缺失: {DICTIONARY_PATH}")
```

### L2. 异常类型细化

**文件**：`src/agents/researcher.py:115-119`

```python
# 粗糙
except Exception as e:
    logger.warning("因子字典加载失败: %s", e)

# 细化
except FileNotFoundError:
    logger.warning("因子字典文件未找到: %s", DICTIONARY_PATH)
except OSError as e:
    logger.error("因子字典读取 IO 错误: %s", e)
```

### L3. 删除 v1 遗留文件

v2 实施完成后，以下文件/目录应删除：
- `src/sandbox/`（整个目录，被 `src/execution/` 替代）
- `src/agents/coder.py` 中的 Claude Code 相关代码
- `AgentState` 中的 DEPRECATED 字段（`factor_hypothesis`、`backtest_metrics`）

---

## 执行优先级

```
C1（泄露密钥）→ C2（magic number）→ C3（静默异常）
    ↓
H1（print→logging）→ H3（硬编码 IP）→ H2（Docker 镜像名）
    ↓
M1-M4（健壮性）
    ↓
L1-L3（整洁）
```

**建议**：C1-C3 在 v2 Stage 4 实施前修复（可合并）；H/M 类在各 Stage 实施时顺手处理；L 类在所有 Stage 完成后统一清理。
