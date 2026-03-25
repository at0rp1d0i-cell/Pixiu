## NARRATIVE_MINING 专用 grounding 约束（必须遵守）
- 本子空间必须输出 `grounding_claim` 对象
- `grounding_claim` 字段：
  - `mechanism_source`: 必须选择一个已给出的叙事类别名
  - `proxy_fields`: 公式实际使用的运行时字段列表
  - `proxy_rationale`: 为什么这些代理字段能承接该叙事机制
  - `formula_claim`: 用一句话说明公式如何实现该叙事传导
- `proxy_fields` 必须全部来自当前运行时可用字段
- `proposed_formula` 必须实际使用 `proxy_fields` 中至少一个字段
- 禁止只写定性叙事，不给出可检验代理
