import asyncio
import tempfile
import os
from dataclasses import dataclass
from pathlib import Path
import time

@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    returncode: int
    duration_seconds: float

class DockerRunner:
    """
    在 pixiu-coder Docker 容器中执行 Python 脚本。
    使用 subprocess，不依赖任何 LLM。
    """
    DEFAULT_IMAGE = "pixiu-coder:latest"
    
    PROJECT_ROOT = Path(__file__).resolve().parents[2]
    _qlib_env = os.getenv("QLIB_DATA_DIR")
    if _qlib_env:
        _qlib_path = Path(_qlib_env) if os.path.isabs(_qlib_env) else PROJECT_ROOT / _qlib_env
    else:
        _qlib_path = PROJECT_ROOT / "data" / "qlib_bin"
    QLIB_DATA_PATH = str(_qlib_path)

    def __init__(self, image: str | None = None):
        self.image = image or os.getenv("PIXIU_DOCKER_IMAGE", self.DEFAULT_IMAGE)

    async def run_python(
        self,
        script: str,
        timeout_seconds: int = 600,
    ) -> ExecutionResult:
        # 写入临时文件，使用 utf-8 编码，保留后缀 .py
        with tempfile.NamedTemporaryFile(suffix=".py", mode="w", encoding="utf-8", delete=False) as f:
            f.write(script)
            script_path = f.name

        start = time.time()
        try:
            # 兼容 Windows Docker 的 volume mount，通常 str(Path) 可以正常挂载
            proc = await asyncio.create_subprocess_exec(
                "docker", "run", "--rm",
                "--network=none",               # 无网络访问
                "-v", f"{self.QLIB_DATA_PATH}:/data/qlib_bin:ro",  # 只读数据
                "-v", f"{script_path}:/tmp/script.py:ro",
                "--memory=2g",                  # 内存限制
                "--cpus=2.0",                   # CPU 限制
                self.image,
                "python", "/tmp/script.py",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    proc.communicate(),
                    timeout=timeout_seconds,
                )
                
                # 兼容 Windows 环境的输出换行符
                stdout_str = stdout_data.decode("utf-8", errors="replace").replace("\r\n", "\n")
                stderr_str = stderr_data.decode("utf-8", errors="replace").replace("\r\n", "\n")
                
                return ExecutionResult(
                    success=(proc.returncode == 0),
                    stdout=stdout_str,
                    stderr=stderr_str,
                    returncode=proc.returncode or 0,
                    duration_seconds=time.time() - start,
                )
            except asyncio.TimeoutError:
                # 尝试强制关闭
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"执行超时（>{timeout_seconds}s）",
                    returncode=-1,
                    duration_seconds=timeout_seconds,
                )
        finally:
            if os.path.exists(script_path):
                try:
                    os.unlink(script_path)
                except Exception:
                    pass
