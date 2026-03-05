"""
test_researcher_coder.py
logging.basicConfig(level=logging.INFO, format='%(message)s')
模拟 Researcher -> Coder(OpenCode) 的闭环测试。
"""
import logging
import os
from claude_code_adapter import ClaudeCodeAdapter

def run_test():
    logging.info("=== EvoQuant Researcher -> Coder Feasibility Test ===")
    
    # 模拟 Researcher 提出的简单假设和指令
    researcher_prompt = """
    你是一个自动量化交易终端。现在我们在测试环境。
    请你在当前目录下创建一个名为 `hello_quant.py` 的文件。
    该文件内部包含一个简单的函数 `calculate_ma(prices, period)`，输入价格列表和周期，返回移动平均线值。
    打印测试结果 `calculate_ma([1, 2, 3, 4, 5], 3)` 到控制台。
    然后运行它，确保它工作。
    """
    
    logging.info("\n[Researcher] 派发任务给 Coder:")
    logging.info(researcher_prompt.strip())
    
    # 初始化 ClaudeAdapter
    agent = ClaudeCodeAdapter()
    
    # 启动沙箱执行
    success, output_log = agent.run_task_in_sandbox(researcher_prompt)
    
    logging.info("\n=== Coder 执行结果 ===")
    logging.info(output_log)
    
    # 检查沙箱工作区确实生成了文件
    host_target_file = os.path.join(agent.host_workspace_dir, "hello_quant.py")
    if os.path.exists(host_target_file):
        logging.info(f"\n✅ 验证成功: 文件已在外部被写入至 {host_target_file}")
        with open(host_target_file, "r") as f:
            logging.info("\n----- 生成的代码 -----")
            logging.info(f.read())
    else:
        logging.info("\n❌ 验证失败: 目标文件未创建。")

if __name__ == "__main__":
    run_test()
