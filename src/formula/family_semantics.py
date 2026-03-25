from __future__ import annotations

from collections.abc import Iterable
from typing import Final

FACTOR_ALGEBRA_FAMILY_SEMANTICS: Final[dict[str, dict[str, str]]] = {
    "mean_spread": {
        "allowed": "只能描述均价/均线差、价差扩张或收敛。",
        "forbidden": "不要写成收益率变化、相对收益差或动量加速度。",
    },
    "ratio_momentum": {
        "allowed": "只能描述长短窗口相对强弱、比值动量、短强长弱。",
        "forbidden": "不要写成均线差、均价差或纯价差扩张。",
    },
    "volatility_state": {
        "allowed": "只能描述长短窗口波动状态变化。",
        "forbidden": "不要写成价格动量、收益率变化，或“用波动率标准化动量”。",
    },
    "volume_confirmation": {
        "allowed": "必须明确描述成交量/流动性对价格信号的确认；当前 canonical form 是量价差值确认。",
        "forbidden": "不要写成相对成交量变化、量能比、generic momentum 或趋势延续。",
    },
}


def get_factor_algebra_family_semantics(transform_family: str) -> dict[str, str] | None:
    return FACTOR_ALGEBRA_FAMILY_SEMANTICS.get(transform_family)


def render_factor_algebra_family_semantics_block(
    allowed_families: Iterable[str] | None = None,
) -> str:
    allowed = set(allowed_families) if allowed_families is not None else None
    lines = ["## family 语义对齐（必须遵守）"]
    for family, semantics in FACTOR_ALGEBRA_FAMILY_SEMANTICS.items():
        if allowed is not None and family not in allowed:
            continue
        lines.append(f"- `{family}`")
        lines.append(f"  - {semantics['allowed']}")
        lines.append(f"  - {semantics['forbidden']}")
    return "\n".join(lines)
