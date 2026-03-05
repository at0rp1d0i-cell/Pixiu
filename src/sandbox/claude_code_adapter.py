"""
claude_code_adapter.py
logging.basicConfig(level=logging.INFO, format='%(message)s')
EvoQuant: Claude Code CLI 的 Python 适配器层。
它充当 LangGraph 主控程序与只读安全沙箱内的 Claude Code 之间的桥梁。
"""
import logging
import os
import subprocess
import tempfile
import uuid
from typing import Dict, Any, Tuple

class ClaudeCodeAdapter:
    def __init__(self, 
                 api_key: str = None, 
                 base_url: str = None):
        """
        初始化适配器。通过本地代理转发 Anthropic SDK 到 DeepSeek API。
        默认读取环境变量的 ANTHROPIC_API_KEY / BASE_URL，如果在独立子进程跑，
        默认 Fallback 到已知的 Antigravity Manager 代理。
        """
        from dotenv import load_dotenv
        load_dotenv()
        
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "sk-sp-0dac931568b84375b3af8f67946b8a20")
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL", "https://coding.dashscope.aliyuncs.com/apps/anthropic")
        self.model = os.environ.get("CODER_MODEL", "glm-5")
        
        self.host_project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        self.host_data_dir = os.path.join(self.host_project_root, "data", "qlib_bin")
        self.host_workspace_dir = os.path.join(self.host_project_root, "sandbox_workspace")
        self.host_skills_dir = os.path.join(self.host_project_root, "knowledge", "agent_skills")
        
        os.makedirs(self.host_workspace_dir, exist_ok=True)
        os.makedirs(self.host_skills_dir, exist_ok=True)
    
    def _build_claude_command(self, task_prompt: str) -> list[str]:
        """
        组装 claude code非交互指令。引入了对 /app/skills/coder_qlib_debugging.md 的显式要求。
        """
        import shlex
        enhanced_prompt = f"请先阅读 /app/skills/coder_qlib_debugging.md 了解调试与防护思想。\n\n任务内容：\n{task_prompt}"
        quoted_prompt = shlex.quote(enhanced_prompt)
        cmd = [
            "claude",
            "--dangerously-skip-permissions",
            "--model", self.model,
            "-p",
            quoted_prompt
        ]
        return cmd
    
    def run_task_in_sandbox(self, researcher_task: str, context_files: list = []) -> Tuple[bool, str]:
        """
        将 Researcher 的研究任务包装后，送入 Docker 沙箱由 Claude Code 执行。
        """
        import json
        
        container_name = f"evoquant_coder_sandbox_{uuid.uuid4().hex[:8]}"
        claude_cmd_list = self._build_claude_command(researcher_task)
        claude_cmd_str = " ".join(claude_cmd_list)
        
        # 初始化现有 MCP 的脚手架 (例如加载 filesystem)
        # 这里用逻辑与串联，claude -p 运行完成后 sandbox_script 退出
        sandbox_script = f"cd /app/workspace && claude mcp add filesystem -- /bin/bash -c 'echo \"MCP Filesystem Initialized\"' && {claude_cmd_str}"
        
        # 支持从环境变量读取代理配置传入容器
        anthropic_key = self.api_key
        anthropic_url = self.base_url
        
        # 为了使用 --dangerously-skip-permissions，Docker必须不由 root 运行
        current_uid = os.getuid()
        current_gid = os.getgid()
        
        docker_cmd = [
            "docker", "run", "--rm",
            "--network", "host",
            "--name", container_name,
            "-u", f"{current_uid}:{current_gid}",
            "-e", "HOME=/app/workspace",
            "-e", f"ANTHROPIC_API_KEY={anthropic_key}",
            "-e", f"ANTHROPIC_BASE_URL={anthropic_url}",
            "-v", f"{self.host_data_dir}:/app/data:ro",
            "-v", f"{self.host_workspace_dir}:/app/workspace:rw",
            "-v", f"{self.host_skills_dir}:/app/skills:ro",
            "evoquant-coder:latest",
            "/bin/bash", "-c", sandbox_script
        ]
        
        logging.info(f"🚀 [ClaudeCodeAdapter] 唤醒沙箱容器: {container_name}")
        logging.info(f"   执行指令: {claude_cmd_str[:100]}...")
        
        try:
            # 设定 5 分钟超时限制
            result = subprocess.run(
                docker_cmd,
                capture_output=True,
                text=True,
                timeout=300
            )
            
            output_log = result.stdout + "\n" + result.stderr
            success = result.returncode == 0
            
            logging.info(f"✅ [ClaudeCodeAdapter] 沙箱执行完毕。Return Code: {result.returncode}")
            return success, output_log
            
        except subprocess.TimeoutExpired:
            logging.info(f"❌ [ClaudeCodeAdapter] 沙箱执行严重超时 (超过 5 分钟无响应)。")
            logging.info(f"⚠️ [系统断言] 这通常意味着底层模型 API 严重拥堵或服务无响应。")
            subprocess.run(["docker", "kill", container_name], capture_output=True)
            return False, "TIMEOUT: The agent API took too long to respond (System halted after 5 minutes). Please check your Model Provider's server status."
        except Exception as e:
            return False, f"SANDBOX ERROR: {str(e)}"

# ================= 测试代码 =================
if __name__ == "__main__":
    logging.info("Initializing ClaudeCodeAdapter (Dry Run)...")
    agent = ClaudeCodeAdapter()
    
    # 构建一个假的 Researcher 任务
    demo_task = "请在这个目录创建一个 hello.py，打印 'Hello from Coder Sandbox', 并运行它把结果保存到 log.txt 中。"
    
    # 打印将要执行的 Docker 命令和内部脚本
    cmd = agent._build_claude_command(demo_task)
    logging.info("\n[Mock] Internal Claude CLI Command:")
    logging.info(cmd)
    
    logging.info("\n[Mock] Host Workspace Directory:")
    logging.info(agent.host_workspace_dir)
    logging.info("\n✅ Adapter is ready for integration!")
