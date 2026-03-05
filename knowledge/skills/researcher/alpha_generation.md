# Alpha Factor Generation Guidelines

**Role Context**: You are generating Alpha factors for a Qlib-based LightGBM model. 
This skill document outlines the critical thinking process and constraints you must adhere to.

## 1. Syntax Constraints
- You MUST output a strictly valid Qlib formula.
- Do NOT make syntax errors like mismatched parentheses `(` and `)` or brackets `[` and `]`.
- Always verify your formula syntactically before outputting.

## 2. Factor Engineering First Principles
- Focus on linear and non-linear combinations of price, volume, and volatility.
- Over-complexity leads to overfitting. Prefer mathematically sound concepts rather than deeply nested unreadable logic.
- Consider cross-sectional standardizations when appropriate using Qlib operators like `CSRank()`.
- Shift operations: Use `$close` vs `Ref($close, 1)` to represent momentum or return. Be very careful to avoid future data leakage (i.e., do not use tomorrow's data `Ref($close, -1)`).

## 3. Explaining the "Why"
- For every proposed factor, explain the economic or statistical rationale behind it. Why would this factor predict future returns?
- Do not just write what the math is doing; explain *why* it gives an edge in the A-share market.
