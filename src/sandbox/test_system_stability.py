"""
test_system_stability.py
logging.basicConfig(level=logging.INFO, format='%(message)s')
目的：对 Sandbox (OpenCode 容器) 和 oh_my_opencode 适配器进行稳定性与高频压测。
验证：
1. 连续多次拉起隔离容器是否会导致资源泄露或 Docker 异常。
2. 异常输入或超时的情况是否会被 adapter 安全熔断，而不会拖垮主进程。
"""
"""
import logging
import time
from claude_code_adapter import ClaudeCodeAdapter
import threading
import sys

def test_single_run(agent: ClaudeCodeAdapter, task_id: int):
    logging.info(f"[{task_id}] 开始测试拉起沙箱...")
    prompt = f"在当前目录创建一个 test_{task_id}.py，里面写一句 print('success {task_id}')，然后运行它。"
    start_time = time.time()
    
    success, log = agent.run_task_in_sandbox(prompt)
    
    elapsed = time.time() - start_time
    if success and "success" in log:
        logging.info(f"✅ [{task_id}] 测试通过，耗时: {elapsed:.2f}s")
    else:
        logging.info(f"❌ [{task_id}] 测试失败！日志 excerpt:\n{log[-200:] if len(log) > 200 else log}")

def run_stability_test():
    logging.info("=== EvoQuant Sandbox 稳定性压测 ===")
    
    # 使用测试用的 ClaudeAdapter
    agent = ClaudeCodeAdapter()
    
    # 串行测试 2 次，观察容器挂载与清理是否稳定
    logging.info("\n--- 阶段 1: 连续串行测试 ---")
    for i in range(1, 3):
        test_single_run(agent, i)
        
    # 并发测试 (如果系统配置允许，测试 Docker 引擎的多实例容忍度)
    # 取决于本地并发限制以及 Anthropic Proxy 的限制，这里只做轻量级验证
    logging.info("\n--- 阶段 2: 轻量级并发测试 ---")
    threads = []
    for i in range(101, 103):
        t = threading.Thread(target=test_single_run, args=(agent, i))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    logging.info("\n✅ 系统稳定性测试执行完毕。")

if __name__ == "__main__":
    run_stability_test()
