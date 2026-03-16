"""
Subspace Context Builders — 为每个探索子空间生成结构化 LLM 上下文

替代原有的 _SUBSPACE_PROMPTS 纯字符串 hint，提供丰富的原语词汇表、
变异算子说明、机制模板、叙事类别等结构化信息。
"""
from typing import Optional

from src.schemas.hypothesis import ExplorationSubspace, MutationOperator
from src.schemas.exploration import (
    SubspaceRegistry,
    PrimitiveCategory,
)
from src.factor_pool.pool import FactorPool


def build_factor_algebra_context(registry: SubspaceRegistry, island: str) -> str:
    """因子代数搜索上下文：原语词汇表（按类别分组）+ 可用算子"""
    lines = ["## 探索子空间：因子代数搜索（Factor Algebra Search）", ""]
    lines.append("在受约束的原语空间中组合搜索，构造新因子表达式。")
    lines.append("")

    # 按类别分组
    by_cat: dict[PrimitiveCategory, list] = {}
    for p in registry.primitives:
        by_cat.setdefault(p.category, []).append(p)

    lines.append("### 可用原语")
    for cat in PrimitiveCategory:
        prims = by_cat.get(cat, [])
        if not prims:
            continue
        lines.append(f"\n**{cat.value}**:")
        for p in prims:
            lines.append(f"  - `{p.qlib_syntax}` — {p.description}")

    # 算子说明
    config = registry.get_subspace_config(ExplorationSubspace.FACTOR_ALGEBRA)
    if config and config.allowed_primitives:
        lines.append(f"\n### 允许的基础字段\n{', '.join(config.allowed_primitives)}")

    lines.append("\n### 组合规则")
    lines.append("- 时间变换可嵌套（如 Mean(Ref($close, -1), 5)）")
    lines.append("- 截面算子用于横截面排名/标准化")
    lines.append(f"- 当前 Island: {island}，请围绕此方向构造因子")

    return "\n".join(lines)


def build_symbolic_mutation_context(
    registry: SubspaceRegistry,
    factor_pool: Optional[FactorPool],
    island: str,
) -> str:
    """符号变异上下文：现有因子 + 变异算子说明"""
    lines = ["## 探索子空间：符号变异（Symbolic Mutation）", ""]
    lines.append("对已有因子做结构化变异，生成新的候选因子。")
    lines.append("")

    # 现有因子（从 factor_pool 拉取）
    lines.append("### 可变异的现有因子")
    if factor_pool:
        try:
            best = factor_pool.get_island_best_factors(island, top_k=5)
            if best:
                for rec in best:
                    formula = getattr(rec, "factor_expression", getattr(rec, "formula", "N/A"))
                    lines.append(f"  - `{formula}`")
            else:
                lines.append("  （当前 Island 暂无已入池因子，请基于通用公式进行变异）")
        except Exception:
            lines.append("  （因子池不可用，请基于通用公式进行变异）")
    else:
        lines.append("  （因子池未注入，请基于通用公式进行变异）")

    # 变异算子
    lines.append("\n### 可用变异算子")
    operator_desc = {
        MutationOperator.ADD_OPERATOR: "添加算子 — 在现有公式上叠加新的运算（如加 Rank、加 Std）",
        MutationOperator.REMOVE_OPERATOR: "移除算子 — 简化公式，去掉冗余运算",
        MutationOperator.SWAP_HORIZON: "交换时间窗口 — 将 N 日改为 M 日（如 5→20、20→60）",
        MutationOperator.CHANGE_NORMALIZATION: "改变归一化 — 切换标准化方式（zscore/rank/minmax）",
        MutationOperator.ALTER_INTERACTION: "改变交互项 — 修改因子间的组合方式（乘→除、加→减）",
    }
    for op in MutationOperator:
        lines.append(f"  - **{op.value}**: {operator_desc.get(op, op.value)}")

    lines.append(f"\n当前 Island: {island}")
    lines.append("请选择一个现有因子，应用一个变异算子，生成新的候选。")

    return "\n".join(lines)


def build_cross_market_context(registry: SubspaceRegistry) -> str:
    """跨市场模式迁移上下文：机制模板列表"""
    lines = ["## 探索子空间：跨市场模式迁移（Cross-Market Pattern Mining）", ""]
    lines.append("从其他市场的已知 alpha 机制中提取逻辑骨架，适配 A 股。")
    lines.append("不抄因子，抄逻辑骨架。传导的是 market mechanism analogies。")
    lines.append("")

    lines.append("### 可用机制模板")
    for tmpl in registry.mechanism_templates:
        lines.append(f"\n**{tmpl.name}** (来源: {tmpl.source_market})")
        lines.append(f"  传导路径: {tmpl.transmission_path}")
        lines.append(f"  逻辑骨架: {tmpl.skeleton}")

    lines.append("\n### 使用方法")
    lines.append("1. 选择一个机制模板")
    lines.append("2. 将模板中的占位符替换为 A 股具体参数")
    lines.append("3. 构造可测试的 Qlib 因子表达式")

    return "\n".join(lines)


def build_narrative_mining_context(registry: SubspaceRegistry) -> str:
    """经济叙事挖掘上下文：叙事类别 + 抽取目标"""
    lines = ["## 探索子空间：经济叙事挖掘（Narrative Mining）", ""]
    lines.append("A 股 alpha 大量藏在叙事层而非 price signal。")
    lines.append("从政策口径、产业链叙事、市场预期错位中抽取机制假设。")
    lines.append("")

    lines.append("### 叙事类别与抽取目标")
    for cat in registry.narrative_categories:
        lines.append(f"\n**{cat.category}**")
        lines.append(f"  抽取目标: {', '.join(cat.extraction_targets)}")
        lines.append(f"  示例模式:")
        for pat in cat.example_patterns:
            lines.append(f"    - {pat}")

    lines.append("\n### 输出要求")
    lines.append("- 将定性叙事洞察转化为可量化的因子假设")
    lines.append("- 明确因子的 applicable_regimes 和 invalid_regimes")
    lines.append("- 说明从叙事到因子的传导逻辑")

    return "\n".join(lines)


def build_subspace_context(
    subspace: ExplorationSubspace,
    registry: SubspaceRegistry,
    factor_pool: Optional[FactorPool] = None,
    island: str = "",
) -> str:
    """分发器：根据子空间类型调用对应的 context builder"""
    builders = {
        ExplorationSubspace.FACTOR_ALGEBRA: lambda: build_factor_algebra_context(registry, island),
        ExplorationSubspace.SYMBOLIC_MUTATION: lambda: build_symbolic_mutation_context(registry, factor_pool, island),
        ExplorationSubspace.CROSS_MARKET: lambda: build_cross_market_context(registry),
        ExplorationSubspace.NARRATIVE_MINING: lambda: build_narrative_mining_context(registry),
    }
    builder = builders.get(subspace)
    if builder:
        return builder()
    return f"未知子空间: {subspace.value}"