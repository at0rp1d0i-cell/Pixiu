"""
EvoQuant: Coder Agent (Sandbox Environment)
logging.basicConfig(level=logging.INFO, format='%(message)s')
Role: Translates mathematical formulas into Qlib Python code and executes them via OpenCode CLI.
"""
import logging
from src.sandbox.claude_code_adapter import ClaudeCodeAdapter
from .state import AgentState

def coder_node(state: AgentState) -> dict:
    proposal = state.get("factor_proposal", "")
    logging.info(f"\n[Coder Agent] 收到 Researcher 提交的金工因子假设，长度: {len(proposal)} 字符。")
    logging.info("[Coder Agent] 唤醒绝对隔离 Docker 沙箱...")
    
    # Instantiate the adapter
    adapter = ClaudeCodeAdapter()
    
    # Formulate prompt for OpenCode
    # Task: Write a Qlib expression script, inject into dataset, train LightGBM, and output Sharpe.
    prompt = f"""
    作为一名熟练的 Qlib Python 工程师，请根据以下金融假设编写代码并执行回测实验：
    
    核心学术要求：
    {proposal}
    
    任务：
    1. 请读取现有的 Qlib baseline 脚本作为基础结构。
    2. 新建一个 `run_experiment.py`，向其中注入一个新因子（根据上述公式使用字符串表达），例如 `Alpha159: '<your_formula>'`。
    3. 运行模型训练并在 2025-04-01 到 2026-02-24 截面数据上进行 TopK50 评估。
    4. 确保代码不会崩溃，并在控制台打印出含有 "Sharpe Ratio" 或 "夏普比率" 以及 "Cumulative Return" 关键字的结果。
    5. 最后执行该 python 脚本。
    6. 在脚本最后，必须输出一行结构化指标（严格按此格式，不要换行）：
    BACKTEST_METRICS_JSON: {{"sharpe": <值>, "ic": <值>, "icir": <值>, "turnover": <值>, "annualized_return": <值>, "max_drawdown": <值>}}
    若某项指标无法计算，用 0.0 填充。
    
    如果遇到由于 Numpy 或 Pandas 版本的错误，请自主修复，直到屏幕标准输出包含回测结果。
    """
    
    # Execute through Docker sandbox
    success, full_log = adapter.run_task_in_sandbox(prompt)
    
    # We might have 1000s of lines. Let's truncate and capture the end.
    trimmed_log = full_log[-2000:] if len(full_log) > 2000 else full_log
    
    if success:
        return {
            "backtest_result": trimmed_log,
            "error_message": "",
        }
    else:
        return {
            "backtest_result": "",
            "error_message": f"沙箱代码执行崩溃:\n{trimmed_log}"
        }
