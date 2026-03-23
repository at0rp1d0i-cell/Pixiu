"""
Pixiu: Formula Validator Node
logging.basicConfig(level=logging.INFO, format='%(message)s')
Role: Performs lightweight static analysis on the Researcher's generated Qlib factors
to prevent obvious syntax errors from wasting Sandbox execution time.
"""
import logging
import re
from typing import Any, Dict

def _check_no_future_leak(formula: str) -> tuple[bool, str]:
    """检查 Ref() 是否使用了负数偏移（未来数据）。"""
    if re.search(r'Ref\s*\([^)]+,\s*-\d+', formula):
        return False, "[Validator 拦截] 检测到 Ref() 使用负数偏移（未来数据），这会引入前视偏差。请使用正整数偏移。"
    return True, ""


def _check_valid_fields(formula: str) -> tuple[bool, str]:
    """检查 $ 字段名是否合法。"""
    valid_fields = {"open", "high", "low", "close", "volume", "vwap", "factor"}
    # 找出所有 $xxx 形式的字段名
    used_fields = re.findall(r'\$(\w+)', formula)
    invalid = [f for f in used_fields if f not in valid_fields]
    if invalid:
        return False, f"[Validator 拦截] 使用了不存在的字段：{invalid}。合法字段：{sorted(valid_fields)}"
    return True, ""


def _check_log_safety(formula: str) -> tuple[bool, str]:
    """检查 Log() 的参数是否可能为负。"""
    # 检测 Log($close - ...) 或 Log($close/Ref... - 1) 等危险模式
    if re.search(r'Log\s*\(\s*\$\w+\s*[-]', formula):
        return False, "[Validator 拦截] Log() 的参数可能非正，请改写为可证明正值域的表达式。"
    return True, ""

def validator_node(state: Any) -> dict:
    logging.info("\n[Validator Node] 对生成的 Qlib 公式进行轻量级静态语法检测...")
    proposal = state.get("factor_proposal", "")
    
    # 模拟一个非常基础的验证逻辑
    # 在真实环境中，你可以使用 `pyqlib` 的 eval 逻辑进行 ast 解析
    
    errors = []
    
    # 检测极端的括号不匹配
    if proposal.count('(') != proposal.count(')'):
        errors.append("语法错误: 左右括号 '(' 和 ')' 的数量不匹配。")
        
    if proposal.count('[') != proposal.count(']'):
        errors.append("语法错误: 左右方括号 '[' 和 ']' 的数量不匹配。")
        
    # 检测公式是否过短，防止意外回复
    # (如果 LLM 仅回复了自然语言却没有公式，这可以拦截大半)
    # 此处假设我们强行要求返回至少包含常见算子的符号如 '$', 'Ref', 'Mean'
    # 待业务复杂后可替换为真正的正则提取并验证 Formula 块
    
    if errors:
        error_msg = "[Validator 拦截] 你的公式包含低级语法错误：\n" + "\n".join(errors)
        logging.info(f"❌ {error_msg}")
        return {
            "error_message": error_msg,
            "backtest_result": "" # 清空上一次的，防止干扰
        }

    # A 股硬约束检查
    formula = ""
    hypothesis = state.get("factor_hypothesis")
    if hypothesis:
        formula = hypothesis.formula

    if formula:
        for check_fn in [_check_no_future_leak, _check_valid_fields, _check_log_safety]:
            ok, err_msg = check_fn(formula)
            if not ok:
                return {
                    "error_message": err_msg,
                    "factor_proposal": state.get("factor_proposal", ""),
                }
        
    logging.info("✅ [Validator Node] 语法静态检查通过，放行至 Coder沙箱。")
    return {
        "error_message": "" # Clear previous errors
    }

def route_validation(state: Any) -> str:
    """
    决定流程是走向 Coder 还是打回给 Researcher
    """
    if state.get("error_message") and "[Validator 拦截]" in state["error_message"]:
        return "loop_to_researcher"
    return "proceed_to_coder"
