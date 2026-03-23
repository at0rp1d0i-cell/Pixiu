# LLM Runtime Settings Design

**Date:** 2026-03-23  
**Status:** Approved for implementation

## Goal

给 Pixiu 增加一层显式的 runtime LLM 设置，使：

- provider 凭据和端点由 env 管理
- runtime 选择由 settings 管理
- `researcher / market_analyst / alignment_checker / exploration_agent` 可以按 role 绑定 provider 和 model

而不是继续依赖隐式的 `RESEARCHER_*` 覆盖顺序。

## Problem

当前 runtime 读取顺序在 [openai_compat.py](/home/torpedo/Workspace/ML/Pixiu/src/llm/openai_compat.py) 中被写死：

- 优先 `RESEARCHER_MODEL / RESEARCHER_BASE_URL / RESEARCHER_API_KEY`
- 其次 `OPENAI_MODEL / OPENAI_API_BASE / OPENAI_API_KEY`

这个设计有三个直接问题：

1. 运行时到底在用哪个 provider，不可显式声明
2. 用户即使补了 `OPENAI_*`，也可能继续被 `RESEARCHER_*` 静默覆盖
3. provider 和 model 被绑死在同一套角色级 env 上，扩展性差

这已经开始阻碍后续工作：

- fast feedback 中只切 `researcher` 到 OpenAI
- 对比不同 provider 的 token / latency / quality
- 后续 experiment settings layer 对 runtime 行为进行显式控制

## Chosen Now

本轮实现一个最小的 runtime LLM settings layer：

- 新增 `config/llm_runtime.json`
- 新增 `src/llm/runtime_settings.py`
- env 只提供 provider credentials/endpoints
- settings 负责 `default provider + provider default models + role overrides`
- `build_researcher_llm(profile=...)` 按 profile/role 读取 provider/model 选择
- 若 settings 缺失或 role 未配置，回退到当前 legacy env 逻辑

### Config shape

第一版配置结构：

```json
{
  "default_provider": "deepseek",
  "provider_defaults": {
    "deepseek": {
      "model": "deepseek-chat"
    },
    "openai": {
      "model": "gpt-5.4"
    }
  },
  "roles": {
    "market_analyst": {
      "provider": "deepseek"
    },
    "researcher": {
      "provider": "deepseek"
    },
    "alignment_checker": {
      "provider": "deepseek"
    },
    "exploration_agent": {
      "provider": "deepseek"
    }
  }
}
```

第一版 env 约定：

- `DEEPSEEK_API_BASE`
- `DEEPSEEK_API_KEY`
- `OPENAI_API_BASE`
- `OPENAI_API_KEY`
- 可选：`PIXIU_LLM_DEFAULT_PROVIDER`

说明：

- env 不再承担“哪个 role 用哪个 provider”的职责
- env 只提供 provider 连接信息
- settings 决定 role 用哪个 provider、哪个 model

### Resolution rules

1. 若传入 `profile` 且 `config/llm_runtime.json` 存在：
   - 先按 role 找 override
   - 若无 override，使用 `default_provider`
   - model 优先级：
     - role override `model`
     - `provider_defaults[provider].model`
   - endpoint/credential 优先从 provider 对应 env 中读取
   - 最终拼出 `ChatOpenAI` 所需连接参数
2. 若 role 未映射或配置无效：
   - fallback 到当前 `RESEARCHER_* -> OPENAI_*` 逻辑
3. 显式函数参数 `temperature / max_tokens / overrides` 继续最高优先级
4. `PIXIU_LLM_DEFAULT_PROVIDER` 可覆盖 settings 中的全局默认 provider，但不覆盖 role 显式 override

## Why This Shape

这轮只按 role 切 provider/model，不按 stage、subspace、round 细分，原因是：

- 当前真正要解决的是“runtime 到底用了谁”
- role 粒度已经足够服务：
  - `researcher` 单独切 OpenAI 做 fast feedback
  - `market_analyst` 保持 DeepSeek
  - `alignment_checker` 后续再决定是否切
- 若先做更细粒度路由，只会把设置层过早做重
- 把 provider credentials 和 selection 拆开后，后续扩模型不会再依赖新增一套角色级 env

## Compatibility

本轮必须保持兼容：

- 旧 `.env` 只配 `RESEARCHER_*` 时，系统继续可运行
- 新 `.env` 可只配 `DEEPSEEK_* / OPENAI_*`
- 旧测试默认仍可通过
- 只有当配置文件存在且 role 显式映射时，新的 provider selection 才生效

## Explicitly Deferred

本轮不做：

- `Responses API` 迁移
- provider-specific advanced params（例如 reasoning effort）
- 按 stage / subspace / experiment profile 的细粒度模型路由
- token pricing / budget policy
- 多 provider fallback / failover

这些都属于后续更重的 runtime settings architecture。

## Verification Plan

本轮验证只做三类：

1. unit tests
   - runtime settings 加载
   - role -> provider/model 解析
   - provider env 解析
   - legacy fallback
2. config smoke
   - `get_researcher_llm_kwargs(profile='researcher')` 能解析出预期 provider
3. live smoke
   - 先不要求整条主链切 OpenAI
   - 只要求能显式把某个 role 切到 OpenAI，并做一次最小调用取证

## Exit Path

这层落地后，后续可以自然继续：

1. experiment settings layer 引用 role-level provider mapping
2. fast feedback 支持 `researcher=openai`
3. token ledger 按 provider / model 做更可靠对比
4. 若后续需要，再升级到 schema-level runtime settings
