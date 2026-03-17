"""
Symbolic Mutation 运行时（Phase 2 子任务 2.4）

包含：
- FormulaNode: Qlib 公式 AST 节点
- QlibFormulaParser: 将 Qlib 函数调用公式解析为 AST
- SymbolicMutator: 对 AST 施加 5 种 MutationOperator

设计原则：
- v1 parser 只支持纯函数调用格式（不含顶层中缀运算符）
- 任何解析或 mutation 失败一律返回 None，不抛异常
- mutation 结果用 MutationResult（内部结构）返回，供 researcher 写入 MutationRecord
"""
from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import List, Optional

from src.schemas.hypothesis import MutationOperator

logger = logging.getLogger(__name__)

# 已知的 Qlib 函数算子（前缀调用形式）
_KNOWN_OPS = {
    "Mean", "Std", "Rank", "Ref", "Corr", "Sum", "Min", "Max",
    "Delta", "Div", "Mul", "Add", "Sub", "Zscore", "Demean",
    "Log", "Abs", "Sign", "Power", "If", "Slope", "Resi",
    "Neutralize",
}

# 窗口参数候选：可以在此范围内轮换
_HORIZON_CANDIDATES = [5, 10, 20, 40, 60, 120]

# Normalization 算子对（互相切换）
_NORM_PAIRS = {
    "Rank": "Zscore",
    "Zscore": "Rank",
    "Demean": "Zscore",
}

# SWAP_FIELD 的替换映射（同类字段互换）
_FIELD_SWAP_MAP = {
    "$close": "$open",
    "$open": "$close",
    "$high": "$close",
    "$low": "$close",
    "$volume": "$amount",
    "$amount": "$volume",
    "$vwap": "$close",
}

# ADD_INTERACTION_TERM 可注入的交叉字段
_INTERACTION_FIELD = "$volume"


# ─────────────────────────────────────────────────────────
# FormulaNode
# ─────────────────────────────────────────────────────────

@dataclass
class FormulaNode:
    """Qlib 公式 AST 节点。

    叶节点（字段或整数）：op 为字段名（如 "$close"）或数字字符串，args 为空。
    函数节点：op 为函数名（如 "Mean"），args 为子节点列表。
    """
    op: str
    args: List["FormulaNode"] = field(default_factory=list)

    def to_formula(self) -> str:
        """将 AST 序列化回 Qlib 公式字符串。"""
        if not self.args:
            return self.op
        args_str = ", ".join(a.to_formula() for a in self.args)
        return f"{self.op}({args_str})"

    def is_leaf(self) -> bool:
        return len(self.args) == 0

    def is_field(self) -> bool:
        return self.is_leaf() and self.op.startswith("$")

    def is_numeric(self) -> bool:
        try:
            float(self.op)
            return True
        except (ValueError, TypeError):
            return False


# ─────────────────────────────────────────────────────────
# QlibFormulaParser
# ─────────────────────────────────────────────────────────

class QlibFormulaParser:
    """将 Qlib 公式字符串解析为 FormulaNode AST。

    v1 只支持纯函数调用格式：Op(arg1, arg2, N)
    遇到顶层中缀运算符（+  -  *  /  不在括号内）直接返回 None。
    """

    # 中缀运算符字符集
    _INFIX_CHARS = set("+-*/")

    def parse(self, formula: str) -> Optional[FormulaNode]:
        """解析公式字符串，返回 AST 或 None。

        None 的含义：公式包含顶层中缀运算符，或语法不符合 v1 支持范围。
        """
        formula = formula.strip()
        if not formula:
            return None
        try:
            if self._has_toplevel_infix(formula):
                return None
            tokens = self._tokenize(formula)
            pos = [0]
            node = self._parse_expr(tokens, pos)
            # 确保所有 token 都被消耗
            if pos[0] < len(tokens):
                logger.debug("QlibFormulaParser: unparsed tokens after pos %d: %s", pos[0], tokens[pos[0]:])
                return None
            return node
        except Exception as e:
            logger.debug("QlibFormulaParser.parse failed for %r: %s", formula, e)
            return None

    # ── 快速检测：顶层中缀运算符 ──────────────────────────

    def _has_toplevel_infix(self, formula: str) -> bool:
        """检测公式是否在顶层（括号深度=0）含有中缀运算符。

        跳过数字中的负号和引号内的内容。
        """
        depth = 0
        i = 0
        while i < len(formula):
            ch = formula[i]
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif depth == 0 and ch in self._INFIX_CHARS:
                # 特殊情况：负号出现在数字之前（如 Ref($close, -5)）
                # 此时它是参数前缀而非二元运算符；但在顶层不可能有合法的前缀负号
                # （因为整个公式要么是函数调用，要么是字段，不会以 - 开头）
                # 安全做法：只要顶层出现 +-*/ 就返回 True
                return True
            i += 1
        return False

    # ── Tokenizer ─────────────────────────────────────────

    def _tokenize(self, formula: str) -> List[str]:
        """将公式字符串切分为 token 列表。

        Token 类型：标识符（含 $前缀）、整数/浮点数字面量、括号、逗号。
        """
        tokens: List[str] = []
        i = 0
        n = len(formula)
        while i < n:
            ch = formula[i]
            if ch in (' ', '\t', '\n'):
                i += 1
                continue
            if ch in ('(', ')', ','):
                tokens.append(ch)
                i += 1
                continue
            # 字段或标识符：以字母、$ 或 _ 开头
            if ch.isalpha() or ch in ('$', '_'):
                j = i + 1
                while j < n and (formula[j].isalnum() or formula[j] in ('_', '$')):
                    j += 1
                tokens.append(formula[i:j])
                i = j
                continue
            # 数字（含前缀负号）：在这里负号只出现在参数位置
            if ch.isdigit() or (ch == '-' and i + 1 < n and (formula[i + 1].isdigit() or formula[i + 1] == '.')):
                j = i + 1
                while j < n and (formula[j].isdigit() or formula[j] == '.'):
                    j += 1
                tokens.append(formula[i:j])
                i = j
                continue
            # 小数点开头的浮点数（如 .5）
            if ch == '.':
                j = i + 1
                while j < n and formula[j].isdigit():
                    j += 1
                tokens.append(formula[i:j])
                i = j
                continue
            # 未知字符：跳过但记录
            logger.debug("QlibFormulaParser: unexpected char %r at pos %d", ch, i)
            i += 1
        return tokens

    # ── 递归下降解析器 ─────────────────────────────────────

    def _parse_expr(self, tokens: List[str], pos: List[int]) -> FormulaNode:
        """解析单个表达式（字段、数字字面量、或函数调用）。"""
        if pos[0] >= len(tokens):
            raise ValueError("Unexpected end of tokens")

        tok = tokens[pos[0]]
        pos[0] += 1

        # 数字字面量（含负数）
        try:
            float(tok)
            return FormulaNode(op=tok)
        except ValueError:
            pass

        # 字段（$xxx）
        if tok.startswith("$"):
            return FormulaNode(op=tok)

        # 函数调用：标识符后跟 "("
        if pos[0] < len(tokens) and tokens[pos[0]] == "(":
            pos[0] += 1  # consume "("
            args = self._parse_args(tokens, pos)
            if pos[0] >= len(tokens) or tokens[pos[0]] != ")":
                raise ValueError(f"Expected ')' after args of {tok}, got: {tokens[pos[0]:pos[0]+3]}")
            pos[0] += 1  # consume ")"
            return FormulaNode(op=tok, args=args)

        # 裸标识符（无括号），视为字段的简写（不常见，但容错）
        return FormulaNode(op=tok)

    def _parse_args(self, tokens: List[str], pos: List[int]) -> List[FormulaNode]:
        """解析逗号分隔的参数列表，直到遇到 ")" 为止。"""
        args: List[FormulaNode] = []
        # 空参数列表
        if pos[0] < len(tokens) and tokens[pos[0]] == ")":
            return args
        while True:
            arg = self._parse_expr(tokens, pos)
            args.append(arg)
            if pos[0] >= len(tokens):
                break
            if tokens[pos[0]] == ")":
                break
            if tokens[pos[0]] == ",":
                pos[0] += 1  # consume ","
                continue
            break
        return args


# ─────────────────────────────────────────────────────────
# MutationResult（内部传输对象，不是 schema）
# ─────────────────────────────────────────────────────────

@dataclass
class MutationResult:
    """一次 mutation 操作的结果（内部使用，不写入持久化 schema）。"""
    operator: MutationOperator
    source_formula: str
    result_formula: str
    description: str


# ─────────────────────────────────────────────────────────
# SymbolicMutator
# ─────────────────────────────────────────────────────────

class SymbolicMutator:
    """对 Qlib 公式 AST 施加 MutationOperator。

    所有公开方法失败时返回 None，不抛异常。
    """

    def mutate(
        self,
        formula: str,
        operator: MutationOperator,
        pool=None,   # FactorPool | None，保持接口一致但 v1 不使用
    ) -> Optional[MutationResult]:
        """对 formula 施加 operator，返回 MutationResult 或 None。

        None 表示：公式不支持该 operator，或解析失败。
        """
        try:
            parser = QlibFormulaParser()
            ast = parser.parse(formula)
            if ast is None:
                return None

            mutated = self._apply(ast, operator)
            if mutated is None:
                return None

            result_formula = mutated.to_formula()
            if result_formula == formula:
                # 变异无效果（防止生成完全相同的公式）
                return None

            return MutationResult(
                operator=operator,
                source_formula=formula,
                result_formula=result_formula,
                description=self._describe(operator, formula, result_formula),
            )
        except Exception as e:
            logger.debug("SymbolicMutator.mutate failed: formula=%r op=%s err=%s", formula, operator, e)
            return None

    # ── Operator 分发 ────────────────────────────────────

    def _apply(self, node: FormulaNode, op: MutationOperator) -> Optional[FormulaNode]:
        match op:
            case MutationOperator.SWAP_HORIZON:
                return self._swap_horizon(node)
            case MutationOperator.CHANGE_NORMALIZATION:
                return self._change_normalization(node)
            case MutationOperator.REMOVE_OPERATOR:
                return self._remove_outer_operator(node)
            case MutationOperator.ADD_OPERATOR:
                return self._add_cross_section_wrapper(node)
            case MutationOperator.ALTER_INTERACTION:
                return self._add_interaction_term(node)
            case _:
                return None

    # ── SWAP_HORIZON ─────────────────────────────────────

    def _swap_horizon(self, node: FormulaNode) -> Optional[FormulaNode]:
        """将公式中第一个找到的窗口参数替换为下一个候选值。

        策略：在 _HORIZON_CANDIDATES 中取当前窗口的"下一个更大值"，
        若已是最大值则取最小值（循环）。
        """
        result = copy.deepcopy(node)
        changed = [False]
        self._swap_horizon_inplace(result, changed)
        return result if changed[0] else None

    def _swap_horizon_inplace(self, node: FormulaNode, changed: List[bool]) -> None:
        if changed[0]:
            return
        for i, arg in enumerate(node.args):
            if changed[0]:
                return
            if arg.is_numeric():
                try:
                    val = int(float(arg.op))
                    new_val = self._next_horizon(val)
                    if new_val != val:
                        node.args[i] = FormulaNode(op=str(new_val))
                        changed[0] = True
                        return
                except (ValueError, TypeError):
                    pass
            else:
                self._swap_horizon_inplace(arg, changed)

    def _next_horizon(self, current: int) -> int:
        """返回 _HORIZON_CANDIDATES 中 current 的下一个候选（循环）。"""
        candidates = _HORIZON_CANDIDATES
        # 找最近的候选
        for i, c in enumerate(candidates):
            if c == current:
                return candidates[(i + 1) % len(candidates)]
        # 不在标准候选中：找下一个更大的候选
        for c in candidates:
            if c > current:
                return c
        return candidates[0]

    # ── CHANGE_NORMALIZATION ─────────────────────────────

    def _change_normalization(self, node: FormulaNode) -> Optional[FormulaNode]:
        """将最外层归一化算子在 Rank / Zscore / Demean 之间切换。"""
        target = _NORM_PAIRS.get(node.op)
        if target is None:
            return None
        result = copy.deepcopy(node)
        result.op = target
        return result

    # ── REMOVE_OPERATOR ──────────────────────────────────

    def _remove_outer_operator(self, node: FormulaNode) -> Optional[FormulaNode]:
        """移除最外层一元算子，返回其第一个非数字子节点。

        例：Rank($close) → $close
            Mean($close, 5) → $close（取第一个非数字子节点）
        """
        if node.is_leaf():
            return None
        # 找第一个非数字的子节点作为内容节点
        for arg in node.args:
            if not arg.is_numeric():
                return copy.deepcopy(arg)
        return None

    # ── ADD_OPERATOR（ADD_CROSS_SECTION_WRAPPER）────────

    def _add_cross_section_wrapper(self, node: FormulaNode) -> Optional[FormulaNode]:
        """在公式外包裹一层 Rank（截面标准化）。

        若最外层已是 Rank，则改为 Zscore（避免 Rank(Rank(...)) 冗余）。
        """
        if node.op == "Rank":
            # 改 Rank 为 Zscore（避免双重 Rank）
            return FormulaNode(op="Zscore", args=[copy.deepcopy(node.args[0])] if node.args else [])
        return FormulaNode(op="Rank", args=[copy.deepcopy(node)])

    # ── ALTER_INTERACTION ────────────────────────────────

    def _add_interaction_term(self, node: FormulaNode) -> Optional[FormulaNode]:
        """添加与成交量的交叉项：Mul(原公式, Rank($volume))。

        若公式已经是 Mul 节点且参数数量为 2，则尝试替换第二个参数为 Rank($volume)。
        """
        volume_rank = FormulaNode(
            op="Rank",
            args=[FormulaNode(op=_INTERACTION_FIELD)],
        )
        if node.op == "Mul" and len(node.args) == 2:
            # 已有 Mul：替换第二个 arg
            result = copy.deepcopy(node)
            result.args[1] = volume_rank
            return result
        # 包裹为 Mul
        return FormulaNode(op="Mul", args=[copy.deepcopy(node), volume_rank])

    # ── Description ──────────────────────────────────────

    def _describe(self, op: MutationOperator, src: str, result: str) -> str:
        desc_map = {
            MutationOperator.SWAP_HORIZON: f"时间窗口变异: {src} → {result}",
            MutationOperator.CHANGE_NORMALIZATION: f"归一化切换: {src} → {result}",
            MutationOperator.REMOVE_OPERATOR: f"移除外层算子: {src} → {result}",
            MutationOperator.ADD_OPERATOR: f"添加截面算子: {src} → {result}",
            MutationOperator.ALTER_INTERACTION: f"添加交叉项: {src} → {result}",
        }
        return desc_map.get(op, f"{op.value}: {src} → {result}")


# ─────────────────────────────────────────────────────────
# 工具函数：供 researcher 直接调用
# ─────────────────────────────────────────────────────────

def try_all_mutations(
    formula: str,
    mutator: Optional[SymbolicMutator] = None,
) -> List[MutationResult]:
    """对一个公式尝试所有 MutationOperator，返回成功的变异结果列表。"""
    if mutator is None:
        mutator = SymbolicMutator()
    results = []
    for op in MutationOperator:
        r = mutator.mutate(formula, op)
        if r is not None:
            results.append(r)
    return results


def build_mutation_record_dict(result: MutationResult) -> dict:
    """将 MutationResult 转换为 FactorResearchNote.mutation_record 字段的 dict 格式。

    格式与 MutationRecord schema 兼容：
      source_factor_id, operator, parameter_change, result_formula
    """
    return {
        "operator": result.operator.value,
        "source_formula": result.source_formula,
        "result_formula": result.result_formula,
        "description": result.description,
    }
